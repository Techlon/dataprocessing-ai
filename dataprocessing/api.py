"""
DataProcessing REST API
Exposes ingest, clean, transform and analyse modules over HTTP.
Any AI agent can call these endpoints.
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
import pandas as pd
import io
import json

from dataprocessing import __version__
from dataprocessing._defaults import (
    DEFAULT_IQR_FACTOR, DEFAULT_NULL_THRESHOLD, DEFAULT_ROW_NULL_THRESHOLD,
)
from dataprocessing import verify
from dataprocessing._serialise import df_to_json, to_native
from dataprocessing.clean import (
    drop_nulls, remove_duplicates, remove_outliers as remove_outliers_iqr,
    standardise_columns,
)
from dataprocessing.transform import (
    filter_rows, select_columns, rename_columns,
    sort_rows, group_and_aggregate, pivot, add_column, merge_dataframes
)
from dataprocessing.analyse import full_report

from dataprocessing.visualise import (
    histogram, bar_chart, scatter, line_chart, correlation_heatmap
)

app = FastAPI(title="DataProcessing API", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CleanRequest(BaseModel):
    data: List[Dict[str, Any]]
    drop_null_threshold: float = DEFAULT_NULL_THRESHOLD
    # Share of a row that may be null before the row is dropped. 0.0 (any null
    # drops the row) is the historical behaviour and costs about a quarter of
    # the rows on data with 5% of cells missing; 1.0 keeps every row.
    row_null_threshold: float = DEFAULT_ROW_NULL_THRESHOLD
    # Parity with the MCP clean_data tool, which has always offered these two.
    # This endpoint deduplicated and renamed columns unconditionally, so a
    # caller who wanted their column names left alone had no way to say so.
    remove_dupes: bool = True
    standardise_cols: bool = True
    remove_outliers: bool = False
    # The multiplier on the IQR that sets the outlier fence. Only consulted
    # when remove_outliers is true; 3.0 removes fewer rows than the 1.5 default.
    outlier_factor: float = DEFAULT_IQR_FACTOR

class TransformRequest(BaseModel):
    data: List[Dict[str, Any]]
    operation: str
    params: Dict[str, Any] = {}

class AnalyseRequest(BaseModel):
    data: List[Dict[str, Any]]

class MergeRequest(BaseModel):
    """A merge needs two datasets, so it cannot use the single-payload shape
    the other transform endpoints share."""
    left: List[Dict[str, Any]]
    right: List[Dict[str, Any]]
    on: Optional[Union[str, List[str]]] = None
    how: str = "inner"
    # The JSON key stays "validate" to match pandas' own vocabulary; the Python
    # attribute is renamed because a field called `validate` shadows a
    # BaseModel attribute and pydantic warns about it.
    validate_join: Optional[str] = Field(default=None, alias="validate")
    suffixes: List[str] = ["_x", "_y"]

    model_config = {"populate_by_name": True}

@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}

@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        # A filename with no dot used to yield the whole name as the extension,
        # so the error read "Unsupported file type: myexport".
        filename = file.filename or ""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(contents))
        elif ext == "json":
            df = pd.read_json(io.BytesIO(contents))
        elif ext == "xlsx":
            df = pd.read_excel(io.BytesIO(contents))
        elif ext == "parquet":
            df = pd.read_parquet(io.BytesIO(contents))
        elif ext == "txt":
            # read_file and the MCP ingest_file tool have always accepted .txt;
            # this endpoint rejected it, so the two interfaces disagreed.
            df = pd.read_csv(io.BytesIO(contents), sep=None, engine="python")
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext or filename!r}. "
                       "Supported: csv, json, xlsx, parquet, txt",
            )
        return {"data": df_to_json(df), "rows": len(df), "columns": list(df.columns)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/clean")
def clean(req: CleanRequest):
    try:
        df = pd.DataFrame(req.data)
        rows_in, columns_in = len(df), len(df.columns)
        original_columns = list(df.columns)
        warnings = []

        df = drop_nulls(df, threshold=req.drop_null_threshold,
                        row_threshold=req.row_null_threshold)
        # Measured per stage rather than once at the end, so each warning can
        # name the step that actually caused the loss and the option that
        # changes it. A single before/after count could not.
        warnings.append(verify.row_loss(
            rows_in, len(df),
            f"rows with more than {req.row_null_threshold:.0%} null values were dropped.",
            "Raise row_null_threshold to keep patchy rows, or pass a subset to "
            "judge rows on key columns only.",
        ))
        warnings.append(verify.dropped_columns(
            original_columns, list(df.columns),
            f"more than {req.drop_null_threshold:.0%} of their values were null.",
            "Raise drop_null_threshold to keep them.",
        ))

        rows_before_dupes = len(df)
        if req.remove_dupes:
            df = remove_duplicates(df)
            warnings.append(verify.row_loss(
                rows_before_dupes, len(df), "duplicate rows were removed.",
                "Set remove_dupes to false to keep them.",
            ))
        # The request model has always offered this flag; it was declared and
        # then ignored, so callers asking for outlier removal silently got none.
        rows_before_outliers = len(df)
        if req.remove_outliers:
            df = remove_outliers_iqr(df, factor=req.outlier_factor)
            warnings.append(verify.row_loss(
                rows_before_outliers, len(df),
                f"rows holding a value beyond {req.outlier_factor} x the "
                f"interquartile range were removed.",
                "Raise outlier_factor to keep more, or set remove_outliers to "
                "false — an extreme value is sometimes the observation that matters.",
            ))
        if req.standardise_cols:
            df = standardise_columns(df)
        # Per-stage warnings each carry a specific remedy, but each is judged
        # against its own threshold — so several small losses can compound past
        # it while no single stage trips. This catches that case.
        if not any(warnings):
            warnings.append(verify.row_loss(
                rows_in, len(df), "cleaning removed rows across several steps.",
                "Compare rows against rows_in, and relax the thresholds if the "
                "loss is more than you intended.",
            ))
        return {
            "data": df_to_json(df),
            "rows": len(df),
            "columns": list(df.columns),
            # Cleaning drops every row holding any null, which costs far more
            # rows than callers expect. Reporting the input size makes the loss
            # visible in the response instead of something to think to check.
            "rows_in": rows_in,
            "columns_in": columns_in,
            "warnings": [w for w in warnings if w],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transform")
def transform(req: TransformRequest):
    try:
        df = pd.DataFrame(req.data)
        ops = {
            "filter_rows": filter_rows,
            "select_columns": select_columns,
            "rename_columns": rename_columns,
            "sort_rows": sort_rows,
            "group_and_aggregate": group_and_aggregate,
            "pivot": pivot,
            "add_column": add_column,
        }
        if req.operation not in ops:
            raise HTTPException(status_code=400, detail=f"Unknown operation: {req.operation}. Valid: {list(ops.keys())}")
        rows_in = len(df)
        result = ops[req.operation](df, **req.params)
        warning = verify.row_loss(
            rows_in, len(result), f"{req.operation} matched fewer rows than it received.",
            "Check the operator and value against the column's actual contents.",
        )
        return {
            "data": df_to_json(result),
            "rows": len(result),
            "columns": list(result.columns),
            "rows_in": rows_in,
            "warnings": [warning] if warning else [],
        }
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError) as e:
        # A bad column name or a malformed params dict is the caller's mistake,
        # not a server fault; these previously came back as 500s.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/merge")
def merge(req: MergeRequest):
    try:
        if len(req.suffixes) != 2:
            raise ValueError("suffixes must be a list of exactly two strings.")
        left = pd.DataFrame(req.left)
        right = pd.DataFrame(req.right)
        result = merge_dataframes(
            left, right,
            on=req.on,
            how=req.how,
            validate=req.validate_join,
            suffixes=tuple(req.suffixes),
        )
        return {
            "data": df_to_json(result),
            "rows": len(result),
            "columns": list(result.columns),
            # Row counts are reported because a join's usual failure is silent
            # inflation: the caller can see 3 x 3 rows became 9.
            "left_rows": len(left),
            "right_rows": len(right),
            "warnings": verify.merge_result(
                len(left), len(right), len(result), how=req.how),
        }
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyse")
def analyse(req: AnalyseRequest):
    try:
        df = pd.DataFrame(req.data)
        return to_native(full_report(df))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
class VisualiseRequest(BaseModel):
    data: List[Dict[str, Any]]
    chart: str
    params: Dict[str, Any] = {}

@app.post("/visualise")
def visualise(req: VisualiseRequest):
    try:
        df = pd.DataFrame(req.data)
        charts = {
            "histogram": histogram,
            "bar_chart": bar_chart,
            "scatter": scatter,
            "line_chart": line_chart,
            "correlation_heatmap": correlation_heatmap,
        }
        if req.chart not in charts:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown chart: {req.chart}. Valid: {list(charts.keys())}",
            )
        result = charts[req.chart](df, **req.params)
        return to_native(result)
    except HTTPException:
        raise
    except Exception as e:
        # bad/missing/non-numeric column raises ValueError -> client error
        raise HTTPException(status_code=400, detail=str(e))
