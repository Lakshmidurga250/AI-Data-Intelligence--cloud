"""Dashboard and Widget entities for Interactive BI and Analytics."""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.workspace import Workspace


class Dashboard(Base, UUIDMixin, TimestampMixin):
    """Interactive analytics dashboard container scoped to a workspace."""

    __tablename__ = "dashboards"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    layout_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="{}")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    widgets: Mapped[List["DashboardWidget"]] = relationship(
        "DashboardWidget",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="DashboardWidget.created_at.asc()",
    )


class DashboardWidget(Base, UUIDMixin, TimestampMixin):
    """Visualization widget placed on an analytics dashboard canvas."""

    __tablename__ = "dashboard_widgets"

    dashboard_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    visualization_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )  # "bar", "line", "area", "scatter", "pie", "kpi", "table"
    query_config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    position: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="{}")

    # Relationships
    dashboard: Mapped["Dashboard"] = relationship("Dashboard", back_populates="widgets")
    dataset: Mapped[Optional["Dataset"]] = relationship("Dataset")
