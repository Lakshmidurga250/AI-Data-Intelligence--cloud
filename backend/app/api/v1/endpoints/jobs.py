"""FastAPI endpoints for background worker tasks, diagnostics, and job lifecycle."""

from typing import List, Optional, Tuple
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
    JobTaskCreate,
    JobTaskRead,
    JobTaskSummary,
    WorkerDiagnosticsResponse,
)
from app.services.job_service import (
    cancel_job,
    create_and_dispatch_job,
    get_job,
    get_worker_diagnostics,
    list_jobs,
)

router = APIRouter()


@router.get("", response_model=List[JobTaskSummary])
async def list_workspace_jobs(
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> List[JobTaskSummary]:
    """List asynchronous background worker jobs within the active workspace."""
    workspace, _ = workspace_context
    jobs = await list_jobs(
        db=db,
        workspace_id=workspace.id,
        task_type=task_type,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [JobTaskSummary.model_validate(j) for j in jobs]


@router.get("/diagnostics", response_model=WorkerDiagnosticsResponse)
async def worker_diagnostics(
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> WorkerDiagnosticsResponse:
    """Check health, queue telemetry, and Celery broker diagnostics."""
    workspace, _ = workspace_context
    return await get_worker_diagnostics(db=db, workspace_id=workspace.id)


@router.post("", response_model=JobTaskRead, status_code=status.HTTP_201_CREATED)
async def dispatch_job(
    payload: JobTaskCreate,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> JobTaskRead:
    """Dispatch a new asynchronous task to the background worker cluster."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot dispatch background jobs.",
        )

    try:
        job = await create_and_dispatch_job(
            db=db,
            workspace_id=workspace.id,
            task_type=payload.task_type,
            parameters=payload.parameters,
            resource_id=payload.resource_id,
            user_id=current_user.id,
        )
        return JobTaskRead.model_validate(job)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.get("/{job_id}", response_model=JobTaskRead)
async def get_job_details(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> JobTaskRead:
    """Retrieve detailed execution telemetry and result payload for a specific job."""
    workspace, _ = workspace_context
    job = await get_job(db=db, job_id=job_id, workspace_id=workspace.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found in workspace.",
        )
    return JobTaskRead.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobTaskRead)
async def cancel_workspace_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> JobTaskRead:
    """Cancel a pending or running background job."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot cancel jobs.",
        )

    try:
        job = await cancel_job(
            db=db,
            job_id=job_id,
            workspace_id=workspace.id,
            user_id=current_user.id,
        )
        return JobTaskRead.model_validate(job)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
