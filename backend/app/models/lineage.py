"""Data Lineage entity models for graph nodes and directed dependency edges."""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.workspace import Workspace


class LineageNode(Base, UUIDMixin, TimestampMixin):
    """Represents an asset or execution stage node in the lineage graph."""

    __tablename__ = "lineage_nodes"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )  # dataset, pipeline, transformation, quality_suite, external_source
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    outgoing_edges: Mapped[List["LineageEdge"]] = relationship(
        "LineageEdge",
        foreign_keys="LineageEdge.source_node_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[List["LineageEdge"]] = relationship(
        "LineageEdge",
        foreign_keys="LineageEdge.target_node_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )


class LineageEdge(Base, UUIDMixin):
    """Directed dependency edge representing data flow or provenance between nodes."""

    __tablename__ = "lineage_edges"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lineage_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lineage_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_type: Mapped[str] = mapped_column(
        String(64),
        default="data_flow",
        nullable=False,
    )  # data_flow, derivation, validation, pipeline_execution
    column_mappings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transformation_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    source_node: Mapped["LineageNode"] = relationship(
        "LineageNode",
        foreign_keys=[source_node_id],
        back_populates="outgoing_edges",
    )
    target_node: Mapped["LineageNode"] = relationship(
        "LineageNode",
        foreign_keys=[target_node_id],
        back_populates="incoming_edges",
    )
