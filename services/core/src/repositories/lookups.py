"""School-scoped "get or 404" lookups shared across route modules - e.g.
retest_progress.py and improvement.py both need "this Homework, but only
if it's in the caller's school," exactly like homework.py's own routes do.
Factored out here rather than imported across route modules directly.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, NotFoundError

from src.domain.models import Homework, SchoolClass, TestStatus, VoiceTest


async def get_class_in_school(session: AsyncSession, class_id: str, school_id: UUID) -> SchoolClass:
    result = await session.execute(
        select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.school_id == school_id)
    )
    school_class = result.scalar_one_or_none()
    if school_class is None:
        raise NotFoundError(f'Class "{class_id}" was not found.')
    return school_class


async def get_test_in_school(session: AsyncSession, test_id: str, school_id: UUID) -> VoiceTest:
    result = await session.execute(
        select(VoiceTest)
        .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
        .where(VoiceTest.id == test_id, SchoolClass.school_id == school_id)
    )
    test = result.scalar_one_or_none()
    if test is None:
        raise NotFoundError(f'No Test with id "{test_id}" in your school.')
    return test


async def get_ready_test_in_school(session: AsyncSession, test_id: str, school_id: UUID) -> VoiceTest:
    test = await get_test_in_school(session, test_id, school_id)
    if test.status != TestStatus.RESULTS_READY:
        raise ConflictError("Test status isn't RESULTS_READY yet.")
    return test


async def get_homework_in_school(session: AsyncSession, homework_id: str, school_id: UUID) -> Homework:
    result = await session.execute(
        select(Homework)
        .join(SchoolClass, SchoolClass.id == Homework.class_id)
        .where(Homework.id == homework_id, SchoolClass.school_id == school_id)
    )
    hw = result.scalar_one_or_none()
    if hw is None:
        raise NotFoundError(f'No Homework with id "{homework_id}" in your school.')
    return hw
