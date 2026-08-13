import pandas as pd
import numpy as np
from typing import List, Dict, Any

from dataprocessing._defaults import DEFAULT_IQR_FACTOR, check_positive


def _require_column(df, column):
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist.")


def _numeric_columns(df):
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _num(value):
    """Return a JSON-safe float, or None where the statistic is undefined.

    std of a single value, and every statistic of an all-null column, are NaN.
    NaN is not a JSON value, so it is reported as null rather than emitted raw.
    """
    value = float(value)
    return None if value != value else value


def summary_stats(df, columns=None):
    """Summary statistics per numeric column, computed over non-null values.

    `count` is the number of non-null values, and `null_count` reports what was
    excluded. Quartiles use pandas' `quantile`, which skips nulls; the previous
    `np.percentile` returned NaN for every statistic if a column held a single
    null, so any real dataset produced an all-NaN report.
    """
    if columns is None:
        columns = _numeric_columns(df)

    stats = {}
    for column in columns:
        _require_column(df, column)
        col_data = df[column].dropna()
        null_count = int(df[column].isna().sum())

        if col_data.empty:
            stats[column] = {
                'count': 0, 'null_count': null_count,
                'mean': None, 'median': None, 'std': None, 'min': None, 'max': None,
                'quartiles': {'25%': None, '75%': None},
            }
            continue

        stats[column] = {
            'count': int(col_data.count()),
            'null_count': null_count,
            'mean': _num(col_data.mean()),
            'median': _num(col_data.median()),
            'std': _num(col_data.std()),
            'min': _num(col_data.min()),
            'max': _num(col_data.max()),
            'quartiles': {
                '25%': _num(col_data.quantile(0.25)),
                '75%': _num(col_data.quantile(0.75)),
            },
        }
    return stats


def correlation_matrix(df, columns=None):
    """Pairwise correlations across numeric columns.

    A zero-variance column and a single-row frame both produce undefined
    correlations. These are reported as None rather than NaN, matching the rest
    of the module and keeping the result valid JSON.
    """
    if columns is None:
        columns = _numeric_columns(df)
    columns = list(columns)
    for column in columns:
        _require_column(df, column)
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise ValueError(f"'{column}' is not a numeric column.")
    if not columns:
        return {}
    matrix = df[columns].corr().to_dict()
    return {
        outer: {inner: _num(value) for inner, value in row.items()}
        for outer, row in matrix.items()
    }


def value_counts(df, column, dropna=True):
    """Count occurrences of each distinct value in a column, of any dtype.

    Counting is a categorical operation, so the columns most worth counting are
    text ones — categories, labels, city names. This previously rejected
    anything non-numeric, which excluded exactly its useful cases.
    """
    _require_column(df, column)
    counts = df[column].value_counts(dropna=dropna)
    return {key: int(count) for key, count in counts.items()}


def missing_report(df):
    total = len(df)
    report = {}
    for column in df.columns:
        null_count = df[column].isnull().sum()
        percentage = (null_count / total) * 100 if total > 0 else 0
        report[column] = {'missing_count': int(null_count), 'percentage': float(percentage)}
    return report


def distribution(df, column, bins=10):
    _require_column(df, column)
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ValueError(f"'{column}' is not a numeric column.")
    col_data = df[column].dropna()
    if col_data.empty:
        return {'bin_edges': [], 'counts': []}
    hist, bin_edges = np.histogram(col_data, bins=bins)
    return {
        'bin_edges': [float(edge) for edge in bin_edges],
        'counts': [int(count) for count in hist],
    }


def detect_outliers(df, columns=None, factor=DEFAULT_IQR_FACTOR):
    """Index labels of IQR outliers, per numeric column.

    Bounds are computed over non-null values. Previously a single null made
    every bound NaN, every comparison False, and the report came back empty —
    a confident "no outliers" for a column that had them.

    `factor` is the multiplier on the interquartile range. It shares a default
    with `clean.remove_outliers`, so what this reports is what that would drop.
    """
    check_positive(factor)
    if columns is None:
        columns = _numeric_columns(df)

    outliers = {}
    for column in columns:
        _require_column(df, column)
        col = df[column]
        col_data = col.dropna()
        if col_data.empty:
            outliers[column] = []
            continue
        q1 = col_data.quantile(0.25)
        q3 = col_data.quantile(0.75)
        iqr = q3 - q1
        lo = q1 - factor * iqr
        hi = q3 + factor * iqr
        mask = (col < lo) | (col > hi)
        outliers[column] = [
            label.item() if hasattr(label, 'item') else label
            for label in df.index[mask.fillna(False)]
        ]
    return outliers


def full_report(df):
    return {'summary_stats': summary_stats(df), 'correlation_matrix': correlation_matrix(df),
            'missing_values': missing_report(df), 'outliers': detect_outliers(df)}
