import json
import pandas as pd
import pytest
from dataprocessing.visualise import histogram, bar_chart, scatter, line_chart, correlation_heatmap

# Sample DataFrame for testing
@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'A': [1, 2, 3, 4, 5],
        'B': [5, 4, 3, 2, 1],
        'C': ['a', 'b', 'c', 'd', 'e']
    })

def test_histogram(sample_df):
    spec = histogram(sample_df, 'A')
    assert isinstance(spec, dict)
    assert "mark" in spec
    assert "data" in spec
    assert len(spec["data"]["values"]) > 0
    assert all("bin_start" in row and "bin_end" in row and "count" in row for row in spec["data"]["values"])
    try:
        json.dumps(spec)
    except TypeError:
        pytest.fail("Spec is not JSON serializable")

def test_histogram_invalid_column(sample_df):
    with pytest.raises(ValueError):
        histogram(sample_df, 'C')

def test_bar_chart(sample_df):
    spec = bar_chart(sample_df, 'C')
    assert isinstance(spec, dict)
    assert "mark" in spec
    assert "data" in spec
    assert len(spec["data"]["values"]) > 0
    assert all("category" in row and "count" in row for row in spec["data"]["values"])
    try:
        json.dumps(spec)
    except TypeError:
        pytest.fail("Spec is not JSON serializable")

def test_bar_chart_missing_column(sample_df):
    # bar_chart works on any existing column (numeric or categorical); only a
    # column that doesn't exist should raise.
    with pytest.raises(ValueError):
        bar_chart(sample_df, "does_not_exist")

def test_scatter(sample_df):
    spec = scatter(sample_df, 'A', 'B')
    assert isinstance(spec, dict)
    assert "mark" in spec
    assert "data" in spec
    assert len(spec["data"]["values"]) > 0
    assert all("x" in row and "y" in row for row in spec["data"]["values"])
    try:
        json.dumps(spec)
    except TypeError:
        pytest.fail("Spec is not JSON serializable")

def test_scatter_invalid_columns(sample_df):
    with pytest.raises(ValueError):
        scatter(sample_df, 'A', 'C')

def test_line_chart(sample_df):
    spec = line_chart(sample_df, 'A', 'B')
    assert isinstance(spec, dict)
    assert "mark" in spec
    assert "data" in spec
    assert len(spec["data"]["values"]) > 0
    assert all("x" in row and "y" in row for row in spec["data"]["values"])
    try:
        json.dumps(spec)
    except TypeError:
        pytest.fail("Spec is not JSON serializable")

def test_line_chart_non_numeric_y(sample_df):
    # y must be numeric; column C is strings -> should raise.
    with pytest.raises(ValueError):
        line_chart(sample_df, 'A', 'C')


def test_line_chart_non_numeric_x():
    # x may be categorical/date; only y must be numeric.
    df = pd.DataFrame({"month": ["Jan", "Feb", "Mar"], "sales": [100.0, 150.0, 120.0]})
    spec = line_chart(df, "month", "sales")
    assert spec["encoding"]["x"]["type"] == "nominal"
    assert spec["data"]["values"][0] == {"x": "Jan", "y": 100.0}
    json.dumps(spec)

def test_correlation_heatmap(sample_df):
    spec = correlation_heatmap(sample_df)
    assert isinstance(spec, dict)
    assert "mark" in spec
    assert "data" in spec
    assert len(spec["data"]["values"]) > 0
    assert all("x" in row and "y" in row and "correlation" in row for row in spec["data"]["values"])
    try:
        json.dumps(spec)
    except TypeError:
        pytest.fail("Spec is not JSON serializable")

def test_correlation_heatmap_invalid_columns(sample_df):
    with pytest.raises(ValueError):
        correlation_heatmap(sample_df, columns=['A', 'C'])
