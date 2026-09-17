from .common import CamelModel


class JourneyChapterNodeOut(CamelModel):
    chapter_id: str
    chapter_label: str
    state: str  # "DONE" | "CURRENT" | "LOCKED"
    stars_earned: int


class SubjectJourneyOut(CamelModel):
    subject_id: str
    subject_label: str
    nodes: list[JourneyChapterNodeOut]
