"""JobSchedule entity model for periodic recurring pipeline triggers."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.pipeline import Pipeline
    from app.models.user import User
    from app.models.workspace import Workspace


class JobSchedule(Base, UUIDMixin, TimestampMixin):
    """Recurring cron or interval schedule for automated ETL pipeline execution."""

    __tablename__ = "job_schedules"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "0 * * * *" or "hourly"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    pipeline: Mapped["Pipeline"] = relationship("Pipeline")
    creator: Mapped[Optional["User"]] = relationship("User")
