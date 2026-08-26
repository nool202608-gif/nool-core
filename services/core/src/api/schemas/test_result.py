from .bloom import BloomScore
from .common import CamelModel


class ClassTestResultOut(CamelModel):
    test_id: str
    class_mastery_percent: int
    assigned_count: int
    completed_count: int
    priority_gap_topic: str
    priority_gap_percent: int
    bloom_performance: list[BloomScore]


class StudentTestResultOut(CamelModel):
    test_id: str
    student_id: str
    mastery_percent: int
    bloom_performance: list[BloomScore]
