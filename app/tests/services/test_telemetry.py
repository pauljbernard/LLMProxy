from app.services.telemetry import (
    emit_counter,
    emit_metric,
    observe_cache_event,
    observe_provider_attempt,
    observe_request,
    prometheus_metrics_payload,
    reset_telemetry_state_for_tests,
)


def test_emit_metric_and_counter_include_attributes() -> None:
    metric = emit_metric("local_routing_rate", 0.6, attributes={"domain": "coding"})
    counter = emit_counter("jobs_processed", increment=2, attributes={"job_type": "kpi.generate"})
    assert metric["metric"] == "local_routing_rate"
    assert metric["attributes"]["domain"] == "coding"
    assert counter["value"] == 2.0


def test_prometheus_payload_reflects_recorded_events() -> None:
    reset_telemetry_state_for_tests()
    observe_request(
        endpoint="/v1/chat/completions",
        provider="openai",
        stream=False,
        status="ok",
        latency_seconds=0.05,
    )
    observe_provider_attempt(
        provider="openai",
        stream=False,
        outcome="success",
        latency_seconds=0.01,
    )
    observe_cache_event(cache="exact", outcome="hit")
    payload = prometheus_metrics_payload().decode("utf-8")
    assert "llmproxy_requests_total" in payload
    assert 'provider="openai"' in payload
    assert "llmproxy_provider_attempts_total" in payload
    assert 'cache="exact"' in payload
