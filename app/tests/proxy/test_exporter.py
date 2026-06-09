from pathlib import Path
import json

from app.config import Settings
from app.db.models import DatasetExport, TrainingCandidate
from app.operator_payloads import dataset_export_payload
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
        provenance_json={
            "source": "frontier_single",
            "interaction_traces": [
                {
                    "trace_id": "trace_llm_resp_1",
                    "protocol": "llm",
                    "operation": "chat_completion",
                },
                {
                    "trace_id": "trace_mcp_req_1_0",
                    "protocol": "mcp",
                    "operation": "tool_call",
                },
            ],
        },
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
    assert candidate.export_eligible is False
    assert len(session.added) == 2
    exported_record = json.loads(Path(response.data_path).read_text(encoding="utf-8").strip())
    exported_manifest = json.loads(Path(response.manifest_path).read_text(encoding="utf-8"))
    assert exported_record["interaction_traces"][0]["protocol"] == "llm"
    assert exported_manifest["interaction_protocols"] == ["llm", "mcp"]
    assert exported_manifest["interaction_protocol_counts"] == {"llm": 1, "mcp": 1}
    export_record = next(item for item in session.added if isinstance(item, DatasetExport))
    export_payload = dataset_export_payload(export_record)
    assert export_payload["name"] == "coding-adapter"
    assert export_payload["interaction_protocols"] == ["llm", "mcp"]
    assert export_payload["interaction_protocol_counts"] == {"llm": 1, "mcp": 1}
    assert export_payload["interaction_filters"] == {}


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
        provenance_json={"source": "frontier_single", "interaction_traces": []},
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


def test_export_candidates_filters_by_interaction_protocol_operation_and_outcome(tmp_path: Path) -> None:
    llm_candidate = TrainingCandidate(
        id="cand_llm",
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
        provenance_json={
            "interaction_traces": [
                {"protocol": "llm", "operation": "chat_completion", "success": True},
                {"protocol": "mcp", "operation": "tool_call", "success": False},
            ],
        },
        validation_json={"validated": True},
        metadata_json={"task_type": "code_review"},
    )
    rest_candidate = TrainingCandidate(
        id="cand_rest",
        request_log_id="req_2",
        routing_decision_id="route_2",
        session_id="sess_2",
        domain="coding",
        task_type="code_review",
        status="approved",
        quality_score=0.88,
        approval_status="approved",
        export_eligible=True,
        selected_response="Call the downstream API.",
        messages_json=[{"role": "user", "content": "Invoke endpoint"}],
        provenance_json={
            "interaction_traces": [
                {"protocol": "rest", "operation": "invoke_endpoint", "success": True},
            ],
        },
        validation_json={"validated": True},
        metadata_json={"task_type": "code_review"},
    )
    session = FakeSession([llm_candidate, rest_candidate])
    settings = Settings(llmproxy_exports_path=str(tmp_path))

    response = export_candidates(
        session,
        request=DatasetExportRequest(
            domain="coding",
            interaction_protocol="rest",
            interaction_operation="invoke_endpoint",
            interaction_outcome="success",
        ),
        settings=settings,
    )

    assert response.record_count == 1
    exported_record = json.loads(Path(response.data_path).read_text(encoding="utf-8").strip())
    exported_manifest = json.loads(Path(response.manifest_path).read_text(encoding="utf-8"))
    export_record = next(item for item in session.added if isinstance(item, DatasetExport))
    export_payload = dataset_export_payload(export_record)
    assert exported_record["candidate_id"] == "cand_rest"
    assert exported_manifest["interaction_filters"] == {
        "protocol": "rest",
        "operation": "invoke_endpoint",
        "outcome": "success",
        "prompt_template_name": None,
        "prompt_template_version": None,
        "prompt_template_selection_mode": None,
    }
    assert export_payload["interaction_filters"] == {
        "protocol": "rest",
        "operation": "invoke_endpoint",
        "outcome": "success",
    }


def test_export_candidates_filters_by_prompt_template_lineage(tmp_path: Path) -> None:
    matching_candidate = TrainingCandidate(
        id="cand_prompt_match",
        request_log_id="req_1",
        routing_decision_id="route_1",
        session_id="sess_1",
        domain="coding",
        task_type="code_review",
        status="approved",
        quality_score=0.95,
        approval_status="approved",
        export_eligible=True,
        selected_response="Use the smaller patch.",
        messages_json=[{"role": "user", "content": "Review patch"}],
        provenance_json={"interaction_traces": [{"protocol": "llm", "operation": "chat_completion", "success": True}]},
        validation_json={"validated": True},
        metadata_json={
            "prompt_template_name": "architecture_review",
            "prompt_template_version": 3,
            "prompt_template_selection_mode": "challenger_canary",
            "requested_model": "proxy-auto",
            "effective_model": "gpt-5",
        },
    )
    other_candidate = TrainingCandidate(
        id="cand_prompt_other",
        request_log_id="req_2",
        routing_decision_id="route_2",
        session_id="sess_2",
        domain="coding",
        task_type="code_review",
        status="approved",
        quality_score=0.91,
        approval_status="approved",
        export_eligible=True,
        selected_response="Use a follow-up check.",
        messages_json=[{"role": "user", "content": "Review follow-up patch"}],
        provenance_json={"interaction_traces": [{"protocol": "llm", "operation": "chat_completion", "success": True}]},
        validation_json={"validated": True},
        metadata_json={
            "prompt_template_name": "incident_summary",
            "prompt_template_version": 1,
        },
    )
    session = FakeSession([matching_candidate, other_candidate])
    settings = Settings(llmproxy_exports_path=str(tmp_path))

    response = export_candidates(
        session,
        request=DatasetExportRequest(
            domain="coding",
            prompt_template_name="architecture_review",
            prompt_template_version=3,
            prompt_template_selection_mode="challenger_canary",
        ),
        settings=settings,
    )

    assert response.record_count == 1
    exported_record = json.loads(Path(response.data_path).read_text(encoding="utf-8").strip())
    exported_manifest = json.loads(Path(response.manifest_path).read_text(encoding="utf-8"))
    export_record = next(item for item in session.added if isinstance(item, DatasetExport))
    export_payload = dataset_export_payload(export_record)
    assert exported_record["candidate_id"] == "cand_prompt_match"
    assert exported_manifest["interaction_filters"] == {
        "protocol": None,
        "operation": None,
        "outcome": None,
        "prompt_template_name": "architecture_review",
        "prompt_template_version": 3,
        "prompt_template_selection_mode": "challenger_canary",
    }
    assert export_payload["interaction_filters"] == {
        "prompt_template_name": "architecture_review",
        "prompt_template_version": 3,
        "prompt_template_selection_mode": "challenger_canary",
    }
    assert exported_manifest["prompt_rollout_mode_counts"] == {"challenger_canary": 1}
    assert export_payload["prompt_rollout_mode_counts"] == {"challenger_canary": 1}
