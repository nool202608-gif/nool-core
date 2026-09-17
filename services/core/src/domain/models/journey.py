import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class StudentChapterProgress(Base):
    """One row per (student, chapter) the student has made any progress
    on. `completed_at` not null is what src/api/routes/journey.py treats
    as "DONE"; the first not-done chapter (in `Chapter.order_index` order)
    for a subject is "CURRENT", everything after that is "LOCKED" - not
    stored, computed at read time from this table plus chapter order.
    """

    __tablename__ = "student_chapter_progress"
    __table_args__ = (UniqueConstraint("student_id", "chapter_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chapters.id"))
    stars: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
