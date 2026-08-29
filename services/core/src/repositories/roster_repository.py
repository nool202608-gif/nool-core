from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import (
    SchoolClass,
    SchoolGrade,
    StudentProfile,
    TeacherClassAssignment,
)


async def student_count(session: AsyncSession, class_id: UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(StudentProfile).where(StudentProfile.class_id == class_id)
    )
    return result.scalar_one()


async def section_count(session: AsyncSession, grade_id: UUID) -> int:
    """Number of sections (SchoolClass rows) under one Class (SchoolGrade) -
    used both to render SchoolGradeOut and to block deleting a Class that
    still has sections under it, same shape as student_count's use in
    delete_school_class.
    """
    result = await session.execute(
        select(func.count()).select_from(SchoolClass).where(SchoolClass.grade_id == grade_id)
    )
    return result.scalar_one()


async def grade_student_count(session: AsyncSession, grade_id: UUID) -> int:
    """Total students across every section under one Class - same join
    shape as school_oversight/admin analytics queries that need a
    class-level rollup over StudentProfile via SchoolClass.
    """
    result = await session.execute(
        select(func.count())
        .select_from(StudentProfile)
        .join(SchoolClass, SchoolClass.id == StudentProfile.class_id)
        .where(SchoolClass.grade_id == grade_id)
    )
    return result.scalar_one()


async def get_or_create_grade(session: AsyncSession, school_id: UUID | str, grade: int) -> SchoolGrade:
    """Resolves the Class (SchoolGrade) a new section belongs to, creating
    it transparently on first use so creating a Section never requires a
    separate "create the Class first" step - see school_admin.py's and
    admin.py's create_school_class/create_class_as_admin, the only two
    callers. Every section written by application code therefore always
    has grade_id set; only pre-migration rows were ever backfilled
    directly in SQL (see 6f2f4d9c1a3e_school_grades).
    """
    result = await session.execute(
        select(SchoolGrade).where(SchoolGrade.school_id == school_id, SchoolGrade.grade == grade)
    )
    school_grade = result.scalar_one_or_none()
    if school_grade is not None:
        return school_grade
    school_grade = SchoolGrade(school_id=school_id, grade=grade)
    session.add(school_grade)
    await session.flush()
    return school_grade


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
