import uuid
from enum import Enum

from sqlalchemy import ForeignKey, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import IdMixin, TimestampMixin


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class SupportTicket(IdMixin, TimestampMixin, Base):
    """An internal-only issue tracker replacing the untracked side-channel
    ("email/call noolAI when something's broken") School Admin otherwise
    has no record of - same gap UpgradeRequest closed for upgrade asks
    (see that model's docstring), but for general support issues. No
    email/Slack integration and no SLAs by design for this first version -
    just a durable, queryable record both sides can see and act on.
    """

    __tablename__ = "support_tickets"

    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(SAEnum(TicketStatus, name="ticket_status"), default=TicketStatus.OPEN)


class SupportTicketComment(IdMixin, TimestampMixin, Base):
    """One reply in a ticket's thread - either side can post one, in
    either status (a RESOLVED ticket can still get a follow-up comment
    that reopens the conversation without necessarily changing status).
    """

    __tablename__ = "support_ticket_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("support_tickets.id"))
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
