"""Every ORM model in Core, imported here so Base.metadata sees the full
schema - database/migrations/env.py imports this module for exactly that
side effect before pointing Alembic's target_metadata at Base.metadata.
"""

from ..base import Base
from .ai_assessor import AiAssessorSession, AiAssessorSessionBloomLevel
from .assistant import AssistantMessage, ChatRole
from .bloom import BloomLevel
from .curriculum import Chapter, SchoolCurriculum, Subject, Topic
from .dataset import Dataset, SchoolDataset
from .foundation import (
    AuditLog,
    Plan,
    Role,
    School,
    SchoolStatus,
    Subscription,
    SubscriptionStatus,
    User,
    UserStatus,
)
from .homework import (
    Homework,
    HomeworkBloomDistribution,
    HomeworkDataset,
    HomeworkDifficulty,
    HomeworkQuestion,
    HomeworkStatus,
    HomeworkTargetStudent,
    StudentHomeworkProgress,
    StudentHomeworkStatus,
)
from .improvement import TopicPerformance
from .leaderboard import StudentPoints
from .question_paper import (
    PaperDifficultyLevel,
    QuestionPaper,
    QuestionPaperBloomDistribution,
    QuestionPaperChapter,
    QuestionPaperDatasetShare,
    QuestionPaperDifficultyDistribution,
    QuestionPaperQuestion,
    QuestionPaperSection,
    QuestionPaperStatus,
    QuestionPaperTopic,
    QuestionPaperValidation,
)
from .retest import RetestAttempt, RetestBloomComparison, StudentRetestStatus
from .roster import SchoolClass, StudentProfile, TeacherClassAssignment
from .test_result import StudentTestResult, StudentTestResultBloomScore
from .voice_test import (
    AssignmentTargetMode,
    TestStatus,
    VoiceTest,
    VoiceTestBloomLevel,
    VoiceTestTargetStudent,
)

__all__ = [
    "Base",
    "AiAssessorSession",
    "AiAssessorSessionBloomLevel",
    "AssistantMessage",
    "ChatRole",
    "BloomLevel",
    "Chapter",
    "SchoolCurriculum",
    "Subject",
    "Topic",
    "Dataset",
    "SchoolDataset",
    "AuditLog",
    "Plan",
    "Role",
    "School",
    "SchoolStatus",
    "Subscription",
    "SubscriptionStatus",
    "User",
    "UserStatus",
    "Homework",
    "HomeworkBloomDistribution",
    "HomeworkDataset",
    "HomeworkDifficulty",
    "HomeworkQuestion",
    "HomeworkStatus",
    "HomeworkTargetStudent",
    "StudentHomeworkProgress",
    "StudentHomeworkStatus",
    "TopicPerformance",
    "StudentPoints",
    "PaperDifficultyLevel",
    "QuestionPaper",
    "QuestionPaperBloomDistribution",
    "QuestionPaperChapter",
    "QuestionPaperDatasetShare",
    "QuestionPaperDifficultyDistribution",
    "QuestionPaperQuestion",
    "QuestionPaperSection",
    "QuestionPaperStatus",
    "QuestionPaperTopic",
    "QuestionPaperValidation",
    "RetestAttempt",
    "RetestBloomComparison",
    "StudentRetestStatus",
    "SchoolClass",
    "StudentProfile",
    "TeacherClassAssignment",
    "StudentTestResult",
    "StudentTestResultBloomScore",
    "AssignmentTargetMode",
    "TestStatus",
    "VoiceTest",
    "VoiceTestBloomLevel",
    "VoiceTestTargetStudent",
]
