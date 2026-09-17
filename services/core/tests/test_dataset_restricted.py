"""GET /datasets (teacher-facing) must not leak a `restricted` dataset -
a school-exclusive question bank meant for one specific school - to every
other school just because that school hasn't configured its own dataset
list yet. See Dataset.restricted's docstring.
"""

import uuid

import pytest

from src.api.routes import dataset as dataset_routes
from src.domain.models import Dataset, Role, School, SchoolDataset, User, UserStatus


async def _seed_teacher(db_session) -> tuple[User, School]:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email=f"{uuid.uuid4()}@b.com")
    db_session.add(school)
    await db_session.flush()
    teacher = User(
        firebase_uid=f"t-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Teacher", role=Role.TEACHER, school_id=school.id, status=UserStatus.ACTIVE,
    )
    db_session.add(teacher)
    await db_session.flush()
    return teacher, school


@pytest.mark.asyncio
async def test_a_restricted_dataset_is_invisible_to_a_school_with_no_config_at_all(db_session):
    teacher, _school = await _seed_teacher(db_session)
    restricted = Dataset(
        name="MVM-only bank", question_count=10, description="", restricted=True,
    )
    ordinary = Dataset(name="Shared catalog dataset", question_count=5, description="", restricted=False)
    db_session.add_all([restricted, ordinary])
    await db_session.flush()

    result = await dataset_routes.list_datasets(user=teacher, session=db_session)

    names = {item.name for item in result.items}
    assert ordinary.name in names
    assert restricted.name not in names


@pytest.mark.asyncio
async def test_a_restricted_dataset_shows_up_once_a_school_explicitly_enables_it(db_session):
    teacher, school = await _seed_teacher(db_session)
    restricted = Dataset(name="MVM-only bank", question_count=10, description="", restricted=True)
    db_session.add(restricted)
    await db_session.flush()
    db_session.add(SchoolDataset(school_id=school.id, dataset_id=restricted.id, enabled=True))
    await db_session.flush()

    result = await dataset_routes.list_datasets(user=teacher, session=db_session)

    assert [item.name for item in result.items] == [restricted.name]


@pytest.mark.asyncio
async def test_a_restricted_dataset_stays_hidden_from_a_school_with_other_config_but_no_row_for_it(
    db_session,
):
    teacher, school = await _seed_teacher(db_session)
    restricted = Dataset(name="MVM-only bank", question_count=10, description="", restricted=True)
    unrelated = Dataset(name="Unrelated dataset", question_count=1, description="", restricted=False)
    db_session.add_all([restricted, unrelated])
    await db_session.flush()
    # This school has configured *something* (unrelated), but never
    # touched the restricted one - it must still stay hidden, not fall
    # back to "show everything" just because some config exists.
    db_session.add(SchoolDataset(school_id=school.id, dataset_id=unrelated.id, enabled=True))
    await db_session.flush()

    result = await dataset_routes.list_datasets(user=teacher, session=db_session)

    names = {item.name for item in result.items}
    assert unrelated.name in names
    assert restricted.name not in names
