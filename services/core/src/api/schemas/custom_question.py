from datetime import datetime

from pydantic import model_validator

from src.domain.models import BloomLevel, QuestionType

from .common import CamelModel

_CHOICE_TYPES = (QuestionType.MCQ, QuestionType.TRUE_FALSE)


class CustomQuestionOut(CamelModel):
    id: str
    # Exactly one of class_id/grade is set - see CustomQuestion's docstring.
    # class_id = one specific section; grade = every section in that grade.
    class_id: str | None
    grade: int | None
    subject_id: str
    chapter_id: str
    topic_id: str | None
    bloom_level: BloomLevel
    question_type: QuestionType
    text: str
    options: list[str] | None
    answer: str
    created_by: str
    created_at: datetime
    # None = sitting in the school's general question bank (the default).
    # A name = a set the author chose to group it under - see
    # CustomQuestion.collection_name's docstring.
    collection_name: str | None


class CustomQuestionCollectionSummaryOut(CamelModel):
    """One row per named set (plus one synthetic row for the general bank,
    collection_name=None) with a real question count - shown on the
    Datasets page as this school's own, locally-owned question bank
    content, alongside the global (Super-Admin-owned) Dataset catalog.
    """

    collection_name: str | None
    question_count: int


def _check_options_match_type(question_type: QuestionType, options: list[str] | None, answer: str) -> None:
    if question_type in _CHOICE_TYPES:
        if not options or len(options) < 2:
            raise ValueError(f"{question_type.value} questions need at least 2 options.")
        if answer not in options:
            raise ValueError("answer must exactly match one of the given options.")
    elif options is not None:
        raise ValueError(f"{question_type.value} questions don't take options - leave it blank.")


class CreateCustomQuestionIn(CamelModel):
    # Exactly one of class_id/grade - a specific section, or every section
    # in that grade at this school (common content shouldn't need
    # duplicating once per section). See CustomQuestion's docstring.
    class_id: str | None = None
    grade: int | None = None
    subject_id: str
    chapter_id: str
    topic_id: str | None = None
    bloom_level: BloomLevel
    question_type: QuestionType
    text: str
    options: list[str] | None = None
    answer: str
    # Blank/omitted = the school's general question bank. A name groups
    # this question under a custom-named set instead.
    collection_name: str | None = None

    @model_validator(mode="after")
    def _validate_class_xor_grade(self) -> "CreateCustomQuestionIn":
        if (self.class_id is None) == (self.grade is None):
            raise ValueError("Set exactly one of classId or grade.")
        return self

    @model_validator(mode="after")
    def _validate_options(self) -> "CreateCustomQuestionIn":
        _check_options_match_type(self.question_type, self.options, self.answer)
        return self


class UpdateCustomQuestionIn(CamelModel):
    class_id: str | None = None
    grade: int | None = None
    subject_id: str | None = None
    chapter_id: str | None = None
    topic_id: str | None = None
    bloom_level: BloomLevel | None = None
    question_type: QuestionType | None = None
    text: str | None = None
    options: list[str] | None = None
    answer: str | None = None
    collection_name: str | None = None

    @model_validator(mode="after")
    def _validate_class_or_grade_not_both(self) -> "UpdateCustomQuestionIn":
        if self.class_id is not None and self.grade is not None:
            raise ValueError("Set either classId or grade, not both.")
        return self
