import pandas as pd
import numpy as np
from typing import Callable, Dict, List, Union

def filter_rows(df, column, operator, value):
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

def select_columns(df, columns):
    return df[columns]

def rename_columns(df, mapping):
    return df.rename(columns=mapping)

def sort_rows(df, columns, ascending=True):
    return df.sort_values(by=columns, ascending=ascending)

def group_and_aggregate(df, group_by, aggregations):
    return df.groupby(group_by).agg(aggregations)

def pivot(df, index, columns, values, aggfunc='mean'):
    return df.pivot_table(index=index, columns=columns, values=values, aggfunc=aggfunc)

def merge_dataframes(df1, df2, on, how='inner'):
    return pd.merge(df1, df2, on=on, how=how)

def add_column(df, column_name, expression):
    # Use pandas' sandboxed expression evaluator rather than the builtin eval().
    # df.eval understands column arithmetic (e.g. "A + C", "price * 1.2") but
    # cannot import modules or run arbitrary Python, so it is safe to expose to
    # API callers. Column names are referenced bare: "A + C", not "A + df.C".
    df[column_name] = df.eval(expression)
    return df
