"""Data Lineage Graph Construction, Provenance Traversal, and Impact Analysis Service."""

import json
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.lineage import LineageEdge, LineageNode
from app.models.pipeline import Pipeline
from app.models.quality import QualityRuleSuite
from app.schemas.lineage import (
    ImpactAnalysisResponse,
    LineageEdgeRead,
    LineageGraphResponse,
    LineageNodeRead,
)


async def register_or_get_node(
    db: AsyncSession,
    workspace_id: str,
    name: str,
    node_type: str,
    resource_id: Optional[str] = None,
    metadata_dict: Optional[Dict[str, Any]] = None,
) -> LineageNode:
    """Register a new lineage node or retrieve an existing one matching the resource/name."""
    query = select(LineageNode).where(
        LineageNode.workspace_id == workspace_id,
        LineageNode.node_type == node_type,
    )
    if resource_id:
        query = query.where(LineageNode.resource_id == resource_id)
    else:
        query = query.where(LineageNode.name == name)

    result = await db.execute(query)
    node = result.scalars().first()

    metadata_str = json.dumps(metadata_dict) if metadata_dict else None

    if not node:
        node = LineageNode(
            workspace_id=workspace_id,
            name=name,
            node_type=node_type,
            resource_id=resource_id,
            metadata_json=metadata_str,
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)
    elif metadata_str and node.metadata_json != metadata_str:
        node.metadata_json = metadata_str
        node.name = name
        await db.commit()
        await db.refresh(node)

    return node


async def create_edge_if_not_exists(
    db: AsyncSession,
    workspace_id: str,
    source_node_id: str,
    target_node_id: str,
    edge_type: str = "data_flow",
    column_mappings: Optional[List[Dict[str, str]]] = None,
    summary: Optional[str] = None,
) -> LineageEdge:
    """Create a directed lineage edge if it does not already exist."""
    query = select(LineageEdge).where(
        LineageEdge.workspace_id == workspace_id,
        LineageEdge.source_node_id == source_node_id,
        LineageEdge.target_node_id == target_node_id,
    )
    result = await db.execute(query)
    edge = result.scalars().first()

    if not edge:
        edge = LineageEdge(
            workspace_id=workspace_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_type=edge_type,
            column_mappings_json=json.dumps(column_mappings) if column_mappings else None,
            transformation_summary=summary,
        )
        db.add(edge)
        await db.commit()
        await db.refresh(edge)

    return edge


async def get_workspace_lineage_graph(
    db: AsyncSession,
    workspace_id: str,
) -> LineageGraphResponse:
    """Retrieve all lineage nodes and edges for a workspace with root/leaf diagnostics."""
    nodes_query = select(LineageNode).where(LineageNode.workspace_id == workspace_id)
    nodes_res = await db.execute(nodes_query)
    nodes = list(nodes_res.scalars().all())

    edges_query = select(LineageEdge).where(LineageEdge.workspace_id == workspace_id)
    edges_res = await db.execute(edges_query)
    edges = list(edges_res.scalars().all())

    incoming_counts: Dict[str, int] = {node.id: 0 for node in nodes}
    outgoing_counts: Dict[str, int] = {node.id: 0 for node in nodes}

    for edge in edges:
        if edge.target_node_id in incoming_counts:
            incoming_counts[edge.target_node_id] += 1
        if edge.source_node_id in outgoing_counts:
            outgoing_counts[edge.source_node_id] += 1

    root_count = sum(1 for node_id, count in incoming_counts.items() if count == 0)
    leaf_count = sum(1 for node_id, count in outgoing_counts.items() if count == 0)

    return LineageGraphResponse(
        nodes=[LineageNodeRead.model_validate(n) for n in nodes],
        edges=[LineageEdgeRead.model_validate(e) for e in edges],
        root_node_count=root_count,
        leaf_node_count=leaf_count,
    )


async def get_impact_analysis(
    db: AsyncSession,
    workspace_id: str,
    node_id: str,
) -> Optional[ImpactAnalysisResponse]:
    """Perform bidirectional traversal to identify upstream root sources and downstream impact."""
    node_query = select(LineageNode).where(
        LineageNode.workspace_id == workspace_id,
        LineageNode.id == node_id,
    )
    node_res = await db.execute(node_query)
    target_node = node_res.scalars().first()
    if not target_node:
        return None

    # Load all edges for workspace
    edges_query = select(LineageEdge).where(LineageEdge.workspace_id == workspace_id)
    edges_res = await db.execute(edges_query)
    all_edges = list(edges_res.scalars().all())

    # Build adjacency lists
    downstream_adj: Dict[str, List[str]] = {}
    upstream_adj: Dict[str, List[str]] = {}
    for edge in all_edges:
        downstream_adj.setdefault(edge.source_node_id, []).append(edge.target_node_id)
        upstream_adj.setdefault(edge.target_node_id, []).append(edge.source_node_id)

    # BFS Downstream (Impacted dependents)
    downstream_ids: Set[str] = set()
    queue = deque([node_id])
    while queue:
        curr = queue.popleft()
        for nxt in downstream_adj.get(curr, []):
            if nxt not in downstream_ids and nxt != node_id:
                downstream_ids.add(nxt)
                queue.append(nxt)

    # BFS Upstream (Root ancestors)
    upstream_ids: Set[str] = set()
    queue = deque([node_id])
    while queue:
        curr = queue.popleft()
        for prev in upstream_adj.get(curr, []):
            if prev not in upstream_ids and prev != node_id:
                upstream_ids.add(prev)
                queue.append(prev)

    all_node_ids = downstream_ids.union(upstream_ids)
    node_map: Dict[str, LineageNode] = {}
    if all_node_ids:
        nodes_q = select(LineageNode).where(LineageNode.id.in_(all_node_ids))
        res = await db.execute(nodes_q)
        for n in res.scalars().all():
            node_map[n.id] = n

    upstream_nodes = [
        LineageNodeRead.model_validate(node_map[uid])
        for uid in upstream_ids
        if uid in node_map
    ]
    downstream_nodes = [
        LineageNodeRead.model_validate(node_map[did])
        for did in downstream_ids
        if did in node_map
    ]

    pipeline_count = sum(1 for n in downstream_nodes if n.node_type == "pipeline")
    dataset_count = sum(1 for n in downstream_nodes if n.node_type == "dataset")
    quality_count = sum(1 for n in downstream_nodes if n.node_type == "quality_suite")

    return ImpactAnalysisResponse(
        target_node=LineageNodeRead.model_validate(target_node),
        upstream_ancestors=upstream_nodes,
        downstream_dependents=downstream_nodes,
        total_impacted_pipelines=pipeline_count,
        total_impacted_datasets=dataset_count,
        total_impacted_quality_suites=quality_count,
    )


