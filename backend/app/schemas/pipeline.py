from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.transforms import TransformStep



PipelineNodeType = Literal[
    "source",
    "transform",
    "filter",
    "aggregate",
    "join",
    "sink",
]


class NodePosition(BaseModel):
    """Visual coordinates on the pipeline canvas."""

    x: float = 0.0
    y: float = 0.0


class PipelineNode(BaseModel):
    """Individual processing node in a pipeline DAG."""

    id: str = Field(..., description="Unique node identifier within the graph")
    type: PipelineNodeType = Field(..., description="Operator node type")
    label: str = Field(default="", description="Display name for the node")
    position: NodePosition = Field(default_factory=NodePosition)
    config: Dict[str, Any] = Field(default_factory=dict, description="Node parameters and options")


class PipelineEdge(BaseModel):
    """Directed connection edge between pipeline nodes."""

    id: str = Field(..., description="Unique edge identifier")
    source: str = Field(..., description="Upstream node ID producing output")
    target: str = Field(..., description="Downstream node ID consuming input")
    source_handle: Optional[str] = Field(None, description="Output port identifier")
    target_handle: Optional[str] = Field(None, description="Input port identifier ('left'/'right')")


class PipelineGraph(BaseModel):
    """Complete graph definition with nodes and directed edges."""

    nodes: List[PipelineNode] = Field(default_factory=list)
    edges: List[PipelineEdge] = Field(default_factory=list)


class PipelineCreate(BaseModel):
    """Payload to create a new visual ETL pipeline."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    graph_definition: PipelineGraph = Field(default_factory=PipelineGraph)


class PipelineUpdate(BaseModel):
    """Payload to modify an existing pipeline."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    graph_definition: Optional[PipelineGraph] = None


class PipelineSummary(BaseModel):
    """Lightweight summary of a pipeline for list endpoints."""

    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    node_count: int = 0
    edge_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineRead(BaseModel):
    """Detailed pipeline schema including graph topology."""

    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    graph_definition: PipelineGraph
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineValidationResult(BaseModel):
    """Topological cycle detection and graph integrity validation."""

    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    execution_order: List[str] = Field(
        default_factory=list,
        description="Topologically sorted node IDs",
    )


class PipelineStageResult(BaseModel):
    """Telemetry report for an individual stage execution within a run."""

    node_id: str
    node_type: str
    label: str
    status: Literal["completed", "failed", "skipped"]
    rows_in: int = 0
    rows_out: int = 0
    columns_out: List[str] = Field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None
    summary: str = ""


class PipelineRunResponse(BaseModel):
    """Result of executing an ETL pipeline."""

    run_id: str
    pipeline_id: str
    workspace_id: str
    status: Literal["completed", "failed"]
    started_at: datetime
    completed_at: Optional[datetime] = None
    execution_time_ms: int = 0
    output_dataset_id: Optional[str] = None
    output_dataset_name: Optional[str] = None
    stage_results: List[PipelineStageResult] = Field(default_factory=list)
    error_message: Optional[str] = None


class PipelineRunSummary(BaseModel):
    """Summary of a past pipeline run."""

    id: str
    pipeline_id: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None
    output_dataset_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

