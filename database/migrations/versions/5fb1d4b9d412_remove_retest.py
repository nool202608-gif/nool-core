"""remove retest

Revision ID: 5fb1d4b9d412
Revises: bf51ac358189
Create Date: 2026-09-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5fb1d4b9d412'
down_revision: Union[str, None] = 'bf51ac358189'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ai_assessor_sessions.retest_attempt_id FK'd to retest_attempts.id -
    # must go before retest_attempts itself can be dropped.
    op.drop_column('ai_assessor_sessions', 'retest_attempt_id')
    op.drop_table('retest_bloom_comparison')
    op.drop_table('topic_performance')
    op.drop_table('retest_attempts')
    op.drop_column('homework', 'retest_authorized')
    postgresql.ENUM(name='student_retest_status').drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.add_column('homework', sa.Column('retest_authorized', sa.Boolean(), nullable=True))
    student_retest_status = postgresql.ENUM(
        'ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'RESULT_READY',
        name='student_retest_status', create_type=False,
    )
    student_retest_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'retest_attempts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('homework_id', sa.UUID(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('status', student_retest_status, nullable=False),
        sa.Column('attempts_used', sa.Integer(), nullable=False),
        sa.Column('baseline_percent', sa.Integer(), nullable=True),
        sa.Column('retest_percent', sa.Integer(), nullable=True),
        sa.Column('improvement_percent', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['homework_id'], ['homework.id']),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('homework_id', 'student_id'),
    )
    op.create_table(
        'topic_performance',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('test_id', sa.UUID(), nullable=False),
        sa.Column('homework_id', sa.UUID(), nullable=False),
        sa.Column('topic_label', sa.Text(), nullable=False),
        sa.Column('before_percent', sa.Integer(), nullable=True),
        sa.Column('after_percent', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['test_id'], ['voice_tests.id']),
        sa.ForeignKeyConstraint(['homework_id'], ['homework.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'retest_bloom_comparison',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('retest_attempt_id', sa.UUID(), nullable=False),
        sa.Column(
            'bloom_level',
            postgresql.ENUM(
                'REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYZE', 'EVALUATE', 'CREATE',
                name='bloom_level', create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('before', sa.Integer(), nullable=True),
        sa.Column('after', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['retest_attempt_id'], ['retest_attempts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('retest_attempt_id', 'bloom_level'),
    )
    op.add_column(
        'ai_assessor_sessions', sa.Column('retest_attempt_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        None, 'ai_assessor_sessions', 'retest_attempts', ['retest_attempt_id'], ['id']
    )
