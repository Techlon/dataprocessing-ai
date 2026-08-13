# CLAUDE.md

Project context for Claude Code. Read this at the start of every session.

## What this project is

`dataprocessing-ai` — a published Python library (live on PyPI) that cleans,
reshapes, and analyses tabular data, exposed through three interfaces:

- **Python import** — `from dataprocessing.clean import clean_all`
- **REST API** — FastAPI app at `dataprocessing/api.py`, run via `uvicorn dataprocessing.api:app`
- **MCP server** — `dataprocessing/mcp_server.py`, exposed as the `dataprocessing-mcp` command

The differentiator is being MCP-first and agent-callable. The distribution
channel that matters is the MCP ecosystem, not PyPI search — do not optimise for
competing head-on with pandas.

- GitHub: `Techlon/dataprocessing-ai`
- Package name (PyPI): `dataprocessing-ai`
- Import name (Python): `dataprocessing`  (these intentionally differ)
- Current published version: 0.1.1 (0.2.0 prepared, see CHANGELOG.md)

## Package layout

```
dataprocessing/
  ingest/       read CSV, JSON, Excel, Parquet, delimited .txt
  clean/        drop nulls, dedupe, fix types, standardise columns
  transform/    filter, sort, group, pivot, merge, add_column
  analyse/      summary stats, correlations, outliers, missing report
  visualise/    histogram, bar, scatter, line, correlation_heatmap (Vega-Lite specs)
  _defaults.py  judgement values (null/type thresholds, IQR factor) + validators
  _serialise.py to_native + df_to_json, shared by BOTH interfaces (core deps only)
  api.py        FastAPI app (all five modules as endpoints)
  mcp_server.py MCP server (all five modules as tools)
tests/          pytest suite — 163 tests, must stay green
pyproject.toml  package config; dependencies split into extras
```

Each module's code lives in its `__init__.py` (e.g. `dataprocessing/clean/__init__.py`).

## The development workflow (important — do not drift from this)

This project uses a deliberate division of labour:

1. A local LLM (`deepseek-coder-v2`, via Ollama) **generates** code from written
   specifications ("briefs").
2. Claude (you) **assesses and verifies** by reproducing and running the code —
   you do NOT write the implementation directly.

When adding a feature: write a precise brief describing the target (signatures,
return shapes, error behaviour, conventions), have the local model generate from
it, then review by running. Reading generated code is not enough — run it.

For small, surgical corrections to already-generated code, direct edits are fine.
For new modules or substantial code, route generation through the local model.

If working without access to the local model, prefer writing briefs the user can
run, and keep the review/verification role.

## Hard rules learned the hard way

- **Never regenerate a whole file to add one feature.** The local model drops
  unrelated parts of the file when asked to rewrite it wholesale. Ask for only
  the new snippet and integrate it, or generate to a scratch file and diff
  against the real one before applying.
