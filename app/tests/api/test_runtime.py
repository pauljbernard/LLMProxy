from unittest.mock import patch

from app.runtime import parse_args, run_migrations, run_worker_iteration


def test_parse_args_accepts_api_role() -> None:
    with patch("sys.argv", ["runtime", "api"]):
        args = parse_args()
    assert args.role == "api"


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
