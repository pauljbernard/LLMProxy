"""Cost helpers."""


def value_per_dollar(score: float, cost: float) -> float:
    if cost <= 0:
        return 0.0
    return score / cost
