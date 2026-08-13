import json
from pathlib import Path
from typing import Union

import pandas as pd

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

    A file holding a single JSON object of scalars — `{"a": 1, "b": 2}` — is a
    perfectly ordinary one-row export, but pd.read_json rejects it with "If
    using all scalar values, you must pass an index". Such a file is read as
    one row rather than failing.

    Parameters:
        file_path (str): The path to the JSON file.

    Returns:
        pd.DataFrame: A DataFrame containing the data from the JSON file.
    """
    try:
        return pd.read_json(file_path)
    except ValueError:
        try:
            with open(file_path) as handle:
                payload = json.load(handle)
        except Exception as e:
            raise ValueError(f"Error reading JSON file {file_path}: {e}")
        if isinstance(payload, dict) and not any(
            isinstance(v, (list, dict)) for v in payload.values()
        ):
            return pd.DataFrame([payload])
        raise ValueError(f"Error reading JSON file {file_path}: unsupported JSON structure")
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

def read_txt(file_path: str, delimiter: str = None) -> pd.DataFrame:
    """
    Reads a delimited text file and returns a pandas DataFrame.

    The delimiter is sniffed when not given. The previous implementation chose
    between two branches that both read comma-separated data, so a tab- or
    semicolon-separated .txt came back as a single column with the delimiter
    embedded in the values.

    Parameters:
        file_path (str): The path to the text file.
        delimiter (str): Field separator. Sniffed from the file when omitted.

    Returns:
        pd.DataFrame: A DataFrame containing the data from the text file.
    """
    try:
        if delimiter is not None:
            return pd.read_csv(file_path, delimiter=delimiter)
        # sep=None asks the python engine to sniff the separator.
        return pd.read_csv(file_path, sep=None, engine="python")
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