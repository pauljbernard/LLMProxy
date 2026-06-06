from unittest.mock import patch

import pytest

from app.runtime import parse_args, run_migrations, run_worker, run_worker_iteration


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
