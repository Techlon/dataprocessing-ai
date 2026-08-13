import pandas as pd
import numpy as np
from typing import Callable, Dict, List, Union

_OPERATORS = ('eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'contains', 'startswith', 'endswith')
_MERGE_HOWS = ('inner', 'left', 'right', 'outer', 'cross')
# Aggregations that need numbers. Applying these to text raises deep inside
# pandas as "dtype 'str' does not support operation 'mean'", which names the
# operation but not the column that caused it.
_NUMERIC_AGGFUNCS = ('mean', 'sum', 'median', 'std', 'var', 'prod', 'sem', 'quantile')


def _require_column(df, column):
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist.")


def _as_list(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def filter_rows(df, column, operator, value):
    _require_column(df, column)
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
        return df[df[column].astype(str).str.contains(value, na=False)]
    elif operator == 'startswith':
        return df[df[column].astype(str).str.startswith(value, na=False)]
    elif operator == 'endswith':
        return df[df[column].astype(str).str.endswith(value, na=False)]
    else:
        raise ValueError(f"Invalid operator: {operator!r}. Valid: {list(_OPERATORS)}")


def select_columns(df, columns):
    columns = _as_list(columns)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {missing}")
    repeated = sorted({c for c in columns if columns.count(c) > 1})
    if repeated:
        # A repeated name produces duplicate columns, which then fail at the
        # JSON boundary with "DataFrame columns must be unique" — far from here.
        raise ValueError(f"Column(s) requested more than once: {repeated}")
    return df[columns]


def rename_columns(df, mapping):
    """Rename columns. Both a missing source name and a colliding result raise.

    Renaming a name that does not exist used to be a silent no-op: the caller
    was told the operation succeeded while nothing changed. A rename that
    collides with an existing name used to produce duplicate columns, which
    then failed later at the JSON boundary rather than here.
    """
    if not isinstance(mapping, dict):
        raise ValueError("mapping must be a dict of {old_name: new_name}")
    missing = [old for old in mapping if old not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {missing}")

    result = df.rename(columns=mapping)
    duplicated = sorted(set(result.columns[result.columns.duplicated()]))
    if duplicated:
        raise ValueError(f"Rename would produce duplicate column name(s): {duplicated}")
    return result


def sort_rows(df, columns, ascending=True):
    for column in (columns if isinstance(columns, (list, tuple)) else [columns]):
        _require_column(df, column)
    return df.sort_values(by=columns, ascending=ascending)


def group_and_aggregate(df, group_by, aggregations):
    """Group and aggregate. Grouping keys land in the index, per pandas.

    Callers crossing a JSON boundary should use `_serialise.df_to_json`, which
    resets a named index so the keys survive.
    """
    for column in _as_list(group_by):
        _require_column(df, column)
    if not isinstance(aggregations, dict):
        raise ValueError("aggregations must be a dict of {column: function}")
    for column in aggregations:
        _require_column(df, column)

    try:
        return df.groupby(group_by).agg(aggregations)
    except AttributeError as e:
        # An unknown function name surfaces as "'SeriesGroupBy' object has no
        # attribute 'totalise'", which reads like an internal fault.
        raise ValueError(f"Invalid aggregation function in {aggregations!r}: {e}") from e


def pivot(df, index, columns, values, aggfunc='mean'):
    for column in _as_list(index) + _as_list(columns) + _as_list(values):
        _require_column(df, column)

    if aggfunc in _NUMERIC_AGGFUNCS:
        for column in _as_list(values):
            if not pd.api.types.is_numeric_dtype(df[column]):
                raise ValueError(
                    f"'{column}' is not numeric, so aggfunc={aggfunc!r} cannot be "
                    f"applied. Use aggfunc='first', 'count' or 'nunique' for text values."
                )

    return df.pivot_table(index=index, columns=columns, values=values, aggfunc=aggfunc)


def merge_dataframes(df1, df2, on, how='inner', validate=None, suffixes=('_x', '_y')):
    """Merge two frames on a shared key.

    `validate` is passed through to pandas and is the guard against the quiet
    failure mode of joins: an unintended many-to-many match multiplies rows
    rather than erroring, so a 3-row frame can come back with 9 rows and no
    indication anything went wrong. Pass "one_to_one" or "many_to_one" when you
    expect those, and the mismatch raises instead of inflating the data.

    Columns present in both frames and not joined on are suffixed, `_x` for the
    left and `_y` for the right by default.
    """
    if how not in _MERGE_HOWS:
        raise ValueError(f"Invalid how: {how!r}. Valid: {list(_MERGE_HOWS)}")

    if how == 'cross':
        return pd.merge(df1, df2, how=how, suffixes=suffixes)

    keys = _as_list(on)
    if not keys:
        raise ValueError("'on' must name at least one join column.")
    missing_left = [k for k in keys if k not in df1.columns]
    missing_right = [k for k in keys if k not in df2.columns]
    if missing_left:
        raise ValueError(f"Join column(s) {missing_left} not in the left frame.")
    if missing_right:
        raise ValueError(f"Join column(s) {missing_right} not in the right frame.")

    try:
        return pd.merge(df1, df2, on=on, how=how, validate=validate, suffixes=suffixes)
    except pd.errors.MergeError as e:
        raise ValueError(str(e)) from e


def add_column(df, column_name, expression):
    # Use pandas' sandboxed expression evaluator rather than the builtin eval().
    # df.eval understands column arithmetic (e.g. "A + C", "price * 1.2") but
    # cannot import modules or run arbitrary Python, so it is safe to expose to
    # API callers. Column names are referenced bare: "A + C", not "A + df.C".
    df = df.copy()
    df[column_name] = df.eval(expression)
    return df
