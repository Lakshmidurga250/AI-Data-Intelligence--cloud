"""FastAPI dependency injection utilities for DB sessions, authentication, and workspace isolation."""

from typing import AsyncGenerator, Callable, List, Optional, Tuple
from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_async_session
from app.models.membership import WorkspaceMembership
from app.models.user import User
from app.models.workspace import Workspace
from app.services.user_service import get_user_by_id
from app.services.workspace_service import get_workspace_by_id, get_workspace_membership

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an asynchronous database session."""
    async for session in get_async_session():
        yield session


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
) -> User:
    """Validate JWT bearer token and return the authenticated User."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload["sub"]
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token was not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


async def get_current_workspace(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_workspace_id: Optional[str] = Header(None, alias="X-Workspace-ID"),
    workspace_id: Optional[str] = Query(None),
) -> Tuple[Workspace, WorkspaceMembership]:
    """
    Enforce tenant workspace isolation boundary.
    Extracts the target workspace ID from the header or query parameter,
    and verifies that the authenticated user holds valid membership in that workspace.
    """
    target_id = x_workspace_id or workspace_id
    if not target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace context required. Provide X-Workspace-ID header or workspace_id parameter.",
        )

    workspace = await get_workspace_by_id(db, target_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{target_id}' was not found.",
        )

    membership = await get_workspace_membership(db, target_id, current_user.id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. You do not hold membership in workspace '{target_id}'.",
        )

    return workspace, membership


def require_workspace_role(allowed_roles: List[str]) -> Callable:
    """Factory creating a dependency that enforces workspace RBAC roles."""

    async def role_checker(
        workspace_context: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    ) -> Tuple[Workspace, WorkspaceMembership]:
        workspace, membership = workspace_context
        if membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action requires one of the following roles: {allowed_roles}. Current role: '{membership.role}'.",
            )
        return workspace, membership

    return role_checker
