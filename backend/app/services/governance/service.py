"""Governance policy management, compliance audit logging, and PII scanning service."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.governance import ComplianceAuditLog, DatasetGovernanceTag, GovernancePolicy
from app.schemas.governance import (
    DatasetGovernanceTagRead,
    DatasetPIIScanResponse,
    GovernancePolicyCreate,
    GovernancePolicyRead,
    PIIScanResult,
)
from app.services.governance.classifier import scan_dataframe_pii
from app.services.ingestion.parser import read_file_to_dataframe


async def create_governance_policy(
    db: AsyncSession,
    workspace_id: str,
    policy_in: GovernancePolicyCreate,
) -> GovernancePolicy:
    """Create a new data governance and compliance policy for the workspace."""
    policy = GovernancePolicy(
        workspace_id=workspace_id,
        name=policy_in.name,
        description=policy_in.description,
        classification_tier=policy_in.classification_tier,
        retention_days=policy_in.retention_days,
        compliance_framework=policy_in.compliance_framework,
        data_steward=policy_in.data_steward,
        auto_purge_enabled=policy_in.auto_purge_enabled,
        is_active=policy_in.is_active,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def list_governance_policies(
    db: AsyncSession,
    workspace_id: str,
) -> List[GovernancePolicy]:
    """Retrieve all governance policies for a workspace."""
    query = select(GovernancePolicy).where(GovernancePolicy.workspace_id == workspace_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_governance_policy(
    db: AsyncSession,
    workspace_id: str,
    policy_id: str,
) -> Optional[GovernancePolicy]:
    """Retrieve a single governance policy by ID with tenant isolation."""
    query = select(GovernancePolicy).where(
        GovernancePolicy.workspace_id == workspace_id,
        GovernancePolicy.id == policy_id,
    )
    result = await db.execute(query)
    return result.scalars().first()


async def delete_governance_policy(
    db: AsyncSession,
    workspace_id: str,
    policy_id: str,
) -> bool:
    """Delete a governance policy."""
    policy = await get_governance_policy(db, workspace_id, policy_id)
    if not policy:
        return False
    await db.delete(policy)
    await db.commit()
    return True


async def scan_dataset_pii_and_tag(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: str,
    actor_email: str = "system",
) -> Optional[DatasetPIIScanResponse]:
    """Execute automated PII classification scan, persist governance tags, and write audit log."""
    ds_query = select(Dataset).where(
        Dataset.workspace_id == workspace_id,
        Dataset.id == dataset_id,
    )
    res = await db.execute(ds_query)
    dataset = res.scalars().first()
    if not dataset:
        return None

    # Load dataset DataFrame
    df = read_file_to_dataframe(
        Path(dataset.storage_path),
        dataset.format,
    )

    findings, tier, quarantine = scan_dataframe_pii(df)

    # Clean old tags for this dataset
    await db.execute(
        delete(DatasetGovernanceTag).where(
            DatasetGovernanceTag.workspace_id == workspace_id,
            DatasetGovernanceTag.dataset_id == dataset_id,
        )
    )

    # Persist new governance tags
    for item in findings:
        tag = DatasetGovernanceTag(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            column_name=item.column_name,
            sensitivity_label=item.sensitivity_label,
            confidence_score=item.confidence_score,
            is_quarantined=quarantine,
        )
        db.add(tag)

    # Log audit entry
    findings_data = {
        "dataset_name": dataset.name,
        "scanned_columns": len(df.columns),
        "flagged_columns": len(findings),
        "overall_tier": tier,
        "quarantined": quarantine,
        "labels": [f.sensitivity_label for f in findings],
    }
    audit = ComplianceAuditLog(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        event_type="pii_scan",
        severity="critical" if quarantine else ("warning" if findings else "info"),
        findings_json=json.dumps(findings_data),
        actor=actor_email,
    )
    db.add(audit)

    await db.commit()

    return DatasetPIIScanResponse(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        scanned_columns_count=len(df.columns),
        flagged_columns_count=len(findings),
        findings=findings,
        overall_classification=tier,
        is_quarantined=quarantine,
    )


async def list_dataset_governance_tags(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: str,
) -> List[DatasetGovernanceTagRead]:
    """Retrieve all governance classification tags for a dataset."""
    query = select(DatasetGovernanceTag).where(
        DatasetGovernanceTag.workspace_id == workspace_id,
        DatasetGovernanceTag.dataset_id == dataset_id,
    )
    result = await db.execute(query)
    tags = list(result.scalars().all())
    return [DatasetGovernanceTagRead.model_validate(t) for t in tags]


async def list_compliance_audit_logs(
    db: AsyncSession,
    workspace_id: str,
    limit: int = 50,
) -> List[ComplianceAuditLog]:
    """Retrieve recent compliance audit logs for a workspace."""
    query = (
        select(ComplianceAuditLog)
        .where(ComplianceAuditLog.workspace_id == workspace_id)
        .order_by(ComplianceAuditLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def evaluate_retention_compliance(
    db: AsyncSession,
    workspace_id: str,
    actor_email: str = "system",
) -> Dict[str, Any]:
    """Check dataset ages against active governance policies and flag purge candidates."""
    policies = await list_governance_policies(db, workspace_id)
    if not policies:
        return {"status": "no_policies", "flagged_datasets": 0}

    now = datetime.now(timezone.utc)
    flagged: List[Dict[str, Any]] = []

    ds_query = select(Dataset).where(Dataset.workspace_id == workspace_id)
    ds_res = await db.execute(ds_query)
    datasets = list(ds_res.scalars().all())

    for policy in policies:
        if not policy.is_active or policy.retention_days <= 0:
            continue
        cutoff = now - timedelta(days=policy.retention_days)
        for ds in datasets:
            ds_created = ds.created_at if ds.created_at.tzinfo else ds.created_at.replace(tzinfo=timezone.utc)
            if ds_created < cutoff:
                flagged.append({
                    "dataset_id": ds.id,
                    "dataset_name": ds.name,
                    "policy_name": policy.name,
                    "retention_days": policy.retention_days,
                    "age_days": (now - ds_created).days,
                })

    audit = ComplianceAuditLog(
        workspace_id=workspace_id,
        event_type="retention_check",
        severity="warning" if flagged else "info",
        findings_json=json.dumps({"flagged_count": len(flagged), "items": flagged}),
        actor=actor_email,
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "evaluated",
        "total_datasets_checked": len(datasets),
        "flagged_datasets": len(flagged),
        "details": flagged,
    }
