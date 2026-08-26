from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import NotFoundError

from src.api.deps import get_db_session, require_role
from src.api.schemas.common import ListEnvelope
from src.api.schemas.homework import HomeworkQuestionOut
from src.api.schemas.student_homework import (
    CurrentHomeworkResponse,
    HomeworkLearningContextOut,
    HomeworkQaConfirmationOut,
    HomeworkReference,
    StudentHomeworkOverviewOut,
)
from src.domain.models import (
    Homework,
    HomeworkQuestion,
    Role,
    StudentHomeworkProgress,
    StudentHomeworkStatus,
    User,
)

router = APIRouter(prefix="/api/v1", tags=["homework-student"])


async def _progress_in(session: AsyncSession, homework_id: str, student_id) -> StudentHomeworkProgress:
    result = await session.execute(
        select(StudentHomeworkProgress).where(
            StudentHomeworkProgress.homework_id == homework_id,
            StudentHomeworkProgress.student_id == student_id,
        )
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        raise NotFoundError("This Homework isn't assigned to you.")
    return progress


@router.get("/me/homework/current")
async def get_current_homework(
    user: User = Depends(require_role(Role.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentHomeworkResponse:
    """homework: null when nothing is assigned right now - a real empty state."""
    result = await session.execute(
        select(StudentHomeworkProgress, Homework)
        .join(Homework, Homework.id == StudentHomeworkProgress.homework_id)
        .where(
            StudentHomeworkProgress.student_id == user.id,
            StudentHomeworkProgress.status != StudentHomeworkStatus.COMPLETED,
        )
        .limit(1)
    )
    row = result.first()
    if row is None:
        return CurrentHomeworkResponse(homework=None)
    progress, hw = row
    return CurrentHomeworkResponse(
        homework=StudentHomeworkOverviewOut(
            homework_id=str(hw.id),
            gap_topic=hw.gap_topic,
            total_questions=hw.total_questions,
            qa_completed=progress.qa_completed,
            expired=progress.expired,
        )
    )


@router.get("/me/homework/{homework_id}/context")
async def get_homework_context(
    homework_id: str,
    user: User = Depends(require_role(Role.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
) -> HomeworkLearningContextOut:
    await _progress_in(session, homework_id, user.id)
    result = await session.execute(select(Homework).where(Homework.id == homework_id))
    hw = result.scalar_one_or_none()
    if hw is None:
        raise NotFoundError(f'No Homework with id "{homework_id}".')
    return HomeworkLearningContextOut(
        homework_id=str(hw.id),
        topic_label=hw.gap_topic,
        what_needs_understanding=f"You need more practice with {hw.gap_topic}.",
        references=[HomeworkReference(title="Class notes", subtitle=hw.gap_topic)],
        key_idea_title=hw.gap_topic,
        key_idea_body=f"A quick refresher on {hw.gap_topic}.",
        connection_prompt=f"How does {hw.gap_topic} connect to what you already know?",
    )


@router.get("/me/homework/{homework_id}/questions")
async def get_my_homework_questions(
    homework_id: str,
    user: User = Depends(require_role(Role.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[HomeworkQuestionOut]:
    """The offline-capable Q&A set - the client caches this on-device."""
    await _progress_in(session, homework_id, user.id)
    result = await session.execute(
        select(HomeworkQuestion)
        .where(HomeworkQuestion.homework_id == homework_id)
        .order_by(HomeworkQuestion.order)
    )
    items = [
        HomeworkQuestionOut(
            id=str(q.id),
            homework_id=homework_id,
            order=q.order,
            bloom_level=q.bloom_level,
            dataset_id=str(q.dataset_id),
            text=q.text,
            answer=q.answer,
        )
        for q in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))


@router.post("/me/homework/{homework_id}/confirm-completion")
async def confirm_completion(
    homework_id: str,
    user: User = Depends(require_role(Role.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
) -> HomeworkQaConfirmationOut:
    """The only call that flips qaCompleted - and therefore Retest
    eligibility. Local recall progress never syncs on its own.
    """
    progress = await _progress_in(session, homework_id, user.id)
    progress.qa_completed = True
    progress.confirmed_at = datetime.now(timezone.utc)
    await session.commit()
    return HomeworkQaConfirmationOut(confirmed_at=progress.confirmed_at)
