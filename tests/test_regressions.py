"""Regression tests for the defects fixed in 0.1.2.

Each test here failed against 0.1.1. They are grouped in one file because they
were found in a single audit pass; each names the behaviour it pins down.
"""
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from dataprocessing._serialise import df_to_json, to_native
from dataprocessing.analyse import (
    detect_outliers, distribution, full_report, summary_stats,
)
from dataprocessing.api import app
from dataprocessing.clean import (
    clean_all, drop_nulls, fix_types, remove_duplicates, remove_outliers,
    standardise_columns,
)
from dataprocessing.transform import add_column, filter_rows, group_and_aggregate
from dataprocessing.visualise import correlation_heatmap, histogram, line_chart

client = TestClient(app)


def tool_result(raw):
    """Return a tool's payload, whichever mcp version produced it.

    call_tool has returned three different shapes across the range this package
    supports, and the server works on all of them — only the tests need to care:

    - mcp 2.x      a CallToolResult, payload under .structured_content["result"]
    - mcp ~1.10+   a (content, {"result": ...}) tuple
    - mcp 1.2.0    just [TextContent]; structured output did not exist yet, so
                   the payload is the JSON text the tool serialised to
    """
    if hasattr(raw, "structured_content"):  # mcp >= 2.0
        return raw.structured_content["result"]
    if len(raw) == 2 and isinstance(raw[1], dict):  # mcp ~1.10+
        return raw[1]["result"]
    content = raw[0] if isinstance(raw, (list, tuple)) else raw  # mcp 1.2.0
    return json.loads(content.text)



# --- clean: fix_types destroyed text columns -------------------------------

def test_fix_types_preserves_text_columns():
    # 0.1.1 ran pd.to_datetime(errors="coerce") over every object column, so a
    # column of names became entirely NaT.
    df = pd.DataFrame({"name": ["Ada Lovelace", "Bob Smith", "Cy Jones"]})
    out = fix_types(df)
    assert out["name"].tolist() == ["Ada Lovelace", "Bob Smith", "Cy Jones"]


def test_fix_types_still_converts_real_dates():
    df = pd.DataFrame({"when": ["2024-01-01", "2024-06-15", "2024-12-31"]})
    out = fix_types(df)
    assert pd.api.types.is_datetime64_any_dtype(out["when"])


def test_fix_types_still_converts_numeric_strings():
    df = pd.DataFrame({"n": ["1", "2", "3"]})
    out = fix_types(df)
    assert pd.api.types.is_numeric_dtype(out["n"])


def test_clean_all_preserves_text_end_to_end():
    df = pd.DataFrame({
        "Full Name": ["Ada Lovelace", "Bob Smith", "Cy Jones"],
        "age": [36, 41, 29],
    })
    cleaned = clean_all(df)
    assert cleaned["full_name"].tolist() == ["Ada Lovelace", "Bob Smith", "Cy Jones"]


# --- clean: functions mutated the caller's DataFrame ------------------------

def test_clean_functions_do_not_mutate_caller():
    df = pd.DataFrame({"A B": [1.0, None, 3.0]})
    original_columns = list(df.columns)
    original_rows = len(df)

    drop_nulls(df)
    remove_duplicates(df)
    standardise_columns(df)

    assert list(df.columns) == original_columns
    assert len(df) == original_rows


def test_standardise_columns_handles_non_string_names():
    # A pivot produces integer column labels; col.lower() raised AttributeError.
    df = pd.DataFrame({1: [1], 2: [2]})
    assert list(standardise_columns(df).columns) == ["1", "2"]


def test_standardise_columns_strips_whitespace():
    df = pd.DataFrame({"First Name ": [1]})
    assert list(standardise_columns(df).columns) == ["first_name"]


def test_remove_outliers_rejects_unknown_method():
    # Previously any method other than 'iqr' silently returned the frame intact.
    df = pd.DataFrame({"A": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError):
        remove_outliers(df, method="zscore")


def test_remove_outliers_rejects_non_numeric_column():
    df = pd.DataFrame({"name": ["a", "b", "c"]})
    with pytest.raises(ValueError):
        remove_outliers(df, columns=["name"])


# --- analyse: nulls poisoned every statistic --------------------------------

def test_summary_stats_quartiles_survive_nulls():
    # np.percentile returned NaN for every statistic if one null was present.
    df = pd.DataFrame({"age": [23.0, 35.0, np.nan, 42.0]})
    s = summary_stats(df)["age"]
    assert s["quartiles"]["25%"] is not None
    assert s["quartiles"]["75%"] is not None
    assert s["mean"] == pytest.approx(33.333333, rel=1e-4)


def test_summary_stats_count_excludes_nulls():
    df = pd.DataFrame({"age": [23.0, 35.0, np.nan, 42.0]})
    s = summary_stats(df)["age"]
    assert s["count"] == 3
    assert s["null_count"] == 1


def test_summary_stats_all_null_column():
    df = pd.DataFrame({"age": [np.nan, np.nan]})
    s = summary_stats(df)["age"]
    assert s["count"] == 0
    assert s["mean"] is None


def test_detect_outliers_finds_outlier_despite_nulls():
    # The worst of the null bugs: bounds became NaN, every comparison was
    # False, and the report confidently came back empty.
    df = pd.DataFrame({"age": [23.0, 35.0, np.nan, 42.0, 900.0]})
    assert 4 in detect_outliers(df)["age"]


def test_distribution_survives_nulls():
    df = pd.DataFrame({"age": [23.0, 35.0, np.nan, 42.0]})
    dist = distribution(df, "age", bins=2)
    assert sum(dist["counts"]) == 3


def test_summary_stats_missing_column_raises():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError):
        summary_stats(df, columns=["nope"])


# --- JSON safety across the interface boundary ------------------------------

def test_full_report_is_json_safe_after_to_native():
    df = pd.DataFrame({"age": [23, 35, 42], "city": ["A", "B", "C"]})
    json.dumps(to_native(full_report(df)))  # raised TypeError on numpy int64


def test_to_native_converts_nan_to_none():
    assert to_native({"x": float("nan")}) == {"x": None}


def test_df_to_json_preserves_group_keys():
    # orient="records" drops the index, and group keys live in the index, so
    # both interfaces returned rows nothing could tell apart.
    df = pd.DataFrame({"city": ["A", "A", "B"], "n": [1, 2, 3]})
    grouped = group_and_aggregate(df, "city", {"n": "sum"})
    records = df_to_json(grouped)
    assert records == [{"city": "A", "n": 3}, {"city": "B", "n": 3}]


def test_df_to_json_leaves_plain_index_alone():
    df = pd.DataFrame({"a": [1, 2]})
    assert df_to_json(df) == [{"a": 1}, {"a": 2}]


