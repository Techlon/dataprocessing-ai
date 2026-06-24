import pytest
import pandas as pd
import numpy as np
from dataprocessing.transform import (
    filter_rows, select_columns, rename_columns, sort_rows,
    group_and_aggregate, pivot, merge_dataframes, add_column,
)


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "A": [1, 2, 3, 4, 5],
        "B": ["a", "b", "c", "d", "e"],
        "C": [10, 20, 30, 40, 50],
    })


def test_filter_rows_eq(sample_df):
    out = filter_rows(sample_df, "A", "eq", 3)
    assert len(out) == 1
    assert out["A"].iloc[0] == 3


def test_filter_rows_ne(sample_df):
    out = filter_rows(sample_df, "B", "ne", "a")
    assert len(out) == 4


def test_filter_rows_gt(sample_df):
    out = filter_rows(sample_df, "A", "gt", 3)
    assert list(out["A"]) == [4, 5]


def test_filter_rows_invalid_operator(sample_df):
    with pytest.raises(ValueError):
        filter_rows(sample_df, "A", "not_an_op", 1)


def test_select_columns(sample_df):
    out = select_columns(sample_df, ["A", "C"])
    assert list(out.columns) == ["A", "C"]


def test_rename_columns(sample_df):
    out = rename_columns(sample_df, {"A": "X", "B": "Y"})
    assert list(out.columns) == ["X", "Y", "C"]


def test_sort_rows(sample_df):
    out = sort_rows(sample_df, ["C"], ascending=False)
    assert list(out["C"]) == [50, 40, 30, 20, 10]


def test_group_and_aggregate():
    df = pd.DataFrame({
        "grp": ["x", "x", "y"],
        "val": [1, 2, 10],
    })
    out = group_and_aggregate(df, ["grp"], {"val": "sum"})
    # x -> 1+2 = 3, y -> 10
    assert out.loc["x", "val"] == 3
    assert out.loc["y", "val"] == 10


def test_pivot():
    df = pd.DataFrame({
        "row": ["r1", "r1", "r2"],
        "col": ["c1", "c2", "c1"],
        "val": [1, 2, 3],
    })
    out = pivot(df, index="row", columns="col", values="val")
    assert out.loc["r1", "c1"] == 1
    assert out.loc["r1", "c2"] == 2
    assert out.loc["r2", "c1"] == 3


def test_merge_dataframes():
    df1 = pd.DataFrame({"key": ["A", "B", "C"], "value": [1, 2, 3]})
    df2 = pd.DataFrame({"key": ["B", "C", "D"], "value2": [4, 5, 6]})
    merged = merge_dataframes(df1, df2, on="key")  # inner join
    assert list(merged["key"]) == ["B", "C"]
    assert list(merged["value2"]) == [4, 5]


def test_add_column(sample_df):
    # add_column evaluates `df.<expression>`, so column refs must be attribute
    # or bracket access on df (e.g. "A + df.C"), not bare names.
    out = add_column(sample_df.copy(), "D", "A + df.C")
    assert list(out["D"]) == [11, 22, 33, 44, 55]
