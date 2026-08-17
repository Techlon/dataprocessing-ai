"""
DataProcessing MCP Server
Exposes ingest, clean, transform and analyse as native Claude tools.
"""
from typing import Any, Dict, List, Optional

try:
    # mcp >= 2.0 renamed FastMCP to MCPServer and moved it. The decorator,
    # run() and call_tool() surfaces are otherwise the same, so one shim covers
    # both majors rather than stranding either. Ordered newest-first so a 2.x
    # install does not pay for a failed legacy import.
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # pragma: no cover - depends on the installed mcp major
    from mcp.server.fastmcp import FastMCP as _Server
import pandas as pd
import json
import io
import base64

from dataprocessing._defaults import (
    DEFAULT_IQR_FACTOR, DEFAULT_NULL_THRESHOLD, DEFAULT_ROW_NULL_THRESHOLD,
    DEFAULT_TYPE_THRESHOLD,
)
from dataprocessing import verify
from dataprocessing._serialise import df_to_json, to_native
from dataprocessing.ingest import read_file
from dataprocessing.clean import (
    drop_nulls, fix_types as fix_types_fn, remove_duplicates,
    remove_outliers as remove_outliers_iqr, standardise_columns,
)
from dataprocessing.transform import (
    filter_rows, select_columns, rename_columns,
    sort_rows, group_and_aggregate, pivot, add_column, merge_dataframes
)
from dataprocessing.analyse import full_report

from dataprocessing.visualise import (
    histogram, bar_chart, scatter, line_chart, correlation_heatmap)


