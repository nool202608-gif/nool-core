from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, require_role
from src.api.schemas.common import ListEnvelope
from src.api.schemas.dataset import DatasetOut
from src.domain.models import Dataset, Role, SchoolDataset, User

router = APIRouter(prefix="/api/v1", tags=["datasets"])


@router.get("/datasets")
async def list_datasets(
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[DatasetOut]:
    """Filtered to the caller's school's enabled datasets (school_datasets)
    - if the school has no school_datasets rows at all yet, every
    non-restricted dataset in the global catalog is returned rather than
    an empty list, since "not configured" shouldn't look identical to
    "explicitly enabled nothing" - same rule as GET /subjects.

    A `restricted` dataset (see Dataset.restricted's docstring) is the one
    exception to that fallback: it's a school-exclusive dataset (e.g. a
    large question bank meant only for one specific school), not part of
    the shared default catalog, so it stays invisible everywhere unless a
    school has explicitly enabled it - "not configured" must not
    accidentally leak it to every school that simply hasn't touched their
    dataset config yet.
    """
    has_any_config = await session.execute(
        select(SchoolDataset.id).where(SchoolDataset.school_id == user.school_id).limit(1)
    )
    if has_any_config.scalar_one_or_none() is None:
        # No rows for this school at all yet - trust the catalog's own
        # non-restricted datasets; a restricted one can't be "enabled" for
        # this school either, since that would itself be a school_datasets
        # row, which is exactly what "no rows at all" rules out.
        result = await session.execute(select(Dataset).where(Dataset.restricted.is_(False)))
    else:
        enabled = await session.execute(
            select(SchoolDataset.dataset_id).where(
                SchoolDataset.school_id == user.school_id, SchoolDataset.enabled.is_(True)
            )
        )
        enabled_ids = [row[0] for row in enabled.all()]
        result = await session.execute(select(Dataset).where(Dataset.id.in_(enabled_ids)))

    items = [
        DatasetOut(
            id=str(d.id), name=d.name, question_count=d.question_count, description=d.description,
            type=d.type,
        )
        for d in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))
