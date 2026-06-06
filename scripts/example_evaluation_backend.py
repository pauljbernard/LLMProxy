#!/usr/bin/env python3
"""Example command-backed evaluation adapter for llmProxy.

This is a smoke-test backend that demonstrates the JSON stdin/stdout contract
used by LLMPROXY_EVALUATION_COMMAND. It is not a real benchmark evaluator.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    benchmark_records = list(payload.get("benchmark_records") or [])
    training_run = dict(payload.get("training_run") or {})
    dataset_version = dict(payload.get("dataset_version") or {})

    record_scores = {}
    for index, record in enumerate(benchmark_records, start=1):
        benchmark_id = str(record.get("benchmark_id", f"benchmark-{index}"))
        record_scores[benchmark_id] = round(0.9 - ((index - 1) * 0.01), 4)

    overall_score = round(sum(record_scores.values()) / max(len(record_scores), 1), 4)

    json.dump(
        {
            "overall_score": overall_score,
            "record_scores": record_scores,
            "package_metadata": {
                "artifact_paths": [str(training_run.get("artifact_path", ""))],
                "domains": [str(dataset_version.get("domain", "general"))],
                "task_types": [str(dataset_version.get("domain", "general"))],
                "runtime_targets": ["ollama"],
            },
            "backend": "example_evaluation_backend",
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