async def auto_sync_workspace_lineage(
    db: AsyncSession,
    workspace_id: str,
) -> Dict[str, int]:
    """Inspects all datasets, pipelines, and quality suites in workspace and syncs lineage graph."""
    # 1. Sync Datasets
    ds_query = select(Dataset).where(Dataset.workspace_id == workspace_id)
    ds_res = await db.execute(ds_query)
    datasets = list(ds_res.scalars().all())

    created_nodes = 0
    created_edges = 0

    dataset_node_map: Dict[str, LineageNode] = {}
    for ds in datasets:
        # Ingestion source node
        src_name = f"Raw Ingestion ({ds.format.upper()})"
        src_node = await register_or_get_node(
            db,
            workspace_id,
            name=src_name,
            node_type="external_source",
            resource_id=None,
            metadata_dict={"format": ds.format, "source": ds.filename},
        )
        ds_node = await register_or_get_node(
            db,
            workspace_id,
            name=ds.name,
            node_type="dataset",
            resource_id=ds.id,
            metadata_dict={"row_count": ds.row_count, "format": ds.format},
        )
        dataset_node_map[ds.id] = ds_node

        # Edge from ingestion to dataset
        await create_edge_if_not_exists(
            db,
            workspace_id,
            source_node_id=src_node.id,
            target_node_id=ds_node.id,
            edge_type="data_flow",
            summary=f"Streamed ingestion of {ds.filename}",
        )

    # 2. Sync Pipelines
    pipe_query = select(Pipeline).where(Pipeline.workspace_id == workspace_id)
    pipe_res = await db.execute(pipe_query)
    pipelines = list(pipe_res.scalars().all())

    for pipe in pipelines:
        pipe_node = await register_or_get_node(
            db,
            workspace_id,
            name=pipe.name,
            node_type="pipeline",
            resource_id=pipe.id,
            metadata_dict={"description": pipe.description},
        )
        # Parse graph definition to link input datasets and sink datasets
        if pipe.graph_definition:
            try:
                g_def = (
                    json.loads(pipe.graph_definition)
                    if isinstance(pipe.graph_definition, str)
                    else pipe.graph_definition
                )
                nodes = g_def.get("nodes", [])
                for n in nodes:
                    config = n.get("configuration", {}) or {}
                    ntype = n.get("type")
                    if ntype == "source":
                        src_ds_id = config.get("dataset_id")
                        if src_ds_id and src_ds_id in dataset_node_map:
                            await create_edge_if_not_exists(
                                db,
                                workspace_id,
                                source_node_id=dataset_node_map[src_ds_id].id,
                                target_node_id=pipe_node.id,
                                edge_type="pipeline_execution",
                                summary=f"Source input: {n.get('name')}",
                            )
                    elif ntype == "sink":
                        sink_ds_name = config.get("target_dataset_name")
                        # Find if dataset exists
                        for ds_id, d_node in dataset_node_map.items():
                            if d_node.name == sink_ds_name or d_node.resource_id == ds_id:
                                await create_edge_if_not_exists(
                                    db,
                                    workspace_id,
                                    source_node_id=pipe_node.id,
                                    target_node_id=d_node.id,
                                    edge_type="data_flow",
                                    summary=f"Materialized sink output: {sink_ds_name}",
                                )
            except Exception:
                pass

    # 3. Sync Quality Suites
    qs_query = (
        select(QualityRuleSuite)
        .options(selectinload(QualityRuleSuite.rules))
        .where(QualityRuleSuite.workspace_id == workspace_id)
    )
    qs_res = await db.execute(qs_query)
    suites = list(qs_res.scalars().all())

    for suite in suites:
        qs_node = await register_or_get_node(
            db,
            workspace_id,
            name=f"Quality: {suite.name}",
            node_type="quality_suite",
            resource_id=suite.id,
            metadata_dict={"rules_count": len(suite.rules) if suite.rules else 0},
        )
        if suite.dataset_id and suite.dataset_id in dataset_node_map:
            await create_edge_if_not_exists(
                db,
                workspace_id,
                source_node_id=dataset_node_map[suite.dataset_id].id,
                target_node_id=qs_node.id,
                edge_type="validation",
                summary=f"Contract validation suite: {suite.name}",
            )

    graph = await get_workspace_lineage_graph(db, workspace_id)
    return {
        "total_nodes": len(graph.nodes),
        "total_edges": len(graph.edges),
        "root_nodes": graph.root_node_count,
        "leaf_nodes": graph.leaf_node_count,
    }
