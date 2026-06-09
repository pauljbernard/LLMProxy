import json
from contextlib import contextmanager
from pathlib import Path

from app.cli import main
from app.config import Settings


def test_cli_config_set_writes_env_file(tmp_path: Path, capsys) -> None:
    env_file = tmp_path / ".env"

    exit_code = main(["config", "set", "LLMPROXY_OPENAI_MODEL", "gpt-5.5", "--env-file", str(env_file)])

    assert exit_code == 0
    assert env_file.read_text(encoding="utf-8") == "LLMPROXY_OPENAI_MODEL=gpt-5.5\n"
    payload = json.loads(capsys.readouterr().out)
    assert payload["updated"] is True


def test_cli_config_show_outputs_settings(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "app.cli.get_settings",
        lambda: Settings(llmproxy_openai_model="gpt-5.5", llmproxy_models_path="/tmp/models"),
    )

    exit_code = main(["config", "show"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["llmproxy_openai_model"] == "gpt-5.5"


def test_cli_models_register_writes_manifest(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "app.cli.get_settings",
        lambda: Settings(llmproxy_models_path=str(tmp_path)),
    )

    exit_code = main(
        [
            "models",
            "register",
            "model_1",
            "coding-lora-1",
            "Qwen/Qwen2.5-Coder-7B-Instruct",
            "lora",
            "/tmp/adapter.bin",
            "ollama",
            "http://localhost:11434",
            "--domain",
            "coding",
            "--task-type",
            "code_review",
        ]
    )

    assert exit_code == 0
    manifest_path = tmp_path / "coding-lora-1" / "model-package.json"
    assert manifest_path.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["manifest"]["model_alias"] == "coding-lora-1"


def test_cli_jobs_list_outputs_job_rows(monkeypatch, capsys) -> None:
    fake_job = type(
        "Job",
        (),
        {
            "id": "job_1",
            "job_type": "kpi.generate",
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
            "payload_json": {},
            "created_at": None,
        },
    )()

    class FakeScalarResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def __iter__(self):
            return iter(self._items)

    class FakeSession:
        def execute(self, _statement):
            return FakeScalarResult([fake_job])

    @contextmanager
    def fake_scope():
        yield FakeSession()

    monkeypatch.setattr("app.cli.session_scope", fake_scope)

    exit_code = main(["jobs", "list"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["job_type"] == "kpi.generate"


def test_cli_deploy_activate_outputs_response(monkeypatch, capsys) -> None:
    from app.schemas.integration import DeploymentResponse

    monkeypatch.setattr("app.cli.get_settings", lambda: Settings())
    monkeypatch.setattr(
        "app.cli.deploy_model",
        lambda session, model_alias, request, settings: DeploymentResponse(
            model_alias=model_alias,
            deployment_mode=request.deployment_mode,
            status="deployed",
            policy_version="rpol_1",
            runtime="ollama",
            endpoint_url="http://localhost:11434",
        ),
    )

    @contextmanager
    def fake_scope():
        yield object()

    monkeypatch.setattr("app.cli.session_scope", fake_scope)

    exit_code = main(["deploy", "activate", "coding-lora-1", "production"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "deployed"


def test_cli_training_run_outputs_response(monkeypatch, capsys) -> None:
    from app.schemas.training import TrainingRunResponse

    monkeypatch.setattr("app.cli.get_settings", lambda: Settings())
    monkeypatch.setattr(
        "app.cli.create_training_run",
        lambda session, request, settings: TrainingRunResponse(
            training_run_id="train_1",
            dataset_version_id=request.dataset_version_id,
            training_mode=request.training_mode,
            trainer_backend=request.trainer_backend,
            status="completed",
            artifact_path="/tmp/train_1",
            metrics={"loss": 0.1},
        ),
    )

    @contextmanager
    def fake_scope():
        yield object()

    monkeypatch.setattr("app.cli.session_scope", fake_scope)

    exit_code = main(["training", "run", "dsv_1", "gpt-5.5", "lora", "--trainer-backend", "unsloth"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["training_run_id"] == "train_1"
    assert payload["trainer_backend"] == "unsloth"


def test_cli_scheduler_run_once(monkeypatch, capsys) -> None:
    called = {"value": False}

    def fake_run_scheduler_iteration() -> None:
        called["value"] = True

    monkeypatch.setattr("app.cli.run_scheduler_iteration", fake_run_scheduler_iteration)

    exit_code = main(["scheduler", "run-once"])

    assert exit_code == 0
    assert called["value"] is True
    payload = json.loads(capsys.readouterr().out)
    assert payload["scheduled"] is True


def test_cli_proxy_chat_outputs_response(monkeypatch, capsys) -> None:
    from app.schemas.chat import ChatCompletionResponse, Choice, ChoiceMessage, UsageInfo

    async def fake_chat_completions(request, session, settings):
        assert request.metadata.session_id == "sess_1"
        assert request.messages[0].role == "user"
        return ChatCompletionResponse(
            id="chatcmpl_1",
            created=1,
            model="gpt-5.5",
            choices=[Choice(message=ChoiceMessage(content="hello back"))],
            usage=UsageInfo(prompt_tokens=2, completion_tokens=2, total_tokens=4),
        )

    monkeypatch.setattr("app.cli.get_settings", lambda: Settings())
    monkeypatch.setattr("app.cli.chat_completions", fake_chat_completions)

    @contextmanager
    def fake_scope():
        yield object()

    monkeypatch.setattr("app.cli.session_scope", fake_scope)

    exit_code = main(["proxy", "chat", "--session-id", "sess_1", "--message", "user:hello there"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["choices"][0]["message"]["content"] == "hello back"


def test_cli_jobs_retry_resets_state(monkeypatch, capsys) -> None:
    from datetime import datetime, timezone

    job = type(
        "Job",
        (),
        {
            "id": "job_1",
            "status": "failed",
            "claimed_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
            "last_error": "boom",
            "attempts": 3,
            "available_at": datetime.now(timezone.utc),
        },
    )()

    class FakeSession:
        def get(self, model, key):
            assert key == "job_1"
            return job

    @contextmanager
    def fake_scope():
        yield FakeSession()

    monkeypatch.setattr("app.cli.session_scope", fake_scope)

    exit_code = main(["jobs", "retry", "job_1", "--reset-attempts", "--available-now"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["retried"] is True
    assert job.status == "pending"
    assert job.attempts == 0
    assert job.last_error is None


def test_cli_events_replay_marks_event_pending_and_processes(monkeypatch, capsys) -> None:
    event = type(
        "Event",
        (),
        {
            "id": "evt_1",
            "event_type": "dataset.exported",
            "processed_at": "already",
        },
    )()

    class FakeResponse:
        processed_count = 1
        imported_count = 1

    class FakeSession:
        def get(self, model, key):
            assert key == "evt_1"
            return event

        def flush(self):
            return None

    @contextmanager
    def fake_scope():
        yield FakeSession()

    monkeypatch.setattr("app.cli.get_settings", lambda: Settings())
    monkeypatch.setattr("app.cli.session_scope", fake_scope)
    monkeypatch.setattr("app.cli.process_pending_events", lambda session, settings: FakeResponse())

    exit_code = main(["events", "replay", "evt_1"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["replayed"] is True
    assert event.processed_at is None


def test_cli_datasets_versions_lists_rows(monkeypatch, capsys) -> None:
    fake_version = type(
        "DatasetVersion",
        (),
        {
            "id": "dsv_1",
            "domain": "coding",
            "version_name": "coding-v1",
            "source_import_id": "imp_1",
            "train_path": "/tmp/train.jsonl",
            "validation_path": "/tmp/validation.jsonl",
            "test_path": "/tmp/test.jsonl",
            "record_count": 12,
            "created_at": None,
        },
    )()

    class FakeScalarResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def __iter__(self):
            return iter(self._items)

    class FakeSession:
        def execute(self, _statement):
            return FakeScalarResult([fake_version])

    @contextmanager
    def fake_scope():
        yield FakeSession()

    monkeypatch.setattr("app.cli.session_scope", fake_scope)

    exit_code = main(["datasets", "versions"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["version_name"] == "coding-v1"
