"""Transformation execution pipeline and persistence orchestrator."""

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.user import User
from app.schemas.dataset import ColumnSchema
from app.schemas.transforms import (
    TransformApplyResponse,
    TransformPreviewResponse,
    TransformRecipeRequest,
    TransformStep,
)
from app.services.audit_service import log_audit
from app.services.ingestion.parser import (
    infer_column_schemas,
    read_file_to_dataframe,
    sanitize_records_for_json,
)
from app.services.profiling.profiler import profile_dataframe
from app.services.transforms.operators import OPERATORS_REGISTRY


def execute_recipe(
    df: pd.DataFrame, steps: List[TransformStep]
) -> Tuple[pd.DataFrame, List[str]]:
    """Sequentially apply ordered transformation steps to a DataFrame."""
    current_df = df.copy()
    summaries: List[str] = []

    for idx, step in enumerate(steps, start=1):
        op_func = OPERATORS_REGISTRY.get(step.step_type)
        if not op_func:
            summaries.append(f"Step {idx}: Skipped unknown operator '{step.step_type}'.")
            continue

        try:
            current_df, step_summary = op_func(current_df, step.params)
            summaries.append(f"Step {idx} ({step.step_type}): {step_summary}")
        except Exception as e:
            summaries.append(f"Step {idx} ({step.step_type}) failed: {str(e)}")

    return current_df, summaries


def preview_recipe_execution(
    df: pd.DataFrame, steps: List[TransformStep], sample_size: int = 50
) -> TransformPreviewResponse:
    """Non-destructively simulate recipe execution on sample rows."""
    original_row_count = len(df)
    original_columns = infer_column_schemas(df.head(sample_size))
    preview_before = sanitize_records_for_json(df.head(sample_size).to_dict(orient="records"))

    transformed_df, step_summaries = execute_recipe(df, steps)

    transformed_row_count = len(transformed_df)
    transformed_columns = infer_column_schemas(transformed_df.head(sample_size))
    preview_after = sanitize_records_for_json(
        transformed_df.head(sample_size).to_dict(orient="records")
    )

    rows_affected = abs(original_row_count - transformed_row_count)

    return TransformPreviewResponse(
        original_row_count=original_row_count,
        transformed_row_count=transformed_row_count,
        rows_affected=rows_affected,
        original_columns=original_columns,
        transformed_columns=transformed_columns,
        preview_before=preview_before,
        preview_after=preview_after,
        step_summaries=step_summaries,
    )


