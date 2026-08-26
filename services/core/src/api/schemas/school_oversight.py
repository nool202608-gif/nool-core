from datetime import datetime

from src.domain.models import (
    HomeworkStatus,
    QuestionPaperStatus,
    TestStatus,
)

from .common import CamelModel


class SchoolVoiceTestOut(CamelModel):
    """A read-only, school-wide row for School Admin oversight - the
    teacher name is a best-effort resolution via TeacherClassAssignment
    (the class+subject pair), not a stored column, since VoiceTest itself
    doesn't record who created it.
    """

    id: str
    class_label: str
    subject_name: str
    teacher_name: str | None
    status: TestStatus
    assigned_count: int
    completed_count: int
    created_at: datetime


class SchoolHomeworkOut(CamelModel):
    id: str
    class_label: str
    gap_topic: str
    teacher_name: str | None
    status: HomeworkStatus
    assigned_count: int
    completed_count: int


class SchoolQuestionPaperOut(CamelModel):
    id: str
    name: str
    exam_type: str
    subject_name: str
    created_by_name: str
    status: QuestionPaperStatus
    created_at: datetime


class SchoolRetestProgressOut(CamelModel):
    homework_id: str
    class_label: str
    gap_topic: str
    assigned_count: int
    completed_count: int
    in_progress_count: int
    not_started_count: int


class SchoolImprovementOut(CamelModel):
    test_id: str
    homework_id: str
    class_label: str
    gap_topic: str
    baseline_percent: int
    retest_percent: int
    improvement_percent: int
    assigned_count: int
    retested_count: int


class SchoolLeaderboardEntryOut(CamelModel):
    student_id: str
    display_name: str
    class_label: str
    points: int
    rank: int


class SchoolAuditLogEntryOut(CamelModel):
    """School-scoped counterpart to Super Admin's GET /admin/audit-log -
    only entries whose actor belongs to this caller's own school (an
    action a Super Admin took on this school, e.g. creating its
    subscription, is deliberately out of scope here - that's visible on
    the Super Admin side, not this one)."""

    id: str
    actor_name: str
    action: str
    target_type: str
    target_id: str
    created_at: datetime
