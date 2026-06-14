import pandas as pd
import numpy as np
from typing import List, Dict, Any

def summary_stats(df: pd.DataFrame, columns: List[str] = None) -> Dict[str, Any]:
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns
    stats = {}
    for column in columns:
        col_data = df[column]
        stats[column] = {
            'count': len(col_data),
            'mean': col_data.mean(),
            'median': col_data.median(),
            'std': col_data.std(),
            'min': col_data.min(),
            'max': col_data.max(),
            'quartiles': {
                '25%': np.percentile(col_data, 25),
                '75%': np.percentile(col_data, 75)
            }
        }
    return stats

def correlation_matrix(df: pd.DataFrame, columns: List[str] = None) -> Dict[str, Any]:
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns
    corr_matrix = df[columns].corr()
    return corr_matrix.to_dict()

def value_counts(df: pd.DataFrame, column: str) -> Dict[Any, int]:
    if not np.issubdtype(df[column].dtype, np.number):
        raise ValueError("Column must be numeric")
    return df[column].value_counts().to_dict()

def missing_report(df: pd.DataFrame) -> Dict[str, Any]:
    total = len(df)
    report = {}
    for column in df.columns:
        null_count = df[column].isnull().sum()
        percentage = (null_count / total) * 100 if total > 0 else 0
        report[column] = {
            'missing_count': int(null_count),
            'percentage': float(percentage)
        }
    return report

def distribution(df: pd.DataFrame, column: str, bins: int = 10) -> Dict[str, Any]:
    if not np.issubdtype(df[column].dtype, np.number):
        raise ValueError("Column must be numeric")
    hist, bin_edges = np.histogram(df[column], bins=bins)
    return {
        'bin_edges': list(bin_edges),
        'counts': list(hist)
    }

def detect_outliers(df: pd.DataFrame, columns: List[str] = None) -> Dict[str, Any]:
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns
    outliers = {}
    for column in columns:
        q1 = np.percentile(df[column], 25)
        q3 = np.percentile(df[column], 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outliers_in_col = df[(df[column] < lower_bound) | (df[column] > upper_bound)]
        outliers[column] = list(outliers_in_col.index)
    return outliers

def full_report(df: pd.DataFrame) -> Dict[str, Any]:
    report = {
        'summary_stats': summary_stats(df),
        'correlation_matrix': correlation_matrix(df),
        'missing_values': missing_report(df),
        'outliers': detect_outliers(df),
        # Assuming value_counts is not needed in the final report based on provided requirements
    }
    return report