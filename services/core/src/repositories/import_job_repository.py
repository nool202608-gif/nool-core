from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import ImportJob, ImportJobType


def record(
    session: AsyncSession,
    *,
    school_id: UUID,
    initiated_by: UUID,
    job_type: ImportJobType,
    filename: str,
    row_count: int,
    created_count: int,
    error_count: int,
) -> None:
    """Stages one ImportJob row - callers still call session.commit()
    themselves afterward, matching audit_repository.record's contract.
    """
    session.add(
        ImportJob(
            school_id=school_id, initiated_by=initiated_by, job_type=job_type, filename=filename,
            row_count=row_count, created_count=created_count, error_count=error_count,
        )
    )
