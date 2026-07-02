# DataProcessing AI

An AI-native Python library for data processing and transformation.
Built to be called by any AI agent via REST API, MCP server, or direct Python import.

## What it does

- **Ingest** - read CSV, JSON, Excel, Parquet files into a standard format
- **Clean** - remove nulls, duplicates, outliers, standardise column names
- **Transform** - filter, sort, group, pivot, merge, reshape datasets
- **Analyse** - generate statistics, correlations, distributions, outlier reports
- **Visualise** - produce Vega-Lite chart specs (histogram, bar, scatter, line, correlation heatmap)

## Three ways to use it

### 1. REST API (any AI, any language)

Start the server:
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Call it:
```bash
curl -X POST http://localhost:8000/ingest -F "file=@data.csv"
curl -X POST http://localhost:8000/clean -H "Content-Type: application/json" -d '{"data": [...]}'
curl -X POST http://localhost:8000/transform -H "Content-Type: application/json" -d '{"data": [...], "operation": "filter_rows", "params": {"column": "age", "operator": "gt", "value": 25}}'
curl -X POST http://localhost:8000/analyse -H "Content-Type: application/json" -d '{"data": [...]}'
curl -X POST http://localhost:8000/visualise -H "Content-Type: application/json" -d '{"data": [...], "chart": "histogram", "params": {"column": "age", "bins": 10}}'
```

### 2. MCP Server (Claude native tools)

Add to your claude_desktop_config.json:
```json
{
  "mcpServers": {
    "dataprocessing": {
      "command": "python3",
      "args": ["/path/to/datalib/mcp_server.py"],
      "env": {"PYTHONPATH": "/path/to/datalib"}
    }
  }
}
```

### 3. Python package (direct import)

```python
from dataprocessing.ingest import read_file
from dataprocessing.clean import clean_all
from dataprocessing.transform import filter_rows
from dataprocessing.analyse import full_report
from dataprocessing.visualise import histogram, correlation_heatmap

df = read_file("data.csv")
df = clean_all(df)
report = full_report(df)

# Chart functions return Vega-Lite spec dicts (JSON-serialisable)
hist_spec = histogram(df, column="age", bins=10)
heatmap_spec = correlation_heatmap(df)
```

## Installation

```bash
git clone https://github.com/Techlon/dataprocessing-ai.git
cd dataprocessing-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | API status |
| POST | /ingest | Upload and read a data file |
| POST | /clean | Clean a dataset |
| POST | /transform | Transform a dataset |
| POST | /analyse | Analyse a dataset |
| POST | /visualise | Produce a Vega-Lite chart spec from a dataset |

## Charts

The `/visualise` endpoint (and the `visualise_data` MCP tool) accept a `chart`
name and a `params` object. Each returns a [Vega-Lite](https://vega.github.io/vega-lite/)
spec dict that any Vega-Lite renderer can display.

| Chart | Params | Notes |
|-------|--------|-------|
| `histogram` | `column` (numeric), `bins` (int, default 10) | Distribution of a numeric column |
| `bar_chart` | `column` (any) | Counts per category |
| `scatter` | `x` (numeric), `y` (numeric) | Relationship between two numeric columns |
| `line_chart` | `x` (any), `y` (numeric) | `x` may be a date or category; `y` must be numeric |
| `correlation_heatmap` | `columns` (list, optional) | Correlations across numeric columns; defaults to all numeric columns |

A bad chart name, a missing column, or a non-numeric column where a numeric one
is required returns HTTP 400 (or raises `ValueError` when called directly).

## MCP Tools

The MCP server exposes each capability as a Claude-native tool:
`ingest_file`, `clean_data`, `transform_data`, `analyse_data`, and
`visualise_data`. The `visualise_data` tool takes `data`, `chart`, and `params`
(the same chart names and params as the table above) and returns a Vega-Lite
spec dict.

## Supported formats
CSV, JSON, Excel (.xlsx), Parquet

## License
MIT
