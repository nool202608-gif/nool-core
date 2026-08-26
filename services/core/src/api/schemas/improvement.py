from enum import Enum

from .bloom import BloomDelta
from .common import CamelModel


class StudentImprovementStatus(str, Enum):
    RETEST_COMPLETE = "RETEST_COMPLETE"
    RETEST_INCOMPLETE = "RETEST_INCOMPLETE"


class TopicImprovementOut(CamelModel):
    topic_label: str
    before_percent: int | None
    after_percent: int | None


class StudentImprovementSummaryOut(CamelModel):
    student_id: str
    status: StudentImprovementStatus
    before_percent: int
    after_percent: int | None  # null while RETEST_INCOMPLETE - never render as 0


class ClassImprovementOut(CamelModel):
    test_id: str
    homework_id: str
    homework_gap_topic: str
    baseline_percent: int
    retest_percent: int
    improvement_percent: int
    assigned_count: int
    retested_count: int
    bloom_improvement: list[BloomDelta]
    topic_improvement: list[TopicImprovementOut]
    students: list[StudentImprovementSummaryOut]


class StudentImprovementOut(CamelModel):
    student_id: str
    test_id: str
    homework_id: str
    homework_gap_topic: str
    status: StudentImprovementStatus
    before_percent: int
    after_percent: int | None
    bloom_improvement: list[BloomDelta]
    topic_improvement: list[TopicImprovementOut]
