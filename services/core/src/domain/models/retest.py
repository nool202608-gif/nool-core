import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .bloom import BloomLevel
from .mixins import IdMixin


class StudentRetestStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    RESULT_READY = "RESULT_READY"


class RetestAttempt(IdMixin, Base):
    """maxAttempts is always 1 per the reference contract - enforced in
    the service layer (a second attempt raises ConflictError), not here.
    """

    __tablename__ = "retest_attempts"
    __table_args__ = (UniqueConstraint("homework_id", "student_id"),)

    homework_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("homework.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[StudentRetestStatus] = mapped_column(
        SAEnum(StudentRetestStatus, name="student_retest_status"),
        default=StudentRetestStatus.ASSIGNED,
    )
    attempts_used: Mapped[int] = mapped_column(Integer, default=0)
    baseline_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retest_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    improvement_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetestBloomComparison(Base):
    __tablename__ = "retest_bloom_comparison"
    __table_args__ = (UniqueConstraint("retest_attempt_id", "bloom_level"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    retest_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retest_attempts.id")
    )
    bloom_level: Mapped[BloomLevel] = mapped_column(SAEnum(BloomLevel, name="bloom_level"))
    before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after: Mapped[int | None] = mapped_column(Integer, nullable=True)
