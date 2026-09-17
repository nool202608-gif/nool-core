"""practice bank entries

Revision ID: a4cc8ec1b122
Revises: 5fb1d4b9d412
Create Date: 2026-09-11 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a4cc8ec1b122'
down_revision: Union[str, None] = '5fb1d4b9d412'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'practice_bank_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('source_homework_id', sa.UUID(), nullable=False),
        sa.Column('source_question_id', sa.UUID(), nullable=False),
        sa.Column('subject_id', sa.UUID(), nullable=True),
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
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.ForeignKeyConstraint(['source_homework_id'], ['homework.id']),
        sa.ForeignKeyConstraint(['source_question_id'], ['homework_questions.id']),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id']),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id']),
        sa.ForeignKeyConstraint(['topic_id'], ['topics.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'source_question_id'),
    )
    op.create_index(
        'ix_practice_bank_entries_student_id', 'practice_bank_entries', ['student_id']
    )


def downgrade() -> None:
    op.drop_table('practice_bank_entries')
