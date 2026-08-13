import warnings

import pandas as pd
import numpy as np
from typing import Optional

from dataprocessing._defaults import (
    DEFAULT_IQR_FACTOR, DEFAULT_NULL_THRESHOLD, DEFAULT_ROW_NULL_THRESHOLD,
    DEFAULT_TYPE_THRESHOLD, check_positive, check_share,
)


def drop_nulls(df, threshold=DEFAULT_NULL_THRESHOLD,
               row_threshold=DEFAULT_ROW_NULL_THRESHOLD, subset=None):
    """Drop mostly-null columns, then rows with too many nulls of their own.

    Both steps are governed the same way — something is dropped when its share
    of nulls *exceeds* the threshold:

    - `threshold` (0.5) applies down a column: drop a column more than half null.
    - `row_threshold` (0.0) applies across a row: at 0.0 any single null drops
      the row, which is what `dropna()` does and what this function always did.

    That row default is the lossiest thing in the library and, until now, the
    only part of it that could not be adjusted. On a frame with 5% of its cells
    missing at random it discards roughly a quarter of the rows, because a row
    only has to be unlucky once. Useful alternatives:

    - `row_threshold=1.0` keeps every row; a fully-null row has a share of 1.0,
      which does not exceed 1.0. Use this to drop dead columns and nothing else.
    - `row_threshold=0.5` drops rows that are more than half empty, keeping the
      merely patchy ones.
    - `subset=[...]` judges rows only on the columns you name, so a row survives
      a null in a column you do not care about. Use it to require the key fields
      and tolerate gaps elsewhere.

    Returns a new frame; the caller's DataFrame is left untouched.
    """
    check_share(threshold)
    check_share(row_threshold, name="row_threshold")

    if subset is not None:
        missing = [c for c in subset if c not in df.columns]
        if missing:
            raise ValueError(f"Column(s) not found: {missing}")

    cols_to_drop = df.columns[df.isnull().mean() > threshold]
    result = df.drop(columns=cols_to_drop)

    if subset is None:
        considered = result
    else:
        # A subset column may itself have just been dropped for being mostly
        # null. Judge rows on what actually survived rather than raising here.
        considered = result[[c for c in subset if c in result.columns]]

    if considered.shape[1] == 0:
        return result

    row_null_share = considered.isnull().mean(axis=1)
    return result[row_null_share <= row_threshold]


def _try_convert(series, threshold=DEFAULT_TYPE_THRESHOLD):
    """Return a converted series, or None to leave the column as text.

    A conversion is accepted only if at least `threshold` of the non-null values
    survive it. Without that guard, `pd.to_datetime(errors="coerce")` turns an
    ordinary text column — names, cities, product codes — entirely into NaT and
    destroys the data silently. The guard is what makes a speculative parse safe.
    """
    check_share(threshold)
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


def fix_types(df, threshold=DEFAULT_TYPE_THRESHOLD):
    """Coerce object columns to numeric or datetime where the data supports it.

    Columns that are already numeric, boolean, or datetime are left alone.
    Text that does not convert cleanly stays text.

    `threshold` is the share of a column's non-null values that must convert
    before the conversion is accepted, and 0.9 is a judgement rather than a
    fact — the right value depends on the data:

    - Raise it (0.99, or 1.0 for "only if everything converts") when a column
      could be *coincidentally* parseable. Product codes like "03-11-2024-A"
      may be 94% date-shaped, and accepting that conversion blanks the other 6%.
    - Lower it (say 0.7) for a genuine date column carrying messy entries —
      "N/A", "unknown", typos. At 0.9 the whole column stays text and you lose
      date handling for the 75% that were fine.

    Values that fail the accepted conversion become null, so a lower threshold
    trades data for usable types. That is the trade-off the number controls.
    """
    check_share(threshold)
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
        converted = _try_convert(df[col], threshold=threshold)
        if converted is not None:
            df[col] = converted
    return df


def remove_duplicates(df, subset=None):
    """Drop duplicate rows. Returns a new frame."""
    return df.drop_duplicates(subset=subset)


def remove_outliers(df, columns=None, method='iqr', factor=DEFAULT_IQR_FACTOR):
    """Drop rows holding an IQR outlier in any of the given numeric columns.

    `factor` is the multiplier on the interquartile range that sets the fence.
    1.5 is Tukey's convention; 3.0 marks only 'far out' points and so removes
    fewer rows. Because this drops whole rows, widening the fence is the
    conservative choice when the extreme values might be real observations.
    """
    if method != 'iqr':
        raise ValueError(f"Unknown method: {method!r}. Only 'iqr' is supported.")
    check_positive(factor)

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
    lower = Q1 - factor * IQR
    upper = Q3 + factor * IQR
    return df[~((numeric_df < lower) | (numeric_df > upper)).any(axis=1)]


def standardise_columns(df):
    """Lowercase column names, trim surrounding whitespace, underscore spaces.

    `str(col)` rather than `col.lower()`: pivot and group operations produce
    non-string column labels, which the bare attribute access crashed on.
    """
    df = df.copy()
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    return df


def clean_all(df, remove_outlier_rows=True, null_threshold=DEFAULT_NULL_THRESHOLD,
              row_null_threshold=DEFAULT_ROW_NULL_THRESHOLD,
              type_threshold=DEFAULT_TYPE_THRESHOLD,
              outlier_factor=DEFAULT_IQR_FACTOR):
    """Run the full cleaning pipeline.

    Note that this is lossy by design, and more so than it looks: `drop_nulls`
    removes every row containing any null, so a frame with 5% of cells missing
    can lose around a quarter of its rows. Callers that need to know how much
    went should compare `len()` before and after — the REST and MCP interfaces
    report `rows_in` alongside `rows` for exactly this reason.

    `remove_outlier_rows` is exposed because dropping outliers is a judgement,
    not a repair: the extreme value is sometimes the observation that matters.
    It defaults to True to preserve the behaviour of earlier releases.

    Each step's judgement value is named separately, because they govern
    different things and a single `threshold` argument would be ambiguous:

    - `null_threshold` — share of nulls above which a column is dropped (0.5)
    - `row_null_threshold` — share of nulls above which a *row* is dropped
      (0.0, meaning any null at all; raise it to keep patchy rows)
    - `type_threshold` — share of values that must convert before a column's
      type is changed, see `fix_types` (0.9)
    - `outlier_factor` — multiplier on the IQR that sets the outlier fence,
      see `remove_outliers` (1.5)

    All keep the defaults of earlier releases, so calling `clean_all(df)`
    behaves exactly as before.
    """
    df = drop_nulls(df, threshold=null_threshold, row_threshold=row_null_threshold)
    df = fix_types(df, threshold=type_threshold)
    df = remove_duplicates(df)
    if remove_outlier_rows:
        df = remove_outliers(df, factor=outlier_factor)
    df = standardise_columns(df)
    return df
