from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import NotFoundError

from src.api.deps import get_db_session, require_role
from src.api.schemas.bloom import BloomScore
from src.api.schemas.bloom_result import StudentTestBloomResultOut
from src.domain.models import BloomLevel, Role, StudentTestResult, StudentTestResultBloomScore, User

router = APIRouter(prefix="/api/v1", tags=["bloom-result"])


@router.get("/me/tests/{test_id}/bloom-result")
async def get_bloom_result(
    test_id: str,
    user: User = Depends(require_role(Role.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
) -> StudentTestBloomResultOut:
    result = await session.execute(
        select(StudentTestResult).where(
            StudentTestResult.test_id == test_id, StudentTestResult.student_id == user.id
        )
    )
    student_result = result.scalar_one_or_none()
    if student_result is None:
        raise NotFoundError("You haven't attempted this Test.")

    scores = await session.execute(
        select(StudentTestResultBloomScore).where(
            StudentTestResultBloomScore.student_test_result_id == student_result.id
        )
    )
    by_level = {s.bloom_level: s.percent for s in scores.scalars().all()}
    bloom_performance = [
        BloomScore(level=level, percent=by_level.get(level)) for level in BloomLevel
    ]

    return StudentTestBloomResultOut(
        test_id=test_id,
        overall_percent=student_result.mastery_percent,
        bloom_performance=bloom_performance,
    )
