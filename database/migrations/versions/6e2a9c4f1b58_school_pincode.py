"""school pincode

Revision ID: 6e2a9c4f1b58
Revises: 2b6d8f0a3c17
Create Date: 2026-08-28 18:00:00.000000

Adds a Pincode field to School's address - flagged as a missing field on
the school onboarding/edit forms.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6e2a9c4f1b58'
down_revision: Union[str, None] = '2b6d8f0a3c17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('pincode', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('schools', 'pincode')
