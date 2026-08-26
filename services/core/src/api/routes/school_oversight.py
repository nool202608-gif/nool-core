"""Read-only, school-wide oversight for School Admin - Voice Tests,
Homework, Question Papers, Retest Progress, Improvement, and a school-wide
Leaderboard, none of which had any school-scoped view before this (every
one of the underlying resources was Teacher-only, or Student-only for the
leaderboard). School Admin never creates/edits this content - only
observes it - so every route here is a GET.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, require_role
from src.api.schemas.common import ListEnvelope
from src.api.schemas.school_oversight import (
    SchoolAuditLogEntryOut,
    SchoolHomeworkOut,
    SchoolImprovementOut,
    SchoolLeaderboardEntryOut,
    SchoolQuestionPaperOut,
    SchoolRetestProgressOut,
    SchoolVoiceTestOut,
)
from src.domain.models import (
    AuditLog,
    Homework,
    QuestionPaper,
    RetestAttempt,
    Role,
    SchoolClass,
    StudentPoints,
    StudentProfile,
    StudentRetestStatus,
    Subject,
    TeacherClassAssignment,
    User,
    VoiceTest,
)

router = APIRouter(prefix="/api/v1/school", tags=["school-oversight"])


def _class_label(school_class: SchoolClass) -> str:
    return f"Class {school_class.grade} · {school_class.section}"


async def _teacher_names_for(
    session: AsyncSession, class_subject_pairs: set[tuple[UUID, UUID]]
) -> dict[tuple[UUID, UUID], str]:
    """Best-effort (class_id, subject_id) -> teacher display name lookup.
    VoiceTest/Homework don't record who created them, only the class they
    belong to - the teacher is derived via TeacherClassAssignment instead.
    If more than one teacher is assigned to the same class+subject
    (co-teaching), this picks one deterministically rather than listing
    all - good enough for an oversight table, not a source of truth.
    """
    if not class_subject_pairs:
        return {}
    class_ids = {pair[0] for pair in class_subject_pairs}
    subject_ids = {pair[1] for pair in class_subject_pairs}
    result = await session.execute(
        select(TeacherClassAssignment.class_id, TeacherClassAssignment.subject_id, User.display_name)
        .join(User, User.id == TeacherClassAssignment.teacher_id)
        .where(
            TeacherClassAssignment.class_id.in_(class_ids),
            TeacherClassAssignment.subject_id.in_(subject_ids),
        )
    )
    names: dict[tuple[UUID, UUID], str] = {}
    for class_id, subject_id, display_name in result.all():
        names.setdefault((class_id, subject_id), display_name)
    return names


@router.get("/voice-tests")
async def list_school_voice_tests(
    class_id: str | None = Query(default=None, alias="classId"),
    teacher_id: str | None = Query(default=None, alias="teacherId"),
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolVoiceTestOut]:
    base = (
        select(VoiceTest, SchoolClass, Subject)
        .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
        .join(Subject, Subject.id == VoiceTest.subject_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    if class_id is not None:
        base = base.where(VoiceTest.class_id == class_id)
    if teacher_id is not None:
        base = base.where(
            exists(
                select(TeacherClassAssignment.id).where(
                    TeacherClassAssignment.teacher_id == teacher_id,
                    TeacherClassAssignment.class_id == VoiceTest.class_id,
                    TeacherClassAssignment.subject_id == VoiceTest.subject_id,
                )
            )
        )

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await session.execute(base.order_by(VoiceTest.created_at.desc()).limit(limit).offset(offset))
    ).all()

    teacher_names = await _teacher_names_for(
        session, {(test.class_id, test.subject_id) for test, _, _ in rows}
    )
    items = [
        SchoolVoiceTestOut(
            id=str(test.id),
            class_label=_class_label(school_class),
            subject_name=subject.name,
            teacher_name=teacher_names.get((test.class_id, test.subject_id)),
            status=test.status,
            assigned_count=test.assigned_count,
            completed_count=test.completed_count,
            created_at=test.created_at,
        )
        for test, school_class, subject in rows
    ]
    return ListEnvelope(items=items, total=total)


@router.get("/homework")
async def list_school_homework(
    class_id: str | None = Query(default=None, alias="classId"),
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolHomeworkOut]:
    base = (
        select(Homework, SchoolClass, VoiceTest.subject_id)
        .join(SchoolClass, SchoolClass.id == Homework.class_id)
        .join(VoiceTest, VoiceTest.id == Homework.test_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    if class_id is not None:
        base = base.where(Homework.class_id == class_id)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.limit(limit).offset(offset))).all()

    teacher_names = await _teacher_names_for(
        session, {(hw.class_id, subject_id) for hw, _, subject_id in rows}
    )
    items = [
        SchoolHomeworkOut(
            id=str(hw.id),
            class_label=_class_label(school_class),
            gap_topic=hw.gap_topic,
            teacher_name=teacher_names.get((hw.class_id, subject_id)),
            status=hw.status,
            assigned_count=hw.assigned_count,
            completed_count=hw.completed_count,
        )
        for hw, school_class, subject_id in rows
    ]
    return ListEnvelope(items=items, total=total)


@router.get("/question-papers")
async def list_school_question_papers(
    subject_id: str | None = Query(default=None, alias="subjectId"),
    created_by: str | None = Query(default=None, alias="createdBy"),
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolQuestionPaperOut]:
    base = (
        select(QuestionPaper, Subject, User)
        .join(Subject, Subject.id == QuestionPaper.subject_id)
        .join(User, User.id == QuestionPaper.created_by)
        .where(QuestionPaper.school_id == user.school_id)
    )
    if subject_id is not None:
        base = base.where(QuestionPaper.subject_id == subject_id)
    if created_by is not None:
        base = base.where(QuestionPaper.created_by == created_by)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await session.execute(base.order_by(QuestionPaper.created_at.desc()).limit(limit).offset(offset))
    ).all()

    items = [
        SchoolQuestionPaperOut(
            id=str(paper.id),
            name=paper.name,
            exam_type=paper.exam_type,
            subject_name=subject.name,
            created_by_name=creator.display_name,
            status=paper.status,
            created_at=paper.created_at,
        )
        for paper, subject, creator in rows
    ]
    return ListEnvelope(items=items, total=total)


@router.get("/retest-progress")
async def list_school_retest_progress(
    class_id: str | None = Query(default=None, alias="classId"),
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolRetestProgressOut]:
    base = (
        select(Homework, SchoolClass)
        .join(SchoolClass, SchoolClass.id == Homework.class_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    if class_id is not None:
        base = base.where(Homework.class_id == class_id)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.limit(limit).offset(offset))).all()

    items = []
    for hw, school_class in rows:
        attempts = (
            await session.execute(select(RetestAttempt).where(RetestAttempt.homework_id == hw.id))
        ).scalars().all()
        completed = [a for a in attempts if a.status == StudentRetestStatus.COMPLETED]
        in_progress = [a for a in attempts if a.status == StudentRetestStatus.IN_PROGRESS]
        not_started = [a for a in attempts if a.status == StudentRetestStatus.ASSIGNED]
        items.append(
            SchoolRetestProgressOut(
                homework_id=str(hw.id),
                class_label=_class_label(school_class),
                gap_topic=hw.gap_topic,
                assigned_count=hw.assigned_count,
                completed_count=len(completed),
                in_progress_count=len(in_progress),
                not_started_count=len(not_started),
            )
        )
    return ListEnvelope(items=items, total=total)


@router.get("/improvement")
async def list_school_improvement(
    class_id: str | None = Query(default=None, alias="classId"),
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolImprovementOut]:
    base = (
        select(Homework, SchoolClass, VoiceTest.id.label("test_id"))
        .join(SchoolClass, SchoolClass.id == Homework.class_id)
        .join(VoiceTest, VoiceTest.id == Homework.test_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    if class_id is not None:
        base = base.where(Homework.class_id == class_id)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.limit(limit).offset(offset))).all()

    items = []
    for hw, school_class, test_id in rows:
        attempts = (
            await session.execute(select(RetestAttempt).where(RetestAttempt.homework_id == hw.id))
        ).scalars().all()
        completed = [a for a in attempts if a.status == StudentRetestStatus.RESULT_READY]
        baseline_vals = [a.baseline_percent for a in completed if a.baseline_percent is not None]
        retest_vals = [a.retest_percent for a in completed if a.retest_percent is not None]
        baseline_percent = round(sum(baseline_vals) / len(baseline_vals)) if baseline_vals else 0
        retest_percent = round(sum(retest_vals) / len(retest_vals)) if retest_vals else 0
        items.append(
            SchoolImprovementOut(
                test_id=str(test_id),
                homework_id=str(hw.id),
                class_label=_class_label(school_class),
                gap_topic=hw.gap_topic,
                baseline_percent=baseline_percent,
                retest_percent=retest_percent,
                improvement_percent=retest_percent - baseline_percent,
                assigned_count=hw.assigned_count,
                retested_count=len(completed),
            )
        )
    return ListEnvelope(items=items, total=total)


@router.get("/leaderboard")
async def get_school_leaderboard(
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolLeaderboardEntryOut]:
    """School-wide version of GET /me/leaderboard (which is per-class,
    Student-only) - same StudentPoints source, ranked across the whole
    school instead of one class.
    """
    rank = func.rank().over(order_by=StudentPoints.points.desc())
    base = (
        select(User.id, User.display_name, SchoolClass, StudentPoints.points, rank.label("rank"))
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(SchoolClass, SchoolClass.id == StudentProfile.class_id)
        .join(StudentPoints, StudentPoints.student_id == User.id, isouter=True)
        .where(SchoolClass.school_id == user.school_id)
    )
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await session.execute(
            base.order_by(StudentPoints.points.desc().nulls_last()).limit(limit).offset(offset)
        )
    ).all()
    items = [
        SchoolLeaderboardEntryOut(
            student_id=str(student_id),
            display_name=display_name,
            class_label=_class_label(school_class),
            points=points or 0,
            rank=rank_value,
        )
        for student_id, display_name, school_class, points, rank_value in rows
    ]
    return ListEnvelope(items=items, total=total)


@router.get("/audit-log", summary="This school's own activity log")
async def list_school_audit_log(
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolAuditLogEntryOut]:
    """School-scoped counterpart to GET /admin/audit-log - only entries
    whose actor belongs to this caller's own school (AuditLog has no
    school_id of its own, so this joins through the actor's User row).
    """
    base = (
        select(AuditLog, User.display_name)
        .join(User, User.id == AuditLog.actor_id)
        .where(User.school_id == user.school_id)
    )
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await session.execute(base.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset))
    ).all()
    items = [
        SchoolAuditLogEntryOut(
            id=str(entry.id), actor_name=actor_name, action=entry.action,
            target_type=entry.target_type, target_id=entry.target_id, created_at=entry.created_at,
        )
        for entry, actor_name in rows
    ]
    return ListEnvelope(items=items, total=total)
