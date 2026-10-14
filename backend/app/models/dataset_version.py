"""DatasetVersion entity model tracking immutable snapshots and historical schema evolutions."""

from typing import TYPE_CHECKING, Optional
from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.user import User


class DatasetVersion(Base, UUIDMixin, TimestampMixin):
    """Immutable version snapshot representing dataset state at a point in time."""

    __tablename__ = "dataset_versions"

    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str] = mapped_column(
        String(255),
        default="Initial dataset snapshot",
        nullable=False,
    )
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # In-depth statistical profile snapshot (stored as JSON text)
    profile_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="versions")
    creator: Mapped[Optional["User"]] = relationship("User")
