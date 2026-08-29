"""Global catalog CRUD (Subjects, Chapters, Topics, Datasets) - Super
Admin only. These are explicitly modeled as a global catalog shared across
every school (no school_id on any of these tables - SchoolCurriculum is
the per-school enable/disable toggle, and that stays School Admin's,
unchanged). Giving School Admin write access here would silently change
these for every other school too.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, NotFoundError, ValidationError

from src.api.deps import get_db_session, require_role
from src.api.schemas.admin_catalog import (
    ChapterOut,
    CreateChapterIn,
    CreateDatasetIn,
    CreateDatasetQuestionIn,
    CreateSubjectIn,
    CreateTopicIn,
    DatasetOut,
    DatasetQuestionOut,
    SubjectOut,
    TopicOut,
    UpdateChapterIn,
    UpdateDatasetIn,
    UpdateDatasetQuestionIn,
    UpdateSubjectIn,
    UpdateTopicIn,
)
from src.api.schemas.common import ListEnvelope
from src.domain.models import Chapter, Dataset, DatasetQuestion, QuestionType, Role, Subject, Topic, User
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


async def _subject_name_taken(session: AsyncSession, name: str, *, exclude_subject_id: str | None = None) -> bool:
    query = select(Subject.id).where(Subject.name == name)
    if exclude_subject_id is not None:
        query = query.where(Subject.id != exclude_subject_id)
    result = await session.execute(query)
    return result.first() is not None


@router.post("/subjects", status_code=201)
async def create_subject(
    body: CreateSubjectIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SubjectOut:
    if await _subject_name_taken(session, body.name):
        raise ConflictError(f'A subject named "{body.name}" already exists.')

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
    if await _subject_name_taken(session, body.name, exclude_subject_id=subject_id):
        raise ConflictError(f'A subject named "{body.name}" already exists.')
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

async def _real_question_count(session: AsyncSession, dataset_id) -> int:
    result = await session.execute(
        select(func.count()).select_from(DatasetQuestion).where(DatasetQuestion.dataset_id == dataset_id)
    )
    return result.scalar_one()


async def _dataset_out(session: AsyncSession, dataset: Dataset) -> DatasetOut:
    real_count = await _real_question_count(session, dataset.id)
    return DatasetOut(
        id=str(dataset.id), name=dataset.name,
        question_count=real_count if real_count > 0 else dataset.question_count,
        description=dataset.description,
        subject_id=str(dataset.subject_id) if dataset.subject_id else None,
    )


@router.get("/datasets")
async def list_datasets(
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[DatasetOut]:
    result = await session.execute(select(Dataset))
    items = [await _dataset_out(session, d) for d in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.post("/datasets", status_code=201)
async def create_dataset(
    body: CreateDatasetIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetOut:
    dataset = Dataset(
        name=body.name, question_count=body.question_count, description=body.description,
        subject_id=body.subject_id,
    )
    session.add(dataset)
    await session.flush()
    await audit_repository.record(
        session, actor_id=actor.id, action="dataset.created", target_type="dataset", target_id=str(dataset.id)
    )
    await session.commit()
    await session.refresh(dataset)
    return await _dataset_out(session, dataset)


async def _get_dataset(session: AsyncSession, dataset_id: str) -> Dataset:
    result = await session.execute(select(Dataset).where(Dataset.id == dataset_id))
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise NotFoundError(f'No dataset with id "{dataset_id}".')
    return dataset


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetOut:
    dataset = await _get_dataset(session, dataset_id)
    return await _dataset_out(session, dataset)


@router.patch("/datasets/{dataset_id}")
async def update_dataset(
    dataset_id: str,
    body: UpdateDatasetIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetOut:
    dataset = await _get_dataset(session, dataset_id)
    if body.name is not None:
        dataset.name = body.name
    if body.question_count is not None:
        dataset.question_count = body.question_count
    if body.description is not None:
        dataset.description = body.description
    if "subject_id" in body.model_fields_set:
        dataset.subject_id = body.subject_id
    await audit_repository.record(
        session, actor_id=actor.id, action="dataset.updated", target_type="dataset", target_id=dataset_id
    )
    await session.commit()
    return await _dataset_out(session, dataset)


# ---- Dataset Questions (the real content behind question_count) -----------

def _dataset_question_out(q: DatasetQuestion) -> DatasetQuestionOut:
    return DatasetQuestionOut(
        id=str(q.id), dataset_id=str(q.dataset_id),
        chapter_id=str(q.chapter_id) if q.chapter_id else None,
        topic_id=str(q.topic_id) if q.topic_id else None,
        bloom_level=q.bloom_level, question_type=q.question_type, text=q.text,
        options=q.options, answer=q.answer, created_by=str(q.created_by), created_at=q.created_at,
    )


@router.get("/datasets/{dataset_id}/questions")
async def list_dataset_questions(
    dataset_id: str,
    _: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[DatasetQuestionOut]:
    await _get_dataset(session, dataset_id)
    result = await session.execute(
        select(DatasetQuestion).where(DatasetQuestion.dataset_id == dataset_id).order_by(
            DatasetQuestion.created_at.desc()
        )
    )
    items = [_dataset_question_out(q) for q in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.post("/datasets/{dataset_id}/questions", status_code=201)
async def create_dataset_question(
    dataset_id: str,
    body: CreateDatasetQuestionIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetQuestionOut:
    await _get_dataset(session, dataset_id)
    question = DatasetQuestion(
        dataset_id=dataset_id, chapter_id=body.chapter_id, topic_id=body.topic_id,
        bloom_level=body.bloom_level, question_type=body.question_type, text=body.text,
        options=body.options, answer=body.answer, created_by=actor.id,
    )
    session.add(question)
    await session.flush()
    await audit_repository.record(
        session, actor_id=actor.id, action="dataset.question.created",
        target_type="dataset_question", target_id=str(question.id), detail=f"Dataset {dataset_id}",
    )
    await session.commit()
    await session.refresh(question)
    return _dataset_question_out(question)


async def _get_dataset_question(session: AsyncSession, dataset_id: str, question_id: str) -> DatasetQuestion:
    result = await session.execute(
        select(DatasetQuestion).where(
            DatasetQuestion.id == question_id, DatasetQuestion.dataset_id == dataset_id
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise NotFoundError(f'No question with id "{question_id}" in this dataset.')
    return question


@router.patch("/datasets/{dataset_id}/questions/{question_id}")
async def update_dataset_question(
    dataset_id: str,
    question_id: str,
    body: UpdateDatasetQuestionIn,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetQuestionOut:
    question = await _get_dataset_question(session, dataset_id, question_id)

    if "chapter_id" in body.model_fields_set:
        question.chapter_id = body.chapter_id
    if "topic_id" in body.model_fields_set:
        question.topic_id = body.topic_id
    if body.bloom_level is not None:
        question.bloom_level = body.bloom_level

    question_type = body.question_type or question.question_type
    options = body.options if "options" in body.model_fields_set else question.options
    answer = body.answer or question.answer
    # Inline, not the shared _check_dataset_question_options helper - that
    # one's written to raise plain ValueError for Pydantic's
    # @model_validator to catch (see CreateDatasetQuestionIn), but route
    # code needs shared.errors.ValidationError instead so FastAPI's own
    # error-envelope handler produces the right 422 - same split
    # custom_question.py's update_custom_question already uses.
    if question_type in (QuestionType.MCQ, QuestionType.TRUE_FALSE):
        if not options or len(options) < 2:
            raise ValidationError(f"{question_type.value} questions need at least 2 options.")
        if answer not in options:
            raise ValidationError("answer must exactly match one of the given options.")
    elif options is not None:
        raise ValidationError(f"{question_type.value} questions don't take options - leave it blank.")
    question.question_type = question_type
    question.options = options
    question.answer = answer
    if body.text is not None:
        question.text = body.text

    await audit_repository.record(
        session, actor_id=actor.id, action="dataset.question.updated",
        target_type="dataset_question", target_id=question_id,
    )
    await session.commit()
    return _dataset_question_out(question)


@router.delete("/datasets/{dataset_id}/questions/{question_id}")
async def delete_dataset_question(
    dataset_id: str,
    question_id: str,
    actor: User = Depends(require_role(Role.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    result = await session.execute(
        select(DatasetQuestion).where(
            DatasetQuestion.id == question_id, DatasetQuestion.dataset_id == dataset_id
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        return {"deleted": True}
    await session.delete(question)
    await audit_repository.record(
        session, actor_id=actor.id, action="dataset.question.deleted",
        target_type="dataset_question", target_id=question_id,
    )
    await session.commit()
    return {"deleted": True}
