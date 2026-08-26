import uuid

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class StudentPoints(Base):
    """Game-like mastery score, NOT a raw test percent - see
    types/domain/leaderboard.ts. Rank is computed at query time via a
    window function, never stored.
    """

    __tablename__ = "student_points"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    points: Mapped[int] = mapped_column(Integer, default=0)
