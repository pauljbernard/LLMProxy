"""Evaluation runner."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import DatasetVersion, EvaluationRun, TrainingRun
from app.evaluation.benchmark_loader import load_benchmarks
from app.evaluation.economics import compare_value_per_dollar
from app.evaluation.gates import evaluate_promotion_gate
from app.integration.events import emit_event
from app.proxy.recorder import generate_prefixed_id
from app.registry.artifact_store import store_artifact
from app.services.command_backend import run_json_command
from app.schemas.evaluation import EvaluationResult, EvaluationRunRequest

LOCAL_RUNTIME_COST_BY_MODE = {
    "lora": 0.02,
    "qlora": 0.025,
}


def frontier_baseline_score(domain: str, settings: Settings) -> float:
    return float(settings.llmproxy_frontier_baseline_scores.get(domain, 0.90))


def frontier_baseline_cost(domain: str, settings: Settings) -> float:
    return float(settings.llmproxy_frontier_baseline_costs.get(domain, 0.12))


def frontier_baseline_name_for_domain(domain: str, settings: Settings) -> str:
    return settings.llmproxy_frontier_baseline_names.get(domain, settings.llmproxy_anthropic_model)


def list_evaluation_runs(session: Session) -> list[EvaluationRun]:
    return list(session.execute(select(EvaluationRun).order_by(EvaluationRun.created_at.desc())).scalars())


def run_evaluation(
    session: Session,
    *,
    request: EvaluationRunRequest,
    settings: Settings,
) -> EvaluationResult:
    training_run = session.get(TrainingRun, request.training_run_id)
    if training_run is None:
        raise ValueError(f"Training run '{request.training_run_id}' was not found.")

    dataset_version = session.get(DatasetVersion, training_run.dataset_version_id)
    if dataset_version is None:
        raise ValueError(f"Dataset version '{training_run.dataset_version_id}' was not found.")
    if not settings.llmproxy_evaluation_command:
        raise NotImplementedError(
            "Real benchmark execution is not configured. Set LLMPROXY_EVALUATION_COMMAND to a command that reads benchmark JSON from stdin and emits JSON scores."
        )

    benchmark_bundle = load_benchmarks(dataset_version.domain)
    benchmark_manifest = benchmark_bundle["manifest"]
    benchmark_records = benchmark_bundle["records"]

    baseline_name = request.frontier_baseline_name or frontier_baseline_name_for_domain(
        dataset_version.domain,
        settings,
    )
    frontier_score = frontier_baseline_score(dataset_version.domain, settings)
    frontier_cost = frontier_baseline_cost(dataset_version.domain, settings)
    local_cost = LOCAL_RUNTIME_COST_BY_MODE.get(training_run.training_mode, 0.03)
    evaluation_backend_result = run_json_command(
        command=settings.llmproxy_evaluation_command,
        payload={
            "training_run": {
                "id": training_run.id,
                "dataset_version_id": training_run.dataset_version_id,
                "base_model": training_run.base_model,
                "training_mode": training_run.training_mode,
                "artifact_path": training_run.artifact_path,
                "training_config": training_run.training_config_json,
                "metrics": training_run.metrics_json,
            },
            "dataset_version": {
                "id": dataset_version.id,
                "domain": dataset_version.domain,
                "record_count": dataset_version.record_count,
                "train_path": dataset_version.train_path,
                "validation_path": dataset_version.validation_path,
                "test_path": dataset_version.test_path,
            },
            "benchmark_manifest": benchmark_manifest,
            "benchmark_records": benchmark_records,
            "frontier_baseline_name": baseline_name,
        },
        timeout_seconds=settings.llmproxy_evaluation_timeout_seconds,
    )
    overall_score = float(evaluation_backend_result["overall_score"])
    quality_delta_vs_frontier = round(frontier_score - overall_score, 4)
    value_per_dollar_gain_vs_frontier = compare_value_per_dollar(
        local_score=overall_score,
        frontier_score=frontier_score,
        local_cost=local_cost,
        frontier_cost=frontier_cost,
    )
    promotion_status, gate_failures = evaluate_promotion_gate(
        overall_score=overall_score,
        domain=dataset_version.domain,
        quality_delta_vs_frontier=quality_delta_vs_frontier,
        value_per_dollar_gain_vs_frontier=value_per_dollar_gain_vs_frontier,
    )

    evaluation_run_id = generate_prefixed_id("eval")
    package_dir = Path(settings.llmproxy_models_path) / training_run.id
    package_metadata = dict(evaluation_backend_result.get("package_metadata") or {})
    package_manifest = {
        "package_version": "1.0",
        "model_registry_id": f"model_{training_run.id}",
        "model_alias": f"{dataset_version.domain}-{training_run.training_mode}-{training_run.id}",
        "base_model": training_run.base_model,
        "adapter_type": training_run.training_mode,
        "artifact_format": "adapter-binary",
        "artifact_paths": package_metadata.get("artifact_paths") or [training_run.artifact_path],
        "domains": package_metadata.get("domains") or [dataset_version.domain],
        "task_types": package_metadata.get("task_types") or [dataset_version.domain],
        "quality_summary": {
            "overall_score": overall_score,
            "domain_scores": {dataset_version.domain: overall_score},
            "quality_delta_vs_frontier": quality_delta_vs_frontier,
            "value_per_dollar_gain_vs_frontier": value_per_dollar_gain_vs_frontier,
            "promotion_status": promotion_status,
        },
        "compatibility": {
            "model_contract_version": "1.0",
            "learner_version": "0.1.0",
            "compatible_proxy_versions": ["0.1.0"],
            "runtime_targets": package_metadata.get("runtime_targets") or ["ollama"],
        },
        "provenance": {
            "training_run_id": training_run.id,
            "dataset_version_id": dataset_version.id,
            "evaluation_run_id": evaluation_run_id,
            "frontier_baseline_name": baseline_name,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    package_manifest_path = store_artifact(
        directory=package_dir,
        artifact_name="model-package.json",
        payload=package_manifest,
    )

    result_json = {
        "benchmark_manifest": benchmark_manifest,
        "benchmark_record_count": len(benchmark_records),
        "frontier_baseline_score": frontier_score,
        "frontier_baseline_cost": frontier_cost,
        "local_runtime_cost": local_cost,
        "backend_result": evaluation_backend_result,
        "promotion_status": promotion_status,
        "gate_failures": gate_failures,
        "package_manifest_path": package_manifest_path,
    }

    evaluation_run = EvaluationRun(
        id=evaluation_run_id,
        training_run_id=training_run.id,
        domain=dataset_version.domain,
        frontier_baseline_name=baseline_name,
        overall_score=overall_score,
        quality_delta_vs_frontier=quality_delta_vs_frontier,
        value_per_dollar_gain_vs_frontier=value_per_dollar_gain_vs_frontier,
        result_json=result_json,
    )
    session.add(evaluation_run)
    emit_event(
        session,
        event_type="evaluation.completed",
        source="llmproxy",
        payload={
            "evaluation_run_id": evaluation_run_id,
            "training_run_id": training_run.id,
            "promotion_status": promotion_status,
            "package_manifest_path": package_manifest_path,
        },
    )
    if promotion_status == "approved":
        emit_event(
            session,
            event_type="model.approved",
            source="llmproxy",
            payload={
                "evaluation_run_id": evaluation_run_id,
                "training_run_id": training_run.id,
                "model_alias": package_manifest["model_alias"],
            },
        )

    return EvaluationResult(
        evaluation_run_id=evaluation_run.id,
        training_run_id=training_run.id,
        domain=evaluation_run.domain,
        frontier_baseline_name=evaluation_run.frontier_baseline_name,
        overall_score=evaluation_run.overall_score,
        quality_delta_vs_frontier=evaluation_run.quality_delta_vs_frontier,
        value_per_dollar_gain_vs_frontier=evaluation_run.value_per_dollar_gain_vs_frontier,
        promotion_status=promotion_status,
        package_manifest_path=package_manifest_path,
        result=result_json,
    )
