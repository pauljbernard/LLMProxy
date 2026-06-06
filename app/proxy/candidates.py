"""Training candidate lifecycle helpers."""

from __future__ import annotations

from datetime import datetime, timezone

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


def list_training_candidates(session: Session) -> list[TrainingCandidate]:
    return list(
        session.execute(
            select(TrainingCandidate).order_by(TrainingCandidate.created_at.desc())
        ).scalars()
    )


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
