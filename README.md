# DataProcessing AI

An AI-native Python library for data processing and transformation.
Built to be called by any AI agent via REST API, MCP server, or direct Python import.

## What it does

- **Ingest** - read CSV, JSON, Excel, Parquet files into a standard format
- **Clean** - remove nulls, duplicates, outliers, standardise column names
- **Transform** - filter, sort, group, pivot, merge, reshape datasets
- **Analyse** - generate statistics, correlations, distributions, outlier reports

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

df = read_file("data.csv")
df = clean_all(df)
report = full_report(df)
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

## Supported formats
CSV, JSON, Excel (.xlsx), Parquet

## License
MIT
