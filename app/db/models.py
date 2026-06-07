"""Canonical first-pass database models."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RequestLog(Base):
    __tablename__ = "request_log"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    external_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    requested_model: Mapped[str] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    task_type: Mapped[str | None] = mapped_column(String, nullable=True)
    complexity: Mapped[str] = mapped_column(String, default="medium")
    privacy_level: Mapped[str] = mapped_column(String, default="standard")
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoutingDecisionRecord(Base):
    __tablename__ = "routing_decision"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_log_id: Mapped[str] = mapped_column(ForeignKey("proxy.request_log.id"), index=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    policy_version: Mapped[str] = mapped_column(String)
    selected_provider: Mapped[str] = mapped_column(String)
    selected_provider_family: Mapped[str] = mapped_column(String)
    selected_model: Mapped[str] = mapped_column(String)
    selected_mode: Mapped[str] = mapped_column(String)
    decision_rationale: Mapped[str] = mapped_column(Text)
    predicted_cost_class: Mapped[str] = mapped_column(String)
    predicted_latency_class: Mapped[str] = mapped_column(String)
    ranked_alternatives_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    fallback_chain_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelResponse(Base):
    __tablename__ = "model_response"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_log_id: Mapped[str] = mapped_column(ForeignKey("proxy.request_log.id"), index=True)
    provider: Mapped[str] = mapped_column(String)
    provider_family: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    finish_reason: Mapped[str] = mapped_column(String, default="stop")
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response_role: Mapped[str] = mapped_column(String, default="teacher_candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JudgeCritique(Base):
    __tablename__ = "judge_critique"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_log_id: Mapped[str] = mapped_column(ForeignKey("proxy.request_log.id"), index=True)
    routing_decision_id: Mapped[str] = mapped_column(ForeignKey("proxy.routing_decision.id"), index=True)
    judge_provider: Mapped[str] = mapped_column(String)
    judge_model: Mapped[str] = mapped_column(String)
    selected_provider: Mapped[str] = mapped_column(String)
    selected_model: Mapped[str] = mapped_column(String)
    selected_response_id: Mapped[str] = mapped_column(String)
    critique_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    synthesized_response: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingCandidate(Base):
    __tablename__ = "training_candidate"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_log_id: Mapped[str] = mapped_column(ForeignKey("proxy.request_log.id"), index=True)
    routing_decision_id: Mapped[str] = mapped_column(ForeignKey("proxy.routing_decision.id"), index=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    domain: Mapped[str] = mapped_column(String)
    task_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    approval_status: Mapped[str] = mapped_column(String)
    export_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_response: Mapped[str] = mapped_column(Text)
    messages_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    validation_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class DatasetExport(Base):
    __tablename__ = "dataset_export"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    domain: Mapped[str] = mapped_column(String)
    dataset_export_id: Mapped[str] = mapped_column(String, unique=True)
    manifest_path: Mapped[str] = mapped_column(String)
    data_path: Mapped[str] = mapped_column(String)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String)
    schema_version: Mapped[str] = mapped_column(String, default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetImport(Base):
    __tablename__ = "dataset_import"
    __table_args__ = {"schema": "learner"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_export_id: Mapped[str] = mapped_column(String)
    manifest_path: Mapped[str | None] = mapped_column(String, nullable=True)
    data_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    quarantined_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetVersion(Base):
    __tablename__ = "dataset_version"
    __table_args__ = {"schema": "learner"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    domain: Mapped[str] = mapped_column(String)
    version_name: Mapped[str] = mapped_column(String)
    source_import_id: Mapped[str] = mapped_column(ForeignKey("learner.dataset_import.id"), index=True)
    train_path: Mapped[str] = mapped_column(String)
    validation_path: Mapped[str] = mapped_column(String)
    test_path: Mapped[str] = mapped_column(String)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingRun(Base):
    __tablename__ = "training_run"
    __table_args__ = {"schema": "learner"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("learner.dataset_version.id"), index=True)
    base_model: Mapped[str] = mapped_column(String)
    training_mode: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    training_config_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    artifact_path: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationRun(Base):
    __tablename__ = "evaluation_run"
    __table_args__ = {"schema": "learner"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    training_run_id: Mapped[str] = mapped_column(ForeignKey("learner.training_run.id"), index=True)
    domain: Mapped[str] = mapped_column(String)
    frontier_baseline_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    promotion_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_delta_vs_frontier: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_per_dollar_gain_vs_frontier: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrationEvent(Base):
    __tablename__ = "integration_event"
    __table_args__ = {"schema": "integration"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(String)
    event_type: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VirtualAPIKey(Base):
    __tablename__ = "virtual_api_key"
    __table_args__ = {"schema": "integration"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    key_prefix: Mapped[str] = mapped_column(String, index=True)
    key_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    role: Mapped[str] = mapped_column(String, default="api")
    status: Mapped[str] = mapped_column(String, default="active", index=True)
    models_allowed_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spend_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    max_budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    budget_reset_period: Mapped[str | None] = mapped_column(String, nullable=True)
    budget_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rate_limit_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requests_used_current_window: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used_current_window: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoutingPolicyVersion(Base):
    __tablename__ = "routing_policy_version"
    __table_args__ = {"schema": "integration"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    policy_version: Mapped[str] = mapped_column(String)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptTemplate(Base):
    __tablename__ = "prompt_template"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_template_name_version"),
        {"schema": "integration"},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_text: Mapped[str] = mapped_column(Text)
    variables_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    model_override: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelPerformanceSample(Base):
    __tablename__ = "model_performance_sample"
    __table_args__ = {"schema": "integration"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    model_alias: Mapped[str] = mapped_column(String, index=True)
    domain: Mapped[str] = mapped_column(String, index=True)
    request_log_id: Mapped[str] = mapped_column(String)
    route_type: Mapped[str] = mapped_column(String, index=True)
    cost_estimate: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    successful: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobQueueRecord(Base):
    __tablename__ = "job_queue"
    __table_args__ = {"schema": "integration"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_type: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
