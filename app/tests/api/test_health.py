from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "development"
    assert payload["database_backend"] == "postgresql"
    assert payload["redis_configured"] is True
    assert "provider_families_configured" in payload
    assert "groq" in payload["provider_families_configured"]
    assert "mistral" in payload["provider_families_configured"]
    assert "deepseek" in payload["provider_families_configured"]
    assert "cohere" in payload["provider_families_configured"]
    assert "together" in payload["provider_families_configured"]
    assert "fireworks" in payload["provider_families_configured"]
    assert "perplexity" in payload["provider_families_configured"]
    assert "cloudflare_workers_ai" in payload["provider_families_configured"]
    assert "huggingface_tgi" in payload["provider_families_configured"]
    assert "vertex_ai" in payload["provider_families_configured"]
    assert "provider_ping" in payload
    assert "openai" in payload["provider_ping"]
    assert "logs_path" in payload


def test_metrics() -> None:
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    payload = response.json()
    assert "job_counts" in payload
    assert "event_counts" in payload
    assert "provider_health" in payload


def test_prometheus_metrics_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/metrics/prometheus")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    payload = response.text
    assert "llmproxy_requests_total" in payload
    assert "llmproxy_provider_attempts_total" in payload
    assert "llmproxy_cache_events_total" in payload
