"""AI Assistant and Conversational Analytics entities."""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.user import User
    from app.models.workspace import Workspace


class AssistantConversation(Base, UUIDMixin, TimestampMixin):
    """Conversational intelligence thread scoped to a workspace."""

    __tablename__ = "assistant_conversations"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New Conversation")
    active_dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    user: Mapped[Optional["User"]] = relationship("User")
    active_dataset: Mapped[Optional["Dataset"]] = relationship("Dataset")
    messages: Mapped[List["AssistantMessage"]] = relationship(
        "AssistantMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AssistantMessage.created_at.asc()",
    )


class AssistantMessage(Base, UUIDMixin, TimestampMixin):
    """Individual message turn in an assistant conversation."""

    __tablename__ = "assistant_messages"

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # "user", "assistant", "system"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    execution_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    conversation: Mapped["AssistantConversation"] = relationship(
        "AssistantConversation", back_populates="messages"
    )
