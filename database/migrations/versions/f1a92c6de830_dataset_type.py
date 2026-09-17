"""dataset type

Revision ID: f1a92c6de830
Revises: d8b1f2c40a17
Create Date: 2026-09-19 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f1a92c6de830'
down_revision: Union[str, None] = 'd8b1f2c40a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A brand-new enum type used inside add_column (not create_table)
    # doesn't reliably get its CREATE TYPE issued implicitly - same
    # pitfall as 5fb1d4b9d412_remove_retest.py's plain sa.Enum inside
    # create_table - so create it explicitly first, then reference it with
    # create_type=False.
    dataset_type = postgresql.ENUM('QA', 'PRIMARY_CONTENT', name='dataset_type')
    dataset_type.create(op.get_bind(), checkfirst=True)

    # Nullable at first so the backfill below can set a real value per
    # existing row before the NOT NULL constraint goes on - a single
    # server_default would have to guess wrong for at least one of the two
    # kinds of dataset that already exist.
    op.add_column(
        'datasets',
        sa.Column('type', postgresql.ENUM('QA', 'PRIMARY_CONTENT', name='dataset_type', create_type=False), nullable=True),
    )

    # A dataset that already names a real KG root (board+grade+subject_id
    # all set - see Dataset.board/grade's docstring) is PRIMARY_CONTENT;
    # every other existing dataset is the hand-curated Q&A catalog this
    # app has always had, so it's QA.
    op.execute(
        """
        UPDATE datasets
        SET type = CASE
            WHEN board IS NOT NULL AND grade IS NOT NULL AND subject_id IS NOT NULL
                THEN 'PRIMARY_CONTENT'::dataset_type
            ELSE 'QA'::dataset_type
        END
        """
    )

    op.alter_column('datasets', 'type', nullable=False, server_default='QA')
    op.alter_column('datasets', 'type', server_default=None)


def downgrade() -> None:
    op.drop_column('datasets', 'type')
    postgresql.ENUM(name='dataset_type').drop(op.get_bind(), checkfirst=True)
