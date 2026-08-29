"""The Class level (SchoolGrade) of School -> Class -> Section -> Students,
added additively alongside the pre-existing Section (SchoolClass) entity -
see database/migrations/versions/6f2f4d9c1a3e_school_grades.py's docstring
for why this is a new sibling table rather than a rename. Covers both
surfaces (school_admin.py's own-school routes, admin.py's cross-tenant
routes) plus the grade_id auto-linking on section create/edit, real rows
against the dev Postgres via db_session, same pattern as
test_admin_classes.py.
"""

import uuid

import pytest
from sqlalchemy import select

from shared.errors import ConflictError, NotFoundError

from src.api.routes import admin, school_admin
from src.api.schemas.school_admin import (
    CreateClassIn,
    CreateGradeIn,
    UpdateClassIn,
    UpdateGradeStatusIn,
)
from src.domain.models import Role, School, SchoolClass, SchoolGrade, StudentProfile, User, UserStatus


async def _seed_super_admin(db_session) -> User:
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()
    return super_admin


async def _seed_school(db_session) -> School:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_school_admin(db_session, school_id) -> User:
    admin_user = User(
        firebase_uid=f"admin-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Admin", role=Role.SCHOOL_ADMIN, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(admin_user)
    await db_session.flush()
    return admin_user


async def _seed_grade(db_session, school_id, *, grade=5) -> SchoolGrade:
    school_grade = SchoolGrade(school_id=school_id, grade=grade)
    db_session.add(school_grade)
    await db_session.flush()
    return school_grade


async def _seed_class(db_session, school_id, *, grade=5, section=None, grade_id=None) -> SchoolClass:
    section = section or f"S{uuid.uuid4().hex[:8]}"
    school_class = SchoolClass(school_id=school_id, grade=grade, section=section, grade_id=grade_id)
    db_session.add(school_class)
    await db_session.flush()
    return school_class


# --- School Admin surface (school_admin.py) --------------------------------


async def test_create_school_class_auto_creates_and_links_grade(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)

    out = await school_admin.create_school_class(
        CreateClassIn(grade=10, section="A"), user=admin_user, session=db_session
    )

    result = await db_session.execute(select(SchoolClass).where(SchoolClass.id == out.id))
    school_class = result.scalar_one()
    assert school_class.grade_id is not None

    grade_result = await db_session.execute(select(SchoolGrade).where(SchoolGrade.id == school_class.grade_id))
    school_grade = grade_result.scalar_one()
    assert school_grade.school_id == school.id
    assert school_grade.grade == 10


async def test_create_school_class_reuses_existing_grade_for_second_section(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)

    first = await school_admin.create_school_class(
        CreateClassIn(grade=10, section="A"), user=admin_user, session=db_session
    )
    second = await school_admin.create_school_class(
        CreateClassIn(grade=10, section="B"), user=admin_user, session=db_session
    )

    first_row = (await db_session.execute(select(SchoolClass).where(SchoolClass.id == first.id))).scalar_one()
    second_row = (await db_session.execute(select(SchoolClass).where(SchoolClass.id == second.id))).scalar_one()
    assert first_row.grade_id == second_row.grade_id

    grades = await db_session.execute(select(SchoolGrade).where(SchoolGrade.school_id == school.id))
    assert len(grades.scalars().all()) == 1


async def test_create_school_class_does_not_cross_link_grades_between_schools(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    admin_b = await _seed_school_admin(db_session, school_b.id)

    out_a = await school_admin.create_school_class(
        CreateClassIn(grade=10, section="A"), user=admin_a, session=db_session
    )
    out_b = await school_admin.create_school_class(
        CreateClassIn(grade=10, section="A"), user=admin_b, session=db_session
    )

    row_a = (await db_session.execute(select(SchoolClass).where(SchoolClass.id == out_a.id))).scalar_one()
    row_b = (await db_session.execute(select(SchoolClass).where(SchoolClass.id == out_b.id))).scalar_one()
    assert row_a.grade_id != row_b.grade_id


async def test_update_school_class_relinks_grade_when_grade_number_changes(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    created = await school_admin.create_school_class(
        CreateClassIn(grade=9, section="A"), user=admin_user, session=db_session
    )
    original_row = (await db_session.execute(select(SchoolClass).where(SchoolClass.id == created.id))).scalar_one()
    original_grade_id = original_row.grade_id

    await school_admin.update_school_class(
        created.id, UpdateClassIn(grade=10, section="A"), user=admin_user, session=db_session
    )

    updated_row = (await db_session.execute(select(SchoolClass).where(SchoolClass.id == created.id))).scalar_one()
    assert updated_row.grade_id != original_grade_id
    new_grade = (await db_session.execute(select(SchoolGrade).where(SchoolGrade.id == updated_row.grade_id))).scalar_one()
    assert new_grade.grade == 10


async def test_list_school_grades_scoped_to_own_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    await _seed_grade(db_session, school_a.id, grade=8)
    await _seed_grade(db_session, school_b.id, grade=9)

    result = await school_admin.list_school_grades(user=admin_a, session=db_session)

    assert result.total == 1
    assert result.items[0].grade == 8


async def test_create_school_grade_rejects_duplicate(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    await school_admin.create_school_grade(CreateGradeIn(grade=11), user=admin_user, session=db_session)

    with pytest.raises(ConflictError):
        await school_admin.create_school_grade(CreateGradeIn(grade=11), user=admin_user, session=db_session)


async def test_create_school_grade_allows_same_grade_number_at_different_schools(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    admin_b = await _seed_school_admin(db_session, school_b.id)

    out_a = await school_admin.create_school_grade(CreateGradeIn(grade=11), user=admin_a, session=db_session)
    out_b = await school_admin.create_school_grade(CreateGradeIn(grade=11), user=admin_b, session=db_session)
    assert out_a.id != out_b.id


async def test_school_grade_counts_reflect_real_sections_and_students(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    grade = await _seed_grade(db_session, school.id, grade=7)
    class_a = await _seed_class(db_session, school.id, grade=7, section="A", grade_id=grade.id)
    await _seed_class(db_session, school.id, grade=7, section="B", grade_id=grade.id)
    student = User(
        firebase_uid=f"student-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Student", role=Role.STUDENT, school_id=school.id, status=UserStatus.ACTIVE,
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(StudentProfile(user_id=student.id, class_id=class_a.id, roll_number=1))
    await db_session.flush()

    result = await school_admin.list_school_grades(user=admin_user, session=db_session)
    out = next(g for g in result.items if g.id == str(grade.id))
    assert out.section_count == 2
    assert out.student_count == 1


async def test_update_school_grade_status_round_trips(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    grade = await _seed_grade(db_session, school.id)

    out = await school_admin.update_school_grade_status(
        str(grade.id), UpdateGradeStatusIn(status=UserStatus.DEACTIVATED), user=admin_user, session=db_session
    )
    assert out.status == UserStatus.DEACTIVATED


async def test_update_school_grade_status_unknown_grade_404s(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    with pytest.raises(NotFoundError):
        await school_admin.update_school_grade_status(
            str(uuid.uuid4()), UpdateGradeStatusIn(status=UserStatus.DEACTIVATED),
            user=admin_user, session=db_session,
        )


async def test_delete_school_grade_blocked_when_sections_present(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    grade = await _seed_grade(db_session, school.id)
    await _seed_class(db_session, school.id, grade=grade.grade, grade_id=grade.id)

    with pytest.raises(ConflictError):
        await school_admin.delete_school_grade(str(grade.id), user=admin_user, session=db_session)


async def test_delete_school_grade_deletes_when_empty_and_is_idempotent(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    grade = await _seed_grade(db_session, school.id)

    result = await school_admin.delete_school_grade(str(grade.id), user=admin_user, session=db_session)
    assert result == {"deleted": True}

    result2 = await school_admin.delete_school_grade(str(grade.id), user=admin_user, session=db_session)
    assert result2 == {"deleted": True}


async def test_school_admin_cannot_see_or_touch_another_schools_grade(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    grade_b = await _seed_grade(db_session, school_b.id)

    with pytest.raises(NotFoundError):
        await school_admin.update_school_grade_status(
            str(grade_b.id), UpdateGradeStatusIn(status=UserStatus.DEACTIVATED),
            user=admin_a, session=db_session,
        )
    # Delete is idempotent-shaped (not a NotFoundError) - confirm it still
    # doesn't touch the other school's row, same reasoning as
    # delete_school_class's own cross-school test.
    result = await school_admin.delete_school_grade(str(grade_b.id), user=admin_a, session=db_session)
    assert result == {"deleted": True}
    still_there = await db_session.execute(select(SchoolGrade).where(SchoolGrade.id == grade_b.id))
    assert still_there.scalar_one_or_none() is not None


# --- Super Admin cross-tenant surface (admin.py) ----------------------------


async def test_list_grades_as_admin_scoped_to_one_school_only(db_session):
    super_admin = await _seed_super_admin(db_session)
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    grade_a = await _seed_grade(db_session, school_a.id, grade=6)
    await _seed_grade(db_session, school_b.id, grade=7)

    result = await admin.list_grades_as_admin(str(school_a.id), _=super_admin, session=db_session)

    assert result.total == 1
    assert result.items[0].id == str(grade_a.id)


async def test_list_grades_as_admin_unknown_school_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin.list_grades_as_admin(str(uuid.uuid4()), _=super_admin, session=db_session)


async def test_create_grade_as_admin_creates_in_target_school(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)

    result = await admin.create_grade_as_admin(
        str(school.id), CreateGradeIn(grade=8), actor=super_admin, session=db_session
    )
    assert result.grade == 8
    assert result.section_count == 0


async def test_create_grade_as_admin_rejects_duplicate(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    await admin.create_grade_as_admin(str(school.id), CreateGradeIn(grade=8), actor=super_admin, session=db_session)

    with pytest.raises(ConflictError):
        await admin.create_grade_as_admin(
            str(school.id), CreateGradeIn(grade=8), actor=super_admin, session=db_session
        )


async def test_create_class_as_admin_auto_links_grade(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)

    out = await admin.create_class_as_admin(
        str(school.id), CreateClassIn(grade=10, section="A"), actor=super_admin, session=db_session
    )
    school_class = (await db_session.execute(select(SchoolClass).where(SchoolClass.id == out.id))).scalar_one()
    assert school_class.grade_id is not None


async def test_update_grade_status_as_admin_no_school_filter(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    grade = await _seed_grade(db_session, school.id)

    out = await admin.update_grade_status_as_admin(
        str(grade.id), UpdateGradeStatusIn(status=UserStatus.DEACTIVATED), actor=super_admin, session=db_session
    )
    assert out.status == UserStatus.DEACTIVATED


async def test_delete_grade_as_admin_blocked_when_sections_present(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    grade = await _seed_grade(db_session, school.id)
    await _seed_class(db_session, school.id, grade=grade.grade, grade_id=grade.id)

    with pytest.raises(ConflictError):
        await admin.delete_grade_as_admin(str(grade.id), actor=super_admin, session=db_session)


async def test_delete_grade_as_admin_deletes_when_empty_and_is_idempotent(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    grade = await _seed_grade(db_session, school.id)

    result = await admin.delete_grade_as_admin(str(grade.id), actor=super_admin, session=db_session)
    assert result == {"deleted": True}
    result2 = await admin.delete_grade_as_admin(str(grade.id), actor=super_admin, session=db_session)
    assert result2 == {"deleted": True}


async def test_delete_grade_as_admin_unknown_grade_is_idempotent(db_session):
    super_admin = await _seed_super_admin(db_session)
    result = await admin.delete_grade_as_admin(str(uuid.uuid4()), actor=super_admin, session=db_session)
    assert result == {"deleted": True}
