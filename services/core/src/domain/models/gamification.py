import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class StudentGamification(Base):
    """Level/XP snapshot - one row per student, lazily created on first
    GET (see src/api/routes/gamification.py's `_get_or_create_state`).
    Daily-goal completion and achievements are derived elsewhere
    (StudentDailyGoalCompletion below, and live queries against
    StudentTestResult/StudentChapterProgress/the learning-streak
    calculation) - not stored on this row.
    """

    __tablename__ = "student_gamification"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    level: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    xp_for_next_level: Mapped[int] = mapped_column(Integer, default=500)


class StudentDailyGoalCompletion(Base):
    """One row per (student, goal, calendar day) completed. The goal
    catalog itself (title/xp_reward) is a small fixed in-code list - see
    gamification.py's DAILY_GOAL_CATALOG - not stored here. Keying
    completion by calendar day rather than a single boolean is what makes
    "daily" actually reset without a cron job: a row from yesterday
    simply doesn't match today's query.
    """

    __tablename__ = "student_daily_goal_completions"
    __table_args__ = (UniqueConstraint("student_id", "goal_key", "completed_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    goal_key: Mapped[str] = mapped_column(String)
    completed_date: Mapped[date] = mapped_column(Date)
