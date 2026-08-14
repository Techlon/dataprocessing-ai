# Changelog

## 0.2.0

A correctness pass over every module, plus the two interfaces. Most of this
release fixes behaviour that was wrong; several of those failures were silent,
returning a confident answer that happened to be false, which is the worst
failure mode for a tool an agent calls unsupervised. It is a minor rather than a
patch release because it also adds a merge endpoint and tool, and because the
volume of corrected behaviour is substantive.

### Release engineering

- **CI runs the suite across Python 3.10–3.13, both mcp majors, and the oldest
  supported dependency set.** There was no CI at all, which is why a broken
  `pip install "dataprocessing-ai[mcp]"` went unnoticed: the repo's virtualenv
  held versions resolved months earlier, so the tests passed while a new user's
  install could not import the server. A weekly scheduled job installs with the
  upper bounds stripped, so the next breaking major surfaces there rather than
  in someone's project.
- **The MCP server supports mcp 1.x and 2.x.** `mcp` 2.0 renamed `FastMCP` to
  `MCPServer` and moved it, but left the decorator, `run()` and `call_tool()`
  surfaces unchanged, so `mcp_server.py` imports whichever is installed. The
  extra is now `mcp>=1.2.0,<3.0.0` and the full suite is run against 1.27.2 and
  2.0.0 in CI. `call_tool` does differ in what it returns — a tuple in 1.x, a
  `CallToolResult` in 2.x — which the tests normalise.
- **`requires-python` is `>=3.10`, corrected from `>=3.9`.** `mcp`, `fastapi`
  and `uvicorn` all require 3.10, so a 3.9 user could install the bare core but
  none of the three interfaces this library exists to provide. The old claim was
  both misleading and untestable.
- **Publishing runs from GitHub Actions via PyPI Trusted Publishing**, so no API
  token exists to store or leak, and the workflow refuses to publish when the
  git tag and the packaged version disagree. See `RELEASING.md`.
- **The version is single-sourced.** It was written in both `pyproject.toml` and
  `api.py`, and `/health` consequently reported `0.1.0` for the whole of 0.1.1.
  `dataprocessing.__version__` now reads the installed package metadata, and a
  test asserts the two agree.
- **The declared minimum dependency set is now actually installable.** The
  `[api]` extra declared `pydantic>=2.6.0` while `mcp>=1.2.0` requires
  `pydantic>=2.10.1`, so `pip install "dataprocessing-ai[all]"` resolved to
  nothing at the versions the package itself claimed to support. Nobody hit it
  because pip picks the newest version, not the oldest — CI's floor job found it
  on its first run, and a second conflict (`mcp` needs `uvicorn>=0.30`, the
  extra said `>=0.27.0`) on its second. Both floors are raised, and
  `scripts/check_dependency_floors.py` answers the question locally rather than
  one CI round-trip per conflict.
- **Runtime dependencies have upper bounds.** `pandas>=2.2.0,<4.0.0` and
  `numpy>=1.26.0,<3.0.0`, for the reason the `mcp` pin exists: an unbounded
  requirement lets a breaking major in silently. The suite is run against both
  ends — pandas 2.2.0/numpy 1.26.4 and pandas 3.0.x/numpy 2.x — so the declared
  floor is verified rather than assumed.
- PyPI classifiers now describe the project (status, audience, topic, supported
  Python versions).

### Fixed — data loss

- **`fix_types` no longer destroys text columns.** It ran
  `pd.to_datetime(errors="coerce")` over every object column, so a column of
  names or cities became entirely `NaT`. A conversion is now accepted only if at
  least 90% of the non-null values survive it; genuine dates and numeric strings
  still convert. Because `clean_all` calls `fix_types`, cleaning any dataset with
  text in it silently emptied those columns.
- **Grouping keys survive the JSON boundary.** `group_and_aggregate` and `pivot`
  put their keys in the DataFrame index, and `orient="records"` discards the
  index, so the REST API and MCP server returned rows with no way to tell which
  group each belonged to. Both interfaces now reset a meaningful index first.

### Fixed — silently wrong results

- **Nulls no longer poison every statistic.** `summary_stats`, `detect_outliers`
  and `distribution` used `np.percentile`, which returns `NaN` if the column
  holds a single null. `detect_outliers` was the worst case: `NaN` bounds made
  every comparison false, so it reported *no outliers* for columns that had them.
  All three now compute over non-null values.
- **`summary_stats` counts honestly.** `count` was the row count including
  nulls; it is now the non-null count, with the excluded total reported
  separately as `null_count`.

### Fixed — outright failures

- **The MCP `analyse_data` tool works.** It returned raw numpy `int64`/`float64`
  and failed for every input with "Unable to serialize unknown type". The
  `to_native` converter that `api.py` had was never applied to `mcp_server.py`;
  both now share one implementation in `dataprocessing/_serialise.py`.
