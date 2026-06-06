"""Performance sampling and KPI reporting helpers."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    DatasetExport,
    DatasetImport,
    EvaluationRun,
    IntegrationEvent,
    ModelPerformanceSample,
    RoutingPolicyVersion,
    TrainingCandidate,
    TrainingRun,
)
from app.evaluation.runner import frontier_baseline_cost, frontier_baseline_score
from app.proxy.recorder import generate_prefixed_id
from app.schemas.integration import KpiMetricView, KpiReportResponse

FORMULA_VERSION = "1.0"


def sample_performance(
    session: Session,
    *,
    model_alias: str,
    domain: str,
    request_log_id: str,
    route_type: str,
    cost_estimate: float,
    quality_score: float | None,
    successful: bool,
) -> ModelPerformanceSample:
    sample = ModelPerformanceSample(
        id=generate_prefixed_id("mperf"),
        model_alias=model_alias,
        domain=domain,
        request_log_id=request_log_id,
        route_type=route_type,
        cost_estimate=cost_estimate,
        quality_score=quality_score,
        successful=successful,
    )
    session.add(sample)
    return sample


def _metric(
    *,
    time_window: str,
    name: str,
    value: float,
    policy_version: str,
    sample_size: int,
    currency: str | None = None,
    estimation_flag: bool | None = None,
) -> KpiMetricView:
    return KpiMetricView(
        time_window=time_window,
        metric_name=name,
        metric_value=round(value, 6),
        formula_version=FORMULA_VERSION,
        policy_version=policy_version,
        sample_size=sample_size,
        currency=currency,
        estimation_flag=estimation_flag,
    )


def generate_kpi_report(session: Session, *, settings: Settings) -> KpiReportResponse:
    samples = list(session.execute(select(ModelPerformanceSample)).scalars())
    candidates = list(session.execute(select(TrainingCandidate)).scalars())
    exports = list(session.execute(select(DatasetExport)).scalars())
    imports = list(session.execute(select(DatasetImport)).scalars())
    training_runs = list(session.execute(select(TrainingRun)).scalars())
    evaluation_runs = list(session.execute(select(EvaluationRun)).scalars())
    events = list(session.execute(select(IntegrationEvent)).scalars())
    latest_policy = session.execute(
        select(RoutingPolicyVersion).order_by(RoutingPolicyVersion.created_at.desc())
    ).scalars().first()
    policy_version = latest_policy.policy_version if latest_policy is not None else "none"

    total_requests = len(samples)
    total_cost = sum(sample.cost_estimate for sample in samples)
    successful_samples = [sample for sample in samples if sample.successful]
    successful_cost = sum(sample.cost_estimate for sample in successful_samples)
    local_samples = [sample for sample in samples if sample.route_type.startswith("local_") or sample.route_type == "local_only"]
    frontier_samples = [sample for sample in samples if sample.route_type.startswith("frontier") or sample.route_type == "fallback"]
    shadow_samples = [sample for sample in samples if sample.route_type == "shadow"]
    eligible_local_samples = [sample for sample in samples if sample.route_type != "shadow"]

    successful_local_substitutions = [
        sample
        for sample in local_samples
        if sample.quality_score is not None
        and sample.quality_score >= frontier_baseline_score(sample.domain) - 0.05
    ]
    avoided_frontier_spend = sum(
        frontier_baseline_cost(sample.domain) - sample.cost_estimate
        for sample in successful_local_substitutions
    )
    approved_candidates = [candidate for candidate in candidates if candidate.approval_status == "approved"]
    reviewed_candidates = [candidate for candidate in candidates if candidate.approval_status != "needs_review"]
    successful_training_runs = [run for run in training_runs if run.status == "completed"]
    approved_models = [run for run in evaluation_runs if str(run.result_json.get("promotion_status")) == "approved"]
    rollback_events = [event for event in events if event.event_type == "model.rolled_back"]

    metrics = [
        _metric(
            time_window="all_time",
            name="average_cost_per_request",
            value=(total_cost / total_requests) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="average_cost_per_successful_request",
            value=(successful_cost / len(successful_samples)) if successful_samples else 0.0,
            policy_version=policy_version,
            sample_size=len(successful_samples),
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="frontier_spend_per_100_requests",
            value=(sum(sample.cost_estimate for sample in frontier_samples) / total_requests * 100) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="local_spend_per_100_requests",
            value=(sum(sample.cost_estimate for sample in local_samples) / total_requests * 100) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="blended_spend_per_100_requests",
            value=(total_cost / total_requests * 100) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="local_routing_rate",
            value=(len(local_samples) / len(eligible_local_samples)) if eligible_local_samples else 0.0,
            policy_version=policy_version,
            sample_size=len(eligible_local_samples),
        ),
        _metric(
            time_window="all_time",
            name="frontier_routing_rate",
            value=(len(frontier_samples) / total_requests) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
        ),
        _metric(
            time_window="all_time",
            name="frontier_to_local_substitution_rate",
            value=(len(successful_local_substitutions) / len(eligible_local_samples)) if eligible_local_samples else 0.0,
            policy_version=policy_version,
            sample_size=len(eligible_local_samples),
        ),
        _metric(
            time_window="all_time",
            name="avoided_frontier_spend",
            value=avoided_frontier_spend,
            policy_version=policy_version,
            sample_size=len(successful_local_substitutions),
            currency="USD",
            estimation_flag=True,
        ),
        _metric(
            time_window="all_time",
            name="training_candidate_capture_rate",
            value=(len(candidates) / total_requests) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
        ),
        _metric(
            time_window="all_time",
            name="approval_rate",
            value=(len(approved_candidates) / len(reviewed_candidates)) if reviewed_candidates else 0.0,
            policy_version=policy_version,
            sample_size=len(reviewed_candidates),
        ),
        _metric(
            time_window="all_time",
            name="export_yield_rate",
            value=(sum(export.record_count for export in exports) / len(approved_candidates)) if approved_candidates else 0.0,
            policy_version=policy_version,
            sample_size=len(approved_candidates),
        ),
        _metric(
            time_window="all_time",
            name="dataset_quarantine_rate",
            value=(sum(dataset_import.quarantined_count for dataset_import in imports) / sum(dataset_import.record_count + dataset_import.quarantined_count for dataset_import in imports))
            if imports and sum(dataset_import.record_count + dataset_import.quarantined_count for dataset_import in imports)
            else 0.0,
            policy_version=policy_version,
            sample_size=len(imports),
        ),
        _metric(
            time_window="all_time",
            name="training_success_rate",
            value=(len(successful_training_runs) / len(training_runs)) if training_runs else 0.0,
            policy_version=policy_version,
            sample_size=len(training_runs),
        ),
        _metric(
            time_window="all_time",
            name="promotion_pass_rate",
            value=(len(approved_models) / len(evaluation_runs)) if evaluation_runs else 0.0,
            policy_version=policy_version,
            sample_size=len(evaluation_runs),
        ),
        _metric(
            time_window="all_time",
            name="rollback_rate",
            value=(len(rollback_events) / len(approved_models)) if approved_models else 0.0,
            policy_version=policy_version,
            sample_size=len(approved_models),
        ),
    ]

    report_dir = Path(settings.llmproxy_reports_path)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "kpi-report-latest.json"
    report_path.write_text(
        json.dumps({"metrics": [metric.model_dump(mode="json") for metric in metrics]}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return KpiReportResponse(report_path=str(report_path), metrics=metrics)
