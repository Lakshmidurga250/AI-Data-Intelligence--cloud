"""Workspace ORM entity model for multi-tenant data isolation."""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.membership import WorkspaceMembership
    from app.models.audit import AuditLog
    from app.models.pipeline import Pipeline


class Workspace(Base, UUIDMixin, TimestampMixin):
    """Isolated tenant workspace grouping datasets, pipelines, and ML models."""

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Relationships
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="owned_workspaces",
    )
    memberships: Mapped[List["WorkspaceMembership"]] = relationship(
        "WorkspaceMembership",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    pipelines: Mapped[List["Pipeline"]] = relationship(
        "Pipeline",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
