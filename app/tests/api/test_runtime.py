from unittest.mock import patch

import pytest

from app.runtime import parse_args, run_migrations, run_scheduler, run_scheduler_iteration, run_worker, run_worker_iteration


def test_parse_args_accepts_api_role() -> None:
    with patch("sys.argv", ["runtime", "api"]):
        args = parse_args()
    assert args.role == "api"


def test_parse_args_accepts_training_worker_role() -> None:
    with patch("sys.argv", ["runtime", "training-worker"]):
        args = parse_args()
    assert args.role == "training-worker"


def test_run_migrations_invokes_alembic() -> None:
    with patch("subprocess.run") as run:
        run_migrations()
    run.assert_called_once_with(["python3", "-m", "alembic", "upgrade", "head"], check=True)


def test_run_worker_iteration_returns_false_when_no_job() -> None:
    fake_session = type(
        "FakeSession",
        (),
        {
            "execute": lambda self, statement: type("Result", (), {"scalars": lambda self: type("Scalars", (), {"first": lambda self: None})()})(),
            "commit": lambda self: None,
            "close": lambda self: None,
            "rollback": lambda self: None,
            "get": lambda self, model, job_id: None,
        },
    )()

    with patch("app.runtime.get_session_factory", return_value=lambda: fake_session):
        assert run_worker_iteration() is False


def test_run_worker_iteration_supports_additional_job_types() -> None:
    job = type(
        "Job",
        (),
        {
            "id": "job_1",
            "job_type": "performance.sample",
            "payload_json": {"trigger_event_type": "evaluation.completed", "evaluation_run_id": "eval_1"},
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
            "claimed_at": None,
            "completed_at": None,
            "last_error": None,
        },
    )()
    evaluation_run = type(
        "EvaluationRun",
        (),
        {
            "frontier_baseline_name": "claude-3-5-sonnet",
            "domain": "coding",
        },
    )()
    fake_session = type(
        "FakeSession",
        (),
        {
            "execute": lambda self, statement: type("Result", (), {"scalars": lambda self: type("Scalars", (), {"first": lambda self: job})()})(),
            "commit": lambda self: None,
            "close": lambda self: None,
            "rollback": lambda self: None,
            "get": lambda self, model, job_id: evaluation_run,
            "add": lambda self, value: None,
        },
    )()

    with patch("app.runtime.get_session_factory", return_value=lambda: fake_session):
        assert run_worker_iteration() is True


