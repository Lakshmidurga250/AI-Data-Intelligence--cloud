"""Dataset entity model representing ingested files and tabular data assets."""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.dataset_version import DatasetVersion
    from app.models.user import User
    from app.models.workspace import Workspace


class Dataset(Base, UUIDMixin, TimestampMixin):
    """Ingested tabular data asset belonging to an isolated workspace."""

    __tablename__ = "datasets"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Inferred schema definitions & cached preview records (stored as JSON text)
    schema_metadata: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    preview_data: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    profile_cache: Mapped[Optional[str]] = mapped_column(Text, default="{}", nullable=True)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    creator: Mapped[Optional["User"]] = relationship("User")
    versions: Mapped[List["DatasetVersion"]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version_number.desc()",
    )
