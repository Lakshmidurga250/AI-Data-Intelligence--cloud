"""JobTask entity model tracking asynchronous background worker execution state."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class JobTask(Base, UUIDMixin, TimestampMixin):
    """Asynchronous background task lifecycle and progress state tracking."""

    __tablename__ = "job_tasks"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
    )  # pending, running, completed, failed, cancelled
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(String(255), default="Task queued", nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Serialized parameters and return data
    parameters: Mapped[Optional[str]] = mapped_column(Text, default="{}", nullable=False)
    result_payload: Mapped[Optional[str]] = mapped_column(Text, default="{}", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retries and timing
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    triggered_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    user: Mapped[Optional["User"]] = relationship("User")
