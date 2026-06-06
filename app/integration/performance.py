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
    total_requests = int(session.execute(select(func.count()).select_from(ModelPerformanceSample)).scalar_one())
    total_cost = float(session.execute(select(func.coalesce(func.sum(ModelPerformanceSample.cost_estimate), 0.0))).scalar_one())
    successful_sample_count = int(
        session.execute(
            select(func.count()).select_from(ModelPerformanceSample).where(ModelPerformanceSample.successful.is_(True))
        ).scalar_one()
    )
    successful_cost = float(
        session.execute(
            select(func.coalesce(func.sum(ModelPerformanceSample.cost_estimate), 0.0)).where(
                ModelPerformanceSample.successful.is_(True)
            )
        ).scalar_one()
    )
    local_sample_count = int(
        session.execute(
            select(func.count()).select_from(ModelPerformanceSample).where(
                (ModelPerformanceSample.route_type.startswith("local_"))
                | (ModelPerformanceSample.route_type == "local_only")
            )
        ).scalar_one()
    )
    frontier_sample_count = int(
        session.execute(
            select(func.count()).select_from(ModelPerformanceSample).where(
                (ModelPerformanceSample.route_type.startswith("frontier"))
                | (ModelPerformanceSample.route_type == "fallback")
            )
        ).scalar_one()
    )
    shadow_sample_count = int(
        session.execute(
            select(func.count()).select_from(ModelPerformanceSample).where(ModelPerformanceSample.route_type == "shadow")
        ).scalar_one()
    )
    frontier_cost_total = float(
        session.execute(
            select(func.coalesce(func.sum(ModelPerformanceSample.cost_estimate), 0.0)).where(
                (ModelPerformanceSample.route_type.startswith("frontier"))
                | (ModelPerformanceSample.route_type == "fallback")
            )
        ).scalar_one()
    )
    local_cost_total = float(
        session.execute(
            select(func.coalesce(func.sum(ModelPerformanceSample.cost_estimate), 0.0)).where(
                (ModelPerformanceSample.route_type.startswith("local_"))
                | (ModelPerformanceSample.route_type == "local_only")
            )
        ).scalar_one()
    )
    candidate_count = int(session.execute(select(func.count()).select_from(TrainingCandidate)).scalar_one())
    approved_candidate_count = int(
        session.execute(
            select(func.count()).select_from(TrainingCandidate).where(TrainingCandidate.approval_status == "approved")
        ).scalar_one()
    )
    reviewed_candidate_count = int(
        session.execute(
            select(func.count()).select_from(TrainingCandidate).where(TrainingCandidate.approval_status != "needs_review")
        ).scalar_one()
    )
    import_count = int(session.execute(select(func.count()).select_from(DatasetImport)).scalar_one())
    import_record_total = int(
        session.execute(
            select(func.coalesce(func.sum(DatasetImport.record_count + DatasetImport.quarantined_count), 0))
        ).scalar_one()
    )
    quarantined_total = int(
        session.execute(select(func.coalesce(func.sum(DatasetImport.quarantined_count), 0))).scalar_one()
    )
    export_record_total = int(
        session.execute(select(func.coalesce(func.sum(DatasetExport.record_count), 0))).scalar_one()
    )
    training_run_count = int(session.execute(select(func.count()).select_from(TrainingRun)).scalar_one())
    successful_training_runs = int(
        session.execute(
            select(func.count()).select_from(TrainingRun).where(TrainingRun.status == "completed")
        ).scalar_one()
    )
    evaluation_run_count = int(session.execute(select(func.count()).select_from(EvaluationRun)).scalar_one())
    approved_models = int(
        session.execute(
            select(func.count()).select_from(EvaluationRun).where(
                EvaluationRun.promotion_status == "approved"
            )
        ).scalar_one()
    )
    rollback_events = int(
        session.execute(
            select(func.count()).select_from(IntegrationEvent).where(IntegrationEvent.event_type == "model.rolled_back")
        ).scalar_one()
    )
    latest_policy = session.execute(
        select(RoutingPolicyVersion).order_by(RoutingPolicyVersion.created_at.desc())
    ).scalars().first()
    policy_version = latest_policy.policy_version if latest_policy is not None else "none"
    eligible_local_samples = max(total_requests - shadow_sample_count, 0)
    local_sample_rows = session.execute(
        select(
            ModelPerformanceSample.domain,
            ModelPerformanceSample.quality_score,
            ModelPerformanceSample.cost_estimate,
        ).where(
            (
                (ModelPerformanceSample.route_type.startswith("local_"))
                | (ModelPerformanceSample.route_type == "local_only")
            ),
            ModelPerformanceSample.quality_score.is_not(None),
        )
    ).all()
    successful_local_substitution_count = 0
    avoided_frontier_spend = 0.0
    for domain, quality_score, cost_estimate in local_sample_rows:
        if quality_score is not None and float(quality_score) >= frontier_baseline_score(str(domain), settings) - 0.05:
            successful_local_substitution_count += 1
            avoided_frontier_spend += frontier_baseline_cost(str(domain), settings) - float(cost_estimate)

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
            value=(successful_cost / successful_sample_count) if successful_sample_count else 0.0,
            policy_version=policy_version,
            sample_size=successful_sample_count,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="frontier_spend_per_100_requests",
            value=(frontier_cost_total / total_requests * 100) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="local_spend_per_100_requests",
            value=(local_cost_total / total_requests * 100) if total_requests else 0.0,
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
            value=(local_sample_count / eligible_local_samples) if eligible_local_samples else 0.0,
            policy_version=policy_version,
            sample_size=eligible_local_samples,
        ),
        _metric(
            time_window="all_time",
            name="frontier_routing_rate",
            value=(frontier_sample_count / total_requests) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
        ),
        _metric(
            time_window="all_time",
            name="frontier_to_local_substitution_rate",
            value=(successful_local_substitution_count / eligible_local_samples) if eligible_local_samples else 0.0,
            policy_version=policy_version,
            sample_size=eligible_local_samples,
        ),
        _metric(
            time_window="all_time",
            name="avoided_frontier_spend",
            value=avoided_frontier_spend,
            policy_version=policy_version,
            sample_size=successful_local_substitution_count,
            currency="USD",
            estimation_flag=True,
        ),
        _metric(
            time_window="all_time",
            name="training_candidate_capture_rate",
            value=(candidate_count / total_requests) if total_requests else 0.0,
            policy_version=policy_version,
            sample_size=total_requests,
        ),
        _metric(
            time_window="all_time",
            name="approval_rate",
            value=(approved_candidate_count / reviewed_candidate_count) if reviewed_candidate_count else 0.0,
            policy_version=policy_version,
            sample_size=reviewed_candidate_count,
        ),
        _metric(
            time_window="all_time",
            name="export_yield_rate",
            value=(export_record_total / approved_candidate_count) if approved_candidate_count else 0.0,
            policy_version=policy_version,
            sample_size=approved_candidate_count,
        ),
        _metric(
            time_window="all_time",
            name="dataset_quarantine_rate",
            value=(quarantined_total / import_record_total)
            if import_count and import_record_total
            else 0.0,
            policy_version=policy_version,
            sample_size=import_count,
        ),
        _metric(
            time_window="all_time",
            name="training_success_rate",
            value=(successful_training_runs / training_run_count) if training_run_count else 0.0,
            policy_version=policy_version,
            sample_size=training_run_count,
        ),
        _metric(
            time_window="all_time",
            name="promotion_pass_rate",
            value=(approved_models / evaluation_run_count) if evaluation_run_count else 0.0,
            policy_version=policy_version,
            sample_size=evaluation_run_count,
        ),
        _metric(
            time_window="all_time",
            name="rollback_rate",
            value=(rollback_events / approved_models) if approved_models else 0.0,
            policy_version=policy_version,
            sample_size=approved_models,
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
