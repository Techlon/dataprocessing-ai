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

Install with the API extra, then start the server:
```bash
pip install "dataprocessing-ai[api]"
uvicorn dataprocessing.api:app --host 0.0.0.0 --port 8000
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

Install with the MCP extra:
```bash
pip install "dataprocessing-ai[mcp]"
```

Then add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "dataprocessing": {
      "command": "dataprocessing-mcp"
    }
  }
}
```

No paths, no `PYTHONPATH` — the installed package provides the
`dataprocessing-mcp` command directly.

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
pip install dataprocessing-ai
```

That gives you the core library (`ingest`, `clean`, `transform`, `analyse`,
`visualise`) with a minimal dependency footprint.

Optional extras add the interfaces and file formats you need:

```bash
pip install "dataprocessing-ai[mcp]"      # MCP server (for Claude and other agents)
pip install "dataprocessing-ai[api]"      # REST API server
pip install "dataprocessing-ai[formats]"  # Excel (.xlsx) and Parquet support
pip install "dataprocessing-ai[all]"      # everything
```

### Installing from source

```bash
git clone https://github.com/Techlon/dataprocessing-ai.git
cd dataprocessing-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | API status |
| POST | /ingest | Upload and read a data file |
| POST | /clean | Clean a dataset |
| POST | /transform | Transform a dataset |
| POST | /analyse | Analyse a dataset |
| POST | /merge | Join two datasets on a shared key |
| POST | /visualise | Produce a Vega-Lite chart spec from a dataset |

`/merge` takes `left` and `right` datasets rather than the single `data` payload
the other endpoints share, plus `on`, `how` (inner, left, right, outer, cross),
an optional `validate`, and `suffixes`. It returns `left_rows` and `right_rows`
alongside `rows` so an inflated join is visible in the response:

```bash
curl -X POST http://localhost:8000/merge -H "Content-Type: application/json" -d '{
  "left":  [{"id": 1, "name": "Ada"}],
  "right": [{"id": 1, "score": 10}],
  "on": "id", "how": "inner", "validate": "one_to_one"
}'
```

`/clean` accepts `drop_null_threshold` (float, default 0.5) and `remove_outliers`
(bool, default false, IQR method), and returns `rows_in` and `columns_in`
alongside `rows` and `columns` so you can see how much was removed. A bad column
name or malformed `params` returns 400; only genuine server faults return 500.

**Cleaning is lossier than it looks.** Dropping nulls removes every row
containing any null, so a dataset with 5% of its cells missing loses roughly a
quarter of its rows. Compare `rows` against `rows_in` before trusting a cleaned
result, and raise `drop_null_threshold` or clean column-by-column if the loss is
unacceptable.

## Behaviour worth knowing

**Nulls are excluded, not propagated.** Every statistic in `analyse` and every
chart in `visualise` is computed over the non-null values of a column. In
`summary_stats`, `count` is therefore the number of non-null values, and
`null_count` reports how many were left out.

**Cleaning does not convert text to dates.** `fix_types` will convert a column to
numeric or datetime only when at least 90% of its non-null values convert
cleanly. Anything else stays text.

That 90% is adjustable, because the right value depends on the data. Raise it
when a column might be *coincidentally* parseable — product codes like
`03-11-2024-A` can be 94% date-shaped, and converting them blanks the rest.
Lower it for a real date column carrying messy entries, where the default would
leave the whole column as text:

```python
from dataprocessing.clean import fix_types, clean_all

fix_types(df, threshold=1.0)              # only if every value converts
clean_all(df, type_threshold=0.7)         # same dial, from the top level
```

Values that fail an accepted conversion become null, so a lower threshold trades
data for usable types.

**Functions return new frames.** No function in `clean` or `transform` modifies
the DataFrame you pass it.

**Grouping keys are preserved over the wire.** `group_and_aggregate` and `pivot`
put keys in the index, per pandas. The REST API and MCP server reset that index
before serialising, so the keys appear as ordinary fields in the response. A
pivot over several value columns has nested column labels, which are flattened
to `value_category` (a pivot of `v1` over category `x` becomes `v1_x`).

**Operations that cannot do what you asked raise, rather than doing nothing.**
Renaming a column that does not exist, selecting one twice, or pivoting text
values with a numeric aggregation all raise `ValueError` naming the column. The
one exception you must opt into is join fan-out: `merge_dataframes` follows
pandas and lets a many-to-many match multiply rows, so pass
`validate="one_to_one"` (or `"many_to_one"`) when you expect it not to.

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

### Example response

A call with `{"chart": "histogram", "params": {"column": "age", "bins": 3}}`
returns a Vega-Lite spec like:

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "description": "Histogram of age",
  "data": {
    "values": [
      {"bin_start": 23.0, "bin_end": 29.33, "count": 4},
      {"bin_start": 29.33, "bin_end": 35.67, "count": 3},
      {"bin_start": 35.67, "bin_end": 42.0, "count": 1}
    ]
  },
  "mark": "bar",
  "encoding": {
    "x": {"field": "bin_start", "type": "quantitative"},
    "x2": {"field": "bin_end", "type": "quantitative"},
    "y": {"field": "count", "type": "quantitative"}
  }
}
```

Paste the returned spec into the [Vega-Lite editor](https://vega.github.io/editor/)
or render it with any Vega-Lite-compatible frontend.

## MCP Tools

The MCP server exposes each capability as a Claude-native tool:

| Tool | Arguments | Description |
|------|-----------|-------------|
| `ingest_file` | `file_path` | Read a data file (CSV, JSON, Excel, Parquet) from disk |
| `clean_data` | `data`, `drop_null_threshold`, `remove_dupes`, `standardise_cols` | Remove nulls, duplicates, and standardise column names |
| `transform_data` | `data`, `operation`, `params` | Apply a named transform (filter, select, rename, sort, group, pivot, add column) |
| `merge_data` | `left`, `right`, `on`, `how`, `validate`, `suffixes` | Join two datasets on a shared key |
| `analyse_data` | `data` | Full statistical report (summary, correlations, missing, outliers) |
| `visualise_data` | `data`, `chart`, `params` | Produce a Vega-Lite chart spec (see [Charts](#charts) for names and params) |

The `visualise_data` tool uses the same chart names and params as the `/visualise`
endpoint and returns a Vega-Lite spec dict.

## Supported formats

CSV, JSON, Excel (.xlsx), Parquet, and delimited text (.txt, delimiter sniffed).

## License
MIT
