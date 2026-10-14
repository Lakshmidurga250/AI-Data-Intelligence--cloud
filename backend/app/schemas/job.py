"""Pydantic schemas for background worker jobs and periodic schedules."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

JobStatusType = Literal["pending", "running", "completed", "failed", "cancelled"]
TaskType = Literal["pipeline_run", "dataset_profile", "dataset_ingest", "scheduled_job"]


class JobTaskCreate(BaseModel):
    """Payload to dispatch an asynchronous background worker task."""

    task_type: TaskType = Field(..., description="Worker task identifier")
    resource_id: Optional[str] = Field(None, description="Target resource (e.g. pipeline_id or dataset_id)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Job parameters and arguments")


class JobTaskSummary(BaseModel):
    """Lightweight summary of a background job."""

    id: str
    workspace_id: str
    task_type: str
    status: JobStatusType
    progress_pct: int = 0
    message: str
    resource_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class JobTaskRead(BaseModel):
    """Detailed job telemetry schema including parameters and results."""

    id: str
    workspace_id: str
    task_type: str
    celery_task_id: Optional[str] = None
    status: JobStatusType
    progress_pct: int = 0
    message: str
    resource_id: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result_payload: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None
    triggered_by_user_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def _parse_json(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except Exception:
                return {}
        if isinstance(v, dict):
            return v
        return {}

    @field_validator("parameters", "result_payload", mode="before")
    @classmethod
    def convert_json_fields(cls, v: Any) -> Dict[str, Any]:
        return cls._parse_json(v)



class JobProgressUpdate(BaseModel):
    """Internal schema for updating job progress percentage and message."""

    progress_pct: int = Field(..., ge=0, le=100)
    message: str
    status: Optional[JobStatusType] = None
    result_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class JobScheduleCreate(BaseModel):
    """Payload to register a new recurring pipeline execution schedule."""

    pipeline_id: str = Field(..., description="ID of pipeline to trigger")
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cron_expression: str = Field(..., description="Cron expression (e.g. '0 * * * *') or interval ('hourly', 'daily')")
    is_active: bool = True


class JobScheduleUpdate(BaseModel):
    """Payload to modify schedule frequency or active state."""

    name: Optional[str] = None
    description: Optional[str] = None
    cron_expression: Optional[str] = None
    is_active: Optional[bool] = None


class JobScheduleRead(BaseModel):
    """Detailed schedule configuration schema."""

    id: str
    workspace_id: str
    pipeline_id: str
    name: str
    description: Optional[str] = None
    cron_expression: str
    is_active: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkerDiagnosticsResponse(BaseModel):
    """Diagnostic health telemetry for the Celery/Redis worker subsystem."""

    status: Literal["operational", "degraded", "offline"]
    broker_type: str = "redis"
    broker_url: str
    active_worker_count: int = 0
    queued_task_count: int = 0
    running_task_count: int = 0
    completed_today_count: int = 0
    failed_today_count: int = 0
    timestamp: datetime
