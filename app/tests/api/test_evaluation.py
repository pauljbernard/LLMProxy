from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.models import EvaluationRun
from app.main import app
from app.schemas.evaluation import EvaluationResult
from app.schemas.integration import KpiMetricView, KpiReportResponse


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


def test_submit_evaluation_run_returns_response(monkeypatch) -> None:
    from app.api import evaluation as evaluation_api
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    class FakeSession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        evaluation_api,
        "run_evaluation",
        lambda session, request, settings: EvaluationResult(
            evaluation_run_id="eval_1",
            training_run_id=request.training_run_id,
            domain="coding",
            frontier_baseline_name="claude-3-5-sonnet",
            overall_score=0.9,
            quality_delta_vs_frontier=0.02,
            value_per_dollar_gain_vs_frontier=4.1,
            promotion_status="approved",
            package_manifest_path="/tmp/model-package.json",
            result={"promotion_status": "approved"},
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

    assert response.status_code == 200
    assert response.json()["promotion_status"] == "approved"


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
    assert payload[0]["promotion_status"] == "approved"


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
