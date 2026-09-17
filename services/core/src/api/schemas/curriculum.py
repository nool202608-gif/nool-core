from .common import CamelModel


class SubjectOut(CamelModel):
    id: str
    name: str


class ChapterOut(CamelModel):
    id: str
    subject_id: str
    name: str
    # Null means "applies to any grade" - see Chapter.grade's docstring.
    grade: int | None = None


class TopicOut(CamelModel):
    id: str
    chapter_id: str
    name: str