# --- visualise --------------------------------------------------------------

def test_histogram_survives_nulls():
    df = pd.DataFrame({"age": [23.0, 35.0, np.nan, 42.0]})
    spec = histogram(df, "age", bins=2)
    assert sum(row["count"] for row in spec["data"]["values"]) == 3


def test_histogram_description_names_the_column():
    # The description was the literal string "Histogram of <column>".
    df = pd.DataFrame({"age": [23, 35, 42]})
    assert histogram(df, "age")["description"] == "Histogram of age"


def test_line_chart_emits_no_nan():
    df = pd.DataFrame({"t": [1, 2, 3], "y": [1.0, np.nan, 3.0]})
    spec = line_chart(df, "t", "y")
    assert "NaN" not in json.dumps(spec["data"]["values"])
    assert len(spec["data"]["values"]) == 2


def test_correlation_heatmap_rejects_named_non_numeric_column():
    # Previously surfaced as "could not convert string to float: 'x'", which
    # names neither the column nor the real problem.
    df = pd.DataFrame({"a": [1, 2, 3], "name": ["x", "y", "z"]})
    with pytest.raises(ValueError, match="name"):
        correlation_heatmap(df, columns=["a", "name"])


def test_visualise_missing_column_raises_valueerror():
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError):
        histogram(df, "nope")


# --- transform --------------------------------------------------------------

def test_filter_rows_missing_column_raises_valueerror():
    # Was a bare KeyError, which the API turned into a 500.
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError):
        filter_rows(df, "nope", "gt", 1)


def test_filter_rows_bad_operator_lists_valid_ones():
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError, match="contains"):
        filter_rows(df, "a", "roughly", 1)


def test_add_column_does_not_mutate_caller():
    df = pd.DataFrame({"price": [10.0, 20.0]})
    add_column(df, "with_vat", "price * 1.2")
    assert "with_vat" not in df.columns


def test_add_column_still_rejects_arbitrary_code():
    df = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(Exception):
        add_column(df, "evil", '__import__("os").getcwd()')


# --- REST API ---------------------------------------------------------------

def test_clean_endpoint_honours_remove_outliers():
    # The flag was declared on the request model and never read.
    rows = [{"a": v} for v in [1.0, 2.0, 3.0, 4.0, 1000.0]]
    kept = client.post("/clean", json={"data": rows, "remove_outliers": False})
    dropped = client.post("/clean", json={"data": rows, "remove_outliers": True})
    assert kept.json()["rows"] == 5
    assert dropped.json()["rows"] == 4


def test_transform_bad_column_is_client_error():
    response = client.post("/transform", json={
        "data": [{"a": 1}],
        "operation": "filter_rows",
        "params": {"column": "nope", "operator": "gt", "value": 0},
    })
    assert response.status_code == 400


def test_transform_group_and_aggregate_keeps_keys_over_http():
    response = client.post("/transform", json={
        "data": [{"city": "A", "n": 1}, {"city": "A", "n": 2}, {"city": "B", "n": 3}],
        "operation": "group_and_aggregate",
        "params": {"group_by": "city", "aggregations": {"n": "sum"}},
    })
    assert response.status_code == 200
    assert response.json()["data"] == [{"city": "A", "n": 3}, {"city": "B", "n": 3}]


def test_analyse_endpoint_with_nulls_and_text():
    response = client.post("/analyse", json={
        "data": [{"age": 23, "city": "A"}, {"age": None, "city": "B"}, {"age": 900, "city": "A"}],
    })
    assert response.status_code == 200
    assert response.json()["summary_stats"]["age"]["count"] == 2


# --- MCP server -------------------------------------------------------------

async def test_mcp_analyse_data_returns_serialisable_result():
    # This tool failed for every input: "Unable to serialize unknown type:
    # numpy.int64". api.py had the to_native fix; mcp_server.py never got it.
    from dataprocessing import mcp_server

    result = await mcp_server.mcp.call_tool(
        "analyse_data", {"data": [{"age": 23}, {"age": 35}, {"age": 42}]}
    )
    assert "summary_stats" in tool_result(result)


async def test_mcp_visualise_data_returns_serialisable_result():
    from dataprocessing import mcp_server

    result = await mcp_server.mcp.call_tool(
        "visualise_data",
        {"data": [{"city": "A"}, {"city": "A"}, {"city": "B"}],
         "chart": "bar_chart", "params": {"column": "city"}},
    )
    json.dumps(tool_result(result))


async def test_mcp_transform_exposes_pivot():
    # pivot was wired into the REST API but missing from the MCP tool's map.
    from dataprocessing import mcp_server

    result = await mcp_server.mcp.call_tool(
        "transform_data",
        {"data": [{"city": "A", "q": "x", "n": 1}, {"city": "B", "q": "x", "n": 3}],
         "operation": "pivot",
         "params": {"index": "city", "columns": "q", "values": "n"}},
    )
    assert tool_result(result)["rows"] == 2


async def test_mcp_group_and_aggregate_keeps_keys():
    from dataprocessing import mcp_server

    result = await mcp_server.mcp.call_tool(
        "transform_data",
        {"data": [{"city": "A", "n": 1}, {"city": "A", "n": 2}, {"city": "B", "n": 3}],
         "operation": "group_and_aggregate",
         "params": {"group_by": "city", "aggregations": {"n": "sum"}}},
    )
    assert tool_result(result)["data"] == [{"city": "A", "n": 3}, {"city": "B", "n": 3}]


# ===========================================================================
# Second hardening pass: merge, pivot, rename, ingest
# ===========================================================================

from dataprocessing.ingest import read_json, read_txt
from dataprocessing.transform import (
    merge_dataframes, pivot, rename_columns, select_columns, sort_rows,
)
from dataprocessing.analyse import correlation_matrix


@pytest.fixture
def left():
    return pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})


@pytest.fixture
def right():
    return pd.DataFrame({"id": [1, 2, 4], "score": [10, 20, 40]})


# --- merge_dataframes -------------------------------------------------------

def test_merge_missing_key_names_the_side(left, right):
    # Was a bare KeyError that said only 'nope', with no hint which frame.
    with pytest.raises(ValueError, match="right frame"):
        merge_dataframes(left, right.drop(columns=["id"]), on="id")
    with pytest.raises(ValueError, match="left frame"):
        merge_dataframes(left.drop(columns=["id"]), right, on="id")


def test_merge_rejects_invalid_how(left, right):
    with pytest.raises(ValueError, match="Invalid how"):
        merge_dataframes(left, right, on="id", how="sideways")


