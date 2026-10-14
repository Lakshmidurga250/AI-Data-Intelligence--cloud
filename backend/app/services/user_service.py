"""User domain service for authentication and account management."""

from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.user import UserCreate
from app.services.audit_service import log_audit
from app.services.workspace_service import create_workspace


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Look up a user entity by case-insensitive email address."""
    query = select(User).where(User.email == email.lower().strip())
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    """Look up a user entity by primary key ID."""
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    user_in: UserCreate,
    ip_address: Optional[str] = None,
) -> Tuple[User, Workspace]:
    """
    Register a new user account, hash the password, and auto-provision
    a default personal workspace for immediate isolated tenancy.
    """
    existing = await get_user_by_email(db, user_in.email)
    if existing:
        raise ValueError("A user with this email address already exists.")

    hashed_pw = get_password_hash(user_in.password)
    user = User(
        email=user_in.email.lower().strip(),
        full_name=user_in.full_name.strip(),
        hashed_password=hashed_pw,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()

    # Provision default isolated personal workspace
    default_ws_name = f"{user.full_name}'s Workspace"
    default_ws = await create_workspace(
        db,
        owner=user,
        name=default_ws_name,
        description=f"Personal isolated workspace for {user.full_name}",
    )

    await log_audit(
        db,
        action="auth.register",
        resource_type="user",
        resource_id=user.id,
        details={"email": user.email, "default_workspace_id": default_ws.id},
        user_id=user.id,
        workspace_id=default_ws.id,
        ip_address=ip_address,
    )

    return user, default_ws


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    ip_address: Optional[str] = None,
) -> Optional[User]:
    """Verify email and password credentials, returning User if valid."""
    user = await get_user_by_email(db, email)
    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if not user.is_active:
        return None

    await log_audit(
        db,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        details={"email": user.email},
        user_id=user.id,
        ip_address=ip_address,
    )

    return user
