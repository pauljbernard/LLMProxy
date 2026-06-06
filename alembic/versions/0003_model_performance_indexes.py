"""model performance sample indexes and nullable quality score"""

from alembic import context, op
import sqlalchemy as sa


revision = "0003_model_perf_indexes"
down_revision = "0002_schema_completion"
branch_labels = None
depends_on = None


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], *, schema: str) -> None:
    if context.is_offline_mode():
        op.create_index(index_name, table_name, columns, schema=schema)
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name, schema=schema)}
    if index_name in existing_indexes:
        return
    op.create_index(index_name, table_name, columns, schema=schema)


def upgrade() -> None:
    op.alter_column(
        "model_performance_sample",
        "quality_score",
        schema="integration",
        existing_type=sa.Float(),
        nullable=True,
    )
    _create_index_if_missing(
        "ix_integration_model_performance_sample_model_alias",
        "model_performance_sample",
        ["model_alias"],
        schema="integration",
    )
    _create_index_if_missing(
        "ix_integration_model_performance_sample_domain",
        "model_performance_sample",
        ["domain"],
        schema="integration",
    )
    _create_index_if_missing(
        "ix_integration_model_performance_sample_route_type",
        "model_performance_sample",
        ["route_type"],
        schema="integration",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_model_performance_sample_route_type",
        table_name="model_performance_sample",
        schema="integration",
    )
    op.drop_index(
        "ix_integration_model_performance_sample_domain",
        table_name="model_performance_sample",
        schema="integration",
    )
    op.drop_index(
        "ix_integration_model_performance_sample_model_alias",
        table_name="model_performance_sample",
        schema="integration",
    )
    op.alter_column(
        "model_performance_sample",
        "quality_score",
        schema="integration",
        existing_type=sa.Float(),
        nullable=False,
    )
