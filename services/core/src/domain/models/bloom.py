from enum import Enum


class BloomLevel(str, Enum):
    """Bloom's taxonomy level - shared across Voice Tests, Test Results,
    Homework, Question Papers, Improvement, and AI Assessor sessions.
    Values match types/domain/bloom.ts's BloomLevel exactly.
    """

    REMEMBER = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY = "APPLY"
    ANALYZE = "ANALYZE"
    EVALUATE = "EVALUATE"
    CREATE = "CREATE"