def test_merge_validate_catches_unintended_fan_out():
    # The quiet failure mode of joins: 2 rows x 2 rows silently becomes 4.
    a = pd.DataFrame({"k": [1, 1], "x": ["p", "q"]})
    b = pd.DataFrame({"k": [1, 1], "y": ["r", "s"]})
    assert len(merge_dataframes(a, b, on="k")) == 4          # still allowed
    with pytest.raises(ValueError):                           # now detectable
        merge_dataframes(a, b, on="k", validate="one_to_one")


def test_merge_still_joins_normally(left, right):
    out = merge_dataframes(left, right, on="id")
    assert len(out) == 2
    assert sorted(out.columns) == ["id", "name", "score"]


def test_merge_cross_join_needs_no_key(left, right):
    assert len(merge_dataframes(left, right, on=None, how="cross")) == 9


def test_merge_requires_a_key_when_not_cross(left, right):
    with pytest.raises(ValueError, match="at least one join column"):
        merge_dataframes(left, right, on=None)


# --- pivot ------------------------------------------------------------------

def test_pivot_missing_column_raises_valueerror():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="nope"):
        pivot(df, index="nope", columns="a", values="a")


def test_pivot_non_numeric_values_explains_aggfunc():
    # Was "dtype 'str' does not support operation 'mean'", which names neither
    # the column nor the fix.
    df = pd.DataFrame({"row": ["a", "b"], "col": ["x", "y"], "val": ["p", "q"]})
    with pytest.raises(ValueError, match="aggfunc"):
        pivot(df, index="row", columns="col", values="val")


def test_pivot_non_numeric_values_works_with_first():
    df = pd.DataFrame({"row": ["a", "b"], "col": ["x", "y"], "val": ["p", "q"]})
    out = pivot(df, index="row", columns="col", values="val", aggfunc="first")
    assert out.loc["a", "x"] == "p"


def test_pivot_multiindex_columns_flatten_in_json():
    # to_json stringified each column tuple into a key like "('v1', 'x')".
    df = pd.DataFrame({"row": ["a", "b"], "col": ["x", "y"], "v1": [1, 2], "v2": [3, 4]})
    records = df_to_json(pivot(df, index="row", columns="col", values=["v1", "v2"]))
    assert set(records[0]) == {"row", "v1_x", "v1_y", "v2_x", "v2_y"}
    assert records[0]["row"] == "a" and records[0]["v1_x"] == 1.0


# --- rename_columns / select_columns ---------------------------------------

def test_rename_missing_column_no_longer_silent():
    # Reported success while changing nothing.
    df = pd.DataFrame({"a": [1], "b": [2]})
    with pytest.raises(ValueError, match="nope"):
        rename_columns(df, {"nope": "renamed"})


def test_rename_rejects_resulting_duplicate():
    df = pd.DataFrame({"a": [1], "b": [2]})
    with pytest.raises(ValueError, match="duplicate"):
        rename_columns(df, {"a": "b"})


def test_rename_still_renames():
    df = pd.DataFrame({"a": [1], "b": [2]})
    assert list(rename_columns(df, {"a": "z"}).columns) == ["z", "b"]


def test_rename_rejects_non_dict_mapping():
    with pytest.raises(ValueError, match="dict"):
        rename_columns(pd.DataFrame({"a": [1]}), [("a", "b")])


def test_select_columns_rejects_repeats():
    df = pd.DataFrame({"a": [1], "b": [2]})
    with pytest.raises(ValueError, match="more than once"):
        select_columns(df, ["a", "a"])


def test_df_to_json_rejects_duplicate_columns():
    df = pd.DataFrame([[1, 2]], columns=["a", "a"])
    with pytest.raises(ValueError, match="duplicate"):
        df_to_json(df)


# --- group_and_aggregate ----------------------------------------------------

def test_group_and_aggregate_missing_value_column():
    with pytest.raises(ValueError, match="nope"):
        group_and_aggregate(pd.DataFrame({"g": ["a"]}), "g", {"nope": "sum"})


def test_group_and_aggregate_invalid_function():
    # Was an AttributeError naming SeriesGroupBy, which reads as an internal fault.
    with pytest.raises(ValueError, match="Invalid aggregation"):
        group_and_aggregate(pd.DataFrame({"g": ["a"], "n": [1]}), "g", {"n": "totalise"})


def test_sort_rows_missing_column():
    with pytest.raises(ValueError, match="nope"):
        sort_rows(pd.DataFrame({"a": [1]}), ["nope"])


# --- correlation_matrix -----------------------------------------------------

def test_correlation_matrix_zero_variance_is_json_safe():
    df = pd.DataFrame({"a": [1, 2, 3], "const": [5, 5, 5]})
    corr = correlation_matrix(df)
    assert corr["a"]["const"] is None
    assert "NaN" not in json.dumps(corr)


def test_correlation_matrix_still_correlates():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]})
    assert correlation_matrix(df)["a"]["b"] == pytest.approx(-1.0)


# --- ingest -----------------------------------------------------------------

def test_read_txt_sniffs_tab_delimiter(tmp_path):
    # Both branches of the old ternary read comma-separated data, so a
    # tab-separated file came back as one column.
    path = tmp_path / "t.txt"
    path.write_text("a\tb\n1\t2")
    df = read_txt(str(path))
    assert list(df.columns) == ["a", "b"]


def test_read_txt_honours_explicit_delimiter(tmp_path):
    path = tmp_path / "t.txt"
    path.write_text("a;b\n1;2")
    assert list(read_txt(str(path), delimiter=";").columns) == ["a", "b"]


def test_read_json_flat_object(tmp_path):
    # pd.read_json rejects a single JSON object of scalars.
    path = tmp_path / "one.json"
    path.write_text('{"a": 1, "b": 2}')
    df = read_json(str(path))
    assert df.to_dict("records") == [{"a": 1, "b": 2}]


def test_read_json_list_of_objects_still_works(tmp_path):
    path = tmp_path / "many.json"
    path.write_text('[{"a": 1}, {"a": 2}]')
    assert len(read_json(str(path))) == 2


# --- interface parity -------------------------------------------------------

def test_ingest_endpoint_accepts_txt():
    response = client.post("/ingest", files={"file": ("x.txt", b"a\tb\n1\t2", "text/plain")})
    assert response.status_code == 200
    assert response.json()["columns"] == ["a", "b"]


def test_ingest_endpoint_handles_extensionless_filename():
    response = client.post("/ingest", files={"file": ("myexport", b"a,b\n1,2", "text/csv")})
    assert response.status_code == 400
    assert "Supported" in response.json()["detail"]


def test_transform_pivot_over_http_keeps_index():
    response = client.post("/transform", json={
        "data": [{"row": "a", "col": "x", "v": 1}, {"row": "b", "col": "x", "v": 3}],
        "operation": "pivot",
        "params": {"index": "row", "columns": "col", "values": "v"},
    })
    assert response.status_code == 200
    assert response.json()["data"] == [{"row": "a", "x": 1.0}, {"row": "b", "x": 3.0}]


