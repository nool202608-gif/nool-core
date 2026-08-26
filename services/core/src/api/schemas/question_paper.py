from src.domain.models import BloomLevel, PaperDifficultyLevel, QuestionPaperStatus

from .bloom import BloomTarget
from .common import CamelModel
from .dataset import DatasetShare


class PaperSection(CamelModel):
    label: str
    question_count: int
    marks_each: int


class PaperRules(CamelModel):
    allow_internal_choice: bool
    avoid_duplicate_concepts: bool
    respect_chapter_weightage: bool
    avoid_recent_repetition: bool


class PaperDifficultyTarget(CamelModel):
    level: PaperDifficultyLevel
    value: int


class PaperValidationOut(CamelModel):
    coverage_percent: int
    marks_accounted_for: int
    duplicate_count: int
    quality_percent: int
    issues: list[str]  # non-empty only when VALIDATION_FAILED


class QuestionPaperOut(CamelModel):
    id: str
    name: str
    exam_type: str
    board: str
    grade: int
    language: str
    subject_id: str
    dataset_shares: list[DatasetShare]
    chapter_ids: list[str]
    topic_ids: list[str]
    total_marks: int | None
    duration_minutes: int | None
    sections: list[PaperSection]
    bloom_distribution: list[BloomTarget]
    difficulty_distribution: list[PaperDifficultyTarget]
    question_types: list[str]
    rules: PaperRules
    status: QuestionPaperStatus
    validation: PaperValidationOut | None
    custom_header_text: str | None = None
    logo_data_uri: str | None = None
    instructions: list[str] | None = None


class CreateQuestionPaperIn(CamelModel):
    name: str
    exam_type: str
    board: str
    grade: int
    language: str
    subject_id: str
    chapter_ids: list[str] | None = None
    topic_ids: list[str] | None = None
    dataset_shares: list[DatasetShare] | None = None
    question_types: list[str] | None = None
    sections: list[PaperSection] | None = None
    total_marks: int | None = None
    duration_minutes: int | None = None
    bloom_distribution: list[BloomTarget] | None = None
    difficulty_distribution: list[PaperDifficultyTarget] | None = None
    custom_header_text: str | None = None
    logo_data_uri: str | None = None
    instructions: list[str] | None = None


class QuestionPaperQuestionOut(CamelModel):
    id: str
    paper_id: str
    order: int
    bloom_level: BloomLevel
    marks: int
    text: str


class UpdateQuestionPaperQuestionIn(CamelModel):
    text: str


class QuestionPaperQuestionCandidateOut(CamelModel):
    id: str
    text: str


class ReorderQuestionsIn(CamelModel):
    ordered_question_ids: list[str]
