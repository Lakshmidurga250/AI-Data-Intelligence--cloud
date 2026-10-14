"""Analytics and Dashboard service layer managing dashboards, widgets, and live queries."""

import json
from pathlib import Path
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import Dashboard, DashboardWidget
from app.models.dataset import Dataset
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
    MetricSpec,
    WidgetQueryConfig,
)
from app.services.analytics.engine import execute_analytics_query
from app.services.ingestion.parser import read_file_to_dataframe
from app.services.lineage.service import create_edge_if_not_exists, register_or_get_node


async def list_dashboards(
    db: AsyncSession,
    workspace_id: str,
    skip: int = 0,
    limit: int = 100,
) -> List[DashboardRead]:
    """Retrieve all dashboards scoped to the specified workspace."""
    stmt = (
        select(
            Dashboard,
            func.count(DashboardWidget.id).label("widgets_count"),
        )
        .outerjoin(DashboardWidget, Dashboard.id == DashboardWidget.dashboard_id)
        .where(Dashboard.workspace_id == workspace_id)
        .group_by(Dashboard.id)
        .order_by(Dashboard.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    output = []
    for d, w_count in rows:
        read_obj = DashboardRead(
            id=d.id,
            workspace_id=d.workspace_id,
            name=d.name,
            description=d.description,
            layout_config=d.layout_config,
            is_default=d.is_default,
            widgets_count=w_count,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        output.append(read_obj)
    return output


async def get_dashboard(
    db: AsyncSession,
    workspace_id: str,
    dashboard_id: str,
) -> DashboardDetailRead:
    """Retrieve dashboard with all embedded widgets."""
    stmt = select(Dashboard).where(
        Dashboard.id == dashboard_id,
        Dashboard.workspace_id == workspace_id,
    )
    res = await db.execute(stmt)
    dash = res.scalar_one_or_none()
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard not found or access denied.",
        )

    # Fetch widgets directly to prevent async MissingGreenlet lazy-load error
    w_stmt = (
        select(DashboardWidget)
        .where(DashboardWidget.dashboard_id == dashboard_id)
        .order_by(DashboardWidget.created_at.asc())
    )
    w_res = await db.execute(w_stmt)
    widgets = w_res.scalars().all()

    widget_reads = [
        DashboardWidgetRead(
            id=w.id,
            dashboard_id=w.dashboard_id,
            dataset_id=w.dataset_id,
            name=w.name,
            visualization_type=w.visualization_type,
            query_config=w.query_config,
            position=w.position,
            created_at=w.created_at,
            updated_at=w.updated_at,
        )
        for w in widgets
    ]

    return DashboardDetailRead(
        id=dash.id,
        workspace_id=dash.workspace_id,
        name=dash.name,
        description=dash.description,
        layout_config=dash.layout_config,
        is_default=dash.is_default,
        widgets_count=len(widgets),
        widgets=widget_reads,
        created_at=dash.created_at,
        updated_at=dash.updated_at,
    )


async def create_dashboard(
    db: AsyncSession,
    workspace_id: str,
    payload: DashboardCreate,
) -> DashboardDetailRead:
    """Create a new analytics dashboard in the workspace."""
    layout_str = json.dumps(payload.layout_config) if payload.layout_config else "{}"

    new_dash = Dashboard(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
        layout_config=layout_str,
        is_default=payload.is_default or False,
    )
    db.add(new_dash)
    await db.commit()
    await db.refresh(new_dash)

    return DashboardDetailRead(
        id=new_dash.id,
        workspace_id=new_dash.workspace_id,
        name=new_dash.name,
        description=new_dash.description,
        layout_config=new_dash.layout_config,
        is_default=new_dash.is_default,
        widgets_count=0,
        widgets=[],
        created_at=new_dash.created_at,
        updated_at=new_dash.updated_at,
    )


async def update_dashboard(
    db: AsyncSession,
    workspace_id: str,
    dashboard_id: str,
    payload: DashboardUpdate,
) -> DashboardDetailRead:
    """Update dashboard metadata or canvas layout."""
    stmt = select(Dashboard).where(
        Dashboard.id == dashboard_id,
        Dashboard.workspace_id == workspace_id,
    )
    res = await db.execute(stmt)
    dash = res.scalar_one_or_none()
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard not found or access denied.",
        )

    if payload.name is not None:
        dash.name = payload.name
    if payload.description is not None:
        dash.description = payload.description
    if payload.layout_config is not None:
        dash.layout_config = json.dumps(payload.layout_config)
    if payload.is_default is not None:
        dash.is_default = payload.is_default

    await db.commit()
    return await get_dashboard(db, workspace_id, dashboard_id)


async def delete_dashboard(
    db: AsyncSession,
    workspace_id: str,
    dashboard_id: str,
) -> None:
    """Delete a dashboard and its associated widgets."""
    stmt = select(Dashboard).where(
        Dashboard.id == dashboard_id,
        Dashboard.workspace_id == workspace_id,
    )
    res = await db.execute(stmt)
    dash = res.scalar_one_or_none()
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard not found or access denied.",
        )

    await db.delete(dash)
    await db.commit()


