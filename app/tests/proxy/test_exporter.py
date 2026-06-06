from pathlib import Path

from app.config import Settings
from app.db.models import TrainingCandidate
from app.proxy.exporter import export_candidates
from app.schemas.candidate import DatasetExportRequest


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._items)


class FakeSession:
    def __init__(self, candidates):
        self._candidates = candidates
        self.added = []

    def execute(self, _statement):
        return FakeScalarResult(self._candidates)

    def add(self, item):
        self.added.append(item)


def test_export_candidates_writes_jsonl_and_manifest(tmp_path: Path) -> None:
    candidate = TrainingCandidate(
        id="cand_1",
        request_log_id="req_1",
        routing_decision_id="route_1",
        session_id="sess_1",
        domain="coding",
        task_type="code_review",
        status="approved",
        quality_score=0.91,
        approval_status="approved",
        export_eligible=True,
        selected_response="Use the smaller patch.",
        messages_json=[{"role": "user", "content": "Review patch"}],
        provenance_json={"source": "frontier_single"},
        validation_json={"validated": True},
        metadata_json={"task_type": "code_review"},
    )
    session = FakeSession([candidate])
    settings = Settings(llmproxy_exports_path=str(tmp_path))

    response = export_candidates(
        session,
        request=DatasetExportRequest(domain="coding", min_quality_score=0.5),
        settings=settings,
    )

    assert response.record_count == 1
    assert Path(response.data_path).exists()
    assert Path(response.manifest_path).exists()
    assert candidate.status == "exported"
    assert len(session.added) == 2


def test_export_candidates_allows_approved_unscored_candidates_at_default_threshold(tmp_path: Path) -> None:
    candidate = TrainingCandidate(
        id="cand_1",
        request_log_id="req_1",
        routing_decision_id="route_1",
        session_id="sess_1",
        domain="coding",
        task_type="code_review",
        status="approved",
        quality_score=None,
        approval_status="approved",
        export_eligible=True,
        selected_response="Use the smaller patch.",
        messages_json=[{"role": "user", "content": "Review patch"}],
        provenance_json={"source": "frontier_single"},
        validation_json={"validated": True},
        metadata_json={"task_type": "code_review"},
    )
    session = FakeSession([candidate])
    settings = Settings(llmproxy_exports_path=str(tmp_path))

    response = export_candidates(
        session,
        request=DatasetExportRequest(domain="coding"),
        settings=settings,
    )

    assert response.record_count == 1
