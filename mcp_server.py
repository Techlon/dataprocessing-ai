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

from dataprocessing.ingest import read_file
from dataprocessing.clean import drop_nulls, remove_duplicates, standardise_columns
from dataprocessing.transform import (
    filter_rows, select_columns, rename_columns,
    sort_rows, group_and_aggregate, add_column
)
from dataprocessing.analyse import full_report

mcp = FastMCP("DataProcessing")

def df_to_json(df: pd.DataFrame) -> List[Dict]:
    return json.loads(df.where(df.notna(), other=None).to_json(orient="records"))

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
    drop_null_threshold: float = 0.5,
    remove_dupes: bool = True,
    standardise_cols: bool = True
) -> Dict[str, Any]:
    """
    Clean a dataset by removing nulls, duplicates and standardising column names.
    Args:
        data: List of row dicts (from ingest_file or any source)
        drop_null_threshold: Drop columns with more than this fraction of nulls (0.0-1.0)
        remove_dupes: Whether to remove duplicate rows
        standardise_cols: Whether to lowercase and underscore column names
    Returns:
        Dict with keys: data (cleaned records), rows (int), columns (list)
    """
    df = pd.DataFrame(data)
    df = drop_nulls(df, threshold=drop_null_threshold)
    if remove_dupes:
        df = remove_duplicates(df)
    if standardise_cols:
        df = standardise_columns(df)
    return {
        "data": df_to_json(df),
        "rows": len(df),
        "columns": list(df.columns)
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
                   sort_rows, group_and_aggregate, add_column
        params: Parameters for the operation, e.g.:
                filter_rows    -> {column, operator, value}
                select_columns -> {columns: [list]}
                rename_columns -> {mapping: {old: new}}
                sort_rows      -> {columns: [list], ascending: true}
                group_and_aggregate -> {group_by: [list], aggregations: {col: func}}
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
def analyse_data(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run a full statistical analysis on a dataset.
    Args:
        data: List of row dicts
    Returns:
        Dict containing: summary_stats, correlation_matrix, missing_report,
        value_counts per column, and outlier detection results
    """
    df = pd.DataFrame(data)
    return full_report(df)

if __name__ == "__main__":
    mcp.run()