- **`pip install "dataprocessing-ai[mcp]"` produces a working MCP server again.**
  The extra declared `mcp>=0.9.0` with no upper bound. `mcp` 2.0.0 removed
  `mcp.server.fastmcp` (FastMCP became MCPServer), so any install done after
  that release resolved to 2.x and `mcp_server.py` failed at import — breaking
  the project's flagship interface for new users of 0.1.1. The extra is now
  `mcp>=1.2.0,<3.0.0` and the server imports whichever class the installed major
  provides, so 1.x and 2.x both work.
- **`histogram` and `distribution` no longer crash on nulls** with "autodetected
  range of [nan, nan] is not finite".
- **`standardise_columns` no longer crashes on non-string column names**, which
  a pivot produces. It also strips surrounding whitespace now, as the README
  always claimed it did.
- **`line_chart` no longer emits `NaN`** into its Vega-Lite spec, which is not
  valid JSON. Rows with a null in either axis are dropped, as `scatter` already
  did.

### Fixed — operations that reported success while doing nothing

- **`rename_columns` no longer ignores names that do not exist.** Renaming a
  column that was not there returned the frame unchanged with no error, so a
  caller was told the rename succeeded while nothing happened. It now raises,
  and also refuses a rename that would collide with an existing column — that
  previously produced duplicate columns which failed much later, at the JSON
  boundary, with an error pointing nowhere near the cause.
- **`merge_dataframes` can now catch an unintended fan-out.** A many-to-many
  match multiplies rows rather than erroring, so a join of two 2-row frames
  quietly returns 4 rows. The pandas `validate` argument is now exposed
  (`"one_to_one"`, `"many_to_one"`, …), which turns that into an error. The
  default is unchanged, so existing joins behave as before.
- **`merge_dataframes` names which side is missing the join key.** It raised a
  bare `KeyError: 'id'` that did not say whether the left or right frame lacked
  it. It also validates `how` and supports `how="cross"`.
- **`pivot` with a list of values no longer produces unusable JSON keys.** The
  nested column labels were stringified into keys like `"('v1', 'x')"`. They
  are now flattened to `v1_x`.
- **`pivot` explains the aggfunc mismatch.** Pivoting text values under the
  default `aggfunc="mean"` failed with "dtype 'str' does not support operation
  'mean'", naming neither the column nor the fix; it now names both.
- **`select_columns` rejects a repeated column name**, which otherwise produced
  duplicate columns that failed later during serialisation.
- **`group_and_aggregate` validates its columns and function names.** A missing
  column was a `KeyError`; an unknown function was an `AttributeError` naming
  `SeriesGroupBy`, which reads as an internal fault rather than a caller error.

### Fixed — ingest

- **`read_txt` honours the delimiter.** Both branches of its conditional read
  comma-separated data, so a tab- or semicolon-separated `.txt` came back as a
  single column with the delimiter embedded in the values. The separator is now
  sniffed, and can be passed explicitly.
- **`read_json` accepts a single JSON object.** A file holding
  `{"a": 1, "b": 2}` — an ordinary one-row export — failed with "If using all
  scalar values, you must pass an index". It is read as one row.
- **`/ingest` accepts `.txt`**, which `read_file` and the MCP `ingest_file` tool
  have always supported; the two interfaces disagreed about a supported format.
- **`/ingest` handles a filename with no extension.** It used the whole filename
  as the extension, producing "Unsupported file type: myexport". The error now
  lists what is supported.

### Changed

- **Cleaning reports how much it removed.** `/clean` and the MCP `clean_data`
  tool now return `rows_in` and `columns_in` alongside `rows` and `columns`.
  Cleaning drops every row containing any null, so a dataset with 5% of cells
  missing loses roughly a quarter of its rows — a large, silent reduction the
  caller previously had no way to notice from the response alone.
- **The type-conversion threshold is adjustable.** The guard that stops
  `fix_types` blanking a text column accepts a conversion only when 90% of a
  column's non-null values survive it. That 90% is a judgement, not a fact —
  a coincidentally date-shaped column wants a stricter value, a genuine date
  column full of `"N/A"` wants a looser one — but it sat on a private helper
  that `fix_types` called without passing anything through, so it could not be
  changed without reaching into internals. It is now a parameter on `fix_types`
  and on `clean_all` (as `type_threshold`), exported as
  `DEFAULT_TYPE_THRESHOLD`, and validated: a value outside 0–1 raises rather
  than silently doing nothing, since passing `90` for 90% is the obvious slip.
