"""School Admin's side of the internal support-ticket tracker - the
Super Admin inbox (cross-tenant list, status updates) lives in admin.py
instead, right next to the closely-analogous UpgradeRequest inbox rather
than duplicating a second admin-facing router for the same underlying
table. See SupportTicket's model docstring for why this exists.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import NotFoundError

from src.api.deps import get_db_session, require_role
from src.api.schemas.common import ListEnvelope
from src.api.schemas.support_ticket import (
    CreateSupportTicketIn,
    CreateTicketCommentIn,
    SupportTicketOut,
    TicketCommentOut,
)
from src.domain.models import Role, School, SupportTicket, SupportTicketComment, User
from src.repositories import audit_repository

router = APIRouter(prefix="/api/v1/school", tags=["support-tickets"])


async def _ticket_out(session: AsyncSession, ticket: SupportTicket) -> SupportTicketOut:
    school = await session.get(School, ticket.school_id)
    creator = await session.get(User, ticket.created_by)
    count_result = await session.execute(
        select(func.count()).select_from(SupportTicketComment).where(SupportTicketComment.ticket_id == ticket.id)
    )
    return SupportTicketOut(
        id=str(ticket.id), school_id=str(ticket.school_id), school_name=school.name if school else "",
        created_by=str(ticket.created_by), created_by_name=creator.display_name if creator else "",
        subject=ticket.subject, description=ticket.description, status=ticket.status,
        created_at=ticket.created_at, comment_count=count_result.scalar_one(),
    )


async def _get_own_ticket(session: AsyncSession, ticket_id: str, school_id) -> SupportTicket:
    result = await session.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id, SupportTicket.school_id == school_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError(f'No ticket with id "{ticket_id}" for your school.')
    return ticket


@router.get("/tickets", summary="This school's support tickets")
async def list_school_tickets(
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[SupportTicketOut]:
    result = await session.execute(
        select(SupportTicket).where(SupportTicket.school_id == user.school_id).order_by(
            SupportTicket.created_at.desc()
        )
    )
    items = [await _ticket_out(session, t) for t in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.post("/tickets", status_code=201, summary="File a new support ticket")
async def create_school_ticket(
    body: CreateSupportTicketIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SupportTicketOut:
    ticket = SupportTicket(
        school_id=user.school_id, created_by=user.id, subject=body.subject, description=body.description,
    )
    session.add(ticket)
    await session.flush()
    await audit_repository.record(
        session, actor_id=user.id, action="ticket.created", target_type="support_ticket", target_id=str(ticket.id),
    )
    await session.commit()
    await session.refresh(ticket)
    return await _ticket_out(session, ticket)


@router.get("/tickets/{ticket_id}", summary="One ticket's detail")
async def get_school_ticket(
    ticket_id: str,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> SupportTicketOut:
    ticket = await _get_own_ticket(session, ticket_id, user.school_id)
    return await _ticket_out(session, ticket)


@router.get("/tickets/{ticket_id}/comments", summary="A ticket's comment thread")
async def list_school_ticket_comments(
    ticket_id: str,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[TicketCommentOut]:
    await _get_own_ticket(session, ticket_id, user.school_id)
    result = await session.execute(
        select(SupportTicketComment).where(SupportTicketComment.ticket_id == ticket_id).order_by(
            SupportTicketComment.created_at
        )
    )
    comments = result.scalars().all()
    authors = {a.id: a for a in (
        await session.execute(select(User).where(User.id.in_({c.author_id for c in comments})))
    ).scalars().all()} if comments else {}
    items = [
        TicketCommentOut(
            id=str(c.id), author_id=str(c.author_id),
            author_name=authors[c.author_id].display_name if c.author_id in authors else "",
            body=c.body, created_at=c.created_at,
        )
        for c in comments
    ]
    return ListEnvelope(items=items, total=len(items))


@router.post("/tickets/{ticket_id}/comments", status_code=201, summary="Reply on a ticket")
async def create_school_ticket_comment(
    ticket_id: str,
    body: CreateTicketCommentIn,
    user: User = Depends(require_role(Role.SCHOOL_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> TicketCommentOut:
    await _get_own_ticket(session, ticket_id, user.school_id)
    comment = SupportTicketComment(ticket_id=ticket_id, author_id=user.id, body=body.body)
    session.add(comment)
    await audit_repository.record(
        session, actor_id=user.id, action="ticket.comment.created",
        target_type="support_ticket", target_id=ticket_id,
    )
    await session.commit()
    await session.refresh(comment)
    return TicketCommentOut(
        id=str(comment.id), author_id=str(comment.author_id), author_name=user.display_name,
        body=comment.body, created_at=comment.created_at,
    )
