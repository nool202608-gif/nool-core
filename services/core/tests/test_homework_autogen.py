"""homework_autogen.auto_generate_homework - the per-student automatic
follow-up Homework fanned out from test_completion.py. Exercised directly
here (rather than only indirectly through test_test_completion.py) so the
no-dataset no-op path is deterministic regardless of what else is seeded
in the shared dev Postgres.
"""

import uuid

from sqlalchemy import select

from src.domain.models import (
    AssignmentTargetMode,
    BloomLevel,
    Chapter,
    Dataset,
    Homework,
    HomeworkQuestion,
    HomeworkStatus,
    HomeworkTargetStudent,
    Role,
    School,
    SchoolClass,
    StudentHomeworkProgress,
    Subject,
    User,
    UserStatus,
    VoiceTest,
)
from src.services import homework_autogen
from src.services.homework_autogen import AUTO_HOMEWORK_QUESTION_COUNT, auto_generate_homework


async def _seed_test(db_session) -> VoiceTest:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    subject = Subject(name=f"Subject-{uuid.uuid4()}")
    db_session.add_all([school, subject])
    await db_session.flush()
    school_class = SchoolClass(school_id=school.id, grade=9, section=str(uuid.uuid4())[:1].upper())
    chapter = Chapter(subject_id=subject.id, name="Photosynthesis")
    db_session.add_all([school_class, chapter])
    await db_session.flush()
    test = VoiceTest(
        class_id=school_class.id, subject_id=subject.id, chapter_id=chapter.id, topic_id=None,
        duration_minutes=20, completion_window_hours=48, target_mode=AssignmentTargetMode.WHOLE_CLASS,
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


async def test_creates_homework_targeted_at_just_this_student_using_the_subjects_dataset(db_session):
    test = await _seed_test(db_session)
    student = await _seed_student(db_session)
    dataset = Dataset(name="Bank", question_count=20, description="", subject_id=test.subject_id)
    db_session.add(dataset)
    await db_session.flush()

    await auto_generate_homework(
        db_session, test=test, student_id=student.id, mastery_percent=60,
        bloom_levels=[BloomLevel.REMEMBER, BloomLevel.APPLY],
    )
    await db_session.flush()

    hw = (await db_session.execute(select(Homework).where(Homework.test_id == test.id))).scalar_one()
    assert hw.status == HomeworkStatus.ASSIGNED
    assert hw.target_mode == AssignmentTargetMode.SPECIFIC_STUDENTS
    assert hw.gap_topic == "Photosynthesis"
    assert hw.gap_mastery_percent == 60
    assert hw.assigned_count == 1

    progress = (
        await db_session.execute(
            select(StudentHomeworkProgress).where(StudentHomeworkProgress.homework_id == hw.id)
        )
    ).scalar_one()
    assert progress.student_id == student.id

    target = (
        await db_session.execute(
            select(HomeworkTargetStudent).where(HomeworkTargetStudent.homework_id == hw.id)
        )
    ).scalar_one()
    assert target.student_id == student.id

    questions = (
        await db_session.execute(select(HomeworkQuestion).where(HomeworkQuestion.homework_id == hw.id))
    ).scalars().all()
    assert len(questions) == AUTO_HOMEWORK_QUESTION_COUNT
    assert all(q.dataset_id == dataset.id for q in questions)


async def test_falls_back_to_any_dataset_when_none_matches_the_subject(db_session):
    test = await _seed_test(db_session)  # no Dataset seeded for this subject
    student = await _seed_student(db_session)
    db_session.add(Dataset(name="Unscoped", question_count=5, description=""))
    await db_session.flush()

    await auto_generate_homework(
        db_session, test=test, student_id=student.id, mastery_percent=40, bloom_levels=[]
    )
    await db_session.flush()

    hw = (await db_session.execute(select(Homework).where(Homework.test_id == test.id))).scalar_one()
    questions = (
        await db_session.execute(select(HomeworkQuestion).where(HomeworkQuestion.homework_id == hw.id))
    ).scalars().all()
    assert len(questions) == AUTO_HOMEWORK_QUESTION_COUNT


async def _no_dataset(*_args, **_kwargs):
    return None


async def test_no_ops_when_no_dataset_exists_anywhere(db_session, monkeypatch):
    test = await _seed_test(db_session)
    student = await _seed_student(db_session)
    monkeypatch.setattr(homework_autogen, "_pick_dataset", _no_dataset)

    await auto_generate_homework(
        db_session, test=test, student_id=student.id, mastery_percent=40, bloom_levels=[]
    )
    await db_session.flush()

    assert (
        await db_session.execute(select(Homework).where(Homework.test_id == test.id))
    ).scalar_one_or_none() is None
