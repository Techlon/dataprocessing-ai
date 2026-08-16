import pandas as pd
import numpy as np
from typing import Callable, Dict, List, Union

_OPERATORS = ('eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'contains', 'startswith', 'endswith')
_MERGE_HOWS = ('inner', 'left', 'right', 'outer', 'cross')
# Aggregations that need numbers. Applying these to text raises deep inside
# pandas as "dtype 'str' does not support operation 'mean'", which names the
# operation but not the column that caused it.
_NUMERIC_AGGFUNCS = ('mean', 'sum', 'median', 'std', 'var', 'prod', 'sem', 'quantile')


from dataprocessing._columns import not_found_message, require_column as _require_column, suggest


def _missing_message(missing, available, label="Column(s)", where=None, other_side=None):
    location = f" in the {where}" if where else ""
    hints = []
    for name in missing:
        matches = suggest(name, available)
        if matches:
            hints.append(f"{name!r} -> {matches[0]!r}")
    message = f"{label} {missing} not found{location}."
    if hints:
        message += " Did you mean: " + ", ".join(hints) + "?"
    if other_side is not None and hints:
        # The two frames spell the key differently — usually because one has
        # been through clean() and the other has not. No single `on` can work.
        message += (" The two frames name this key differently; pass left_on "
                    "and right_on instead of on.")
    return message


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
        raise ValueError(_missing_message(missing, df.columns))
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
        raise ValueError(_missing_message(missing, df.columns))

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


def merge_dataframes(df1, df2, on=None, how='inner', validate=None,
                     suffixes=('_x', '_y'), left_on=None, right_on=None):
    """Merge two frames on a shared key, or on differently-named keys.

    `validate` is passed through to pandas and is the guard against the quiet
    failure mode of joins: an unintended many-to-many match multiplies rows
    rather than erroring, so a 3-row frame can come back with 9 rows and no
    indication anything went wrong. Pass "one_to_one" or "many_to_one" when you
    expect those, and the mismatch raises instead of inflating the data.

    Use `left_on`/`right_on` when the two frames spell the key differently.
    That is not an exotic case here: `clean` standardises column names, so a
    cleaned frame joined to a freshly ingested one has `customer_id` on one side
    and `Customer ID` on the other, and no single `on` value can work. Found by
    running a realistic pipeline through the MCP tools, where it was a dead end.

    Columns present in both frames and not joined on are suffixed, `_x` for the
    left and `_y` for the right by default.
    """
    if how not in _MERGE_HOWS:
        raise ValueError(f"Invalid how: {how!r}. Valid: {list(_MERGE_HOWS)}")

    if how == 'cross':
        return pd.merge(df1, df2, how=how, suffixes=suffixes)

    if on is not None and (left_on is not None or right_on is not None):
        raise ValueError("Pass either 'on', or 'left_on' and 'right_on' — not both.")
    if on is None and bool(left_on) != bool(right_on):
        raise ValueError("'left_on' and 'right_on' must be given together.")

    if on is not None:
        left_keys = right_keys = _as_list(on)
    elif left_on:
        left_keys, right_keys = _as_list(left_on), _as_list(right_on)
        if len(left_keys) != len(right_keys):
            raise ValueError(
                f"'left_on' names {len(left_keys)} column(s) and 'right_on' names "
                f"{len(right_keys)}; they must match one for one."
            )
    else:
        raise ValueError("'on' must name at least one join column.")

    missing_left = [k for k in left_keys if k not in df1.columns]
    missing_right = [k for k in right_keys if k not in df2.columns]
    # Name the side AND suggest a near match: cleaning standardises column
    # names, so joining a cleaned frame to a freshly ingested one fails here
    # with the caller holding the right column under its previous spelling.
    if missing_left:
        raise ValueError(_missing_message(
            missing_left, df1.columns, "Join column(s)", "left frame",
            other_side=df2.columns if on is not None else None))
    if missing_right:
        raise ValueError(_missing_message(
            missing_right, df2.columns, "Join column(s)", "right frame",
            other_side=df1.columns if on is not None else None))

    try:
        if on is not None:
            return pd.merge(df1, df2, on=on, how=how, validate=validate, suffixes=suffixes)
        return pd.merge(df1, df2, left_on=left_on, right_on=right_on, how=how,
                        validate=validate, suffixes=suffixes)
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
