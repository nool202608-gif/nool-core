from src.domain.models import StudentRetestStatus

from .common import CamelModel


class StudentRetestOut(CamelModel):
    student_id: str
    status: StudentRetestStatus
    improvement_percent: int | None  # set only once RESULT_READY


class RetestProgressOut(CamelModel):
    homework_id: str
    class_id: str
    assigned_count: int
    completed_count: int
    in_progress_count: int
    not_started_count: int
    students: list[StudentRetestOut]
