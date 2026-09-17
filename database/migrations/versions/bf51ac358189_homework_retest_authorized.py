"""homework retest_authorized

Revision ID: bf51ac358189
Revises: f3daf3e7fd76
Create Date: 2026-09-11 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf51ac358189'
down_revision: Union[str, None] = 'f3daf3e7fd76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('homework', sa.Column('retest_authorized', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('homework', 'retest_authorized')
