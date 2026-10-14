"""Data Quality Suite, Rule, Evaluation Run, and Alert entity models."""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.workspace import Workspace


class QualityRuleSuite(Base, UUIDMixin, TimestampMixin):
    """Collection of Data Quality validation rules scoped to a tenant workspace and optional dataset."""

    __tablename__ = "quality_rule_suites"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    dataset: Mapped[Optional["Dataset"]] = relationship("Dataset")
    rules: Mapped[List["QualityRule"]] = relationship(
        "QualityRule",
        back_populates="suite",
        cascade="all, delete-orphan",
        order_by="QualityRule.created_at",
    )
    evaluation_runs: Mapped[List["QualityEvaluationRun"]] = relationship(
        "QualityEvaluationRun",
        back_populates="suite",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[List["QualityAlert"]] = relationship(
        "QualityAlert",
        back_populates="suite",
        cascade="all, delete-orphan",
    )


class QualityRule(Base, UUIDMixin, TimestampMixin):
    """Individual declarative validation constraint within a QualityRuleSuite."""

    __tablename__ = "quality_rules"

    suite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("quality_rule_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # null_threshold, uniqueness, value_range, regex_match, set_membership, expression
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20),
        default="critical",
        nullable=False,
    )  # critical, warning, info
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship
    suite: Mapped["QualityRuleSuite"] = relationship("QualityRuleSuite", back_populates="rules")


class QualityEvaluationRun(Base, UUIDMixin, TimestampMixin):
    """Historical record of rule suite evaluation against a dataset DataFrame."""

    __tablename__ = "quality_evaluation_runs"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("quality_rule_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="completed",
        nullable=False,
    )  # completed, failed
    score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)  # 0.0 - 100.0
    grade: Mapped[str] = mapped_column(String(5), default="A", nullable=False)  # A, B, C, D, F
    total_rules: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_rules: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rules: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    execution_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rule_results: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    suite: Mapped["QualityRuleSuite"] = relationship("QualityRuleSuite", back_populates="evaluation_runs")
    dataset: Mapped["Dataset"] = relationship("Dataset")
    alerts: Mapped[List["QualityAlert"]] = relationship(
        "QualityAlert",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class QualityAlert(Base, UUIDMixin, TimestampMixin):
    """Notification event generated when one or more critical or warning quality rules fail."""

    __tablename__ = "quality_alerts"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("quality_rule_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("quality_evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # critical, warning, info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    suite: Mapped["QualityRuleSuite"] = relationship("QualityRuleSuite", back_populates="alerts")
    run: Mapped["QualityEvaluationRun"] = relationship("QualityEvaluationRun", back_populates="alerts")
