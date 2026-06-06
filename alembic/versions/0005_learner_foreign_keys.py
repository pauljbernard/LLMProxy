"""Add learner foreign keys and indexes.

Revision ID: 0005_learner_foreign_keys
Revises: 0004_tc_quality_nullable
Create Date: 2026-06-06
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0005_learner_fks"
down_revision = "0004_tc_quality_nullable"
branch_labels = None
depends_on = None


def _foreign_key_names(bind, schema: str, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name, schema=schema) if fk.get("name")}


def _index_names(bind, schema: str, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name, schema=schema)}


def upgrade() -> None:
    if context.is_offline_mode():
        op.create_foreign_key(
            "fk_learner_dataset_version_source_import_id",
            "dataset_version",
            "dataset_import",
            ["source_import_id"],
            ["id"],
            source_schema="learner",
            referent_schema="learner",
        )
        op.create_foreign_key(
            "fk_learner_training_run_dataset_version_id",
            "training_run",
            "dataset_version",
            ["dataset_version_id"],
            ["id"],
            source_schema="learner",
            referent_schema="learner",
        )
        op.create_foreign_key(
            "fk_learner_evaluation_run_training_run_id",
            "evaluation_run",
            "training_run",
            ["training_run_id"],
            ["id"],
            source_schema="learner",
            referent_schema="learner",
        )
        op.create_index(
            "ix_learner_dataset_version_source_import_id",
            "dataset_version",
            ["source_import_id"],
            schema="learner",
        )
        op.create_index(
            "ix_learner_training_run_dataset_version_id",
            "training_run",
            ["dataset_version_id"],
            schema="learner",
        )
        op.create_index(
            "ix_learner_evaluation_run_training_run_id",
            "evaluation_run",
            ["training_run_id"],
            schema="learner",
        )
        return

    bind = op.get_bind()

    dataset_version_fks = _foreign_key_names(bind, "learner", "dataset_version")
    if "fk_learner_dataset_version_source_import_id" not in dataset_version_fks:
        op.create_foreign_key(
            "fk_learner_dataset_version_source_import_id",
            "dataset_version",
            "dataset_import",
            ["source_import_id"],
            ["id"],
            source_schema="learner",
            referent_schema="learner",
        )

    training_run_fks = _foreign_key_names(bind, "learner", "training_run")
    if "fk_learner_training_run_dataset_version_id" not in training_run_fks:
        op.create_foreign_key(
            "fk_learner_training_run_dataset_version_id",
            "training_run",
            "dataset_version",
            ["dataset_version_id"],
            ["id"],
            source_schema="learner",
            referent_schema="learner",
        )

    evaluation_run_fks = _foreign_key_names(bind, "learner", "evaluation_run")
    if "fk_learner_evaluation_run_training_run_id" not in evaluation_run_fks:
        op.create_foreign_key(
            "fk_learner_evaluation_run_training_run_id",
            "evaluation_run",
            "training_run",
            ["training_run_id"],
            ["id"],
            source_schema="learner",
            referent_schema="learner",
        )

    dataset_version_indexes = _index_names(bind, "learner", "dataset_version")
    if "ix_learner_dataset_version_source_import_id" not in dataset_version_indexes:
        op.create_index(
            "ix_learner_dataset_version_source_import_id",
            "dataset_version",
            ["source_import_id"],
            schema="learner",
        )

    training_run_indexes = _index_names(bind, "learner", "training_run")
    if "ix_learner_training_run_dataset_version_id" not in training_run_indexes:
        op.create_index(
            "ix_learner_training_run_dataset_version_id",
            "training_run",
            ["dataset_version_id"],
            schema="learner",
        )

    evaluation_run_indexes = _index_names(bind, "learner", "evaluation_run")
    if "ix_learner_evaluation_run_training_run_id" not in evaluation_run_indexes:
        op.create_index(
            "ix_learner_evaluation_run_training_run_id",
            "evaluation_run",
            ["training_run_id"],
            schema="learner",
        )


def downgrade() -> None:
    op.drop_index("ix_learner_evaluation_run_training_run_id", table_name="evaluation_run", schema="learner")
    op.drop_index("ix_learner_training_run_dataset_version_id", table_name="training_run", schema="learner")
    op.drop_index("ix_learner_dataset_version_source_import_id", table_name="dataset_version", schema="learner")
    op.drop_constraint("fk_learner_evaluation_run_training_run_id", "evaluation_run", schema="learner", type_="foreignkey")
    op.drop_constraint("fk_learner_training_run_dataset_version_id", "training_run", schema="learner", type_="foreignkey")
    op.drop_constraint("fk_learner_dataset_version_source_import_id", "dataset_version", schema="learner", type_="foreignkey")
