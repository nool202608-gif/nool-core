from datetime import datetime

from pydantic import model_validator

from src.domain.models import BloomLevel, DatasetType, QuestionType

from .common import CamelModel

_CHOICE_TYPES = (QuestionType.MCQ, QuestionType.TRUE_FALSE)


class SubjectOut(CamelModel):
    id: str
    name: str


class CreateSubjectIn(CamelModel):
    name: str


class UpdateSubjectIn(CamelModel):
    name: str


class SyncFromKgResultOut(CamelModel):
    dataset_id: str
    dataset_name: str
    subject: str
    board: str
    grade: int
    chapters_synced: int
    topics_synced: int


class SyncFromKgOut(CamelModel):
    # One entry per Dataset that names a KG root (board+grade+subject_id
    # all set) - a Dataset like "10th Science" IS that root, so syncing is
    # inherently per-dataset now, not a single hardcoded pull. Empty is a
    # legitimate outcome (no dataset names a KG root yet), not an error.
    results: list[SyncFromKgResultOut]


class ChapterOut(CamelModel):
    id: str
    subject_id: str
    name: str


class CreateChapterIn(CamelModel):
    name: str


class UpdateChapterIn(CamelModel):
    name: str


class TopicOut(CamelModel):
    id: str
    chapter_id: str
    name: str


class CreateTopicIn(CamelModel):
    name: str


class UpdateTopicIn(CamelModel):
    name: str


class DatasetOut(CamelModel):
    id: str
    name: str
    # The real count of DatasetQuestion rows once any exist; falls back to
    # the manually-typed value for a dataset with no real content yet -
    # see Dataset.question_count's docstring.
    question_count: int
    description: str
    subject_id: str | None = None
    # Which kg-service Curriculum root this dataset corresponds to - see
    # Dataset's docstring. Null until a Super Admin sets them.
    board: str | None = None
    grade: int | None = None
    # False (the default catalog) or True (hidden unless a school
    # explicitly enables it) - see Dataset.restricted's docstring.
    restricted: bool = False
    # QA (a hand-curated question/answer bank) or PRIMARY_CONTENT (raw
    # ingested source content backing a KG Curriculum root) - see
    # DatasetType's docstring.
    type: DatasetType = DatasetType.QA


class CreateDatasetIn(CamelModel):
    name: str
    question_count: int
    description: str
    subject_id: str | None = None
    board: str | None = None
    grade: int | None = None
    restricted: bool = False
    type: DatasetType = DatasetType.QA


class UpdateDatasetIn(CamelModel):
    name: str | None = None
    question_count: int | None = None
    description: str | None = None
    subject_id: str | None = None
    board: str | None = None
    grade: int | None = None
    restricted: bool | None = None
    type: DatasetType | None = None


class DatasetQuestionOut(CamelModel):
    id: str
    dataset_id: str
    chapter_id: str | None
    topic_id: str | None
    bloom_level: BloomLevel
    question_type: QuestionType
    text: str
    options: list[str] | None
    answer: str
    created_by: str
    created_at: datetime


def _check_dataset_question_options(question_type: QuestionType, options: list[str] | None, answer: str) -> None:
    if question_type in _CHOICE_TYPES:
        if not options or len(options) < 2:
            raise ValueError(f"{question_type.value} questions need at least 2 options.")
        if answer not in options:
            raise ValueError("answer must exactly match one of the given options.")
    elif options is not None:
        raise ValueError(f"{question_type.value} questions don't take options - leave it blank.")


class CreateDatasetQuestionIn(CamelModel):
    chapter_id: str | None = None
    topic_id: str | None = None
    bloom_level: BloomLevel
    question_type: QuestionType
    text: str
    options: list[str] | None = None
    answer: str

    @model_validator(mode="after")
    def _validate_options(self) -> "CreateDatasetQuestionIn":
        _check_dataset_question_options(self.question_type, self.options, self.answer)
        return self


class UpdateDatasetQuestionIn(CamelModel):
    chapter_id: str | None = None
    topic_id: str | None = None
    bloom_level: BloomLevel | None = None
    question_type: QuestionType | None = None
    text: str | None = None
    options: list[str] | None = None
    answer: str | None = None
