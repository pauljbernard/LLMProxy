"""Promotion gate helpers."""

from __future__ import annotations

from app.config import Settings


def evaluate_promotion_gate(
    *,
    overall_score: float,
    domain: str,
    quality_delta_vs_frontier: float,
    value_per_dollar_gain_vs_frontier: float,
    settings: Settings,
) -> tuple[str, list[str]]:
    failures: list[str] = []
    if overall_score < settings.llmproxy_promotion_min_overall_score:
        failures.append("overall_score_below_threshold")
    domain_threshold = settings.llmproxy_promotion_domain_min_scores.get(domain)
    if domain_threshold is not None and overall_score < domain_threshold:
        failures.append(f"{domain}_score_below_threshold")
    if quality_delta_vs_frontier > settings.llmproxy_promotion_max_quality_delta_vs_frontier:
        failures.append("quality_delta_vs_frontier_too_high")
    if value_per_dollar_gain_vs_frontier < settings.llmproxy_promotion_min_value_per_dollar_gain_vs_frontier:
        failures.append("value_per_dollar_gain_vs_frontier_too_low")
    return ("approved" if not failures else "rejected", failures)
