"""baseline schema"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS proxy")
    op.execute("CREATE SCHEMA IF NOT EXISTS learner")
    op.execute("CREATE SCHEMA IF NOT EXISTS integration")

    op.create_table(
        "request_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("external_request_id", sa.String(), nullable=True),
        sa.Column("requested_model", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("task_type", sa.String(), nullable=True),
        sa.Column("complexity", sa.String(), nullable=False, server_default="medium"),
        sa.Column("privacy_level", sa.String(), nullable=False, server_default="standard"),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="proxy",
    )
    op.create_index("ix_proxy_request_log_session_id", "request_log", ["session_id"], schema="proxy")

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
        sa.Column("predicted_cost_class", sa.String(), nullable=False),
        sa.Column("predicted_latency_class", sa.String(), nullable=False),
        sa.Column("ranked_alternatives_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_chain_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_log_id"], ["proxy.request_log.id"]),
        schema="proxy",
    )
    op.create_index("ix_proxy_routing_decision_request_log_id", "routing_decision", ["request_log_id"], schema="proxy")
    op.create_index("ix_proxy_routing_decision_session_id", "routing_decision", ["session_id"], schema="proxy")

    op.create_table(
        "model_response",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("request_log_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_family", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_estimate", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("finish_reason", sa.String(), nullable=False, server_default="stop"),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_role", sa.String(), nullable=False, server_default="teacher_candidate"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_log_id"], ["proxy.request_log.id"]),
        schema="proxy",
    )
    op.create_index("ix_proxy_model_response_request_log_id", "model_response", ["request_log_id"], schema="proxy")

    op.create_table(
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
        sa.ForeignKeyConstraint(["request_log_id"], ["proxy.request_log.id"]),
        sa.ForeignKeyConstraint(["routing_decision_id"], ["proxy.routing_decision.id"]),
        schema="proxy",
    )
    op.create_index("ix_proxy_judge_critique_request_log_id", "judge_critique", ["request_log_id"], schema="proxy")

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
        sa.Column("export_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("selected_response", sa.Text(), nullable=False),
        sa.Column("messages_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("validation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_log_id"], ["proxy.request_log.id"]),
        sa.ForeignKeyConstraint(["routing_decision_id"], ["proxy.routing_decision.id"]),
        schema="proxy",
    )

    op.create_table(
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
        schema="proxy",
    )

    op.create_table(
        "dataset_import",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_export_id", sa.String(), nullable=False),
        sa.Column("manifest_path", sa.String(), nullable=True),
        sa.Column("data_path", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quarantined_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="learner",
    )

    op.create_table(
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
        schema="learner",
    )

    op.create_table(
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
        schema="learner",
    )

    op.create_table(
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
        schema="learner",
    )

    op.create_table(
        "integration_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        schema="integration",
    )

    op.create_table(
        "routing_policy_version",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="integration",
    )

    op.create_table(
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
        schema="integration",
    )

    op.create_table(
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
        schema="integration",
    )
    op.create_index("ix_integration_job_queue_job_type", "job_queue", ["job_type"], schema="integration")
    op.create_index("ix_integration_job_queue_status", "job_queue", ["status"], schema="integration")
    op.create_index("ix_integration_job_queue_available_at", "job_queue", ["available_at"], schema="integration")


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
    op.drop_table("dataset_import", schema="learner")
    op.drop_table("dataset_export", schema="proxy")
    op.drop_table("training_candidate", schema="proxy")
    op.drop_index("ix_proxy_judge_critique_request_log_id", table_name="judge_critique", schema="proxy")
    op.drop_table("judge_critique", schema="proxy")
    op.drop_index("ix_proxy_model_response_request_log_id", table_name="model_response", schema="proxy")
    op.drop_table("model_response", schema="proxy")
    op.drop_index("ix_proxy_routing_decision_session_id", table_name="routing_decision", schema="proxy")
    op.drop_index("ix_proxy_routing_decision_request_log_id", table_name="routing_decision", schema="proxy")
    op.drop_table("routing_decision", schema="proxy")
    op.drop_index("ix_proxy_request_log_session_id", table_name="request_log", schema="proxy")
    op.drop_table("request_log", schema="proxy")
    op.execute("DROP SCHEMA IF EXISTS integration")
    op.execute("DROP SCHEMA IF EXISTS learner")
    op.execute("DROP SCHEMA IF EXISTS proxy")
