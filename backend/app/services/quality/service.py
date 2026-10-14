"""Data Quality management and execution service layer."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dataset import Dataset
from app.models.quality import (
    QualityAlert,
    QualityEvaluationRun,
    QualityRule,
    QualityRuleSuite,
)
from app.schemas.quality import (
    QualityRuleCreate,
    QualityRuleSuiteCreate,
    QualityRuleSuiteUpdate,
)
from app.services.audit_service import log_audit
from app.services.ingestion.parser import read_file_to_dataframe
from app.services.quality.evaluator import evaluate_suite_on_dataframe


async def create_suite(
    db: AsyncSession,
    workspace_id: str,
    suite_in: QualityRuleSuiteCreate,
    user_id: Optional[str] = None,
) -> QualityRuleSuite:
    """Create a new quality rule suite with optional initial rules."""
    suite = QualityRuleSuite(
        workspace_id=workspace_id,
        dataset_id=suite_in.dataset_id,
        name=suite_in.name,
        description=suite_in.description,
        is_active=suite_in.is_active,
    )
    db.add(suite)
    await db.flush()

    for r_in in suite_in.rules:
        params_str = json.dumps(r_in.parameters) if isinstance(r_in.parameters, dict) else str(r_in.parameters)
        rule = QualityRule(
            suite_id=suite.id,
            name=r_in.name,
            rule_type=r_in.rule_type,
            target_column=r_in.target_column,
            parameters=params_str,
            severity=r_in.severity,
            is_active=r_in.is_active,
        )
        db.add(rule)

    await db.commit()

    # Re-fetch with rules eager loaded
    return await get_suite(db, suite.id, workspace_id)  # type: ignore


async def get_suite(
    db: AsyncSession,
    suite_id: str,
    workspace_id: str,
) -> Optional[QualityRuleSuite]:
    """Retrieve a single rule suite with all associated rules."""
    query = (
        select(QualityRuleSuite)
        .options(selectinload(QualityRuleSuite.rules))
        .where(
            QualityRuleSuite.id == suite_id,
            QualityRuleSuite.workspace_id == workspace_id,
        )
    )
    res = await db.execute(query)
    return res.scalar_one_or_none()


async def list_suites(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: Optional[str] = None,
) -> List[QualityRuleSuite]:
    """List all rule suites for a workspace, optionally filtered by dataset."""
    query = (
        select(QualityRuleSuite)
        .options(selectinload(QualityRuleSuite.rules))
        .where(QualityRuleSuite.workspace_id == workspace_id)
        .order_by(desc(QualityRuleSuite.created_at))
    )
    if dataset_id:
        query = query.where(QualityRuleSuite.dataset_id == dataset_id)

    res = await db.execute(query)
    return list(res.scalars().all())


async def update_suite(
    db: AsyncSession,
    suite_id: str,
    workspace_id: str,
    suite_in: QualityRuleSuiteUpdate,
) -> Optional[QualityRuleSuite]:
    """Update metadata for an existing quality rule suite."""
    suite = await get_suite(db, suite_id, workspace_id)
    if not suite:
        return None

    if suite_in.name is not None:
        suite.name = suite_in.name
    if suite_in.description is not None:
        suite.description = suite_in.description
    if suite_in.dataset_id is not None:
        suite.dataset_id = suite_in.dataset_id
    if suite_in.is_active is not None:
        suite.is_active = suite_in.is_active

    await db.commit()
    await db.refresh(suite)
    return suite


async def delete_suite(
    db: AsyncSession,
    suite_id: str,
    workspace_id: str,
) -> bool:
    """Delete a rule suite and cascade delete child rules and evaluations."""
    suite = await get_suite(db, suite_id, workspace_id)
    if not suite:
        return False

    await db.delete(suite)
    await db.commit()
    return True


async def add_rule_to_suite(
    db: AsyncSession,
    suite_id: str,
    workspace_id: str,
    rule_in: QualityRuleCreate,
) -> Optional[QualityRule]:
    """Add a new validation rule to an existing suite."""
    suite = await get_suite(db, suite_id, workspace_id)
    if not suite:
        return None

    params_str = json.dumps(rule_in.parameters) if isinstance(rule_in.parameters, dict) else str(rule_in.parameters)
    rule = QualityRule(
        suite_id=suite.id,
        name=rule_in.name,
        rule_type=rule_in.rule_type,
        target_column=rule_in.target_column,
        parameters=params_str,
        severity=rule_in.severity,
        is_active=rule_in.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(
    db: AsyncSession,
    rule_id: str,
    workspace_id: str,
) -> bool:
    """Delete an individual quality rule."""
    query = (
        select(QualityRule)
        .join(QualityRuleSuite)
        .where(
            QualityRule.id == rule_id,
            QualityRuleSuite.workspace_id == workspace_id,
        )
    )
    res = await db.execute(query)
    rule = res.scalar_one_or_none()
    if not rule:
        return False

    await db.delete(rule)
    await db.commit()
    return True


async def evaluate_suite(
    db: AsyncSession,
    suite_id: str,
    workspace_id: str,
    dataset_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> QualityEvaluationRun:
    """Execute quality rule validation against target dataset."""
    suite = await get_suite(db, suite_id, workspace_id)
    if not suite:
        raise ValueError(f"Quality suite '{suite_id}' not found in workspace.")

    target_dataset_id = dataset_id or suite.dataset_id
    if not target_dataset_id:
        raise ValueError("No target dataset specified for quality evaluation.")

    # Fetch dataset
    ds_query = select(Dataset).where(
        Dataset.id == target_dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    ds_res = await db.execute(ds_query)
    dataset = ds_res.scalar_one_or_none()
    if not dataset:
        raise ValueError(f"Dataset '{target_dataset_id}' not found in workspace.")

    # Read DataFrame
    df = read_file_to_dataframe(Path(dataset.storage_path), dataset.format)

    # Prepare active rules
    active_rules: List[Dict[str, Any]] = []
    for r in suite.rules:
        if r.is_active:
            try:
                params = json.loads(r.parameters) if isinstance(r.parameters, str) else r.parameters
            except Exception:
                params = {}
            active_rules.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "rule_type": r.rule_type,
                    "target_column": r.target_column,
                    "parameters": params,
                    "severity": r.severity,
                }
            )

    t0 = time.time()
    score, grade, total, passed, failed, results = evaluate_suite_on_dataframe(df, active_rules)
    duration_ms = int((time.time() - t0) * 1000)

    # Record evaluation run
    serialized_results = json.dumps([r.model_dump() for r in results])
    eval_run = QualityEvaluationRun(
        workspace_id=workspace_id,
        suite_id=suite.id,
        dataset_id=dataset.id,
        status="completed",
        score=score,
        grade=grade,
        total_rules=total,
        passed_rules=passed,
        failed_rules=failed,
        execution_time_ms=duration_ms,
        rule_results=serialized_results,
    )
    db.add(eval_run)
    await db.flush()

    # Generate alerts for failed rules
    failed_results = [r for r in results if not r.passed]
    if failed_results:
        critical_count = sum(1 for r in failed_results if r.severity == "critical")
        warning_count = sum(1 for r in failed_results if r.severity == "warning")
        highest_sev = "critical" if critical_count > 0 else "warning"

        alert = QualityAlert(
            workspace_id=workspace_id,
            suite_id=suite.id,
            run_id=eval_run.id,
            severity=highest_sev,
            title=f"Quality Check Failed: Suite '{suite.name}' (Grade {grade}, {score}%)",
            message=(
                f"{len(failed_results)} rule(s) violated on dataset '{dataset.name}'. "
                f"({critical_count} critical, {warning_count} warning). Total rows tested: {len(df):,}."
            ),
            is_acknowledged=False,
        )
        db.add(alert)

    # Audit logging
    await log_audit(
        db=db,
        workspace_id=workspace_id,
        action="quality.evaluate",
        resource_type="quality_suite",
        resource_id=suite.id,
        user_id=user_id,
        details={
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "score": score,
            "grade": grade,
            "failed_rules": failed,
        },
    )

    await db.commit()
    await db.refresh(eval_run)
    return eval_run


async def list_evaluation_runs(
    db: AsyncSession,
    workspace_id: str,
    suite_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    limit: int = 50,
) -> List[QualityEvaluationRun]:
    """Retrieve evaluation history timeline."""
    query = (
        select(QualityEvaluationRun)
        .where(QualityEvaluationRun.workspace_id == workspace_id)
        .order_by(desc(QualityEvaluationRun.created_at))
        .limit(limit)
    )
    if suite_id:
        query = query.where(QualityEvaluationRun.suite_id == suite_id)
    if dataset_id:
        query = query.where(QualityEvaluationRun.dataset_id == dataset_id)

    res = await db.execute(query)
    return list(res.scalars().all())


async def get_evaluation_run(
    db: AsyncSession,
    run_id: str,
    workspace_id: str,
) -> Optional[QualityEvaluationRun]:
    """Retrieve details for a specific evaluation run."""
    query = select(QualityEvaluationRun).where(
        QualityEvaluationRun.id == run_id,
        QualityEvaluationRun.workspace_id == workspace_id,
    )
    res = await db.execute(query)
    return res.scalar_one_or_none()


async def list_alerts(
    db: AsyncSession,
    workspace_id: str,
    is_acknowledged: Optional[bool] = None,
    limit: int = 50,
) -> List[QualityAlert]:
    """Retrieve generated quality alerts."""
    query = (
        select(QualityAlert)
        .where(QualityAlert.workspace_id == workspace_id)
        .order_by(desc(QualityAlert.created_at))
        .limit(limit)
    )
    if is_acknowledged is not None:
        query = query.where(QualityAlert.is_acknowledged == is_acknowledged)

    res = await db.execute(query)
    return list(res.scalars().all())


async def acknowledge_alert(
    db: AsyncSession,
    alert_id: str,
    workspace_id: str,
) -> Optional[QualityAlert]:
    """Mark an alert as acknowledged."""
    query = select(QualityAlert).where(
        QualityAlert.id == alert_id,
        QualityAlert.workspace_id == workspace_id,
    )
    res = await db.execute(query)
    alert = res.scalar_one_or_none()
    if not alert:
        return None

    alert.is_acknowledged = True
    await db.commit()
    await db.refresh(alert)
    return alert
