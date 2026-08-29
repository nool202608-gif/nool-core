import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .bloom import BloomLevel
from .custom_question import QuestionType
from .mixins import IdMixin, TimestampMixin


class Dataset(IdMixin, Base):
    """A global question-bank catalog used as the grounding pool for
    Homework and Question Paper generation. `subject_id` ties a dataset to
    the one Subject it belongs to (a Subject can have many Datasets - e.g.
    separate "Algebra" and "Geometry" datasets both under Math). Nullable
    so pre-existing datasets created before this column existed, or a
    genuinely cross-subject dataset, aren't forced to pick one.

    `question_count` stays as a plain stored column for a dataset that's
    only ever been described manually (no real DatasetQuestion rows yet) -
    see GET /admin/datasets' resolution: real row count wins once any
    DatasetQuestion rows exist, this manual value is the fallback only.
    """

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String)
    question_count: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)


class DatasetQuestion(IdMixin, TimestampMixin, Base):
    """One real question in a Dataset's own question bank - the actual
    content GET /admin/datasets previously only described via a manually-
    typed `question_count` integer (see requirements.md's flagged gap:
    "no linkage between a Dataset row and actual generated questions
    anywhere in the schema"). Same shape as CustomQuestion (School Admin's
    own per-school content) but scoped to a Dataset instead of a school,
    since this is Super-Admin-owned shared catalog content, not one
    school's private bank. chapter_id/topic_id are optional refinement
    within the Dataset's own subject, not required the way CustomQuestion
    requires chapter_id - a curator can add a question to the bank without
    committing to exact placement yet.
    """

    __tablename__ = "dataset_questions"

    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)
    bloom_level: Mapped[BloomLevel] = mapped_column(SAEnum(BloomLevel, name="bloom_level"))
    question_type: Mapped[QuestionType] = mapped_column(SAEnum(QuestionType, name="question_type"))
    text: Mapped[str] = mapped_column(Text)
    # Only meaningful for MCQ/TRUE_FALSE - see CustomQuestion's identical
    # column for the same reasoning (validated in the schema layer, not
    # here - see CreateDatasetQuestionIn).
    options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    answer: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class SchoolDataset(IdMixin, Base):
    """Which datasets a school has enabled - see PUT /api/v1/school/datasets.
    Scopes what a Teacher at that school sees in GET /api/v1/datasets, the
    same way SchoolCurriculum scopes GET /api/v1/subjects.
    """

    __tablename__ = "school_datasets"
    __table_args__ = (UniqueConstraint("school_id", "dataset_id"),)

    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
