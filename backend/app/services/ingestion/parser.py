"""Multi-format tabular parser and schema inference engine for CSV, Excel, JSON, and Parquet."""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from fastapi import HTTPException, status

from app.schemas.dataset import ColumnSchema

SUPPORTED_EXTENSIONS = {
    ".csv": "csv",
    ".tsv": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".json": "json",
    ".parquet": "parquet",
    ".pq": "parquet",
}


def detect_file_format(file_path: Path, filename: str) -> str:
    """Detect file format from extension and signature."""
    ext = Path(filename).suffix.lower()
    if ext in SUPPORTED_EXTENSIONS:
        return SUPPORTED_EXTENSIONS[ext]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported file format '{ext}'. Supported formats: CSV (.csv), Excel (.xlsx), JSON (.json), Parquet (.parquet).",
    )


def sanitize_value_for_json(val: Any) -> Any:
    """Convert pandas/numpy types (NaN, NaT, inf, timestamps) to JSON-serializable primitives."""
    if val is None:
        return None
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    if pd.isna(val):
        return None
    return str(val)


def read_file_to_dataframe(file_path: Path, format_type: str) -> pd.DataFrame:
    """Read file into a pandas DataFrame depending on detected format."""
    try:
        if format_type == "csv":
            try:
                return pd.read_csv(file_path, encoding="utf-8")
            except (UnicodeDecodeError, pd.errors.ParserError):
                return pd.read_csv(file_path, encoding="latin1")

        elif format_type == "excel":
            return pd.read_excel(file_path, engine="openpyxl")

        elif format_type == "json":
            try:
                # Try standard JSON records/array
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                if isinstance(raw_data, list):
                    return pd.DataFrame(raw_data)
                elif isinstance(raw_data, dict):
                    # Check if dictionary has records under common keys or flat records
                    if "data" in raw_data and isinstance(raw_data["data"], list):
                        return pd.DataFrame(raw_data["data"])
                    return pd.DataFrame([raw_data])
                else:
                    return pd.DataFrame(raw_data)
            except Exception:
                # Fallback to line-delimited JSON (JSON lines)
                return pd.read_json(file_path, lines=True)

        elif format_type == "parquet":
            return pd.read_parquet(file_path, engine="pyarrow")

        else:
            raise ValueError(f"Unknown format: {format_type}")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse {format_type.upper()} data file: {str(e)}",
        )


def infer_column_schemas(df: pd.DataFrame) -> List[ColumnSchema]:
    """Extract column data types, null counts, null percentages, and sample values."""
    row_count = int(len(df))
    columns_schema: List[ColumnSchema] = []
    for col in df.columns:
        col_name = str(col)
        dtype_str = str(df[col].dtype)
        null_count = int(df[col].isna().sum())
        null_percentage = round((null_count / max(row_count, 1)) * 100.0, 2)

        sample_vals = df[col].dropna().unique()[:3].tolist()
        sanitized_samples = [sanitize_value_for_json(v) for v in sample_vals]

        columns_schema.append(
            ColumnSchema(
                name=col_name,
                data_type=dtype_str,
                null_count=null_count,
                null_percentage=null_percentage,
                sample_values=sanitized_samples,
            )
        )
    return columns_schema


def sanitize_records_for_json(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw dict records to JSON-safe primitives replacing NaN/inf."""
    cleaned: List[Dict[str, Any]] = []
    for r in records:
        clean_row: Dict[str, Any] = {}
        for k, v in r.items():
            clean_row[str(k)] = sanitize_value_for_json(v)
        cleaned.append(clean_row)
    return cleaned


def parse_and_profile_tabular_file(
    file_path: Path,
    filename: str,
    max_preview_rows: int = 50,
) -> Tuple[str, int, int, List[ColumnSchema], List[Dict[str, Any]]]:
    """
    Parse uploaded tabular file, extract column schemas and null stats,
    and produce JSON-safe head preview records.
    
    Returns:
        (format_type, row_count, column_count, columns_schema_list, preview_rows)
    """
    format_type = detect_file_format(file_path, filename)
    df = read_file_to_dataframe(file_path, format_type)

    row_count = int(len(df))
    column_count = int(len(df.columns))
    columns_schema = infer_column_schemas(df)

    preview_df = df.head(max_preview_rows)
    raw_preview = preview_df.to_dict(orient="records")
    preview_rows = sanitize_records_for_json(raw_preview)

    return format_type, row_count, column_count, columns_schema, preview_rows

