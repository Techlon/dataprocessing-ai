import io
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_ingest_csv():
    csv_bytes = b"col1,col2\nval1,val2\nval3,val4"
    response = client.post(
        "/ingest", files={"file": ("test.csv", csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert data["rows"] == 2
    assert data["columns"] == ["col1", "col2"]


def test_ingest_unsupported_extension():
    # The endpoint raises HTTPException(400) for unknown extensions, which
    # FastAPI returns as a 400 response (not a raised exception client-side).
    response = client.post(
        "/ingest", files={"file": ("test.weird", b"whatever", "application/octet-stream")}
    )
    assert response.status_code == 400


def test_clean_drops_null_row():
    payload = {
        "data": [
            {"col1": "val1", "col2": None},
            {"col1": "val3", "col2": "val4"},
        ]
    }
    response = client.post("/clean", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    # col2 is 50% null -> column kept (threshold is > 0.5), null row dropped.
    assert data["rows"] == 1


def test_transform_filter_rows():
    payload = {
        "data": [
            {"col1": "val1", "col2": "x"},
            {"col1": "val3", "col2": "y"},
        ],
        "operation": "filter_rows",
        "params": {"column": "col1", "operator": "eq", "value": "val1"},
    }
    response = client.post("/transform", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["rows"] == 1


def test_transform_unknown_operation():
    payload = {
        "data": [{"col1": "val1"}],
        "operation": "not_a_real_op",
        "params": {},
    }
    response = client.post("/transform", json=payload)
    assert response.status_code == 400

def test_analyse_returns_report():
    # full_report output is now passed through to_native(), so numpy types are
    # serialised and a mixed numeric/string payload returns valid JSON.
    payload = {
        "data": [
            {"num": 1, "label": "a"},
            {"num": 2, "label": "b"},
            {"num": 3, "label": "c"},
        ]
    }
    response = client.post("/analyse", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "summary_stats" in data

def test_visualise_histogram():
    payload = {"data": [{"col1": 1}, {"col1": 2}, {"col1": 3}], "chart": "histogram", "params": {"column": "col1"}}
    response = client.post("/visualise", json=payload)
    assert response.status_code == 200
    vega_lite_spec = response.json()
    assert "mark" in vega_lite_spec
    assert "data" in vega_lite_spec
    data = vega_lite_spec["data"]
    assert "values" in data
    assert isinstance(data["values"], list)

def test_visualise_bar_chart():
    payload = {"data": [{"col1": "val1"}, {"col1": "val2"}, {"col1": "val3"}], "chart": "bar_chart", "params": {"column": "col1"}}
    response = client.post("/visualise", json=payload)
    assert response.status_code == 200
    vega_lite_spec = response.json()
    assert "mark" in vega_lite_spec
    assert "data" in vega_lite_spec
    data = vega_lite_spec["data"]
    assert "values" in data
    assert isinstance(data["values"], list)

def test_visualise_scatter():
    payload = {"data": [{"col1": 1, "col2": 2}, {"col1": 3, "col2": 4}], "chart": "scatter", "params": {"x": "col1", "y": "col2"}}
    response = client.post("/visualise", json=payload)
    assert response.status_code == 200
    vega_lite_spec = response.json()
    assert "mark" in vega_lite_spec
    assert "data" in vega_lite_spec
    data = vega_lite_spec["data"]
    assert "values" in data
    assert isinstance(data["values"], list)

def test_visualise_correlation_heatmap():
    payload = {"data": [{"col1": 1, "col2": 2}, {"col1": 3, "col2": 4}], "chart": "correlation_heatmap", "params": {"columns": ["col1", "col2"]}}
    response = client.post("/visualise", json=payload)
    assert response.status_code == 200
    vega_lite_spec = response.json()
    assert "mark" in vega_lite_spec
    assert "data" in vega_lite_spec
    data = vega_lite_spec["data"]
    assert "values" in data
    assert isinstance(data["values"], list)
    assert len(data["values"]) > 0

def test_visualise_unknown_chart():
    payload = {"data": [{"col1": 1}, {"col1": 2}], "chart": "piechart", "params": {}}
    response = client.post("/visualise", json=payload)
    assert response.status_code == 400

def test_visualise_bad_column():
    payload = {"data": [{"col1": "val1"}, {"col1": "val2"}], "chart": "histogram", "params": {"column": "col1"}}
    response = client.post("/visualise", json=payload)
    assert response.status_code == 400