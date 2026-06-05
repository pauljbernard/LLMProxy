"""baseline schema"""

from alembic import op
import sqlalchemy as sa


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS proxy")
    op.execute("CREATE SCHEMA IF NOT EXISTS learner")
    op.create_table(
        "request_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("requested_model", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("task_type", sa.String(), nullable=True),
        sa.Column("request_json", sa.Text(), nullable=False),
        schema="proxy",
    )
    op.create_table(
        "routing_decision",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("request_log_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("selected_provider", sa.String(), nullable=False),
        sa.Column("selected_provider_family", sa.String(), nullable=False),
        sa.Column("selected_model", sa.String(), nullable=False),
        sa.Column("selected_mode", sa.String(), nullable=False),
        sa.Column("decision_rationale", sa.Text(), nullable=False),
        schema="proxy",
    )
    op.create_table(
        "training_candidate",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("request_log_id", sa.String(), nullable=False),
        sa.Column("routing_decision_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("approval_status", sa.String(), nullable=False),
        sa.Column("export_eligible", sa.Boolean(), nullable=False),
        sa.Column("selected_response", sa.Text(), nullable=False),
        schema="proxy",
    )
    op.create_table(
        "dataset_import",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_export_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        schema="learner",
    )


def downgrade() -> None:
    op.drop_table("dataset_import", schema="learner")
    op.drop_table("training_candidate", schema="proxy")
    op.drop_table("routing_decision", schema="proxy")
    op.drop_table("request_log", schema="proxy")
    op.execute("DROP SCHEMA IF EXISTS learner")
    op.execute("DROP SCHEMA IF EXISTS proxy")
