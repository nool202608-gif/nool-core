"""Support tickets - School Admin's own-school routes (support_ticket.py)
plus Super Admin's cross-tenant inbox (admin.py's ticket routes). Real rows
against the dev Postgres via db_session, same pattern as
test_reporting.py.
"""

import uuid

import pytest

from shared.errors import NotFoundError

from src.api.routes import admin, support_ticket
from src.api.schemas.support_ticket import (
    CreateSupportTicketIn,
    CreateTicketCommentIn,
    UpdateTicketStatusIn,
)
from src.domain.models import Role, School, TicketStatus, User, UserStatus


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


async def _seed_super_admin(db_session) -> User:
    su = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(su)
    await db_session.flush()
    return su


async def test_create_and_list_school_ticket(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)

    created = await support_ticket.create_school_ticket(
        CreateSupportTicketIn(subject="Can't invite a teacher", description="Getting a 500 error."),
        user=admin_user, session=db_session,
    )
    assert created.status == TicketStatus.OPEN
    assert created.school_name == school.name
    assert created.comment_count == 0

    listed = await support_ticket.list_school_tickets(user=admin_user, session=db_session)
    assert listed.total == 1
    assert listed.items[0].id == created.id


async def test_school_ticket_isolated_per_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    admin_b = await _seed_school_admin(db_session, school_b.id)

    ticket_a = await support_ticket.create_school_ticket(
        CreateSupportTicketIn(subject="A's issue", description="..."), user=admin_a, session=db_session,
    )
    await support_ticket.create_school_ticket(
        CreateSupportTicketIn(subject="B's issue", description="..."), user=admin_b, session=db_session,
    )

    listed_a = await support_ticket.list_school_tickets(user=admin_a, session=db_session)
    assert listed_a.total == 1
    assert listed_a.items[0].id == ticket_a.id

    with pytest.raises(NotFoundError):
        await support_ticket.get_school_ticket(ticket_a.id, user=admin_b, session=db_session)


async def test_school_ticket_comment_thread(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    ticket = await support_ticket.create_school_ticket(
        CreateSupportTicketIn(subject="Issue", description="..."), user=admin_user, session=db_session,
    )

    comment = await support_ticket.create_school_ticket_comment(
        ticket.id, CreateTicketCommentIn(body="Any update?"), user=admin_user, session=db_session,
    )
    assert comment.body == "Any update?"
    assert comment.author_name == admin_user.display_name

    thread = await support_ticket.list_school_ticket_comments(ticket.id, user=admin_user, session=db_session)
    assert thread.total == 1

    refreshed = await support_ticket.get_school_ticket(ticket.id, user=admin_user, session=db_session)
    assert refreshed.comment_count == 1


async def test_admin_inbox_lists_across_schools_and_filters_by_status(db_session):
    # Baselines captured before this test's own writes, then asserted as
    # deltas/membership - the dev Postgres this runs against is shared
    # with real, previously-committed rows from live UI testing sessions,
    # so an unfiltered or status-filtered list isn't reliably small going in.
    super_admin = await _seed_super_admin(db_session)
    baseline_all = (await admin.list_support_tickets(status=None, _=super_admin, session=db_session)).total
    baseline_open_ids = {
        t.id for t in (await admin.list_support_tickets(status=TicketStatus.OPEN, _=super_admin, session=db_session)).items
    }

    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    admin_b = await _seed_school_admin(db_session, school_b.id)

    ticket_a = await support_ticket.create_school_ticket(
        CreateSupportTicketIn(subject="A's issue", description="..."), user=admin_a, session=db_session,
    )
    ticket_b = await support_ticket.create_school_ticket(
        CreateSupportTicketIn(subject="B's issue", description="..."), user=admin_b, session=db_session,
    )

    all_tickets = await admin.list_support_tickets(status=None, _=super_admin, session=db_session)
    assert all_tickets.total == baseline_all + 2

    await admin.update_support_ticket_status(
        ticket_a.id, UpdateTicketStatusIn(status=TicketStatus.RESOLVED),
        actor=super_admin, session=db_session,
    )

    resolved = await admin.list_support_tickets(status=TicketStatus.RESOLVED, _=super_admin, session=db_session)
    assert ticket_a.id in {t.id for t in resolved.items}

    still_open = await admin.list_support_tickets(status=TicketStatus.OPEN, _=super_admin, session=db_session)
    still_open_ids = {t.id for t in still_open.items}
    assert still_open_ids == baseline_open_ids | {ticket_b.id}


async def test_admin_can_comment_on_any_ticket(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    super_admin = await _seed_super_admin(db_session)
    ticket = await support_ticket.create_school_ticket(
        CreateSupportTicketIn(subject="Issue", description="..."), user=admin_user, session=db_session,
    )

    await admin.create_support_ticket_comment(
        ticket.id, CreateTicketCommentIn(body="Looking into this now."),
        actor=super_admin, session=db_session,
    )

    thread = await admin.list_support_ticket_comments(ticket.id, _=super_admin, session=db_session)
    assert thread.total == 1
    assert thread.items[0].author_name == super_admin.display_name

    # School Admin sees the same comment through their own read path.
    school_side_thread = await support_ticket.list_school_ticket_comments(
        ticket.id, user=admin_user, session=db_session
    )
    assert school_side_thread.total == 1


async def test_get_unknown_ticket_raises_not_found(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin.get_support_ticket(str(uuid.uuid4()), _=super_admin, session=db_session)
