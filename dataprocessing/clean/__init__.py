import pandas as pd
import numpy as np
from typing import Optional

def drop_nulls(df, threshold=0.5):
    cols_to_drop = df.columns[df.isnull().mean() > threshold]
    df.drop(columns=cols_to_drop, inplace=True)
    df.dropna(inplace=True)
    return df

def fix_types(df):
    for col in df.columns:
        # Check bool BEFORE numeric: pandas treats bool as a numeric dtype, so
        # the numeric branch would otherwise swallow boolean columns.
        if pd.api.types.is_bool_dtype(df[col]):
            df[col] = df[col].astype(bool)
        elif pd.api.types.is_numeric_dtype(df[col]):
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except Exception as e:
                print(f"Error converting column {col} to numeric: {e}")
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        else:
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
            except Exception as e:
                print(f"Error converting column {col} to datetime: {e}")
    return df

def remove_duplicates(df, subset=None):
    if subset is not None:
        df.drop_duplicates(subset=subset, inplace=True)
    else:
        df.drop_duplicates(inplace=True)
    return df

def remove_outliers(df, columns=None, method='iqr'):
    if method == 'iqr':
        if columns is None:
            numeric_df = df.select_dtypes(include=[np.number])
        else:
            numeric_df = df[columns]
        Q1 = numeric_df.quantile(0.25); Q3 = numeric_df.quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR; upper = Q3 + 1.5 * IQR
        df = df[~((numeric_df < lower) | (numeric_df > upper)).any(axis=1)]
    return df

def standardise_columns(df):
    df.columns = [col.lower().replace(" ", "_") for col in df.columns]
    return df

def clean_all(df):
    df = drop_nulls(df)
    df = fix_types(df)
    df = remove_duplicates(df)
    df = remove_outliers(df)
    df = standardise_columns(df)
    return df
