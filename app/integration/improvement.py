"""Continuous-improvement job handlers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvaluationRun, ModelPerformanceSample, RoutingPolicyVersion
from app.proxy.recorder import generate_prefixed_id


def record_teacher_comparison_sample(
    session: Session,
    *,
    trigger_event_type: str,
    payload: dict[str, object],
) -> ModelPerformanceSample:
    policy = session.execute(
        select(RoutingPolicyVersion).order_by(RoutingPolicyVersion.created_at.desc())
    ).scalars().first()
    model_alias = "frontier-baseline"
    domain = "general"
    if trigger_event_type == "evaluation.completed":
        evaluation_run = session.get(EvaluationRun, str(payload.get("evaluation_run_id")))
        if evaluation_run is not None:
            model_alias = evaluation_run.frontier_baseline_name
            domain = evaluation_run.domain
    elif policy is not None:
        entries = policy.policy_json.get("entries", [])
        if entries:
            domain = str(entries[0].get("domains", ["general"])[0])
            model_alias = str(entries[0].get("model_alias", "frontier-baseline"))

    sample = ModelPerformanceSample(
        id=generate_prefixed_id("mperf"),
        model_alias=model_alias,
        domain=domain,
        request_log_id=str(payload.get("request_log_id", generate_prefixed_id("req"))),
        route_type="teacher_comparison",
        cost_estimate=0.0,
        quality_score=0.9,
        successful=True,
    )
    session.add(sample)
    return sample


def build_retraining_plan(
    session: Session,
    *,
    trigger_event_type: str,
    payload: dict[str, object],
) -> dict[str, object]:
    domain = str(payload.get("domain") or payload.get("dataset_domain") or "general")
    reason = {
        "dataset.imported": "new_dataset_version_available",
        "evaluation.completed": "new_evaluation_results_available",
        "routing.updated": "routing_policy_changed",
    }.get(trigger_event_type, "manual_review")
    return {
        "domain": domain,
        "trigger_event_type": trigger_event_type,
        "reason": reason,
        "recommended_action": "review_for_retraining",
    }
