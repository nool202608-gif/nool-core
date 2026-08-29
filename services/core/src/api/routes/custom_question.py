"""School Admin-authored questions - see CustomQuestion's docstring. The
first question content in this product a human types directly, rather
than DeterministicContentGenerator producing it. Deliberately School
Admin only (not Teacher) for V1 - see requirements.md.
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import NotFoundError, ValidationError

from src.api.deps import get_db_session, require_role
from src.api.schemas.school_admin import BulkImportResultOut, BulkRowResultOut
from src.api.schemas.common import ListEnvelope
from src.api.schemas.custom_question import (
    CreateCustomQuestionIn,
    CustomQuestionCollectionSummaryOut,
    CustomQuestionOut,
    UpdateCustomQuestionIn,
)
from src.domain.models import (
    BloomLevel,
    Chapter,
    CustomQuestion,
    ImportJobType,
    QuestionType,
    Role,
    SchoolClass,
    Subject,
    Topic,
    User,
)
from src.repositories import audit_repository, import_job_repository
from src.services.bulk_import import BulkRowResult, parse_rows

router = APIRouter(prefix="/api/v1/school", tags=["custom-questions"])


def _out(q: CustomQuestion) -> CustomQuestionOut:
    return CustomQuestionOut(
        id=str(q.id), class_id=str(q.class_id) if q.class_id else None, grade=q.grade,
        subject_id=str(q.subject_id),
        chapter_id=str(q.chapter_id), topic_id=str(q.topic_id) if q.topic_id else None,
        bloom_level=q.bloom_level, question_type=q.question_type, text=q.text,
        options=q.options, answer=q.answer, created_by=str(q.created_by), created_at=q.created_at,
        collection_name=q.collection_name,
    )


def _normalize_collection_name(name: str | None) -> str | None:
    stripped = name.strip() if name else None
    return stripped or None


async def _get_own_question(session: AsyncSession, question_id: str, school_id) -> CustomQuestion:
    result = await session.execute(
        select(CustomQuestion).where(CustomQuestion.id == question_id, CustomQuestion.school_id == school_id)
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise NotFoundError(f'No custom question with id "{question_id}".')
    return question


async def _validate_hierarchy(
    session: AsyncSession, *, school_id, class_id: str | None, grade: int | None,
    subject_id: str, chapter_id: str, topic_id: str | None,
) -> None:
    """Every FK/value a human picked from a dropdown, re-checked
    server-side: the class belongs to this school (or, for a grade-level
    question, at least one class in that grade exists at this school), and
    chapter->subject/topic->chapter actually nest the way the payload
    claims - a dropdown built from GET /school/classes + the global
    catalog can't silently drift, but a hand-built API request could.
    """
    if class_id is not None:
        school_class = await session.get(SchoolClass, class_id)
        if school_class is None or str(school_class.school_id) != str(school_id):
            raise NotFoundError(f'No class with id "{class_id}" in your school.')
    else:
        grade_exists = await session.execute(
            select(SchoolClass.id).where(SchoolClass.school_id == school_id, SchoolClass.grade == grade).limit(1)
        )
        if grade_exists.first() is None:
            raise NotFoundError(f'No class in grade {grade} at your school.')

    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise NotFoundError(f'No subject with id "{subject_id}".')

    chapter = await session.get(Chapter, chapter_id)
    if chapter is None or str(chapter.subject_id) != str(subject_id):
        raise NotFoundError(f'No chapter with id "{chapter_id}" under that subject.')

    if topic_id is not None:
        topic = await session.get(Topic, topic_id)
        if topic is None or str(topic.chapter_id) != str(chapter_id):
            raise NotFoundError(f'No topic with id "{topic_id}" under that chapter.')


@router.get("/custom-questions", summary="This school's custom question bank")
async def list_custom_questions(
    # Every multi-word query param needs an explicit camelCase alias -
    # FastAPI's Query() has no CamelModel-style auto-aliasing the way
    # JSON bodies/responses do, so without it the frontend's camelCase
    # query string (e.g. `?classId=`) simply never binds and the
    # parameter silently stays at its default. See school_admin.py's/
    # school_oversight.py's existing class_id params for precedent.
    class_id: str | None = Query(default=None, alias="classId"),
    grade: int | None = Query(default=None, description="Matches grade-level questions only, not any specific class in that grade."),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    chapter_id: str | None = Query(default=None, alias="chapterId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    bloom_level: BloomLevel | None = Query(default=None, alias="bloomLevel"),
    question_type: QuestionType | None = Query(default=None, alias="questionType"),
    collection_name: str | None = Query(default=None, alias="collectionName", description="Exact match on a named set."),
    # A separate boolean flag rather than overloading collection_name=""
    # for "the general bank" - keeps the two cases unambiguous rather
    # than relying on empty-string-vs-omitted query semantics.
    general_bank_only: bool = Query(default=False, alias="generalBankOnly", description="True = only rows with no named set"),
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[CustomQuestionOut]:
    query = select(CustomQuestion).where(CustomQuestion.school_id == user.school_id)
    if class_id:
        query = query.where(CustomQuestion.class_id == class_id)
    if grade is not None:
        query = query.where(CustomQuestion.grade == grade)
    if subject_id:
        query = query.where(CustomQuestion.subject_id == subject_id)
    if chapter_id:
        query = query.where(CustomQuestion.chapter_id == chapter_id)
    if topic_id:
        query = query.where(CustomQuestion.topic_id == topic_id)
    if bloom_level:
        query = query.where(CustomQuestion.bloom_level == bloom_level)
    if question_type:
        query = query.where(CustomQuestion.question_type == question_type)
    if general_bank_only:
        query = query.where(CustomQuestion.collection_name.is_(None))
    elif collection_name:
        query = query.where(CustomQuestion.collection_name == collection_name)

    all_matching = (await session.execute(query.order_by(CustomQuestion.created_at.desc()))).scalars().all()
    page = all_matching[offset : offset + limit]
    return ListEnvelope(items=[_out(q) for q in page], total=len(all_matching))


@router.get("/custom-questions/collections", summary="Distinct named sets this school has used, for a picker")
async def list_custom_question_collections(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> list[str]:
    result = await session.execute(
        select(CustomQuestion.collection_name)
        .where(CustomQuestion.school_id == user.school_id, CustomQuestion.collection_name.is_not(None))
        .distinct()
    )
    return sorted(result.scalars().all())


@router.get(
    "/custom-questions/collections/summary",
    summary="Question counts per named set, plus the general bank - shown as this school's own datasets",
)
async def summarize_custom_question_collections(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> list[CustomQuestionCollectionSummaryOut]:
    result = await session.execute(
        select(CustomQuestion.collection_name, func.count())
        .where(CustomQuestion.school_id == user.school_id)
        .group_by(CustomQuestion.collection_name)
    )
    rows = [
        CustomQuestionCollectionSummaryOut(collection_name=name, question_count=count)
        for name, count in result.all()
    ]
    # General bank (collection_name=None) sorts first, named sets
    # alphabetically after - matches the picker's own convention elsewhere.
    rows.sort(key=lambda r: (r.collection_name is not None, r.collection_name or ""))
    return rows


@router.get("/custom-questions/{question_id}")
async def get_custom_question(
    question_id: str,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> CustomQuestionOut:
    return _out(await _get_own_question(session, question_id, user.school_id))


@router.post("/custom-questions", status_code=201)
async def create_custom_question(
    body: CreateCustomQuestionIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> CustomQuestionOut:
    await _validate_hierarchy(
        session, school_id=user.school_id, class_id=body.class_id, grade=body.grade, subject_id=body.subject_id,
        chapter_id=body.chapter_id, topic_id=body.topic_id,
    )
    question = CustomQuestion(
        school_id=user.school_id, class_id=body.class_id, grade=body.grade, subject_id=body.subject_id,
        chapter_id=body.chapter_id, topic_id=body.topic_id, bloom_level=body.bloom_level,
        question_type=body.question_type, text=body.text, options=body.options, answer=body.answer,
        created_by=user.id, collection_name=_normalize_collection_name(body.collection_name),
    )
    session.add(question)
    await session.flush()
    await audit_repository.record(
        session, actor_id=user.id, action="custom_question.created",
        target_type="custom_question", target_id=str(question.id),
    )
    await session.commit()
    await session.refresh(question)
    return _out(question)


@router.patch("/custom-questions/{question_id}")
async def update_custom_question(
    question_id: str,
    body: UpdateCustomQuestionIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> CustomQuestionOut:
    question = await _get_own_question(session, question_id, user.school_id)

    # Switching to class_id clears grade and vice versa - the schema's
    # validator already rejects setting both at once. Neither set keeps
    # whichever of the two the question already had.
    if body.class_id is not None:
        class_id, grade = body.class_id, None
    elif body.grade is not None:
        class_id, grade = None, body.grade
    else:
        class_id, grade = (str(question.class_id) if question.class_id else None), question.grade

    subject_id = body.subject_id or str(question.subject_id)
    chapter_id = body.chapter_id or str(question.chapter_id)
    topic_id = body.topic_id if "topic_id" in body.model_fields_set else (
        str(question.topic_id) if question.topic_id else None
    )
    if (
        body.class_id is not None or body.grade is not None or body.subject_id or body.chapter_id
        or "topic_id" in body.model_fields_set
    ):
        await _validate_hierarchy(
            session, school_id=user.school_id, class_id=class_id, grade=grade, subject_id=subject_id,
            chapter_id=chapter_id, topic_id=topic_id,
        )

    question_type = body.question_type or question.question_type
    options = body.options if "options" in body.model_fields_set else question.options
    answer = body.answer or question.answer
    if question_type in (QuestionType.MCQ, QuestionType.TRUE_FALSE):
        if not options or len(options) < 2:
            raise ValidationError(f"{question_type.value} questions need at least 2 options.")
        if answer not in options:
            raise ValidationError("answer must exactly match one of the given options.")
    elif options is not None:
        raise ValidationError(f"{question_type.value} questions don't take options - leave it blank.")

    question.class_id = class_id
    question.grade = grade
    question.subject_id = subject_id
    question.chapter_id = chapter_id
    question.topic_id = topic_id
    question.bloom_level = body.bloom_level or question.bloom_level
    question.question_type = question_type
    question.text = body.text or question.text
    question.options = options
    question.answer = answer
    if "collection_name" in body.model_fields_set:
        question.collection_name = _normalize_collection_name(body.collection_name)

    await audit_repository.record(
        session, actor_id=user.id, action="custom_question.updated",
        target_type="custom_question", target_id=question_id,
    )
    await session.commit()
    await session.refresh(question)
    return _out(question)


@router.delete("/custom-questions/{question_id}")
async def delete_custom_question(
    question_id: str,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    question = await _get_own_question(session, question_id, user.school_id)
    await session.delete(question)
    await audit_repository.record(
        session, actor_id=user.id, action="custom_question.deleted",
        target_type="custom_question", target_id=question_id,
    )
    await session.commit()
    return {"deleted": True}


@router.post("/custom-questions/bulk-import", summary="Bulk-create custom questions from a .csv or .xlsx file")
async def bulk_import_custom_questions(
    file: UploadFile = File(...),
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> BulkImportResultOut:
    """Columns (header row, any order): grade, section (optional - blank
    means the question applies to every section in that grade), subject,
    chapter, topic (optional), bloomLevel, questionType, text, options
    (optional - pipe-separated, e.g. "Paris|London|Berlin|Rome", only for
    MCQ/TRUE_FALSE), answer, collection (optional - a set name; blank
    means the school's general question bank). grade/section/subject/
    chapter/topic are resolved by name within this school - a human
    filling a spreadsheet won't know internal UUIDs, same reasoning as
    bulk_create_students's classGrade/classSection columns.
    """
    content = await file.read()
    rows = parse_rows(file.filename or "upload", content)

    classes_result = await session.execute(select(SchoolClass).where(SchoolClass.school_id == user.school_id))
    classes = classes_result.scalars().all()
    classes_by_key = {(c.grade, c.section.strip().lower()): c for c in classes}
    grades_present = {c.grade for c in classes}

    subjects_result = await session.execute(select(Subject))
    subjects_by_name = {s.name.strip().lower(): s for s in subjects_result.scalars().all()}

    results: list[BulkRowResult] = []
    for index, row in enumerate(rows, start=2):
        grade_raw = row.get("grade", "")
        section = row.get("section", "").strip().lower()
        subject_name = row.get("subject", "").strip().lower()
        chapter_name = row.get("chapter", "").strip().lower()
        topic_name = row.get("topic", "").strip().lower() or None
        bloom_raw = row.get("bloomlevel", "").strip().upper()
        type_raw = row.get("questiontype", "").strip().upper()
        text = row.get("text", "")
        options_raw = row.get("options", "").strip()
        answer = row.get("answer", "")
        collection_name = _normalize_collection_name(row.get("collection", ""))

        if not all([grade_raw, subject_name, chapter_name, bloom_raw, type_raw, text, answer]):
            results.append(
                BulkRowResult(
                    row=index, status="error",
                    error="grade, subject, chapter, bloomLevel, questionType, text, and answer are required.",
                )
            )
            continue

        try:
            row_grade = int(grade_raw)
        except ValueError:
            results.append(BulkRowResult(row=index, status="error", error="grade must be a number."))
            continue

        # Blank section = every section in that grade (see this route's
        # docstring) - CustomQuestion.grade is set instead of class_id.
        school_class = None
        if section:
            school_class = classes_by_key.get((row_grade, section))
            if school_class is None:
                results.append(BulkRowResult(row=index, status="error", error=f"No class {grade_raw}-{section} in your school."))
                continue
        elif row_grade not in grades_present:
            results.append(BulkRowResult(row=index, status="error", error=f"No class in grade {grade_raw} in your school."))
            continue

        subject = subjects_by_name.get(subject_name)
        if subject is None:
            results.append(BulkRowResult(row=index, status="error", error=f'No subject named "{row.get("subject")}".'))
            continue

        chapter_result = await session.execute(
            select(Chapter).where(Chapter.subject_id == subject.id)
        )
        chapter = next(
            (c for c in chapter_result.scalars().all() if c.name.strip().lower() == chapter_name), None
        )
        if chapter is None:
            results.append(
                BulkRowResult(row=index, status="error", error=f'No chapter named "{row.get("chapter")}" under {row.get("subject")}.')
            )
            continue

        topic = None
        if topic_name:
            topic_result = await session.execute(select(Topic).where(Topic.chapter_id == chapter.id))
            topic = next((t for t in topic_result.scalars().all() if t.name.strip().lower() == topic_name), None)
            if topic is None:
                results.append(
                    BulkRowResult(row=index, status="error", error=f'No topic named "{row.get("topic")}" under {row.get("chapter")}.')
                )
                continue

        try:
            bloom_level = BloomLevel(bloom_raw)
        except ValueError:
            results.append(BulkRowResult(row=index, status="error", error=f'"{row.get("bloomLevel")}" is not a valid Bloom level.'))
            continue

        try:
            question_type = QuestionType(type_raw)
        except ValueError:
            results.append(BulkRowResult(row=index, status="error", error=f'"{row.get("questionType")}" is not a valid question type.'))
            continue

        options = [o.strip() for o in options_raw.split("|") if o.strip()] if options_raw else None
        if question_type in (QuestionType.MCQ, QuestionType.TRUE_FALSE):
            if not options or len(options) < 2:
                results.append(BulkRowResult(row=index, status="error", error=f"{question_type.value} needs at least 2 options."))
                continue
            if answer not in options:
                results.append(BulkRowResult(row=index, status="error", error="answer must exactly match one of the options."))
                continue
        elif options is not None:
            results.append(BulkRowResult(row=index, status="error", error=f"{question_type.value} questions don't take options."))
            continue

        session.add(
            CustomQuestion(
                school_id=user.school_id,
                class_id=school_class.id if school_class else None,
                grade=row_grade if school_class is None else None,
                subject_id=subject.id,
                chapter_id=chapter.id, topic_id=topic.id if topic else None, bloom_level=bloom_level,
                question_type=question_type, text=text, options=options, answer=answer, created_by=user.id,
                collection_name=collection_name,
            )
        )
        results.append(BulkRowResult(row=index, status="created"))

    created_count = sum(1 for r in results if r.status == "created")
    error_count = sum(1 for r in results if r.status == "error")
    await audit_repository.record(
        session, actor_id=user.id, action="custom_question.bulk_created", target_type="school",
        target_id=str(user.school_id),
        detail=f"{created_count} created, {error_count} failed",
    )
    import_job_repository.record(
        session, school_id=user.school_id, initiated_by=user.id, job_type=ImportJobType.CUSTOM_QUESTION,
        filename=file.filename or "upload", row_count=len(rows),
        created_count=created_count, error_count=error_count,
    )
    await session.commit()
    return BulkImportResultOut(
        results=[BulkRowResultOut(**r.__dict__) for r in results],
        created_count=created_count,
        error_count=error_count,
    )
