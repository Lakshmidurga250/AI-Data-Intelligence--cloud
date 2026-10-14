"""Pydantic schemas for Interactive BI, Dashboards, and Analytics Query Engine."""

import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator

VisualizationType = Literal["bar", "line", "area", "scatter", "pie", "kpi", "table"]
AggregationType = Literal["sum", "avg", "min", "max", "count", "distinct_count"]
TimeGrain = Literal["day", "week", "month", "year"]
SortOrder = Literal["asc", "desc"]
FilterOperator = Literal[
    "==",
    "!=",
    ">",
    "<",
    ">=",
    "<=",
    "in",
    "contains",
    "is_null",
    "not_null",
]


class MetricSpec(BaseModel):
    """Specification of an aggregated measure."""

    column: str = Field(..., description="Target dataset column to measure, or '*' for count")
    aggregation: AggregationType = Field("count", description="Aggregation function")
    alias: Optional[str] = Field(None, description="Optional custom label for the metric output")


class FilterSpec(BaseModel):
    """Filter criteria applied prior to grouping and aggregation."""

    column: str = Field(..., description="Target column to filter on")
    operator: FilterOperator = Field("==", description="Comparison operator")
    value: Optional[Any] = Field(None, description="Scalar comparison value, array of values, or substring")


class WidgetPosition(BaseModel):
    """Canvas position and dimension coordinates."""

    x: int = 0
    y: int = 0
    w: int = 6
    h: int = 4


class WidgetQueryConfig(BaseModel):
    """Declarative query parameters powering a dashboard widget."""

    metrics: List[MetricSpec] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list, description="Categorical or discrete grouping columns")
    filters: List[FilterSpec] = Field(default_factory=list, description="Pre-aggregation filters")
    time_column: Optional[str] = Field(None, description="Timestamp/datetime column for temporal grouping")
    time_grain: Optional[TimeGrain] = Field(None, description="Temporal bucket granularity")
    sort_by: Optional[str] = Field(None, description="Metric or dimension alias to sort results by")
    sort_order: SortOrder = Field("desc", description="Sort direction")
    limit: Optional[int] = Field(100, ge=1, le=5000, description="Max rows returned")


class AnalyticsQueryRequest(BaseModel):
    """Payload to execute an ad-hoc or widget-bound analytical aggregation query."""

    dataset_id: str = Field(..., description="Source dataset ID")
    metrics: List[MetricSpec] = Field(..., min_length=1, description="List of aggregations to compute")
    dimensions: Optional[List[str]] = Field(default_factory=list, description="Categorical grouping dimensions")
    filters: Optional[List[FilterSpec]] = Field(default_factory=list, description="Pre-aggregation filters")
    time_column: Optional[str] = Field(None, description="Timestamp column for temporal grouping")
    time_grain: Optional[TimeGrain] = Field(None, description="Temporal bucketing granularity")
    sort_by: Optional[str] = Field(None, description="Column or metric to sort by")
    sort_order: Optional[SortOrder] = "desc"
    limit: Optional[int] = Field(500, ge=1, le=10000)


class AnalyticsQueryResponse(BaseModel):
    """Result of an analytical aggregation query."""

    columns: List[str]
    data: List[Dict[str, Any]]
    row_count: int
    execution_time_ms: float


class DashboardWidgetCreate(BaseModel):
    """Payload to create a new widget in a dashboard."""

    name: str = Field(..., min_length=1, max_length=255)
    dataset_id: Optional[str] = None
    visualization_type: VisualizationType = Field(..., description="Chart or widget display type")
    query_config: Union[WidgetQueryConfig, Dict[str, Any]] = Field(default_factory=dict)
    position: Optional[Union[WidgetPosition, Dict[str, Any]]] = None


class DashboardWidgetUpdate(BaseModel):
    """Payload to modify an existing dashboard widget."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    dataset_id: Optional[str] = None
    visualization_type: Optional[VisualizationType] = None
    query_config: Optional[Union[WidgetQueryConfig, Dict[str, Any]]] = None
    position: Optional[Union[WidgetPosition, Dict[str, Any]]] = None


class DashboardWidgetRead(BaseModel):
    """Schema for a registered dashboard widget."""

    id: str
    dashboard_id: str
    dataset_id: Optional[str] = None
    name: str
    visualization_type: str
    query_config: Dict[str, Any] = Field(default_factory=dict)
    position: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("query_config", mode="before")
    @classmethod
    def parse_query_config(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        if isinstance(v, dict):
            return v
        return {}

    @field_validator("position", mode="before")
    @classmethod
    def parse_position(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        if isinstance(v, dict):
            return v
        return None


class DashboardCreate(BaseModel):
    """Payload to create an analytics dashboard."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    layout_config: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = False


class DashboardUpdate(BaseModel):
    """Payload to update an analytics dashboard."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    layout_config: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


class DashboardRead(BaseModel):
    """Summary schema for an analytics dashboard."""

    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    layout_config: Optional[Dict[str, Any]] = None
    is_default: bool = False
    widgets_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("layout_config", mode="before")
    @classmethod
    def parse_layout(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        if isinstance(v, dict):
            return v
        return None


class DashboardDetailRead(DashboardRead):
    """Detailed analytics dashboard schema with all embedded widgets."""

    widgets: List[DashboardWidgetRead] = Field(default_factory=list)