async def test_mcp_clean_data_offers_outlier_removal():
    from dataprocessing import mcp_server

    rows = [{"a": v} for v in [1.0, 2.0, 3.0, 4.0, 1000.0]]
    kept = await mcp_server.mcp.call_tool("clean_data", {"data": rows})
    dropped = await mcp_server.mcp.call_tool(
        "clean_data", {"data": rows, "remove_outlier_rows": True}
    )
    assert tool_result(kept)["rows"] == 5
    assert tool_result(dropped)["rows"] == 4


# ===========================================================================
# merge exposed on both interfaces
# ===========================================================================

LEFT_ROWS = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]
RIGHT_ROWS = [{"id": 1, "score": 10}, {"id": 2, "score": 20}, {"id": 4, "score": 40}]


def test_merge_endpoint_inner_join():
    response = client.post("/merge", json={
        "left": LEFT_ROWS, "right": RIGHT_ROWS, "on": "id",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == [
        {"id": 1, "name": "a", "score": 10},
        {"id": 2, "name": "b", "score": 20},
    ]
    assert body["left_rows"] == 3 and body["right_rows"] == 3 and body["rows"] == 2


def test_merge_endpoint_reports_row_counts_for_fan_out():
    # The counts are the point: they make silent inflation visible.
    rows = [{"k": 1}, {"k": 1}]
    body = client.post("/merge", json={"left": rows, "right": rows, "on": "k"}).json()
    assert body["left_rows"] == 2 and body["right_rows"] == 2 and body["rows"] == 4


def test_merge_endpoint_validate_rejects_fan_out():
    rows = [{"k": 1}, {"k": 1}]
    response = client.post("/merge", json={
        "left": rows, "right": rows, "on": "k", "validate": "one_to_one",
    })
    assert response.status_code == 400


def test_merge_endpoint_missing_key_is_client_error():
    response = client.post("/merge", json={
        "left": LEFT_ROWS, "right": RIGHT_ROWS, "on": "nope",
    })
    assert response.status_code == 400
    assert "left frame" in response.json()["detail"]


def test_merge_endpoint_bad_how_is_client_error():
    response = client.post("/merge", json={
        "left": LEFT_ROWS, "right": RIGHT_ROWS, "on": "id", "how": "sideways",
    })
    assert response.status_code == 400


def test_merge_endpoint_cross_join():
    response = client.post("/merge", json={
        "left": LEFT_ROWS, "right": RIGHT_ROWS, "how": "cross",
    })
    assert response.status_code == 200
    assert response.json()["rows"] == 9


def test_merge_endpoint_custom_suffixes():
    body = client.post("/merge", json={
        "left": [{"k": 1, "v": "l"}], "right": [{"k": 1, "v": "r"}],
        "on": "k", "suffixes": ["_left", "_right"],
    }).json()
    assert "v_left" in body["columns"] and "v_right" in body["columns"]


def test_merge_endpoint_rejects_bad_suffixes():
    response = client.post("/merge", json={
        "left": [{"k": 1}], "right": [{"k": 1}], "on": "k", "suffixes": ["only_one"],
    })
    assert response.status_code == 400


def test_merge_endpoint_outer_join_nulls_are_json_null():
    body = client.post("/merge", json={
        "left": LEFT_ROWS, "right": RIGHT_ROWS, "on": "id", "how": "outer",
    }).json()
    assert body["rows"] == 4
    assert "NaN" not in json.dumps(body["data"])


async def test_mcp_merge_data_joins():
    from dataprocessing import mcp_server

    result = await mcp_server.mcp.call_tool(
        "merge_data", {"left": LEFT_ROWS, "right": RIGHT_ROWS, "on": "id"}
    )
    payload = tool_result(result)
    assert payload["rows"] == 2
    assert payload["left_rows"] == 3 and payload["right_rows"] == 3


async def test_mcp_merge_data_validate_rejects_fan_out():
    from dataprocessing import mcp_server

    rows = [{"k": 1}, {"k": 1}]
    with pytest.raises(Exception):
        await mcp_server.mcp.call_tool(
            "merge_data",
            {"left": rows, "right": rows, "on": "k", "validate": "one_to_one"},
        )


async def test_mcp_merge_data_is_registered():
    from dataprocessing import mcp_server

    names = [t.name for t in await mcp_server.mcp.list_tools()]
    assert "merge_data" in names


# ===========================================================================
# Pre-release hardening: version sourcing and visible data loss
# ===========================================================================

def test_version_is_single_sourced():
    # /health reported 0.1.0 for the whole of 0.1.1 because the number was
    # written in both pyproject.toml and api.py. It is now read from the
    # installed package metadata, so it cannot drift again.
    import dataprocessing
    from importlib.metadata import version

    assert dataprocessing.__version__ == version("dataprocessing-ai")
    assert client.get("/health").json()["version"] == dataprocessing.__version__


def test_clean_endpoint_reports_input_size():
    # Cleaning drops every row holding any null; without the input size the
    # caller cannot see how much of the dataset went.
    rows = [{"a": 1, "b": 1}, {"a": 2, "b": None}, {"a": 3, "b": 3}]
    body = client.post("/clean", json={"data": rows}).json()
    assert body["rows_in"] == 3 and body["rows"] == 2
    assert body["columns_in"] == 2


def test_clean_endpoint_reports_dropped_columns():
    rows = [{"keep": 1, "mostly_null": 1}, {"keep": 2, "mostly_null": None},
            {"keep": 3, "mostly_null": None}, {"keep": 4, "mostly_null": None}]
    body = client.post("/clean", json={"data": rows}).json()
    assert body["columns_in"] == 2 and body["columns"] == ["keep"]


async def test_mcp_clean_data_reports_input_size():
    from dataprocessing import mcp_server

    rows = [{"a": 1, "b": 1}, {"a": 2, "b": None}, {"a": 3, "b": 3}]
    result = await mcp_server.mcp.call_tool("clean_data", {"data": rows})
    payload = tool_result(result)
    assert payload["rows_in"] == 3 and payload["rows"] == 2


def test_clean_all_outlier_removal_is_optional():
    # Dropping outliers is a judgement, not a repair — the extreme value is
    # sometimes the observation that matters. Default is unchanged.
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 1000.0]})
    assert len(clean_all(df)) == 4
    assert len(clean_all(df, remove_outlier_rows=False)) == 5


# ===========================================================================
# The type-conversion threshold is reachable, not welded shut
# ===========================================================================

# 9 of 10 values parse as dates — exactly the 0.9 default, so the default
# accepts it and anything stricter does not.
NINE_OF_TEN_DATES = [f"2024-01-0{i}" for i in range(1, 10)] + ["not a date"]

