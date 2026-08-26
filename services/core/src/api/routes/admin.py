from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, NotFoundError

from src.api.deps import get_db_session, require_role
from src.api.schemas.admin import (
    AuditLogEntryOut,
    CreatePlanIn,
    CreateSchoolIn,
    CreateSubscriptionIn,
    InviteSchoolAdminIn,
    InviteSchoolAdminOut,
    PlanOut,
    PlatformAnalyticsOut,
    ResetPasswordOut,
    SchoolAdminOut,
    SchoolBreakdownOut,
    SchoolOut,
    SeatsOut,
    SubscriptionOut,
    UpdatePlanIn,
    UpdateSchoolAdminIn,
    UpdateSchoolAdminStatusIn,
    UpdateSchoolIn,
    UpdateSchoolStatusIn,
    UpdateSubscriptionIn,
)
from src.api.schemas.bloom import BloomDistributionOut, UpdateBloomDistributionIn
from src.api.schemas.common import ListEnvelope
from src.domain.models import (
    AuditLog,
    Homework,
    Plan,
    Role,
    School,
    SchoolClass,
    SchoolStatus,
    StudentTestResult,
    Subscription,
    User,
    UserStatus,
    VoiceTest,
)
from src.repositories import audit_repository
from src.services.user_provisioning import create_firebase_user, reset_password

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def _counts_for_school(session: AsyncSession, school_id) -> tuple[int, int]:
    teachers = await session.execute(
        select(func.count()).select_from(User).where(User.school_id == school_id, User.role == Role.TEACHER)
    )
    students = await session.execute(
        select(func.count()).select_from(User).where(User.school_id == school_id, User.role == Role.STUDENT)
    )
    return teachers.scalar_one(), students.scalar_one()


async def _plan_id_for_school(session: AsyncSession, school_id) -> str | None:
    """SchoolOut.planId is always resolved via the school's Subscription
    row - see School.plan_id's deprecation note in
    src/domain/models/foundation.py.
    """
    result = await session.execute(select(Subscription.plan_id).where(Subscription.school_id == school_id))
    plan_id = result.scalar_one_or_none()
    return str(plan_id) if plan_id else None


async def _serialize_school(session: AsyncSession, school: School) -> SchoolOut:
    teacher_count, student_count = await _counts_for_school(session, school.id)
    return SchoolOut(
        id=str(school.id),
        name=school.name,
        board=school.board,
        city=school.city,
        address=school.address,
        contact_email=school.contact_email,
        contact_phone=school.contact_phone,
        principal_name=school.principal_name,
        status=school.status,
        plan_id=await _plan_id_for_school(session, school.id),
        teacher_count=teacher_count,
        student_count=student_count,
        created_at=school.created_at,
    )


