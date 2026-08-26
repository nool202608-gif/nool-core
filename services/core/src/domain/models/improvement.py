import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import IdMixin


class TopicPerformance(IdMixin, Base):
    """Per-topic before/after breakdown for a Test->Homework->Retest loop -
    the one table with no direct 1:1 TS type, needed because
    TopicImprovement's granularity isn't derivable from the coarser
    bloom/test-result tables alone. before_percent is captured from the
    original Test; after_percent is filled in once the Retest completes.
    """

    __tablename__ = "topic_performance"

    test_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("voice_tests.id"))
    homework_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("homework.id"))
    topic_label: Mapped[str] = mapped_column(Text)
    before_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
