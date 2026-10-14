"""Audit logging business service."""

import json
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_audit(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str,
    details: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Record an audit trail event in the persistence store."""
    details_str = json.dumps(details or {})
    entry = AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details_str,
        user_id=user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    return entry
