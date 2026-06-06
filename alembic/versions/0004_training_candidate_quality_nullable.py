"""Make training candidate quality nullable.

Revision ID: 0004_training_candidate_quality_nullable
Revises: 0003_model_perf_indexes
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_tc_quality_nullable"
down_revision = "0003_model_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "training_candidate",
        "quality_score",
        schema="proxy",
        existing_type=sa.Float(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "training_candidate",
        "quality_score",
        schema="proxy",
        existing_type=sa.Float(),
        nullable=False,
    )
