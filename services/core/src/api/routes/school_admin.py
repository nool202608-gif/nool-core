import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, NotFoundError

from src.api.deps import get_db_session, require_role
from src.api.schemas.bloom import BloomDistributionOut, BloomScore, UpdateBloomDistributionIn
from src.api.schemas.common import ListEnvelope
from src.api.schemas.school_admin import (
    BulkImportResultOut,
    BulkRowResultOut,
    ClassAssignmentOut,
    ClassBreakdownOut,
    CreateClassIn,
    CreateSchoolSubjectIn,
    CreateStudentIn,
    CreateStudentOut,
    InviteTeacherIn,
    InviteTeacherOut,
    ResetPasswordOut,
    SchoolAdminClassOut,
    SchoolAdminMeOut,
    SchoolAnalyticsOut,
    SchoolCurriculumOut,
    SchoolDatasetOut,
    SchoolStudentOut,
    SchoolSubscriptionOut,
    SchoolTeacherOut,
    SendCredentialsEmailIn,
    SendCredentialsEmailOut,
    SubjectToggle,
    UpdateClassAssignmentsIn,
    UpdateClassIn,
    UpdateClassStatusIn,
    UpdateSchoolAdminMeIn,
    UpdateSchoolCurriculumIn,
    UpdateSchoolDatasetsIn,
    UpdateStudentIn,
    UpdateTeacherIn,
    UpdateTeacherStatusIn,
)
from src.domain.models import (
    AssistantMessage,
    BloomLevel,
    Dataset,
    Homework,
    Plan,
    QuestionPaper,
    RetestAttempt,
    Role,
    School,
    SchoolClass,
    SchoolCurriculum,
    SchoolDataset,
    StudentHomeworkProgress,
    StudentPoints,
    StudentProfile,
    StudentTestResult,
    StudentTestResultBloomScore,
    Subject,
    Subscription,
    TeacherClassAssignment,
    TopicPerformance,
    User,
    UserStatus,
    VoiceTest,
    VoiceTestTargetStudent,
)
from src.repositories import audit_repository
from src.repositories.roster_repository import student_count
from src.repositories.subscription_repository import get_active_plan
from src.repositories.usage_repository import (
    count_question_papers,
    count_students,
    count_teachers,
    count_tests,
)
from src.services.bulk_import import BulkRowResult, parse_rows
from src.services.email import send_email
from src.services.user_provisioning import create_firebase_user, reset_password

router = APIRouter(prefix="/api/v1/school", tags=["school-admin"])

# Kept as thin aliases (rather than a mass rename across this file) - the
# actual counting logic now lives in usage_repository, shared with
# GET /school/subscription's usage-vs-limit fields and with
# voice_test.py/question_paper.py's own limit checks.
_current_teacher_count = count_teachers
_current_student_count = count_students


async def _row_exists(session: AsyncSession, column, value) -> bool:
    """Existence pre-check used before a permanent delete (teacher/student/
    class), instead of attempting the delete and catching the resulting
    IntegrityError - the FK violation approach also works, but leaves the
    DB-level transaction aborted in a way this codebase's session-per-request
    model doesn't cleanly recover from mid-request, so this checks first
    and never lets the delete hit a real constraint violation.
    """
    result = await session.execute(select(column).where(column == value).limit(1))
    return result.first() is not None


def _teacher_out(t: User, class_ids: list[str]) -> SchoolTeacherOut:
    return SchoolTeacherOut(
        id=str(t.id), display_name=t.display_name, email=t.email,
        phone_number=t.phone_number, employee_id=t.employee_id,
        class_ids=class_ids, status=t.status, must_change_password=t.must_change_password,
    )


@router.get("/teachers")
async def list_teachers(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolTeacherOut]:
    result = await session.execute(
        select(User).where(User.school_id == user.school_id, User.role == Role.TEACHER)
    )
    teachers = result.scalars().all()
    items = []
    for t in teachers:
        assignments = await session.execute(
            select(TeacherClassAssignment.class_id).where(TeacherClassAssignment.teacher_id == t.id)
        )
        class_ids = list({str(row[0]) for row in assignments.all()})
        items.append(_teacher_out(t, class_ids))
    return ListEnvelope(items=items, total=len(items))


