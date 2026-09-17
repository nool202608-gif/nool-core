import uuid
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .bloom import BloomLevel
from .custom_question import QuestionType
from .mixins import IdMixin, TimestampMixin


class DatasetType(str, Enum):
    """What kind of content a Dataset actually holds - the two mechanisms
    this app has built are otherwise indistinguishable except by
    inspecting which columns happen to be filled in:

    QA - a hand-curated bank of ready-made question/answer pairs
    (DatasetQuestion rows), the same shape as CustomQuestion. This is the
    default, and what every Dataset was before PRIMARY_CONTENT existed.

    PRIMARY_CONTENT - raw ingested source material (a textbook) backing a
    knowledge-graph Curriculum root (board+grade+subject_id all set) - see
    Dataset's docstring on those three columns. Grounds real, on-demand
    LLM generation (services/kg's /question-papers/generate) rather than
    storing questions ahead of time; a PRIMARY_CONTENT dataset's own
    `question_count`/DatasetQuestion rows are therefore not meaningful and
    expected to stay empty.

    Every KG-facing code path (sync_curriculum_from_kg, `_paper_kg_identity`)
    checks this explicitly rather than only inferring it from board/grade
    being set, so a QA dataset can never be accidentally treated as a KG
    root even if those columns end up populated by mistake.
    """

    QA = "QA"
    PRIMARY_CONTENT = "PRIMARY_CONTENT"


class Dataset(IdMixin, Base):
    """A global question-bank catalog used as the grounding pool for
    Homework and Question Paper generation. `subject_id` ties a dataset to
    the one Subject it belongs to (a Subject can have many Datasets - e.g.
    separate "Algebra" and "Geometry" datasets both under Math). Nullable
    so pre-existing datasets created before this column existed, or a
    genuinely cross-subject dataset, aren't forced to pick one.

    `board`/`grade` (also nullable, same reasoning as `subject_id`) name
    which knowledge-graph Curriculum root (see services/kg's
    Curriculum{board, grade, subject} node) this dataset corresponds to -
    a dataset like "10th Science" *is* that KG root, with its chapters/
    topics underneath it, not a separate concept from it. Together with
    `subject_id` these are what lets Question Paper (and, later, Homework)
    generation resolve "which part of the knowledge graph does this
    dataset mean" instead of only ever using the paper's own board/grade -
    see question_paper.py's `_paper_kg_identity`. Only meaningful for a
    `type == PRIMARY_CONTENT` dataset - see DatasetType.

    `question_count` stays as a plain stored column for a dataset that's
    only ever been described manually (no real DatasetQuestion rows yet) -
    see GET /admin/datasets' resolution: real row count wins once any
    DatasetQuestion rows exist, this manual value is the fallback only.

    `restricted` (default False) flips GET /datasets' "school hasn't
    configured anything yet -> show every dataset" fallback (see
    dataset.py) for this one dataset: a restricted dataset is invisible to
    every school by default, and only shows up for a school with an
    explicit SchoolDataset(enabled=True) row for it - e.g. a large
    question bank meant only for one specific school's Science subject,
    not the shared default catalog every school implicitly gets.
    """

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String)
    question_count: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    type: Mapped[DatasetType] = mapped_column(
        SAEnum(DatasetType, name="dataset_type"), default=DatasetType.QA
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    board: Mapped[str | None] = mapped_column(String, nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
