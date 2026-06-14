import pandas as pd
import numpy as np
from typing import Optional

def drop_nulls(df: pd.DataFrame, threshold: float = 0.5) -> pd.DataFrame:
    """
    Drops columns where more than a specified threshold of values are null, then drops remaining rows with any nulls.
    
    Args:
        df (pd.DataFrame): The DataFrame to clean.
        threshold (float): The percentage threshold for null values in a column to be dropped. Default is 0.5.
        
    Returns:
        pd.DataFrame: A cleaned DataFrame with specified columns and rows removed based on null values.
    """
    # Drop columns with more than the threshold of nulls
    cols_to_drop = df.columns[df.isnull().mean() > threshold]
    df.drop(columns=cols_to_drop, inplace=True)
    
    # Drop rows with any nulls
    df.dropna(inplace=True)
    return df

def fix_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Automatically detects and converts columns to the correct dtype (numeric, datetime, boolean, string).
    
    Args:
        df (pd.DataFrame): The DataFrame to clean.
        
    Returns:
        pd.DataFrame: A cleaned DataFrame with inferred dtypes for each column.
    """
    for col in df.columns:
        if np.issubdtype(df[col].dtype, np.number):
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except Exception as e:
                print(f"Error converting column {col} to numeric: {e}")
        elif df[col].dtype == 'datetime64[ns]':
            continue
        elif np.issubdtype(df[col].dtype, np.bool_):
            df[col] = df[col].astype(bool)
        else:
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
            except Exception as e:
                print(f"Error converting column {col} to datetime: {e}")
    return df

def remove_duplicates(df: pd.DataFrame, subset: Optional[list] = None) -> pd.DataFrame:
    """
    Removes duplicate rows, optionally based on a subset of columns.
    
    Args:
        df (pd.DataFrame): The DataFrame to clean.
        subset (Optional[list]): A list of column names to consider when identifying duplicates. If None, all columns are used.
        
    Returns:
        pd.DataFrame: A cleaned DataFrame with duplicate rows removed.
    """
    if subset is not None:
        df.drop_duplicates(subset=subset, inplace=True)
    else:
        df.drop_duplicates(inplace=True)
    return df

def remove_outliers(df: pd.DataFrame, columns: Optional[list] = None, method: str = 'iqr') -> pd.DataFrame:
    """
    Removes outliers using the IQR method on numeric columns.
    
    Args:
        df (pd.DataFrame): The DataFrame to clean.
        columns (Optional[list]): A list of column names to consider for removing outliers. If None, all numeric columns are used.
        method (str): The method to use for detecting outliers. Currently supports 'iqr' only.
        
    Returns:
        pd.DataFrame: A cleaned DataFrame with outliers removed.
    """
    if method == 'iqr':
        if columns is None:
            numeric_df = df.select_dtypes(include=[np.number])
        else:
            numeric_df = df[columns]
        
        Q1 = numeric_df.quantile(0.25)
        Q3 = numeric_df.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        df = df[~((numeric_df < lower_bound) | (numeric_df > upper_bound)).any(axis=1)]
    return df

def standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lowercases column names, replaces spaces with underscores, strips whitespace.
    
    Args:
        df (pd.DataFrame): The DataFrame to clean.
        
    Returns:
        pd.DataFrame: A cleaned DataFrame with standardized column names.
    """
    df.columns = [col.lower().replace(" ", "_") for col in df.columns]
    return df

def clean_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    Runs all the cleaning functions in the correct order and returns a cleaned DataFrame.
    
    Args:
        df (pd.DataFrame): The DataFrame to clean.
        
    Returns:
        pd.DataFrame: A completely cleaned DataFrame.
    """
    df = drop_nulls(df)
    df = fix_types(df)
    df = remove_duplicates(df)
    df = remove_outliers(df)
    df = standardise_columns(df)
    return df