from src.domain.models import BloomLevel, HomeworkDifficulty, HomeworkStatus

from .bloom import BloomTarget
from .common import CamelModel
from .roster import AssignmentTarget


class HomeworkOut(CamelModel):
    id: str
    test_id: str
    class_id: str
    gap_topic: str
    gap_mastery_percent: int
    dataset_ids: list[str]
    total_questions: int
    difficulty: HomeworkDifficulty
    bloom_distribution: list[BloomTarget]
    target: AssignmentTarget
    completion_window_hours: int | None
    status: HomeworkStatus
    assigned_count: int
    completed_count: int


class CreateHomeworkIn(CamelModel):
    test_id: str
    dataset_ids: list[str]
    total_questions: int
    difficulty: HomeworkDifficulty
    bloom_distribution: list[BloomTarget]


class AssignHomeworkIn(CamelModel):
    target: AssignmentTarget
    completion_window_hours: int


class HomeworkQuestionOut(CamelModel):
    id: str
    homework_id: str
    order: int
    bloom_level: BloomLevel
    dataset_id: str
    text: str
    answer: str


class UpdateHomeworkQuestionIn(CamelModel):
    text: str
