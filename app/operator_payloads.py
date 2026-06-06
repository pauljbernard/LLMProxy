"""Shared payload builders for operator-facing surfaces."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.db.models import (
    DatasetExport,
    DatasetImport,
    DatasetVersion,
    EvaluationRun,
    IntegrationEvent,
    JobQueueRecord,
    JudgeCritique,
    ModelPerformanceSample,
    ModelResponse,
    RequestLog,
    RoutingDecisionRecord,
    TrainingCandidate,
    TrainingRun,
)


def settings_payload(settings: Settings) -> dict[str, Any]:
    return {
        "llmproxy_env": settings.llmproxy_env,
        "llmproxy_log_level": settings.llmproxy_log_level,
        "llmproxy_api_host": settings.llmproxy_api_host,
        "llmproxy_api_port": settings.llmproxy_api_port,
        "llmproxy_database_url": settings.llmproxy_database_url,
        "llmproxy_redis_url": settings.llmproxy_redis_url,
        "llmproxy_default_route_model": settings.llmproxy_default_route_model,
        "llmproxy_openai_model": settings.llmproxy_openai_model,
        "llmproxy_anthropic_model": settings.llmproxy_anthropic_model,
        "llmproxy_google_model": settings.llmproxy_google_model,
        "llmproxy_xai_model": settings.llmproxy_xai_model,
        "llmproxy_bedrock_model": settings.llmproxy_bedrock_model,
        "llmproxy_azure_openai_model": settings.llmproxy_azure_openai_model,
        "llmproxy_ollama_model": settings.llmproxy_ollama_model,
        "llmproxy_exports_path": settings.llmproxy_exports_path,
        "llmproxy_datasets_path": settings.llmproxy_datasets_path,
        "llmproxy_models_path": settings.llmproxy_models_path,
        "llmproxy_checkpoints_path": settings.llmproxy_checkpoints_path,
        "llmproxy_reports_path": settings.llmproxy_reports_path,
        "llmproxy_logs_path": settings.llmproxy_logs_path,
        "llmproxy_auto_deploy_approved_evaluations": settings.llmproxy_auto_deploy_approved_evaluations,
        "llmproxy_auto_deploy_deployment_mode": settings.llmproxy_auto_deploy_deployment_mode,
        "provider_configuration": {
            "openai": bool(settings.llmproxy_openai_api_key),
            "anthropic": bool(settings.llmproxy_anthropic_api_key),
            "google": bool(settings.llmproxy_google_api_key),
            "xai": bool(settings.llmproxy_xai_api_key),
            "azure_openai": bool(settings.llmproxy_azure_openai_api_key and settings.llmproxy_azure_openai_endpoint),
            "bedrock": bool(
                settings.llmproxy_bedrock_region
                and settings.llmproxy_bedrock_access_key_id
                and settings.llmproxy_bedrock_secret_access_key
            ),
            "ollama": bool(settings.llmproxy_ollama_base_url),
        },
    }


def request_summary_payload(request: RequestLog) -> dict[str, Any]:
    return {
        "id": request.id,
        "session_id": request.session_id,
        "requested_model": request.requested_model,
        "domain": request.domain,
        "task_type": request.task_type,
        "complexity": request.complexity,
        "privacy_level": request.privacy_level,
        "created_at": request.created_at,
    }


def routing_decision_payload(item: RoutingDecisionRecord) -> dict[str, Any]:
    return {
        "id": item.id,
        "policy_version": item.policy_version,
        "selected_provider": item.selected_provider,
        "selected_provider_family": item.selected_provider_family,
        "selected_model": item.selected_model,
        "selected_mode": item.selected_mode,
        "decision_rationale": item.decision_rationale,
        "predicted_cost_class": item.predicted_cost_class,
        "predicted_latency_class": item.predicted_latency_class,
        "ranked_alternatives_json": item.ranked_alternatives_json,
        "fallback_chain_json": item.fallback_chain_json,
        "created_at": item.created_at,
    }


def model_response_payload(item: ModelResponse) -> dict[str, Any]:
    return {
        "id": item.id,
        "provider": item.provider,
        "provider_family": item.provider_family,
        "model": item.model,
        "latency_ms": item.latency_ms,
        "input_tokens": item.input_tokens,
        "output_tokens": item.output_tokens,
        "cost_estimate": item.cost_estimate,
        "finish_reason": item.finish_reason,
        "response_role": item.response_role,
        "response_json": item.response_json,
        "created_at": item.created_at,
    }


def judge_critique_payload(item: JudgeCritique) -> dict[str, Any]:
    return {
        "id": item.id,
        "judge_provider": item.judge_provider,
        "judge_model": item.judge_model,
        "selected_provider": item.selected_provider,
        "selected_model": item.selected_model,
        "selected_response_id": item.selected_response_id,
        "critique_json": item.critique_json,
        "synthesized_response": item.synthesized_response,
        "created_at": item.created_at,
    }


def training_candidate_payload(item: TrainingCandidate) -> dict[str, Any]:
    return {
        "id": item.id,
        "domain": item.domain,
        "task_type": item.task_type,
        "status": item.status,
        "approval_status": item.approval_status,
        "quality_score": item.quality_score,
        "export_eligible": item.export_eligible,
        "selected_response": item.selected_response,
        "metadata": item.metadata_json,
        "created_at": item.created_at,
    }


def performance_sample_payload(item: ModelPerformanceSample) -> dict[str, Any]:
    return {
        "id": item.id,
        "model_alias": item.model_alias,
        "domain": item.domain,
        "route_type": item.route_type,
        "cost_estimate": item.cost_estimate,
        "quality_score": item.quality_score,
        "successful": item.successful,
        "created_at": item.created_at,
    }


def request_detail_payload(
    *,
    request: RequestLog,
    routing_decisions: list[RoutingDecisionRecord],
    model_responses: list[ModelResponse],
    judge_critiques: list[JudgeCritique],
    candidates: list[TrainingCandidate],
    performance_samples: list[ModelPerformanceSample],
) -> dict[str, Any]:
    return {
        "request": {**request_summary_payload(request), "request_json": request.request_json},
        "routing_decisions": [routing_decision_payload(item) for item in routing_decisions],
        "model_responses": [model_response_payload(item) for item in model_responses],
        "judge_critiques": [judge_critique_payload(item) for item in judge_critiques],
        "training_candidates": [training_candidate_payload(item) for item in candidates],
        "performance_samples": [performance_sample_payload(item) for item in performance_samples],
    }


def dataset_export_payload(item: DatasetExport) -> dict[str, Any]:
    return {
        "id": item.id,
        "domain": item.domain,
        "dataset_export_id": item.dataset_export_id,
        "manifest_path": item.manifest_path,
        "data_path": item.data_path,
        "record_count": item.record_count,
        "schema_version": item.schema_version,
        "created_at": item.created_at,
    }


def dataset_import_payload(item: DatasetImport) -> dict[str, Any]:
    return {
        "id": item.id,
        "dataset_export_id": item.dataset_export_id,
        "manifest_path": item.manifest_path,
        "data_path": item.data_path,
        "status": item.status,
        "record_count": item.record_count,
        "quarantined_count": item.quarantined_count,
        "created_at": item.created_at,
    }


def dataset_version_payload(item: DatasetVersion) -> dict[str, Any]:
    return {
        "id": item.id,
        "domain": item.domain,
        "version_name": item.version_name,
        "source_import_id": item.source_import_id,
        "train_path": item.train_path,
        "validation_path": item.validation_path,
        "test_path": item.test_path,
        "record_count": item.record_count,
        "created_at": item.created_at,
    }


def training_run_payload(run: TrainingRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "dataset_version_id": run.dataset_version_id,
        "base_model": run.base_model,
        "training_mode": run.training_mode,
        "status": run.status,
        "training_config_json": run.training_config_json,
        "metrics_json": run.metrics_json,
        "artifact_path": run.artifact_path,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def evaluation_run_payload(run: EvaluationRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "training_run_id": run.training_run_id,
        "domain": run.domain,
        "frontier_baseline_name": run.frontier_baseline_name,
        "status": run.status,
        "promotion_status": run.promotion_status,
        "overall_score": run.overall_score,
        "quality_delta_vs_frontier": run.quality_delta_vs_frontier,
        "value_per_dollar_gain_vs_frontier": run.value_per_dollar_gain_vs_frontier,
        "result_json": run.result_json,
        "created_at": run.created_at,
    }


def job_payload(job: JobQueueRecord) -> dict[str, Any]:
    return {
        "id": getattr(job, "id", None),
        "job_type": getattr(job, "job_type", None),
        "status": getattr(job, "status", None),
        "payload": getattr(job, "payload_json", None),
        "attempts": getattr(job, "attempts", None),
        "max_attempts": getattr(job, "max_attempts", None),
        "available_at": getattr(job, "available_at", None),
        "claimed_at": getattr(job, "claimed_at", None),
        "completed_at": getattr(job, "completed_at", None),
        "last_error": getattr(job, "last_error", None),
        "created_at": getattr(job, "created_at", None),
    }


def event_payload(event: IntegrationEvent) -> dict[str, Any]:
    return {
        "id": getattr(event, "id", None),
        "event_id": getattr(event, "event_id", None),
        "event_type": getattr(event, "event_type", None),
        "source": getattr(event, "source", None),
        "payload_json": getattr(event, "payload_json", None),
        "occurred_at": getattr(event, "occurred_at", None),
        "processed_at": getattr(event, "processed_at", None),
    }
