"""Add versioned prompt template storage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_prompt_templates"
down_revision = "0009_virtual_key_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_template",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("variables_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("model_override", sa.String(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_prompt_template_name_version"),
        schema="integration",
    )
    op.create_index(op.f("ix_integration_prompt_template_name"), "prompt_template", ["name"], unique=False, schema="integration")
    op.create_index(op.f("ix_integration_prompt_template_version"), "prompt_template", ["version"], unique=False, schema="integration")


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_prompt_template_version"), table_name="prompt_template", schema="integration")
    op.drop_index(op.f("ix_integration_prompt_template_name"), table_name="prompt_template", schema="integration")
    op.drop_table("prompt_template", schema="integration")
