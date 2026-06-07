"""Add virtual key rate limits and recurring budget reset fields."""

from alembic import op
import sqlalchemy as sa


revision = "0009_virtual_key_limits"
down_revision = "0008_virtual_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for schema in ("integration",):
        op.add_column("virtual_api_key", sa.Column("rpm_limit", sa.Integer(), nullable=True), schema=schema)
        op.add_column("virtual_api_key", sa.Column("tpm_limit", sa.Integer(), nullable=True), schema=schema)
        op.add_column("virtual_api_key", sa.Column("budget_reset_period", sa.String(), nullable=True), schema=schema)
        op.add_column("virtual_api_key", sa.Column("rate_limit_window_started_at", sa.DateTime(timezone=True), nullable=True), schema=schema)
        op.add_column(
            "virtual_api_key",
            sa.Column("requests_used_current_window", sa.Integer(), nullable=False, server_default="0"),
            schema=schema,
        )
        op.add_column(
            "virtual_api_key",
            sa.Column("tokens_used_current_window", sa.Integer(), nullable=False, server_default="0"),
            schema=schema,
        )


def downgrade() -> None:
    for schema in ("integration",):
        op.drop_column("virtual_api_key", "tokens_used_current_window", schema=schema)
        op.drop_column("virtual_api_key", "requests_used_current_window", schema=schema)
        op.drop_column("virtual_api_key", "rate_limit_window_started_at", schema=schema)
        op.drop_column("virtual_api_key", "budget_reset_period", schema=schema)
        op.drop_column("virtual_api_key", "tpm_limit", schema=schema)
        op.drop_column("virtual_api_key", "rpm_limit", schema=schema)
