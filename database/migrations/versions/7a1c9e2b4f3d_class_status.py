"""class status

Revision ID: 7a1c9e2b4f3d
Revises: 0b2fa06371d7
Create Date: 2026-08-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7a1c9e2b4f3d'
down_revision: Union[str, None] = '0b2fa06371d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reuses the existing user_status enum type (PENDING/ACTIVE/DEACTIVATED)
    # created by the initial schema migration - create_type=False so this
    # doesn't try to CREATE TYPE user_status a second time.
    op.add_column(
        'classes',
        sa.Column(
            'status',
            sa.Enum('PENDING', 'ACTIVE', 'DEACTIVATED', name='user_status', create_type=False),
            nullable=False,
            server_default='ACTIVE',
        ),
    )


def downgrade() -> None:
    op.drop_column('classes', 'status')
