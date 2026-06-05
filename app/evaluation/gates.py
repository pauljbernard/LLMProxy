"""Promotion gate helpers."""

from __future__ import annotations


def evaluate_promotion_gate(
    *,
    overall_score: float,
    domain: str,
    quality_delta_vs_frontier: float,
    value_per_dollar_gain_vs_frontier: float,
) -> tuple[str, list[str]]:
    failures: list[str] = []
    if overall_score < 0.85:
        failures.append("overall_score_below_threshold")
    if domain == "coding" and overall_score < 0.80:
        failures.append("coding_pass_rate_below_threshold")
    if domain == "software_architecture" and overall_score < 0.85:
        failures.append("architecture_score_below_threshold")
    if domain == "writing_style" and overall_score < 0.80:
        failures.append("style_score_below_threshold")
    if quality_delta_vs_frontier > 0.05:
        failures.append("quality_delta_vs_frontier_too_high")
    if value_per_dollar_gain_vs_frontier < 3.0:
        failures.append("value_per_dollar_gain_vs_frontier_too_low")
    return ("approved" if not failures else "rejected", failures)
