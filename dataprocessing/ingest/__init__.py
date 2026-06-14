import pandas as pd
from pathlib import Path
from typing import Union

def read_csv(file_path: str) -> pd.DataFrame:
    """
    Reads a CSV file and returns a pandas DataFrame.
    
    Parameters:
        file_path (str): The path to the CSV file.
        
    Returns:
        pd.DataFrame: A DataFrame containing the data from the CSV file.
    """
    try:
        return pd.read_csv(file_path)
    except Exception as e:
        raise ValueError(f"Error reading CSV file {file_path}: {e}")

def read_json(file_path: str) -> pd.DataFrame:
    """
    Reads a JSON file and returns a pandas DataFrame.
    
    Parameters:
        file_path (str): The path to the JSON file.
        
    Returns:
        pd.DataFrame: A DataFrame containing the data from the JSON file.
    """
    try:
        return pd.read_json(file_path)
    except Exception as e:
        raise ValueError(f"Error reading JSON file {file_path}: {e}")

def read_excel(file_path: str) -> pd.DataFrame:
    """
    Reads an Excel (.xlsx) file and returns a pandas DataFrame.
    
    Parameters:
        file_path (str): The path to the Excel file.
        
    Returns:
        pd.DataFrame: A DataFrame containing the data from the Excel file.
    """
    try:
        return pd.read_excel(file_path)
    except Exception as e:
        raise ValueError(f"Error reading Excel file {file_path}: {e}")

def read_parquet(file_path: str) -> pd.DataFrame:
    """
    Reads a Parquet file and returns a pandas DataFrame.
    
    Parameters:
        file_path (str): The path to the Parquet file.
        
    Returns:
        pd.DataFrame: A DataFrame containing the data from the Parquet file.
    """
    try:
        return pd.read_parquet(file_path)
    except Exception as e:
        raise ValueError(f"Error reading Parquet file {file_path}: {e}")

def read_txt(file_path: str) -> pd.DataFrame:
    """
    Reads a plain text file and returns a pandas DataFrame. The text file is assumed to be comma-separated if no delimiter is specified.
    
    Parameters:
        file_path (str): The path to the text file.
        
    Returns:
        pd.DataFrame: A DataFrame containing the data from the text file.
    """
    try:
        return pd.read_csv(file_path, delimiter=",") if Path(file_path).suffix == ".txt" else pd.read_csv(file_path)
    except Exception as e:
        raise ValueError(f"Error reading text file {file_path}: {e}")

def read_file(file_path: str) -> pd.DataFrame:
    """
    Dispatches the appropriate reader function based on the file extension.
    
    Parameters:
        file_path (str): The path to the file.
        
    Returns:
        pd.DataFrame: A DataFrame containing the data from the file.
    """
    ext = Path(file_path).suffix.lower()
    if ext == ".csv":
        return read_csv(file_path)
    elif ext == ".json":
        return read_json(file_path)
    elif ext == ".xlsx":
        return read_excel(file_path)
    elif ext == ".parquet":
        return read_parquet(file_path)
    elif ext == ".txt":
        return read_txt(file_path)
    else:
        raise ValueError(f"Unsupported file format for {file_path}")