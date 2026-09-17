"""board/grade on datasets

Revision ID: c7e4a1b8f930
Revises: e2957f0dbe5b
Create Date: 2026-09-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e4a1b8f930'
down_revision: Union[str, None] = 'e2957f0dbe5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, additive - same reasoning as subject_id: a pre-existing
    # dataset (or a genuinely cross-board/cross-grade one) isn't forced to
    # pick these. Together with subject_id, these name which
    # kg-service Curriculum{board, grade, subject} root a dataset
    # corresponds to - see Dataset's docstring.
    op.add_column('datasets', sa.Column('board', sa.String(), nullable=True))
    op.add_column('datasets', sa.Column('grade', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('datasets', 'grade')
    op.drop_column('datasets', 'board')
