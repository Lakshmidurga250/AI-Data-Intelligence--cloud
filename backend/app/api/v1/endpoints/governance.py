"""FastAPI endpoints for Data Governance policies, compliance audits, and PII scanning."""

from typing import Any, Dict, List, Optional, Tuple
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
from app.schemas.governance import (
    ComplianceAuditLogRead,
    DatasetGovernanceTagRead,
    DatasetPIIScanResponse,
    GovernancePolicyCreate,
    GovernancePolicyRead,
)
from app.services.governance.service import (
    create_governance_policy,
    delete_governance_policy,
    evaluate_retention_compliance,
    get_governance_policy,
    list_compliance_audit_logs,
    list_dataset_governance_tags,
    list_governance_policies,
    scan_dataset_pii_and_tag,
)

router = APIRouter()


@router.get(
    "/policies",
    response_model=List[GovernancePolicyRead],
    summary="List governance policies for workspace",
)
async def list_policies(
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> List[GovernancePolicyRead]:
    """Retrieve all governance and retention policies for the authenticated workspace."""
    workspace, _ = ws_ctx
    policies = await list_governance_policies(db, workspace.id)
    return [GovernancePolicyRead.model_validate(p) for p in policies]


@router.post(
    "/policies",
    response_model=GovernancePolicyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new governance policy",
)
async def create_policy(
    policy_in: GovernancePolicyCreate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
    ),
    current_user: User = Depends(get_current_user),
) -> GovernancePolicyRead:
    """Create a new data retention and classification policy (Admin only)."""
    workspace, _ = ws_ctx
    policy = await create_governance_policy(db, workspace.id, policy_in)
    return GovernancePolicyRead.model_validate(policy)


@router.delete(
    "/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a governance policy",
)
async def delete_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
    ),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a governance policy by ID (Admin only)."""
    workspace, _ = ws_ctx
    deleted = await delete_governance_policy(db, workspace.id, policy_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Governance policy not found",
        )


@router.post(
    "/classify/{dataset_id}",
    response_model=DatasetPIIScanResponse,
    summary="Execute automated PII classification scan on dataset",
)
async def classify_dataset(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
    current_user: User = Depends(get_current_user),
) -> DatasetPIIScanResponse:
    """Scan dataset columns for PII and sensitive data patterns, assign tags and audit log."""
    workspace, _ = ws_ctx
    scan_res = await scan_dataset_pii_and_tag(
        db,
        workspace_id=workspace.id,
        dataset_id=dataset_id,
        actor_email=current_user.email,
    )
    if not scan_res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found in this workspace",
        )
    return scan_res


@router.get(
    "/tags/{dataset_id}",
    response_model=List[DatasetGovernanceTagRead],
    summary="Get governance sensitivity tags for dataset",
)
async def get_dataset_tags(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> List[DatasetGovernanceTagRead]:
    """Retrieve sensitivity classification tags for dataset columns."""
    workspace, _ = ws_ctx
    return await list_dataset_governance_tags(db, workspace.id, dataset_id)


@router.get(
    "/audit-logs",
    response_model=List[ComplianceAuditLogRead],
    summary="List compliance audit logs",
)
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> List[ComplianceAuditLogRead]:
    """Retrieve immutable compliance audit logs for the workspace."""
    workspace, _ = ws_ctx
    logs = await list_compliance_audit_logs(db, workspace.id, limit=limit)
    return [ComplianceAuditLogRead.model_validate(l) for l in logs]


@router.post(
    "/retention/evaluate",
    response_model=Dict[str, Any],
    summary="Evaluate retention compliance for workspace datasets",
)
async def evaluate_retention(
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
    ),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Evaluate all datasets against active retention policies and report purge candidates."""
    workspace, _ = ws_ctx
    return await evaluate_retention_compliance(db, workspace.id, actor_email=current_user.email)
