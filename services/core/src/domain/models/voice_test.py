import uuid
from enum import Enum

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .bloom import BloomLevel
from .mixins import IdMixin, TimestampMixin


class TestStatus(str, Enum):
    """DRAFT -> SCHEDULED -> ACTIVE -> COMPLETED -> RESULTS_PROCESSING ->
    RESULTS_READY. Each is a real, distinct state - never collapsed.
    """

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    RESULTS_PROCESSING = "RESULTS_PROCESSING"
    RESULTS_READY = "RESULTS_READY"


class AssignmentTargetMode(str, Enum):
    WHOLE_CLASS = "WHOLE_CLASS"
    SPECIFIC_STUDENTS = "SPECIFIC_STUDENTS"


class VoiceTest(IdMixin, TimestampMixin, Base):
    __tablename__ = "voice_tests"

    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chapters.id"))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True
    )
    duration_minutes: Mapped[int] = mapped_column(Integer)
    completion_window_hours: Mapped[int] = mapped_column(Integer)
    target_mode: Mapped[AssignmentTargetMode] = mapped_column(
        SAEnum(AssignmentTargetMode, name="assignment_target_mode")
    )
    status: Mapped[TestStatus] = mapped_column(
        SAEnum(TestStatus, name="test_status"), default=TestStatus.DRAFT
    )
    assigned_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)


class VoiceTestBloomLevel(Base):
    __tablename__ = "voice_test_bloom_levels"
    __table_args__ = (UniqueConstraint("test_id", "bloom_level"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("voice_tests.id"))
    bloom_level: Mapped[BloomLevel] = mapped_column(SAEnum(BloomLevel, name="bloom_level"))


class VoiceTestTargetStudent(Base):
    """The real per-student delivery list for every Test, regardless of
    target_mode - every read path a student's own app uses to find "my
    assigned tests" joins through this table. For SPECIFIC_STUDENTS these
    rows come straight from the teacher's picked list; for WHOLE_CLASS
    they're resolved from the class roster once, at creation time (see
    voice_test.py's create_test) - either way, this table is always the
    complete, queryable answer to "who was this test actually sent to."
    """

    __tablename__ = "voice_test_target_students"
    __table_args__ = (UniqueConstraint("test_id", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("voice_tests.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
