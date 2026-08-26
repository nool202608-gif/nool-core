from .common import CamelModel


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
    question_count: int
    description: str


class CreateDatasetIn(CamelModel):
    name: str
    question_count: int
    description: str


class UpdateDatasetIn(CamelModel):
    name: str | None = None
    question_count: int | None = None
    description: str | None = None
