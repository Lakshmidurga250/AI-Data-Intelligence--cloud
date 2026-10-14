"""Dataset ingestion, listing, and inspection API endpoints."""

from typing import List, Optional, Tuple
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace, get_db
from app.models.membership import WorkspaceMembership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.dataset import DatasetDetailRead, DatasetRead
from app.schemas.profiling import DatasetProfileResponse, DatasetVersionCreate, DatasetVersionRead
from app.services.dataset_service import (
    create_dataset_version_snapshot,
    delete_dataset,
    get_dataset_by_id,
    get_dataset_profile,
    get_dataset_versions,
    get_workspace_datasets,
    ingest_dataset,
)

router = APIRouter(prefix="/datasets", tags=["Dataset Ingestion & Catalog"])


@router.post(
    "/upload",
    response_model=DatasetDetailRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(
    file: UploadFile = File(..., description="Tabular file (CSV, Excel, JSON, Parquet)"),
    name: Optional[str] = Form(None, description="Optional custom dataset name"),
    description: Optional[str] = Form(None, description="Optional dataset description"),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetDetailRead:
    """
    Ingest a CSV, Excel (.xlsx), JSON, or Parquet file into the active workspace.
    Performs streaming file quarantine, schema inference, and preview generation.
    """
    workspace, membership = workspace_context

    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot upload datasets to this workspace.",
        )

    return await ingest_dataset(
        db=db,
        upload_file=file,
        workspace_id=workspace.id,
        user=current_user,
        name=name,
        description=description,
    )


@router.get("", response_model=List[DatasetRead])
async def list_datasets(
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> List[DatasetRead]:
    """List all ingested datasets within the active tenant workspace."""
    workspace, _ = workspace_context
    return await get_workspace_datasets(db, workspace.id)


@router.get("/{dataset_id}", response_model=DatasetDetailRead)
async def get_dataset(
    dataset_id: str,
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> DatasetDetailRead:
    """Retrieve detailed metadata, inferred column schemas, and preview rows for a dataset."""
    workspace, _ = workspace_context
    dataset = await get_dataset_by_id(db, dataset_id, workspace.id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in workspace.",
        )
    return dataset


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_dataset(
    dataset_id: str,
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a dataset and delete quarantined storage files. Requires Admin or Owner role."""
    workspace, membership = workspace_context

    if membership.role not in [WorkspaceRole.OWNER.value, WorkspaceRole.ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace Owners and Admins can delete datasets.",
        )

    deleted = await delete_dataset(db, dataset_id, workspace.id, current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in workspace.",
        )


@router.get("/{dataset_id}/profile", response_model=DatasetProfileResponse)
async def get_profile(
    dataset_id: str,
    refresh: bool = False,
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> DatasetProfileResponse:
    """Retrieve statistical profile and correlation scorecard for a dataset."""
    workspace, _ = workspace_context
    profile = await get_dataset_profile(db, dataset_id, workspace.id, refresh=refresh)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for dataset '{dataset_id}' could not be loaded or dataset was not found.",
        )
    return profile


@router.post("/{dataset_id}/profile/refresh", response_model=DatasetProfileResponse)
async def refresh_profile(
    dataset_id: str,
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> DatasetProfileResponse:
    """Force re-computation of dataset statistical metrics and correlation matrix."""
    workspace, _ = workspace_context
    profile = await get_dataset_profile(db, dataset_id, workspace.id, refresh=True)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found or storage file is inaccessible.",
        )
    return profile


@router.get("/{dataset_id}/versions", response_model=List[DatasetVersionRead])
async def list_versions(
    dataset_id: str,
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> List[DatasetVersionRead]:
    """Retrieve all immutable version history snapshots for a dataset."""
    workspace, _ = workspace_context
    versions = await get_dataset_versions(db, dataset_id, workspace.id)
    if versions is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in workspace.",
        )
    return versions


@router.post(
    "/{dataset_id}/versions",
    response_model=DatasetVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    dataset_id: str,
    payload: DatasetVersionCreate,
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetVersionRead:
    """Create a new point-in-time version snapshot for a dataset."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot create version snapshots.",
        )

    version_record = await create_dataset_version_snapshot(
        db,
        dataset_id=dataset_id,
        workspace_id=workspace.id,
        user=current_user,
        change_summary=payload.change_summary,
    )
    if not version_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in workspace.",
        )
    return version_record

