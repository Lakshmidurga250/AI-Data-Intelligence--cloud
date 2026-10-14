"""Data Governance, Compliance Policy, and Sensitivity Classification models."""

from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.workspace import Workspace


class GovernancePolicy(Base, UUIDMixin, TimestampMixin):
    """Defines retention rules, sensitivity tiers, and compliance requirements for a workspace."""

    __tablename__ = "governance_policies"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    classification_tier: Mapped[str] = mapped_column(
        String(64),
        default="INTERNAL",
        nullable=False,
    )  # PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED_PII
    retention_days: Mapped[int] = mapped_column(Integer, default=365, nullable=False)
    compliance_framework: Mapped[str] = mapped_column(
        String(64),
        default="INTERNAL",
        nullable=False,
    )  # GDPR, HIPAA, SOC2, CCPA, INTERNAL
    data_steward: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    auto_purge_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")


class ComplianceAuditLog(Base, UUIDMixin):
    """Immutable audit entry capturing governance evaluations, access scans, and retention checks."""

    __tablename__ = "compliance_audit_logs"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    policy_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )  # pii_scan, retention_check, access_audit, policy_override, quarantine_flag
    severity: Mapped[str] = mapped_column(String(32), default="info", nullable=False)
    findings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(255), default="system", nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")


class DatasetGovernanceTag(Base, UUIDMixin, TimestampMixin):
    """Column or dataset-level sensitivity classification and quarantine metadata."""

    __tablename__ = "dataset_governance_tags"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    sensitivity_label: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )  # PII_EMAIL, PII_PHONE, PII_SSN, PII_CREDIT_CARD, PII_IP, PII_NAME, CONFIDENTIAL, INTERNAL, PUBLIC
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_quarantined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    dataset: Mapped["Dataset"] = relationship("Dataset")
