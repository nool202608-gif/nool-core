from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import AuditLog


async def record(
    session: AsyncSession, *, actor_id: UUID, action: str, target_type: str, target_id: str
) -> None:
    """Appends one row to audit_logs - callers still call session.commit()
    themselves afterward (this only stages the row), matching every other
    write in these route handlers.
    """
    session.add(
        AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id)
    )
