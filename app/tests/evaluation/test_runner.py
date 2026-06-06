from pathlib import Path

from app.config import Settings
from app.db.models import DatasetVersion, TrainingRun
from app.evaluation.runner import run_evaluation
from app.schemas.evaluation import EvaluationRunRequest


class FakeSession:
    def __init__(self, training_run: TrainingRun, dataset_version: DatasetVersion) -> None:
        self.training_run = training_run
        self.dataset_version = dataset_version
        self.added: list[object] = []
        self.commit_count = 0

    def get(self, model, object_id: str):
        if model is TrainingRun and object_id == self.training_run.id:
            return self.training_run
        if model is DatasetVersion and object_id == self.dataset_version.id:
            return self.dataset_version
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    def commit(self) -> None:
        self.commit_count += 1


def build_training_run() -> TrainingRun:
    return TrainingRun(
        id="train_1",
        dataset_version_id="dsv_1",
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        training_mode="lora",
        status="completed",
        training_config_json={},
        metrics_json={},
        artifact_path="/tmp/adapter.bin",
    )


def build_dataset_version() -> DatasetVersion:
    return DatasetVersion(
        id="dsv_1",
        domain="coding",
        version_name="coding-dsv_1",
        source_import_id="dsimp_1",
        train_path="/tmp/train.jsonl",
        validation_path="/tmp/validation.jsonl",
        test_path="/tmp/test.jsonl",
        record_count=6,
    )


def test_run_evaluation_blocks_until_real_backend_exists(tmp_path) -> None:
    session = FakeSession(build_training_run(), build_dataset_version())
    settings = Settings(llmproxy_models_path=str(tmp_path))

    try:
        run_evaluation(
            session,
            request=EvaluationRunRequest(training_run_id="train_1"),
            settings=settings,
        )
    except NotImplementedError as exc:
        assert "Real benchmark execution is not configured" in str(exc)
    else:
        raise AssertionError("Expected NotImplementedError for synthetic evaluation path")


def test_run_evaluation_uses_configured_backend(monkeypatch, tmp_path: Path) -> None:
    from app.evaluation import runner as evaluation_runner

    session = FakeSession(build_training_run(), build_dataset_version())
    settings = Settings(
        llmproxy_models_path=str(tmp_path),
        llmproxy_evaluation_command="fake-evaluator",
    )

    monkeypatch.setattr(
        evaluation_runner,
        "run_json_command",
        lambda **kwargs: {
            "overall_score": 0.94,
            "package_metadata": {
                "runtime_targets": ["ollama"],
                "domains": ["coding"],
                "task_types": ["code_review"],
            },
            "record_scores": {"coding-1": 0.95, "coding-2": 0.93},
        },
    )

    result = run_evaluation(
        session,
        request=EvaluationRunRequest(training_run_id="train_1"),
        settings=settings,
    )

    assert result.overall_score == 0.94
    assert result.package_manifest_path.endswith("model-package.json")
    assert result.result["backend_result"]["record_scores"]["coding-1"] == 0.95
    assert len(session.added) >= 2


def test_run_evaluation_uses_configured_frontier_baselines(monkeypatch, tmp_path: Path) -> None:
    from app.evaluation import runner as evaluation_runner

    session = FakeSession(build_training_run(), build_dataset_version())
    settings = Settings(
        llmproxy_models_path=str(tmp_path),
        llmproxy_evaluation_command="fake-evaluator",
        llmproxy_frontier_baseline_names={"coding": "gpt-5.5"},
        llmproxy_frontier_baseline_scores={"coding": 0.97},
        llmproxy_frontier_baseline_costs={"coding": 0.2},
    )

    monkeypatch.setattr(
        evaluation_runner,
        "run_json_command",
        lambda **kwargs: {
            "overall_score": 0.91,
            "package_metadata": {},
        },
    )

    result = run_evaluation(
        session,
        request=EvaluationRunRequest(training_run_id="train_1"),
        settings=settings,
    )

    assert result.frontier_baseline_name == "gpt-5.5"
    assert result.result["frontier_baseline_score"] == 0.97
    assert result.result["frontier_baseline_cost"] == 0.2


def test_run_evaluation_rejects_missing_training_run(tmp_path: Path) -> None:
    session = FakeSession(build_training_run(), build_dataset_version())
    settings = Settings(llmproxy_models_path=str(tmp_path))

    session.training_run = build_training_run()
    session.training_run.id = "other"

    try:
        run_evaluation(
            session,
            request=EvaluationRunRequest(training_run_id="train_1"),
            settings=settings,
        )
    except ValueError as exc:
        assert "Training run 'train_1' was not found" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing training run")
