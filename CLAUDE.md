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
- Current published version: 0.5.0. NOTE: 0.3.0 shipped with a false-alarm bug
  (group-by reported as row loss); it was tagged mid-stream, five commits behind.
- CI: `.github/workflows/ci.yml`. Release: tag `vX.Y.Z`, see `RELEASING.md`
- Supported: Python 3.10-3.13, pandas 2.2-3.x, mcp 1.x and 2.x (all in CI)

## Package layout

```
dataprocessing/
  ingest/       read CSV, JSON, Excel, Parquet, delimited .txt
  clean/        drop nulls, dedupe, fix types, standardise columns
  transform/    filter, sort, group, pivot, merge, add_column
  analyse/      summary stats, correlations, outliers, missing report
  visualise/    histogram, bar, scatter, line, correlation_heatmap (Vega-Lite specs)
  verify/       warnings: what an operation did that the caller may not expect
  _defaults.py  judgement values (null/type thresholds, IQR factor) + validators
  _serialise.py to_native + df_to_json, shared by BOTH interfaces (core deps only)
  api.py        FastAPI app (all five modules as endpoints)
  mcp_server.py MCP server (all five modules as tools)
tests/          pytest suite — 265 tests, must stay green
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
- **Pin test dependencies alongside runtime ones when testing a floor.** Left
  to float they resolve to newest, and newest-httpx against oldest-starlette is
  a combination nobody ships — the job then fails on a mixture it never meant to
  exercise rather than on the floor itself.
- **A dependency floor is an unverified claim.** pip installs the newest
  version that fits, never the oldest, so a wrong minimum is invisible until
  someone pins. Two of ours made `[all]` unsatisfiable at its own stated
  versions. Run `python scripts/check_dependency_floors.py` after touching any
  dependency; CI's `floor` job is the gate.
- **Put upper bounds on fast-moving SDK dependencies.** `mcp>=0.9.0` was an open
  invitation to a breaking major. The `[mcp]` extra is `>=1.2.0,<3.0.0`, and the
  `unbounded` CI job installs past those bounds weekly to find the next one.
- **`mcp_server.py` must import cleanly on mcp 1.x AND 2.x.** It picks
  `MCPServer` (2.x) or `FastMCP` (1.x) at import. `call_tool` returns THREE
  shapes across the supported range — `[TextContent]` on 1.2.0 (before
  structured output existed), `(content, {"result": ...})` on later 1.x, and a
  `CallToolResult` on 2.x. Tests go through the `tool_result` helper; never
  subscript the raw return. All three are in the CI matrix.
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
- **A helper with no call sites is a bug, not spare capacity.** `verify.type_changes`
  shipped in two releases unused, because the `fix_types` call it described was
  never wired into either interface. Grep for call sites before believing a
  feature is reachable.
- **A tag publishes whatever it points at, not whatever is on main.** `v0.3.0`
  was pushed while work was still landing, so PyPI got a build five commits
  behind that contained the group-by false alarm. Before tagging, check
  `git log --oneline vX.Y.Z..HEAD` is empty, and re-check what is actually on
  PyPI rather than repeating what you remember.
- **Mutation-test a claim before trusting it.** Reverting a fix and rerunning
  the suite is the only proof a regression test guards what it says. Doing this
  showed that removing `to_native` from the API and MCP handlers broke nothing,
  because `analyse` and `visualise` return native types themselves — the tests
  now pin that guarantee at the source instead.
- **`dropna()` is not a neutral default.** Dropping a row for a single null
  discards about a quarter of a frame with 5% of cells missing. `drop_nulls`
  governs rows and columns by the same "share exceeds threshold" rule; reach for
  `row_threshold=1.0` or a `subset` before accepting that loss.

## Dogfooding

Run a realistic messy dataset through the MCP tools before believing a feature
is done, and check for NOISE as well as signal — a warning that fires on healthy
data is worse than no warning, because it teaches the reader to skip all of them. The warnings layer passed 209 tests and was still wrong in ways only
visible from the output: a false alarm on every group-by, and a join between a
cleaned and an uncleaned frame with no way through. Tests check what you thought
to check; using the thing shows what you did not.

## Testing

```bash
pip install -e ".[dev]"    # install with all dev + runtime deps
pytest -q                  # expect: 265 passed
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

