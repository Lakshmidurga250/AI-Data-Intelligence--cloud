"""
Platform Service for AI Data Intelligence Cloud
Provides unified dataset management, profiling, cleaning, pipeline execution,
dynamic analytics, AI assistant queries, and AutoML benchmarking.
Matches existing SQLAlchemy models and ai_data_cloud.db schema.
"""

import os
import sys
import uuid
import math
import json
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure backend directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import numpy as np
import pandas as pd

from app.services.ingestion.parser import read_file_to_dataframe, infer_column_schemas, sanitize_records_for_json
from app.services.profiling.profiler import profile_dataframe
from app.services.assistant.engine import translate_and_execute_nl_query, discover_dataset_insights, classify_user_intent
from app.services.ml.trainer import get_candidate_estimators, compute_metrics
from sklearn.model_selection import train_test_split

def df_to_clean_json_records(df_subset: pd.DataFrame) -> List[Dict[str, Any]]:
    """Safely convert DataFrame subset to JSON-serializable list of dicts."""
    return sanitize_records_for_json(df_subset.to_dict(orient="records"))


DB_PATH = PROJECT_ROOT / "ai_data_cloud.db"
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "workspaces" / "default" / "raw"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_WORKSPACE_ID = "c269cd18-2e86-427e-b878-96a8aa45cf98"
DEFAULT_USER_ID = "82b73422-72b4-4bc2-a169-fc0d0a401f5b"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def seed_default_datasets_if_needed():
    """Seed initial sample datasets into database if not already present."""
    conn = get_db_connection()
    cursor = conn.cursor()

    samples = [
        ("data/sample_sales_data.csv", "Sample Sales Dataset (Primary)", "Realistic enterprise sales transactions with order dates, categories, quantities, unit prices, and revenues."),
        ("data/sample_customers.csv", "Sample Customers Dataset", "Customer profiles with age, city, signup dates, loyalty tiers, and churn risk scores."),
        ("data/sample_employees.csv", "Sample Employees Dataset", "Employee records across departments, salary figures, hire dates, and performance ratings."),
        ("data/sample_sensor_readings.csv", "Sample IoT Sensor Readings", "Telemetry sensor recordings with temperature, humidity, pressure, and operational alerts.")
    ]

    now_iso = datetime.now(timezone.utc).isoformat()

    for rel_path, display_name, desc in samples:
        abs_path = PROJECT_ROOT / rel_path
        if not abs_path.exists():
            continue

        cursor.execute("SELECT id FROM datasets WHERE name = ?", (display_name,))
        if cursor.fetchone():
            continue

        try:
            df = read_file_to_dataframe(abs_path, "csv")
            with open(abs_path, "rb") as f:
                checksum = hashlib.sha256(f.read()).hexdigest()
            file_size = abs_path.stat().st_size
            ds_id = str(uuid.uuid4())

            # Copy to upload directory
            dest_file = UPLOAD_DIR / f"{ds_id}_{abs_path.name}"
            with open(abs_path, "rb") as src, open(dest_file, "wb") as dst:
                dst.write(src.read())

            schemas = infer_column_schemas(df)
            schemas_json = json.dumps([s.model_dump() for s in schemas])
            preview_json = json.dumps(df_to_clean_json_records(df.head(25)))

            cursor.execute("""
                INSERT INTO datasets (id, workspace_id, name, description, filename, storage_path, format, size_bytes, row_count, column_count, sha256, version, created_by_id, schema_metadata, preview_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'csv', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            """, (ds_id, DEFAULT_WORKSPACE_ID, display_name, desc, abs_path.name, str(dest_file), file_size, len(df), len(df.columns), checksum, DEFAULT_USER_ID, schemas_json, preview_json, now_iso, now_iso))

            cursor.execute("""
                INSERT INTO dataset_versions (id, dataset_id, version_number, storage_path, size_bytes, row_count, column_count, sha256, change_summary, created_by_id, profile_json, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?, ?, ?, ?, 'Initial sample dataset ingestion', ?, '{}', ?, ?)
            """, (str(uuid.uuid4()), ds_id, str(dest_file), file_size, len(df), len(df.columns), checksum, DEFAULT_USER_ID, now_iso, now_iso))

        except Exception as e:
            print(f"Error seeding {display_name}: {e}")

    conn.commit()
    conn.close()


def list_datasets() -> List[Dict[str, Any]]:
    """List all registered datasets."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, description, filename, format, storage_path, size_bytes, sha256, row_count, column_count, version, created_at
        FROM datasets
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    datasets = [dict(r) for r in rows]
    conn.close()
    return datasets


def get_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    """Get single dataset metadata."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_dataset_preview(dataset_id: str, limit: int = 25) -> Dict[str, Any]:
    """Load dataset from storage and return schema + preview rows."""
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found.")

    file_path = Path(meta["storage_path"])
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset file at {file_path} missing.")

    df = read_file_to_dataframe(file_path, meta["format"])
    schemas = infer_column_schemas(df)
    preview_rows = df_to_clean_json_records(df.head(limit))

    return {
        "dataset_id": dataset_id,
        "name": meta["name"],
        "format": meta["format"],
        "row_count": len(df),
        "column_count": len(df.columns),
        "size_bytes": meta["size_bytes"],
        "columns": [s.model_dump() for s in schemas],
        "preview_data": preview_rows,
        "created_at": meta["created_at"],
    }


