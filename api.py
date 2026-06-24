"""
DataProcessing REST API
Exposes ingest, clean, transform and analyse modules over HTTP.
Any AI agent can call these endpoints.
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import pandas as pd
import io
import json

from dataprocessing.clean import drop_nulls, remove_duplicates, standardise_columns
from dataprocessing.transform import (
    filter_rows, select_columns, rename_columns,
    sort_rows, group_and_aggregate, pivot, add_column
)
from dataprocessing.analyse import full_report

app = FastAPI(title="DataProcessing API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def df_to_json(df):
    return json.loads(df.where(df.notna(), other=None).to_json(orient="records"))

def to_native(obj):
    """Recursively convert numpy scalars/arrays to JSON-serialisable Python types.

    full_report() returns dicts containing numpy int64/float64 values and numpy
    arrays, which FastAPI's encoder cannot serialise. This normalises them.
    """
    import numpy as np
    if isinstance(obj, dict):
        return {to_native(k): to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_native(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return [to_native(v) for v in obj.tolist()]
    if isinstance(obj, float) and (obj != obj):  # NaN -> null
        return None
    return obj

class CleanRequest(BaseModel):
    data: List[Dict[str, Any]]
    drop_null_threshold: float = 0.5
    remove_outliers: bool = False

class TransformRequest(BaseModel):
    data: List[Dict[str, Any]]
    operation: str
    params: Dict[str, Any] = {}

class AnalyseRequest(BaseModel):
    data: List[Dict[str, Any]]

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(contents))
        elif ext == "json":
            df = pd.read_json(io.BytesIO(contents))
        elif ext == "xlsx":
            df = pd.read_excel(io.BytesIO(contents))
        elif ext == "parquet":
            df = pd.read_parquet(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
        return {"data": df_to_json(df), "rows": len(df), "columns": list(df.columns)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/clean")
def clean(req: CleanRequest):
    try:
        df = pd.DataFrame(req.data)
        df = drop_nulls(df, threshold=req.drop_null_threshold)
        df = remove_duplicates(df)
        df = standardise_columns(df)
        return {"data": df_to_json(df), "rows": len(df), "columns": list(df.columns)}
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
        result = ops[req.operation](df, **req.params)
        return {"data": df_to_json(result), "rows": len(result), "columns": list(result.columns)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyse")
def analyse(req: AnalyseRequest):
    try:
        df = pd.DataFrame(req.data)
        return to_native(full_report(df))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
