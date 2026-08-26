from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import StudentProfile, TeacherClassAssignment


async def student_count(session: AsyncSession, class_id: UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(StudentProfile).where(StudentProfile.class_id == class_id)
    )
    return result.scalar_one()


async def teacher_assigned_class_ids(session: AsyncSession, teacher_id: UUID) -> list[UUID]:
    """Distinct classes this teacher has any assignment row for, regardless
    of subject - the set that scopes GET /classes.
    """
    result = await session.execute(
        select(TeacherClassAssignment.class_id).where(
            TeacherClassAssignment.teacher_id == teacher_id
        ).distinct()
    )
    return [row[0] for row in result.all()]


async def teaches_class_subject(
    session: AsyncSession, teacher_id: UUID, class_id: str, subject_id: str
) -> bool:
    """Whether this teacher is assigned exactly this subject in exactly
    this class - the real authorization check for creating a Test/Homework
    (checking class alone isn't enough: a teacher can teach one subject in
    a class and not another).
    """
    result = await session.execute(
        select(TeacherClassAssignment.id).where(
            TeacherClassAssignment.teacher_id == teacher_id,
            TeacherClassAssignment.class_id == class_id,
            TeacherClassAssignment.subject_id == subject_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def teaches_class(session: AsyncSession, teacher_id: UUID, class_id: str) -> bool:
    """Whether this teacher has any assignment (any subject) in this
    class - used to gate direct class/roster lookups that aren't
    subject-specific (GET /classes/{id}, GET /classes/{id}/students).
    """
    result = await session.execute(
        select(TeacherClassAssignment.id).where(
            TeacherClassAssignment.teacher_id == teacher_id,
            TeacherClassAssignment.class_id == class_id,
        )
    )
    return result.scalar_one_or_none() is not None