def test_run_worker_iteration_processes_evaluation_jobs() -> None:
    job = type(
        "Job",
        (),
        {
            "id": "job_1",
            "job_type": "evaluation.run",
            "payload_json": {"evaluation_run_id": "eval_1"},
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
            "claimed_at": None,
            "completed_at": None,
            "last_error": None,
        },
    )()

    class ClaimSession:
        commit_count = 0

        def commit(self) -> None:
            self.commit_count += 1

        def close(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    claim_session = ClaimSession()

    with patch("app.runtime.get_session_factory", return_value=lambda: claim_session):
        with patch("app.runtime.claim_next_job_for_lane", return_value=job):
            with patch("app.runtime.execute_evaluation_run") as execute_evaluation_run:
                execute_evaluation_run.return_value = None
                assert run_worker_iteration() is True

    assert claim_session.commit_count == 1
    _, kwargs = execute_evaluation_run.call_args
    assert kwargs["evaluation_run_id"] == "eval_1"


def test_run_worker_iteration_processes_deployment_jobs() -> None:
    job = type(
        "Job",
        (),
        {
            "id": "job_1",
            "job_type": "deployment.activate",
            "payload_json": {
                "model_alias": "coding-lora-v1",
                "deployment_mode": "production",
                "domains": ["coding"],
                "task_types": ["code_review"],
            },
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
            "claimed_at": None,
            "completed_at": None,
            "last_error": None,
        },
    )()

    class ClaimSession:
        commit_count = 0

        def commit(self) -> None:
            self.commit_count += 1

        def close(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    claim_session = ClaimSession()

    with patch("app.runtime.get_session_factory", return_value=lambda: claim_session):
        with patch("app.runtime.claim_next_job_for_lane", return_value=job):
            with patch("app.runtime.deploy_model") as deploy_model:
                deploy_model.return_value = None
                assert run_worker_iteration() is True

    assert claim_session.commit_count == 1
    _, kwargs = deploy_model.call_args
    assert kwargs["model_alias"] == "coding-lora-v1"
    assert kwargs["request"].deployment_mode == "production"


def test_run_worker_iteration_processes_replicate_prediction_jobs() -> None:
    job = type(
        "Job",
        (),
        {
            "id": "job_rep_1",
            "job_type": "replicate.prediction",
            "payload_json": {
                "model": "replicate/hello-world",
                "input": {"text": "Alice"},
                "wait_for_completion": True,
            },
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
            "claimed_at": None,
            "completed_at": None,
            "last_error": None,
        },
    )()

    class ClaimSession:
        commit_count = 0

        def commit(self) -> None:
            self.commit_count += 1

        def close(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    claim_session = ClaimSession()

    async def fake_run_replicate_prediction(*, settings, model, input_payload, wait_for_completion):
        return {"id": "pred_1", "status": "succeeded", "output": "hello Alice"}

    with patch("app.runtime.get_session_factory", return_value=lambda: claim_session):
        with patch("app.runtime.claim_next_job_for_lane", return_value=job):
            with patch("app.runtime.run_replicate_prediction", fake_run_replicate_prediction):
                assert run_worker_iteration() is True

    assert claim_session.commit_count == 1
    assert job.payload_json["result"]["status"] == "succeeded"


def test_run_worker_iteration_passes_job_lane_filters() -> None:
    fake_session = type(
        "FakeSession",
        (),
        {
            "commit": lambda self: None,
            "close": lambda self: None,
            "rollback": lambda self: None,
            "get": lambda self, model, job_id: None,
        },
    )()

    with patch("app.runtime.get_session_factory", return_value=lambda: fake_session):
        with patch("app.runtime.claim_next_job_for_lane", return_value=None) as claim:
            assert run_worker_iteration(include_job_types={"training.run"}, exclude_job_types={"kpi.generate"}) is False
    claim.assert_called_once()
    _, kwargs = claim.call_args
    assert kwargs["include_job_types"] == {"training.run"}
    assert kwargs["exclude_job_types"] == {"kpi.generate"}


def test_run_scheduler_iteration_resets_virtual_key_budgets_and_logs() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.commit_count = 0
            self.closed = False

        def commit(self) -> None:
            self.commit_count += 1

        def close(self) -> None:
            self.closed = True

    fake_session = FakeSession()
    scheduler_result = type("SchedulerResult", (), {"processed_count": 4, "imported_count": 1})()
    fake_job = type("Job", (), {"id": "job_kpi_1"})()

    with patch("app.runtime.get_session_factory", return_value=lambda: fake_session):
        with patch("app.runtime.process_pending_events", return_value=scheduler_result):
            with patch("app.runtime.enqueue_kpi_report_job", return_value=fake_job):
                with patch("app.runtime.reset_due_virtual_key_budgets", return_value=3) as reset_budgets:
                    with patch("app.runtime.log_record") as log_record:
                        run_scheduler_iteration()

    reset_budgets.assert_called_once_with(fake_session)
    assert fake_session.commit_count == 1
    assert fake_session.closed is True
    _, kwargs = log_record.call_args
    assert kwargs["data"]["virtual_key_budget_resets"] == 3


def test_run_worker_recovers_after_job_failure() -> None:
    settings = type(
        "Settings",
        (),
        {
            "llmproxy_database_wait_timeout_seconds": 1,
            "worker_include_job_types": set(),
            "worker_exclude_job_types": set(),
        },
    )()

    with patch("app.runtime.get_settings", return_value=settings):
        with patch("app.runtime.wait_for_database"):
            with patch("app.runtime.time.sleep"):
                with patch("app.runtime.log_record"):
                    with patch("app.runtime.run_worker_iteration", side_effect=[RuntimeError("boom"), KeyboardInterrupt()]) as run_iteration:
                        with pytest.raises(KeyboardInterrupt):
                            run_worker()

    assert run_iteration.call_count == 2


def test_run_worker_iteration_marks_training_run_failed_in_retry_session() -> None:
    job = type(
        "Job",
        (),
        {
            "id": "job_1",
            "job_type": "training.run",
            "payload_json": {"training_run_id": "train_1"},
            "status": "running",
            "attempts": 1,
            "max_attempts": 3,
            "claimed_at": None,
            "completed_at": None,
            "last_error": None,
        },
    )()
    training_run = type(
        "TrainingRun",
        (),
        {
            "id": "train_1",
            "status": "pending",
            "metrics_json": {},
        },
    )()

    class ClaimSession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    class RetrySession:
        committed = False

        def get(self, model, object_id):
            if object_id == "job_1":
                return job
            if object_id == "train_1":
                return training_run
            return None

        def commit(self) -> None:
            self.committed = True

        def close(self) -> None:
            return None

    claim_session = ClaimSession()
    retry_session = RetrySession()
    sessions = iter([claim_session, retry_session])

    with patch("app.runtime.get_session_factory", return_value=lambda: next(sessions)):
        with patch("app.runtime.claim_next_job_for_lane", return_value=job):
            with patch("app.runtime.execute_training_run", side_effect=RuntimeError("trainer boom")):
                with patch("app.runtime.log_record"):
                    with pytest.raises(RuntimeError, match="trainer boom"):
                        run_worker_iteration()

    assert training_run.status == "failed"
    assert training_run.metrics_json == {"error": "trainer boom"}
    assert retry_session.committed is True


def test_run_scheduler_recovers_after_iteration_failure() -> None:
    settings = type(
        "Settings",
        (),
        {
            "llmproxy_database_wait_timeout_seconds": 1,
        },
    )()

    with patch("app.runtime.get_settings", return_value=settings):
        with patch("app.runtime.wait_for_database"):
            with patch("app.runtime.time.sleep"):
                with patch("app.runtime.log_record"):
                    with patch("app.runtime.run_scheduler_iteration", side_effect=[RuntimeError("boom"), KeyboardInterrupt()]) as run_iteration:
                        with pytest.raises(KeyboardInterrupt):
                            run_scheduler()

    assert run_iteration.call_count == 2
