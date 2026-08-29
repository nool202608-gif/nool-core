"""Which subjects a Class (SchoolGrade) teaches - narrower than the
existing school-wide SchoolCurriculum toggle, picked explicitly per Class.
Covers both surfaces (school_admin.py, admin.py), same pattern as
test_grades.py.
"""

import uuid

import pytest
from sqlalchemy import select

from shared.errors import NotFoundError

from src.api.routes import admin, school_admin
from src.api.schemas.school_admin import UpdateGradeSubjectsIn
from src.domain.models import GradeSubject, Role, School, SchoolGrade, Subject, User, UserStatus


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


async def _seed_subject(db_session) -> Subject:
    subject = Subject(name=f"Subject-{uuid.uuid4()}")
    db_session.add(subject)
    await db_session.flush()
    return subject


# --- School Admin surface ---------------------------------------------------


async def test_get_grade_subjects_lists_every_subject_unmarked_when_none_enabled(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    grade = await _seed_grade(db_session, school.id)
    subject = await _seed_subject(db_session)

    result = await school_admin.get_grade_subjects(str(grade.id), user=admin_user, session=db_session)

    row = next(s for s in result.subjects if s.id == str(subject.id))
    assert row.enabled is False


async def test_update_grade_subjects_enables_and_disables(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    grade = await _seed_grade(db_session, school.id)
    subject_a = await _seed_subject(db_session)
    subject_b = await _seed_subject(db_session)

    enabled = await school_admin.update_grade_subjects(
        str(grade.id), UpdateGradeSubjectsIn(subject_ids=[str(subject_a.id)]), user=admin_user, session=db_session
    )
    row_a = next(s for s in enabled.subjects if s.id == str(subject_a.id))
    row_b = next(s for s in enabled.subjects if s.id == str(subject_b.id))
    assert row_a.enabled is True
    assert row_b.enabled is False

    # Swap which one is enabled - confirms the toggle-off path (not just
    # additive) and that no duplicate row gets inserted for subject_a.
    swapped = await school_admin.update_grade_subjects(
        str(grade.id), UpdateGradeSubjectsIn(subject_ids=[str(subject_b.id)]), user=admin_user, session=db_session
    )
    assert next(s for s in swapped.subjects if s.id == str(subject_a.id)).enabled is False
    assert next(s for s in swapped.subjects if s.id == str(subject_b.id)).enabled is True

    rows = await db_session.execute(select(GradeSubject).where(GradeSubject.grade_id == grade.id))
    assert len(rows.scalars().all()) == 2


async def test_grade_subjects_scoped_to_own_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    grade_b = await _seed_grade(db_session, school_b.id)

    with pytest.raises(NotFoundError):
        await school_admin.get_grade_subjects(str(grade_b.id), user=admin_a, session=db_session)


async def test_get_grade_subjects_unknown_grade_404s(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    with pytest.raises(NotFoundError):
        await school_admin.get_grade_subjects(str(uuid.uuid4()), user=admin_user, session=db_session)


# --- Super Admin cross-tenant surface ---------------------------------------


async def test_get_grade_subjects_as_admin_no_school_filter(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    grade = await _seed_grade(db_session, school.id)
    subject = await _seed_subject(db_session)

    result = await admin.get_grade_subjects_as_admin(str(grade.id), _=super_admin, session=db_session)
    assert any(s.id == str(subject.id) and s.enabled is False for s in result.subjects)


async def test_update_grade_subjects_as_admin_round_trips(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    grade = await _seed_grade(db_session, school.id)
    subject = await _seed_subject(db_session)

    result = await admin.update_grade_subjects_as_admin(
        str(grade.id), UpdateGradeSubjectsIn(subject_ids=[str(subject.id)]), actor=super_admin, session=db_session
    )
    assert next(s for s in result.subjects if s.id == str(subject.id)).enabled is True


async def test_get_grade_subjects_as_admin_unknown_grade_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin.get_grade_subjects_as_admin(str(uuid.uuid4()), _=super_admin, session=db_session)
