import warnings

import pandas as pd
import numpy as np
from typing import Optional


def drop_nulls(df, threshold=0.5):
    """Drop columns whose null share exceeds `threshold`, then drop null rows.

    Returns a new frame; the caller's DataFrame is left untouched.
    """
    cols_to_drop = df.columns[df.isnull().mean() > threshold]
    return df.drop(columns=cols_to_drop).dropna()


def _try_convert(series, threshold=0.9):
    """Return a converted series, or None to leave the column as text.

    A conversion is accepted only if at least `threshold` of the non-null values
    survive it. Without that guard, `pd.to_datetime(errors="coerce")` turns an
    ordinary text column — names, cities, product codes — entirely into NaT and
    destroys the data silently. The guard is what makes a speculative parse safe.
    """
    non_null = int(series.notna().sum())
    if non_null == 0:
        return None

    numeric = pd.to_numeric(series, errors="coerce")
    if int(numeric.notna().sum()) >= threshold * non_null:
        return numeric

    # This parse is a hypothesis, not an assertion, so pandas' "could not infer
    # format" warning is expected noise here rather than signal. It is silenced
    # for the trial only; a column that genuinely parses is still converted.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        try:
            dates = pd.to_datetime(series, errors="coerce")
        except Exception:
            return None
    if int(dates.notna().sum()) >= threshold * non_null:
        return dates

    return None


def fix_types(df):
    """Coerce object columns to numeric or datetime where the data supports it.

    Columns that are already numeric, boolean, or datetime are left alone.
    Text that does not convert cleanly stays text.
    """
    df = df.copy()
    for col in df.columns:
        # Check bool BEFORE numeric: pandas treats bool as a numeric dtype, so
        # the numeric branch would otherwise swallow boolean columns.
        if pd.api.types.is_bool_dtype(df[col]):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        converted = _try_convert(df[col])
        if converted is not None:
            df[col] = converted
    return df


def remove_duplicates(df, subset=None):
    """Drop duplicate rows. Returns a new frame."""
    return df.drop_duplicates(subset=subset)


def remove_outliers(df, columns=None, method='iqr'):
    """Drop rows holding an IQR outlier in any of the given numeric columns."""
    if method != 'iqr':
        raise ValueError(f"Unknown method: {method!r}. Only 'iqr' is supported.")

    if columns is None:
        numeric_df = df.select_dtypes(include=[np.number])
    else:
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise ValueError(f"Column(s) not found: {missing}")
        non_numeric = [c for c in columns if not pd.api.types.is_numeric_dtype(df[c])]
        if non_numeric:
            raise ValueError(f"Column(s) not numeric: {non_numeric}")
        numeric_df = df[columns]

    if numeric_df.shape[1] == 0 or numeric_df.empty:
        return df

    Q1 = numeric_df.quantile(0.25)
    Q3 = numeric_df.quantile(0.75)
    IQR = Q3 - Q1
    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR
    return df[~((numeric_df < lower) | (numeric_df > upper)).any(axis=1)]


def standardise_columns(df):
    """Lowercase column names, trim surrounding whitespace, underscore spaces.

    `str(col)` rather than `col.lower()`: pivot and group operations produce
    non-string column labels, which the bare attribute access crashed on.
    """
    df = df.copy()
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    return df


def clean_all(df, remove_outlier_rows=True):
    """Run the full cleaning pipeline.

    Note that this is lossy by design, and more so than it looks: `drop_nulls`
    removes every row containing any null, so a frame with 5% of cells missing
    can lose around a quarter of its rows. Callers that need to know how much
    went should compare `len()` before and after — the REST and MCP interfaces
    report `rows_in` alongside `rows` for exactly this reason.

    `remove_outlier_rows` is exposed because dropping outliers is a judgement,
    not a repair: the extreme value is sometimes the observation that matters.
    It defaults to True to preserve the behaviour of earlier releases.
    """
    df = drop_nulls(df)
    df = fix_types(df)
    df = remove_duplicates(df)
    if remove_outlier_rows:
        df = remove_outliers(df)
    df = standardise_columns(df)
    return df
