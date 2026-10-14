"""Workspace and membership validation schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.membership import WorkspaceRole


class WorkspaceBase(BaseModel):
    """Base workspace fields."""

    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)


class WorkspaceCreate(WorkspaceBase):
    """Schema for creating a workspace."""

    slug: Optional[str] = Field(default=None, min_length=2, max_length=255)


class WorkspaceUpdate(BaseModel):
    """Schema for updating workspace metadata."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)


class WorkspaceMemberRead(BaseModel):
    """Schema for presenting workspace members."""

    id: str
    workspace_id: str
    user_id: str
    role: str
    created_at: datetime
    user_email: Optional[str] = None
    user_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WorkspaceMemberCreate(BaseModel):
    """Schema for adding/inviting a user to a workspace."""

    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.MEMBER


class WorkspaceMemberUpdate(BaseModel):
    """Schema for changing a member's role."""

    role: WorkspaceRole


class WorkspaceRead(WorkspaceBase):
    """Public workspace schema."""

    id: str
    slug: str
    owner_id: str
    created_at: datetime
    role: Optional[str] = None  # Role of current querying user

    model_config = ConfigDict(from_attributes=True)
