"""grade subjects

Revision ID: 8b4e6c2f9d17
Revises: 6f2f4d9c1a3e
Create Date: 2026-08-28 12:00:00.000000

Which subjects a Class (SchoolGrade) teaches - narrower than the existing
school-wide SchoolCurriculum toggle, picked explicitly per Class rather than
derived from it. See GradeSubject's model docstring.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8b4e6c2f9d17'
down_revision: Union[str, None] = '6f2f4d9c1a3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'grade_subjects',
        sa.Column('grade_id', sa.UUID(), nullable=False),
        sa.Column('subject_id', sa.UUID(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['grade_id'], ['school_grades.id'], ),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('grade_id', 'subject_id'),
    )


def downgrade() -> None:
    op.drop_table('grade_subjects')
