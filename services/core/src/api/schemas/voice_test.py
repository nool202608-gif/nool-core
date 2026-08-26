from datetime import datetime

from src.domain.models import BloomLevel, TestStatus

from .bloom import BloomTarget  # noqa: F401 - re-exported for convenience
from .common import CamelModel
from .roster import AssignmentTarget


class VoiceTestOut(CamelModel):
    id: str
    class_id: str
    subject_id: str
    chapter_id: str
    topic_id: str | None  # null only while status is DRAFT
    bloom_levels: list[BloomLevel]
    duration_minutes: int
    completion_window_hours: int
    target: AssignmentTarget
    status: TestStatus
    assigned_count: int
    completed_count: int
    created_at: datetime


class CreateTestIn(CamelModel):
    class_id: str
    subject_id: str
    chapter_id: str
    topic_id: str
    bloom_levels: list[BloomLevel]
    duration_minutes: int
    completion_window_hours: int
    target: AssignmentTarget
