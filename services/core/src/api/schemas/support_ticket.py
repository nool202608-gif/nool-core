from datetime import datetime

from src.domain.models import TicketStatus

from .common import CamelModel


class SupportTicketOut(CamelModel):
    id: str
    school_id: str
    school_name: str
    created_by: str
    created_by_name: str
    subject: str
    description: str
    status: TicketStatus
    created_at: datetime
    comment_count: int


class CreateSupportTicketIn(CamelModel):
    subject: str
    description: str


class UpdateTicketStatusIn(CamelModel):
    status: TicketStatus


class TicketCommentOut(CamelModel):
    id: str
    author_id: str
    author_name: str
    body: str
    created_at: datetime


class CreateTicketCommentIn(CamelModel):
    body: str
