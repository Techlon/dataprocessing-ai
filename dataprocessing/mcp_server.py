"""
DataProcessing MCP Server
Exposes ingest, clean, transform and analyse as native Claude tools.
"""
from mcp.server.fastmcp import FastMCP
from typing import Any, Dict, List, Optional
import pandas as pd
import json
import io
import base64

from dataprocessing._defaults import (
    DEFAULT_IQR_FACTOR, DEFAULT_NULL_THRESHOLD, DEFAULT_ROW_NULL_THRESHOLD,
)
from dataprocessing._serialise import df_to_json, to_native
from dataprocessing.ingest import read_file
from dataprocessing.clean import (
    drop_nulls, remove_duplicates, remove_outliers as remove_outliers_iqr,
    standardise_columns,
)
from dataprocessing.transform import (
    filter_rows, select_columns, rename_columns,
    sort_rows, group_and_aggregate, pivot, add_column, merge_dataframes
)
from dataprocessing.analyse import full_report

from dataprocessing.visualise import (
    histogram, bar_chart, scatter, line_chart, correlation_heatmap)

mcp = FastMCP("DataProcessing")

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
        remove_dupes: Whether to remove duplicate rows
        standardise_cols: Whether to lowercase and underscore column names
        remove_outlier_rows: Whether to drop rows holding an IQR outlier
        outlier_factor: Multiplier on the interquartile range that sets the
                        outlier fence, used only when remove_outlier_rows is
                        true. 1.5 is conventional; 3.0 removes fewer rows
    Returns:
        Dict with keys: data (cleaned records), rows, columns, rows_in,
        columns_in. Compare rows against rows_in: cleaning drops every row
        containing any null, so a dataset with a few percent of cells missing
        routinely loses a quarter of its rows.
    """
    df = pd.DataFrame(data)
    rows_in, columns_in = len(df), len(df.columns)
    df = drop_nulls(df, threshold=drop_null_threshold,
                    row_threshold=row_null_threshold)
    if remove_dupes:
        df = remove_duplicates(df)
    # Parity with the REST /clean endpoint, which offers the same option.
    if remove_outlier_rows:
        df = remove_outliers_iqr(df, factor=outlier_factor)
    if standardise_cols:
        df = standardise_columns(df)
    return {
        "data": df_to_json(df),
        "rows": len(df),
        "columns": list(df.columns),
        "rows_in": rows_in,
        "columns_in": columns_in
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
        Dict with keys: data (transformed records), rows (int), columns (list)
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
    result = ops[operation](df, **params)
    return {
        "data": df_to_json(result),
        "rows": len(result),
        "columns": list(result.columns)
    }

@mcp.tool()
def merge_data(
    left: List[Dict[str, Any]],
    right: List[Dict[str, Any]],
    on: Optional[Any] = None,
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
        right_rows. Compare rows against left_rows/right_rows to spot a join
        that inflated the data.
    """
    if suffixes is None:
        suffixes = ["_x", "_y"]
    if len(suffixes) != 2:
        raise ValueError("suffixes must be a list of exactly two strings.")

    left_df = pd.DataFrame(left)
    right_df = pd.DataFrame(right)
    result = merge_dataframes(
        left_df, right_df, on=on, how=how,
        validate=validate, suffixes=tuple(suffixes),
    )
    return {
        "data": df_to_json(result),
        "rows": len(result),
        "columns": list(result.columns),
        "left_rows": len(left_df),
        "right_rows": len(right_df),
    }

@mcp.tool()
def analyse_data(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run a full statistical analysis on a dataset.
    Args:
        data: List of row dicts
    Returns:
        Dict containing: summary_stats, correlation_matrix, missing_values,
        and outliers
    """
    df = pd.DataFrame(data)
    # to_native is essential here, not cosmetic: full_report returns numpy
    # int64/float64, which MCP cannot serialise, and this tool failed outright
    # for every input until it was applied.
    return to_native(full_report(df))

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
        Dict[str, Any]: A JSON-serializable Vega-Lite spec dict representing the chart.
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

    return to_native(charts[chart](df, **params))

def main():
    mcp.run()

if __name__ == "__main__":
    main()
    
    