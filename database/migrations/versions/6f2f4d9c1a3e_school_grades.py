"""school grades

Revision ID: 6f2f4d9c1a3e
Revises: 94dcb78f75fd
Create Date: 2026-08-28 10:45:00.000000

Adds the 'Class' level (e.g. "Class 10") of the School -> Class -> Section ->
Students hierarchy, as a new sibling table rather than a rename of the
existing `classes` table - `classes` (model SchoolClass) keeps its exact
name/columns/shape, since nool-apps (mobile, not touched by this migration)
already depends on it. `classes.grade_id` links each existing row (a
Section) to the Class it belongs to, backfilled here by grouping on the
`(school_id, grade)` pairs already present in the data - one new
`school_grades` row per distinct pair, id chosen with gen_random_uuid() to
match every other UUID primary key in this schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6f2f4d9c1a3e'
down_revision: Union[str, None] = '94dcb78f75fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'school_grades',
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('grade', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            postgresql.ENUM('PENDING', 'ACTIVE', 'DEACTIVATED', name='user_status', create_type=False),
            nullable=False,
            server_default='ACTIVE',
        ),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'grade'),
    )
    op.add_column('classes', sa.Column('grade_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'classes_grade_id_fkey', 'classes', 'school_grades', ['grade_id'], ['id'],
    )

    # Backfill: one school_grades row per distinct (school_id, grade) pair
    # already present in classes, then point every matching classes row at
    # it. Plain SQL rather than the ORM - migrations run standalone,
    # outside the app's session/request lifecycle.
    op.execute(
        """
        INSERT INTO school_grades (id, school_id, grade, status, created_at)
        SELECT gen_random_uuid(), school_id, grade, 'ACTIVE', now()
        FROM (SELECT DISTINCT school_id, grade FROM classes) AS distinct_grades
        """
    )
    op.execute(
        """
        UPDATE classes
        SET grade_id = school_grades.id
        FROM school_grades
        WHERE classes.school_id = school_grades.school_id
          AND classes.grade = school_grades.grade
        """
    )


def downgrade() -> None:
    op.drop_constraint('classes_grade_id_fkey', 'classes', type_='foreignkey')
    op.drop_column('classes', 'grade_id')
    op.drop_table('school_grades')
