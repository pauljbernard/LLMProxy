"""Benchmark loader helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings


def load_benchmarks(domain: str, settings: Settings) -> dict[str, object]:
    benchmark_dir = Path(settings.llmproxy_benchmarks_path) / domain
    manifest_path = benchmark_dir / "benchmark_manifest.json"
    records_path = benchmark_dir / "benchmark_records.jsonl"
    if not manifest_path.exists() or not records_path.exists():
        raise ValueError(f"Benchmark artifacts for domain '{domain}' were not found.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {
        "manifest": manifest,
        "records": records,
    }