# 3 of 4 parse — below the default, so only a lowered threshold accepts it.
THREE_OF_FOUR_DATES = ["2024-01-01", "2024-06-15", "2024-12-31", "unknown"]


def test_default_threshold_is_ninety_percent():
    from dataprocessing.clean import DEFAULT_TYPE_THRESHOLD

    assert DEFAULT_TYPE_THRESHOLD == 0.9


def test_fix_types_accepts_a_stricter_threshold():
    # A column that is only coincidentally date-shaped: at the default it
    # converts and the odd one out is blanked; at 1.0 it stays text intact.
    df = pd.DataFrame({"code": NINE_OF_TEN_DATES})

    default = fix_types(df)
    assert pd.api.types.is_datetime64_any_dtype(default["code"])
    assert default["code"].isna().sum() == 1  # the value that did not parse

    strict = fix_types(df, threshold=1.0)
    assert strict["code"].tolist() == NINE_OF_TEN_DATES  # nothing lost


def test_fix_types_accepts_a_looser_threshold():
    # A genuine date column carrying messy entries. The default leaves it as
    # text; lowering the threshold buys date handling at the cost of the
    # entries that could not be parsed.
    df = pd.DataFrame({"when": THREE_OF_FOUR_DATES})

    assert not pd.api.types.is_datetime64_any_dtype(fix_types(df)["when"])

    loose = fix_types(df, threshold=0.7)
    assert pd.api.types.is_datetime64_any_dtype(loose["when"])
    assert loose["when"].isna().sum() == 1


def test_clean_all_passes_the_threshold_through():
    # The point of the change: reachable from the top-level entry point,
    # without touching the private helper.
    df = pd.DataFrame({"when": THREE_OF_FOUR_DATES, "n": [1, 2, 3, 4]})

    assert not pd.api.types.is_datetime64_any_dtype(
        clean_all(df, type_threshold=0.9)["when"]
    )
    assert pd.api.types.is_datetime64_any_dtype(
        clean_all(df, type_threshold=0.7, remove_outlier_rows=False)["when"]
    )


def test_clean_all_exposes_the_null_threshold():
    df = pd.DataFrame({"keep": [1, 2, 3, 4], "half_null": [1.0, None, 3.0, None]})
    assert "half_null" in clean_all(df).columns          # 0.5 is not > 0.5
    assert "half_null" not in clean_all(df, null_threshold=0.4).columns


@pytest.mark.parametrize("bad", [-0.1, 1.5, 90])
def test_threshold_outside_zero_to_one_raises(bad):
    # 90 is the likely mistake: a percentage where a share is wanted.
    df = pd.DataFrame({"a": ["x"]})
    with pytest.raises(ValueError, match="between 0 and 1"):
        fix_types(df, threshold=bad)


# ===========================================================================
# The IQR outlier fence is reachable, and shared between the two modules
# ===========================================================================

# 18.0 lands between the two fences: outside the conventional 1.5 fence, inside
# the 3.0 "far out" one. That gap is what makes the factor observable. All
# values are distinct so that clean_all's dedupe step does not confuse the count.
ONE_MILD_OUTLIER = [10.0, 11.0, 12.0, 13.0, 14.0, 18.0]


def test_default_iqr_factor_is_one_point_five():
    from dataprocessing._defaults import DEFAULT_IQR_FACTOR

    assert DEFAULT_IQR_FACTOR == 1.5


def test_clean_and_analyse_share_one_fence():
    # The same number lived in both modules. What analyse reports as an outlier
    # must be what clean would drop, or the two disagree as they drift.
    from dataprocessing.analyse import detect_outliers as detect

    df = pd.DataFrame({"v": ONE_MILD_OUTLIER})
    flagged = detect(df)["v"]
    kept = remove_outliers(df)
    assert flagged == [5]
    assert len(kept) == len(df) - len(flagged)


def test_remove_outliers_factor_widens_the_fence():
    df = pd.DataFrame({"v": ONE_MILD_OUTLIER})
    assert len(remove_outliers(df)) == 5                    # 1.5 drops it
    assert len(remove_outliers(df, factor=3.0)) == 6        # 3.0 keeps it


def test_detect_outliers_factor_widens_the_fence():
    from dataprocessing.analyse import detect_outliers as detect

    df = pd.DataFrame({"v": ONE_MILD_OUTLIER})
    assert detect(df)["v"] == [5]
    assert detect(df, factor=3.0)["v"] == []


def test_clean_all_passes_the_outlier_factor_through():
    df = pd.DataFrame({"v": ONE_MILD_OUTLIER})
    assert len(clean_all(df)) == 5
    assert len(clean_all(df, outlier_factor=3.0)) == 6


@pytest.mark.parametrize("bad", [0, -1.5])
def test_non_positive_iqr_factor_raises(bad):
    from dataprocessing.analyse import detect_outliers as detect

    df = pd.DataFrame({"v": ONE_MILD_OUTLIER})
    with pytest.raises(ValueError, match="greater than 0"):
        remove_outliers(df, factor=bad)
    with pytest.raises(ValueError, match="greater than 0"):
        detect(df, factor=bad)


def test_drop_nulls_validates_its_threshold():
    # Was unvalidated: a threshold of 50 (meaning 50%) silently kept every
    # column, since no column can be more than 5000% null.
    df = pd.DataFrame({"a": [1.0, None]})
    with pytest.raises(ValueError, match="between 0 and 1"):
        drop_nulls(df, threshold=50)


def test_clean_endpoint_accepts_outlier_factor():
    rows = [{"v": v} for v in ONE_MILD_OUTLIER]
    tight = client.post("/clean", json={"data": rows, "remove_outliers": True}).json()
    wide = client.post("/clean", json={
        "data": rows, "remove_outliers": True, "outlier_factor": 3.0,
    }).json()
    assert tight["rows"] == 5 and wide["rows"] == 6
    assert tight["rows_in"] == 6


async def test_mcp_clean_data_accepts_outlier_factor():
    from dataprocessing import mcp_server

    rows = [{"v": v} for v in ONE_MILD_OUTLIER]
    tight = await mcp_server.mcp.call_tool(
        "clean_data", {"data": rows, "remove_outlier_rows": True})
    wide = await mcp_server.mcp.call_tool(
        "clean_data", {"data": rows, "remove_outlier_rows": True, "outlier_factor": 3.0})
    assert tool_result(tight)["rows"] == 5
    assert tool_result(wide)["rows"] == 6


# ===========================================================================
# drop_nulls: the row policy is adjustable, not just the column policy
# ===========================================================================

