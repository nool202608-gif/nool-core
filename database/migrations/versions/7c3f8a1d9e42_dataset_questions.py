"""dataset questions

Revision ID: 7c3f8a1d9e42
Revises: 5e91c3a7b2d4
Create Date: 2026-08-28 15:00:00.000000

Real content for a Dataset - previously question_count was a manually-typed
integer with no linkage to actual question rows (see requirements.md's
flagged gap). Also links a Dataset to the one Subject it belongs to. See
DatasetQuestion/Dataset's model docstrings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7c3f8a1d9e42'
down_revision: Union[str, None] = '5e91c3a7b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('datasets', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.create_foreign_key('datasets_subject_id_fkey', 'datasets', 'subjects', ['subject_id'], ['id'])

    op.create_table(
        'dataset_questions',
        sa.Column('dataset_id', sa.UUID(), nullable=False),
        sa.Column('chapter_id', sa.UUID(), nullable=True),
        sa.Column('topic_id', sa.UUID(), nullable=True),
        sa.Column(
            'bloom_level',
            postgresql.ENUM(
                'REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYZE', 'EVALUATE', 'CREATE',
                name='bloom_level', create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            'question_type',
            postgresql.ENUM('MCQ', 'SHORT_ANSWER', 'LONG_ANSWER', 'TRUE_FALSE', name='question_type', create_type=False),
            nullable=False,
        ),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ),
        sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('dataset_questions')
    op.drop_constraint('datasets_subject_id_fkey', 'datasets', type_='foreignkey')
    op.drop_column('datasets', 'subject_id')
