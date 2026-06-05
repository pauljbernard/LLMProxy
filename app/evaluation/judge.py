"""Evaluation judge helpers."""

from __future__ import annotations

from app.evaluation.code_validation import validate_code_output
from app.evaluation.style_scoring import score_style


def judge_benchmark_output(
    *,
    domain: str,
    training_mode: str,
    dataset_record_count: int,
    benchmark_record_count: int,
) -> float:
    if domain == "coding":
        return validate_code_output(
            training_mode=training_mode,
            record_count=dataset_record_count,
            benchmark_record_count=benchmark_record_count,
        )
    return score_style(
        training_mode=training_mode,
        record_count=dataset_record_count,
        benchmark_record_count=benchmark_record_count,
    )
