"""FastAPI endpoints for Data Lineage graph exploration and impact analysis."""

from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_workspace,
    get_db,
    require_workspace_role,
)
from app.models.membership import WorkspaceMembership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.lineage import (
    ImpactAnalysisResponse,
    LineageEdgeCreate,
    LineageEdgeRead,
    LineageGraphResponse,
    LineageNodeCreate,
    LineageNodeRead,
)
from app.services.lineage.service import (
    auto_sync_workspace_lineage,
    create_edge_if_not_exists,
    get_impact_analysis,
    get_workspace_lineage_graph,
    register_or_get_node,
)

router = APIRouter()


@router.get(
    "/graph",
    response_model=LineageGraphResponse,
    summary="Get complete lineage graph for current workspace",
)
async def get_lineage_graph(
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> LineageGraphResponse:
    """Retrieve all lineage nodes and edges for the authenticated workspace."""
    workspace, _ = ws_ctx
    return await get_workspace_lineage_graph(db, workspace.id)


@router.post(
    "/sync",
    response_model=Dict[str, int],
    summary="Automatically scan workspace assets and synchronize lineage graph",
)
async def sync_lineage(
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    current_user: User = Depends(get_current_user),
) -> Dict[str, int]:
    """Scan datasets, ETL pipelines, and quality suites to reconstruct end-to-end lineage."""
    workspace, _ = ws_ctx
    return await auto_sync_workspace_lineage(db, workspace.id)


@router.get(
    "/impact/{node_id}",
    response_model=ImpactAnalysisResponse,
    summary="Perform bidirectional root cause and impact analysis for a node",
)
async def analyze_impact(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> ImpactAnalysisResponse:
    """Traverses DAG upstream to find root sources and downstream to find all impacted assets."""
    workspace, _ = ws_ctx
    analysis = await get_impact_analysis(db, workspace.id, node_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lineage node not found in this workspace",
        )
    return analysis


@router.post(
    "/nodes",
    response_model=LineageNodeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Manually register or update a lineage node",
)
async def create_node(
    node_in: LineageNodeCreate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    current_user: User = Depends(get_current_user),
) -> LineageNodeRead:
    """Register custom lineage node."""
    workspace, _ = ws_ctx
    node = await register_or_get_node(
        db,
        workspace_id=workspace.id,
        name=node_in.name,
        node_type=node_in.node_type,
        resource_id=node_in.resource_id,
        metadata_dict=node_in.metadata_json,
    )
    return LineageNodeRead.model_validate(node)


@router.post(
    "/edges",
    response_model=LineageEdgeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Manually connect two lineage nodes with a dependency edge",
)
async def create_edge(
    edge_in: LineageEdgeCreate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    current_user: User = Depends(get_current_user),
) -> LineageEdgeRead:
    """Register custom directed lineage dependency."""
    workspace, _ = ws_ctx
    edge = await create_edge_if_not_exists(
        db,
        workspace_id=workspace.id,
        source_node_id=edge_in.source_node_id,
        target_node_id=edge_in.target_node_id,
        edge_type=edge_in.edge_type,
        column_mappings=edge_in.column_mappings_json,
        summary=edge_in.transformation_summary,
    )
    return LineageEdgeRead.model_validate(edge)
