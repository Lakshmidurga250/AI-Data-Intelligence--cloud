"""REST API endpoints for Dashboards, Visualization Widgets, and Analytics queries."""

from typing import List, Tuple
from fastapi import APIRouter, Depends, Query, status
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
from app.schemas.dashboard import (
    AnalyticsQueryRequest,
    AnalyticsQueryResponse,
    DashboardCreate,
    DashboardDetailRead,
    DashboardRead,
    DashboardUpdate,
    DashboardWidgetCreate,
    DashboardWidgetRead,
    DashboardWidgetUpdate,
)
from app.services.analytics.service import (
    create_dashboard,
    create_dashboard_widget,
    delete_dashboard,
    delete_dashboard_widget,
    execute_ad_hoc_analytics_query,
    execute_widget_query,
    get_dashboard,
    list_dashboards,
    update_dashboard,
    update_dashboard_widget,
)

router = APIRouter()


@router.get(
    "",
    response_model=List[DashboardRead],
    summary="List workspace analytics dashboards",
)
async def list_dashboards_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> List[DashboardRead]:
    """Retrieve all dashboards registered within the active workspace."""
    workspace, _ = ws_ctx
    return await list_dashboards(db, workspace.id, skip=skip, limit=limit)


@router.post(
    "",
    response_model=DashboardDetailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create new analytics dashboard",
)
async def create_dashboard_endpoint(
    payload: DashboardCreate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
) -> DashboardDetailRead:
    """Register a new interactive dashboard."""
    workspace, _ = ws_ctx
    return await create_dashboard(db, workspace.id, payload)


@router.get(
    "/{dashboard_id}",
    response_model=DashboardDetailRead,
    summary="Get dashboard details with widgets",
)
async def get_dashboard_endpoint(
    dashboard_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> DashboardDetailRead:
    """Retrieve detailed dashboard configuration and all placed widgets."""
    workspace, _ = ws_ctx
    return await get_dashboard(db, workspace.id, dashboard_id)


@router.put(
    "/{dashboard_id}",
    response_model=DashboardDetailRead,
    summary="Update dashboard metadata or canvas layout",
)
async def update_dashboard_endpoint(
    dashboard_id: str,
    payload: DashboardUpdate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
) -> DashboardDetailRead:
    """Update title, description, or canvas grid layout for a dashboard."""
    workspace, _ = ws_ctx
    return await update_dashboard(db, workspace.id, dashboard_id, payload)


@router.delete(
    "/{dashboard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete dashboard",
)
async def delete_dashboard_endpoint(
    dashboard_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
    ),
) -> None:
    """Delete a dashboard and all placed widgets."""
    workspace, _ = ws_ctx
    await delete_dashboard(db, workspace.id, dashboard_id)


@router.post(
    "/{dashboard_id}/widgets",
    response_model=DashboardWidgetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add widget to dashboard",
)
async def create_widget_endpoint(
    dashboard_id: str,
    payload: DashboardWidgetCreate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
) -> DashboardWidgetRead:
    """Add a visualization widget to a dashboard."""
    workspace, _ = ws_ctx
    return await create_dashboard_widget(db, workspace.id, dashboard_id, payload)


@router.put(
    "/{dashboard_id}/widgets/{widget_id}",
    response_model=DashboardWidgetRead,
    summary="Update widget configuration or layout position",
)
async def update_widget_endpoint(
    dashboard_id: str,
    widget_id: str,
    payload: DashboardWidgetUpdate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
) -> DashboardWidgetRead:
    """Update a widget's query parameters, visualization type, or canvas position."""
    workspace, _ = ws_ctx
    return await update_dashboard_widget(db, workspace.id, dashboard_id, widget_id, payload)


@router.delete(
    "/{dashboard_id}/widgets/{widget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove widget from dashboard",
)
async def delete_widget_endpoint(
    dashboard_id: str,
    widget_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
) -> None:
    """Remove a widget from a dashboard."""
    workspace, _ = ws_ctx
    await delete_dashboard_widget(db, workspace.id, dashboard_id, widget_id)


@router.post(
    "/{dashboard_id}/widgets/{widget_id}/query",
    response_model=AnalyticsQueryResponse,
    summary="Execute live query for a dashboard widget",
)
async def execute_widget_query_endpoint(
    dashboard_id: str,
    widget_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> AnalyticsQueryResponse:
    """Execute live aggregated data retrieval for a specific widget."""
    workspace, _ = ws_ctx
    return await execute_widget_query(db, workspace.id, dashboard_id, widget_id)


@router.post(
    "/query",
    response_model=AnalyticsQueryResponse,
    summary="Execute ad-hoc analytics aggregation query",
)
async def execute_ad_hoc_query_endpoint(
    payload: AnalyticsQueryRequest,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> AnalyticsQueryResponse:
    """Execute an ad-hoc grouping and aggregation query across any workspace dataset."""
    workspace, _ = ws_ctx
    return await execute_ad_hoc_analytics_query(db, workspace.id, payload)
