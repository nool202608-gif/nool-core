"""reporting

Revision ID: 5e91c3a7b2d4
Revises: 3d7a9f1e5c62
Create Date: 2026-08-28 14:00:00.000000

Saved report configurations (dimension/metrics/filters) and cross-school
sharing - see ReportConfiguration/ReportShare's model docstrings and
src/services/reporting.py's DIMENSIONS registry.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5e91c3a7b2d4'
down_revision: Union[str, None] = '3d7a9f1e5c62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'report_configurations',
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('dimension', sa.String(), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'report_shares',
        sa.Column('report_configuration_id', sa.UUID(), nullable=False),
        sa.Column('shared_by', sa.UUID(), nullable=False),
        sa.Column('shared_with_school_id', sa.UUID(), nullable=False),
        sa.Column('access_level', sa.String(), nullable=False, server_default='VIEW'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['report_configuration_id'], ['report_configurations.id'], ),
        sa.ForeignKeyConstraint(['shared_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['shared_with_school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('report_shares')
    op.drop_table('report_configurations')
