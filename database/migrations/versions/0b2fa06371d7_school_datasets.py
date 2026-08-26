"""school datasets

Revision ID: 0b2fa06371d7
Revises: ade4f3cd33d7
Create Date: 2026-08-25 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b2fa06371d7'
down_revision: Union[str, None] = 'ade4f3cd33d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('school_datasets',
    sa.Column('school_id', sa.UUID(), nullable=False),
    sa.Column('dataset_id', sa.UUID(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ),
    sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'dataset_id')
    )


def downgrade() -> None:
    op.drop_table('school_datasets')
