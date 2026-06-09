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
    RequestLog,
    RoutingDecisionRecord,
    RoutingPolicyVersion,
    TrainingCandidate,
    TrainingRun,
    VirtualAPIKey,
)
from app.evaluation.runner import frontier_baseline_cost, frontier_baseline_score
from app.proxy.recorder import generate_prefixed_id
from app.services.learning_pipeline import (
    is_learning_pipeline_request,
    learning_pipeline_scope_from_owner,
)
from app.schemas.integration import KpiMetricView, KpiReportResponse, KpiTopologyCostRollupView

FORMULA_VERSION = "1.0"


def _build_topology_rollups(
    *,
    sample_rows: list[ModelPerformanceSample],
    learning_request_ids: set[str],
    routing_decision_by_request: dict[str, RoutingDecisionRecord],
    topology_type: str,
    total_cost_of_ownership: float,
) -> list[KpiTopologyCostRollupView]:
    records: dict[str, dict[str, object]] = {}
    for row in sample_rows:
        decision = routing_decision_by_request.get(row.request_log_id)
        if decision is None:
            continue
        if topology_type == "node":
            topology_id = str(decision.selected_node_id or "").strip()
        else:
            topology_id = str(decision.selected_pool_id or "").strip()
        if not topology_id:
            continue
        record = records.setdefault(
            topology_id,
            {
                "topology_type": topology_type,
                "topology_id": topology_id,
                "node_role": decision.selected_node_role if topology_type == "node" else None,
                "capacity_class": decision.selected_capacity_class if topology_type == "node" else None,
                "request_ids": set(),
                "production_request_ids": set(),
                "learning_request_ids": set(),
                "spend_total": 0.0,
                "production_spend_total": 0.0,
                "learning_spend_total": 0.0,
            },
        )
        cost = float(row.cost_estimate or 0.0)
        request_ids = record["request_ids"]
        assert isinstance(request_ids, set)
        request_ids.add(row.request_log_id)
        if row.request_log_id in learning_request_ids:
            learning_ids = record["learning_request_ids"]
            assert isinstance(learning_ids, set)
            learning_ids.add(row.request_log_id)
            record["learning_spend_total"] = float(record["learning_spend_total"]) + cost
        else:
            production_ids = record["production_request_ids"]
            assert isinstance(production_ids, set)
            production_ids.add(row.request_log_id)
            record["production_spend_total"] = float(record["production_spend_total"]) + cost
        record["spend_total"] = float(record["spend_total"]) + cost
    rollups: list[KpiTopologyCostRollupView] = []
    for record in records.values():
        request_ids = record.pop("request_ids")
        production_ids = record.pop("production_request_ids")
        learning_ids = record.pop("learning_request_ids")
        assert isinstance(request_ids, set)
        assert isinstance(production_ids, set)
        assert isinstance(learning_ids, set)
        spend_total = float(record["spend_total"])
        rollups.append(
            KpiTopologyCostRollupView(
                topology_type=str(record["topology_type"]),
                topology_id=str(record["topology_id"]),
                node_role=str(record["node_role"]) if record["node_role"] else None,
                capacity_class=str(record["capacity_class"]) if record["capacity_class"] else None,
                request_count=len(request_ids),
                production_request_count=len(production_ids),
                learning_request_count=len(learning_ids),
                spend_total=round(spend_total, 6),
                production_spend_total=round(float(record["production_spend_total"]), 6),
                learning_spend_total=round(float(record["learning_spend_total"]), 6),
                share_of_tco=round((spend_total / total_cost_of_ownership) if total_cost_of_ownership else 0.0, 6),
            )
        )
    return sorted(rollups, key=lambda item: (-item.spend_total, item.topology_id))


