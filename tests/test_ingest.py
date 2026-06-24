import pytest
import pandas as pd
from dataprocessing.ingest import (
    read_csv, read_json, read_excel, read_parquet, read_txt, read_file,
)


def test_read_csv(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("a,b\n1,2\n3,4")
    df = read_csv(str(file_path))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ["a", "b"]


def test_read_json(tmp_path):
    file_path = tmp_path / "sample.json"
    file_path.write_text('[{"a": 1, "b": 2}, {"a": 3, "b": 4}]')
    df = read_json(str(file_path))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


def test_read_excel(tmp_path):
    df = pd.DataFrame([[1, 2], [3, 4]], columns=["a", "b"])
    file_path = tmp_path / "sample.xlsx"
    df.to_excel(file_path, index=False)
    out = read_excel(str(file_path))
    assert isinstance(out, pd.DataFrame)
    assert len(out) == 2


def test_read_parquet(tmp_path):
    df = pd.DataFrame([[1, 2], [3, 4]], columns=["a", "b"])
    file_path = tmp_path / "sample.parquet"
    df.to_parquet(file_path)
    out = read_parquet(str(file_path))
    assert isinstance(out, pd.DataFrame)
    assert len(out) == 2


def test_read_txt(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("a,b\n1,2\n3,4")
    df = read_txt(str(file_path))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


def test_read_file_dispatches_csv(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("a,b\n1,2\n3,4")
    df = read_file(str(file_path))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


def test_read_file_unsupported_extension():
    # An unsupported extension hits the explicit `else: raise ValueError` branch.
    with pytest.raises(ValueError):
        read_file("nonexistent.unsupported")


def test_read_csv_bad_path_raises():
    with pytest.raises(ValueError):
        read_csv("definitely_not_a_real_file.csv")
