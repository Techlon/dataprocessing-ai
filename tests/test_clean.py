import pytest
import pandas as pd
import numpy as np
from dataprocessing.clean import (
    drop_nulls, fix_types, remove_duplicates,
    remove_outliers, standardise_columns, clean_all,
)


@pytest.fixture
def sample_df():
    # Column B is exactly 50% null. Column C has a high-null share for the
    # drop-threshold test.
    return pd.DataFrame({
        "A": [1.0, 2.0, np.nan, 4.0],
        "B": [np.nan, 2.0, 3.0, np.nan],
        "C": ["foo", "bar", "baz", "qux"],
    })


def test_drop_nulls_keeps_50pct_column(sample_df):
    # B is 50% null; threshold is `> 0.5`, so 0.5 is NOT over the line ->
    # column B is kept, and rows containing any null are dropped afterwards.
    result = drop_nulls(sample_df.copy())
    assert "B" in result.columns
    # B is exactly 50% null -> kept (threshold is strictly > 0.5). Then every
    # row with ANY null is dropped: rows 0, 2, 3 go, leaving only row 1.
    assert len(result) == 1


def test_drop_nulls_drops_high_null_column():
    df = pd.DataFrame({
        "keep": [1, 2, 3, 4],
        "mostly_null": [1, np.nan, np.nan, np.nan],  # 75% null > 0.5
    })
    result = drop_nulls(df.copy())
    assert "mostly_null" not in result.columns
    assert "keep" in result.columns


def test_fix_types_handles_mixed_columns():
    # fix_types now uses pandas dtype checks, so a string column no longer
    # crashes the numeric guard. Numeric stays numeric; bool stays bool.
    df = pd.DataFrame({
        "A": [1.0, 2.0, 3.0],
        "flag": [True, False, True],
        "text": ["x", "y", "z"],
    })
    fixed = fix_types(df.copy())
    assert pd.api.types.is_numeric_dtype(fixed["A"])
    assert pd.api.types.is_bool_dtype(fixed["flag"])


def test_remove_duplicates(sample_df):
    dup = pd.concat([sample_df, sample_df.iloc[[0]]], ignore_index=True)
    cleaned = remove_duplicates(dup)
    # Original 4 rows + 1 duplicate, duplicate removed -> 4.
    assert len(cleaned) == 4


def test_remove_outliers_removes_extreme_value():
    df = pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0, 1000.0]})
    cleaned = remove_outliers(df.copy())
    assert 1000.0 not in cleaned["A"].values
    assert len(cleaned) == 4


def test_standardise_columns():
    df = pd.DataFrame({"First Name": [1], "Last Name": [2]})
    out = standardise_columns(df.copy())
    assert list(out.columns) == ["first_name", "last_name"]


def test_clean_all_runs_end_to_end():
    df = pd.DataFrame({
        "Num Col": [1.0, 2.0, 2.0, 1000.0],
        "Mostly Null": [1.0, np.nan, np.nan, np.nan],
    })
    cleaned = clean_all(df.copy())
    # High-null column dropped, columns standardised.
    assert "mostly_null" not in cleaned.columns
    assert all(c.islower() for c in cleaned.columns)
    assert isinstance(cleaned, pd.DataFrame)
