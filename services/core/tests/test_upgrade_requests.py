"""Super Admin's Upgrade Requests inbox - closes the loop School Admin's
"Request an upgrade" CTA (school_admin.py's request_subscription_upgrade)
otherwise dead-ends into. See UpgradeRequest's model docstring.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from shared.errors import NotFoundError

from src.api.routes import admin, school_admin
from src.api.schemas.admin import UpdateUpgradeRequestStatusIn
from src.api.schemas.school_admin import UpgradeRequestIn
from src.domain.models import Role, School, UpgradeRequest, UpgradeRequestStatus, User, UserStatus


async def _seed_super_admin(db_session) -> User:
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()
    return super_admin


async def _seed_school(db_session) -> School:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_school_admin(db_session, school_id) -> User:
    admin_user = User(
        firebase_uid=f"admin-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Admin", role=Role.SCHOOL_ADMIN, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(admin_user)
    await db_session.flush()
    return admin_user


async def test_request_subscription_upgrade_creates_upgrade_request_row(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)

    await school_admin.request_subscription_upgrade(
        UpgradeRequestIn(message="need 50 more seats"), user=admin_user, session=db_session
    )

    result = await db_session.execute(select(UpgradeRequest).where(UpgradeRequest.school_id == school.id))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].message == "need 50 more seats"
    assert rows[0].status == UpgradeRequestStatus.PENDING
    assert rows[0].requested_by == admin_user.id


async def test_list_upgrade_requests_resolves_school_and_requester_names(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    db_session.add(UpgradeRequest(school_id=school.id, requested_by=admin_user.id, message="hello"))
    await db_session.flush()

    result = await admin.list_upgrade_requests(status=None, _=super_admin, session=db_session)

    assert result.total == 1
    item = result.items[0]
    assert item.school_name == school.name
    assert item.requested_by_name == admin_user.display_name
    assert item.requested_by_email == admin_user.email
    assert item.message == "hello"
    assert item.status == UpgradeRequestStatus.PENDING
    assert item.resolved_at is None


async def test_list_upgrade_requests_filters_by_status(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    db_session.add(UpgradeRequest(school_id=school.id, requested_by=admin_user.id, status=UpgradeRequestStatus.PENDING))
    db_session.add(UpgradeRequest(school_id=school.id, requested_by=admin_user.id, status=UpgradeRequestStatus.RESOLVED))
    await db_session.flush()

    pending = await admin.list_upgrade_requests(status=UpgradeRequestStatus.PENDING, _=super_admin, session=db_session)
    assert pending.total == 1
    assert pending.items[0].status == UpgradeRequestStatus.PENDING

    resolved = await admin.list_upgrade_requests(status=UpgradeRequestStatus.RESOLVED, _=super_admin, session=db_session)
    assert resolved.total == 1
    assert resolved.items[0].status == UpgradeRequestStatus.RESOLVED


async def test_list_upgrade_requests_newest_first(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    older = UpgradeRequest(
        school_id=school.id, requested_by=admin_user.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    newer = UpgradeRequest(school_id=school.id, requested_by=admin_user.id, created_at=datetime.now(timezone.utc))
    db_session.add(older)
    db_session.add(newer)
    await db_session.flush()

    result = await admin.list_upgrade_requests(status=None, _=super_admin, session=db_session)
    assert result.items[0].id == str(newer.id)
    assert result.items[1].id == str(older.id)


async def test_update_upgrade_request_status_sets_resolved_metadata(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    req = UpgradeRequest(school_id=school.id, requested_by=admin_user.id)
    db_session.add(req)
    await db_session.flush()

    result = await admin.update_upgrade_request_status(
        str(req.id), UpdateUpgradeRequestStatusIn(status=UpgradeRequestStatus.RESOLVED),
        actor=super_admin, session=db_session,
    )
    assert result.status == UpgradeRequestStatus.RESOLVED
    assert result.resolved_at is not None

    refreshed = await db_session.execute(select(UpgradeRequest).where(UpgradeRequest.id == req.id))
    row = refreshed.scalar_one()
    assert row.resolved_by == super_admin.id


async def test_update_upgrade_request_status_back_to_pending_clears_resolved_metadata(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    req = UpgradeRequest(
        school_id=school.id, requested_by=admin_user.id, status=UpgradeRequestStatus.RESOLVED,
        resolved_at=datetime.now(timezone.utc), resolved_by=super_admin.id,
    )
    db_session.add(req)
    await db_session.flush()

    result = await admin.update_upgrade_request_status(
        str(req.id), UpdateUpgradeRequestStatusIn(status=UpgradeRequestStatus.PENDING),
        actor=super_admin, session=db_session,
    )
    assert result.status == UpgradeRequestStatus.PENDING
    assert result.resolved_at is None


async def test_update_upgrade_request_status_unknown_request_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin.update_upgrade_request_status(
            str(uuid.uuid4()), UpdateUpgradeRequestStatusIn(status=UpgradeRequestStatus.CONTACTED),
            actor=super_admin, session=db_session,
        )
