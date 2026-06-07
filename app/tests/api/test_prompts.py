from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api import prompts
from app.main import app


def test_public_prompt_endpoints_list_get_and_render() -> None:
    created = []

    class FakeSession:
        def execute(self, statement):
            text = str(statement)

            class ScalarOneResult:
                def scalar_one(self_inner):
                    return 0

            class ScalarList:
                def __init__(self_inner, items):
                    self_inner._items = items

                def all(self_inner):
                    return self_inner._items

                def first(self_inner):
                    return self_inner._items[0] if self_inner._items else None

            class Result:
                def scalars(self_inner):
                    return ScalarList(created)

            if "coalesce(max" in text.lower():
                return ScalarOneResult()
            return Result()

        def add(self, item):
            created.append(item)

        def commit(self):
            return None

        def refresh(self, item):
            if getattr(item, "created_at", None) is None:
                item.created_at = datetime.now(timezone.utc)

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[prompts.get_session] = fake_session
    client = TestClient(app)
    create_response = client.post(
        "/v1/prompts",
        headers={"Authorization": "Bearer change-me"},
        json={
            "name": "incident_summary",
            "template_text": "Summarize incident for {service_name}.",
            "variables": ["service_name"],
        },
    )
    assert create_response.status_code == 201
    get_response = client.get("/v1/prompts/incident_summary", headers={"Authorization": "Bearer change-me"})
    assert get_response.status_code == 200
    assert get_response.json()["version"] == 1
    list_response = client.get("/v1/prompts", headers={"Authorization": "Bearer change-me"})
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "incident_summary"
    render_response = client.post(
        "/v1/prompts/incident_summary/render",
        headers={"Authorization": "Bearer change-me"},
        json={"version": 1, "variables": {"service_name": "payments"}},
    )
    diff_response = client.get(
        "/v1/prompts/incident_summary/diff?from_version=1&to_version=1",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()
    assert render_response.status_code == 200
    assert render_response.json()["rendered_text"] == "Summarize incident for payments."
    assert diff_response.status_code == 200
    assert diff_response.json()["name"] == "incident_summary"
    assert diff_response.json()["from_version"] == 1


def test_prompt_render_reports_missing_variable() -> None:
    created = []

    class FakeSession:
        def execute(self, _statement):
            class ScalarList:
                def __init__(self_inner, items):
                    self_inner._items = items

                def all(self_inner):
                    return self_inner._items

                def first(self_inner):
                    return self_inner._items[0] if self_inner._items else None

            class Result:
                def scalars(self_inner):
                    return ScalarList(created)

            return Result()

    template = type(
        "PromptTemplateRecord",
        (),
        {
            "id": "prompttpl_1",
            "name": "incident_summary",
            "version": 1,
            "description": None,
            "template_text": "Summarize incident for {service_name}.",
            "variables_json": ["service_name"],
            "model_override": None,
            "metadata_json": {},
            "created_at": datetime.now(timezone.utc),
        },
    )()
    created.append(template)

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[prompts.get_session] = fake_session
    client = TestClient(app)
    response = client.post(
        "/v1/prompts/incident_summary/render",
        headers={"Authorization": "Bearer change-me"},
        json={"version": 1, "variables": {}},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 400
    assert "Missing prompt variable" in response.json()["detail"]
