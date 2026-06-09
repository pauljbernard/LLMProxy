from app.config import Settings
from app.services.a2a_registry import inspect_a2a_peer, invoke_a2a_peer, list_a2a_peers


class _FakeResponse:
    def __init__(self, payload, status_code=200, headers=None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        self.response = _FakeResponse(
            {
                "name": "Planner Agent",
                "description": "Coordinates agent planning",
                "capabilities": ["plan", "delegate"],
            }
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        self.last_url = url
        self.last_headers = headers or {}
        return self.response

    async def post(self, url, headers=None, json=None):
        self.last_url = url
        self.last_headers = headers or {}
        self.last_json = json or {}
        return _FakeResponse({"status": "ok", "handled": self.last_json})


def test_list_a2a_peers_returns_sorted_inventory() -> None:
    settings = Settings(
        llmproxy_a2a_peers={
            "worker": {"label": "Worker Agent", "endpoint": "http://worker.test:9001", "capabilities": ["execute"]},
            "planner": {"label": "Planner Agent", "endpoint": "http://planner.test:9000", "capabilities": ["plan", "delegate"]},
        }
    )
    rows = __import__("asyncio").run(list_a2a_peers(settings))
    assert [row["peer"] for row in rows] == ["planner", "worker"]
    assert rows[0]["capability_count"] == 2


def test_inspect_a2a_peer_validates_discovery(monkeypatch) -> None:
    monkeypatch.setattr("app.services.a2a_registry.httpx.AsyncClient", _FakeAsyncClient)
    settings = Settings(
        llmproxy_a2a_peers={
            "planner": {
                "label": "Planner Agent",
                "endpoint": "http://planner.test:9000",
                "capabilities": ["plan", "delegate"],
            }
        }
    )
    payload = __import__("asyncio").run(inspect_a2a_peer(settings, "planner"))
    assert payload["validated"] is True
    assert payload["status_code"] == 200
    assert payload["discovered_name"] == "Planner Agent"
    assert payload["discovered_capability_count"] == 2
    assert payload["interaction_protocols"] == {"a2a": 1}
    assert payload["interaction_traces"][0]["protocol"] == "a2a"
    assert payload["interaction_traces"][0]["peer"] == "planner"


def test_invoke_a2a_peer_returns_structured_result(monkeypatch) -> None:
    monkeypatch.setattr("app.services.a2a_registry.httpx.AsyncClient", _FakeAsyncClient)
    settings = Settings(
        llmproxy_a2a_peers={
            "planner": {
                "label": "Planner Agent",
                "endpoint": "http://planner.test:9000",
                "capabilities": ["plan"],
            }
        }
    )
    payload = __import__("asyncio").run(
        invoke_a2a_peer(
            settings,
            "planner",
            capability="plan",
            input_payload={"goal": "Review this request"},
        )
    )
    assert payload["invoked"] is True
    assert payload["invoked_capability"] == "plan"
    assert payload["status_code"] == 200
    assert payload["interaction_protocols"] == {"a2a": 1}
    assert payload["interaction_traces"][0]["operation"] == "invoke_capability"
