"""Pipeline DAG execution engine with stage telemetry and multi-operator evaluation."""

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.pipeline import Pipeline
from app.models.pipeline_run import PipelineRun
from app.schemas.pipeline import (
    PipelineGraph,
    PipelineNode,
    PipelineRunResponse,
    PipelineStageResult,
)
from app.schemas.transforms import TransformStep
from app.services.audit_service import log_audit
from app.services.ingestion.parser import (
    infer_column_schemas,
    read_file_to_dataframe,
    sanitize_records_for_json,
)

from app.services.profiling.profiler import profile_dataframe
from app.services.transforms.engine import execute_recipe, save_transformed_dataframe
from app.services.transforms.operators import op_filter_rows
from app.services.pipelines.validator import validate_pipeline_dag


async def execute_pipeline(
    db: AsyncSession,
    pipeline: Pipeline,
    workspace_id: str,
    user_id: Optional[str] = None,
    base_dir: str = "data",
) -> PipelineRunResponse:
    """Execute pipeline DAG stages, stream node outputs, and record execution history."""
    graph = PipelineGraph(**pipeline.graph_definition)
    val_res = validate_pipeline_dag(graph)

    if not val_res.is_valid:
        error_msg = f"Pipeline validation failed: {'; '.join(val_res.errors)}"
        raise ValueError(error_msg)

    # Initialize PipelineRun record
    run_record = PipelineRun(
        pipeline_id=pipeline.id,
        workspace_id=workspace_id,
        status="running",
        triggered_by=user_id,
        started_at=datetime.now(timezone.utc),
        stage_results=[],
    )
    db.add(run_record)
    await db.flush()

    start_timestamp = time.time()
    nodes_by_id: Dict[str, PipelineNode] = {n.id: n for n in graph.nodes}
    incoming_edges = defaultdict(list)
    for edge in graph.edges:
        incoming_edges[edge.target].append(edge)

    node_outputs: Dict[str, pd.DataFrame] = {}
    stage_results: List[PipelineStageResult] = []
    output_dataset_id: Optional[str] = None
    output_dataset_name: Optional[str] = None

    try:
        for node_id in val_res.execution_order:
            node = nodes_by_id[node_id]
            t_node_start = time.time()
            cfg = node.config or {}

            if node.type == "source":
                # 1. Source Node: load dataset
                ds_id = cfg.get("dataset_id")
                q = select(Dataset).where(
                    Dataset.id == ds_id,
                    Dataset.workspace_id == workspace_id,
                )
                res = await db.execute(q)
                source_ds = res.scalar_one_or_none()
                if not source_ds:
                    raise ValueError(f"Source dataset with ID '{ds_id}' not found in workspace.")

                df = read_file_to_dataframe(Path(source_ds.storage_path), source_ds.format)
                node_outputs[node.id] = df
                duration_ms = int((time.time() - t_node_start) * 1000)

                stage_results.append(
                    PipelineStageResult(
                        node_id=node.id,
                        node_type="source",
                        label=node.label or f"Source ({source_ds.name})",
                        status="completed",
                        rows_in=0,
                        rows_out=len(df),
                        columns_out=list(df.columns),
                        duration_ms=duration_ms,
                        summary=f"Loaded {len(df):,} rows from '{source_ds.name}'.",
                    )
                )

            elif node.type == "transform":
                # 2. Transform Node: chain operators
                edges = incoming_edges[node.id]
                parent_df = node_outputs[edges[0].source]
                raw_steps = cfg.get("steps", [])
                steps = [
                    TransformStep(**s) if isinstance(s, dict) else s
                    for s in raw_steps
                ]

                transformed_df, step_summaries = execute_recipe(parent_df, steps)
                node_outputs[node.id] = transformed_df
                duration_ms = int((time.time() - t_node_start) * 1000)

                stage_results.append(
                    PipelineStageResult(
                        node_id=node.id,
                        node_type="transform",
                        label=node.label or "Transform Recipe",
                        status="completed",
                        rows_in=len(parent_df),
                        rows_out=len(transformed_df),
                        columns_out=list(transformed_df.columns),
                        duration_ms=duration_ms,
                        summary=f"Applied {len(steps)} operators ({'; '.join(step_summaries[:2])}).",
                    )
                )

            elif node.type == "filter":
                # 3. Filter Node: conditional row filtering
                edges = incoming_edges[node.id]
                parent_df = node_outputs[edges[0].source]
                filtered_df, filter_summary = op_filter_rows(parent_df, cfg)
                node_outputs[node.id] = filtered_df
                duration_ms = int((time.time() - t_node_start) * 1000)

                stage_results.append(
                    PipelineStageResult(
                        node_id=node.id,
                        node_type="filter",
                        label=node.label or "Conditional Filter",
                        status="completed",
                        rows_in=len(parent_df),
                        rows_out=len(filtered_df),
                        columns_out=list(filtered_df.columns),
                        duration_ms=duration_ms,
                        summary=filter_summary,
                    )
                )

            elif node.type == "aggregate":
                # 4. Aggregate Node: groupby and summaries
                edges = incoming_edges[node.id]
                parent_df = node_outputs[edges[0].source]
                group_by = cfg.get("group_by", [])
                if isinstance(group_by, str):
                    group_by = [group_by]
                valid_group_by = [c for c in group_by if c in parent_df.columns]

                aggregations = cfg.get("aggregations", {})
                if not isinstance(aggregations, dict):
                    aggregations = {}

                # Clean aggregations for existing columns
                valid_aggs = {
                    col: fn
                    for col, fn in aggregations.items()
                    if col in parent_df.columns
                }

                if valid_group_by and valid_aggs:
                    agg_df = parent_df.groupby(valid_group_by, as_index=False).agg(valid_aggs)
                    # Flatten potential tuple columns
                    agg_df.columns = [
                        f"{c[0]}_{c[1]}" if isinstance(c, tuple) and c[1] else (c[0] if isinstance(c, tuple) else c)
                        for c in agg_df.columns
                    ]
                elif valid_group_by:
                    agg_df = parent_df.groupby(valid_group_by, as_index=False).size()
                else:
                    agg_df = parent_df

                node_outputs[node.id] = agg_df
                duration_ms = int((time.time() - t_node_start) * 1000)

                stage_results.append(
                    PipelineStageResult(
                        node_id=node.id,
                        node_type="aggregate",
                        label=node.label or "Aggregations",
                        status="completed",
                        rows_in=len(parent_df),
                        rows_out=len(agg_df),
                        columns_out=list(agg_df.columns),
                        duration_ms=duration_ms,
                        summary=f"Grouped {len(parent_df):,} rows into {len(agg_df):,} groups on {valid_group_by}.",
                    )
                )

            elif node.type == "join":
                # 5. Join Node: multi-stream merging
                edges = incoming_edges[node.id]
                if len(edges) != 2:
                    raise ValueError(f"Join node '{node.id}' expects exactly 2 incoming streams.")

                # Determine left and right sources
                edge_left = next((e for e in edges if e.target_handle == "left"), edges[0])
                edge_right = next((e for e in edges if e.target_handle == "right"), edges[1])

                left_df = node_outputs[edge_left.source]
                right_df = node_outputs[edge_right.source]
                how = cfg.get("how", "inner").lower()
                on = cfg.get("on")
                left_on = cfg.get("left_on")
                right_on = cfg.get("right_on")

                if on and isinstance(on, str):
                    on = [on]
                if left_on and isinstance(left_on, str):
                    left_on = [left_on]
                if right_on and isinstance(right_on, str):
                    right_on = [right_on]

                joined_df = pd.merge(
                    left_df,
                    right_df,
                    how=how,
                    on=on,
                    left_on=left_on,
                    right_on=right_on,
                    suffixes=("_left", "_right"),
                )
                node_outputs[node.id] = joined_df
                duration_ms = int((time.time() - t_node_start) * 1000)

                stage_results.append(
                    PipelineStageResult(
                        node_id=node.id,
                        node_type="join",
                        label=node.label or f"Join ({how.upper()})",
                        status="completed",
                        rows_in=len(left_df) + len(right_df),
                        rows_out=len(joined_df),
                        columns_out=list(joined_df.columns),
                        duration_ms=duration_ms,
                        summary=f"Joined {len(left_df):,} and {len(right_df):,} rows via {how.upper()} join into {len(joined_df):,} rows.",
                    )
                )

            elif node.type == "sink":
                # 6. Sink Node: persist final DataFrame to quarantine storage & catalog
                edges = incoming_edges[node.id]
                parent_df = node_outputs[edges[0].source]
                out_name = cfg.get("output_name") or f"{pipeline.name} Output"
                fmt = cfg.get("format", "parquet").lower()
                target_dir = Path(base_dir) / "workspaces" / workspace_id / "raw"
                stem = f"pipeline_{pipeline.id[:8]}_{int(time.time())}"

                file_path, size_bytes, sha256_hash = save_transformed_dataframe(
                    parent_df,
                    fmt,
                    target_dir,
                    stem,
                )

                cols_schema = infer_column_schemas(parent_df)
                preview_records = sanitize_records_for_json(
                    parent_df.head(50).to_dict(orient="records")
                )

                new_dataset = Dataset(
                    workspace_id=workspace_id,
                    name=out_name,
                    description=cfg.get("description")
                    or f"Materialized by Visual ETL Pipeline '{pipeline.name}'",
                    filename=file_path.name,
                    storage_path=str(file_path),
                    format=fmt,
                    size_bytes=size_bytes,
                    row_count=len(parent_df),
                    column_count=len(parent_df.columns),
                    sha256=sha256_hash,
                    version=1,
                    created_by_id=user_id,
                    schema_metadata=json.dumps([c.model_dump() for c in cols_schema]),
                    preview_data=json.dumps(preview_records),
                    profile_cache=None,
                )
                db.add(new_dataset)
                await db.flush()

                profile_obj = profile_dataframe(parent_df, new_dataset.id, new_dataset.name)
                new_dataset.profile_cache = profile_obj.model_dump_json()

                # Add initial version snapshot
                version_entry = DatasetVersion(
                    dataset_id=new_dataset.id,
                    version_number=1,
                    storage_path=str(file_path),
                    size_bytes=size_bytes,
                    row_count=len(parent_df),
                    column_count=len(parent_df.columns),
                    sha256=sha256_hash,
                    change_summary=f"Initial pipeline output from '{pipeline.name}'",
                    created_by_id=user_id,
                    profile_json=new_dataset.profile_cache,
                )
                db.add(version_entry)
                await db.flush()


                await log_audit(
                    db=db,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    action="pipeline.materialize",
                    resource_type="dataset",
                    resource_id=new_dataset.id,
                    details={
                        "pipeline_id": pipeline.id,
                        "pipeline_name": pipeline.name,
                        "row_count": len(parent_df),
                    },
                )

                output_dataset_id = new_dataset.id
                output_dataset_name = new_dataset.name
                duration_ms = int((time.time() - t_node_start) * 1000)

                stage_results.append(
                    PipelineStageResult(
                        node_id=node.id,
                        node_type="sink",
                        label=node.label or f"Sink ({out_name})",
                        status="completed",
                        rows_in=len(parent_df),
                        rows_out=len(parent_df),
                        columns_out=list(parent_df.columns),
                        duration_ms=duration_ms,
                        summary=f"Materialized {len(parent_df):,} rows as new dataset '{out_name}'.",
                    )
                )

        # Mark Run Completed
        total_time_ms = int((time.time() - start_timestamp) * 1000)
        run_record.status = "completed"
        run_record.completed_at = datetime.now(timezone.utc)
        run_record.execution_time_ms = total_time_ms
        run_record.output_dataset_id = output_dataset_id
        run_record.stage_results = [s.model_dump() for s in stage_results]
        await db.commit()

        return PipelineRunResponse(
            run_id=run_record.id,
            pipeline_id=pipeline.id,
            workspace_id=workspace_id,
            status="completed",
            started_at=run_record.started_at,
            completed_at=run_record.completed_at,
            execution_time_ms=total_time_ms,
            output_dataset_id=output_dataset_id,
            output_dataset_name=output_dataset_name,
            stage_results=stage_results,
        )

    except Exception as exc:
        total_time_ms = int((time.time() - start_timestamp) * 1000)
        run_record.status = "failed"
        run_record.completed_at = datetime.now(timezone.utc)
        run_record.execution_time_ms = total_time_ms
        run_record.error_message = str(exc)
        run_record.stage_results = [s.model_dump() for s in stage_results]
        await db.commit()

        return PipelineRunResponse(
            run_id=run_record.id,
            pipeline_id=pipeline.id,
            workspace_id=workspace_id,
            status="failed",
            started_at=run_record.started_at,
            completed_at=run_record.completed_at,
            execution_time_ms=total_time_ms,
            output_dataset_id=None,
            output_dataset_name=None,
            stage_results=stage_results,
            error_message=str(exc),
        )
