"""upgrade requests

Revision ID: 3d7a9f1e5c62
Revises: 8b4e6c2f9d17
Create Date: 2026-08-28 13:00:00.000000

A durable, queryable inbox for School Admin's "Request an upgrade" CTA -
previously only recorded to the audit log (no resolved/unresolved state)
and a best-effort email that's usually unconfigured in dev. See
UpgradeRequest's model docstring.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3d7a9f1e5c62'
down_revision: Union[str, None] = '8b4e6c2f9d17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'upgrade_requests',
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('requested_by', sa.UUID(), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'CONTACTED', 'RESOLVED', name='upgrade_request_status'),
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('upgrade_requests')
    op.execute('DROP TYPE IF EXISTS upgrade_request_status')
