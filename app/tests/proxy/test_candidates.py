from datetime import datetime, timezone

from app.db.models import TrainingCandidate
from app.proxy.candidates import approve_training_candidate, reject_training_candidate


def build_candidate() -> TrainingCandidate:
    return TrainingCandidate(
        id="cand_1",
        request_log_id="req_1",
        routing_decision_id="route_1",
        session_id="sess_1",
        domain="coding",
        task_type="code_review",
        status="needs_review",
        quality_score=0.9,
        approval_status="needs_review",
        export_eligible=False,
        selected_response="response",
        messages_json=[],
        provenance_json={},
        validation_json={},
        metadata_json={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_approve_training_candidate_sets_exportable_state() -> None:
    candidate = build_candidate()
    approve_training_candidate(None, candidate)
    assert candidate.status == "approved"
    assert candidate.approval_status == "approved"
    assert candidate.export_eligible is True


def test_reject_training_candidate_sets_rejected_state() -> None:
    candidate = build_candidate()
    reject_training_candidate(None, candidate)
    assert candidate.status == "rejected"
    assert candidate.approval_status == "rejected"
    assert candidate.export_eligible is False
