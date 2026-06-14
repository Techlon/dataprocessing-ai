import pandas as pd
import numpy as np
from typing import Callable, Dict, List, Union

def filter_rows(df: pd.DataFrame, column: str, operator: str, value: Union[int, float, str]) -> pd.DataFrame:
    if operator == 'eq':
        return df[df[column] == value]
    elif operator == 'ne':
        return df[df[column] != value]
    elif operator == 'gt':
        return df[df[column] > value]
    elif operator == 'lt':
        return df[df[column] < value]
    elif operator == 'gte':
        return df[df[column] >= value]
    elif operator == 'lte':
        return df[df[column] <= value]
    elif operator == 'contains':
        return df[df[column].astype(str).str.contains(value)]
    elif operator == 'startswith':
        return df[df[column].astype(str).str.startswith(value)]
    elif operator == 'endswith':
        return df[df[column].astype(str).str.endswith(value)]
    else:
        raise ValueError("Invalid operator")

def select_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    return df[columns]

def rename_columns(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    return df.rename(columns=mapping)

def sort_rows(df: pd.DataFrame, columns: List[str], ascending: bool = True) -> pd.DataFrame:
    return df.sort_values(by=columns, ascending=ascending)

def group_and_aggregate(df: pd.DataFrame, group_by: List[str], aggregations: Dict[str, Callable]) -> pd.DataFrame:
    return df.groupby(group_by).agg(aggregations)

def pivot(df: pd.DataFrame, index: str, columns: str, values: str, aggfunc: str = 'mean') -> pd.DataFrame:
    return df.pivot_table(index=index, columns=columns, values=values, aggfunc=aggfunc)

def merge_dataframes(df1: pd.DataFrame, df2: pd.DataFrame, on: str, how: str = 'inner') -> pd.DataFrame:
    return pd.merge(df1, df2, on=on, how=how)

def add_column(df: pd.DataFrame, column_name: str, expression: str) -> pd.DataFrame:
    df[column_name] = eval('df.' + expression)
    return df