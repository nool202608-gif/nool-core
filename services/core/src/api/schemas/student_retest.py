from .bloom import BloomDelta
from .common import CamelModel


class EstimatedMinutes(CamelModel):
    min: int
    max: int


class RetestEntryOut(CamelModel):
    homework_id: str
    original_test_id: str
    subject_label: str
    topic_label: str
    estimated_minutes: EstimatedMinutes
    max_attempts: int  # currently always 1
    attempts_used: int


class RetestEntryResponse(CamelModel):
    entry: RetestEntryOut | None


class ProcessRetestResultIn(CamelModel):
    questions_answered: int
    total_questions: int
    elapsed_seconds: int


class RetestResultOut(CamelModel):
    homework_id: str
    original_test_id: str
    subject_label: str
    topic_label: str
    baseline_percent: int
    retest_percent: int
    improvement_percent: int
    bloom_comparison: list[BloomDelta]
