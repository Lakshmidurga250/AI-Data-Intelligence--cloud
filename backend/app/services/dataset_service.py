"""Dataset ingestion orchestration and persistence service."""

import json
from pathlib import Path
from typing import List, Optional
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.user import User
from app.schemas.dataset import ColumnSchema, DatasetDetailRead, DatasetRead
from app.schemas.profiling import DatasetProfileResponse, DatasetVersionRead
from app.services.audit_service import log_audit
from app.services.ingestion.parser import parse_and_profile_tabular_file
from app.services.ingestion.storage import stream_save_upload_file
from app.services.profiling.profiler import profile_dataset_file


async def ingest_dataset(
    db: AsyncSession,
    upload_file: UploadFile,
    workspace_id: str,
    user: User,
    name: Optional[str] = None,
    description: Optional[str] = None,
    base_dir: str = "data",
) -> DatasetDetailRead:
    """
    Orchestrate multi-format upload streaming, schema inference,
    preview extraction, and database persistence within an isolated workspace.
    """
    # 1. Stream file to workspace quarantine directory
    file_path, clean_name, size_bytes, sha256_hash = await stream_save_upload_file(
        upload_file=upload_file,
        workspace_id=workspace_id,
        base_dir=base_dir,
    )

    # 2. Parse file and extract column schemas & preview
    format_type, row_count, column_count, columns, preview_rows = (
        parse_and_profile_tabular_file(
            file_path=file_path,
            filename=clean_name,
            max_preview_rows=50,
        )
    )

    dataset_name = name.strip() if name and name.strip() else clean_name

    # 3. Create Dataset persistence entity
    dataset = Dataset(
        workspace_id=workspace_id,
        name=dataset_name,
        description=description,
        filename=clean_name,
        storage_path=str(file_path),
        format=format_type,
        size_bytes=size_bytes,
        row_count=row_count,
        column_count=column_count,
        sha256=sha256_hash,
        version=1,
        created_by_id=user.id,
        schema_metadata=json.dumps([c.model_dump() for c in columns]),
        preview_data=json.dumps(preview_rows),
        profile_cache=None,
    )
    db.add(dataset)
    await db.flush()

    # 4. Generate statistical profile and initial version 1 snapshot
    profile_json_str = "{}"
    try:
        from app.services.profiling.profiler import profile_dataset_file

        profile_obj = profile_dataset_file(
            file_path=file_path,
            format_type=format_type,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
        )
        profile_json_str = profile_obj.model_dump_json()
        dataset.profile_cache = profile_json_str
    except Exception:
        profile_json_str = "{}"

    from app.models.dataset_version import DatasetVersion

    initial_version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        storage_path=str(file_path),
        size_bytes=size_bytes,
        row_count=row_count,
        column_count=column_count,
        sha256=sha256_hash,
        change_summary="Initial dataset upload",
        created_by_id=user.id,
        profile_json=profile_json_str,
    )
    db.add(initial_version)
    await db.flush()

    # 5. Record audit event
    await log_audit(
        db,
        action="dataset.upload",
        resource_type="dataset",
        resource_id=dataset.id,
        details={
            "filename": clean_name,
            "format": format_type,
            "row_count": row_count,
            "column_count": column_count,
            "size_bytes": size_bytes,
        },
        user_id=user.id,
        workspace_id=workspace_id,
    )

    return DatasetDetailRead(
        id=dataset.id,
        workspace_id=dataset.workspace_id,
        name=dataset.name,
        description=dataset.description,
        filename=dataset.filename,
        format=dataset.format,
        size_bytes=dataset.size_bytes,
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        sha256=dataset.sha256,
        version=dataset.version,
        created_at=dataset.created_at,
        columns=columns,
        preview_rows=preview_rows,
    )


async def get_workspace_datasets(db: AsyncSession, workspace_id: str) -> List[DatasetRead]:
    """Retrieve all datasets belonging to a specific isolated workspace."""
    query = (
        select(Dataset)
        .where(Dataset.workspace_id == workspace_id)
        .order_by(Dataset.created_at.desc())
    )
    result = await db.execute(query)
    datasets = result.scalars().all()

    output: List[DatasetRead] = []
    for d in datasets:
        columns_data = json.loads(d.schema_metadata or "[]")
        columns = [ColumnSchema(**c) for c in columns_data]
        output.append(
            DatasetRead(
                id=d.id,
                workspace_id=d.workspace_id,
                name=d.name,
                description=d.description,
                filename=d.filename,
                format=d.format,
                size_bytes=d.size_bytes,
                row_count=d.row_count,
                column_count=d.column_count,
                sha256=d.sha256,
                version=d.version,
                created_at=d.created_at,
                columns=columns,
            )
        )
    return output


