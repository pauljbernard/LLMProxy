"""Add missing response_role column to proxy.model_response.

Revision ID: 0006_model_response_role
Revises: 0005_learner_fks
Create Date: 2026-06-06
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0006_model_response_role"
down_revision = "0005_learner_fks"
branch_labels = None
depends_on = None


def _column_names(bind, schema: str, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name, schema=schema)}


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            "model_response",
            sa.Column("response_role", sa.String(), nullable=False, server_default="teacher_candidate"),
            schema="proxy",
        )
        return

    bind = op.get_bind()
    if "response_role" in _column_names(bind, "proxy", "model_response"):
        return

    op.add_column(
        "model_response",
        sa.Column("response_role", sa.String(), nullable=False, server_default="teacher_candidate"),
        schema="proxy",
    )


def downgrade() -> None:
    op.drop_column("model_response", "response_role", schema="proxy")