async def create_dashboard_widget(
    db: AsyncSession,
    workspace_id: str,
    dashboard_id: str,
    payload: DashboardWidgetCreate,
) -> DashboardWidgetRead:
    """Add a visualization widget to a dashboard."""
    # Verify dashboard exists
    dash_stmt = select(Dashboard).where(
        Dashboard.id == dashboard_id,
        Dashboard.workspace_id == workspace_id,
    )
    dash_res = await db.execute(dash_stmt)
    if not dash_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard not found or access denied.",
        )

    # Verify dataset if specified
    if payload.dataset_id:
        ds_stmt = select(Dataset).where(
            Dataset.id == payload.dataset_id,
            Dataset.workspace_id == workspace_id,
        )
        ds_res = await db.execute(ds_stmt)
        if not ds_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target dataset '{payload.dataset_id}' not found in workspace.",
            )

    query_config_str = (
        payload.query_config.model_dump_json()
        if isinstance(payload.query_config, WidgetQueryConfig)
        else json.dumps(payload.query_config)
    )
    position_str = json.dumps(
        payload.position.model_dump()
        if hasattr(payload.position, "model_dump")
        else (payload.position or {"x": 0, "y": 0, "w": 6, "h": 4})
    )

    new_widget = DashboardWidget(
        dashboard_id=dashboard_id,
        dataset_id=payload.dataset_id,
        name=payload.name,
        visualization_type=payload.visualization_type,
        query_config=query_config_str,
        position=position_str,
    )
    db.add(new_widget)
    await db.commit()
    await db.refresh(new_widget)

    # Register lineage edge if widget references a dataset
    if payload.dataset_id:
        try:
            ds_node = await register_or_get_node(
                db,
                workspace_id=workspace_id,
                name=f"Dataset {payload.dataset_id[:8]}",
                node_type="dataset",
                resource_id=payload.dataset_id,
            )
            widget_node = await register_or_get_node(
                db,
                workspace_id=workspace_id,
                name=f"Widget: {new_widget.name}",
                node_type="dashboard",
                resource_id=new_widget.id,
            )
            await create_edge_if_not_exists(
                db,
                workspace_id=workspace_id,
                source_node_id=ds_node.id,
                target_node_id=widget_node.id,
                edge_type="transforms_to",
                summary="Visual aggregation widget data source",
            )
        except Exception:
            pass

    return DashboardWidgetRead(
        id=new_widget.id,
        dashboard_id=new_widget.dashboard_id,
        dataset_id=new_widget.dataset_id,
        name=new_widget.name,
        visualization_type=new_widget.visualization_type,
        query_config=new_widget.query_config,
        position=new_widget.position,
        created_at=new_widget.created_at,
        updated_at=new_widget.updated_at,
    )


