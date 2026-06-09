"""Persist raw/effective request separation for prompt lineage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_prompt_req_lineage"
down_revision = "0011_routing_topology_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "request_log",
        sa.Column("effective_request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="proxy",
    )
    op.execute("UPDATE proxy.request_log SET effective_request_json = request_json WHERE effective_request_json IS NULL")


def downgrade() -> None:
    op.drop_column("request_log", "effective_request_json", schema="proxy")
