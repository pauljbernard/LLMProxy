"""Training candidate lifecycle helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TrainingCandidate
from app.proxy.recorder import generate_prefixed_id


def capture_training_candidate(
    session: Session,
    *,
    request_log_id: str,
    routing_decision_id: str,
    session_id: str,
    domain: str,
    task_type: str,
    quality_score: float | None,
    selected_response: str,
    messages: list[dict[str, object]],
    provenance: dict[str, object],
    validation: dict[str, object],
    metadata: dict[str, object],
) -> TrainingCandidate:
    candidate = TrainingCandidate(
        id=generate_prefixed_id("cand"),
        request_log_id=request_log_id,
        routing_decision_id=routing_decision_id,
        session_id=session_id,
        domain=domain,
        task_type=task_type,
        status="needs_review",
        quality_score=quality_score,
        approval_status="needs_review",
        export_eligible=False,
        selected_response=selected_response,
        messages_json=messages,
        provenance_json=provenance,
        validation_json=validation,
        metadata_json=metadata,
    )
    session.add(candidate)
    return candidate


def candidate_interaction_traces(candidate: TrainingCandidate) -> list[dict[str, Any]]:
    provenance = candidate.provenance_json if isinstance(candidate.provenance_json, dict) else {}
    raw_traces = provenance.get("interaction_traces")
    if not isinstance(raw_traces, list):
        return []
    return [trace for trace in raw_traces if isinstance(trace, dict)]


def summarize_candidate_interactions(candidate: TrainingCandidate) -> dict[str, Any]:
    traces = candidate_interaction_traces(candidate)
    protocols = sorted({str(trace.get("protocol") or "unknown") for trace in traces})
    operations = sorted({str(trace.get("operation") or "unknown") for trace in traces})
    success_count = sum(1 for trace in traces if trace.get("success") is True)
    failure_count = sum(1 for trace in traces if trace.get("success") is False)
    if success_count and failure_count:
        outcome = "mixed"
    elif failure_count:
        outcome = "failure"
    elif success_count:
        outcome = "success"
    else:
        outcome = "unknown"
    return {
        "interaction_protocols": protocols,
        "interaction_operations": operations,
        "interaction_outcome": outcome,
        "interaction_trace_count": len(traces),
        "success_trace_count": success_count,
        "failure_trace_count": failure_count,
    }


def candidate_matches_interaction_filters(
    candidate: TrainingCandidate,
    *,
    interaction_protocol: str | None = None,
    interaction_operation: str | None = None,
    interaction_outcome: str | None = None,
) -> bool:
    traces = candidate_interaction_traces(candidate)
    if not traces:
        return not any((interaction_protocol, interaction_operation, interaction_outcome))

    matching_traces = traces
    if interaction_protocol:
        normalized_protocol = interaction_protocol.strip().lower()
        matching_traces = [
            trace for trace in matching_traces if str(trace.get("protocol") or "unknown").lower() == normalized_protocol
        ]
    if interaction_operation:
        normalized_operation = interaction_operation.strip().lower()
        matching_traces = [
            trace for trace in matching_traces if str(trace.get("operation") or "unknown").lower() == normalized_operation
        ]
    if not matching_traces:
        return False
    if not interaction_outcome:
        return True

    normalized_outcome = interaction_outcome.strip().lower()
    if normalized_outcome == "success":
        return any(trace.get("success") is True for trace in matching_traces)
    if normalized_outcome == "failure":
        return any(trace.get("success") is False for trace in matching_traces)
    if normalized_outcome == "mixed":
        has_success = any(trace.get("success") is True for trace in matching_traces)
        has_failure = any(trace.get("success") is False for trace in matching_traces)
        return has_success and has_failure
    return True


def list_training_candidates(
    session: Session,
    *,
    domain: str | None = None,
    approval_status: str | None = None,
    interaction_protocol: str | None = None,
    interaction_operation: str | None = None,
    interaction_outcome: str | None = None,
    prompt_template_name: str | None = None,
    prompt_template_version: int | None = None,
    prompt_template_selection_mode: str | None = None,
) -> list[TrainingCandidate]:
    candidates = list(
        session.execute(
            select(TrainingCandidate).order_by(TrainingCandidate.created_at.desc())
        ).scalars()
    )
    if domain:
        candidates = [candidate for candidate in candidates if candidate.domain == domain]
    if approval_status:
        candidates = [candidate for candidate in candidates if candidate.approval_status == approval_status]
    if prompt_template_name:
        normalized_name = prompt_template_name.strip().lower()
        candidates = [
            candidate
            for candidate in candidates
            if str((candidate.metadata_json or {}).get("prompt_template_name") or "").strip().lower() == normalized_name
        ]
    if prompt_template_version is not None:
        candidates = [
            candidate
            for candidate in candidates
            if (candidate.metadata_json or {}).get("prompt_template_version") == prompt_template_version
        ]
    if prompt_template_selection_mode:
        normalized_mode = prompt_template_selection_mode.strip().lower()
        candidates = [
            candidate
            for candidate in candidates
            if str((candidate.metadata_json or {}).get("prompt_template_selection_mode") or "").strip().lower() == normalized_mode
        ]
    if interaction_protocol or interaction_operation or interaction_outcome:
        candidates = [
            candidate
            for candidate in candidates
            if candidate_matches_interaction_filters(
                candidate,
                interaction_protocol=interaction_protocol,
                interaction_operation=interaction_operation,
                interaction_outcome=interaction_outcome,
            )
        ]
    return candidates


def get_training_candidate(session: Session, candidate_id: str) -> TrainingCandidate | None:
    return session.get(TrainingCandidate, candidate_id)


def approve_training_candidate(session: Session, candidate: TrainingCandidate) -> TrainingCandidate:
    candidate.status = "approved"
    candidate.approval_status = "approved"
    candidate.export_eligible = True
    candidate.updated_at = datetime.now(timezone.utc)
    return candidate


def reject_training_candidate(session: Session, candidate: TrainingCandidate) -> TrainingCandidate:
    candidate.status = "rejected"
    candidate.approval_status = "rejected"
    candidate.export_eligible = False
    candidate.updated_at = datetime.now(timezone.utc)
    return candidate