async def update_dashboard_widget(
    db: AsyncSession,
    workspace_id: str,
    dashboard_id: str,
    widget_id: str,
    payload: DashboardWidgetUpdate,
) -> DashboardWidgetRead:
    """Update widget configuration or canvas layout coordinates."""
    # Verify widget exists
    w_stmt = select(DashboardWidget).join(Dashboard).where(
        DashboardWidget.id == widget_id,
        DashboardWidget.dashboard_id == dashboard_id,
        Dashboard.workspace_id == workspace_id,
    )
    w_res = await db.execute(w_stmt)
    widget = w_res.scalar_one_or_none()
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found in the specified dashboard.",
        )

    if payload.name is not None:
        widget.name = payload.name
    if payload.dataset_id is not None:
        widget.dataset_id = payload.dataset_id
    if payload.visualization_type is not None:
        widget.visualization_type = payload.visualization_type
    if payload.query_config is not None:
        widget.query_config = (
            payload.query_config.model_dump_json()
            if isinstance(payload.query_config, WidgetQueryConfig)
            else json.dumps(payload.query_config)
        )
    if payload.position is not None:
        widget.position = json.dumps(
            payload.position.model_dump()
            if hasattr(payload.position, "model_dump")
            else payload.position
        )

    await db.commit()
    await db.refresh(widget)

    return DashboardWidgetRead(
        id=widget.id,
        dashboard_id=widget.dashboard_id,
        dataset_id=widget.dataset_id,
        name=widget.name,
        visualization_type=widget.visualization_type,
        query_config=widget.query_config,
        position=widget.position,
        created_at=widget.created_at,
        updated_at=widget.updated_at,
    )


async def delete_dashboard_widget(
    db: AsyncSession,
    workspace_id: str,
    dashboard_id: str,
    widget_id: str,
) -> None:
    """Remove a widget from a dashboard."""
    w_stmt = select(DashboardWidget).join(Dashboard).where(
        DashboardWidget.id == widget_id,
        DashboardWidget.dashboard_id == dashboard_id,
        Dashboard.workspace_id == workspace_id,
    )
    w_res = await db.execute(w_stmt)
    widget = w_res.scalar_one_or_none()
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found in the specified dashboard.",
        )

    await db.delete(widget)
    await db.commit()


async def execute_widget_query(
    db: AsyncSession,
    workspace_id: str,
    dashboard_id: str,
    widget_id: str,
) -> AnalyticsQueryResponse:
    """Execute live data query for a specific widget."""
    w_stmt = select(DashboardWidget).join(Dashboard).where(
        DashboardWidget.id == widget_id,
        DashboardWidget.dashboard_id == dashboard_id,
        Dashboard.workspace_id == workspace_id,
    )
    w_res = await db.execute(w_stmt)
    widget = w_res.scalar_one_or_none()
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found in dashboard.",
        )

    if not widget.dataset_id:
        return AnalyticsQueryResponse(
            columns=[],
            data=[],
            row_count=0,
            execution_time_ms=0.0,
        )

    # Load dataset
    ds_stmt = select(Dataset).where(
        Dataset.id == widget.dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    ds_res = await db.execute(ds_stmt)
    dataset = ds_res.scalar_one_or_none()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget references a dataset that no longer exists.",
        )

    # Read dataframe from disk
    file_path = Path(dataset.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset storage file not found.",
        )

    df = read_file_to_dataframe(file_path, dataset.format)

    # Parse query_config
    try:
        q_dict = json.loads(widget.query_config) if isinstance(widget.query_config, str) else widget.query_config
    except Exception:
        q_dict = {}

    metrics = [MetricSpec(**m) for m in q_dict.get("metrics", [])]
    if not metrics:
        metrics = [MetricSpec(column="*", aggregation="count", alias="count")]

    req = AnalyticsQueryRequest(
        dataset_id=widget.dataset_id,
        metrics=metrics,
        dimensions=q_dict.get("dimensions", []),
        filters=q_dict.get("filters", []),
        time_column=q_dict.get("time_column"),
        time_grain=q_dict.get("time_grain"),
        sort_by=q_dict.get("sort_by"),
        sort_order=q_dict.get("sort_order", "desc"),
        limit=q_dict.get("limit", 500),
    )

    return execute_analytics_query(df, req)


async def execute_ad_hoc_analytics_query(
    db: AsyncSession,
    workspace_id: str,
    request: AnalyticsQueryRequest,
) -> AnalyticsQueryResponse:
    """Execute direct ad-hoc analytical query on any workspace dataset."""
    ds_stmt = select(Dataset).where(
        Dataset.id == request.dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    ds_res = await db.execute(ds_stmt)
    dataset = ds_res.scalar_one_or_none()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{request.dataset_id}' not found in workspace.",
        )

    file_path = Path(dataset.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset storage file missing on disk.",
        )

    df = read_file_to_dataframe(file_path, dataset.format)
    return execute_analytics_query(df, request)
