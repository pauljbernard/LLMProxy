"""Add virtual API key table for multi-tenant auth scaffolding.

Revision ID: 0008_virtual_api_keys
Revises: 0007_eval_run_lifecycle
Create Date: 2026-06-06
"""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_virtual_api_keys"
down_revision = "0007_eval_run_lifecycle"
branch_labels = None
depends_on = None


def _table_names(bind, schema: str) -> set[str]:
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names(schema=schema))


def _index_names(bind, schema: str, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name, schema=schema)}


def upgrade() -> None:
    if context.is_offline_mode():
        op.create_table(
            "virtual_api_key",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("key_prefix", sa.String(), nullable=False),
            sa.Column("key_hash", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("owner_id", sa.String(), nullable=True),
            sa.Column("role", sa.String(), nullable=False, server_default="api"),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("models_allowed_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("spend_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
            sa.Column("max_budget_usd", sa.Numeric(12, 6), nullable=True),
            sa.Column("budget_reset_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id"),
            schema="integration",
        )
        op.create_index("ix_integration_virtual_api_key_key_prefix", "virtual_api_key", ["key_prefix"], unique=False, schema="integration")
        op.create_index("ix_integration_virtual_api_key_key_hash", "virtual_api_key", ["key_hash"], unique=True, schema="integration")
        op.create_index("ix_integration_virtual_api_key_owner_id", "virtual_api_key", ["owner_id"], unique=False, schema="integration")
        op.create_index("ix_integration_virtual_api_key_status", "virtual_api_key", ["status"], unique=False, schema="integration")
        return

    bind = op.get_bind()
    if "virtual_api_key" not in _table_names(bind, "integration"):
        op.create_table(
            "virtual_api_key",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("key_prefix", sa.String(), nullable=False),
            sa.Column("key_hash", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("owner_id", sa.String(), nullable=True),
            sa.Column("role", sa.String(), nullable=False, server_default="api"),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("models_allowed_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("spend_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
            sa.Column("max_budget_usd", sa.Numeric(12, 6), nullable=True),
            sa.Column("budget_reset_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id"),
            schema="integration",
        )
    indexes = _index_names(bind, "integration", "virtual_api_key")
    if "ix_integration_virtual_api_key_key_prefix" not in indexes:
        op.create_index("ix_integration_virtual_api_key_key_prefix", "virtual_api_key", ["key_prefix"], unique=False, schema="integration")
    if "ix_integration_virtual_api_key_key_hash" not in indexes:
        op.create_index("ix_integration_virtual_api_key_key_hash", "virtual_api_key", ["key_hash"], unique=True, schema="integration")
    if "ix_integration_virtual_api_key_owner_id" not in indexes:
        op.create_index("ix_integration_virtual_api_key_owner_id", "virtual_api_key", ["owner_id"], unique=False, schema="integration")
    if "ix_integration_virtual_api_key_status" not in indexes:
        op.create_index("ix_integration_virtual_api_key_status", "virtual_api_key", ["status"], unique=False, schema="integration")


def downgrade() -> None:
    op.drop_index("ix_integration_virtual_api_key_status", table_name="virtual_api_key", schema="integration")
    op.drop_index("ix_integration_virtual_api_key_owner_id", table_name="virtual_api_key", schema="integration")
    op.drop_index("ix_integration_virtual_api_key_key_hash", table_name="virtual_api_key", schema="integration")
    op.drop_index("ix_integration_virtual_api_key_key_prefix", table_name="virtual_api_key", schema="integration")
    op.drop_table("virtual_api_key", schema="integration")
