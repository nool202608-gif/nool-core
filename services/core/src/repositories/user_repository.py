from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import User


async def get_by_firebase_uid(session: AsyncSession, firebase_uid: str) -> User | None:
    result = await session.execute(select(User).where(User.firebase_uid == firebase_uid))
    return result.scalar_one_or_none()
