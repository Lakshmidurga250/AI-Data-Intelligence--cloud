"""Pydantic schemas for Data Lineage graph nodes, edges, and impact analysis."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, field_validator


class LineageNodeBase(BaseModel):
    name: str
    node_type: str  # dataset, pipeline, transformation, quality_suite, external_source
    resource_id: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None

    @field_validator("metadata_json", mode="before")
    @classmethod
    def parse_metadata_json(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class LineageNodeCreate(LineageNodeBase):
    pass


class LineageNodeRead(LineageNodeBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime


class LineageEdgeBase(BaseModel):
    source_node_id: str
    target_node_id: str
    edge_type: str = "data_flow"  # data_flow, derivation, validation, pipeline_execution
    column_mappings_json: Optional[List[Dict[str, str]]] = None
    transformation_summary: Optional[str] = None

    @field_validator("column_mappings_json", mode="before")
    @classmethod
    def parse_column_mappings_json(cls, v: Any) -> Optional[List[Dict[str, str]]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class LineageEdgeCreate(LineageEdgeBase):
    pass


class LineageEdgeRead(LineageEdgeBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    created_at: datetime


class LineageGraphResponse(BaseModel):
    nodes: List[LineageNodeRead]
    edges: List[LineageEdgeRead]
    root_node_count: int
    leaf_node_count: int


class ImpactAnalysisResponse(BaseModel):
    target_node: LineageNodeRead
    upstream_ancestors: List[LineageNodeRead]
    downstream_dependents: List[LineageNodeRead]
    total_impacted_pipelines: int
    total_impacted_datasets: int
    total_impacted_quality_suites: int
