"""Pipeline model representing visual DAG workflows."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import ForeignKey, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.workspace import Workspace
    from app.models.pipeline_run import PipelineRun


class Pipeline(Base, UUIDMixin, TimestampMixin):
    """Pipeline definition storing directed acyclic graph (DAG) topology."""

    __tablename__ = "pipelines"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # graph_definition holds JSON: {"nodes": [...], "edges": [...]}
    graph_definition: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: {"nodes": [], "edges": []},
    )

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="pipelines")
    runs: Mapped[List["PipelineRun"]] = relationship(
        "PipelineRun",
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="desc(PipelineRun.created_at)",
    )
