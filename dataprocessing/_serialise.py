"""JSON-safety helpers shared by the REST API and the MCP server.

Both interfaces hand their results to a JSON encoder, and pandas/numpy produce
values no JSON encoder accepts: int64, float64, ndarray, NaN. The REST API had
a converter for this; the MCP server did not, which is why its analyse_data
tool failed outright. Keeping the helpers here means both interfaces share one
implementation, and the MCP server can use it without importing FastAPI (an
optional extra it must not depend on).
"""
import json

import numpy as np
import pandas as pd


def to_native(obj):
    """Recursively convert numpy scalars/arrays to JSON-serialisable Python types.

    NaN becomes None: it is a float in Python but not a value JSON defines, and
    strict parsers reject the bare `NaN` token that json.dumps would emit.
    """
    if isinstance(obj, dict):
        return {to_native(k): to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_native(v) for v in obj]
    if isinstance(obj, np.generic):
        return to_native(obj.item())
    if isinstance(obj, np.ndarray):
        return [to_native(v) for v in obj.tolist()]
    if isinstance(obj, float) and obj != obj:  # NaN
        return None
    return obj


def df_to_json(df):
    """Convert a DataFrame to a list of row dicts, preserving a meaningful index.

    `orient="records"` discards the index. That is harmless for an ordinary
    RangeIndex, but group_and_aggregate and pivot put the grouping keys *in*
    the index — so discarding it silently threw away the labels and returned
    rows no caller could tell apart. Reset the index first when it carries
    information, then flatten any MultiIndex columns a pivot produced.
    """
    if isinstance(df.index, pd.MultiIndex) or df.index.name is not None:
        df = df.reset_index()

    if isinstance(df.columns, pd.MultiIndex):
        # A pivot over several value columns nests the column labels, and
        # to_json stringifies each tuple into a key like "('v1', 'x')" — not
        # something a caller can reasonably address. Join them instead: v1_x.
        df = df.copy()
        df.columns = [
            "_".join(str(part) for part in col if str(part) != "")
            for col in df.columns
        ]

    duplicated = sorted(set(df.columns[df.columns.duplicated()]))
    if duplicated:
        raise ValueError(f"Cannot serialise duplicate column name(s): {duplicated}")

    return json.loads(df.where(df.notna(), other=None).to_json(orient="records"))
