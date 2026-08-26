from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import Plan, Subscription


async def get_active_plan(session: AsyncSession, school_id: UUID) -> Plan | None:
    """The one place limit-checks resolve "this school's current plan" -
    always via the school's Subscription row, never School.plan_id (see
    that column's deprecation note in src/domain/models/foundation.py).
    Returns None if the school has no subscription yet, in which case
    callers should treat every limit as unset (a school mid-onboarding,
    before its first Subscription row exists, is not yet a billable
    context to enforce limits against).
    """
    result = await session.execute(
        select(Plan).join(Subscription, Subscription.plan_id == Plan.id).where(
            Subscription.school_id == school_id
        )
    )
    return result.scalar_one_or_none()
