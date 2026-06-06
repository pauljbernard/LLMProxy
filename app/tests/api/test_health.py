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
    assert "logs_path" in payload


def test_metrics() -> None:
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    payload = response.json()
    assert "job_counts" in payload
    assert "event_counts" in payload
    assert "provider_health" in payload