def upload_dataset_file(file_storage, custom_name: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
    """Validate, store, and register uploaded tabular dataset file."""
    original_filename = file_storage.filename or "uploaded_dataset.csv"
    ext = Path(original_filename).suffix.lower()

    allowed_exts = {
        ".csv": "csv",
        ".xlsx": "excel",
        ".xls": "excel",
        ".json": "json",
        ".parquet": "parquet"
    }

    if ext not in allowed_exts:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: CSV (.csv), Excel (.xlsx, .xls), JSON (.json), Parquet (.parquet).")

    format_type = allowed_exts[ext]
    dataset_id = str(uuid.uuid4())
    safe_filename = f"{dataset_id}_{Path(original_filename).name}"
    target_path = UPLOAD_DIR / safe_filename

    # Save uploaded file
    file_storage.save(str(target_path))
    file_size = target_path.stat().st_size

    if file_size == 0:
        target_path.unlink(missing_ok=True)
        raise ValueError("Uploaded file is empty (0 bytes).")
    if file_size > 50 * 1024 * 1024:
        target_path.unlink(missing_ok=True)
        raise ValueError("File exceeds maximum upload limit of 50 MB.")

    # Calculate SHA-256
    sha256 = hashlib.sha256()
    with open(target_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    checksum = sha256.hexdigest()

    # Check if CSV/text contains null bytes or binary garbage
    if format_type == "csv":
        has_null_bytes = False
        with open(target_path, "rb") as f:
            header_sample = f.read(2048)
            if b"\x00" in header_sample:
                has_null_bytes = True
        if has_null_bytes:
            target_path.unlink(missing_ok=True)
            raise ValueError("Malformed CSV: Binary / NUL bytes detected in text file.")

    # Parse and validate with pandas
    try:
        df = read_file_to_dataframe(target_path, format_type)
    except Exception as e:
        target_path.unlink(missing_ok=True)
        raise ValueError(f"Failed to parse tabular data from {original_filename}: {str(e)}")

    if len(df.columns) == 0:
        target_path.unlink(missing_ok=True)
        raise ValueError("Uploaded tabular file contains 0 columns.")

    display_name = custom_name.strip() if custom_name and custom_name.strip() else original_filename
    now_iso = datetime.now(timezone.utc).isoformat()

    schemas = infer_column_schemas(df)
    schemas_json = json.dumps([s.model_dump() for s in schemas])
    preview_json = json.dumps(df_to_clean_json_records(df.head(25)))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO datasets (id, workspace_id, name, description, filename, storage_path, format, size_bytes, row_count, column_count, sha256, version, created_by_id, schema_metadata, preview_data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
    """, (dataset_id, DEFAULT_WORKSPACE_ID, display_name, description or f"Ingested from {original_filename}", original_filename, str(target_path), format_type, file_size, len(df), len(df.columns), checksum, DEFAULT_USER_ID, schemas_json, preview_json, now_iso, now_iso))

    cursor.execute("""
        INSERT INTO dataset_versions (id, dataset_id, version_number, storage_path, size_bytes, row_count, column_count, sha256, change_summary, created_by_id, profile_json, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?, 'Initial file upload', ?, '{}', ?, ?)
    """, (str(uuid.uuid4()), dataset_id, str(target_path), file_size, len(df), len(df.columns), checksum, DEFAULT_USER_ID, now_iso, now_iso))

    conn.commit()
    conn.close()

    return {
        "id": dataset_id,
        "name": display_name,
        "format": format_type,
        "row_count": len(df),
        "column_count": len(df.columns),
        "size_bytes": file_size,
        "checksum": checksum,
        "storage_path": str(target_path),
        "created_at": now_iso
    }


def delete_dataset(dataset_id: str) -> bool:
    """Delete dataset record and quarantined file."""
    meta = get_dataset(dataset_id)
    if not meta:
        return False

    file_path = Path(meta["storage_path"])
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            pass

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dataset_versions WHERE dataset_id = ?", (dataset_id,))
    cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    conn.commit()
    conn.close()
    return True


def profile_dataset(dataset_id: str) -> Dict[str, Any]:
    """Compute exhaustive pandas statistical profile and correlation scorecard."""
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found.")

    file_path = Path(meta["storage_path"])
    df = read_file_to_dataframe(file_path, meta["format"])
    prof = profile_dataframe(df, dataset_id, meta["name"])
    return prof.model_dump()


def clean_dataset(dataset_id: str, operations: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform verified data cleaning operations on dataset.
    Preserves original file; creates a new derived dataset version.
    """
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found.")

    file_path = Path(meta["storage_path"])
    df = read_file_to_dataframe(file_path, meta["format"]).copy()

    before_rows = len(df)
    before_nulls = int(df.isna().sum().sum())
    before_dups = int(df.duplicated().sum())

    applied_actions = []

    # 1. Deduplication
    if operations.get("remove_duplicates"):
        df = df.drop_duplicates()
        dups_removed = before_rows - len(df)
        applied_actions.append(f"Removed {dups_removed} duplicate rows")

    # 2. Impute numeric missing values
    num_strat = operations.get("fill_numeric_strategy")
    if num_strat:
        num_cols = df.select_dtypes(include=[np.number]).columns
        for col in num_cols:
            if df[col].isna().sum() > 0:
                if num_strat == "mean":
                    val = float(df[col].mean())
                elif num_strat == "median":
                    val = float(df[col].median())
                elif num_strat == "zero":
                    val = 0.0
                else:
                    val = 0.0
                df[col] = df[col].fillna(val)
                applied_actions.append(f"Imputed missing '{col}' with {num_strat} ({val:.2f})")

    # 3. Impute categorical missing values
    cat_strat = operations.get("fill_categorical_strategy")
    if cat_strat:
        cat_cols = df.select_dtypes(exclude=[np.number]).columns
        for col in cat_cols:
            if df[col].isna().sum() > 0:
                mode_vals = df[col].mode()
                val = str(mode_vals.iloc[0]) if len(mode_vals) > 0 else "Unknown"
                df[col] = df[col].fillna(val)
                applied_actions.append(f"Imputed missing '{col}' with mode ('{val}')")

    # 4. Filter rows
    filter_col = operations.get("filter_column")
    filter_op = operations.get("filter_operator")
    filter_val = operations.get("filter_value")
    if filter_col and filter_col in df.columns and filter_op and filter_val is not None:
        try:
            if pd.api.types.is_numeric_dtype(df[filter_col]):
                num_v = float(filter_val)
                if filter_op == ">": df = df[df[filter_col] > num_v]
                elif filter_op == ">=": df = df[df[filter_col] >= num_v]
                elif filter_op == "<": df = df[df[filter_col] < num_v]
                elif filter_op == "<=": df = df[df[filter_col] <= num_v]
                elif filter_op == "==": df = df[df[filter_col] == num_v]
                elif filter_op == "!=": df = df[df[filter_col] != num_v]
            else:
                str_v = str(filter_val)
                if filter_op == "==": df = df[df[filter_col] == str_v]
                elif filter_op == "!=": df = df[df[filter_col] != str_v]
                elif filter_op == "contains": df = df[df[filter_col].astype(str).str.contains(str_v, case=False, na=False)]
            applied_actions.append(f"Filtered rows where {filter_col} {filter_op} {filter_val}")
        except Exception as e:
            applied_actions.append(f"Filter error: {str(e)}")

    # 5. Rename column
    rename_old = operations.get("rename_old_col")
    rename_new = operations.get("rename_new_col")
    if rename_old and rename_new and rename_old in df.columns:
        df = df.rename(columns={rename_old: rename_new})
        applied_actions.append(f"Renamed column '{rename_old}' to '{rename_new}'")

    after_rows = len(df)
    after_nulls = int(df.isna().sum().sum())
    after_dups = int(df.duplicated().sum())

    # Save as derived dataset
    new_dataset_id = str(uuid.uuid4())
    base_name = Path(meta["name"]).stem
    now_iso = datetime.now(timezone.utc).isoformat()
    derived_name = f"{base_name}_cleaned_{datetime.now(timezone.utc).strftime('%H%M%S')}.csv"
    derived_path = UPLOAD_DIR / f"{new_dataset_id}_{derived_name}"

    df.to_csv(derived_path, index=False)
    file_size = derived_path.stat().st_size

    with open(derived_path, "rb") as f:
        checksum = hashlib.sha256(f.read()).hexdigest()

    schemas = infer_column_schemas(df)
    schemas_json = json.dumps([s.model_dump() for s in schemas])
    preview_json = json.dumps(df_to_clean_json_records(df.head(25)))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO datasets (id, workspace_id, name, description, filename, storage_path, format, size_bytes, row_count, column_count, sha256, version, created_by_id, schema_metadata, preview_data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'csv', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
    """, (new_dataset_id, DEFAULT_WORKSPACE_ID, derived_name, f"Cleaned derived dataset from {meta['name']}. Actions: {'; '.join(applied_actions)}", derived_name, str(derived_path), file_size, after_rows, len(df.columns), checksum, DEFAULT_USER_ID, schemas_json, preview_json, now_iso, now_iso))

    cursor.execute("""
        INSERT INTO dataset_versions (id, dataset_id, version_number, storage_path, size_bytes, row_count, column_count, sha256, change_summary, created_by_id, profile_json, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
    """, (str(uuid.uuid4()), new_dataset_id, str(derived_path), file_size, after_rows, len(df.columns), checksum, f"Derived cleaning: {'; '.join(applied_actions)}", DEFAULT_USER_ID, now_iso, now_iso))
    conn.commit()
    conn.close()

    preview = df_to_clean_json_records(df.head(15))

    return {
        "success": True,
        "new_dataset_id": new_dataset_id,
        "new_dataset_name": derived_name,
        "actions_applied": applied_actions,
        "metrics_before": {
            "rows": before_rows,
            "nulls": before_nulls,
            "duplicates": before_dups
        },
        "metrics_after": {
            "rows": after_rows,
            "nulls": after_nulls,
            "duplicates": after_dups
        },
        "preview_data": preview
    }


def execute_etl_pipeline(source_dataset_id: str, nodes: List[Dict[str, Any]], output_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute real Visual ETL Pipeline DAG stages and materialize output dataset.
    """
    meta = get_dataset(source_dataset_id)
    if not meta:
        raise ValueError(f"Source dataset '{source_dataset_id}' not found.")

    t_start = datetime.now(timezone.utc)
    file_path = Path(meta["storage_path"])
    df = read_file_to_dataframe(file_path, meta["format"]).copy()

    stage_logs = []
    initial_rows = len(df)
    stage_logs.append({
        "stage": "Source Ingestion",
        "node_type": "source",
        "status": "COMPLETED",
        "input_rows": initial_rows,
        "output_rows": initial_rows,
        "message": f"Loaded {initial_rows:,} rows from source '{meta['name']}'"
    })

    current_df = df

    for idx, node in enumerate(nodes):
        ntype = node.get("type", "").lower()
        cfg = node.get("config", {})
        n_in = len(current_df)

        if ntype == "filter":
            col = cfg.get("column")
            op = cfg.get("operator", "==")
            val = cfg.get("value")
            if col and col in current_df.columns:
                try:
                    if pd.api.types.is_numeric_dtype(current_df[col]):
                        nv = float(val)
                        if op == ">": current_df = current_df[current_df[col] > nv]
                        elif op == ">=": current_df = current_df[current_df[col] >= nv]
                        elif op == "<": current_df = current_df[current_df[col] < nv]
                        elif op == "<=": current_df = current_df[current_df[col] <= nv]
                        elif op == "==": current_df = current_df[current_df[col] == nv]
                        elif op == "!=": current_df = current_df[current_df[col] != nv]
                    else:
                        sv = str(val)
                        if op == "==": current_df = current_df[current_df[col] == sv]
                        elif op == "!=": current_df = current_df[current_df[col] != sv]
                        elif op == "contains": current_df = current_df[current_df[col].astype(str).str.contains(sv, case=False, na=False)]
                    stage_logs.append({
                        "stage": f"Stage {idx+1}: Filter Rows",
                        "node_type": "filter",
                        "status": "COMPLETED",
                        "input_rows": n_in,
                        "output_rows": len(current_df),
                        "message": f"Filtered on {col} {op} {val} (retained {len(current_df)} rows)"
                    })
                except Exception as e:
                    stage_logs.append({
                        "stage": f"Stage {idx+1}: Filter Error",
                        "node_type": "filter",
                        "status": "ERROR",
                        "input_rows": n_in,
                        "output_rows": len(current_df),
                        "message": str(e)
                    })

        elif ntype == "deduplicate":
            current_df = current_df.drop_duplicates()
            stage_logs.append({
                "stage": f"Stage {idx+1}: Deduplication",
                "node_type": "deduplicate",
                "status": "COMPLETED",
                "input_rows": n_in,
                "output_rows": len(current_df),
                "message": f"Removed {n_in - len(current_df)} duplicate rows"
            })

        elif ntype == "impute":
            strat = cfg.get("strategy", "median")
            num_cols = current_df.select_dtypes(include=[np.number]).columns
            for c in num_cols:
                if current_df[c].isna().sum() > 0:
                    v = float(current_df[c].median()) if strat == "median" else float(current_df[c].mean())
                    current_df[c] = current_df[c].fillna(v)
            stage_logs.append({
                "stage": f"Stage {idx+1}: Missing Value Imputation",
                "node_type": "impute",
                "status": "COMPLETED",
                "input_rows": n_in,
                "output_rows": len(current_df),
                "message": f"Imputed numeric missing values using {strat}"
            })

        elif ntype == "derive":
            target_col = cfg.get("target_column")
            col_a = cfg.get("column_a")
            col_b = cfg.get("column_b")
            op = cfg.get("op", "*")
            if target_col and col_a in current_df.columns and col_b in current_df.columns:
                try:
                    if op == "*": current_df[target_col] = current_df[col_a] * current_df[col_b]
                    elif op == "+": current_df[target_col] = current_df[col_a] + current_df[col_b]
                    elif op == "-": current_df[target_col] = current_df[col_a] - current_df[col_b]
                    elif op == "/": current_df[target_col] = current_df[col_a] / current_df[col_b].replace(0, np.nan)
                    stage_logs.append({
                        "stage": f"Stage {idx+1}: Derived Column",
                        "node_type": "derive",
                        "status": "COMPLETED",
                        "input_rows": n_in,
                        "output_rows": len(current_df),
                        "message": f"Calculated {target_col} = {col_a} {op} {col_b}"
                    })
                except Exception as e:
                    stage_logs.append({"stage": f"Stage {idx+1}: Derive Error", "node_type": "derive", "status": "ERROR", "message": str(e)})

    # Materialize output dataset
    out_name = output_name.strip() if output_name and output_name.strip() else f"etl_pipeline_output_{datetime.now(timezone.utc).strftime('%H%M%S')}.csv"
    out_id = str(uuid.uuid4())
    out_path = UPLOAD_DIR / f"{out_id}_{out_name}"
    current_df.to_csv(out_path, index=False)
    file_size = out_path.stat().st_size

    with open(out_path, "rb") as f:
        checksum = hashlib.sha256(f.read()).hexdigest()

    now_iso = datetime.now(timezone.utc).isoformat()
    schemas = infer_column_schemas(current_df)
    schemas_json = json.dumps([s.model_dump() for s in schemas])
    preview_json = json.dumps(df_to_clean_json_records(current_df.head(25)))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO datasets (id, workspace_id, name, description, filename, storage_path, format, size_bytes, row_count, column_count, sha256, version, created_by_id, schema_metadata, preview_data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'csv', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
    """, (out_id, DEFAULT_WORKSPACE_ID, out_name, f"Materialized by Visual ETL Pipeline from '{meta['name']}'", out_name, str(out_path), file_size, len(current_df), len(current_df.columns), checksum, DEFAULT_USER_ID, schemas_json, preview_json, now_iso, now_iso))

    cursor.execute("""
        INSERT INTO dataset_versions (id, dataset_id, version_number, storage_path, size_bytes, row_count, column_count, sha256, change_summary, created_by_id, profile_json, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?, 'Pipeline execution output', ?, '{}', ?, ?)
    """, (str(uuid.uuid4()), out_id, str(out_path), file_size, len(current_df), len(current_df.columns), checksum, DEFAULT_USER_ID, now_iso, now_iso))

    # Also log pipeline run
    run_id = str(uuid.uuid4())
    exec_ms = int((datetime.now(timezone.utc) - t_start).total_seconds() * 1000)
    cursor.execute("""
        INSERT INTO pipeline_runs (id, pipeline_id, workspace_id, status, triggered_by, started_at, completed_at, execution_time_ms, stage_results, output_dataset_id, created_at, updated_at)
        VALUES (?, ?, ?, 'succeeded', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, "visual_dag", DEFAULT_WORKSPACE_ID, DEFAULT_USER_ID, t_start.isoformat(), now_iso, exec_ms, json.dumps(stage_logs), out_id, now_iso, now_iso))
    conn.commit()
    conn.close()

    stage_logs.append({
        "stage": "Sink Materialization",
        "node_type": "sink",
        "status": "COMPLETED",
        "input_rows": len(current_df),
        "output_rows": len(current_df),
        "message": f"Successfully materialized into '{out_name}' ({len(current_df):,} rows, {file_size:,} bytes)"
    })

    return {
        "success": True,
        "output_dataset_id": out_id,
        "output_dataset_name": out_name,
        "total_stages": len(stage_logs),
        "input_rows": initial_rows,
        "output_rows": len(current_df),
        "stages": stage_logs,
        "preview_data": df_to_clean_json_records(current_df.head(15))
    }


def get_dataset_analytics(dataset_id: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate dynamic KPIs and visualization aggregations from selected dataset.
    Adapts intelligently between Sales Schema and arbitrary non-sales schemas!
    """
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found.")

    file_path = Path(meta["storage_path"])
    df = read_file_to_dataframe(file_path, meta["format"]).copy()

    # Apply filters if provided
    if filters:
        for k, v in filters.items():
            if k in df.columns and v:
                df = df[df[k].astype(str) == str(v)]

    col_names_lower = [c.lower() for c in df.columns]
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()

    # Check for date column
    date_col = None
    for c in df.columns:
        if "date" in c.lower() or "time" in c.lower() or "timestamp" in c.lower():
            date_col = c
            break

    # 1. SALES DATASET PATH
    is_sales = any("sales" in c or "revenue" in c for c in col_names_lower) and any("quant" in c or "qty" in c for c in col_names_lower)

    if is_sales:
        sales_col = next((c for c in df.columns if "sales" in c.lower() or "revenue" in c.lower() or "amount" in c.lower()), num_cols[0] if num_cols else None)
        qty_col = next((c for c in df.columns if "quantity" in c.lower() or "qty" in c.lower() or "units" in c.lower()), None)
        cat_col = next((c for c in df.columns if "category" in c.lower() or "segment" in c.lower() or "type" in c.lower()), cat_cols[0] if cat_cols else None)
        reg_col = next((c for c in df.columns if "region" in c.lower() or "country" in c.lower() or "territory" in c.lower()), None)
        prod_col = next((c for c in df.columns if "product" in c.lower() or "item" in c.lower()), None)
        pm_col = next((c for c in df.columns if "payment" in c.lower() or "method" in c.lower()), None)

        total_sales = float(df[sales_col].sum()) if sales_col else 0.0
        order_count = len(df)
        units_sold = int(df[qty_col].sum()) if qty_col else 0
        avg_order = round(total_sales / max(order_count, 1), 2)

        kpis = [
            {"title": "Total Revenue", "value": f"${total_sales:,.2f}", "sub": "Gross Sales Volume", "color": "primary"},
            {"title": "Total Orders", "value": f"{order_count:,}", "sub": "Completed Transactions", "color": "emerald"},
            {"title": "Units Sold", "value": f"{units_sold:,}", "sub": "Total Physical/Digital Units", "color": "purple"},
            {"title": "Avg Order Value", "value": f"${avg_order:,.2f}", "sub": "Per-Transaction Revenue", "color": "amber"}
        ]

        # Category Breakdown
        by_category = []
        if cat_col:
            cat_grp = df.groupby(cat_col)[sales_col].sum().reset_index().sort_values(by=sales_col, ascending=False)
            for _, r in cat_grp.iterrows():
                by_category.append({"label": str(r[cat_col]), "value": round(float(r[sales_col]), 2)})

        # Region Breakdown
        by_region = []
        if reg_col:
            reg_grp = df.groupby(reg_col)[sales_col].sum().reset_index().sort_values(by=sales_col, ascending=False)
            for _, r in reg_grp.iterrows():
                by_region.append({"label": str(r[reg_col]), "value": round(float(r[sales_col]), 2)})

        # Sales over time
        sales_timeline = []
        if date_col:
            try:
                time_df = df.copy()
                time_df["_dt"] = pd.to_datetime(time_df[date_col], errors="coerce")
                time_df = time_df.dropna(subset=["_dt"]).sort_values("_dt")
                time_grp = time_df.groupby(time_df["_dt"].dt.strftime("%Y-%m-%d"))[sales_col].sum().reset_index()
                for _, r in time_grp.tail(20).iterrows():
                    sales_timeline.append({"date": r["_dt"], "value": round(float(r[sales_col]), 2)})
            except Exception:
                pass

        # Top Products
        top_products = []
        if prod_col:
            p_grp = df.groupby(prod_col)[sales_col].sum().reset_index().sort_values(by=sales_col, ascending=False).head(5)
            for _, r in p_grp.iterrows():
                top_products.append({"product": str(r[prod_col]), "revenue": round(float(r[sales_col]), 2)})

        # Payment methods
        payment_methods = []
        if pm_col:
            pm_grp = df[pm_col].dropna().value_counts().reset_index()
            for _, r in pm_grp.iterrows():
                payment_methods.append({"method": str(r.iloc[0]), "count": int(r.iloc[1])})

        # Filter options
        filter_options = {
            "categories": sorted(df[cat_col].dropna().unique().tolist()) if cat_col else [],
            "regions": sorted(df[reg_col].dropna().unique().tolist()) if reg_col else []
        }

        return {
            "dataset_type": "sales",
            "kpis": kpis,
            "category_chart": {"title": "Revenue by Product Category", "data": by_category},
            "region_chart": {"title": "Revenue by Geographic Region", "data": by_region},
            "timeline_chart": {"title": "Sales Trajectory Over Time", "data": sales_timeline},
            "top_products": top_products,
            "payment_methods": payment_methods,
            "filter_options": filter_options
        }

    # 2. ADAPTIVE GENERIC / NON-SALES DATASET PATH
    total_records = len(df)
    first_num = num_cols[0] if len(num_cols) > 0 else None
    second_num = num_cols[1] if len(num_cols) > 1 else None
    first_cat = cat_cols[0] if len(cat_cols) > 0 else None

    kpis = [
        {"title": "Total Records", "value": f"{total_records:,}", "sub": f"Schema: {len(df.columns)} Columns", "color": "primary"}
    ]
    if first_num:
        sum_1 = float(df[first_num].sum())
        avg_1 = float(df[first_num].mean())
        kpis.append({"title": f"Total {first_num}", "value": f"{sum_1:,.2f}" if abs(sum_1) > 1000 else f"{sum_1:.4f}", "sub": f"Mean: {avg_1:.2f}", "color": "emerald"})
    if second_num:
        avg_2 = float(df[second_num].mean())
        kpis.append({"title": f"Average {second_num}", "value": f"{avg_2:,.2f}", "sub": f"Min: {df[second_num].min()} | Max: {df[second_num].max()}", "color": "purple"})
    if first_cat:
        distinct_cats = df[first_cat].nunique()
        kpis.append({"title": f"Unique {first_cat}", "value": f"{distinct_cats:,}", "sub": "Categorical Dimension", "color": "amber"})

    # Dynamic group-by distribution
    by_category = []
    if first_cat and first_num:
        grp = df.groupby(first_cat)[first_num].mean().reset_index().sort_values(by=first_num, ascending=False).head(8)
        for _, r in grp.iterrows():
            by_category.append({"label": str(r[first_cat]), "value": round(float(r[first_num]), 2)})
    elif first_cat:
        vc = df[first_cat].value_counts().head(8).reset_index()
        for _, r in vc.iterrows():
            by_category.append({"label": str(r.iloc[0]), "value": int(r.iloc[1])})

    # Timeline or secondary distribution
    timeline_data = []
    if date_col and first_num:
        try:
            t_df = df.copy()
            t_df["_dt"] = pd.to_datetime(t_df[date_col], errors="coerce")
            t_df = t_df.dropna(subset=["_dt"]).sort_values("_dt")
            t_grp = t_df.groupby(t_df["_dt"].dt.strftime("%Y-%m-%d"))[first_num].mean().reset_index()
            for _, r in t_grp.tail(20).iterrows():
                timeline_data.append({"date": r["_dt"], "value": round(float(r[first_num]), 2)})
        except Exception:
            pass

    return {
        "dataset_type": "generic",
        "kpis": kpis,
        "category_chart": {
            "title": f"Distribution by {first_cat}" if first_cat else "Metric Distribution",
            "data": by_category
        },
        "timeline_chart": {
            "title": f"{first_num} Trajectory Over Time" if (date_col and first_num) else "Distribution",
            "data": timeline_data
        },
        "top_products": [],
        "payment_methods": [],
        "filter_options": {
            "categories": sorted(df[first_cat].dropna().unique().tolist()) if first_cat else [],
            "regions": []
        }
    }


def assistant_ask(dataset_id: str, prompt: str) -> Dict[str, Any]:
    """
    Execute AI Query Copilot grounded in dataset facts.
    Uses AST-verified pandas translation and anomaly discovery.
    """
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found.")

    file_path = Path(meta["storage_path"])
    df = read_file_to_dataframe(file_path, meta["format"])
    intent = classify_user_intent(prompt)

    # 1. Anomaly / Quality Discovery
    if intent == "anomaly_insights":
        insights = discover_dataset_insights(df, meta["name"])
        insight_items = [i.model_dump() for i in insights]
        return {
            "intent": "anomaly_insights",
            "answer": f"Completed anomaly and health audit for **{meta['name']}**. Discovered {len(insight_items)} analytical findings across missing values, distribution skewness, and outlier risks.",
            "code": "# Automated dataset anomaly discovery\ninsights = discover_dataset_insights(df, dataset_name)\nprint(insights)",
            "data": [{"type": i["insight_type"], "severity": i["severity"], "feature": i["column"] or "Global", "title": i["title"], "metric": i["metric_value"]} for i in insight_items[:8]],
            "suggested_chart": "table"
        }

    # 2. Specific questions about sales, revenue, products, anomalies
    p_lower = prompt.lower()

    if any(k in p_lower for k in ["total sales", "total revenue", "overall sales"]):
        sales_col = next((c for c in df.columns if "sales" in c.lower() or "revenue" in c.lower() or "amount" in c.lower()), None)
        if sales_col:
            val = float(df[sales_col].sum())
            return {
                "intent": "nl_query",
                "answer": f"The total sales across all records in **{meta['name']}** is **${val:,.2f}**.",
                "code": f"total_sales = df['{sales_col}'].sum()\nprint(f'Total Sales: ${{total_sales:,.2f}}')",
                "data": [{"Metric": "Total Sales", "Value": f"${val:,.2f}"}, {"Metric": "Record Count", "Value": len(df)}],
                "suggested_chart": "kpi"
            }

    if any(k in p_lower for k in ["highest revenue", "top product", "best selling product"]):
        sales_col = next((c for c in df.columns if "sales" in c.lower() or "revenue" in c.lower()), None)
        prod_col = next((c for c in df.columns if "product" in c.lower() or "item" in c.lower() or "name" in c.lower()), None)
        if sales_col and prod_col:
            grp = df.groupby(prod_col)[sales_col].sum().reset_index().sort_values(by=sales_col, ascending=False)
            top_p = grp.iloc[0]
            return {
                "intent": "nl_query",
                "answer": f"The product with the highest revenue is **{top_p[prod_col]}** generating **${float(top_p[sales_col]):,.2f}**.",
                "code": f"top_product = df.groupby('{prod_col}')['{sales_col}'].sum().idxmax()\nrevenue = df.groupby('{prod_col}')['{sales_col}'].sum().max()",
                "data": df_to_clean_json_records(grp.head(5)),
                "suggested_chart": "bar"
            }

    if any(k in p_lower for k in ["highest region", "top region", "sales by region"]):
        sales_col = next((c for c in df.columns if "sales" in c.lower() or "revenue" in c.lower()), None)
        reg_col = next((c for c in df.columns if "region" in c.lower() or "country" in c.lower()), None)
        if sales_col and reg_col:
            grp = df.groupby(reg_col)[sales_col].sum().reset_index().sort_values(by=sales_col, ascending=False)
            top_r = grp.iloc[0]
            return {
                "intent": "nl_query",
                "answer": f"The region with highest revenue is **{top_r[reg_col]}** with total revenue of **${float(top_r[sales_col]):,.2f}**.",
                "code": f"df.groupby('{reg_col}')['{sales_col}'].sum().sort_values(ascending=False)",
                "data": df_to_clean_json_records(grp),
                "suggested_chart": "bar"
            }

    if any(k in p_lower for k in ["missing", "duplicate", "null", "clean"]):
        nulls = int(df.isna().sum().sum())
        dups = int(df.duplicated().sum())
        null_cols = {c: int(df[c].isna().sum()) for c in df.columns if df[c].isna().sum() > 0}
        return {
            "intent": "quality_query",
            "answer": f"Dataset **{meta['name']}** has **{nulls} total missing values** across {len(null_cols)} columns, and **{dups} duplicate records**.",
            "code": "missing_summary = df.isna().sum()\nduplicates_count = df.duplicated().sum()",
            "data": [{"Feature": c, "Missing_Values": cnt, "Missing_Pct": f"{(cnt/len(df))*100:.1f}%"} for c, cnt in null_cols.items()] or [{"Feature": "All Columns", "Missing_Values": 0, "Missing_Pct": "0.0%"}],
            "suggested_chart": "table"
        }

    # 3. Fallback to general NL-to-Pandas translation
    nl_res = translate_and_execute_nl_query(df, prompt, dataset_id)
    if nl_res:
        return {
            "intent": "nl_query",
            "answer": nl_res.explanation,
            "code": f"# Operation: {nl_res.operation}\n# Query spec: {nl_res.query_spec}\nres = df.groupby(...)\nprint(res)",
            "data": nl_res.data,
            "suggested_chart": nl_res.suggested_chart
        }

    # 4. Global overview fallback
    return {
        "intent": "overview",
        "answer": f"Analyzed **{meta['name']}** ({len(df):,} rows, {len(df.columns)} columns). Available features: {', '.join(df.columns[:8])}.",
        "code": f"df.info()\nprint(df.describe())",
        "data": df_to_clean_json_records(df.head(5)),
        "suggested_chart": "table"
    }


def train_automl_benchmark(dataset_id: str, target_column: str, candidate_models: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Train genuine scikit-learn models, benchmark accuracy/RMSE, rank leaderboard.
    """
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found.")

    file_path = Path(meta["storage_path"])
    df = read_file_to_dataframe(file_path, meta["format"]).dropna(subset=[target_column])

    if len(df) < 10:
        raise ValueError("Dataset has insufficient rows for ML training (< 10 valid rows).")

    is_classification = not pd.api.types.is_numeric_dtype(df[target_column]) or df[target_column].nunique() <= 10
    task_type = "classification" if is_classification else "regression"

    # Feature matrix X
    feature_cols = [c for c in df.columns if c != target_column]
    X_df = df[feature_cols].copy()

    # Numeric imputation and one-hot encoding for categorical
    num_cols = X_df.select_dtypes(include=[np.number]).columns
    for c in num_cols:
        X_df[c] = X_df[c].fillna(X_df[c].median())

    cat_cols = X_df.select_dtypes(exclude=[np.number]).columns
    if len(cat_cols) > 0:
        X_df = pd.get_dummies(X_df, columns=cat_cols, drop_first=True)

    # Convert boolean to float
    X_df = X_df.astype(float)

    # Target y
    y_raw = df[target_column]
    if is_classification:
        from sklearn.preprocessing import LabelEncoder
        le = LabelEncoder()
        y = le.fit_transform(y_raw.astype(str))
    else:
        y = y_raw.values.astype(float)

    X_train, X_test, y_train, y_test = train_test_split(X_df, y, test_size=0.2, random_state=42)

    estimators = get_candidate_estimators(task_type, candidate_models)
    leaderboard = []

    for name, estimator in estimators.items():
        t0 = datetime.now()
        estimator.fit(X_train, y_train)
        y_pred = estimator.predict(X_test)
        duration_ms = int((datetime.now() - t0).total_seconds() * 1000)

        metrics = compute_metrics(task_type, y_test, y_pred)
        primary_metric_val = metrics.get("accuracy" if is_classification else "r2", 0.0)

        leaderboard.append({
            "algorithm": name,
            "task_type": task_type,
            "primary_metric": "Accuracy" if is_classification else "R² Score",
            "primary_metric_value": round(float(primary_metric_val), 4),
            "metrics": metrics,
            "training_time_ms": duration_ms
        })

    # Sort descending by primary metric
    leaderboard.sort(key=lambda x: x["primary_metric_value"], reverse=True)
    champion = leaderboard[0] if leaderboard else None

    return {
        "dataset_id": dataset_id,
        "dataset_name": meta["name"],
        "target_column": target_column,
        "task_type": task_type,
        "features_count": len(X_df.columns),
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "champion_algorithm": champion["algorithm"] if champion else "None",
        "champion_score": champion["primary_metric_value"] if champion else 0.0,
        "leaderboard": leaderboard
    }