def save_transformed_dataframe(
    df: pd.DataFrame,
    format_type: str,
    target_dir: Path,
    stem: str,
) -> Tuple[Path, int, str]:
    """Persist DataFrame to quarantine storage and return (file_path, size_bytes, sha256)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    fmt = format_type.lower()
    if fmt == "parquet":
        filename = f"{stem}_transformed.parquet"
        file_path = target_dir / filename
        df.to_parquet(file_path, index=False)
    elif fmt in ["excel", "xlsx"]:
        filename = f"{stem}_transformed.xlsx"
        file_path = target_dir / filename
        df.to_excel(file_path, index=False)
    elif fmt == "json":
        filename = f"{stem}_transformed.json"
        file_path = target_dir / filename
        df.to_json(file_path, orient="records", indent=2)
    else:  # default csv
        filename = f"{stem}_transformed.csv"
        file_path = target_dir / filename
        df.to_csv(file_path, index=False)

    size_bytes = file_path.stat().st_size

    # Compute SHA-256
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    sha256_hash = hasher.hexdigest()

    return file_path, size_bytes, sha256_hash


async def apply_recipe_and_persist(
    db: AsyncSession,
    dataset_id: str,
    workspace_id: str,
    user: User,
    recipe: TransformRecipeRequest,
    base_dir: str = "data",
) -> Optional[TransformApplyResponse]:
    """Execute recipe, serialize transformed table, and persist dataset / version records."""
    query = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    result = await db.execute(query)
    source_dataset = result.scalar_one_or_none()
    if not source_dataset:
        return None

    source_path = Path(source_dataset.storage_path)
    if not source_path.exists():
        return None

    # Load source DataFrame and execute transformation recipe
    df_raw = read_file_to_dataframe(source_path, source_dataset.format)
    df_transformed, summaries = execute_recipe(df_raw, recipe.steps)

    target_dir = Path(base_dir) / "workspaces" / workspace_id / "raw"
    stem_prefix = uuid.uuid4().hex[:8]

    new_file_path, size_bytes, sha256_hash = save_transformed_dataframe(
        df=df_transformed,
        format_type=source_dataset.format,
        target_dir=target_dir,
        stem=stem_prefix,
    )

    column_schemas = infer_column_schemas(df_transformed.head(50))
    preview_data = sanitize_records_for_json(
        df_transformed.head(50).to_dict(orient="records")
    )
    row_count = len(df_transformed)
    col_count = len(df_transformed.columns)

    if recipe.save_as_new_dataset:
        # Create a new dataset asset
        new_name = recipe.name.strip() if recipe.name and recipe.name.strip() else f"{source_dataset.name} (Transformed)"
        new_desc = recipe.description or f"Cleaned & transformed from '{source_dataset.name}' via {len(recipe.steps)} step(s)."

        target_dataset = Dataset(
            workspace_id=workspace_id,
            name=new_name,
            description=new_desc,
            filename=new_file_path.name,
            storage_path=str(new_file_path),
            format=source_dataset.format,
            size_bytes=size_bytes,
            row_count=row_count,
            column_count=col_count,
            sha256=sha256_hash,
            version=1,
            created_by_id=user.id,
            schema_metadata=json.dumps([c.model_dump() for c in column_schemas]),
            preview_data=json.dumps(preview_data),
            profile_cache=None,
        )
        db.add(target_dataset)
        await db.flush()

        # Compute initial profile
        profile_obj = profile_dataframe(df_transformed, target_dataset.id, target_dataset.name)
        target_dataset.profile_cache = profile_obj.model_dump_json()

        # Initial version 1 snapshot
        v1 = DatasetVersion(
            dataset_id=target_dataset.id,
            version_number=1,
            storage_path=str(new_file_path),
            size_bytes=size_bytes,
            row_count=row_count,
            column_count=col_count,
            sha256=sha256_hash,
            change_summary=f"Transformed from {source_dataset.name} ({len(recipe.steps)} steps applied)",
            created_by_id=user.id,
            profile_json=target_dataset.profile_cache,
        )
        db.add(v1)
        await db.flush()

        await log_audit(
            db,
            action="dataset.transform_create",
            resource_type="dataset",
            resource_id=target_dataset.id,
            details={
                "source_dataset_id": source_dataset.id,
                "steps_applied": len(recipe.steps),
                "row_count": row_count,
                "column_count": col_count,
            },
            user_id=user.id,
            workspace_id=workspace_id,
        )

        return TransformApplyResponse(
            dataset_id=target_dataset.id,
            name=target_dataset.name,
            version=target_dataset.version,
            row_count=target_dataset.row_count,
            column_count=target_dataset.column_count,
            size_bytes=target_dataset.size_bytes,
            format=target_dataset.format,
            steps_applied=len(recipe.steps),
            step_summaries=summaries,
        )

    else:
        # Update existing dataset in-place and create a new version snapshot
        new_version_num = source_dataset.version + 1
        source_dataset.version = new_version_num
        source_dataset.storage_path = str(new_file_path)
        source_dataset.filename = new_file_path.name
        source_dataset.size_bytes = size_bytes
        source_dataset.row_count = row_count
        source_dataset.column_count = col_count
        source_dataset.sha256 = sha256_hash
        source_dataset.schema_metadata = json.dumps([c.model_dump() for c in column_schemas])
        source_dataset.preview_data = json.dumps(preview_data)

        profile_obj = profile_dataframe(df_transformed, source_dataset.id, source_dataset.name)
        source_dataset.profile_cache = profile_obj.model_dump_json()

        change_summary = recipe.description or f"Applied {len(recipe.steps)} transformations"
        version_snap = DatasetVersion(
            dataset_id=source_dataset.id,
            version_number=new_version_num,
            storage_path=str(new_file_path),
            size_bytes=size_bytes,
            row_count=row_count,
            column_count=col_count,
            sha256=sha256_hash,
            change_summary=change_summary,
            created_by_id=user.id,
            profile_json=source_dataset.profile_cache,
        )
        db.add(version_snap)
        await db.flush()

        await log_audit(
            db,
            action="dataset.transform_in_place",
            resource_type="dataset",
            resource_id=source_dataset.id,
            details={
                "version_number": new_version_num,
                "steps_applied": len(recipe.steps),
                "row_count": row_count,
            },
            user_id=user.id,
            workspace_id=workspace_id,
        )

        return TransformApplyResponse(
            dataset_id=source_dataset.id,
            name=source_dataset.name,
            version=source_dataset.version,
            row_count=source_dataset.row_count,
            column_count=source_dataset.column_count,
            size_bytes=source_dataset.size_bytes,
            format=source_dataset.format,
            steps_applied=len(recipe.steps),
            step_summaries=summaries,
        )
