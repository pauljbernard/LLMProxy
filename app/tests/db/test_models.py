from app.db.models import DatasetVersion, EvaluationRun, TrainingRun


def test_learner_models_declare_foreign_keys() -> None:
    dataset_version_fk_targets = {fk.target_fullname for fk in DatasetVersion.__table__.c.source_import_id.foreign_keys}
    training_run_fk_targets = {fk.target_fullname for fk in TrainingRun.__table__.c.dataset_version_id.foreign_keys}
    evaluation_run_fk_targets = {fk.target_fullname for fk in EvaluationRun.__table__.c.training_run_id.foreign_keys}

    assert "learner.dataset_import.id" in dataset_version_fk_targets
    assert "learner.dataset_version.id" in training_run_fk_targets
    assert "learner.training_run.id" in evaluation_run_fk_targets
