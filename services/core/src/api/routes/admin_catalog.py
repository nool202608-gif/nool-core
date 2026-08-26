"""Global catalog CRUD (Subjects, Chapters, Topics, Datasets) - Super
Admin only. These are explicitly modeled as a global catalog shared across
every school (no school_id on any of these tables - SchoolCurriculum is
the per-school enable/disable toggle, and that stays School Admin's,
unchanged). Giving School Admin write access here would silently change
these for every other school too.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import NotFoundError

from src.api.deps import get_db_session, require_role
from src.api.schemas.admin_catalog import (
    ChapterOut,
    CreateChapterIn,
    CreateDatasetIn,
    CreateSubjectIn,
    CreateTopicIn,
    DatasetOut,
    SubjectOut,
    TopicOut,
    UpdateChapterIn,
    UpdateDatasetIn,
    UpdateSubjectIn,
    UpdateTopicIn,
)
from src.api.schemas.common import ListEnvelope
from src.domain.models import Chapter, Dataset, Role, Subject, Topic, User
from src.repositories import audit_repository

router = APIRouter(prefix="/api/v1/admin", tags=["admin-catalog"])


# ---- Subjects ---------------------------------------------------------

@router.get("/subjects")
async def list_subjects(
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SubjectOut]:
    result = await session.execute(select(Subject))
    items = [SubjectOut(id=str(s.id), name=s.name) for s in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.post("/subjects", status_code=201)
async def create_subject(
    body: CreateSubjectIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SubjectOut:
    subject = Subject(name=body.name)
    session.add(subject)
    await session.flush()
    await audit_repository.record(
        session, actor_id=actor.id, action="subject.created", target_type="subject", target_id=str(subject.id)
    )
    await session.commit()
    await session.refresh(subject)
    return SubjectOut(id=str(subject.id), name=subject.name)


@router.patch("/subjects/{subject_id}")
async def update_subject(
    subject_id: str,
    body: UpdateSubjectIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SubjectOut:
    result = await session.execute(select(Subject).where(Subject.id == subject_id))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise NotFoundError(f'No subject with id "{subject_id}".')
    subject.name = body.name
    await audit_repository.record(
        session, actor_id=actor.id, action="subject.updated", target_type="subject", target_id=subject_id
    )
    await session.commit()
    return SubjectOut(id=str(subject.id), name=subject.name)


@router.delete("/subjects/{subject_id}")
async def delete_subject(
    subject_id: str,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    result = await session.execute(select(Subject).where(Subject.id == subject_id))
    subject = result.scalar_one_or_none()
    if subject is not None:
        await session.delete(subject)
        await audit_repository.record(
            session, actor_id=actor.id, action="subject.deleted", target_type="subject", target_id=subject_id
        )
        await session.commit()
    return {"deleted": True}


# ---- Chapters -----------------------------------------------------------

@router.get("/subjects/{subject_id}/chapters")
async def list_chapters(
    subject_id: str,
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[ChapterOut]:
    result = await session.execute(select(Chapter).where(Chapter.subject_id == subject_id))
    items = [ChapterOut(id=str(c.id), subject_id=subject_id, name=c.name) for c in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.post("/subjects/{subject_id}/chapters", status_code=201)
async def create_chapter(
    subject_id: str,
    body: CreateChapterIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ChapterOut:
    chapter = Chapter(subject_id=subject_id, name=body.name)
    session.add(chapter)
    await session.flush()
    await audit_repository.record(
        session, actor_id=actor.id, action="chapter.created", target_type="chapter", target_id=str(chapter.id)
    )
    await session.commit()
    await session.refresh(chapter)
    return ChapterOut(id=str(chapter.id), subject_id=subject_id, name=chapter.name)


@router.patch("/chapters/{chapter_id}")
async def update_chapter(
    chapter_id: str,
    body: UpdateChapterIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ChapterOut:
    result = await session.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if chapter is None:
        raise NotFoundError(f'No chapter with id "{chapter_id}".')
    chapter.name = body.name
    await audit_repository.record(
        session, actor_id=actor.id, action="chapter.updated", target_type="chapter", target_id=chapter_id
    )
    await session.commit()
    return ChapterOut(id=str(chapter.id), subject_id=str(chapter.subject_id), name=chapter.name)


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(
    chapter_id: str,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    result = await session.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if chapter is not None:
        await session.delete(chapter)
        await audit_repository.record(
            session, actor_id=actor.id, action="chapter.deleted", target_type="chapter", target_id=chapter_id
        )
        await session.commit()
    return {"deleted": True}


# ---- Topics -------------------------------------------------------------

@router.get("/chapters/{chapter_id}/topics")
async def list_topics(
    chapter_id: str,
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[TopicOut]:
    result = await session.execute(select(Topic).where(Topic.chapter_id == chapter_id))
    items = [TopicOut(id=str(t.id), chapter_id=chapter_id, name=t.name) for t in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.post("/chapters/{chapter_id}/topics", status_code=201)
async def create_topic(
    chapter_id: str,
    body: CreateTopicIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> TopicOut:
    topic = Topic(chapter_id=chapter_id, name=body.name)
    session.add(topic)
    await session.flush()
    await audit_repository.record(
        session, actor_id=actor.id, action="topic.created", target_type="topic", target_id=str(topic.id)
    )
    await session.commit()
    await session.refresh(topic)
    return TopicOut(id=str(topic.id), chapter_id=chapter_id, name=topic.name)


@router.patch("/topics/{topic_id}")
async def update_topic(
    topic_id: str,
    body: UpdateTopicIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> TopicOut:
    result = await session.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if topic is None:
        raise NotFoundError(f'No topic with id "{topic_id}".')
    topic.name = body.name
    await audit_repository.record(
        session, actor_id=actor.id, action="topic.updated", target_type="topic", target_id=topic_id
    )
    await session.commit()
    return TopicOut(id=str(topic.id), chapter_id=str(topic.chapter_id), name=topic.name)


@router.delete("/topics/{topic_id}")
async def delete_topic(
    topic_id: str,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    result = await session.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if topic is not None:
        await session.delete(topic)
        await audit_repository.record(
            session, actor_id=actor.id, action="topic.deleted", target_type="topic", target_id=topic_id
        )
        await session.commit()
    return {"deleted": True}


# ---- Datasets -------------------------------------------------------------

@router.get("/datasets")
async def list_datasets(
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[DatasetOut]:
    result = await session.execute(select(Dataset))
    items = [
        DatasetOut(id=str(d.id), name=d.name, question_count=d.question_count, description=d.description)
        for d in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))


@router.post("/datasets", status_code=201)
async def create_dataset(
    body: CreateDatasetIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetOut:
    dataset = Dataset(name=body.name, question_count=body.question_count, description=body.description)
    session.add(dataset)
    await session.flush()
    await audit_repository.record(
        session, actor_id=actor.id, action="dataset.created", target_type="dataset", target_id=str(dataset.id)
    )
    await session.commit()
    await session.refresh(dataset)
    return DatasetOut(id=str(dataset.id), name=dataset.name, question_count=dataset.question_count, description=dataset.description)


@router.patch("/datasets/{dataset_id}")
async def update_dataset(
    dataset_id: str,
    body: UpdateDatasetIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetOut:
    result = await session.execute(select(Dataset).where(Dataset.id == dataset_id))
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise NotFoundError(f'No dataset with id "{dataset_id}".')
    if body.name is not None:
        dataset.name = body.name
    if body.question_count is not None:
        dataset.question_count = body.question_count
    if body.description is not None:
        dataset.description = body.description
    await audit_repository.record(
        session, actor_id=actor.id, action="dataset.updated", target_type="dataset", target_id=dataset_id
    )
    await session.commit()
    return DatasetOut(id=str(dataset.id), name=dataset.name, question_count=dataset.question_count, description=dataset.description)