- **`drop_nulls` no longer forces the all-or-nothing row policy.** It did two
  things with two very different levels of control: dropping mostly-null
  *columns* was governed by a threshold, while dropping *rows* was a bare
  `dropna()` — any single null anywhere discarded the whole row, with no way to
  change it. That is the lossiest behaviour in the library: on a frame with 5%
  of its cells missing at random it throws away about a quarter of the rows,
  because a row only has to be unlucky once. Both steps now work the same way,
  dropping when the null share *exceeds* a threshold: `row_threshold=0.0` is the
  previous behaviour and remains the default, `0.5` keeps merely patchy rows,
  and `1.0` keeps every row and drops only dead columns. A `subset` argument
  judges rows on named columns alone, so a row survives a null in a column that
  does not matter. Exposed as `row_null_threshold` on `clean_all`, `/clean` and
  the MCP `clean_data` tool.
- **The outlier fence is adjustable, and defined once.** The `1.5 × IQR`
  multiplier was written into both `clean.remove_outliers` and
  `analyse.detect_outliers`, so the two could drift apart and disagree about
  what an outlier is — the same duplication that let `/health` report the wrong
  version. It is now `DEFAULT_IQR_FACTOR` in `dataprocessing/_defaults.py`,
  shared by both, and a `factor` argument on each. `clean_all` passes it through
  as `outlier_factor`, and `/clean` and the MCP `clean_data` tool accept it too.
  A non-positive factor raises.
- **`clean_all` also exposes `null_threshold`**, which was previously fixed at
  0.5 for anyone using the pipeline rather than calling `drop_nulls` directly.
  `drop_nulls` now validates it: a threshold of `50`, meaning 50%, silently kept
  every column, because no column can be 5000% null.
- **`clean_all` takes `remove_outlier_rows`** (default `True`, unchanged).
  Dropping outliers is a judgement rather than a repair — the extreme value is
  sometimes the observation that matters — so it is now possible to decline it
  without reassembling the pipeline by hand.
- **`correlation_matrix` reports undefined correlations as null.** A
  zero-variance column or a single-row frame yields NaN, which is not valid
  JSON. This matches `summary_stats`, which already did this.
- **The MCP `clean_data` tool offers outlier removal**, matching the REST
  `/clean` endpoint's option.
- **`/clean` offers `remove_dupes` and `standardise_cols`**, which the MCP tool
  had and it did not: the endpoint deduplicated rows and renamed columns
  unconditionally, so a caller who wanted their column names left alone had no
  way to say so. A test now asserts the two interfaces expose the same options.
- **`value_counts` accepts any column type.** It rejected non-numeric columns,
  which excluded exactly the columns worth counting. The test asserting that
  rejection encoded the wrong expectation and was corrected.
- **Clean functions no longer mutate their argument.** `drop_nulls`,
  `remove_duplicates`, `standardise_columns` and `add_column` used
  `inplace=True` or wrote through, so the caller's DataFrame changed underneath
  them. All return new frames.
- **`/clean` honours `remove_outliers`.** The flag was declared on the request
  model and never read, so callers asking for outlier removal silently got none.
- **Caller mistakes return 400, not 500.** A bad column name or malformed params
  on `/transform`, `/clean` and `/analyse` raised a bare `KeyError` that surfaced
  as a server error. `/visualise` already did this correctly.
- **Better errors.** Missing columns raise `ValueError` naming the column rather
  than `KeyError`; a bad operator lists the valid ones; `correlation_heatmap`
  with a text column says so instead of "could not convert string to float".
- **`remove_outliers` rejects an unknown `method`** rather than silently
  returning the frame untouched.
- **`/health` reports the real version.** It was hardcoded to `0.1.0` and had
  been wrong since 0.1.1; the test asserted the same stale literal, so it passed.
- **The MCP `transform_data` tool exposes `pivot`**, which the REST API had and
  it did not.

### Added

- **`merge_dataframes` is reachable from both agent interfaces**, via a `/merge`
  endpoint and a `merge_data` MCP tool. It was a public function of the
  transform module that neither interface could call, because both pass a single
  `data` payload and a merge needs two. These take `left` and `right` instead.

  Both return `left_rows` and `right_rows` alongside `rows`, so the failure mode
  a join actually has — silent row inflation — is visible in the response rather
  than something the caller has to think to check. Both also accept `validate`,
  which turns an unexpected cardinality into an error.

  On the REST side the request field is `validate` in JSON but `validate_join`
  in Python: a pydantic field named `validate` shadows a `BaseModel` attribute
  and warns, so it is declared with an alias to keep the public contract
  matching pandas' vocabulary.

### Tests

62 → 188. The new tests are regressions for the above, plus coverage of the two
merge interfaces; two existing tests were corrected where they asserted the old
wrong behaviour.

## 0.1.1

Move `api` and `mcp_server` inside the package; split dependencies into extras.

## 0.1.0

Initial release: ingest, clean, transform, analyse, visualise, over a Python
import, a REST API, and an MCP server.
