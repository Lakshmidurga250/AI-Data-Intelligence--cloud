"""Audit log presentation schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    """Schema for presenting audit log events."""

    id: str
    workspace_id: Optional[str]
    user_id: Optional[str]
    action: str
    resource_type: str
    resource_id: str
    details: str
    ip_address: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
