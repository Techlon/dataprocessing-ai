import pandas as pd
import numpy as np
from typing import List, Dict, Any

def summary_stats(df, columns=None):
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns
    stats = {}
    for column in columns:
        col_data = df[column]
        stats[column] = {
            'count': len(col_data), 'mean': col_data.mean(), 'median': col_data.median(),
            'std': col_data.std(), 'min': col_data.min(), 'max': col_data.max(),
            'quartiles': {'25%': np.percentile(col_data, 25), '75%': np.percentile(col_data, 75)}
        }
    return stats

def correlation_matrix(df, columns=None):
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns
    return df[columns].corr().to_dict()

def value_counts(df, column):
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ValueError("Column must be numeric")
    return df[column].value_counts().to_dict()

def missing_report(df):
    total = len(df)
    report = {}
    for column in df.columns:
        null_count = df[column].isnull().sum()
        percentage = (null_count / total) * 100 if total > 0 else 0
        report[column] = {'missing_count': int(null_count), 'percentage': float(percentage)}
    return report

def distribution(df, column, bins=10):
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ValueError("Column must be numeric")
    hist, bin_edges = np.histogram(df[column], bins=bins)
    return {'bin_edges': list(bin_edges), 'counts': list(hist)}

def detect_outliers(df, columns=None):
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns
    outliers = {}
    for column in columns:
        q1 = np.percentile(df[column], 25); q3 = np.percentile(df[column], 75)
        iqr = q3 - q1
        lo = q1 - 1.5 * iqr; hi = q3 + 1.5 * iqr
        outliers[column] = list(df[(df[column] < lo) | (df[column] > hi)].index)
    return outliers

def full_report(df):
    return {'summary_stats': summary_stats(df), 'correlation_matrix': correlation_matrix(df),
            'missing_values': missing_report(df), 'outliers': detect_outliers(df)}
