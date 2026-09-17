"""voice pipeline and generated content

Revision ID: e8a9c310315a
Revises: f1a92c6de830
Create Date: 2026-09-14 06:41:46.753545

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8a9c310315a'
down_revision: Union[str, None] = 'f1a92c6de830'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Note: autogenerate also detected a pre-existing, unrelated drop of
    # 'ix_practice_bank_entries_student_id' (drift from other in-progress
    # work, not part of this change) - deliberately left out of this
    # revision.
    op.add_column('schools', sa.Column('voice_pipeline', sa.String(), nullable=True))
    op.add_column('voice_tests', sa.Column('reference_questions', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('voice_tests', sa.Column('textbook_context', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('voice_tests', 'textbook_context')
    op.drop_column('voice_tests', 'reference_questions')
    op.drop_column('schools', 'voice_pipeline')
