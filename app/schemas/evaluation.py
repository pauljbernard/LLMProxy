"""Evaluation schemas."""

from pydantic import BaseModel


class EvaluationRunRequest(BaseModel):
    training_run_id: str
    frontier_baseline_name: str | None = None


class EvaluationResult(BaseModel):
    evaluation_run_id: str
    training_run_id: str
    domain: str
    frontier_baseline_name: str
    overall_score: float
    quality_delta_vs_frontier: float
    value_per_dollar_gain_vs_frontier: float
    promotion_status: str
    package_manifest_path: str
    result: dict[str, object]


class EvaluationRunView(BaseModel):
    id: str
    training_run_id: str
    domain: str
    frontier_baseline_name: str
    overall_score: float
    quality_delta_vs_frontier: float
    value_per_dollar_gain_vs_frontier: float
    promotion_status: str
    package_manifest_path: str
