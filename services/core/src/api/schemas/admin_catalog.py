from datetime import datetime

from pydantic import model_validator

from src.domain.models import BloomLevel, QuestionType

from .common import CamelModel

_CHOICE_TYPES = (QuestionType.MCQ, QuestionType.TRUE_FALSE)


class SubjectOut(CamelModel):
    id: str
    name: str


class CreateSubjectIn(CamelModel):
    name: str


class UpdateSubjectIn(CamelModel):
    name: str


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


class CreateDatasetIn(CamelModel):
    name: str
    question_count: int
    description: str
    subject_id: str | None = None


class UpdateDatasetIn(CamelModel):
    name: str | None = None
    question_count: int | None = None
    description: str | None = None
    subject_id: str | None = None


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