- **Strip markdown fences** from any generated output before saving — the model
  wraps code in ```python fences that break the file.
- **Watch for hallucinated imports.** The model has invented non-existent
  dependencies (e.g. `from vega_datasets import data`). Check imports specifically.
- **Use `pd.api.types.is_numeric_dtype(col)`**, never `np.issubdtype(col.dtype, np.number)`.
  The latter crashes on string columns under pandas 3.x.
- **Return JSON-safe types from API/MCP.** NumPy scalars (`int64`, `float64`)
  aren't JSON-serialisable. `to_native()` in `dataprocessing/_serialise.py`
  handles this (it used to live in `api.py`, which is why the MCP server missed
  it); use it for anything returning computed numbers, on either interface.
- **Never use `eval()` on user/network input.** `add_column` uses `df.eval()`
  (pandas' sandboxed evaluator), not the builtin. Keep it that way.
- **Multi-line git commit messages** trigger zsh's `dquote>` prompt on this
  setup. If it hangs, a single-line message is the reliable fallback.
- **A fix applied to `api.py` is not applied to `mcp_server.py`.** The two
  interfaces were written separately and drifted: `to_native` lived only in
  `api.py`, so the MCP `analyse_data` tool failed for every input from 0.1.0
  until 0.1.2, and `pivot` was exposed by one interface and not the other.
  Shared logic now lives in `dataprocessing/_serialise.py`. When changing one
  interface, check the other.
- **Never use `np.percentile` on a raw column.** It returns NaN if a single null
  is present, and NaN bounds make every comparison False — so `detect_outliers`
  silently reported "no outliers" rather than erroring. Use pandas' `.quantile()`
  on a `.dropna()`'d series, which skips nulls by design.
- **Never `pd.to_datetime(errors="coerce")` a column speculatively.** Every
  value that fails becomes NaT, so a column of names converts to all-null and
  the data is gone with no error. Guard any speculative parse by requiring most
  non-null values to survive it.
- **`orient="records"` discards the index.** Anything that puts information in
  the index (`groupby`, `pivot_table`) loses it crossing a JSON boundary. Use
  `_serialise.df_to_json`, which resets a meaningful index first.
- **Prefer returning new frames to `inplace=True`.** The clean module mutated
  its caller's DataFrame, which is a bad property for a library an agent calls
  repeatedly over one dataset.
- **Verify a built wheel from OUTSIDE the repo directory.** Running the smoke
  test with the repo as cwd imports the local `dataprocessing/` source, not the
  installed package, so it proves nothing about the wheel. `cd` elsewhere first
  and print `dataprocessing.__file__` to confirm which copy is loaded.
- **The repo venv hides dependency breakage.** `.venv` holds versions resolved
  months ago; a new user resolves today's. This is exactly how the `mcp 2.0`
  break went unnoticed — tests passed on the pinned 1.27.2 while a fresh
  `pip install "dataprocessing-ai[mcp]"` could not import the server at all.
  Any release check must install into a clean venv, unpinned.
- **Put upper bounds on fast-moving SDK dependencies.** `mcp>=0.9.0` was an open
  invitation to a breaking major. The `[mcp]` extra is now `>=1.2.0,<2.0.0`.
- **A silent no-op is a defect, not lenience.** `rename_columns` ignored names
  that did not exist, so a caller was told the operation succeeded while nothing
  changed — the worst outcome for an agent, which has no other way to check.
  Prefer raising over quietly doing nothing.
- **Validate at the operation, not at the serialisation boundary.** Duplicate
  columns from a rename or a repeated select only failed later inside
  `to_json`, with an error naming neither the operation nor the column that
  caused it. Reject the bad input where it enters.
- **Joins fail by multiplying, not by erroring.** An unintended many-to-many
  match inflates row counts silently. `merge_dataframes` exposes pandas'
  `validate` for this; use it whenever the cardinality is known.
- **A judgement value belongs in `_defaults.py`, defined once.** Thresholds and
  the IQR factor are policy, not fact, so they are parameters with documented
  defaults rather than literals in the body. The IQR multiplier had been written
  into two modules that could drift into disagreeing about what an outlier is.
- **Validate a share as a share.** Passing `50` for "50%" was silently accepted
  and did nothing, because no column is 5000% null. `check_share` rejects it.

## Testing

```bash
pip install -e ".[dev]"    # install with all dev + runtime deps
pytest -q                  # expect: 163 passed
```

One harmless warning is expected (a Starlette/httpx deprecation). Do not "fix"
it by suppressing real signal. The pandas date-parse warning that used to appear
is gone: `fix_types` no longer parses text columns speculatively, which is what
produced it.

The suite has caught real bugs before — a string-dtype crash, the /analyse
serialization failure, and an eval() RCE. Treat a failing test as a real finding,
not noise. Never weaken an assertion to make it pass; fix the code or, if the
test's expectation is genuinely wrong, correct the expectation and say why.

## Release checklist

```bash
# 1. Bump version in pyproject.toml, then VERIFY it took:
grep '^version' pyproject.toml
# 2. Clean rebuild (stale dist/ artifacts cause wrong-version uploads):
rm -rf dist/ build/
python -m build
twine check dist/*
# 3. Rehearse on TestPyPI first (PyPI uploads are permanent, never reusable):
twine upload --repository testpypi dist/*
#    Verify in a clean venv with --no-deps (TestPyPI has a fake "fastapi"):
#    pip install pandas numpy fastapi uvicorn pydantic python-multipart mcp openpyxl pyarrow
#    pip install --index-url https://test.pypi.org/simple/ --no-deps "dataprocessing-ai==X.Y.Z"
# 4. Publish for real:
twine upload dist/*
# 5. Verify the live release with no flags, in a clean venv, from OUTSIDE the
#    repo (inside it, cwd shadows the install and you test local source):
#    pip install "dataprocessing-ai[all]"
#    cd /tmp && python -c "import dataprocessing; print(dataprocessing.__file__)"
#    cd /tmp && python -c "from dataprocessing import mcp_server"   # import is the test
# 6. Tag:
git tag vX.Y.Z && git push --tags
```

Note: PyPI and TestPyPI are separate accounts with separate tokens; a token from
one 403s on the other. Tokens live in `~/.pypirc` (never commit it).

## Dependencies (extras)

Core is deliberately lean (pandas, numpy only). Everything else is optional:

- `[api]` — fastapi, uvicorn, pydantic, python-multipart
- `[mcp]` — mcp
- `[formats]` — openpyxl, pyarrow
- `[all]` — all of the above
- `[dev]` — all + pytest, httpx, pytest-asyncio

Keep the core lean. Don't add runtime dependencies to the core that only one
interface needs.

## Strategic direction

The interesting gap in the ecosystem (per a 177k-MCP-tool study) is **reasoning/
analytical tooling** — the smallest, slowest-growing category, with no natural
incumbent. The strongest next direction is stateful multi-step analysis with
verification (a session that holds data across operations and flags when a step
did something suspicious). This attacks a documented agent failure mode and is a
natural extension of the existing modules.

Treat monetisation as open. MIT-licensed and open-source-first is settled; a
hosted API is the eventual path, not a near-term one.

## Housekeeping / open decisions

- `generate_from_brief.py` and `generate_tests.py` (the generation tooling) are
  untracked by deliberate choice — decide whether they belong in the repo.
- `company-agents/` is a SEPARATE project, moved to `~/Projects/company-agents`.
  It is not part of this library. It's gitignored here in case of re-nesting.

## Style

Prose over bullets in generated docs. Minimal formatting. When explaining a
change, say what it does and why, not just what it is. Own mistakes plainly.
