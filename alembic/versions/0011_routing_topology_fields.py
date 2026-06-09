"""Add routing topology fields to routing decisions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_routing_topology_fields"
down_revision = "0010_prompt_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("routing_decision", sa.Column("selected_entry_id", sa.String(), nullable=True), schema="proxy")
    op.add_column("routing_decision", sa.Column("selected_pool_id", sa.String(), nullable=True), schema="proxy")
    op.add_column("routing_decision", sa.Column("selected_node_id", sa.String(), nullable=True), schema="proxy")
    op.add_column("routing_decision", sa.Column("selected_node_role", sa.String(), nullable=True), schema="proxy")
    op.add_column(
        "routing_decision",
        sa.Column("selected_node_labels_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        schema="proxy",
    )
    op.add_column("routing_decision", sa.Column("selected_capacity_class", sa.String(), nullable=True), schema="proxy")
    op.add_column("routing_decision", sa.Column("selected_balancing_strategy", sa.String(), nullable=True), schema="proxy")
    op.add_column("routing_decision", sa.Column("selected_affinity_key", sa.String(), nullable=True), schema="proxy")
    op.create_index(op.f("ix_proxy_routing_decision_selected_entry_id"), "routing_decision", ["selected_entry_id"], unique=False, schema="proxy")
    op.create_index(op.f("ix_proxy_routing_decision_selected_pool_id"), "routing_decision", ["selected_pool_id"], unique=False, schema="proxy")
    op.create_index(op.f("ix_proxy_routing_decision_selected_node_id"), "routing_decision", ["selected_node_id"], unique=False, schema="proxy")


def downgrade() -> None:
    op.drop_index(op.f("ix_proxy_routing_decision_selected_node_id"), table_name="routing_decision", schema="proxy")
    op.drop_index(op.f("ix_proxy_routing_decision_selected_pool_id"), table_name="routing_decision", schema="proxy")
    op.drop_index(op.f("ix_proxy_routing_decision_selected_entry_id"), table_name="routing_decision", schema="proxy")
    op.drop_column("routing_decision", "selected_affinity_key", schema="proxy")
    op.drop_column("routing_decision", "selected_balancing_strategy", schema="proxy")
    op.drop_column("routing_decision", "selected_capacity_class", schema="proxy")
    op.drop_column("routing_decision", "selected_node_labels_json", schema="proxy")
    op.drop_column("routing_decision", "selected_node_role", schema="proxy")
    op.drop_column("routing_decision", "selected_node_id", schema="proxy")
    op.drop_column("routing_decision", "selected_pool_id", schema="proxy")
    op.drop_column("routing_decision", "selected_entry_id", schema="proxy")
