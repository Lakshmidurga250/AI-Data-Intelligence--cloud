"""REST API endpoints for Conversational Analytics & AI Data Intelligence Assistant."""

from typing import List, Tuple
from fastapi import APIRouter, Depends, Query, status
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
from app.schemas.assistant import (
    AssistantChatResponse,
    ChatMessageCreate,
    ConversationCreate,
    ConversationDetailRead,
    ConversationRead,
    InsightReportResponse,
)
from app.services.assistant.service import (
    create_conversation,
    delete_conversation,
    generate_dataset_insights,
    get_conversation,
    list_conversations,
    post_chat_message,
)

router = APIRouter()


@router.get(
    "/conversations",
    response_model=List[ConversationRead],
    summary="List assistant conversations for active workspace",
)
async def get_conversations_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all conversational assistant threads in the active workspace."""
    workspace, _ = ws_ctx
    return await list_conversations(
        db=db,
        workspace_id=workspace.id,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create assistant conversation thread",
)
async def create_conversation_endpoint(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
):
    """Create a new conversational AI thread."""
    workspace, _ = ws_ctx
    return await create_conversation(
        db=db,
        workspace_id=workspace.id,
        user_id=current_user.id,
        payload=payload,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailRead,
    summary="Get conversation detail with message history",
)
async def get_conversation_endpoint(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    """Retrieve full conversation trajectory with ordered messages."""
    workspace, _ = ws_ctx
    return await get_conversation(
        db=db,
        workspace_id=workspace.id,
        conversation_id=conversation_id,
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete assistant conversation thread",
)
async def delete_conversation_endpoint(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
    ),
):
    """Delete a conversation thread and all nested messages."""
    workspace, _ = ws_ctx
    await delete_conversation(
        db=db,
        workspace_id=workspace.id,
        conversation_id=conversation_id,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AssistantChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send message and receive assistant response",
)
async def post_message_endpoint(
    conversation_id: str,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
):
    """Send a user prompt to the AI Data Intelligence Assistant and get analytical response."""
    workspace, _ = ws_ctx
    return await post_chat_message(
        db=db,
        workspace_id=workspace.id,
        user_id=current_user.id,
        conversation_id=conversation_id,
        payload=payload,
    )


@router.post(
    "/insights/{dataset_id}",
    response_model=InsightReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Run automated anomaly and trend discovery on dataset",
)
async def get_dataset_insights_endpoint(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    """Scan dataset for statistical anomalies, missing value severity, outliers, and correlations."""
    workspace, _ = ws_ctx
    return await generate_dataset_insights(
        db=db,
        workspace_id=workspace.id,
        dataset_id=dataset_id,
    )
