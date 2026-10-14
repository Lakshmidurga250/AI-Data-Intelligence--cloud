"""FastAPI endpoints for recurring ETL pipeline schedule management."""

from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_workspace,
    get_db,
)
from app.models.membership import WorkspaceMembership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.job import (
    JobScheduleCreate,
    JobScheduleRead,
    JobScheduleUpdate,
    JobTaskSummary,
)
from app.services.schedule_service import (
    create_schedule,
    delete_schedule,
    evaluate_and_trigger_schedules,
    get_schedule,
    list_schedules,
    update_schedule,
)

router = APIRouter()


@router.get("", response_model=List[JobScheduleRead])
async def list_workspace_schedules(
    is_active: Optional[bool] = Query(None, description="Filter active/inactive schedules"),
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> List[JobScheduleRead]:
    """List all recurring pipeline execution schedules configured in the workspace."""
    workspace, _ = workspace_context
    schedules = await list_schedules(db=db, workspace_id=workspace.id, is_active=is_active)
    return [JobScheduleRead.model_validate(s) for s in schedules]


@router.post("/trigger-due", response_model=List[JobTaskSummary])
async def trigger_due_schedules(
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> List[JobTaskSummary]:
    """Evaluate and trigger all schedules that are currently due for execution."""
    _, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot trigger scheduled jobs.",
        )

    dispatched = await evaluate_and_trigger_schedules(db=db)
    return [JobTaskSummary.model_validate(j) for j in dispatched]


@router.post("", response_model=JobScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_pipeline_schedule(
    payload: JobScheduleCreate,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> JobScheduleRead:
    """Register a new recurring cron or interval execution schedule for a pipeline."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot configure pipeline schedules.",
        )

    try:
        schedule = await create_schedule(
            db=db,
            workspace_id=workspace.id,
            data=payload,
            user_id=current_user.id,
        )
        return JobScheduleRead.model_validate(schedule)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.get("/{schedule_id}", response_model=JobScheduleRead)
async def get_schedule_details(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> JobScheduleRead:
    """Retrieve details for a specific schedule."""
    workspace, _ = workspace_context
    schedule = await get_schedule(db=db, schedule_id=schedule_id, workspace_id=workspace.id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found in workspace.",
        )
    return JobScheduleRead.model_validate(schedule)


@router.put("/{schedule_id}", response_model=JobScheduleRead)
async def update_pipeline_schedule(
    schedule_id: str,
    payload: JobScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> JobScheduleRead:
    """Update recurring schedule configuration or active state."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot update schedules.",
        )

    try:
        updated = await update_schedule(
            db=db,
            schedule_id=schedule_id,
            workspace_id=workspace.id,
            data=payload,
            user_id=current_user.id,
        )
        return JobScheduleRead.model_validate(updated)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.delete("/{schedule_id}", response_model=Dict[str, Any])
async def delete_pipeline_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete a recurring schedule configuration."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot delete schedules.",
        )

    try:
        await delete_schedule(
            db=db,
            schedule_id=schedule_id,
            workspace_id=workspace.id,
            user_id=current_user.id,
        )
        return {"status": "deleted", "id": schedule_id}
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