# Two clean rows, one patchy (1 of 3 null), one mostly empty (2 of 3). Sized so
# that no COLUMN exceeds the 0.5 column threshold — b is exactly 0.5 null, which
# does not exceed it — so these tests isolate the row policy from the column one.
PATCHY = pd.DataFrame({
    "a": [1.0, 2.0, None, 4.0],
    "b": [1.0, None, None, 4.0],
    "c": [1.0, 3.0, 4.0, 5.0],
})


def test_drop_nulls_default_is_unchanged():
    # Any null drops the row — what dropna() does and what this always did.
    assert len(drop_nulls(PATCHY)) == 2


def test_drop_nulls_keeps_every_column_in_the_fixture():
    # Guards the tests above: if b ever tripped the column threshold, the row
    # assertions would be measuring the wrong thing.
    assert list(drop_nulls(PATCHY, row_threshold=1.0).columns) == ["a", "b", "c"]


def test_drop_nulls_can_keep_every_row():
    # A fully-null row has a share of 1.0, which does not exceed 1.0.
    assert len(drop_nulls(PATCHY, row_threshold=1.0)) == 4


def test_drop_nulls_row_threshold_keeps_patchy_rows():
    # Row 1 is 1/3 null (kept), row 2 is 2/3 null (dropped).
    kept = drop_nulls(PATCHY, row_threshold=0.5)
    assert kept.index.tolist() == [0, 1, 3]


def test_drop_nulls_subset_judges_only_named_columns():
    # Row 2 is null in 'a' but fine in 'c'. Judging on 'c' alone keeps all rows.
    assert len(drop_nulls(PATCHY, subset=["c"])) == 4
    assert len(drop_nulls(PATCHY, subset=["a"])) == 3


def test_drop_nulls_subset_missing_column_raises():
    with pytest.raises(ValueError, match="Column"):
        drop_nulls(PATCHY, subset=["nope"])


def test_drop_nulls_subset_survives_its_column_being_dropped():
    # 'gone' is 100% null so the column goes; judging rows on it must not crash.
    df = pd.DataFrame({"keep": [1.0, 2.0], "gone": [None, None]})
    result = drop_nulls(df, subset=["gone"])
    assert list(result.columns) == ["keep"]
    assert len(result) == 2


def test_drop_nulls_still_drops_mostly_null_columns():
    df = pd.DataFrame({"keep": [1, 2, 3, 4], "mostly_null": [1.0, None, None, None]})
    assert "mostly_null" not in drop_nulls(df, row_threshold=1.0).columns


def test_drop_nulls_validates_row_threshold():
    with pytest.raises(ValueError, match="row_threshold"):
        drop_nulls(PATCHY, row_threshold=50)


def test_row_threshold_rescues_the_scattered_null_case():
    # The scenario that motivated this: 5% of cells missing at random costs a
    # quarter of the rows at the default, and none of them once it is raised.
    rng = np.random.default_rng(0)
    df = pd.DataFrame({f"c{i}": rng.normal(size=1000) for i in range(6)})
    df = df.mask(rng.random(df.shape) < 0.05)

    assert len(drop_nulls(df)) < 800                      # default is lossy
    assert len(drop_nulls(df, row_threshold=1.0)) == 1000  # nothing dropped


def test_clean_all_passes_the_row_threshold_through():
    assert len(clean_all(PATCHY, remove_outlier_rows=False)) == 2
    assert len(clean_all(PATCHY, remove_outlier_rows=False, row_null_threshold=1.0)) == 4


def test_clean_endpoint_accepts_row_null_threshold():
    rows = [{"a": 1.0, "b": 1.0}, {"a": 2.0, "b": None}]
    strict = client.post("/clean", json={"data": rows}).json()
    lenient = client.post("/clean", json={"data": rows, "row_null_threshold": 1.0}).json()
    assert strict["rows"] == 1 and strict["rows_in"] == 2
    assert lenient["rows"] == 2


async def test_mcp_clean_data_accepts_row_null_threshold():
    from dataprocessing import mcp_server

    rows = [{"a": 1.0, "b": 1.0}, {"a": 2.0, "b": None}]
    strict = await mcp_server.mcp.call_tool("clean_data", {"data": rows})
    lenient = await mcp_server.mcp.call_tool(
        "clean_data", {"data": rows, "row_null_threshold": 1.0})
    assert tool_result(strict)["rows"] == 1
    assert tool_result(lenient)["rows"] == 2


# ===========================================================================
# JSON safety is guaranteed at the source, not only at the boundary
# ===========================================================================
# A mutation sweep showed that removing to_native from the API and MCP handlers
# broke no test — because analyse and visualise now return native Python types
# themselves, making to_native redundant defence rather than the fix. These
# tests pin that underlying guarantee, so a future numpy leak fails here rather
# than silently relying on the boundary to paper over it.

def test_full_report_is_json_safe_without_to_native():
    df = pd.DataFrame({"age": [23, 35, None, 900], "city": ["A", "B", "A", "C"]})
    json.dumps(full_report(df))  # no to_native


