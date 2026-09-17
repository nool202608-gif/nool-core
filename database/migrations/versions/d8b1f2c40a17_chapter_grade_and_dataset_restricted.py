"""chapter grade and dataset restricted

Revision ID: d8b1f2c40a17
Revises: c7e4a1b8f930
Create Date: 2026-09-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8b1f2c40a17'
down_revision: Union[str, None] = 'c7e4a1b8f930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, additive - NULL means "applies to any grade" (every
    # chapter that predates this column) rather than being hidden. Only
    # POST /admin/curriculum/sync-from-kg's per-dataset sync sets a value
    # going forward - see Chapter's docstring.
    op.add_column('chapters', sa.Column('grade', sa.Integer(), nullable=True))

    # Defaults False so every pre-existing dataset keeps today's "visible
    # to any school that hasn't configured anything yet" behavior - only a
    # dataset explicitly marked restricted afterward changes that default.
    op.add_column(
        'datasets', sa.Column('restricted', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.alter_column('datasets', 'restricted', server_default=None)


def downgrade() -> None:
    op.drop_column('datasets', 'restricted')
    op.drop_column('chapters', 'grade')
