from .common import CamelModel


class SubjectOut(CamelModel):
    id: str
    name: str


class ChapterOut(CamelModel):
    id: str
    subject_id: str
    name: str


class TopicOut(CamelModel):
    id: str
    chapter_id: str
    name: str
