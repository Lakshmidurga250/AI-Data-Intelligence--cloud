"""Pydantic schemas for Data Quality Rule Suites, Rules, Evaluations, and Alerts."""

import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

QualityRuleType = Literal[
    "null_threshold",
    "uniqueness",
    "value_range",
    "regex_match",
    "set_membership",
    "expression",
]
QualitySeverity = Literal["critical", "warning", "info"]
EvaluationGrade = Literal["A", "B", "C", "D", "F"]


class QualityRuleBase(BaseModel):
    """Base definition for a data quality validation rule."""

    name: str = Field(..., max_length=255, description="Descriptive rule label")
    rule_type: QualityRuleType = Field(..., description="Validation operator category")
    target_column: str = Field(..., max_length=255, description="Target column name")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Rule evaluation parameters")
    severity: QualitySeverity = Field("critical", description="Severity if rule fails")
    is_active: bool = Field(True, description="Whether rule is active in evaluation")


class QualityRuleCreate(QualityRuleBase):
    """Payload to create a quality rule."""

    pass


class QualityRuleRead(QualityRuleBase):
    """Schema for retrieved quality rule."""

    id: str
    suite_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("parameters", mode="before")
    @classmethod
    def parse_parameters(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        if isinstance(v, dict):
            return v
        return {}


class QualityRuleSuiteBase(BaseModel):
    """Base fields for a quality rule suite."""

    name: str = Field(..., max_length=255, description="Rule suite name")
    description: Optional[str] = Field(None, description="Optional purpose or documentation")
    dataset_id: Optional[str] = Field(None, description="Target dataset ID")
    is_active: bool = Field(True, description="Whether suite is active")


class QualityRuleSuiteCreate(QualityRuleSuiteBase):
    """Payload to create a rule suite with optional initial rules."""

    rules: List[QualityRuleCreate] = Field(default_factory=list, description="Initial rules list")


class QualityRuleSuiteUpdate(BaseModel):
    """Payload to update rule suite metadata."""

    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    dataset_id: Optional[str] = None
    is_active: Optional[bool] = None


class QualityRuleSuiteRead(QualityRuleSuiteBase):
    """Schema for retrieved quality rule suite with its child rules."""

    id: str
    workspace_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    rules: List[QualityRuleRead] = Field(default_factory=list)
    rules_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class RuleEvaluationResult(BaseModel):
    """Detailed evaluation telemetry for a single rule."""

    rule_id: str
    rule_name: str
    rule_type: str
    target_column: str
    severity: str
    passed: bool
    total_rows: int
    failed_rows: int
    failure_rate_pct: float
    message: str
    sample_violations: List[Dict[str, Any]] = Field(default_factory=list)


class QualityEvaluationRunRead(BaseModel):
    """Record of a complete rule suite evaluation execution."""

    id: str
    workspace_id: str
    suite_id: str
    dataset_id: str
    status: str
    score: float
    grade: EvaluationGrade
    total_rules: int
    passed_rules: int
    failed_rules: int
    execution_time_ms: int
    rule_results: List[RuleEvaluationResult] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("rule_results", mode="before")
    @classmethod
    def parse_results(cls, v: Any) -> List[Any]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        if isinstance(v, list):
            return v
        return []


class QualityAlertRead(BaseModel):
    """Quality notification alert."""

    id: str
    workspace_id: str
    suite_id: str
    run_id: str
    severity: str
    title: str
    message: str
    is_acknowledged: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QualityEvaluationRequest(BaseModel):
    """Payload to trigger quality evaluation."""

    dataset_id: Optional[str] = Field(None, description="Dataset to evaluate; falls back to suite.dataset_id")