async def get_dataset_by_id(
    db: AsyncSession, dataset_id: str, workspace_id: str
) -> Optional[DatasetDetailRead]:
    """Fetch a single dataset within the authorized workspace tenancy boundary."""
    query = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    result = await db.execute(query)
    d = result.scalar_one_or_none()
    if not d:
        return None

    columns_data = json.loads(d.schema_metadata or "[]")
    columns = [ColumnSchema(**c) for c in columns_data]
    preview_data = json.loads(d.preview_data or "[]")

    return DatasetDetailRead(
        id=d.id,
        workspace_id=d.workspace_id,
        name=d.name,
        description=d.description,
        filename=d.filename,
        format=d.format,
        size_bytes=d.size_bytes,
        row_count=d.row_count,
        column_count=d.column_count,
        sha256=d.sha256,
        version=d.version,
        created_at=d.created_at,
        columns=columns,
        preview_rows=preview_data,
    )


async def delete_dataset(
    db: AsyncSession, dataset_id: str, workspace_id: str, user: User
) -> bool:
    """Delete a dataset and its storage file on disk within the workspace boundary."""
    query = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    result = await db.execute(query)
    d = result.scalar_one_or_none()
    if not d:
        return False

    # Clean up physical file on disk
    file_path = Path(d.storage_path)
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            pass

    await db.delete(d)
    await db.flush()

    await log_audit(
        db,
        action="dataset.delete",
        resource_type="dataset",
        resource_id=dataset_id,
        details={"name": d.name, "filename": d.filename},
        user_id=user.id,
        workspace_id=workspace_id,
    )

    return True


async def get_dataset_profile(
    db: AsyncSession,
    dataset_id: str,
    workspace_id: str,
    refresh: bool = False,
) -> Optional[DatasetProfileResponse]:
    """Retrieve statistical profile from cache or recalculate on demand within workspace boundaries."""
    query = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    result = await db.execute(query)
    dataset = result.scalar_one_or_none()
    if not dataset:
        return None

    if not refresh and dataset.profile_cache and dataset.profile_cache != "{}":
        try:
            return DatasetProfileResponse.model_validate_json(dataset.profile_cache)
        except Exception:
            pass

    # Recalculate profile from file on disk
    file_path = Path(dataset.storage_path)
    if not file_path.exists():
        return None

    profile_obj = profile_dataset_file(
        file_path=file_path,
        format_type=dataset.format,
        dataset_id=dataset.id,
        dataset_name=dataset.name,
    )
    dataset.profile_cache = profile_obj.model_dump_json()
    await db.flush()

    return profile_obj


async def create_dataset_version_snapshot(
    db: AsyncSession,
    dataset_id: str,
    workspace_id: str,
    user: User,
    change_summary: str,
) -> Optional[DatasetVersionRead]:
    """Record an immutable version snapshot reflecting current dataset state."""
    query = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    result = await db.execute(query)
    dataset = result.scalar_one_or_none()
    if not dataset:
        return None

    new_version_number = dataset.version + 1
    dataset.version = new_version_number

    version_record = DatasetVersion(
        dataset_id=dataset.id,
        version_number=new_version_number,
        storage_path=dataset.storage_path,
        size_bytes=dataset.size_bytes,
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        sha256=dataset.sha256,
        change_summary=change_summary,
        created_by_id=user.id,
        profile_json=dataset.profile_cache or "{}",
    )
    db.add(version_record)
    await db.flush()

    await log_audit(
        db,
        action="dataset.version_create",
        resource_type="dataset_version",
        resource_id=version_record.id,
        details={
            "dataset_id": dataset.id,
            "version_number": new_version_number,
            "change_summary": change_summary,
        },
        user_id=user.id,
        workspace_id=workspace_id,
    )

    return DatasetVersionRead.model_validate(version_record)


async def get_dataset_versions(
    db: AsyncSession,
    dataset_id: str,
    workspace_id: str,
) -> Optional[List[DatasetVersionRead]]:
    """Retrieve version history snapshots for a dataset within the workspace."""
    query_dataset = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    result_dataset = await db.execute(query_dataset)
    dataset = result_dataset.scalar_one_or_none()
    if not dataset:
        return None

    query = (
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.version_number.desc())
    )
    result = await db.execute(query)
    versions = result.scalars().all()
    return [DatasetVersionRead.model_validate(v) for v in versions]

