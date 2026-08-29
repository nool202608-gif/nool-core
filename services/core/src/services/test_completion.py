"""Writes the real outcome of a completed AI Assessor session tied to a
VoiceTest - the missing link flagged in NEXT_STEP.md: before this, nothing
in the codebase ever transitioned a VoiceTest to COMPLETED/RESULTS_READY or
wrote StudentTestResult/StudentTestResultBloomScore/StudentPoints, so
school_analytics.py's mastery/Bloom/trend numbers and the leaderboard read
as if no test had ever happened, and homework.py's `test.status ==
RESULTS_READY` gate made "generate follow-up Homework from test gaps"
unreachable in production - only ever exercised via hand-seeded test
fixtures.

`mastery_percent` is a completion-rate placeholder (percent of questions
answered), the same deterministic, honesty-first formula
student_retest.py's process_retest_result already uses for retest_percent
- not a real correctness grade, since no LLM/grading vendor exists yet
(see content_generator.py's docstring). Points awarded follow the same
principle: 10 points per question actually answered, a real participation
signal rather than a synthesized "score."

VoiceTest.status moves straight to RESULTS_READY, collapsing the
COMPLETED/RESULTS_PROCESSING steps the model's docstring describes as
"never collapsed" - defensible only because there is currently no real
async grading step to occupy that gap; revisit once real grading needs
one. `completed_count` increments once per distinct student (idempotent on
replay, e.g. a client reconnect near the end of the same session) - a
correction to a UI-visible number that was silently stuck at 0 for every
Voice Test ever created, matching `assigned_count`'s separately-tracked
issue (never populated at test-creation time - out of scope here, since
fixing it means resolving WHOLE_CLASS/SPECIFIC_STUDENTS target membership
into a real count, a distinct piece of work).
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import (
    BloomLevel,
    StudentPoints,
    StudentTestResult,
    StudentTestResultBloomScore,
    TestStatus,
    VoiceTest,
)

POINTS_PER_ANSWERED_QUESTION = 10


async def record_test_completion(
    session: AsyncSession,
    *,
    student_id: uuid.UUID,
    test_id: uuid.UUID,
    answered: int,
    total_questions: int,
    bloom_levels: list[BloomLevel],
) -> None:
    mastery_percent = round(100 * answered / total_questions) if total_questions else 0

    existing = await session.execute(
        select(StudentTestResult).where(
            StudentTestResult.test_id == test_id, StudentTestResult.student_id == student_id
        )
    )
    result_row = existing.scalar_one_or_none()
    already_completed = result_row is not None
    if result_row is None:
        result_row = StudentTestResult(test_id=test_id, student_id=student_id, mastery_percent=mastery_percent)
        session.add(result_row)
    else:
        result_row.mastery_percent = mastery_percent
    await session.flush()

    await session.execute(
        delete(StudentTestResultBloomScore).where(
            StudentTestResultBloomScore.student_test_result_id == result_row.id
        )
    )
    for level in bloom_levels or [BloomLevel.UNDERSTAND]:
        session.add(
            StudentTestResultBloomScore(
                student_test_result_id=result_row.id, bloom_level=level, percent=mastery_percent
            )
        )

    test = await session.get(VoiceTest, test_id)
    if test is not None:
        if not already_completed:
            test.completed_count += 1
        if test.status in (TestStatus.DRAFT, TestStatus.SCHEDULED, TestStatus.ACTIVE):
            test.status = TestStatus.RESULTS_READY

    if not already_completed:
        points_row = await session.get(StudentPoints, student_id)
        awarded = answered * POINTS_PER_ANSWERED_QUESTION
        if points_row is None:
            session.add(StudentPoints(student_id=student_id, points=awarded))
        else:
            points_row.points += awarded
