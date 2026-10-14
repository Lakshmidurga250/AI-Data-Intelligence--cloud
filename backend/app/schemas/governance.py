"""Pydantic schemas for Data Governance policies, compliance audits, and PII scanning."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, field_validator


class GovernancePolicyBase(BaseModel):
    name: str
    description: Optional[str] = None
    classification_tier: str = "INTERNAL"  # PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED_PII
    retention_days: int = 365
    compliance_framework: str = "INTERNAL"  # GDPR, HIPAA, SOC2, CCPA, INTERNAL
    data_steward: Optional[str] = None
    auto_purge_enabled: bool = False
    is_active: bool = True


class GovernancePolicyCreate(GovernancePolicyBase):
    pass


class GovernancePolicyRead(GovernancePolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime


class DatasetGovernanceTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    dataset_id: str
    column_name: Optional[str] = None
    sensitivity_label: str
    confidence_score: float
    is_quarantined: bool
    created_at: datetime
    updated_at: datetime


class PIIScanResult(BaseModel):
    column_name: str
    sensitivity_label: str
    confidence_score: float
    sample_matches_count: int
    sample_masked_values: List[str]


class DatasetPIIScanResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    scanned_columns_count: int
    flagged_columns_count: int
    findings: List[PIIScanResult]
    overall_classification: str
    is_quarantined: bool


class ComplianceAuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    dataset_id: Optional[str] = None
    policy_id: Optional[str] = None
    event_type: str
    severity: str
    findings_json: Optional[Dict[str, Any]] = None
    actor: str
    created_at: datetime

    @field_validator("findings_json", mode="before")
    @classmethod
    def parse_findings_json(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v
