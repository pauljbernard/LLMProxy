"""Evaluation schemas."""

from pydantic import BaseModel


class EvaluationResult(BaseModel):
    domain: str
    overall_score: float
    quality_delta_vs_frontier: float
    value_per_dollar_gain_vs_frontier: float