## The warnings idea (verify/)

The recurring defect in this library was never a crash — it was a confident,
plausible, wrong answer: cleaning that emptied text columns, outlier detection
that reported none, a rename that did nothing, a join that multiplied rows. An
agent calling these unattended has no other way to notice.

`verify/` is the smallest useful answer: operations report what they did that a
caller may not expect, in the response, in plain sentences. A warning must state
what happened, how much, and what to change — one missing the third cannot be
acted on. Warnings describe outcomes, not faults; removing 90% of rows may be
correct, and only the caller knows.

Two rules worth keeping: do not warn on everything (an agent that sees warnings
constantly stops reading them), and always warn on total loss. This is the
half of the stateful-session idea below that pays off without session state.

## Strategic direction

Read the trial result below before planning work. It refutes part of what this
section used to claim, and it should change what gets built next.

### What was measured (17 Aug 2026)

The same join task was put to Claude Desktop twice, against the same messy CSVs,
with every MCP call logged by a proxy so tool use was measured rather than
inferred from the prose. The two prompts differed by one clause.

| | Tool calls | Outcome |
|---|---|---|
| "Join X to Y and tell me…" | **0** | Wrote its own pandas. Correct, well-caveated answer. |
| "**Using the dataprocessing tools**, join X to Y…" | **3** | Used the tools, and quoted a warning back to the user. |

Two separate findings, with different answers:

**Warnings work.** In the second run the model reproduced the merge warning's
figures verbatim — "the tool flagged this: 103 rows returned from 122 on the
left" — attributed it to the tool, and built its reasoning about the 20 missing
customers on it. This was the open question behind everything in 0.3.0, and the
answer is yes: when the tools run, an agent reads the warnings and acts on them.

**But the tools are not reached for unprompted.** Given a shell and a Python
interpreter, the model used them instead. The bottleneck is invocation, not
comprehension.

### What that means for the pitch

The old claim here — that an agent writing raw pandas is unreliable and a library
of defined operations is safer — did not survive. Unprompted, the model's own
code was correct, and its answer was *better* than the library alone would have
given: it found a conflicting duplicate record, framed the count as a convention
decision, and flagged an unrelated sentinel value.

The claim that did survive is narrower: **when the tools are in the path, they
make an agent notice things it would otherwise have to think to check.** That is
demonstrated. It requires them to be in the path, which means the users who
benefit are the ones with no alternative — MCP clients without a sandbox, hosted
assistants with tool calling but no interpreter, pipelines where arbitrary code
execution is the thing being avoided. Smaller than "AI agents doing data work",
and honest.

### What to do with that

Do not build more warnings. The marginal warning is worth much less than getting
the tools invoked at all.

The stateful session module (per the 177k-MCP-tool study, reasoning/analytical
tooling is the smallest and slowest-growing category, with no incumbent) is still
the most interesting technical direction, and it inherits this finding exactly:
it will help when invoked and go unused by an agent that can write code. Settle
the positioning question before building it, or it is a larger version of the
same leverage problem.

The trial harness is kept outside the repo, at
`~/Projects/dataprocessing-trial-harness/` with data in
`~/Projects/dataprocessing-trial/`. Keep the protocol out of the data directory:
the first run was contaminated because the answer key sat beside the CSVs and the
model read it.

Treat monetisation as open. MIT-licensed and open-source-first is settled; a
hosted API is the eventual path, not a near-term one.

## Housekeeping

- `generate_from_brief.py` and `generate_tests.py` (the generation tooling) are
  gitignored — settled, they stay local. They drive an Ollama model that only
  exists on this machine, so they are noise in a public repo.
- `Claude/` (working notes, handoff docs) is gitignored for the same reason.
  `CLAUDE.md` itself IS tracked, at the repo root where it loads as context —
  it used to sit in `Claude/`, where it probably was not loading at all.
- `company-agents/` is a SEPARATE project, moved to `~/Projects/company-agents`.
  It is not part of this library. It's gitignored here in case of re-nesting.

## Style

Prose over bullets in generated docs. Minimal formatting. When explaining a
change, say what it does and why, not just what it is. Own mistakes plainly.
