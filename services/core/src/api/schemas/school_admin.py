from datetime import date, datetime

from pydantic import field_validator

from src.domain.models import SubscriptionStatus, UserStatus

from .bloom import BloomScore
from .common import CamelModel

# School Admin can only ever create/edit classes for grades 1 through 12 -
# see CreateClassIn/UpdateClassIn's validators below.
MIN_GRADE = 1
MAX_GRADE = 12


class SchoolTeacherOut(CamelModel):
    id: str
    display_name: str
    email: str
    phone_number: str | None
    employee_id: str | None
    class_ids: list[str]
    status: UserStatus
    must_change_password: bool


class InviteTeacherIn(CamelModel):
    email: str
    display_name: str
    phone_number: str | None = None
    employee_id: str | None = None


class InviteTeacherOut(CamelModel):
    id: str
    status: UserStatus
    temp_password: str


class UpdateTeacherStatusIn(CamelModel):
    status: UserStatus


class UpdateTeacherIn(CamelModel):
    """General profile edit, separate from the status-only endpoint above -
    partial update, only provided fields change."""

    display_name: str | None = None
    phone_number: str | None = None
    employee_id: str | None = None


class ResetPasswordOut(CamelModel):
    temp_password: str


class SendCredentialsEmailIn(CamelModel):
    """The admin's reviewed/edited draft (see CredentialReveal /
    SendCredentialsEmailModal on the frontend) - temp_password is passed
    through rather than re-derived, since only the plaintext-once value
    the caller already has in hand (never persisted server-side) can be
    included in the email body.
    """

    subject: str
    message: str
    temp_password: str


class SendCredentialsEmailOut(CamelModel):
    sent: bool


class SchoolStudentOut(CamelModel):
    id: str
    display_name: str
    email: str
    class_id: str
    roll_number: int
    guardian_name: str | None
    guardian_phone: str | None
    date_of_birth: date | None
    status: UserStatus
    must_change_password: bool


class CreateStudentIn(CamelModel):
    display_name: str
    email: str
    class_id: str
    roll_number: int
    guardian_name: str | None = None
    guardian_phone: str | None = None
    date_of_birth: date | None = None


class CreateStudentOut(CamelModel):
    id: str
    display_name: str
    email: str
    class_id: str
    roll_number: int
    status: UserStatus
    temp_password: str


class UpdateStudentIn(CamelModel):
    class_id: str | None = None
    status: UserStatus | None = None
    display_name: str | None = None
    guardian_name: str | None = None
    guardian_phone: str | None = None
    date_of_birth: date | None = None


class BulkRowResultOut(CamelModel):
    row: int
    status: str
    email: str | None = None
    temp_password: str | None = None
    error: str | None = None


class BulkImportResultOut(CamelModel):
    results: list[BulkRowResultOut]
    created_count: int
    error_count: int


class ClassAssignmentOut(CamelModel):
    teacher_id: str
    subject_id: str


class SchoolAdminClassOut(CamelModel):
    id: str
    grade: int
    section: str
    student_count: int
    assignments: list[ClassAssignmentOut]
    status: UserStatus


class CreateClassIn(CamelModel):
    grade: int
    section: str

    @field_validator("grade")
    @classmethod
    def _grade_in_range(cls, value: int) -> int:
        if not (MIN_GRADE <= value <= MAX_GRADE):
            raise ValueError(f"Grade must be between {MIN_GRADE} and {MAX_GRADE}.")
        return value


class UpdateClassIn(CamelModel):
    """Full edit of grade/section - both required (unlike the partial-update
    convention elsewhere in this file) since grade and section together are
    this class's identity (see the school_id+grade+section unique
    constraint); editing just one without the other isn't a meaningful
    partial update the way e.g. a teacher's phone number is.
    """

    grade: int
    section: str

    @field_validator("grade")
    @classmethod
    def _grade_in_range(cls, value: int) -> int:
        if not (MIN_GRADE <= value <= MAX_GRADE):
            raise ValueError(f"Grade must be between {MIN_GRADE} and {MAX_GRADE}.")
        return value


class UpdateClassStatusIn(CamelModel):
    status: UserStatus


class UpdateClassAssignmentsIn(CamelModel):
    assignments: list[ClassAssignmentOut]


class SubjectToggle(CamelModel):
    id: str
    name: str
    enabled: bool


class SchoolCurriculumOut(CamelModel):
    board: str
    subjects: list[SubjectToggle]


class UpdateSchoolCurriculumIn(CamelModel):
    subject_ids: list[str]


class CreateSchoolSubjectIn(CamelModel):
    """Lets a School Admin add a subject that isn't in the catalog yet -
    unlike admin_catalog's Super-Admin-only create, this both creates the
    global Subject row (or reuses one with a matching name, so two schools
    asking for "Sanskrit" don't end up with duplicate catalog rows) and
    immediately enables it for the caller's own school. See
    POST /school/curriculum/subjects.
    """

    name: str


class SchoolDatasetOut(CamelModel):
    id: str
    name: str
    question_count: int
    description: str
    enabled: bool


class UpdateSchoolDatasetsIn(CamelModel):
    dataset_ids: list[str]


class ClassBreakdownOut(CamelModel):
    class_id: str
    label: str
    mastery_avg_percent: int
    improvement_percent: int


class SchoolAnalyticsOut(CamelModel):
    school_mastery_avg_percent: int
    class_breakdown: list[ClassBreakdownOut]
    bloom_averages: list[BloomScore]


class SchoolSubscriptionOut(CamelModel):
    """Read-only for School Admin - same record Super Admin manages at
    /api/v1/admin/schools/{schoolId}/subscription, scoped to the caller's
    own school. Usage fields make plan limits visible proactively, instead
    of only ever surfacing as a 409 at the moment of creation - a null
    *_limit means that resource is unlimited on this plan (see Plan's own
    test_limit/question_paper_limit doc comment).
    """

    school_id: str
    plan_id: str
    plan_name: str
    status: SubscriptionStatus
    renews_at: datetime

    teacher_count: int
    teacher_limit: int
    student_count: int
    student_limit: int
    test_count: int
    test_limit: int | None
    question_paper_count: int
    question_paper_limit: int | None


class SchoolAdminMeOut(CamelModel):
    """The signed-in School Admin's own account - separate from the
    claim-only /me (see profile.py), which every role shares and doesn't
    carry phoneNumber. Self-service only: there is no endpoint for a
    School Admin to view/edit another School Admin.
    """

    id: str
    display_name: str
    email: str
    phone_number: str | None
    school_name: str


class UpdateSchoolAdminMeIn(CamelModel):
    """Partial update, only provided fields change. No email field - email
    changes would desync from the Firebase account and aren't supported
    anywhere else in this API either.
    """

    display_name: str | None = None
    phone_number: str | None = None
