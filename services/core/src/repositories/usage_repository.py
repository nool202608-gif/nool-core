from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import QuestionPaper, Role, SchoolClass, StudentProfile, User, VoiceTest


async def count_teachers(session: AsyncSession, school_id: UUID) -> int:
    result = await session.execute(
        select(User).where(User.school_id == school_id, User.role == Role.TEACHER)
    )
    return len(result.scalars().all())


async def count_students(session: AsyncSession, school_id: UUID) -> int:
    result = await session.execute(
        select(User)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(SchoolClass, SchoolClass.id == StudentProfile.class_id)
        .where(SchoolClass.school_id == school_id)
    )
    return len(result.scalars().all())


async def count_tests(session: AsyncSession, school_id: UUID) -> int:
    result = await session.execute(
        select(VoiceTest).join(SchoolClass, SchoolClass.id == VoiceTest.class_id).where(
            SchoolClass.school_id == school_id
        )
    )
    return len(result.scalars().all())


async def count_question_papers(session: AsyncSession, school_id: UUID) -> int:
    result = await session.execute(select(QuestionPaper).where(QuestionPaper.school_id == school_id))
    return len(result.scalars().all())
