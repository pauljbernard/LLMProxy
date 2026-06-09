"""Add prompt template lifecycle status."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_prompt_tpl_status"
down_revision = "0012_prompt_req_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt_template",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        schema="integration",
    )
    op.create_index(
        "ix_integration_prompt_template_status",
        "prompt_template",
        ["status"],
        unique=False,
        schema="integration",
    )


def downgrade() -> None:
    op.drop_index("ix_integration_prompt_template_status", table_name="prompt_template", schema="integration")
    op.drop_column("prompt_template", "status", schema="integration")