def _as_keys(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _null_row_cause(threshold):
    """Phrase the row-null rule the way it actually behaves at its default."""
    if threshold <= 0:
        return "every row containing any null at all was dropped."
    return f"rows more than {threshold:.0%} null were dropped."

mcp = _Server("DataProcessing")

@mcp.tool()
def ingest_file(file_path: str) -> Dict[str, Any]:
    """
    Read a data file (CSV, JSON, Excel, Parquet) and return its contents.
    Args:
        file_path: Full path to the file on disk
    Returns:
        Dict with keys: data (list of records), rows (int), columns (list)
    """
    df = read_file(file_path)
    return {
        "data": df_to_json(df),
        "rows": len(df),
        "columns": list(df.columns)
    }

@mcp.tool()
def clean_data(
    data: List[Dict[str, Any]],
    drop_null_threshold: float = DEFAULT_NULL_THRESHOLD,
    row_null_threshold: float = DEFAULT_ROW_NULL_THRESHOLD,
    remove_dupes: bool = True,
    standardise_cols: bool = True,
    fix_types: bool = True,
    type_threshold: float = DEFAULT_TYPE_THRESHOLD,
    remove_outlier_rows: bool = False,
    outlier_factor: float = DEFAULT_IQR_FACTOR
) -> Dict[str, Any]:
    """
    Clean a dataset by removing nulls, duplicates and standardising column names.
    Args:
        data: List of row dicts (from ingest_file or any source)
        drop_null_threshold: Drop columns with more than this fraction of nulls (0.0-1.0)
        row_null_threshold: Drop ROWS with more than this fraction of nulls.
                        0.0 (the default) drops a row for a single null and
                        typically discards a quarter of a dataset with 5% of
                        cells missing. Raise it to keep patchy rows; 1.0 keeps
                        every row and drops only dead columns
        fix_types: Convert text columns that are really numbers or dates.
                   Leave this on: without it a dataset whose numbers arrived
                   quoted stays text, and analyse_data then returns an empty
                   report
        type_threshold: Share of a column's values that must convert before the
                   conversion is accepted (0.9). Raise toward 1.0 to leave a
                   column as text unless every value converts
        remove_dupes: Whether to remove duplicate rows
        standardise_cols: Whether to lowercase and underscore column names
        remove_outlier_rows: Whether to drop rows holding an IQR outlier
        outlier_factor: Multiplier on the interquartile range that sets the
                        outlier fence, used only when remove_outlier_rows is
                        true. 1.5 is conventional; 3.0 removes fewer rows
    Returns:
        Dict with keys: data (cleaned records), rows, columns, rows_in,
        columns_in, warnings.

        READ THE WARNINGS before using the data. Cleaning is lossy and says so
        there: it reports how many rows and columns went and which option to
        change. An empty warnings list means nothing surprising happened.
    """
    df = pd.DataFrame(data)
    rows_in, columns_in = len(df), len(df.columns)
    original_columns = list(df.columns)
    warnings = []

    df = drop_nulls(df, threshold=drop_null_threshold,
                    row_threshold=row_null_threshold)
    warnings.append(verify.row_loss(
        rows_in, len(df),
        _null_row_cause(row_null_threshold),
        "Raise row_null_threshold to keep patchy rows.",
    ))
    warnings.append(verify.dropped_columns(
        original_columns, list(df.columns),
        f"more than {drop_null_threshold:.0%} of their values were null.",
        "Raise drop_null_threshold to keep them.",
    ))

    if fix_types:
        before_types = df.copy()
        df = fix_types_fn(df, threshold=type_threshold)
        warnings.extend(verify.type_changes(before_types, df))

    rows_before_dupes = len(df)
    if remove_dupes:
        df = remove_duplicates(df)
        warnings.append(verify.row_loss(
            rows_before_dupes, len(df), "duplicate rows were removed.",
            "Set remove_dupes to false to keep them.",
        ))
    # Parity with the REST /clean endpoint, which offers the same option.
    rows_before_outliers = len(df)
    if remove_outlier_rows:
        df = remove_outliers_iqr(df, factor=outlier_factor)
        warnings.append(verify.row_loss(
            rows_before_outliers, len(df),
            f"rows beyond {outlier_factor} x the interquartile range were removed.",
            "Raise outlier_factor to keep more, or set remove_outlier_rows to false.",
        ))
    # Outliers are not removed by default, and saying nothing about them let a
    # single mistyped value move a mean by a factor of fifty.
    if not remove_outlier_rows:
        warnings.extend(verify.extreme_values(df, factor=outlier_factor))
    if standardise_cols:
        df = standardise_columns(df)
    # Several small losses can compound past the threshold while no single
    # stage trips it; this catches that case.
    if not any(warnings):
        warnings.append(verify.row_loss(
            rows_in, len(df), "cleaning removed rows across several steps.",
            "Compare rows against rows_in, and relax the thresholds if the loss "
            "is more than you intended.",
        ))
    return {
        "data": df_to_json(df),
        "rows": len(df),
        "columns": list(df.columns),
        "rows_in": rows_in,
        "columns_in": columns_in,
        "warnings": [w for w in warnings if w]
    }

@mcp.tool()
def transform_data(
    data: List[Dict[str, Any]],
    operation: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Transform a dataset using a named operation.
    Args:
        data: List of row dicts
        operation: One of: filter_rows, select_columns, rename_columns,
                   sort_rows, group_and_aggregate, pivot, add_column
        params: Parameters for the operation, e.g.:
                filter_rows    -> {column, operator, value}
                select_columns -> {columns: [list]}
                rename_columns -> {mapping: {old: new}}
                sort_rows      -> {columns: [list], ascending: true}
                group_and_aggregate -> {group_by: [list], aggregations: {col: func}}
                pivot          -> {index, columns, values, aggfunc}
                add_column     -> {column_name, expression}
    Returns:
        Dict with keys: data (transformed records), rows, columns, rows_in,
        warnings. Check warnings: an operation that matched far fewer rows than
        it received says so there.
    """
    df = pd.DataFrame(data)
    ops = {
        "filter_rows": filter_rows,
        "select_columns": select_columns,
        "rename_columns": rename_columns,
        "sort_rows": sort_rows,
        "group_and_aggregate": group_and_aggregate,
        "pivot": pivot,
        "add_column": add_column,
    }
    if operation not in ops:
        raise ValueError(f"Unknown operation: {operation}. Valid: {list(ops.keys())}")
    rows_in = len(df)
    result = ops[operation](df, **params)
    warning = verify.transform_result(operation, rows_in, len(result))
    return {
        "data": df_to_json(result),
        "rows": len(result),
        "columns": list(result.columns),
        "rows_in": rows_in,
        "warnings": [warning] if warning else []
    }

@mcp.tool()
def merge_data(
    left: List[Dict[str, Any]],
    right: List[Dict[str, Any]],
    on: Optional[Any] = None,
    left_on: Optional[Any] = None,
    right_on: Optional[Any] = None,
    how: str = "inner",
    validate: Optional[str] = None,
    suffixes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Merge two datasets on a shared key. Needs two datasets, so it is a separate
    tool from transform_data rather than one of its operations.
    Args:
        left: List of row dicts for the left dataset
        right: List of row dicts for the right dataset
        on: Column name, or list of names, to join on. Omit only for how="cross"
            or when using left_on/right_on
        left_on / right_on: Key names when the two datasets spell the key
            differently. Needed after clean_data, which standardises column
            names — a cleaned dataset has 'customer_id' where a freshly
            ingested one still has 'Customer ID', and no single `on` works
        how: One of: inner, left, right, outer, cross
        validate: Optional cardinality check — "one_to_one", "one_to_many",
                  "many_to_one", "many_to_many". Use this when you know what the
                  join should be: an unintended many-to-many match multiplies
                  rows silently rather than failing, so a 3-row join can return
                  9 rows with no sign anything went wrong. Passing the expected
                  cardinality turns that into an error.
        suffixes: Two suffixes for columns present in both, default ["_x", "_y"]
    Returns:
        Dict with keys: data (merged records), rows, columns, left_rows,
        right_rows, warnings.

        READ THE WARNINGS. A join fails by multiplying rows rather than by
        erroring, and that is what they report — along with a join that matched
        nothing, or one that dropped unmatched rows.
    """
    if suffixes is None:
        suffixes = ["_x", "_y"]
    if len(suffixes) != 2:
        raise ValueError("suffixes must be a list of exactly two strings.")

    left_df = pd.DataFrame(left)
    right_df = pd.DataFrame(right)
    result = merge_dataframes(
        left_df, right_df, on=on, left_on=left_on, right_on=right_on, how=how,
        validate=validate, suffixes=tuple(suffixes),
    )
    return {
        "data": df_to_json(result),
        "rows": len(result),
        "columns": list(result.columns),
        "left_rows": len(left_df),
        "right_rows": len(right_df),
        "warnings": verify.merge_result(
            len(left_df), len(right_df), len(result), how=how,
            unmatched=verify.unmatched_rows(
                left_df, right_df,
                _as_keys(left_on or on), _as_keys(right_on or on))
            if how in ("left", "outer") else None),
    }

@mcp.tool()
def analyse_data(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run a full statistical analysis on a dataset.
    Args:
        data: List of row dicts
    Returns:
        Dict containing: summary_stats, correlation_matrix, missing_values,
        outliers, and warnings.

        READ THE WARNINGS before drawing conclusions. They flag statistics that
        rest on very few values, columns that are really identifiers, and
        correlations so perfect that one column is derived from the other.
    """
    df = pd.DataFrame(data)
    report = full_report(df)
    report["warnings"] = verify.analysis(df)
    # to_native is essential here, not cosmetic: full_report returns numpy
    # int64/float64, which MCP cannot serialise, and this tool failed outright
    # for every input until it was applied.
    return to_native(report)

@mcp.tool()
def visualise_data(data: List[Dict[str, Any]], chart: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Visualize data in various charts based on the provided type and parameters.

    Args:
        data (List[Dict[str, Any]]): List of row dicts representing the dataset.
        chart (str): The type of chart to generate ('histogram', 'bar_chart', 'scatter', 'line_chart', or 'correlation_heatmap').
        params (Dict[str, Any]): Parameters specific to each chart type:
            - histogram: {'column': str, 'bins': int}
            - bar_chart: {'column': str}
            - scatter: {'x': str, 'y': str}
            - line_chart: {'x': str, 'y': str}
            - correlation_heatmap: {'columns': List[str] (optional)}

    Returns:
        Dict[str, Any]: A JSON-serializable Vega-Lite spec. If anything about
        the chart would mislead — too few points to read a trend, a mostly-null
        column, a single category — the spec carries usermeta.warnings saying
        so. Check it before describing what the chart shows.
    """
    df = pd.DataFrame(data)
    charts = {
        "histogram": histogram,
        "bar_chart": bar_chart,
        "scatter": scatter,
        "line_chart": line_chart,
        "correlation_heatmap": correlation_heatmap
    }

    if chart not in charts:
        raise ValueError(f"Unknown chart: {chart}. Valid: {list(charts.keys())}")

    spec = charts[chart](df, **params)
    chart_warnings = verify.chart(chart, df, params, len(spec["data"]["values"]))
    if chart_warnings:
        # usermeta is Vega-Lite's own metadata slot, so the spec stays valid.
        spec.setdefault("usermeta", {})["warnings"] = chart_warnings
    return to_native(spec)

def main():
    mcp.run()

if __name__ == "__main__":
    main()
    
    