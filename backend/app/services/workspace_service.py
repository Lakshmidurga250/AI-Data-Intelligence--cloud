"""Workspace management and multi-tenant authorization service."""

import re
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.membership import WorkspaceMembership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.models.audit import AuditLog
from app.schemas.workspace import WorkspaceMemberRead, WorkspaceRead
from app.services.audit_service import log_audit


def generate_slug(name: str) -> str:
    """Create a URL-safe slug from a workspace name."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip().lower()
    slug = re.sub(r"[\s-]+", "-", cleaned)
    if not slug:
        slug = f"workspace-{uuid.uuid4().hex[:8]}"
    return slug


async def create_workspace(
    db: AsyncSession,
    owner: User,
    name: str,
    slug: Optional[str] = None,
    description: Optional[str] = None,
) -> Workspace:
    """Create a new workspace and assign owner membership."""
    target_slug = slug or generate_slug(name)

    # Check for existing slug and deduplicate if necessary
    existing_query = await db.execute(select(Workspace).where(Workspace.slug == target_slug))
    if existing_query.scalar_one_or_none():
        target_slug = f"{target_slug}-{uuid.uuid4().hex[:6]}"

    workspace = Workspace(
        name=name,
        slug=target_slug,
        description=description,
        owner_id=owner.id,
    )
    db.add(workspace)
    await db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=owner.id,
        role=WorkspaceRole.OWNER.value,
    )
    db.add(membership)
    await db.flush()

    await log_audit(
        db,
        action="workspace.create",
        resource_type="workspace",
        resource_id=workspace.id,
        details={"name": name, "slug": target_slug},
        user_id=owner.id,
        workspace_id=workspace.id,
    )

    return workspace


async def get_user_workspaces(db: AsyncSession, user_id: str) -> List[WorkspaceRead]:
    """Retrieve all workspaces the user has access to along with their role."""
    query = (
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership, Workspace.id == WorkspaceMembership.workspace_id)
        .where(WorkspaceMembership.user_id == user_id)
        .order_by(Workspace.created_at.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    workspaces: List[WorkspaceRead] = []
    for ws, role in rows:
        item = WorkspaceRead(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            description=ws.description,
            owner_id=ws.owner_id,
            created_at=ws.created_at,
            role=role,
        )
        workspaces.append(item)
    return workspaces


async def get_workspace_by_id(db: AsyncSession, workspace_id: str) -> Optional[Workspace]:
    """Fetch a workspace entity by ID."""
    query = select(Workspace).where(Workspace.id == workspace_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_workspace_membership(
    db: AsyncSession, workspace_id: str, user_id: str
) -> Optional[WorkspaceMembership]:
    """Retrieve membership and role for a user within a workspace."""
    query = select(WorkspaceMembership).where(
        WorkspaceMembership.workspace_id == workspace_id,
        WorkspaceMembership.user_id == user_id,
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_workspace_members(
    db: AsyncSession, workspace_id: str
) -> List[WorkspaceMemberRead]:
    """List all members of a workspace."""
    query = (
        select(WorkspaceMembership, User.email, User.full_name)
        .join(User, WorkspaceMembership.user_id == User.id)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(WorkspaceMembership.created_at.asc())
    )
    result = await db.execute(query)
    rows = result.all()

    members: List[WorkspaceMemberRead] = []
    for m, email, name in rows:
        members.append(
            WorkspaceMemberRead(
                id=m.id,
                workspace_id=m.workspace_id,
                user_id=m.user_id,
                role=m.role,
                created_at=m.created_at,
                user_email=email,
                user_name=name,
            )
        )
    return members


async def add_workspace_member(
    db: AsyncSession,
    workspace_id: str,
    target_user: User,
    role: WorkspaceRole,
    inviter: User,
) -> WorkspaceMembership:
    """Add a new member to an isolated workspace."""
    existing = await get_workspace_membership(db, workspace_id, target_user.id)
    if existing:
        existing.role = role.value
        membership = existing
    else:
        membership = WorkspaceMembership(
            workspace_id=workspace_id,
            user_id=target_user.id,
            role=role.value,
        )
        db.add(membership)

    await db.flush()

    await log_audit(
        db,
        action="workspace.member_added",
        resource_type="membership",
        resource_id=membership.id,
        details={"target_email": target_user.email, "role": role.value},
        user_id=inviter.id,
        workspace_id=workspace_id,
    )

    return membership


async def get_workspace_audit_logs(
    db: AsyncSession, workspace_id: str, limit: int = 50
) -> List[AuditLog]:
    """Fetch recent audit log entries for a workspace."""
    query = (
        select(AuditLog)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return list(result.scalars().all())
