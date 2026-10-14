"""FastAPI endpoints for Visual ETL Pipelines management, DAG validation, and execution."""

from typing import List, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_workspace,
    get_db,
)
from app.models.membership import WorkspaceMembership, WorkspaceRole
from app.models.pipeline import Pipeline
from app.models.pipeline_run import PipelineRun
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineGraph,
    PipelineRead,
    PipelineRunResponse,
    PipelineRunSummary,
    PipelineSummary,
    PipelineUpdate,
    PipelineValidationResult,
)
from app.services.audit_service import log_audit
from app.services.pipelines import execute_pipeline, validate_pipeline_dag

router = APIRouter()


@router.get("", response_model=List[PipelineSummary])
async def list_pipelines(
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> List[PipelineSummary]:
    """List all ETL pipelines defined in the active tenant workspace."""
    workspace, _ = workspace_context
    query = (
        select(Pipeline)
        .where(
            Pipeline.workspace_id == workspace.id,
            Pipeline.is_active == True,
        )
        .order_by(Pipeline.updated_at.desc())
    )
    result = await db.execute(query)
    pipelines = result.scalars().all()

    summaries = []
    for p in pipelines:
        graph = p.graph_definition or {}
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        summaries.append(
            PipelineSummary(
                id=p.id,
                workspace_id=p.workspace_id,
                name=p.name,
                description=p.description,
                node_count=len(nodes),
                edge_count=len(edges),
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
        )
    return summaries


@router.post("", response_model=PipelineRead, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    payload: PipelineCreate,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> PipelineRead:
    """Create a new visual ETL pipeline with DAG graph topology."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot modify or execute pipelines.",
        )

    pipeline = Pipeline(
        workspace_id=workspace.id,
        name=payload.name,
        description=payload.description,
        graph_definition=payload.graph_definition.model_dump(),
    )
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)

    await log_audit(
        db=db,
        user_id=current_user.id,
        workspace_id=workspace.id,
        action="pipeline.create",
        resource_type="pipeline",
        resource_id=pipeline.id,
        details={"name": pipeline.name},
    )

    return PipelineRead(
        id=pipeline.id,
        workspace_id=pipeline.workspace_id,
        name=pipeline.name,
        description=pipeline.description,
        graph_definition=PipelineGraph(**pipeline.graph_definition),
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
    )


@router.get("/{pipeline_id}", response_model=PipelineRead)
async def get_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> PipelineRead:
    """Retrieve full pipeline configuration including canvas nodes and edges."""
    workspace, _ = workspace_context
    query = select(Pipeline).where(
        Pipeline.id == pipeline_id,
        Pipeline.workspace_id == workspace.id,
        Pipeline.is_active == True,
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found in this workspace.",
        )

    return PipelineRead(
        id=pipeline.id,
        workspace_id=pipeline.workspace_id,
        name=pipeline.name,
        description=pipeline.description,
        graph_definition=PipelineGraph(**pipeline.graph_definition),
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
    )


@router.put("/{pipeline_id}", response_model=PipelineRead)
async def update_pipeline(
    pipeline_id: str,
    payload: PipelineUpdate,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> PipelineRead:
    """Update pipeline name, metadata, or node graph topology."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot modify or execute pipelines.",
        )

    query = select(Pipeline).where(
        Pipeline.id == pipeline_id,
        Pipeline.workspace_id == workspace.id,
        Pipeline.is_active == True,
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found in this workspace.",
        )

    if payload.name is not None:
        pipeline.name = payload.name
    if payload.description is not None:
        pipeline.description = payload.description
    if payload.graph_definition is not None:
        pipeline.graph_definition = payload.graph_definition.model_dump()

    await db.commit()
    await db.refresh(pipeline)

    return PipelineRead(
        id=pipeline.id,
        workspace_id=pipeline.workspace_id,
        name=pipeline.name,
        description=pipeline.description,
        graph_definition=PipelineGraph(**pipeline.graph_definition),
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
    )


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a pipeline and its execution history."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot modify or execute pipelines.",
        )

    query = select(Pipeline).where(
        Pipeline.id == pipeline_id,
        Pipeline.workspace_id == workspace.id,
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found in this workspace.",
        )

    await db.delete(pipeline)
    await db.commit()

    await log_audit(
        db=db,
        user_id=current_user.id,
        workspace_id=workspace.id,
        action="pipeline.delete",
        resource_type="pipeline",
        resource_id=pipeline_id,
        details={"name": pipeline.name},
    )


@router.post("/{pipeline_id}/validate", response_model=PipelineValidationResult)
async def validate_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> PipelineValidationResult:
    """Perform topological cycle detection and connection integrity checks."""
    workspace, _ = workspace_context
    query = select(Pipeline).where(
        Pipeline.id == pipeline_id,
        Pipeline.workspace_id == workspace.id,
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found in this workspace.",
        )

    graph = PipelineGraph(**pipeline.graph_definition)
    return validate_pipeline_dag(graph)


@router.post("/{pipeline_id}/run", response_model=PipelineRunResponse)
async def run_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> PipelineRunResponse:
    """Trigger execution of an ETL pipeline and capture stage telemetry."""
    workspace, membership = workspace_context
    if membership.role == WorkspaceRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace viewers cannot modify or execute pipelines.",
        )

    query = select(Pipeline).where(
        Pipeline.id == pipeline_id,
        Pipeline.workspace_id == workspace.id,
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found in this workspace.",
        )

    try:
        run_res = await execute_pipeline(
            db=db,
            pipeline=pipeline,
            workspace_id=workspace.id,
            user_id=current_user.id,
        )
        return run_res
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{pipeline_id}/runs", response_model=List[PipelineRunSummary])
async def list_pipeline_runs(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
) -> List[PipelineRunSummary]:
    """Retrieve execution history and status records for a pipeline."""
    workspace, _ = workspace_context
    query = select(Pipeline).where(
        Pipeline.id == pipeline_id,
        Pipeline.workspace_id == workspace.id,
    )
    res = await db.execute(query)
    pipeline = res.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found in this workspace.",
        )

    runs_query = (
        select(PipelineRun)
        .where(
            PipelineRun.pipeline_id == pipeline_id,
            PipelineRun.workspace_id == workspace.id,
        )
        .order_by(PipelineRun.created_at.desc())
    )
    runs_res = await db.execute(runs_query)
    return runs_res.scalars().all()