@router.get("/schools")
async def list_schools(
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolOut]:
    result = await session.execute(select(School))
    items = [await _serialize_school(session, s) for s in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


async def _get_school(session: AsyncSession, school_id: str) -> School:
    result = await session.execute(select(School).where(School.id == school_id))
    school = result.scalar_one_or_none()
    if school is None:
        raise NotFoundError(f'No school with id "{school_id}".')
    return school


@router.get("/schools/{school_id}")
async def get_school(
    school_id: str,
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolOut:
    school = await _get_school(session, school_id)
    return await _serialize_school(session, school)


@router.post("/schools", status_code=201, summary="Onboard a school")
async def create_school(
    body: CreateSchoolIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolOut:
    school = School(
        name=body.name,
        board=body.board,
        city=body.city,
        contact_email=body.contact_email,
        address=body.address,
        contact_phone=body.contact_phone,
        principal_name=body.principal_name,
        plan_id=body.plan_id,
        status=SchoolStatus.ONBOARDING,
    )
    session.add(school)
    await session.flush()

    # Onboarding always creates the initial subscription in the same
    # transaction - previously this only stamped School.plan_id, leaving
    # schools with no real Subscription row (the "404 on subscription"
    # gap this session hit against a manually-seeded school).
    session.add(
        Subscription(
            school_id=school.id,
            plan_id=body.plan_id,
            renews_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    await audit_repository.record(
        session, actor_id=actor.id, action="school.onboarded", target_type="school", target_id=str(school.id)
    )
    await session.commit()
    await session.refresh(school)
    return await _serialize_school(session, school)


@router.patch("/schools/{school_id}/status")
async def update_school_status(
    school_id: str,
    body: UpdateSchoolStatusIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolOut:
    """Suspending a school cuts off API access for every teacher/student/
    School Admin under it - enforced by require_role's school-scoped
    dependents rejecting anything under a non-ACTIVE school, not just
    hidden in a UI.
    """
    school = await _get_school(session, school_id)
    school.status = body.status
    await audit_repository.record(
        session, actor_id=actor.id, action="school.status.updated", target_type="school", target_id=school_id
    )
    await session.commit()
    await session.refresh(school)
    return await _serialize_school(session, school)


@router.patch("/schools/{school_id}", summary="Edit a school's profile")
async def update_school(
    school_id: str,
    body: UpdateSchoolIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolOut:
    school = await _get_school(session, school_id)
    for field in ("name", "board", "city", "contact_email", "address", "contact_phone", "principal_name"):
        value = getattr(body, field)
        if value is not None:
            setattr(school, field, value)
    await audit_repository.record(
        session, actor_id=actor.id, action="school.updated", target_type="school", target_id=school_id
    )
    await session.commit()
    await session.refresh(school)
    return await _serialize_school(session, school)


@router.get("/schools/{school_id}/default-bloom-distribution")
async def get_school_default_bloom_distribution(
    school_id: str,
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> BloomDistributionOut:
    school = await _get_school(session, school_id)
    return BloomDistributionOut(distribution=school.default_bloom_distribution)


@router.put("/schools/{school_id}/default-bloom-distribution", summary="Override a school's default Bloom mix")
async def update_school_default_bloom_distribution(
    school_id: str,
    body: UpdateBloomDistributionIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> BloomDistributionOut:
    school = await _get_school(session, school_id)
    school.default_bloom_distribution = {level.value: value for level, value in body.distribution.items()}
    await audit_repository.record(
        session, actor_id=actor.id, action="school.bloom_distribution.updated",
        target_type="school", target_id=school_id,
    )
    await session.commit()
    await session.refresh(school)
    return BloomDistributionOut(distribution=school.default_bloom_distribution)


def _plan_out(p: Plan) -> PlanOut:
    return PlanOut(
        id=str(p.id), name=p.name, price_label=p.price_label,
        teacher_limit=p.teacher_limit, student_limit=p.student_limit,
        test_limit=p.test_limit, question_paper_limit=p.question_paper_limit,
        active=p.active,
    )


@router.get("/plans", summary="Subscription plan catalog")
async def list_plans(
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[PlanOut]:
    result = await session.execute(select(Plan))
    items = [_plan_out(p) for p in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.post("/plans", status_code=201, summary="Create a plan")
async def create_plan(
    body: CreatePlanIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> PlanOut:
    plan = Plan(
        name=body.name, price_label=body.price_label,
        teacher_limit=body.teacher_limit, student_limit=body.student_limit,
        test_limit=body.test_limit, question_paper_limit=body.question_paper_limit,
    )
    session.add(plan)
    await session.flush()
    await audit_repository.record(
        session, actor_id=actor.id, action="plan.created", target_type="plan", target_id=str(plan.id)
    )
    await session.commit()
    await session.refresh(plan)
    return _plan_out(plan)


@router.patch("/plans/{plan_id}", summary="Edit a plan")
async def update_plan(
    plan_id: str,
    body: UpdatePlanIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> PlanOut:
    result = await session.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise NotFoundError(f'No plan with id "{plan_id}".')

    for field in ("name", "price_label", "teacher_limit", "student_limit", "test_limit", "question_paper_limit", "active"):
        value = getattr(body, field)
        if value is not None:
            setattr(plan, field, value)

    await audit_repository.record(
        session, actor_id=actor.id, action="plan.updated", target_type="plan", target_id=plan_id
    )
    await session.commit()
    await session.refresh(plan)
    return _plan_out(plan)


async def _serialize_subscription(session: AsyncSession, sub: Subscription) -> SubscriptionOut:
    plan_result = await session.execute(select(Plan).where(Plan.id == sub.plan_id))
    plan = plan_result.scalar_one_or_none()
    teacher_count, student_count = await _counts_for_school(session, sub.school_id)
    return SubscriptionOut(
        school_id=str(sub.school_id),
        plan_id=str(sub.plan_id),
        status=sub.status,
        renews_at=sub.renews_at,
        seats_used=SeatsOut(teachers=teacher_count, students=student_count),
        seats_limit=SeatsOut(
            teachers=plan.teacher_limit if plan else 0, students=plan.student_limit if plan else 0
        ),
    )


@router.get("/schools/{school_id}/subscription")
async def get_school_subscription(
    school_id: str,
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionOut:
    result = await session.execute(select(Subscription).where(Subscription.school_id == school_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        raise NotFoundError(f'No subscription for school "{school_id}".')
    return await _serialize_subscription(session, sub)


@router.post("/schools/{school_id}/subscription", status_code=201, summary="Create a subscription")
async def create_school_subscription(
    school_id: str,
    body: CreateSubscriptionIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionOut:
    """Covers schools that predate onboarding auto-creating a subscription,
    or that need one re-created. 409 if the school already has one - use
    PUT to change an existing subscription instead.
    """
    await _get_school(session, school_id)
    existing = await session.execute(select(Subscription).where(Subscription.school_id == school_id))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("This school already has a subscription - use PUT to change it instead.")

    plan_result = await session.execute(select(Plan).where(Plan.id == body.plan_id))
    if plan_result.scalar_one_or_none() is None:
        raise NotFoundError(f'No plan with id "{body.plan_id}".')

    sub = Subscription(
        school_id=school_id,
        plan_id=body.plan_id,
        status=body.status,
        renews_at=body.renews_at or (datetime.now(timezone.utc) + timedelta(days=30)),
    )
    session.add(sub)
    await audit_repository.record(
        session, actor_id=actor.id, action="subscription.created", target_type="school", target_id=school_id
    )
    await session.commit()
    await session.refresh(sub)
    return await _serialize_subscription(session, sub)


@router.put("/schools/{school_id}/subscription", summary="Change a subscription")
async def update_school_subscription(
    school_id: str,
    body: UpdateSubscriptionIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionOut:
    result = await session.execute(select(Subscription).where(Subscription.school_id == school_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        raise NotFoundError(f'No subscription for school "{school_id}".')

    if body.plan_id is not None:
        plan_result = await session.execute(select(Plan).where(Plan.id == body.plan_id))
        plan = plan_result.scalar_one_or_none()
        if plan is None:
            raise NotFoundError(f'No plan with id "{body.plan_id}".')
        teacher_count, student_count = await _counts_for_school(session, school_id)
        if teacher_count > plan.teacher_limit or student_count > plan.student_limit:
            raise ConflictError("New plan's limit is below the school's current seat usage.")
        sub.plan_id = body.plan_id

    if body.status is not None:
        sub.status = body.status
    if body.renews_at is not None:
        sub.renews_at = body.renews_at

    await audit_repository.record(
        session, actor_id=actor.id, action="subscription.updated", target_type="school", target_id=school_id
    )
    await session.commit()
    await session.refresh(sub)
    return await _serialize_subscription(session, sub)


async def _mastery_avg_for_school(session: AsyncSession, school_id) -> int:
    row = await session.execute(
        select(func.avg(StudentTestResult.mastery_percent))
        .join(VoiceTest, VoiceTest.id == StudentTestResult.test_id)
        .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
        .where(SchoolClass.school_id == school_id)
    )
    avg = row.scalar_one_or_none()
    return round(avg) if avg is not None else 0


@router.get("/analytics/platform")
async def get_platform_analytics(
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformAnalyticsOut:
    schools_result = await session.execute(select(School))
    schools = schools_result.scalars().all()
    active_schools = [s for s in schools if s.status == SchoolStatus.ACTIVE]

    total_teachers = await session.execute(select(func.count()).select_from(User).where(User.role == Role.TEACHER))
    total_students = await session.execute(select(func.count()).select_from(User).where(User.role == Role.STUDENT))

    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    tests_this_month_row = await session.execute(
        select(func.count()).select_from(VoiceTest).where(VoiceTest.created_at >= month_start)
    )
    tests_this_month = tests_this_month_row.scalar_one()

    # All-time completion rate: Homework.assigned_count/completed_count are
    # running totals already maintained on the row itself (see
    # domain/models/homework.py), not something this endpoint recomputes
    # from StudentHomeworkProgress - simplest honest number available
    # without inventing a "this month" homework-assignment window.
    homework_totals = await session.execute(select(func.sum(Homework.assigned_count), func.sum(Homework.completed_count)))
    assigned_total, completed_total = homework_totals.one()
    homework_completion_rate_percent = (
        round((completed_total or 0) / assigned_total * 100) if assigned_total else 0
    )

    breakdown = []
    for school in schools:
        teacher_count, student_count = await _counts_for_school(session, school.id)
        breakdown.append(
            SchoolBreakdownOut(
                school_id=str(school.id), name=school.name, active_teachers=teacher_count,
                active_students=student_count,
                mastery_avg_percent=await _mastery_avg_for_school(session, school.id),
            )
        )

    return PlatformAnalyticsOut(
        total_schools=len(schools),
        active_schools=len(active_schools),
        total_teachers=total_teachers.scalar_one(),
        total_students=total_students.scalar_one(),
        tests_this_month=tests_this_month,
        homework_completion_rate_percent=homework_completion_rate_percent,
        school_breakdown=breakdown,
    )


@router.get("/school-admins")
async def list_school_admins(
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SchoolAdminOut]:
    result = await session.execute(select(User).where(User.role == Role.SCHOOL_ADMIN))
    items = [
        SchoolAdminOut(
            id=str(u.id), school_id=str(u.school_id) if u.school_id else "",
            display_name=u.display_name, email=u.email, status=u.status,
        )
        for u in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))


@router.post("/school-admins/invite", status_code=201)
async def invite_school_admin(
    body: InviteSchoolAdminIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> InviteSchoolAdminOut:
    await _get_school(session, body.school_id)

    provisioned = create_firebase_user(email=body.email, display_name=body.display_name, role=Role.SCHOOL_ADMIN)

    admin_user = User(
        firebase_uid=provisioned.firebase_uid,
        email=body.email,
        display_name=body.display_name,
        role=Role.SCHOOL_ADMIN,
        school_id=body.school_id,
        status=UserStatus.ACTIVE,
        phone_number=body.phone_number,
        must_change_password=True,
    )
    session.add(admin_user)
    await session.flush()
    await audit_repository.record(
        session, actor_id=actor.id, action="school_admin.invited", target_type="user", target_id=str(admin_user.id)
    )
    await session.commit()
    await session.refresh(admin_user)
    return InviteSchoolAdminOut(
        id=str(admin_user.id), school_id=str(admin_user.school_id), display_name=admin_user.display_name,
        email=admin_user.email, status=admin_user.status, temp_password=provisioned.temp_password,
    )


@router.patch("/school-admins/{admin_id}/status")
async def update_school_admin_status(
    admin_id: str,
    body: UpdateSchoolAdminStatusIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAdminOut:
    result = await session.execute(
        select(User).where(User.id == admin_id, User.role == Role.SCHOOL_ADMIN)
    )
    admin_user = result.scalar_one_or_none()
    if admin_user is None:
        raise NotFoundError(f'No School Admin with id "{admin_id}".')
    admin_user.status = body.status
    await audit_repository.record(
        session, actor_id=actor.id, action="school_admin.status.updated", target_type="user", target_id=admin_id
    )
    await session.commit()
    return SchoolAdminOut(
        id=str(admin_user.id), school_id=str(admin_user.school_id), display_name=admin_user.display_name,
        email=admin_user.email, status=admin_user.status,
    )


async def _get_school_admin(session: AsyncSession, admin_id: str) -> User:
    result = await session.execute(select(User).where(User.id == admin_id, User.role == Role.SCHOOL_ADMIN))
    admin_user = result.scalar_one_or_none()
    if admin_user is None:
        raise NotFoundError(f'No School Admin with id "{admin_id}".')
    return admin_user


@router.patch("/school-admins/{admin_id}", summary="Edit a School Admin's profile")
async def update_school_admin(
    admin_id: str,
    body: UpdateSchoolAdminIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SchoolAdminOut:
    admin_user = await _get_school_admin(session, admin_id)
    if body.display_name is not None:
        admin_user.display_name = body.display_name
    if body.phone_number is not None:
        admin_user.phone_number = body.phone_number
    await audit_repository.record(
        session, actor_id=actor.id, action="school_admin.updated", target_type="user", target_id=admin_id
    )
    await session.commit()
    return SchoolAdminOut(
        id=str(admin_user.id), school_id=str(admin_user.school_id), display_name=admin_user.display_name,
        email=admin_user.email, status=admin_user.status,
    )


@router.post("/school-admins/{admin_id}/reset-password", summary="Issue a new temp password")
async def reset_school_admin_password(
    admin_id: str,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ResetPasswordOut:
    admin_user = await _get_school_admin(session, admin_id)
    if admin_user.firebase_uid is None:
        raise ConflictError("This School Admin has no Firebase account to reset.")
    temp_password = reset_password(firebase_uid=admin_user.firebase_uid, role=Role.SCHOOL_ADMIN)
    admin_user.must_change_password = True
    await audit_repository.record(
        session, actor_id=actor.id, action="school_admin.password_reset", target_type="user", target_id=admin_id
    )
    await session.commit()
    return ResetPasswordOut(temp_password=temp_password)


@router.get("/audit-log")
async def list_audit_log(
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[AuditLogEntryOut]:
    result = await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()))
    items = [
        AuditLogEntryOut(
            id=str(a.id), actor_id=str(a.actor_id), action=a.action,
            target_type=a.target_type, target_id=a.target_id, created_at=a.created_at,
        )
        for a in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))
