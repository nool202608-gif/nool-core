"""import jobs

Revision ID: 2b6d8f0a3c17
Revises: 9a1c4e7b0d3f
Create Date: 2026-08-28 17:00:00.000000

Durable, queryable visibility into bulk .csv/.xlsx upload runs (teacher
bulk-invite, student bulk-create, custom-question bulk-import) - see
ImportJob's model docstring. Previously a run's outcome only ever existed
in the one HTTP response returned to the uploader, never queryable again
afterward and never visible to Super Admin across schools.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2b6d8f0a3c17'
down_revision: Union[str, None] = '9a1c4e7b0d3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'import_jobs',
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('initiated_by', sa.UUID(), nullable=False),
        sa.Column(
            'job_type',
            sa.Enum('TEACHER_INVITE', 'STUDENT_CREATE', 'CUSTOM_QUESTION', name='import_job_type'),
            nullable=False,
        ),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('created_count', sa.Integer(), nullable=False),
        sa.Column('error_count', sa.Integer(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.ForeignKeyConstraint(['initiated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('import_jobs')
    op.execute('DROP TYPE IF EXISTS import_job_type')
