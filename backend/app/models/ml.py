"""Machine Learning Models, Versions, and AutoML Experiment entities."""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.workspace import Workspace


class MLModel(Base, UUIDMixin, TimestampMixin):
    """Registered Machine Learning model scoped to a workspace."""

    __tablename__ = "ml_models"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )  # "classification" or "regression"
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    framework: Mapped[str] = mapped_column(String(64), default="scikit-learn", nullable=False)
    active_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    versions: Mapped[List["MLModelVersion"]] = relationship(
        "MLModelVersion",
        back_populates="model",
        cascade="all, delete-orphan",
        order_by="MLModelVersion.version_number.desc()",
    )
    experiments: Mapped[List["MLExperiment"]] = relationship(
        "MLExperiment",
        back_populates="model",
        cascade="all, delete-orphan",
    )


class MLModelVersion(Base, UUIDMixin, TimestampMixin):
    """Versioned model snapshot with serialized artifact and performance scorecard."""

    __tablename__ = "ml_model_versions"

    model_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ml_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    experiment_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("ml_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)  # candidate, champion, archived
    metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hyperparameters_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feature_names_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feature_importance_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    model: Mapped["MLModel"] = relationship("MLModel", back_populates="versions")
    experiment: Mapped[Optional["MLExperiment"]] = relationship("MLExperiment")


class MLExperiment(Base, UUIDMixin, TimestampMixin):
    """AutoML training experiment benchmarking multiple algorithms on a dataset."""

    __tablename__ = "ml_experiments"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("ml_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)  # "classification" or "regression"
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending, running, completed, failed
    best_algorithm: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    leaderboard_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    training_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    model: Mapped[Optional["MLModel"]] = relationship("MLModel", back_populates="experiments")
    dataset: Mapped[Optional["Dataset"]] = relationship("Dataset")
