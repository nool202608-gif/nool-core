"""School-wide oversight endpoints (GET /school/voice-tests, /homework,
/question-papers, /retest-progress, /improvement, /leaderboard) - real rows
against the dev Postgres via the db_session fixture, same pattern as
test_subscription_limits.py. Two things matter most here: no cross-school
leakage, and pagination actually works.
"""

import uuid

from src.api.routes import school_oversight
from src.domain.models import (
    AssignmentTargetMode,
    Chapter,
    Role,
    School,
    SchoolClass,
    Subject,
    TestStatus,
    User,
    UserStatus,
    VoiceTest,
)


async def _seed_school(db_session) -> School:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_admin(db_session, school_id) -> User:
    admin = User(
        firebase_uid=f"admin-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Admin", role=Role.SCHOOL_ADMIN, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(admin)
    await db_session.flush()
    return admin


async def _seed_class_subject_chapter(db_session, school_id) -> tuple[SchoolClass, Subject, Chapter]:
    school_class = SchoolClass(school_id=school_id, grade=8, section=str(uuid.uuid4())[:1].upper())
    subject = Subject(name=f"Subject-{uuid.uuid4()}")
    db_session.add_all([school_class, subject])
    await db_session.flush()
    chapter = Chapter(subject_id=subject.id, name="Chapter 1")
    db_session.add(chapter)
    await db_session.flush()
    return school_class, subject, chapter


async def _seed_voice_test(db_session, school_class, subject, chapter) -> VoiceTest:
    test = VoiceTest(
        class_id=school_class.id, subject_id=subject.id, chapter_id=chapter.id, topic_id=None,
        duration_minutes=20, completion_window_hours=48,
        target_mode=AssignmentTargetMode.WHOLE_CLASS, status=TestStatus.DRAFT,
    )
    db_session.add(test)
    await db_session.flush()
    return test


async def test_school_voice_tests_has_no_cross_school_leakage(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_admin(db_session, school_a.id)

    class_a, subject_a, chapter_a = await _seed_class_subject_chapter(db_session, school_a.id)
    class_b, subject_b, chapter_b = await _seed_class_subject_chapter(db_session, school_b.id)
    await _seed_voice_test(db_session, class_a, subject_a, chapter_a)
    await _seed_voice_test(db_session, class_b, subject_b, chapter_b)

    result = await school_oversight.list_school_voice_tests(
        class_id=None, teacher_id=None, limit=50, offset=0, user=admin_a, session=db_session
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].subject_name == subject_a.name


async def test_school_voice_tests_pagination(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter = await _seed_class_subject_chapter(db_session, school.id)
    for _ in range(3):
        await _seed_voice_test(db_session, school_class, subject, chapter)

    first_page = await school_oversight.list_school_voice_tests(
        class_id=None, teacher_id=None, limit=2, offset=0, user=admin, session=db_session
    )
    second_page = await school_oversight.list_school_voice_tests(
        class_id=None, teacher_id=None, limit=2, offset=2, user=admin, session=db_session
    )

    assert first_page.total == 3
    assert len(first_page.items) == 2
    assert second_page.total == 3
    assert len(second_page.items) == 1
