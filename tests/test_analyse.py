import pytest
import pandas as pd
import numpy as np
from dataprocessing.analyse import (
    summary_stats, correlation_matrix, value_counts,
    missing_report, distribution, detect_outliers, full_report,
)


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "A": [1.0, 2.0, 3.0, 4.0, 5.0],
        "B": [5.0, 4.0, 3.0, 2.0, 1.0],
        "C": [10.0, np.nan, 30.0, np.nan, 50.0],
        "D": ["a", "b", "c", "d", "e"],
    })


def test_summary_stats(sample_df):
    stats = summary_stats(sample_df, columns=["A", "B"])
    assert set(stats.keys()) == {"A", "B"}
    for col in ["A", "B"]:
        s = stats[col]
        assert {"count", "mean", "median", "std", "min", "max", "quartiles"} <= set(s)
        # quartiles is a dict keyed by '25%' / '75%'
        assert set(s["quartiles"].keys()) == {"25%", "75%"}


def test_summary_stats_default_numeric_only(sample_df):
    stats = summary_stats(sample_df)
    # D is non-numeric and should be excluded by the default selection.
    assert "D" not in stats


def test_correlation_matrix(sample_df):
    corr = correlation_matrix(sample_df, columns=["A", "B"])
    # Nested dict keyed by column name, not positional index.
    assert np.isclose(corr["A"]["A"], 1.0)
    assert np.isclose(corr["A"]["B"], -1.0)


def test_value_counts(sample_df):
    counts = value_counts(sample_df, "A")
    assert len(counts) == 5
    assert all(counts[v] == 1 for v in [1.0, 2.0, 3.0, 4.0, 5.0])


def test_value_counts_non_numeric_raises(sample_df):
    with pytest.raises(ValueError):
        value_counts(sample_df, "D")


def test_missing_report(sample_df):
    report = missing_report(sample_df)
    assert report["C"]["missing_count"] == 2
    assert np.isclose(report["C"]["percentage"], 40.0)
    assert report["A"]["missing_count"] == 0


def test_distribution(sample_df):
    dist = distribution(sample_df, "A", bins=3)
    assert set(dist.keys()) == {"bin_edges", "counts"}
    assert np.isclose(dist["bin_edges"][0], 1)
    assert np.isclose(dist["bin_edges"][-1], 5)
    assert sum(dist["counts"]) == 5


def test_distribution_non_numeric_raises(sample_df):
    with pytest.raises(ValueError):
        distribution(sample_df, "D")


def test_detect_outliers_none_present(sample_df):
    # A and B are evenly spread -> no IQR outliers.
    outliers = detect_outliers(sample_df, columns=["A", "B"])
    assert outliers["A"] == []
    assert outliers["B"] == []


def test_detect_outliers_with_extreme():
    df = pd.DataFrame({"X": [1.0, 2.0, 3.0, 4.0, 1000.0]})
    outliers = detect_outliers(df, columns=["X"])
    # index 4 (value 1000) is the outlier
    assert 4 in outliers["X"]


def test_full_report(sample_df):
    report = full_report(sample_df)
    assert set(report.keys()) == {
        "summary_stats", "correlation_matrix", "missing_values", "outliers",
    }
