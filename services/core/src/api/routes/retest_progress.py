from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, require_role
from src.api.schemas.retest_progress import RetestProgressOut, StudentRetestOut
from src.domain.models import Homework, Role, RetestAttempt, StudentRetestStatus, User
from src.repositories.lookups import get_homework_in_school

router = APIRouter(prefix="/api/v1", tags=["retest-progress"])


@router.get("/homework/{homework_id}/retest-progress")
async def get_retest_progress(
    homework_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> RetestProgressOut:
    hw: Homework = await get_homework_in_school(session, homework_id, user.school_id)
    result = await session.execute(
        select(RetestAttempt).where(RetestAttempt.homework_id == hw.id)
    )
    attempts = result.scalars().all()

    completed = [a for a in attempts if a.status == StudentRetestStatus.COMPLETED]
    in_progress = [a for a in attempts if a.status == StudentRetestStatus.IN_PROGRESS]
    not_started = [a for a in attempts if a.status == StudentRetestStatus.ASSIGNED]

    return RetestProgressOut(
        homework_id=str(hw.id),
        class_id=str(hw.class_id),
        assigned_count=hw.assigned_count,
        completed_count=len(completed),
        in_progress_count=len(in_progress),
        not_started_count=len(not_started),
        students=[
            StudentRetestOut(
                student_id=str(a.student_id), status=a.status, improvement_percent=a.improvement_percent
            )
            for a in attempts
        ],
    )
