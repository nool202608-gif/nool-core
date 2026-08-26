import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .bloom import BloomLevel
from .mixins import IdMixin
from .voice_test import AssignmentTargetMode


class HomeworkStatus(str, Enum):
    """GENERATING -> REVIEW -> ASSIGNED -> IN_PROGRESS -> COMPLETED, or
    FAILED off GENERATING.
    """

    GENERATING = "GENERATING"
    REVIEW = "REVIEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class HomeworkDifficulty(str, Enum):
    EASY = "EASY"
    MIXED = "MIXED"
    HARD = "HARD"


class StudentHomeworkStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class Homework(IdMixin, Base):
    __tablename__ = "homework"

    test_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("voice_tests.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"))
    gap_topic: Mapped[str] = mapped_column(Text)
    gap_mastery_percent: Mapped[int] = mapped_column(Integer)
    total_questions: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[HomeworkDifficulty] = mapped_column(
        SAEnum(HomeworkDifficulty, name="homework_difficulty")
    )
    target_mode: Mapped[AssignmentTargetMode] = mapped_column(
        SAEnum(AssignmentTargetMode, name="assignment_target_mode")
    )
    completion_window_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[HomeworkStatus] = mapped_column(
        SAEnum(HomeworkStatus, name="homework_status"), default=HomeworkStatus.GENERATING
    )
    assigned_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)


class HomeworkDataset(Base):
    __tablename__ = "homework_datasets"
    __table_args__ = (UniqueConstraint("homework_id", "dataset_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    homework_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("homework.id"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"))


class HomeworkBloomDistribution(Base):
    __tablename__ = "homework_bloom_distribution"
    __table_args__ = (UniqueConstraint("homework_id", "bloom_level"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    homework_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("homework.id"))
    bloom_level: Mapped[BloomLevel] = mapped_column(SAEnum(BloomLevel, name="bloom_level"))
    value: Mapped[int] = mapped_column(Integer)


class HomeworkTargetStudent(Base):
    """Only populated when target_mode is SPECIFIC_STUDENTS."""

    __tablename__ = "homework_target_students"
    __table_args__ = (UniqueConstraint("homework_id", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    homework_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("homework.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class HomeworkQuestion(IdMixin, Base):
    __tablename__ = "homework_questions"

    homework_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("homework.id"))
    order: Mapped[int] = mapped_column(Integer)
    bloom_level: Mapped[BloomLevel] = mapped_column(SAEnum(BloomLevel, name="bloom_level"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    text: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)


class StudentHomeworkProgress(IdMixin, Base):
    """Per-student assignment/completion state - backs the teacher's
    assignedCount/completedCount rollups and the student-facing
    StudentHomeworkOverview (GET /api/v1/me/homework/current).
    """

    __tablename__ = "student_homework_progress"
    __table_args__ = (UniqueConstraint("homework_id", "student_id"),)

    homework_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("homework.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[StudentHomeworkStatus] = mapped_column(
        SAEnum(StudentHomeworkStatus, name="student_homework_status"),
        default=StudentHomeworkStatus.ASSIGNED,
    )
    qa_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired: Mapped[bool] = mapped_column(Boolean, default=False)
