"""Economics comparison helpers."""

from __future__ import annotations


def compare_value_per_dollar(*, local_score: float, frontier_score: float, local_cost: float, frontier_cost: float) -> float:
    local_value_per_dollar = local_score / max(local_cost, 0.000001)
    frontier_value_per_dollar = frontier_score / max(frontier_cost, 0.000001)
    return round(local_value_per_dollar / frontier_value_per_dollar, 4)