def _build_listener_rollups(
    *,
    sample_rows: list[ModelPerformanceSample],
    learning_request_ids: set[str],
    request_by_id: dict[str, RequestLog],
    total_cost_of_ownership: float,
) -> list[KpiTopologyCostRollupView]:
    records: dict[str, dict[str, object]] = {}
    for row in sample_rows:
        request = request_by_id.get(row.request_log_id)
        if request is None:
            continue
        metadata = dict((request.request_json or {}).get("metadata") or {})
        listener_id = str(metadata.get("listener_id") or "default").strip() or "default"
        record = records.setdefault(
            listener_id,
            {
                "topology_type": "listener",
                "topology_id": listener_id,
                "request_ids": set(),
                "production_request_ids": set(),
                "learning_request_ids": set(),
                "spend_total": 0.0,
                "production_spend_total": 0.0,
                "learning_spend_total": 0.0,
            },
        )
        cost = float(row.cost_estimate or 0.0)
        request_ids = record["request_ids"]
        assert isinstance(request_ids, set)
        request_ids.add(row.request_log_id)
        if row.request_log_id in learning_request_ids:
            learning_ids = record["learning_request_ids"]
            assert isinstance(learning_ids, set)
            learning_ids.add(row.request_log_id)
            record["learning_spend_total"] = float(record["learning_spend_total"]) + cost
        else:
            production_ids = record["production_request_ids"]
            assert isinstance(production_ids, set)
            production_ids.add(row.request_log_id)
            record["production_spend_total"] = float(record["production_spend_total"]) + cost
        record["spend_total"] = float(record["spend_total"]) + cost
    rollups: list[KpiTopologyCostRollupView] = []
    for record in records.values():
        request_ids = record.pop("request_ids")
        production_ids = record.pop("production_request_ids")
        learning_ids = record.pop("learning_request_ids")
        assert isinstance(request_ids, set)
        assert isinstance(production_ids, set)
        assert isinstance(learning_ids, set)
        spend_total = float(record["spend_total"])
        rollups.append(
            KpiTopologyCostRollupView(
                topology_type="listener",
                topology_id=str(record["topology_id"]),
                request_count=len(request_ids),
                production_request_count=len(production_ids),
                learning_request_count=len(learning_ids),
                spend_total=round(spend_total, 6),
                production_spend_total=round(float(record["production_spend_total"]), 6),
                learning_spend_total=round(float(record["learning_spend_total"]), 6),
                share_of_tco=round((spend_total / total_cost_of_ownership) if total_cost_of_ownership else 0.0, 6),
            )
        )
    return sorted(rollups, key=lambda item: (-item.spend_total, item.topology_id))


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
    request_rows = list(session.execute(select(RequestLog)).scalars())
    request_by_id = {row.id: row for row in request_rows}
    learning_request_ids = {row.id for row in request_rows if is_learning_pipeline_request(row)}
    all_sample_rows = list(session.execute(select(ModelPerformanceSample)).scalars())
    routing_decision_rows = list(session.execute(select(RoutingDecisionRecord)).scalars())
    routing_decision_by_request = {row.request_log_id: row for row in routing_decision_rows}
    sample_rows = [row for row in all_sample_rows if row.request_log_id not in learning_request_ids]
    total_requests = len(sample_rows)
    total_cost = sum(float(row.cost_estimate or 0.0) for row in sample_rows)
    successful_rows = [row for row in sample_rows if row.successful]
    successful_sample_count = len(successful_rows)
    successful_cost = sum(float(row.cost_estimate or 0.0) for row in successful_rows)
    local_rows = [
        row
        for row in sample_rows
        if str(row.route_type).startswith("local_") or str(row.route_type) == "local_only"
    ]
    frontier_rows = [
        row
        for row in sample_rows
        if str(row.route_type).startswith("frontier") or str(row.route_type) == "fallback"
    ]
    shadow_rows = [row for row in sample_rows if str(row.route_type) == "shadow"]
    local_sample_count = len(local_rows)
    frontier_sample_count = len(frontier_rows)
    shadow_sample_count = len(shadow_rows)
    frontier_cost_total = sum(float(row.cost_estimate or 0.0) for row in frontier_rows)
    local_cost_total = sum(float(row.cost_estimate or 0.0) for row in local_rows)
    virtual_key_rows = list(session.execute(select(VirtualAPIKey)).scalars())
    training_pipeline_spend_total = sum(
        float(row.spend_usd or 0.0)
        for row in virtual_key_rows
        if learning_pipeline_scope_from_owner(row.owner_id) == "training"
    )
    evaluation_pipeline_spend_total = sum(
        float(row.spend_usd or 0.0)
        for row in virtual_key_rows
        if learning_pipeline_scope_from_owner(row.owner_id) == "evaluation"
    )
    learning_pipeline_spend_total = training_pipeline_spend_total + evaluation_pipeline_spend_total
    production_request_spend_total = total_cost
    total_cost_of_ownership = production_request_spend_total + learning_pipeline_spend_total
    learning_pipeline_request_count = len(learning_request_ids)
    learning_pipeline_share_of_tco = (
        learning_pipeline_spend_total / total_cost_of_ownership if total_cost_of_ownership else 0.0
    )
    pooled_request_ids = {
        sample.request_log_id
        for sample in sample_rows
        if (routing_decision_by_request.get(sample.request_log_id) and routing_decision_by_request[sample.request_log_id].selected_pool_id)
    }
    node_routed_request_ids = {
        sample.request_log_id
        for sample in sample_rows
        if (routing_decision_by_request.get(sample.request_log_id) and routing_decision_by_request[sample.request_log_id].selected_node_id)
    }
    pooled_request_count = len(pooled_request_ids)
    node_routed_request_count = len(node_routed_request_ids)
    pooled_request_spend_total = sum(
        float(row.cost_estimate or 0.0) for row in sample_rows if row.request_log_id in pooled_request_ids
    )
    node_routed_request_spend_total = sum(
        float(row.cost_estimate or 0.0) for row in sample_rows if row.request_log_id in node_routed_request_ids
    )
    node_routed_share_of_tco = (
        node_routed_request_spend_total / total_cost_of_ownership if total_cost_of_ownership else 0.0
    )
    node_rollups = _build_topology_rollups(
        sample_rows=all_sample_rows,
        learning_request_ids=learning_request_ids,
        routing_decision_by_request=routing_decision_by_request,
        topology_type="node",
        total_cost_of_ownership=total_cost_of_ownership,
    )
    pool_rollups = _build_topology_rollups(
        sample_rows=all_sample_rows,
        learning_request_ids=learning_request_ids,
        routing_decision_by_request=routing_decision_by_request,
        topology_type="pool",
        total_cost_of_ownership=total_cost_of_ownership,
    )
    listener_rollups = _build_listener_rollups(
        sample_rows=all_sample_rows,
        learning_request_ids=learning_request_ids,
        request_by_id=request_by_id,
        total_cost_of_ownership=total_cost_of_ownership,
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
    local_sample_rows = [
        (row.domain, row.quality_score, row.cost_estimate)
        for row in local_rows
        if row.quality_score is not None
    ]
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
        _metric(
            time_window="all_time",
            name="production_request_spend_total",
            value=production_request_spend_total,
            policy_version=policy_version,
            sample_size=total_requests,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="training_pipeline_spend_total",
            value=training_pipeline_spend_total,
            policy_version=policy_version,
            sample_size=training_run_count,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="evaluation_pipeline_spend_total",
            value=evaluation_pipeline_spend_total,
            policy_version=policy_version,
            sample_size=evaluation_run_count,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="learning_pipeline_spend_total",
            value=learning_pipeline_spend_total,
            policy_version=policy_version,
            sample_size=learning_pipeline_request_count,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="learning_pipeline_request_count",
            value=float(learning_pipeline_request_count),
            policy_version=policy_version,
            sample_size=learning_pipeline_request_count,
        ),
        _metric(
            time_window="all_time",
            name="learning_pipeline_share_of_tco",
            value=learning_pipeline_share_of_tco,
            policy_version=policy_version,
            sample_size=learning_pipeline_request_count,
        ),
        _metric(
            time_window="all_time",
            name="pooled_request_spend_total",
            value=pooled_request_spend_total,
            policy_version=policy_version,
            sample_size=pooled_request_count,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="pooled_request_count",
            value=float(pooled_request_count),
            policy_version=policy_version,
            sample_size=pooled_request_count,
        ),
        _metric(
            time_window="all_time",
            name="node_routed_request_spend_total",
            value=node_routed_request_spend_total,
            policy_version=policy_version,
            sample_size=node_routed_request_count,
            currency="USD",
        ),
        _metric(
            time_window="all_time",
            name="node_routed_request_count",
            value=float(node_routed_request_count),
            policy_version=policy_version,
            sample_size=node_routed_request_count,
        ),
        _metric(
            time_window="all_time",
            name="node_routed_share_of_tco",
            value=node_routed_share_of_tco,
            policy_version=policy_version,
            sample_size=node_routed_request_count,
        ),
        _metric(
            time_window="all_time",
            name="total_cost_of_ownership",
            value=total_cost_of_ownership,
            policy_version=policy_version,
            sample_size=total_requests + learning_pipeline_request_count,
            currency="USD",
        ),
    ]

    report_dir = Path(settings.llmproxy_reports_path)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "kpi-report-latest.json"
    report_path.write_text(
        json.dumps(
            {
                "metrics": [metric.model_dump(mode="json") for metric in metrics],
                "node_rollups": [item.model_dump(mode="json") for item in node_rollups],
                "pool_rollups": [item.model_dump(mode="json") for item in pool_rollups],
                "listener_rollups": [item.model_dump(mode="json") for item in listener_rollups],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return KpiReportResponse(
        report_path=str(report_path),
        metrics=metrics,
        node_rollups=node_rollups,
        pool_rollups=pool_rollups,
        listener_rollups=listener_rollups,
    )
