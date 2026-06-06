"""Add lifecycle columns to learner.evaluation_run.

Revision ID: 0007_eval_run_lifecycle
Revises: 0006_model_response_role
Create Date: 2026-06-06
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0007_eval_run_lifecycle"
down_revision = "0006_model_response_role"
branch_labels = None
depends_on = None


def _column_names(bind, schema: str, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name, schema=schema)}


def _index_names(bind, schema: str, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name, schema=schema)}


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            "evaluation_run",
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            schema="learner",
        )
        op.add_column(
            "evaluation_run",
            sa.Column("promotion_status", sa.String(), nullable=True),
            schema="learner",
        )
        op.alter_column("evaluation_run", "overall_score", existing_type=sa.Float(), nullable=True, schema="learner")
        op.alter_column(
            "evaluation_run",
            "quality_delta_vs_frontier",
            existing_type=sa.Float(),
            nullable=True,
            schema="learner",
        )
        op.alter_column(
            "evaluation_run",
            "value_per_dollar_gain_vs_frontier",
            existing_type=sa.Float(),
            nullable=True,
            schema="learner",
        )
        op.execute("update learner.evaluation_run set status = 'completed' where overall_score is not null")
        op.execute("update learner.evaluation_run set promotion_status = result_json->>'promotion_status'")
        op.create_index("ix_learner_evaluation_run_status", "evaluation_run", ["status"], schema="learner")
        op.create_index(
            "ix_learner_evaluation_run_promotion_status",
            "evaluation_run",
            ["promotion_status"],
            schema="learner",
        )
        return

    bind = op.get_bind()
    columns = _column_names(bind, "learner", "evaluation_run")
    if "status" not in columns:
        op.add_column(
            "evaluation_run",
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            schema="learner",
        )
    if "promotion_status" not in columns:
        op.add_column(
            "evaluation_run",
            sa.Column("promotion_status", sa.String(), nullable=True),
            schema="learner",
        )

    op.alter_column("evaluation_run", "overall_score", existing_type=sa.Float(), nullable=True, schema="learner")
    op.alter_column(
        "evaluation_run",
        "quality_delta_vs_frontier",
        existing_type=sa.Float(),
        nullable=True,
        schema="learner",
    )
    op.alter_column(
        "evaluation_run",
        "value_per_dollar_gain_vs_frontier",
        existing_type=sa.Float(),
        nullable=True,
        schema="learner",
    )
    op.execute(sa.text("update learner.evaluation_run set status = 'completed' where overall_score is not null"))
    op.execute(sa.text("update learner.evaluation_run set promotion_status = result_json->>'promotion_status'"))

    indexes = _index_names(bind, "learner", "evaluation_run")
    if "ix_learner_evaluation_run_status" not in indexes:
        op.create_index("ix_learner_evaluation_run_status", "evaluation_run", ["status"], schema="learner")
    if "ix_learner_evaluation_run_promotion_status" not in indexes:
        op.create_index(
            "ix_learner_evaluation_run_promotion_status",
            "evaluation_run",
            ["promotion_status"],
            schema="learner",
        )


def downgrade() -> None:
    op.drop_index("ix_learner_evaluation_run_promotion_status", table_name="evaluation_run", schema="learner")
    op.drop_index("ix_learner_evaluation_run_status", table_name="evaluation_run", schema="learner")
    op.alter_column(
        "evaluation_run",
        "value_per_dollar_gain_vs_frontier",
        existing_type=sa.Float(),
        nullable=False,
        schema="learner",
    )
    op.alter_column(
        "evaluation_run",
        "quality_delta_vs_frontier",
        existing_type=sa.Float(),
        nullable=False,
        schema="learner",
    )
    op.alter_column("evaluation_run", "overall_score", existing_type=sa.Float(), nullable=False, schema="learner")
    op.drop_column("evaluation_run", "promotion_status", schema="learner")
    op.drop_column("evaluation_run", "status", schema="learner")
