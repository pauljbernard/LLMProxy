from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.models import EvaluationRun
from app.main import app
from app.schemas.integration import KpiMetricView, KpiReportResponse, KpiTopologyCostRollupView


def test_evaluation_runs_require_auth() -> None:
    client = TestClient(app)
    response = client.get("/evaluation/runs")
    assert response.status_code == 401


def test_submit_evaluation_run_requires_operator_token() -> None:
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(llmproxy_automation_tokens=["automation-token"])
    client = TestClient(app)
    response = client.post(
        "/evaluation/runs",
        headers={"Authorization": "Bearer automation-token"},
        json={"training_run_id": "train_1"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 403


def test_submit_evaluation_run_queues_job(monkeypatch) -> None:
    from app.api import evaluation as evaluation_api
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    class FakeSession:
        added = []

        def add(self, item) -> None:
            self.added.append(item)

        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        evaluation_api,
        "create_evaluation_run",
        lambda session, request, settings: evaluation_api.EvaluationEnqueueResponse(
            job_id="job_1",
            evaluation_run_id="eval_1",
            training_run_id=request.training_run_id,
            status="pending",
            queued=True,
            frontier_baseline_name=request.frontier_baseline_name,
        ),
    )

    from app.api.dependencies import get_session

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(llmproxy_automation_tokens=["automation-token"])
    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.post(
        "/evaluation/runs",
        headers={"Authorization": "Bearer change-me"},
        json={"training_run_id": "train_1"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["queued"] is True
    assert response.json()["job_id"] == "job_1"
    assert response.json()["evaluation_run_id"] == "eval_1"
    assert response.json()["training_run_id"] == "train_1"


def test_list_evaluation_runs_returns_serialized_runs(monkeypatch) -> None:
    from app.api import evaluation as evaluation_api

    class FakeSession:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        evaluation_api,
        "list_evaluation_runs",
        lambda session: [
            EvaluationRun(
                id="eval_1",
                training_run_id="train_1",
                domain="coding",
                frontier_baseline_name="claude-3-5-sonnet",
                status="completed",
                promotion_status="approved",
                overall_score=0.9,
                quality_delta_vs_frontier=0.02,
                value_per_dollar_gain_vs_frontier=4.1,
                result_json={"promotion_status": "approved", "package_manifest_path": "/tmp/model-package.json"},
                created_at=datetime.now(timezone.utc),
            )
        ],
    )

    from app.api.dependencies import get_session

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get("/evaluation/runs", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["status"] == "completed"
    assert payload[0]["promotion_status"] == "approved"


def test_list_evaluation_runs_supports_paginated_payload() -> None:
    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one(self):
            return self._value

        def scalars(self):
            return self

        def __iter__(self):
            return iter(self._value)

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def close(self) -> None:
            return None

        def execute(self, statement):
            self.calls += 1
            if self.calls == 1:
                return FakeScalarResult(4)
            return FakeScalarResult([
                EvaluationRun(
                    id="eval_2",
                    training_run_id="train_2",
                    domain="support",
                    frontier_baseline_name="gpt-5",
                    status="running",
                    promotion_status="pending",
                    overall_score=None,
                    quality_delta_vs_frontier=None,
                    value_per_dollar_gain_vs_frontier=None,
                    result_json={"package_manifest_path": "/tmp/model-package.json"},
                    created_at=datetime.now(timezone.utc),
                )
            ])

    from app.api.dependencies import get_session

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get("/evaluation/runs?paginated=true&limit=1&offset=2", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["limit"] == 1
    assert payload["offset"] == 2
    assert payload["items"][0]["id"] == "eval_2"
    assert payload["items"][0]["promotion_status"] == "pending"


def test_get_kpi_report_returns_response(monkeypatch) -> None:
    from app.api import evaluation as evaluation_api

    class FakeSession:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        evaluation_api,
        "generate_kpi_report",
        lambda session, settings: KpiReportResponse(
            report_path="/tmp/kpi-report-latest.json",
            metrics=[
                KpiMetricView(
                    time_window="all_time",
                    metric_name="avoided_frontier_spend",
                    metric_value=1.25,
                    formula_version="1.0",
                    policy_version="rpol_1",
                    sample_size=2,
                    currency="USD",
                    estimation_flag=True,
                )
            ],
            listener_rollups=[
                KpiTopologyCostRollupView(
                    topology_type="listener",
                    topology_id="admin",
                    request_count=3,
                    production_request_count=2,
                    learning_request_count=1,
                    spend_total=2.5,
                    production_spend_total=1.5,
                    learning_spend_total=1.0,
                    share_of_tco=0.25,
                )
            ],
            node_rollups=[
                KpiTopologyCostRollupView(
                    topology_type="node",
                    topology_id="child-a",
                    node_role="execution",
                    capacity_class="gpu-large",
                    request_count=3,
                    production_request_count=2,
                    learning_request_count=1,
                    spend_total=2.5,
                    production_spend_total=1.5,
                    learning_spend_total=1.0,
                    share_of_tco=0.25,
                )
            ],
            pool_rollups=[
                KpiTopologyCostRollupView(
                    topology_type="pool",
                    topology_id="coding-east",
                    request_count=3,
                    production_request_count=2,
                    learning_request_count=1,
                    spend_total=2.5,
                    production_spend_total=1.5,
                    learning_spend_total=1.0,
                    share_of_tco=0.25,
                )
            ],
        ),
    )

    from app.api.dependencies import get_session

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get("/evaluation/kpis", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"][0]["metric_name"] == "avoided_frontier_spend"
    assert payload["listener_rollups"][0]["topology_id"] == "admin"
    assert payload["node_rollups"][0]["topology_id"] == "child-a"
    assert payload["pool_rollups"][0]["topology_id"] == "coding-east"
