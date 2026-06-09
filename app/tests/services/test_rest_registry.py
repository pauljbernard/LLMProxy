from app.config import Settings
from app.services.rest_registry import inspect_rest_endpoint, invoke_rest_endpoint, list_rest_endpoints


class _FakeResponse:
    def __init__(self, payload, status_code=200, headers=None, text="") -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self.text = text

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        self.validation_response = _FakeResponse({"status": "ok"})
        self.invoke_response = _FakeResponse({"result": "done"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None):
        self.last_url = url
        self.last_headers = headers or {}
        self.last_params = params or {}
        return self.validation_response

    async def request(self, method, url, headers=None, json=None):
        self.last_method = method
        self.last_url = url
        self.last_headers = headers or {}
        self.last_json = json or {}
        return self.invoke_response


def test_list_rest_endpoints_returns_sorted_inventory() -> None:
    settings = Settings(
        llmproxy_rest_endpoints={
            "worker_api": {"label": "Worker API", "endpoint": "http://worker.test:9001"},
            "status_api": {"label": "Status API", "endpoint": "http://status.test:9000"},
        }
    )
    rows = __import__("asyncio").run(list_rest_endpoints(settings))
    assert [row["endpoint_name"] for row in rows] == ["status_api", "worker_api"]


def test_inspect_rest_endpoint_validates_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("app.services.rest_registry.httpx.AsyncClient", _FakeAsyncClient)
    settings = Settings(
        llmproxy_rest_endpoints={
            "status_api": {
                "label": "Status API",
                "endpoint": "http://status.test:9000",
                "validation_path": "/health",
            }
        }
    )
    payload = __import__("asyncio").run(inspect_rest_endpoint(settings, "status_api"))
    assert payload["validated"] is True
    assert payload["status_code"] == 200
    assert payload["interaction_protocols"] == {"rest": 1}
    assert payload["interaction_traces"][0]["operation"] == "validate_endpoint"


def test_invoke_rest_endpoint_returns_structured_result(monkeypatch) -> None:
    monkeypatch.setattr("app.services.rest_registry.httpx.AsyncClient", _FakeAsyncClient)
    settings = Settings(
        llmproxy_rest_endpoints={
            "status_api": {
                "label": "Status API",
                "endpoint": "http://status.test:9000",
                "invoke_path": "/api/status",
                "method": "POST",
            }
        }
    )
    payload = __import__("asyncio").run(
        invoke_rest_endpoint(
            settings,
            "status_api",
            method="POST",
            path="/api/status",
            input_payload={"id": "1234"},
        )
    )
    assert payload["invoked"] is True
    assert payload["invoked_method"] == "POST"
    assert payload["interaction_protocols"] == {"rest": 1}
    assert payload["interaction_traces"][0]["operation"] == "invoke_endpoint"
