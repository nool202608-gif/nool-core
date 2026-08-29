"""support tickets

Revision ID: 9a1c4e7b0d3f
Revises: 7c3f8a1d9e42
Create Date: 2026-08-28 16:00:00.000000

An internal-only issue tracker for School Admin <-> Super Admin support
issues - previously untracked, no durable record at all. See
SupportTicket's model docstring - same "close the loop" motivation as
UpgradeRequest, but for general issues rather than upgrade asks.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9a1c4e7b0d3f'
down_revision: Union[str, None] = '7c3f8a1d9e42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_tickets',
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('OPEN', 'IN_PROGRESS', 'RESOLVED', name='ticket_status'),
            nullable=False,
            server_default='OPEN',
        ),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'support_ticket_comments',
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('author_id', sa.UUID(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('support_ticket_comments')
    op.drop_table('support_tickets')
    op.execute('DROP TYPE IF EXISTS ticket_status')
