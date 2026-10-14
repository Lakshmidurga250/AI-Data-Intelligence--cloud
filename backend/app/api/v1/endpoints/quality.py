"""FastAPI endpoints for Data Quality Suites, Rules, Evaluations, and Alerts."""

import json
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_workspace,
    get_db,
    require_workspace_role,
)
from app.models.membership import WorkspaceMembership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.quality import (
    QualityAlertRead,
    QualityEvaluationRequest,
    QualityEvaluationRunRead,
    QualityRuleCreate,
    QualityRuleRead,
    QualityRuleSuiteCreate,
    QualityRuleSuiteRead,
    QualityRuleSuiteUpdate,
)
from app.services.quality.service import (
    acknowledge_alert,
    add_rule_to_suite,
    create_suite,
    delete_rule,
    delete_suite,
    evaluate_suite,
    get_evaluation_run,
    get_suite,
    list_alerts,
    list_evaluation_runs,
    list_suites,
    update_suite,
)

router = APIRouter()


def _format_suite_read(suite) -> QualityRuleSuiteRead:
    """Helper to convert ORM suite into QualityRuleSuiteRead with parsed rule parameters."""
    rules_read = []
    for r in getattr(suite, "rules", []):
        params = {}
        if isinstance(r.parameters, str):
            try:
                params = json.loads(r.parameters)
            except Exception:
                params = {}
        elif isinstance(r.parameters, dict):
            params = r.parameters

        rules_read.append(
            QualityRuleRead(
                id=r.id,
                suite_id=r.suite_id,
                name=r.name,
                rule_type=r.rule_type,
                target_column=r.target_column,
                parameters=params,
                severity=r.severity,
                is_active=r.is_active,
                created_at=r.created_at,
                updated_at=getattr(r, "updated_at", None),
            )
        )

    return QualityRuleSuiteRead(
        id=suite.id,
        workspace_id=suite.workspace_id,
        name=suite.name,
        description=suite.description,
        dataset_id=suite.dataset_id,
        is_active=suite.is_active,
        created_at=suite.created_at,
        updated_at=getattr(suite, "updated_at", None),
        rules=rules_read,
        rules_count=len(rules_read),
    )


@router.post("/suites", response_model=QualityRuleSuiteRead, status_code=status.HTTP_201_CREATED)
async def create_quality_suite(
    suite_in: QualityRuleSuiteCreate,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    current_user: User = Depends(get_current_user),
):
    """Create a new declarative data quality rule suite."""
    workspace, _ = workspace_context
    suite = await create_suite(
        db=db,
        workspace_id=workspace.id,
        suite_in=suite_in,
        user_id=current_user.id,
    )
    return _format_suite_read(suite)


@router.get("/suites", response_model=List[QualityRuleSuiteRead])
async def list_quality_suites(
    dataset_id: Optional[str] = Query(None, description="Filter by target dataset ID"),
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
):
    """List all quality rule suites for the current workspace."""
    workspace, _ = workspace_context
    suites = await list_suites(db=db, workspace_id=workspace.id, dataset_id=dataset_id)
    return [_format_suite_read(s) for s in suites]


@router.get("/suites/{suite_id}", response_model=QualityRuleSuiteRead)
async def get_quality_suite(
    suite_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
):
    """Get details and rules for a specific quality suite."""
    workspace, _ = workspace_context
    suite = await get_suite(db=db, suite_id=suite_id, workspace_id=workspace.id)
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality suite not found")
    return _format_suite_read(suite)


@router.put("/suites/{suite_id}", response_model=QualityRuleSuiteRead)
async def update_quality_suite(
    suite_id: str,
    suite_in: QualityRuleSuiteUpdate,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    _: User = Depends(get_current_user),
):
    """Update metadata for a quality rule suite."""
    workspace, _ = workspace_context
    suite = await update_suite(
        db=db,
        suite_id=suite_id,
        workspace_id=workspace.id,
        suite_in=suite_in,
    )
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality suite not found")
    return _format_suite_read(suite)


@router.delete("/suites/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quality_suite(
    suite_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
    ),
    _: User = Depends(get_current_user),
):
    """Delete a quality rule suite and all child rules."""
    workspace, _ = workspace_context
    deleted = await delete_suite(db=db, suite_id=suite_id, workspace_id=workspace.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality suite not found")
    return None


@router.post("/suites/{suite_id}/rules", response_model=QualityRuleRead, status_code=status.HTTP_201_CREATED)
async def add_rule(
    suite_id: str,
    rule_in: QualityRuleCreate,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    _: User = Depends(get_current_user),
):
    """Add a new validation rule to a suite."""
    workspace, _ = workspace_context
    rule = await add_rule_to_suite(
        db=db,
        suite_id=suite_id,
        workspace_id=workspace.id,
        rule_in=rule_in,
    )
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality suite not found")

    params = {}
    if isinstance(rule.parameters, str):
        try:
            params = json.loads(rule.parameters)
        except Exception:
            params = {}
    elif isinstance(rule.parameters, dict):
        params = rule.parameters

    return QualityRuleRead(
        id=rule.id,
        suite_id=rule.suite_id,
        name=rule.name,
        rule_type=rule.rule_type,
        target_column=rule.target_column,
        parameters=params,
        severity=rule.severity,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=getattr(rule, "updated_at", None),
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    _: User = Depends(get_current_user),
):
    """Delete a single validation rule."""
    workspace, _ = workspace_context
    deleted = await delete_rule(db=db, rule_id=rule_id, workspace_id=workspace.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality rule not found")
    return None


@router.post("/suites/{suite_id}/evaluate", response_model=QualityEvaluationRunRead)
async def run_quality_evaluation(
    suite_id: str,
    eval_req: Optional[QualityEvaluationRequest] = None,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    current_user: User = Depends(get_current_user),
):
    """Execute evaluation for a suite against a dataset."""
    workspace, _ = workspace_context
    target_ds_id = eval_req.dataset_id if eval_req else None
    try:
        run = await evaluate_suite(
            db=db,
            suite_id=suite_id,
            workspace_id=workspace.id,
            dataset_id=target_ds_id,
            user_id=current_user.id,
        )
        return run
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/runs", response_model=List[QualityEvaluationRunRead])
async def list_runs(
    suite_id: Optional[str] = Query(None, description="Filter by suite ID"),
    dataset_id: Optional[str] = Query(None, description="Filter by dataset ID"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
):
    """List historical evaluation runs."""
    workspace, _ = workspace_context
    return await list_evaluation_runs(
        db=db,
        workspace_id=workspace.id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        limit=limit,
    )


@router.get("/runs/{run_id}", response_model=QualityEvaluationRunRead)
async def get_run_details(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
):
    """Get detailed results for an evaluation run."""
    workspace, _ = workspace_context
    run = await get_evaluation_run(db=db, run_id=run_id, workspace_id=workspace.id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found")
    return run


@router.get("/alerts", response_model=List[QualityAlertRead])
async def list_quality_alerts(
    is_acknowledged: Optional[bool] = Query(None, description="Filter by ack status"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: User = Depends(get_current_user),
):
    """List all quality alerts in workspace."""
    workspace, _ = workspace_context
    return await list_alerts(
        db=db,
        workspace_id=workspace.id,
        is_acknowledged=is_acknowledged,
        limit=limit,
    )


@router.post("/alerts/{alert_id}/ack", response_model=QualityAlertRead)
async def acknowledge_quality_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    _: User = Depends(get_current_user),
):
    """Mark an alert as acknowledged."""
    workspace, _ = workspace_context
    alert = await acknowledge_alert(db=db, alert_id=alert_id, workspace_id=workspace.id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert
