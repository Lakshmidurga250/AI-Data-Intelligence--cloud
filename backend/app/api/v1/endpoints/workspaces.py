"""Workspace multi-tenant management and RBAC endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
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
from app.schemas.audit import AuditLogRead
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberRead,
    WorkspaceRead,
)
from app.services.user_service import get_user_by_email
from app.services.workspace_service import (
    add_workspace_member,
    create_workspace,
    get_user_workspaces,
    get_workspace_audit_logs,
    get_workspace_by_id,
    get_workspace_members,
    get_workspace_membership,
)

router = APIRouter(prefix="/workspaces", tags=["Workspace Tenancy & RBAC"])


@router.get("", response_model=List[WorkspaceRead])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[WorkspaceRead]:
    """List all isolated tenant workspaces that the user has access to."""
    return await get_user_workspaces(db, current_user.id)


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_new_workspace(
    ws_in: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceRead:
    """Create a new isolated workspace. Current user becomes the workspace Owner."""
    ws = await create_workspace(
        db,
        owner=current_user,
        name=ws_in.name,
        slug=ws_in.slug,
        description=ws_in.description,
    )
    return WorkspaceRead(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        description=ws.description,
        owner_id=ws.owner_id,
        created_at=ws.created_at,
        role=WorkspaceRole.OWNER.value,
    )


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace_details(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceRead:
    """
    Retrieve details of a specific workspace.
    Enforces that the user is a registered member of this workspace.
    """
    membership = await get_workspace_membership(db, workspace_id, current_user.id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not hold membership in this workspace.",
        )

    ws = await get_workspace_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )
    return WorkspaceRead(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        description=ws.description,
        owner_id=ws.owner_id,
        created_at=ws.created_at,
        role=membership.role,
    )


@router.get("/{workspace_id}/members", response_model=List[WorkspaceMemberRead])
async def list_members(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[WorkspaceMemberRead]:
    """List all members and their roles within the workspace."""
    membership = await get_workspace_membership(db, workspace_id, current_user.id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not hold membership in this workspace.",
        )

    return await get_workspace_members(db, workspace_id)


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    workspace_id: str,
    member_in: WorkspaceMemberCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberRead:
    """
    Add a user to the workspace. Requires Owner or Admin role in the workspace.
    """
    caller_membership = await get_workspace_membership(db, workspace_id, current_user.id)
    if not caller_membership or caller_membership.role not in [
        WorkspaceRole.OWNER.value,
        WorkspaceRole.ADMIN.value,
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace Owners and Admins can manage workspace memberships.",
        )

    target_user = await get_user_by_email(db, member_in.email)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email '{member_in.email}' does not exist on the platform.",
        )

    membership = await add_workspace_member(
        db,
        workspace_id=workspace_id,
        target_user=target_user,
        role=member_in.role,
        inviter=current_user,
    )

    return WorkspaceMemberRead(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=membership.user_id,
        role=membership.role,
        created_at=membership.created_at,
        user_email=target_user.email,
        user_name=target_user.full_name,
    )


@router.get("/{workspace_id}/audit-logs", response_model=List[AuditLogRead])
async def get_audit_logs(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AuditLogRead]:
    """Retrieve immutable audit trail for the workspace. Requires Owner or Admin role."""
    caller_membership = await get_workspace_membership(db, workspace_id, current_user.id)
    if not caller_membership or caller_membership.role not in [
        WorkspaceRole.OWNER.value,
        WorkspaceRole.ADMIN.value,
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace Owners and Admins can access workspace audit logs.",
        )

    logs = await get_workspace_audit_logs(db, workspace_id)
    return [
        AuditLogRead(
            id=log.id,
            workspace_id=log.workspace_id,
            user_id=log.user_id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at,
        )
        for log in logs
    ]
