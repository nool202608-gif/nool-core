from src.domain.models import AssignmentTargetMode

from .common import CamelModel


class AssignmentTarget(CamelModel):
    """Mirrors types/domain/roster.ts's discriminated union
    ({mode: 'WHOLE_CLASS'} | {mode: 'SPECIFIC_STUDENTS', studentIds}) as a
    flat optional-field model rather than a tagged union - student_ids is
    simply absent/null when mode is WHOLE_CLASS.
    """

    mode: AssignmentTargetMode
    student_ids: list[str] | None = None


class SchoolClassOut(CamelModel):
    id: str
    grade: int
    section: str
    student_count: int


class RosterStudentOut(CamelModel):
    id: str
    class_id: str
    display_name: str
    roll_number: int
