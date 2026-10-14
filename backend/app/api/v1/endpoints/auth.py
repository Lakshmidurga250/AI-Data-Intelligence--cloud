"""Authentication and identity endpoints."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserLogin, UserRead
from app.schemas.workspace import WorkspaceRead
from app.services.user_service import authenticate_user, create_user
from app.services.workspace_service import get_user_workspaces

router = APIRouter(prefix="/auth", tags=["Identity & Authentication"])


class UserProfileResponse(UserRead):
    """Profile payload including active tenant workspaces."""

    workspaces: List[WorkspaceRead] = []


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Register a new user account and auto-provision an isolated personal workspace.
    Returns access token for immediate platform access.
    """
    client_ip = request.client.host if request.client else None
    try:
        user, _ = await create_user(db, user_in, ip_address=client_ip)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    access_token = create_access_token(subject=user.id)
    return Token(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
    )


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Authenticate with email and password via JSON payload."""
    client_ip = request.client.host if request.client else None
    user = await authenticate_user(
        db,
        email=credentials.email,
        password=credentials.password,
        ip_address=client_ip,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.id)
    return Token(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
    )


@router.post("/login/oauth", response_model=Token, include_in_schema=False)
async def login_oauth_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    """OAuth2 password form compatible endpoint for OpenAPI docs interactive testing."""
    client_ip = request.client.host if request.client else None
    user = await authenticate_user(
        db,
        email=form_data.username,
        password=form_data.password,
        ip_address=client_ip,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.id)
    return Token(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Retrieve profile of the currently authenticated user including workspaces."""
    user_workspaces = await get_user_workspaces(db, current_user.id)
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at,
        workspaces=user_workspaces,
    )
