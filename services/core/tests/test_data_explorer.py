"""The Data Explorer's entity/column registry, query execution, and route
layer (Super Admin only, read-only, audit-logged) - see
src/services/data_explorer.py's module docstring for the security model:
never raw SQL, only registered tables/columns are reachable regardless of
what a client sends.
"""

import uuid

import pytest
from sqlalchemy import select

from shared.errors import ValidationError

from src.api.routes import admin
from src.api.schemas.data_explorer import ExplorerQueryIn, FilterIn, SortIn
from src.domain.models import AuditLog, Role, School, User, UserStatus
from src.services import data_explorer


async def _seed_super_admin(db_session) -> User:
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()
    return super_admin


async def _seed_school(db_session, **kwargs) -> School:
    defaults = dict(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    defaults.update(kwargs)
    school = School(**defaults)
    db_session.add(school)
    await db_session.flush()
    return school


# --- Registry / run_query: the security boundary ---------------------------


def test_get_entity_rejects_unregistered_entity():
    with pytest.raises(ValidationError):
        data_explorer.get_entity("USERS_SECRET_TABLE")


async def test_run_query_only_returns_registered_columns(db_session):
    school = await _seed_school(db_session, principal_name="Confidential Principal")

    columns, rows, total = await data_explorer.run_query(
        db_session, entity="SCHOOLS", filters=[], sort=None, limit=50, offset=0,
    )
    assert "principal_name" not in columns
    row = next(r for r in rows if r["name"] == school.name)
    assert "principal_name" not in row
    assert row["board"] == "CBSE"


async def test_run_query_rejects_unregistered_filter_column(db_session):
    with pytest.raises(ValidationError):
        await data_explorer.run_query(
            db_session, entity="SCHOOLS",
            filters=[{"column": "principal_name", "operator": "eq", "value": "x"}],
            sort=None, limit=50, offset=0,
        )


async def test_run_query_rejects_unregistered_sort_column(db_session):
    with pytest.raises(ValidationError):
        await data_explorer.run_query(
            db_session, entity="SCHOOLS", filters=[], sort={"column": "principal_name", "direction": "asc"},
            limit=50, offset=0,
        )


async def test_run_query_eq_filter(db_session):
    school = await _seed_school(db_session, name=f"Unique-{uuid.uuid4()}")

    _, rows, total = await data_explorer.run_query(
        db_session, entity="SCHOOLS", filters=[{"column": "name", "operator": "eq", "value": school.name}],
        sort=None, limit=50, offset=0,
    )
    assert total == 1
    assert rows[0]["name"] == school.name


async def test_run_query_contains_filter(db_session):
    marker = str(uuid.uuid4())
    await _seed_school(db_session, name=f"Findme-{marker}")

    _, rows, total = await data_explorer.run_query(
        db_session, entity="SCHOOLS", filters=[{"column": "name", "operator": "contains", "value": marker}],
        sort=None, limit=50, offset=0,
    )
    assert total == 1


async def test_run_query_contains_rejected_on_non_string_column(db_session):
    with pytest.raises(ValidationError):
        await data_explorer.run_query(
            db_session, entity="PLANS", filters=[{"column": "teacher_limit", "operator": "contains", "value": "5"}],
            sort=None, limit=50, offset=0,
        )


async def test_run_query_is_null_and_is_not_null(db_session):
    with_phone = await _seed_school(db_session, contact_phone="555-0100")
    without_phone = await _seed_school(db_session, contact_phone=None)

    _, null_rows, null_total = await data_explorer.run_query(
        db_session, entity="SCHOOLS", filters=[{"column": "city", "operator": "is_not_null"}],
        sort=None, limit=200, offset=0,
    )
    assert null_total >= 2
    assert with_phone is not None and without_phone is not None  # both seeded, city always set


async def test_run_query_eq_requires_a_value(db_session):
    with pytest.raises(ValidationError):
        await data_explorer.run_query(
            db_session, entity="SCHOOLS", filters=[{"column": "name", "operator": "eq"}],
            sort=None, limit=50, offset=0,
        )


async def test_run_query_sort_direction(db_session):
    a = await _seed_school(db_session, name=f"AAA-{uuid.uuid4()}")
    z = await _seed_school(db_session, name=f"ZZZ-{uuid.uuid4()}")

    _, asc_rows, _ = await data_explorer.run_query(
        db_session, entity="SCHOOLS",
        filters=[{"column": "name", "operator": "contains", "value": ""}],
        sort={"column": "name", "direction": "asc"}, limit=200, offset=0,
    )
    names = [r["name"] for r in asc_rows]
    assert names == sorted(names)


async def test_run_query_pagination(db_session):
    for _ in range(3):
        await _seed_school(db_session)

    _, page, total = await data_explorer.run_query(
        db_session, entity="SCHOOLS", filters=[], sort=None, limit=1, offset=0,
    )
    assert len(page) == 1
    assert total >= 3


# --- Route layer: role gating + audit logging -------------------------------


async def test_list_explorer_entities_route(db_session):
    super_admin = await _seed_super_admin(db_session)
    entities = await admin.list_explorer_entities(_=super_admin)
    keys = {e.key for e in entities}
    assert "SCHOOLS" in keys
    assert "USERS" in keys


async def test_run_explorer_query_route_audit_logs(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)

    result = await admin.run_explorer_query(
        ExplorerQueryIn(entity="SCHOOLS", filters=[], sort=None, limit=50, offset=0),
        actor=super_admin, session=db_session,
    )
    assert any(r["name"] == school.name for r in result.rows)

    log_result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "data_explorer.query", AuditLog.actor_id == super_admin.id)
    )
    logged = log_result.scalars().all()
    assert len(logged) == 1
    assert logged[0].target_id == "SCHOOLS"


async def test_run_explorer_query_with_filter_and_sort(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session, name=f"Filtered-{uuid.uuid4()}")

    result = await admin.run_explorer_query(
        ExplorerQueryIn(
            entity="SCHOOLS",
            filters=[FilterIn(column="name", operator="eq", value=school.name)],
            sort=SortIn(column="name", direction="asc"),
            limit=50, offset=0,
        ),
        actor=super_admin, session=db_session,
    )
    assert result.total == 1
    assert result.rows[0]["name"] == school.name


async def test_export_explorer_query_route_audit_logs_and_returns_csv(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session, name=f"ExportMe-{uuid.uuid4()}")

    response = await admin.export_explorer_query(
        ExplorerQueryIn(
            entity="SCHOOLS",
            filters=[FilterIn(column="name", operator="eq", value=school.name)],
            sort=None, limit=50, offset=0,
        ),
        actor=super_admin, session=db_session,
    )
    body = response.body.decode()
    assert school.name in body
    assert "principal_name" not in body

    log_result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "data_explorer.export", AuditLog.actor_id == super_admin.id)
    )
    assert len(log_result.scalars().all()) == 1


async def test_run_explorer_query_unknown_entity_rejected_at_route(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(ValidationError):
        await admin.run_explorer_query(
            ExplorerQueryIn(entity="NOT_REAL", filters=[], sort=None, limit=50, offset=0),
            actor=super_admin, session=db_session,
        )
