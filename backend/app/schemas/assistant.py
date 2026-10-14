"""Pydantic schemas for AI Data Intelligence Assistant and Conversational Analytics."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


InsightSeverity = Literal["info", "low", "medium", "high", "critical"]
InsightType = Literal[
    "distribution_anomaly",
    "missing_values",
    "high_correlation",
    "target_imbalance",
    "outlier_risk",
    "cardinality_alert",
    "trend_indicator",
]


class InsightItem(BaseModel):
    """Automated anomaly or trend discovery observation."""

    insight_type: InsightType
    severity: InsightSeverity
    column: Optional[str] = None
    title: str
    description: str
    metric_value: Optional[Union[float, str, int]] = None
    recommendation: str


class InsightReportResponse(BaseModel):
    """Complete automated dataset anomaly scorecard."""

    dataset_id: str
    dataset_name: str
    total_rows: int = 0
    total_columns: int = 0
    total_insights: int
    critical_count: int
    insights: List[InsightItem]
    generated_at: datetime


class NLQueryTranslation(BaseModel):
    """Natural language translated query execution payload."""

    dataset_id: str
    operation: str
    explanation: str
    query_spec: Dict[str, Any]
    columns: List[str]
    data: List[Dict[str, Any]]
    suggested_chart: Optional[str] = "bar"


class ChatMessageCreate(BaseModel):
    """Input payload to post a message to an assistant conversation."""

    content: str = Field(..., min_length=1, description="User prompt or question")
    active_dataset_id: Optional[str] = Field(None, description="Target dataset context")
    dataset_id: Optional[str] = Field(None, description="Target dataset context alias")


class ChatMessageRead(BaseModel):
    """Serialized message representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    intent: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: Optional[float] = None
    created_at: datetime


class ConversationCreate(BaseModel):
    """Payload to create an assistant conversation thread."""

    title: Optional[str] = Field("New Conversation", max_length=255)
    active_dataset_id: Optional[str] = None
    dataset_id: Optional[str] = None


class ConversationRead(BaseModel):
    """Summary of an assistant conversation thread."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: Optional[str] = None
    title: str
    active_dataset_id: Optional[str] = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConversationDetailRead(ConversationRead):
    """Detailed conversation thread with message trajectory."""

    messages: List[ChatMessageRead] = Field(default_factory=list)


class AssistantChatResponse(BaseModel):
    """Full assistant response payload for a user interaction turn."""

    conversation_id: str
    user_message: ChatMessageRead
    assistant_message: ChatMessageRead
    intent: str
    insights: Optional[List[InsightItem]] = None
    query_result: Optional[NLQueryTranslation] = None
    suggested_prompts: List[str] = Field(default_factory=list)
