import uuid
from enum import Enum

from sqlalchemy import ForeignKey, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import IdMixin, TimestampMixin


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class AssistantMessage(IdMixin, TimestampMixin, Base):
    """One running thread per teacher, not threaded/multi-session - see
    services/domain/AssistantService.ts. A rule-based responder, not a
    real LLM integration (nool-apps' own scope discipline explicitly
    excludes real AI backend work; nothing here changes that).
    """

    __tablename__ = "assistant_messages"

    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    role: Mapped[ChatRole] = mapped_column(SAEnum(ChatRole, name="chat_role"))
    text: Mapped[str] = mapped_column(Text)
