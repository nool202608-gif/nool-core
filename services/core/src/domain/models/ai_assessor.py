import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .bloom import BloomLevel
from .mixins import IdMixin, TimestampMixin


class AiAssessorSession(IdMixin, TimestampMixin, Base):
    """Powers both the Test and Retest voice conversation - one session
    contract reused for either (see services/voice/AiAssessorSession.ts).
    Exactly one of test_id/retest_attempt_id is set. The realtime
    conversation itself (WS handler) is driven by a deterministic
    ContentGenerator, not a real voice/LLM vendor - see CLAUDE.md's
    "Current Goal".
    """

    __tablename__ = "ai_assessor_sessions"

    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    test_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_tests.id"), nullable=True
    )
    retest_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retest_attempts.id"), nullable=True
    )
    context_label: Mapped[str] = mapped_column(String)
    duration_seconds: Mapped[int] = mapped_column(Integer)


class AiAssessorSessionBloomLevel(Base):
    __tablename__ = "ai_assessor_session_bloom_levels"
    __table_args__ = (UniqueConstraint("session_id", "bloom_level"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_assessor_sessions.id")
    )
    bloom_level: Mapped[BloomLevel] = mapped_column(SAEnum(BloomLevel, name="bloom_level"))
