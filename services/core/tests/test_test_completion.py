"""src/services/test_completion.py - the missing "a Voice Test session
just finished" write path (see that module's docstring for why it exists:
before this, VoiceTest never reached RESULTS_READY and StudentTestResult/
StudentPoints were only ever written by test fixtures, never production
code). Real rows against the dev Postgres via db_session, same pattern as
test_reporting.py/test_analytics.py.
"""

import uuid

from sqlalchemy import select

from src.domain.models import (
    AssignmentTargetMode,
    BloomLevel,
    Chapter,
    Role,
    School,
    SchoolClass,
    StudentPoints,
    StudentTestResult,
    StudentTestResultBloomScore,
    Subject,
    TestStatus,
    User,
    UserStatus,
    VoiceTest,
)
from src.services.test_completion import POINTS_PER_ANSWERED_QUESTION, record_test_completion


async def _seed_test(db_session, *, status=TestStatus.SCHEDULED) -> VoiceTest:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    subject = Subject(name=f"Subject-{uuid.uuid4()}")
    db_session.add_all([school, subject])
    await db_session.flush()
    school_class = SchoolClass(school_id=school.id, grade=9, section=str(uuid.uuid4())[:1].upper())
    chapter = Chapter(subject_id=subject.id, name="Chapter 1")
    db_session.add_all([school_class, chapter])
    await db_session.flush()

    test = VoiceTest(
        class_id=school_class.id, subject_id=subject.id, chapter_id=chapter.id, topic_id=None,
        duration_minutes=20, completion_window_hours=48,
        target_mode=AssignmentTargetMode.WHOLE_CLASS, status=status,
    )
    db_session.add(test)
    await db_session.flush()
    return test


async def _seed_student(db_session) -> User:
    student = User(
        firebase_uid=f"student-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Student", role=Role.STUDENT, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(student)
    await db_session.flush()
    return student


async def test_record_test_completion_writes_result_and_advances_status(db_session):
    test = await _seed_test(db_session)
    student = await _seed_student(db_session)

    await record_test_completion(
        db_session, student_id=student.id, test_id=test.id,
        answered=4, total_questions=5, bloom_levels=[BloomLevel.REMEMBER, BloomLevel.APPLY],
    )
    await db_session.flush()

    result = (
        await db_session.execute(
            select(StudentTestResult).where(
                StudentTestResult.test_id == test.id, StudentTestResult.student_id == student.id
            )
        )
    ).scalar_one()
    assert result.mastery_percent == 80

    bloom_scores = (
        await db_session.execute(
            select(StudentTestResultBloomScore).where(
                StudentTestResultBloomScore.student_test_result_id == result.id
            )
        )
    ).scalars().all()
    assert {s.bloom_level for s in bloom_scores} == {BloomLevel.REMEMBER, BloomLevel.APPLY}
    assert all(s.percent == 80 for s in bloom_scores)

    await db_session.refresh(test)
    assert test.status == TestStatus.RESULTS_READY
    assert test.completed_count == 1

    points = (
        await db_session.execute(select(StudentPoints).where(StudentPoints.student_id == student.id))
    ).scalar_one()
    assert points.points == 4 * POINTS_PER_ANSWERED_QUESTION


async def test_record_test_completion_zero_questions_is_zero_percent_not_a_crash(db_session):
    test = await _seed_test(db_session)
    student = await _seed_student(db_session)

    await record_test_completion(
        db_session, student_id=student.id, test_id=test.id,
        answered=0, total_questions=0, bloom_levels=[],
    )
    await db_session.flush()

    result = (
        await db_session.execute(
            select(StudentTestResult).where(
                StudentTestResult.test_id == test.id, StudentTestResult.student_id == student.id
            )
        )
    ).scalar_one()
    assert result.mastery_percent == 0


async def test_record_test_completion_never_regresses_a_terminal_status(db_session):
    test = await _seed_test(db_session, status=TestStatus.RESULTS_READY)
    student = await _seed_student(db_session)

    await record_test_completion(
        db_session, student_id=student.id, test_id=test.id,
        answered=1, total_questions=1, bloom_levels=[BloomLevel.UNDERSTAND],
    )
    await db_session.flush()
    await db_session.refresh(test)
    assert test.status == TestStatus.RESULTS_READY


async def test_record_test_completion_is_idempotent_on_replay(db_session):
    """A client reconnect near the end of the same session shouldn't
    double-count completed_count or points, though the mastery/Bloom
    numbers themselves are refreshed to the latest submission.
    """
    test = await _seed_test(db_session)
    student = await _seed_student(db_session)

    await record_test_completion(
        db_session, student_id=student.id, test_id=test.id,
        answered=2, total_questions=4, bloom_levels=[BloomLevel.REMEMBER],
    )
    await db_session.flush()
    await record_test_completion(
        db_session, student_id=student.id, test_id=test.id,
        answered=4, total_questions=4, bloom_levels=[BloomLevel.REMEMBER],
    )
    await db_session.flush()

    result = (
        await db_session.execute(
            select(StudentTestResult).where(
                StudentTestResult.test_id == test.id, StudentTestResult.student_id == student.id
            )
        )
    ).scalar_one()
    assert result.mastery_percent == 100

    await db_session.refresh(test)
    assert test.completed_count == 1

    points = (
        await db_session.execute(select(StudentPoints).where(StudentPoints.student_id == student.id))
    ).scalar_one()
    assert points.points == 2 * POINTS_PER_ANSWERED_QUESTION


async def test_record_test_completion_accumulates_points_across_different_tests(db_session):
    student = await _seed_student(db_session)
    test_a = await _seed_test(db_session)
    test_b = await _seed_test(db_session)

    await record_test_completion(
        db_session, student_id=student.id, test_id=test_a.id,
        answered=3, total_questions=3, bloom_levels=[BloomLevel.REMEMBER],
    )
    await db_session.flush()
    await record_test_completion(
        db_session, student_id=student.id, test_id=test_b.id,
        answered=2, total_questions=2, bloom_levels=[BloomLevel.REMEMBER],
    )
    await db_session.flush()

    points = (
        await db_session.execute(select(StudentPoints).where(StudentPoints.student_id == student.id))
    ).scalar_one()
    assert points.points == 5 * POINTS_PER_ANSWERED_QUESTION