def test_full_report_leaks_no_numpy_types():
    df = pd.DataFrame({"age": [23, 35, None, 900], "city": ["A", "B", "A", "C"]})

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                assert type(key).__module__ != "numpy", f"numpy key at {path}"
                walk(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for item in obj:
                walk(item, path + "[]")
        else:
            assert type(obj).__module__ != "numpy", f"numpy value at {path}: {type(obj)}"

    walk(full_report(df))


@pytest.mark.parametrize("chart,params", [
    ("histogram", {"column": "n", "bins": 3}),
    ("bar_chart", {"column": "g"}),
    ("scatter", {"x": "n", "y": "m"}),
    ("line_chart", {"x": "n", "y": "m"}),
    ("correlation_heatmap", {}),
])
def test_chart_specs_are_json_safe_without_to_native(chart, params):
    from dataprocessing import visualise

    df = pd.DataFrame({"n": [1.0, 2.0, 3.0, 4.0], "m": [4.0, 3.0, 2.0, 1.0],
                       "g": ["a", "b", "a", "b"]})
    json.dumps(getattr(visualise, chart)(df, **params))


def test_to_native_converts_numpy_scalars_and_arrays():
    # to_native itself is pinned directly, since its callers no longer depend
    # on it to produce serialisable output.
    out = to_native({
        "i": np.int64(3), "f": np.float64(1.5), "b": np.bool_(True),
        "arr": np.array([1, 2]), "nested": [{"x": np.int32(7)}],
    })
    assert out == {"i": 3, "f": 1.5, "b": True, "arr": [1, 2], "nested": [{"x": 7}]}
    json.dumps(out)


def test_to_native_converts_numpy_dict_keys():
    assert to_native({np.int64(1): np.float64(2.0)}) == {1: 2.0}


def test_chart_values_are_exactly_native_types():
    # bar_chart's int() looks redundant on pandas 3.x, where iterating a Series
    # already yields Python ints — but it is load-bearing on pandas 2.2, which
    # this package still supports. Asserting the type pins it on both.
    from dataprocessing.visualise import bar_chart, histogram

    df = pd.DataFrame({"g": ["a", "b", "a"], "n": [1.0, 2.0, 3.0]})
    for row in bar_chart(df, "g")["data"]["values"]:
        assert type(row["count"]) is int
        assert type(row["category"]) is str
    for row in histogram(df, "n", bins=2)["data"]["values"]:
        assert type(row["count"]) is int
        assert type(row["bin_start"]) is float


def test_clean_endpoint_reaches_parity_with_the_mcp_tool():
    # /clean deduplicated and renamed columns unconditionally while the MCP
    # clean_data tool let the caller decline both — the same interface drift
    # that hid the analyse_data failure, pointing the other way.
    rows = [{"First Name": "Ada"}, {"First Name": "Ada"}, {"First Name": "Bob"}]

    default = client.post("/clean", json={"data": rows}).json()
    assert default["columns"] == ["first_name"] and default["rows"] == 2

    kept = client.post("/clean", json={
        "data": rows, "remove_dupes": False, "standardise_cols": False,
    }).json()
    assert kept["columns"] == ["First Name"] and kept["rows"] == 3


def test_clean_options_match_across_interfaces():
    # Guards against the two drifting apart again.
    import inspect
    from dataprocessing import mcp_server
    from dataprocessing.api import CleanRequest

    rest = set(CleanRequest.model_fields) - {"data"}
    tool = set(inspect.signature(mcp_server.clean_data).parameters) - {"data"}
    # The REST field is named for the operation it controls; the tool predates it.
    rest = {"remove_outlier_rows" if f == "remove_outliers" else f for f in rest}
    assert rest == tool, f"only in REST: {rest - tool}; only in MCP: {tool - rest}"


# ===========================================================================
# Warnings: the library says when it did something surprising
# ===========================================================================
# Passive reporting (rows vs rows_in) only helps a caller who thinks to compare
# them. These assert the active version: a plain statement in the response.

from dataprocessing import verify


def test_row_loss_is_quiet_below_the_threshold():
    # A warning on every row removed would fire constantly, and an agent that
    # sees warnings on every call learns to ignore them.
    assert verify.row_loss(1000, 995, "cause") is None
    assert verify.row_loss(1000, 100, "cause") is not None


def test_row_loss_always_reports_total_loss():
    # However the threshold is set: an empty result is the most misleading
    # thing the library can return without saying why.
    warning = verify.row_loss(1000, 0, "everything matched nothing.")
    assert "All 1000 rows were removed" in warning


def test_row_loss_is_silent_when_nothing_was_lost():
    assert verify.row_loss(10, 10, "cause") is None
    assert verify.row_loss(0, 0, "cause") is None


def test_warnings_name_the_remedy():
    # What happened, how much, and what to do — a warning missing the third
    # cannot be acted on.
    warning = verify.row_loss(100, 10, "rows were dropped.", "Raise the threshold.")
    assert "90 of 100" in warning and "Raise the threshold." in warning


def test_dropped_columns_always_reported():
    warning = verify.dropped_columns(["a", "b"], ["a"], "they were empty.")
    assert "'b'" in warning
    assert verify.dropped_columns(["a"], ["a"], "cause") is None


def test_merge_warns_about_fan_out():
    warnings = verify.merge_result(3, 2, 4, how="inner")
    assert any("multiplied" in w and "validate" in w for w in warnings)


def test_merge_warns_about_no_overlap():
    warnings = verify.merge_result(3, 3, 0, how="inner")
    assert any("do not overlap" in w for w in warnings)


def test_merge_warns_about_dropped_unmatched_rows():
    warnings = verify.merge_result(10, 10, 4, how="inner")
    assert any("how='left'" in w for w in warnings)


def test_merge_is_quiet_on_a_clean_join():
    assert verify.merge_result(3, 3, 3, how="inner") == []


def test_merge_is_quiet_for_a_cross_join():
    # A cross join is supposed to multiply; saying so would be noise.
    assert verify.merge_result(3, 3, 9, how="cross") == []


# 20 rows with b null in 5 of them. Deliberately 25%, not more: over 50% and
# the COLUMN threshold drops b entirely before any row is judged, and these
# tests would silently be measuring column loss instead of row loss.
ROWS_WITH_SOME_NULLS = [
    {"a": float(i), "b": None if i < 5 else float(i)} for i in range(20)
]


def test_clean_endpoint_warns_about_row_loss():
    body = client.post("/clean", json={"data": ROWS_WITH_SOME_NULLS}).json()
    assert body["rows_in"] == 20 and body["rows"] == 15
    assert list(body["columns"]) == ["a", "b"]  # the column survived
    assert any("row_null_threshold" in w for w in body["warnings"])


def test_clean_endpoint_warns_about_dropped_columns():
    rows = [{"keep": 1.0, "dead": None} for _ in range(4)]
    body = client.post("/clean", json={"data": rows}).json()
    assert any("'dead'" in w for w in body["warnings"])


def test_clean_endpoint_is_quiet_on_clean_data():
    rows = [{"a": float(i), "b": float(i)} for i in range(10)]
    assert client.post("/clean", json={"data": rows}).json()["warnings"] == []


def test_clean_endpoint_catches_compound_loss():
    # Three stages each losing under the threshold, compounding past it. No
    # single stage trips, so without the fallback this would report nothing.
    rows = [{"a": float(i), "b": float(i)} for i in range(100)]
    for row in rows[:5]:
        row["a"] = None
    rows += [dict(rows[20])] * 5
    for row in rows[30:35]:
        row["a"] = 99999.0

    body = client.post("/clean", json={"data": rows, "remove_outliers": True}).json()
    assert body["rows_in"] - body["rows"] == 15
    assert len(body["warnings"]) == 1
    assert "across several steps" in body["warnings"][0]


def test_merge_endpoint_warns_about_fan_out():
    body = client.post("/merge", json={
        "left": [{"k": 1}, {"k": 1}], "right": [{"k": 1}, {"k": 1}], "on": "k",
    }).json()
    assert any("multiplied" in w for w in body["warnings"])


def test_transform_endpoint_warns_about_an_aggressive_filter():
    rows = [{"a": i} for i in range(100)]
    body = client.post("/transform", json={
        "data": rows, "operation": "filter_rows",
        "params": {"column": "a", "operator": "gt", "value": 95},
    }).json()
    assert body["rows_in"] == 100 and body["rows"] == 4
    assert any("filter_rows" in w for w in body["warnings"])


def test_transform_endpoint_is_quiet_when_nothing_is_lost():
    rows = [{"a": i} for i in range(10)]
    body = client.post("/transform", json={
        "data": rows, "operation": "sort_rows", "params": {"columns": "a"},
    }).json()
    assert body["warnings"] == []


async def test_mcp_clean_data_returns_warnings():
    from dataprocessing import mcp_server

    payload = tool_result(await mcp_server.mcp.call_tool(
        "clean_data", {"data": ROWS_WITH_SOME_NULLS}))
    assert any("row_null_threshold" in w for w in payload["warnings"])


async def test_mcp_merge_data_returns_warnings():
    from dataprocessing import mcp_server

    payload = tool_result(await mcp_server.mcp.call_tool(
        "merge_data", {"left": [{"k": 1}, {"k": 1}], "right": [{"k": 1}, {"k": 1}], "on": "k"}))
    assert any("multiplied" in w for w in payload["warnings"])


async def test_mcp_tool_descriptions_tell_the_agent_to_read_warnings():
    # The field is useless if the agent does not know to look at it, so the
    # instruction lives in the tool description the model actually sees.
    from dataprocessing import mcp_server

    tools = {t.name: t.description for t in await mcp_server.mcp.list_tools()}
    assert "READ THE WARNINGS" in tools["clean_data"]
    assert "READ THE WARNINGS" in tools["merge_data"]


def test_warnings_are_json_safe():
    rows = [{"a": 1.0, "b": None} for _ in range(20)]
    body = client.post("/clean", json={"data": rows}).json()
    json.dumps(body["warnings"])
    assert all(isinstance(w, str) for w in body["warnings"])


# ===========================================================================
# Found by driving the MCP tools through a realistic pipeline
# ===========================================================================
# A messy CRM export, cleaned, grouped, filtered and joined. None of these were
# caught by the tests; all three came from reading what the tools actually said.

from dataprocessing._columns import suggest
from dataprocessing.transform import merge_dataframes


def test_grouping_does_not_warn_about_losing_rows():
    # It reported "Removed 115 of 120 rows (96%)" for a group-by. Collapsing
    # rows IS grouping, so this fired on correct behaviour — the precise noise
    # that teaches a reader to skip warnings.
    assert verify.transform_result("group_and_aggregate", 120, 5) is None
    assert verify.transform_result("pivot", 120, 5) is None


def test_a_normal_filter_does_not_warn():
    # Filtering is meant to remove rows; 25 of 120 is a filter working.
    assert verify.transform_result("filter_rows", 120, 25) is None


def test_a_filter_matching_nothing_always_warns():
    warning = verify.transform_result("filter_rows", 120, 0)
    assert "no rows at all" in warning and "type" in warning


def test_a_filter_matching_almost_nothing_warns():
    # The signature of a wrong value or a type mismatch.
    warning = verify.transform_result("filter_rows", 1000, 3)
    assert "kept only 3 of 1000" in warning


def test_reshaping_operation_returning_nothing_stays_quiet():
    # An empty group-by result means empty input, which other warnings cover.
    assert verify.transform_result("pivot", 100, 0) is None


def test_suggest_catches_the_standardisation_case():
    # The single most likely mistake this library produces: clean() renames
    # 'Customer ID' to 'customer_id', so the next call uses the old name.
    assert "customer_id" in suggest("Customer ID", ["customer_id", "full_name"])


def test_suggest_catches_a_typo():
    assert "revenue" in suggest("revenu", ["revenue", "region"])


def test_suggest_returns_nothing_for_an_unrelated_name():
    assert suggest("zzzz", ["revenue", "region"]) == []


def test_missing_column_error_suggests_the_standardised_name():
    df = pd.DataFrame({"customer_id": [1], "v": [2]})
    with pytest.raises(ValueError, match="customer_id"):
        filter_rows(df, "Customer ID", "gt", 0)


def test_merge_accepts_differently_named_keys():
    # A cleaned frame joined to an ingested one: no single `on` can work.
    left = pd.DataFrame({"customer_id": [1, 2], "v": [10, 20]})
    right = pd.DataFrame({"Customer ID": [1, 2], "tier": ["gold", "silver"]})
    result = merge_dataframes(left, right, left_on="customer_id", right_on="Customer ID")
    assert len(result) == 2
    assert result["tier"].tolist() == ["gold", "silver"]


def test_merge_error_points_at_left_on_right_on():
    # The dead end: whichever single key name the caller picks, one side fails.
    left = pd.DataFrame({"customer_id": [1]})
    right = pd.DataFrame({"Customer ID": [1]})
    with pytest.raises(ValueError, match="left_on and right_on"):
        merge_dataframes(left, right, on="customer_id")


def test_merge_rejects_on_together_with_left_on():
    left = right = pd.DataFrame({"k": [1]})
    with pytest.raises(ValueError, match="not both"):
        merge_dataframes(left, right, on="k", left_on="k", right_on="k")


def test_merge_requires_both_sides_of_a_split_key():
    left = right = pd.DataFrame({"k": [1]})
    with pytest.raises(ValueError, match="together"):
        merge_dataframes(left, right, left_on="k")


def test_merge_requires_matching_key_counts():
    left = pd.DataFrame({"a": [1], "b": [1]})
    right = pd.DataFrame({"c": [1]})
    with pytest.raises(ValueError, match="one for one"):
        merge_dataframes(left, right, left_on=["a", "b"], right_on=["c"])


def test_merge_endpoint_accepts_left_on_right_on():
    body = client.post("/merge", json={
        "left": [{"customer_id": 1, "v": 10}],
        "right": [{"Customer ID": 1, "tier": "gold"}],
        "left_on": "customer_id", "right_on": "Customer ID",
    }).json()
    assert body["rows"] == 1 and "tier" in body["columns"]


async def test_mcp_merge_data_accepts_left_on_right_on():
    from dataprocessing import mcp_server

    payload = tool_result(await mcp_server.mcp.call_tool("merge_data", {
        "left": [{"customer_id": 1}], "right": [{"Customer ID": 1, "tier": "gold"}],
        "left_on": "customer_id", "right_on": "Customer ID",
    }))
    assert payload["rows"] == 1


def test_null_row_warning_reads_naturally_at_the_default():
    # It said "rows with more than 0% null values were dropped", which is true
    # and unreadable.
    # 'b' is 30% null, so the COLUMN survives the 50% threshold and the rows
    # holding those nulls are what get dropped. Sized deliberately: at 10/11
    # null the column is dropped instead, nothing is left holding a null, and
    # no row warning fires at all.
    rows = [{"a": float(i), "b": float(i)} for i in range(10)]
    for row in rows[:3]:
        row["b"] = None

    body = client.post("/clean", json={"data": rows}).json()
    assert body["columns"] == ["a", "b"]
    assert any("any null at all" in w for w in body["warnings"])
