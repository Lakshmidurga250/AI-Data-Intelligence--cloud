"""Dataset data cleaning, transformation recipes, and preview API endpoints."""

from pathlib import Path
from typing import Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace, get_db
from app.models.dataset import Dataset
from app.models.membership import WorkspaceMembership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.transforms import (
    TransformApplyResponse,
    TransformPreviewRequest,
    TransformPreviewResponse,
    TransformRecipeRequest,
)
from app.services.ingestion.parser import read_file_to_dataframe
from app.services.transforms.engine import (
    apply_recipe_and_persist,
    preview_recipe_execution,
)

router = APIRouter(prefix="/datasets/{dataset_id}/transforms", tags=["Data Cleaning & Transformations"])


@router.post("/preview", response_model=TransformPreviewResponse)
async def preview_transforms(
    dataset_id: str,
    payload: TransformPreviewRequest,
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> TransformPreviewResponse:
    """
    Simulate transformation recipe non-destructively on sample rows.
    Returns before-and-after record previews, schema changes, and step impact summaries.
    """
    workspace, _ = workspace_context

    query = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace.id,
    )
    result = await db.execute(query)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in workspace.",
        )

    file_path = Path(dataset.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Storage file for dataset '{dataset_id}' is inaccessible.",
        )

    try:
        df = read_file_to_dataframe(file_path, dataset.format)
        return preview_recipe_execution(df, payload.steps, payload.sample_size)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate transformation preview: {str(e)}",
        )


@router.post(
    "/apply",
    response_model=TransformApplyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def apply_transforms(
    dataset_id: str,
    payload: TransformRecipeRequest,
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransformApplyResponse:
    """
    Execute transformation recipe, serialize cleaned data, and persist as a new dataset
    or as an immutable version snapshot on the existing dataset.
    """
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot execute dataset transformations.",
        )

    res = await apply_recipe_and_persist(
        db=db,
        dataset_id=dataset_id,
        workspace_id=workspace.id,
        user=current_user,
        recipe=payload,
    )
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in workspace.",
        )
    return res
