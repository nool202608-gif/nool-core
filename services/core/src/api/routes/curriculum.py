from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, require_role
from src.api.schemas.common import ListEnvelope
from src.api.schemas.curriculum import ChapterOut, SubjectOut, TopicOut
from src.domain.models import (
    Chapter,
    Role,
    SchoolCurriculum,
    Subject,
    TeacherClassAssignment,
    Topic,
    User,
)

router = APIRouter(prefix="/api/v1", tags=["curriculum"])


@router.get("/subjects")
async def list_subjects(
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SubjectOut]:
    """Filtered to the caller's school's enabled subjects
    (school_curriculum) - if the school has no school_curriculum rows at
    all yet, every subject in the global catalog is returned rather than
    an empty list, since "not configured" shouldn't look identical to
    "explicitly enabled nothing."
    """
    enabled = await session.execute(
        select(SchoolCurriculum.subject_id).where(
            SchoolCurriculum.school_id == user.school_id, SchoolCurriculum.enabled.is_(True)
        )
    )
    enabled_ids = [row[0] for row in enabled.all()]

    has_any_config = await session.execute(
        select(SchoolCurriculum.id).where(SchoolCurriculum.school_id == user.school_id).limit(1)
    )
    if has_any_config.scalar_one_or_none() is None:
        result = await session.execute(select(Subject))
    else:
        result = await session.execute(select(Subject).where(Subject.id.in_(enabled_ids)))

    items = [SubjectOut(id=str(s.id), name=s.name) for s in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.get("/classes/{class_id}/subjects")
async def list_subjects_for_class(
    class_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SubjectOut]:
    """The subjects this teacher is actually assigned to teach in this
    class (TeacherClassAssignment) - narrower than GET /subjects, which
    only scopes to the school. Scopes the Voice Test wizard's Subject
    step once a class has been chosen. An empty result is a legitimate
    outcome, not an error.
    """
    result = await session.execute(
        select(Subject)
        .join(TeacherClassAssignment, TeacherClassAssignment.subject_id == Subject.id)
        .where(
            TeacherClassAssignment.teacher_id == user.id,
            TeacherClassAssignment.class_id == class_id,
        )
        .distinct()
    )
    items = [SubjectOut(id=str(s.id), name=s.name) for s in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.get("/subjects/{subject_id}/chapters")
async def list_chapters(
    subject_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[ChapterOut]:
    result = await session.execute(select(Chapter).where(Chapter.subject_id == subject_id))
    items = [ChapterOut(id=str(c.id), subject_id=subject_id, name=c.name) for c in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.get("/chapters/{chapter_id}/topics")
async def list_topics(
    chapter_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[TopicOut]:
    """Returns items: [] for a chapter with no authored topics yet - a
    real, expected empty state, not an error.
    """
    result = await session.execute(select(Topic).where(Topic.chapter_id == chapter_id))
    items = [TopicOut(id=str(t.id), chapter_id=chapter_id, name=t.name) for t in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))
