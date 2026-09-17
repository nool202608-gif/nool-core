"""kg_ref on chapters/topics

Revision ID: e2957f0dbe5b
Revises: a4cc8ec1b122
Create Date: 2026-09-11 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2957f0dbe5b'
down_revision: Union[str, None] = 'a4cc8ec1b122'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, additive: existing admin-entered rows have no KG
    # counterpart and stay NULL forever. Only rows written by the
    # kg-service sync (POST /admin/curriculum/sync-from-kg) get a value -
    # it's the stable match key that makes that sync idempotent (a
    # chapter/topic title can be hand-edited afterward without breaking
    # re-sync, unlike matching on name).
    op.add_column('chapters', sa.Column('kg_ref', sa.String(), nullable=True))
    op.add_column('topics', sa.Column('kg_ref', sa.String(), nullable=True))
    op.create_unique_constraint('uq_chapters_kg_ref', 'chapters', ['kg_ref'])
    op.create_unique_constraint('uq_topics_kg_ref', 'topics', ['kg_ref'])


def downgrade() -> None:
    op.drop_constraint('uq_topics_kg_ref', 'topics', type_='unique')
    op.drop_constraint('uq_chapters_kg_ref', 'chapters', type_='unique')
    op.drop_column('topics', 'kg_ref')
    op.drop_column('chapters', 'kg_ref')