@router.post("/teachers/invite", status_code=201)
async def invite_teacher(
    body: InviteTeacherIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> InviteTeacherOut:
    plan = await get_active_plan(session, user.school_id)
    if plan is not None:
        current = await _current_teacher_count(session, user.school_id)
        if current >= plan.teacher_limit:
            raise ConflictError(
                f"Your plan allows up to {plan.teacher_limit} teachers - you already have {current}."
            )

    provisioned = create_firebase_user(email=body.email, display_name=body.display_name, role=Role.TEACHER)

    teacher = User(
        firebase_uid=provisioned.firebase_uid,
        email=body.email, display_name=body.display_name, role=Role.TEACHER,
        school_id=user.school_id, status=UserStatus.ACTIVE,
        phone_number=body.phone_number, employee_id=body.employee_id,
        must_change_password=True,
    )
    session.add(teacher)
    await session.flush()
    await audit_repository.record(
        session, actor_id=user.id, action="teacher.invited", target_type="user", target_id=str(teacher.id)
    )
    await session.commit()
    await session.refresh(teacher)
    return InviteTeacherOut(id=str(teacher.id), status=teacher.status, temp_password=provisioned.temp_password)


@router.post("/teachers/bulk-invite", summary="Bulk-invite teachers from a .csv or .xlsx file")
async def bulk_invite_teachers(
    file: UploadFile = File(...),
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> BulkImportResultOut:
    """Columns (header row, any order): displayName, email, phoneNumber
    (optional), employeeId (optional). Rejects the whole batch upfront if
    it would exceed the plan's teacherLimit; otherwise each row is
    provisioned independently, so one bad row doesn't block the rest.
    """
    content = await file.read()
    rows = parse_rows(file.filename or "upload", content)

    plan = await get_active_plan(session, user.school_id)
    if plan is not None:
        current = await _current_teacher_count(session, user.school_id)
        if current + len(rows) > plan.teacher_limit:
            raise ConflictError(
                f"Your plan allows up to {plan.teacher_limit} teachers - you have {current} and this "
                f"file would add {len(rows)}, {current + len(rows) - plan.teacher_limit} over the limit."
            )

    results: list[BulkRowResult] = []
    for index, row in enumerate(rows, start=2):  # row 1 is the header
        display_name = row.get("displayname", "")
        email = row.get("email", "")
        if not display_name or not email:
            results.append(BulkRowResult(row=index, status="error", error="displayName and email are required."))
            continue
        try:
            provisioned = create_firebase_user(email=email, display_name=display_name, role=Role.TEACHER)
            teacher = User(
                firebase_uid=provisioned.firebase_uid, email=email, display_name=display_name,
                role=Role.TEACHER, school_id=user.school_id, status=UserStatus.ACTIVE,
                phone_number=row.get("phonenumber") or None, employee_id=row.get("employeeid") or None,
                must_change_password=True,
            )
            session.add(teacher)
            await session.commit()
            results.append(
                BulkRowResult(row=index, status="created", email=email, temp_password=provisioned.temp_password)
            )
        except ConflictError as exc:
            await session.rollback()
            results.append(BulkRowResult(row=index, status="error", email=email, error=exc.message))
        except Exception as exc:  # noqa: BLE001 - one bad row must not fail the batch
            await session.rollback()
            results.append(BulkRowResult(row=index, status="error", email=email, error=str(exc)))

    created_count = sum(1 for r in results if r.status == "created")
    error_count = sum(1 for r in results if r.status == "error")
    # One summary row per batch, not one per teacher - a per-row audit
    # entry here would flood the log without adding anything the per-row
    # BulkRowResultOut (already shown to the caller) doesn't already say.
    await audit_repository.record(
        session, actor_id=user.id, action="teacher.bulk_invited", target_type="school",
        target_id=str(user.school_id),
    )
    await session.commit()
    return BulkImportResultOut(
        results=[BulkRowResultOut(**r.__dict__) for r in results],
        created_count=created_count,
        error_count=error_count,
    )


@router.patch("/teachers/{teacher_id}/status")
async def update_teacher_status(
    teacher_id: str,
    body: UpdateTeacherStatusIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolTeacherOut:
    result = await session.execute(
        select(User).where(User.id == teacher_id, User.school_id == user.school_id, User.role == Role.TEACHER)
    )
    teacher = result.scalar_one_or_none()
    if teacher is None:
        raise NotFoundError(f'No teacher with id "{teacher_id}" in your school.')
    teacher.status = body.status
    await audit_repository.record(
        session, actor_id=user.id, action="teacher.status.updated", target_type="user", target_id=teacher_id
    )
    await session.commit()
    assignments = await session.execute(
        select(TeacherClassAssignment.class_id).where(TeacherClassAssignment.teacher_id == teacher.id)
    )
    return _teacher_out(teacher, list({str(row[0]) for row in assignments.all()}))


async def _get_teacher_in_school(session: AsyncSession, teacher_id: str, school_id) -> User:
    result = await session.execute(
        select(User).where(User.id == teacher_id, User.school_id == school_id, User.role == Role.TEACHER)
    )
    teacher = result.scalar_one_or_none()
    if teacher is None:
        raise NotFoundError(f'No teacher with id "{teacher_id}" in your school.')
    return teacher


@router.patch("/teachers/{teacher_id}", summary="Edit a teacher's profile")
async def update_teacher(
    teacher_id: str,
    body: UpdateTeacherIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolTeacherOut:
    teacher = await _get_teacher_in_school(session, teacher_id, user.school_id)
    if body.display_name is not None:
        teacher.display_name = body.display_name
    if body.phone_number is not None:
        teacher.phone_number = body.phone_number
    if body.employee_id is not None:
        teacher.employee_id = body.employee_id
    await audit_repository.record(
        session, actor_id=user.id, action="teacher.updated", target_type="user", target_id=teacher_id
    )
    await session.commit()
    assignments = await session.execute(
        select(TeacherClassAssignment.class_id).where(TeacherClassAssignment.teacher_id == teacher.id)
    )
    return _teacher_out(teacher, list({str(row[0]) for row in assignments.all()}))


@router.post("/teachers/{teacher_id}/reset-password", summary="Issue a new temp password")
async def reset_teacher_password(
    teacher_id: str,
    actor: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ResetPasswordOut:
    """The no-email recovery path: a locked-out teacher has no self-service
    way back in, so School Admin issues a fresh one-time temp password
    here - same one-time-reveal contract as invite.
    """
    teacher = await _get_teacher_in_school(session, teacher_id, actor.school_id)
    if teacher.firebase_uid is None:
        raise ConflictError("This teacher has no Firebase account to reset.")
    temp_password = reset_password(firebase_uid=teacher.firebase_uid, role=Role.TEACHER)
    teacher.must_change_password = True
    await audit_repository.record(
        session, actor_id=actor.id, action="teacher.password_reset", target_type="user", target_id=teacher_id
    )
    await session.commit()
    return ResetPasswordOut(temp_password=temp_password)


@router.get("/teachers/export", summary="Download the current teacher roster as CSV")
async def export_teachers(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    result = await session.execute(
        select(User).where(User.school_id == user.school_id, User.role == Role.TEACHER)
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["displayName", "email", "phoneNumber", "employeeId"])
    for t in result.scalars().all():
        writer.writerow([t.display_name, t.email, t.phone_number or "", t.employee_id or ""])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=teachers.csv"},
    )


@router.post("/teachers/{teacher_id}/send-credentials-email", summary="Email a temp password the admin has reviewed")
async def send_teacher_credentials_email(
    teacher_id: str,
    body: SendCredentialsEmailIn,
    actor: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SendCredentialsEmailOut:
    teacher = await _get_teacher_in_school(session, teacher_id, actor.school_id)
    send_email(to_email=teacher.email, subject=body.subject, message=body.message)
    await audit_repository.record(
        session, actor_id=actor.id, action="teacher.credentials_emailed", target_type="user", target_id=teacher_id
    )
    await session.commit()
    return SendCredentialsEmailOut(sent=True)


@router.delete("/teachers/{teacher_id}", summary="Permanently delete a teacher")
async def delete_teacher(
    teacher_id: str,
    actor: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    """Idempotent, like admin_catalog's delete_subject. Unlike status
    (deactivate), this can't be undone, so it blocks (via _row_exists,
    checked up front) rather than delete if the teacher has created real
    content (Tests, Question Papers, ...) - deactivate instead to revoke
    access without losing that content's history.
    """
    result = await session.execute(
        select(User).where(User.id == teacher_id, User.school_id == actor.school_id, User.role == Role.TEACHER)
    )
    teacher = result.scalar_one_or_none()
    if teacher is None:
        return {"deleted": True}

    has_content = await _row_exists(
        session, AssistantMessage.teacher_id, teacher.id
    ) or await _row_exists(session, QuestionPaper.created_by, teacher.id)
    if has_content:
        raise ConflictError(
            "This teacher has created Tests, Question Papers, or other content and can't be deleted. "
            "Deactivate them instead to revoke access."
        )

    assignments = await session.execute(
        select(TeacherClassAssignment).where(TeacherClassAssignment.teacher_id == teacher.id)
    )
    for row in assignments.scalars().all():
        await session.delete(row)
    await session.flush()  # no ORM relationship links these two tables, so explicit ordering is needed
    await session.delete(teacher)
    await audit_repository.record(
        session, actor_id=actor.id, action="teacher.deleted", target_type="user", target_id=teacher_id
    )
    await session.commit()
    return {"deleted": True}


def _student_out(u: User, sp: StudentProfile) -> SchoolStudentOut:
    return SchoolStudentOut(
        id=str(u.id), display_name=u.display_name, email=u.email, class_id=str(sp.class_id),
        roll_number=sp.roll_number, guardian_name=sp.guardian_name, guardian_phone=sp.guardian_phone,
        date_of_birth=sp.date_of_birth, status=u.status, must_change_password=u.must_change_password,
    )


@router.get("/students")
async def list_students(
    class_id: str | None = Query(default=None, alias="classId"),
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolStudentOut]:
    query = (
        select(User, StudentProfile)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(SchoolClass, SchoolClass.id == StudentProfile.class_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    if class_id:
        query = query.where(StudentProfile.class_id == class_id)
    result = await session.execute(query)
    items = [_student_out(u, sp) for u, sp in result.all()]
    return ListEnvelope(items=items, total=len(items))


@router.post("/students", status_code=201, summary="Create a student")
async def create_student(
    body: CreateStudentIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> CreateStudentOut:
    plan = await get_active_plan(session, user.school_id)
    if plan is not None:
        current = await _current_student_count(session, user.school_id)
        if current >= plan.student_limit:
            raise ConflictError(
                f"Your plan allows up to {plan.student_limit} students - you already have {current}."
            )

    provisioned = create_firebase_user(email=body.email, display_name=body.display_name, role=Role.STUDENT)

    student_user = User(
        firebase_uid=provisioned.firebase_uid, email=body.email,
        display_name=body.display_name, role=Role.STUDENT, school_id=user.school_id,
        status=UserStatus.ACTIVE, must_change_password=True,
    )
    session.add(student_user)
    await session.flush()
    session.add(
        StudentProfile(
            user_id=student_user.id, class_id=body.class_id, roll_number=body.roll_number,
            guardian_name=body.guardian_name, guardian_phone=body.guardian_phone,
            date_of_birth=body.date_of_birth,
        )
    )
    await audit_repository.record(
        session, actor_id=user.id, action="student.created", target_type="user", target_id=str(student_user.id)
    )
    await session.commit()
    return CreateStudentOut(
        id=str(student_user.id), display_name=student_user.display_name, email=student_user.email,
        class_id=body.class_id, roll_number=body.roll_number, status=student_user.status,
        temp_password=provisioned.temp_password,
    )


@router.post("/students/bulk-create", summary="Bulk-create students from a .csv or .xlsx file")
async def bulk_create_students(
    file: UploadFile = File(...),
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> BulkImportResultOut:
    """Columns (header row, any order): displayName, email, classGrade,
    classSection, rollNumber, guardianName (optional), guardianPhone
    (optional), dateOfBirth (optional, YYYY-MM-DD). classGrade/classSection
    are resolved to this school's class per row (not a raw classId - a
    human filling a spreadsheet won't know internal UUIDs).
    """
    content = await file.read()
    rows = parse_rows(file.filename or "upload", content)

    plan = await get_active_plan(session, user.school_id)
    if plan is not None:
        current = await _current_student_count(session, user.school_id)
        if current + len(rows) > plan.student_limit:
            raise ConflictError(
                f"Your plan allows up to {plan.student_limit} students - you have {current} and this "
                f"file would add {len(rows)}, {current + len(rows) - plan.student_limit} over the limit."
            )

    classes_result = await session.execute(select(SchoolClass).where(SchoolClass.school_id == user.school_id))
    classes_by_key = {(c.grade, c.section.strip().lower()): c for c in classes_result.scalars().all()}

    results: list[BulkRowResult] = []
    for index, row in enumerate(rows, start=2):
        display_name = row.get("displayname", "")
        email = row.get("email", "")
        grade_raw = row.get("classgrade", "")
        section = row.get("classsection", "").strip().lower()
        roll_raw = row.get("rollnumber", "")

        if not display_name or not email or not grade_raw or not section or not roll_raw:
            results.append(
                BulkRowResult(
                    row=index, status="error", email=email or None,
                    error="displayName, email, classGrade, classSection, and rollNumber are required.",
                )
            )
            continue

        school_class = classes_by_key.get((_safe_int(grade_raw), section))
        if school_class is None:
            results.append(
                BulkRowResult(row=index, status="error", email=email, error=f"No class {grade_raw}-{section} in your school.")
            )
            continue

        # Parsed up front, before any Firebase/DB call - create_student's
        # single-record path gets this for free from Pydantic's date
        # field, but the bulk path only ever has raw CSV/XLSX strings.
        # Catching a bad value here (not by letting asyncpg reject it
        # during commit) avoids ever provisioning a Firebase account for a
        # row that was always going to fail, and avoids running the rest
        # of this row's DB writes against a session an earlier exception
        # left in a failed-transaction state.
        date_of_birth_raw = row.get("dateofbirth") or None
        date_of_birth = None
        if date_of_birth_raw:
            try:
                date_of_birth = datetime.strptime(date_of_birth_raw, "%Y-%m-%d").date()
            except ValueError:
                results.append(
                    BulkRowResult(
                        row=index, status="error", email=email,
                        error='dateOfBirth must be in YYYY-MM-DD format.',
                    )
                )
                continue

        try:
            provisioned = create_firebase_user(email=email, display_name=display_name, role=Role.STUDENT)
            student_user = User(
                firebase_uid=provisioned.firebase_uid, email=email, display_name=display_name,
                role=Role.STUDENT, school_id=user.school_id, status=UserStatus.ACTIVE,
                must_change_password=True,
            )
            session.add(student_user)
            await session.flush()
            session.add(
                StudentProfile(
                    user_id=student_user.id, class_id=school_class.id, roll_number=_safe_int(roll_raw),
                    guardian_name=row.get("guardianname") or None, guardian_phone=row.get("guardianphone") or None,
                    date_of_birth=date_of_birth,
                )
            )
            await session.commit()
            results.append(
                BulkRowResult(row=index, status="created", email=email, temp_password=provisioned.temp_password)
            )
        except ConflictError as exc:
            await session.rollback()
            results.append(BulkRowResult(row=index, status="error", email=email, error=exc.message))
        except Exception as exc:  # noqa: BLE001 - one bad row must not fail the batch
            await session.rollback()
            results.append(BulkRowResult(row=index, status="error", email=email, error=str(exc)))

    await audit_repository.record(
        session, actor_id=user.id, action="student.bulk_created", target_type="school",
        target_id=str(user.school_id),
    )
    await session.commit()
    return BulkImportResultOut(
        results=[BulkRowResultOut(**r.__dict__) for r in results],
        created_count=sum(1 for r in results if r.status == "created"),
        error_count=sum(1 for r in results if r.status == "error"),
    )


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return -1


@router.patch("/students/{student_id}", summary="Reassign class / change status")
async def update_student(
    student_id: str,
    body: UpdateStudentIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolStudentOut:
    result = await session.execute(
        select(User, StudentProfile)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.id == student_id, User.school_id == user.school_id)
    )
    row = result.first()
    if row is None:
        raise NotFoundError(f'No student with id "{student_id}" in your school.')
    student_user, profile = row
    if body.class_id is not None:
        profile.class_id = body.class_id
    if body.status is not None:
        student_user.status = body.status
    if body.display_name is not None:
        student_user.display_name = body.display_name
    if body.guardian_name is not None:
        profile.guardian_name = body.guardian_name
    if body.guardian_phone is not None:
        profile.guardian_phone = body.guardian_phone
    if body.date_of_birth is not None:
        profile.date_of_birth = body.date_of_birth
    await audit_repository.record(
        session, actor_id=user.id, action="student.updated", target_type="user", target_id=student_id
    )
    await session.commit()
    return _student_out(student_user, profile)


@router.post("/students/{student_id}/reset-password", summary="Issue a new temp password")
async def reset_student_password(
    student_id: str,
    actor: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ResetPasswordOut:
    result = await session.execute(
        select(User).where(User.id == student_id, User.school_id == actor.school_id, User.role == Role.STUDENT)
    )
    student_user = result.scalar_one_or_none()
    if student_user is None:
        raise NotFoundError(f'No student with id "{student_id}" in your school.')
    if student_user.firebase_uid is None:
        raise ConflictError("This student has no Firebase account to reset.")
    temp_password = reset_password(firebase_uid=student_user.firebase_uid, role=Role.STUDENT)
    student_user.must_change_password = True
    await audit_repository.record(
        session, actor_id=actor.id, action="student.password_reset", target_type="user", target_id=student_id
    )
    await session.commit()
    return ResetPasswordOut(temp_password=temp_password)


@router.get("/students/export", summary="Download the current student roster as CSV")
async def export_students(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    result = await session.execute(
        select(User, StudentProfile, SchoolClass)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(SchoolClass, SchoolClass.id == StudentProfile.class_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["displayName", "email", "classGrade", "classSection", "rollNumber", "guardianName", "guardianPhone", "dateOfBirth"]
    )
    for u, sp, c in result.all():
        writer.writerow(
            [
                u.display_name, u.email, c.grade, c.section, sp.roll_number,
                sp.guardian_name or "", sp.guardian_phone or "",
                sp.date_of_birth.isoformat() if sp.date_of_birth else "",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=students.csv"},
    )


@router.post("/students/{student_id}/send-credentials-email", summary="Email a temp password the admin has reviewed")
async def send_student_credentials_email(
    student_id: str,
    body: SendCredentialsEmailIn,
    actor: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SendCredentialsEmailOut:
    result = await session.execute(
        select(User).where(User.id == student_id, User.school_id == actor.school_id, User.role == Role.STUDENT)
    )
    student_user = result.scalar_one_or_none()
    if student_user is None:
        raise NotFoundError(f'No student with id "{student_id}" in your school.')
    send_email(to_email=student_user.email, subject=body.subject, message=body.message)
    await audit_repository.record(
        session, actor_id=actor.id, action="student.credentials_emailed", target_type="user", target_id=student_id
    )
    await session.commit()
    return SendCredentialsEmailOut(sent=True)


@router.delete("/students/{student_id}", summary="Permanently delete a student")
async def delete_student(
    student_id: str,
    actor: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    """Same idempotent/blocked-up-front shape as delete_teacher - real
    activity (test results, homework progress, retest attempts, leaderboard
    points) blocks the delete rather than being cascaded away.
    """
    result = await session.execute(
        select(User, StudentProfile)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.id == student_id, User.school_id == actor.school_id)
    )
    row = result.first()
    if row is None:
        return {"deleted": True}
    student_user, profile = row

    has_activity = (
        await _row_exists(session, StudentTestResult.student_id, student_user.id)
        or await _row_exists(session, StudentHomeworkProgress.student_id, student_user.id)
        or await _row_exists(session, RetestAttempt.student_id, student_user.id)
        or await _row_exists(session, StudentPoints.student_id, student_user.id)
        or await _row_exists(session, VoiceTestTargetStudent.student_id, student_user.id)
    )
    if has_activity:
        raise ConflictError(
            "This student has test results, homework progress, or other activity and can't be deleted. "
            "Deactivate them instead to revoke access."
        )

    await session.delete(profile)
    await session.flush()  # no ORM relationship links these two tables, so explicit ordering is needed
    await session.delete(student_user)
    await audit_repository.record(
        session, actor_id=actor.id, action="student.deleted", target_type="user", target_id=student_id
    )
    await session.commit()
    return {"deleted": True}


@router.get("/classes")
async def list_school_classes(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolAdminClassOut]:
    result = await session.execute(select(SchoolClass).where(SchoolClass.school_id == user.school_id))
    classes = result.scalars().all()
    items = []
    for c in classes:
        assignments = await session.execute(
            select(TeacherClassAssignment).where(TeacherClassAssignment.class_id == c.id)
        )
        items.append(
            SchoolAdminClassOut(
                id=str(c.id), grade=c.grade, section=c.section,
                student_count=await student_count(session, c.id),
                assignments=[
                    ClassAssignmentOut(teacher_id=str(a.teacher_id), subject_id=str(a.subject_id))
                    for a in assignments.scalars().all()
                ],
                status=c.status,
            )
        )
    return ListEnvelope(items=items, total=len(items))


@router.post("/classes", status_code=201)
async def create_school_class(
    body: CreateClassIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAdminClassOut:
    school_class = SchoolClass(school_id=user.school_id, grade=body.grade, section=body.section)
    session.add(school_class)
    await session.flush()
    await audit_repository.record(
        session, actor_id=user.id, action="class.created", target_type="class", target_id=str(school_class.id)
    )
    await session.commit()
    await session.refresh(school_class)
    return SchoolAdminClassOut(
        id=str(school_class.id), grade=school_class.grade, section=school_class.section,
        student_count=0, assignments=[], status=school_class.status,
    )


@router.patch("/classes/{class_id}", summary="Edit a class's grade/section")
async def update_school_class(
    class_id: str,
    body: UpdateClassIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAdminClassOut:
    result = await session.execute(
        select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.school_id == user.school_id)
    )
    school_class = result.scalar_one_or_none()
    if school_class is None:
        raise NotFoundError(f'No class with id "{class_id}" in your school.')
    school_class.grade = body.grade
    school_class.section = body.section
    await audit_repository.record(
        session, actor_id=user.id, action="class.updated", target_type="class", target_id=class_id
    )
    await session.commit()
    assignments = await session.execute(
        select(TeacherClassAssignment).where(TeacherClassAssignment.class_id == class_id)
    )
    return SchoolAdminClassOut(
        id=str(school_class.id), grade=school_class.grade, section=school_class.section,
        student_count=await student_count(session, school_class.id),
        assignments=[
            ClassAssignmentOut(teacher_id=str(a.teacher_id), subject_id=str(a.subject_id))
            for a in assignments.scalars().all()
        ],
        status=school_class.status,
    )


@router.patch("/classes/{class_id}/status")
async def update_school_class_status(
    class_id: str,
    body: UpdateClassStatusIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAdminClassOut:
    result = await session.execute(
        select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.school_id == user.school_id)
    )
    school_class = result.scalar_one_or_none()
    if school_class is None:
        raise NotFoundError(f'No class with id "{class_id}" in your school.')
    school_class.status = body.status
    await audit_repository.record(
        session, actor_id=user.id, action="class.status.updated", target_type="class", target_id=class_id
    )
    await session.commit()
    assignments = await session.execute(
        select(TeacherClassAssignment).where(TeacherClassAssignment.class_id == class_id)
    )
    return SchoolAdminClassOut(
        id=str(school_class.id), grade=school_class.grade, section=school_class.section,
        student_count=await student_count(session, school_class.id),
        assignments=[
            ClassAssignmentOut(teacher_id=str(a.teacher_id), subject_id=str(a.subject_id))
            for a in assignments.scalars().all()
        ],
        status=school_class.status,
    )


@router.delete("/classes/{class_id}", summary="Permanently delete a class")
async def delete_school_class(
    class_id: str,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    """Blocks up front (rather than letting a delete fail partway through)
    when the class still has students, or has Tests/Homework recorded
    against it - deactivate instead to hide it without losing that history.
    """
    result = await session.execute(
        select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.school_id == user.school_id)
    )
    school_class = result.scalar_one_or_none()
    if school_class is None:
        return {"deleted": True}

    remaining_students = await student_count(session, school_class.id)
    if remaining_students > 0:
        raise ConflictError(
            f"This class still has {remaining_students} student(s). Move or remove them first."
        )
    has_activity = await _row_exists(session, VoiceTest.class_id, school_class.id) or await _row_exists(
        session, Homework.class_id, school_class.id
    )
    if has_activity:
        raise ConflictError(
            "This class has Tests, Homework, or other activity recorded against it and can't be "
            "deleted. Deactivate it instead."
        )

    assignments = await session.execute(
        select(TeacherClassAssignment).where(TeacherClassAssignment.class_id == class_id)
    )
    for row in assignments.scalars().all():
        await session.delete(row)
    await session.flush()  # no ORM relationship links these two tables, so explicit ordering is needed
    await session.delete(school_class)
    await audit_repository.record(
        session, actor_id=user.id, action="class.deleted", target_type="class", target_id=class_id
    )
    await session.commit()
    return {"deleted": True}


@router.put("/classes/{class_id}/assignments", summary="Assign teacher + subject")
async def update_class_assignments(
    class_id: str,
    body: UpdateClassAssignmentsIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAdminClassOut:
    """Full replace of this class's teacher/subject pairings, same pattern
    as Question Paper's question-order PUT.
    """
    result = await session.execute(
        select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.school_id == user.school_id)
    )
    school_class = result.scalar_one_or_none()
    if school_class is None:
        raise NotFoundError(f'No class with id "{class_id}" in your school.')

    existing = await session.execute(
        select(TeacherClassAssignment).where(TeacherClassAssignment.class_id == class_id)
    )
    for row in existing.scalars().all():
        await session.delete(row)
    await session.flush()

    for a in body.assignments:
        session.add(
            TeacherClassAssignment(teacher_id=a.teacher_id, class_id=class_id, subject_id=a.subject_id)
        )
    await audit_repository.record(
        session, actor_id=user.id, action="class.assignments.updated", target_type="class", target_id=class_id
    )
    await session.commit()

    assignments = await session.execute(
        select(TeacherClassAssignment).where(TeacherClassAssignment.class_id == class_id)
    )
    return SchoolAdminClassOut(
        id=str(school_class.id), grade=school_class.grade, section=school_class.section,
        student_count=await student_count(session, school_class.id),
        assignments=[
            ClassAssignmentOut(teacher_id=str(a.teacher_id), subject_id=str(a.subject_id))
            for a in assignments.scalars().all()
        ],
        status=school_class.status,
    )


@router.get("/curriculum")
async def get_school_curriculum(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolCurriculumOut:
    subjects_result = await session.execute(select(Subject))
    subjects = subjects_result.scalars().all()
    enabled_result = await session.execute(
        select(SchoolCurriculum.subject_id).where(
            SchoolCurriculum.school_id == user.school_id, SchoolCurriculum.enabled.is_(True)
        )
    )
    enabled_ids = {row[0] for row in enabled_result.all()}
    return SchoolCurriculumOut(
        board="",
        subjects=[
            SubjectToggle(id=str(s.id), name=s.name, enabled=s.id in enabled_ids) for s in subjects
        ],
    )


@router.put("/curriculum")
async def update_school_curriculum(
    body: UpdateSchoolCurriculumIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolCurriculumOut:
    existing = await session.execute(
        select(SchoolCurriculum).where(SchoolCurriculum.school_id == user.school_id)
    )
    by_subject = {row.subject_id: row for row in existing.scalars().all()}

    enabled_ids = set(body.subject_ids)
    for subject_id, row in by_subject.items():
        row.enabled = subject_id in enabled_ids
    for subject_id in enabled_ids - set(by_subject.keys()):
        session.add(SchoolCurriculum(school_id=user.school_id, subject_id=subject_id, enabled=True))
    await audit_repository.record(
        session, actor_id=user.id, action="curriculum.updated", target_type="school", target_id=str(user.school_id)
    )
    await session.commit()

    return await get_school_curriculum(user=user, session=session)


@router.post("/curriculum/subjects", status_code=201, summary="Add a subject not yet in the catalog")
async def create_school_subject(
    body: CreateSchoolSubjectIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SubjectToggle:
    """The one write School Admin gets against the otherwise Super-Admin-
    only global Subject catalog (see admin_catalog.py's module docstring) -
    reuses an existing subject by case-insensitive name match instead of
    always inserting, so two schools both asking for "Sanskrit" share one
    catalog row rather than colliding on Subject.name's unique constraint.
    Either way, the result is enabled for the caller's own school only.
    """
    name = body.name.strip()
    if not name:
        raise ConflictError("Subject name can't be empty.")

    existing = await session.execute(select(Subject).where(func.lower(Subject.name) == name.lower()))
    subject = existing.scalar_one_or_none()
    if subject is None:
        subject = Subject(name=name)
        session.add(subject)
        await session.flush()
        await audit_repository.record(
            session, actor_id=user.id, action="subject.created", target_type="subject", target_id=str(subject.id)
        )

    curriculum_row = await session.execute(
        select(SchoolCurriculum).where(
            SchoolCurriculum.school_id == user.school_id, SchoolCurriculum.subject_id == subject.id
        )
    )
    row = curriculum_row.scalar_one_or_none()
    if row is None:
        session.add(SchoolCurriculum(school_id=user.school_id, subject_id=subject.id, enabled=True))
    else:
        row.enabled = True
    await audit_repository.record(
        session, actor_id=user.id, action="curriculum.subject_added", target_type="subject", target_id=str(subject.id)
    )
    await session.commit()
    return SubjectToggle(id=str(subject.id), name=subject.name, enabled=True)


@router.get("/datasets")
async def get_school_datasets(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolDatasetOut]:
    datasets_result = await session.execute(select(Dataset))
    datasets = datasets_result.scalars().all()
    enabled_result = await session.execute(
        select(SchoolDataset.dataset_id).where(
            SchoolDataset.school_id == user.school_id, SchoolDataset.enabled.is_(True)
        )
    )
    enabled_ids = {row[0] for row in enabled_result.all()}
    items = [
        SchoolDatasetOut(
            id=str(d.id),
            name=d.name,
            question_count=d.question_count,
            description=d.description,
            enabled=d.id in enabled_ids,
        )
        for d in datasets
    ]
    return ListEnvelope(items=items, total=len(items))


@router.put("/datasets")
async def update_school_datasets(
    body: UpdateSchoolDatasetsIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolDatasetOut]:
    existing = await session.execute(
        select(SchoolDataset).where(SchoolDataset.school_id == user.school_id)
    )
    # Keyed by str(dataset_id): body.dataset_ids is list[str] off the wire,
    # while row.dataset_id is a UUID object - comparing/diffing them
    # directly would silently never match (see update_school_curriculum's
    # identical-shaped code just above, which has this exact bug today).
    by_dataset = {str(row.dataset_id): row for row in existing.scalars().all()}

    enabled_ids = set(body.dataset_ids)
    for dataset_id, row in by_dataset.items():
        row.enabled = dataset_id in enabled_ids
    for dataset_id in enabled_ids - set(by_dataset.keys()):
        session.add(SchoolDataset(school_id=user.school_id, dataset_id=dataset_id, enabled=True))
    await audit_repository.record(
        session, actor_id=user.id, action="datasets.updated", target_type="school", target_id=str(user.school_id)
    )
    await session.commit()

    return await get_school_datasets(user=user, session=session)


@router.get("/analytics")
async def get_school_analytics(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAnalyticsOut:
    classes_result = await session.execute(select(SchoolClass).where(SchoolClass.school_id == user.school_id))
    classes = classes_result.scalars().all()

    school_mastery_row = await session.execute(
        select(func.avg(StudentTestResult.mastery_percent))
        .join(VoiceTest, VoiceTest.id == StudentTestResult.test_id)
        .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    school_mastery_avg = school_mastery_row.scalar_one_or_none()

    class_breakdown = []
    for c in classes:
        mastery_row = await session.execute(
            select(func.avg(StudentTestResult.mastery_percent))
            .join(VoiceTest, VoiceTest.id == StudentTestResult.test_id)
            .where(VoiceTest.class_id == c.id)
        )
        mastery_avg = mastery_row.scalar_one_or_none()

        # Improvement = the average after-minus-before delta across every
        # topic in this class's Test -> Homework -> Retest loop that has
        # actually completed both halves (TopicPerformance's before/after
        # columns - see domain/models/improvement.py).
        improvement_row = await session.execute(
            select(func.avg(TopicPerformance.after_percent - TopicPerformance.before_percent))
            .join(Homework, Homework.id == TopicPerformance.homework_id)
            .where(
                Homework.class_id == c.id,
                TopicPerformance.before_percent.is_not(None),
                TopicPerformance.after_percent.is_not(None),
            )
        )
        improvement_avg = improvement_row.scalar_one_or_none()

        class_breakdown.append(
            ClassBreakdownOut(
                class_id=str(c.id), label=f"Class {c.grade} · {c.section}",
                mastery_avg_percent=round(mastery_avg) if mastery_avg is not None else 0,
                improvement_percent=round(improvement_avg) if improvement_avg is not None else 0,
            )
        )

    bloom_averages = []
    for level in BloomLevel:
        bloom_row = await session.execute(
            select(func.avg(StudentTestResultBloomScore.percent))
            .join(
                StudentTestResult,
                StudentTestResult.id == StudentTestResultBloomScore.student_test_result_id,
            )
            .join(VoiceTest, VoiceTest.id == StudentTestResult.test_id)
            .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
            .where(SchoolClass.school_id == user.school_id, StudentTestResultBloomScore.bloom_level == level)
        )
        percent = bloom_row.scalar_one_or_none()
        # None stays None ("not assessed") rather than 0 - see BloomScore's
        # docstring; only a real score of 0 should ever render as 0%.
        bloom_averages.append(BloomScore(level=level, percent=round(percent) if percent is not None else None))

    return SchoolAnalyticsOut(
        school_mastery_avg_percent=round(school_mastery_avg) if school_mastery_avg is not None else 0,
        class_breakdown=class_breakdown,
        bloom_averages=bloom_averages,
    )


@router.get("/curriculum/default-bloom-distribution")
async def get_default_bloom_distribution(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> BloomDistributionOut:
    school = await session.get(School, user.school_id)
    return BloomDistributionOut(distribution=school.default_bloom_distribution)


@router.put("/curriculum/default-bloom-distribution")
async def update_default_bloom_distribution(
    body: UpdateBloomDistributionIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> BloomDistributionOut:
    school = await session.get(School, user.school_id)
    school.default_bloom_distribution = {level.value: value for level, value in body.distribution.items()}
    await audit_repository.record(
        session, actor_id=user.id, action="school.bloom_distribution.updated",
        target_type="school", target_id=str(user.school_id),
    )
    await session.commit()
    await session.refresh(school)
    return BloomDistributionOut(distribution=school.default_bloom_distribution)


@router.get("/subscription")
async def get_school_subscription(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolSubscriptionOut:
    result = await session.execute(select(Subscription).where(Subscription.school_id == user.school_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        raise NotFoundError("No subscription for your school.")
    plan = await session.get(Plan, sub.plan_id)
    return SchoolSubscriptionOut(
        school_id=str(sub.school_id), plan_id=str(sub.plan_id), status=sub.status, renews_at=sub.renews_at,
        plan_name=plan.name,
        teacher_count=await count_teachers(session, user.school_id), teacher_limit=plan.teacher_limit,
        student_count=await count_students(session, user.school_id), student_limit=plan.student_limit,
        test_count=await count_tests(session, user.school_id), test_limit=plan.test_limit,
        question_paper_count=await count_question_papers(session, user.school_id),
        question_paper_limit=plan.question_paper_limit,
    )


@router.get("/me", summary="The signed-in School Admin's own account")
async def get_school_admin_me(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAdminMeOut:
    school = await session.get(School, user.school_id)
    return SchoolAdminMeOut(
        id=str(user.id), display_name=user.display_name, email=user.email,
        phone_number=user.phone_number, school_name=school.name if school else "",
    )


@router.patch("/me", summary="Edit the signed-in School Admin's own profile")
async def update_school_admin_me(
    body: UpdateSchoolAdminMeIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAdminMeOut:
    """Self-service only, deliberately separate from PATCH
    /admin/school-admins/{id} (Super Admin editing *someone else's*
    School Admin account) - that route is require_role(SUPER_ADMIN) and
    can't authorize a School Admin acting on themselves.
    """
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.phone_number is not None:
        user.phone_number = body.phone_number
    await audit_repository.record(
        session, actor_id=user.id, action="school_admin.self_updated", target_type="user", target_id=str(user.id)
    )
    await session.commit()
    school = await session.get(School, user.school_id)
    return SchoolAdminMeOut(
        id=str(user.id), display_name=user.display_name, email=user.email,
        phone_number=user.phone_number, school_name=school.name if school else "",
    )
