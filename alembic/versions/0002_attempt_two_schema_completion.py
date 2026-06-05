"""attempt two schema completion

Bring older 0001-baseline databases forward to the current schema without
requiring destructive volume resets.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_schema_completion"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _create_table_if_missing(schema: str, table: str, *columns: sa.Column, foreign_keys: tuple[sa.ForeignKeyConstraint, ...] = ()) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names(schema=schema))
    if table in existing_tables:
        return
    op.create_table(table, *columns, *foreign_keys, schema=schema)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], *, schema: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name, schema=schema)}
    if index_name in existing_indexes:
        return
    op.create_index(index_name, table_name, columns, schema=schema)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS proxy")
    op.execute("CREATE SCHEMA IF NOT EXISTS learner")
    op.execute("CREATE SCHEMA IF NOT EXISTS integration")

    _create_table_if_missing(
        "proxy",
        "judge_critique",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("request_log_id", sa.String(), nullable=False),
        sa.Column("routing_decision_id", sa.String(), nullable=False),
        sa.Column("judge_provider", sa.String(), nullable=False),
        sa.Column("judge_model", sa.String(), nullable=False),
        sa.Column("selected_provider", sa.String(), nullable=False),
        sa.Column("selected_model", sa.String(), nullable=False),
        sa.Column("selected_response_id", sa.String(), nullable=False),
        sa.Column("critique_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("synthesized_response", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        foreign_keys=(
            sa.ForeignKeyConstraint(["request_log_id"], ["proxy.request_log.id"]),
            sa.ForeignKeyConstraint(["routing_decision_id"], ["proxy.routing_decision.id"]),
        ),
    )
    _create_index_if_missing("ix_proxy_judge_critique_request_log_id", "judge_critique", ["request_log_id"], schema="proxy")

    _create_table_if_missing(
        "proxy",
        "dataset_export",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("dataset_export_id", sa.String(), nullable=False, unique=True),
        sa.Column("manifest_path", sa.String(), nullable=False),
        sa.Column("data_path", sa.String(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    _create_table_if_missing(
        "learner",
        "dataset_version",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("version_name", sa.String(), nullable=False),
        sa.Column("source_import_id", sa.String(), nullable=False),
        sa.Column("train_path", sa.String(), nullable=False),
        sa.Column("validation_path", sa.String(), nullable=False),
        sa.Column("test_path", sa.String(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    _create_table_if_missing(
        "learner",
        "training_run",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_version_id", sa.String(), nullable=False),
        sa.Column("base_model", sa.String(), nullable=False),
        sa.Column("training_mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("training_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_path", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    _create_table_if_missing(
        "learner",
        "evaluation_run",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("training_run_id", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("frontier_baseline_name", sa.String(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("quality_delta_vs_frontier", sa.Float(), nullable=False),
        sa.Column("value_per_dollar_gain_vs_frontier", sa.Float(), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    _create_table_if_missing(
        "integration",
        "integration_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    _create_table_if_missing(
        "integration",
        "routing_policy_version",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    _create_table_if_missing(
        "integration",
        "model_performance_sample",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("model_alias", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("request_log_id", sa.String(), nullable=False),
        sa.Column("route_type", sa.String(), nullable=False),
        sa.Column("cost_estimate", sa.Float(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("successful", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    _create_table_if_missing(
        "integration",
        "job_queue",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    _create_index_if_missing("ix_integration_job_queue_job_type", "job_queue", ["job_type"], schema="integration")
    _create_index_if_missing("ix_integration_job_queue_status", "job_queue", ["status"], schema="integration")
    _create_index_if_missing("ix_integration_job_queue_available_at", "job_queue", ["available_at"], schema="integration")


def downgrade() -> None:
    op.drop_index("ix_integration_job_queue_available_at", table_name="job_queue", schema="integration")
    op.drop_index("ix_integration_job_queue_status", table_name="job_queue", schema="integration")
    op.drop_index("ix_integration_job_queue_job_type", table_name="job_queue", schema="integration")
    op.drop_table("job_queue", schema="integration")
    op.drop_table("model_performance_sample", schema="integration")
    op.drop_table("routing_policy_version", schema="integration")
    op.drop_table("integration_event", schema="integration")
    op.drop_table("evaluation_run", schema="learner")
    op.drop_table("training_run", schema="learner")
    op.drop_table("dataset_version", schema="learner")
    op.drop_table("dataset_export", schema="proxy")
    op.drop_index("ix_proxy_judge_critique_request_log_id", table_name="judge_critique", schema="proxy")
    op.drop_table("judge_critique", schema="proxy")
