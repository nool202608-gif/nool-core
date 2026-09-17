"""Auto-generates and immediately assigns a personal Homework the moment a
student's own Test/Co-learner session completes - see test_completion.py's
call site.

PRODUCT.md's original Homework flow ("Test complete -> results -> teacher
generates -> reviews -> assigns") was teacher-gated end to end: a teacher
had to notice a completed Test and manually run generate/review/assign
before any student ever saw Homework. Per product direction, that gate is
removed for the student's own follow-up - the completing student's AI
Learner session *is* their learning path, and Homework is the automatic
next step on it, targeted at just that student (SPECIFIC_STUDENTS, one
name). A teacher's manual whole-class flow (POST /homework, /generate,
/assign - homework.py) still exists unchanged for anything beyond this
per-student follow-up (e.g. assigning the same intervention to a whole
class after reviewing results).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import (
    AssignmentTargetMode,
    BloomLevel,
    Chapter,
    Dataset,
    Homework,
    HomeworkDifficulty,
    HomeworkQuestion,
    HomeworkStatus,
    HomeworkTargetStudent,
    StudentHomeworkProgress,
    VoiceTest,
)
from src.services import homework_content_resolver

AUTO_HOMEWORK_QUESTION_COUNT = 5
AUTO_HOMEWORK_COMPLETION_WINDOW_HOURS = 48


async def auto_generate_homework(
    session: AsyncSession,
    *,
    test: VoiceTest,
    student_id: uuid.UUID,
    mastery_percent: int,
    bloom_levels: list[BloomLevel],
) -> None:
    """No-ops (rather than raising) when there is no Dataset to ground
    questions in - HomeworkQuestion.dataset_id is NOT NULL, the same
    requirement the manual teacher flow has, just with no teacher present
    to pick one. Caller (test_completion.py) only invokes this once per
    (test, student) - guarded by the same `already_completed` check that
    gates the points award, so a WS reconnect replay never double-creates.
    """
    dataset_id = await _pick_dataset(session, test.subject_id)
    if dataset_id is None:
        return

    chapter = await session.get(Chapter, test.chapter_id)
    gap_topic = chapter.name if chapter is not None else "this chapter"

    hw = Homework(
        test_id=test.id,
        class_id=test.class_id,
        gap_topic=gap_topic,
        gap_mastery_percent=mastery_percent,
        total_questions=AUTO_HOMEWORK_QUESTION_COUNT,
        difficulty=HomeworkDifficulty.MIXED,
        target_mode=AssignmentTargetMode.SPECIFIC_STUDENTS,
        completion_window_hours=AUTO_HOMEWORK_COMPLETION_WINDOW_HOURS,
        status=HomeworkStatus.ASSIGNED,
        assigned_count=1,
    )
    session.add(hw)
    await session.flush()

    session.add(HomeworkTargetStudent(homework_id=hw.id, student_id=student_id))
    session.add(StudentHomeworkProgress(homework_id=hw.id, student_id=student_id))

    questions = await homework_content_resolver.generate_questions(
        session,
        chapter_id=test.chapter_id,
        subject_id=test.subject_id,
        class_id=test.class_id,
        topic_id=test.topic_id,
        topic=gap_topic,
        bloom_distribution=_even_bloom_distribution(bloom_levels, AUTO_HOMEWORK_QUESTION_COUNT),
        count=AUTO_HOMEWORK_QUESTION_COUNT,
    )
    for order, q in enumerate(questions, start=1):
        session.add(
            HomeworkQuestion(
                homework_id=hw.id,
                order=order,
                bloom_level=q.bloom_level,
                dataset_id=dataset_id,
                text=q.text,
                answer=q.answer,
            )
        )


def _even_bloom_distribution(levels: list[BloomLevel], count: int) -> dict[BloomLevel, int]:
    """Spreads `count` questions as evenly as possible across the assessed
    Bloom levels, for the KG grounding call's `bloom_distribution` -
    this auto-generated flow only has a flat list of assessed levels
    (unlike the teacher-driven flow, which has a real per-level count from
    HomeworkBloomDistribution), so there's no real weighting to preserve.
    """
    if not levels:
        return {BloomLevel.UNDERSTAND: count}
    base, remainder = divmod(count, len(levels))
    return {level: base + (1 if i < remainder else 0) for i, level in enumerate(levels)}


async def _pick_dataset(session: AsyncSession, subject_id: uuid.UUID) -> uuid.UUID | None:
    subject_match = await session.execute(select(Dataset.id).where(Dataset.subject_id == subject_id).limit(1))
    dataset_id = subject_match.scalar_one_or_none()
    if dataset_id is not None:
        return dataset_id
    # No dataset scoped to this subject (e.g. a smoke-test subject with no
    # real question bank yet) - fall back to any dataset in the catalog
    # rather than leaving the student with no follow-up at all.
    any_dataset = await session.execute(select(Dataset.id).limit(1))
    return any_dataset.scalar_one_or_none()
