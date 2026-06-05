from app.datasets.curriculum import build_curriculum
from app.integration.contracts import contract_version, event_contract
from app.services.secrets import get_secret
from app.services.telemetry import emit_counter, emit_metric


def test_build_curriculum_returns_staged_plan() -> None:
    result = build_curriculum(domain="coding", record_count=120)
    assert result["status"] == "ready"
    assert result["domain"] == "coding"
    assert len(result["stages"]) == 3


def test_event_contract_returns_versioned_metadata() -> None:
    result = event_contract("dataset.exported")
    assert result["contract_version"] == contract_version()
    assert result["event_type"] == "dataset.exported"


def test_emit_metric_and_counter_include_attributes() -> None:
    metric = emit_metric("local_routing_rate", 0.6, attributes={"domain": "coding"})
    counter = emit_counter("jobs_processed", increment=2, attributes={"job_type": "kpi.generate"})
    assert metric["metric"] == "local_routing_rate"
    assert metric["attributes"]["domain"] == "coding"
    assert counter["value"] == 2.0


def test_get_secret_reports_missing_secret_metadata() -> None:
    value, reference = get_secret("LLMPROXY_MISSING_SECRET_FOR_TEST")
    assert value is None
    assert reference.name == "LLMPROXY_MISSING_SECRET_FOR_TEST"
