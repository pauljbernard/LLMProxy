"""Helpers for command-backed training and evaluation backends."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any


def run_json_command(
    *,
    command: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"Command failed with exit code {completed.returncode}."
        raise RuntimeError(detail)
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("Command completed successfully but produced no JSON output on stdout.")
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Command output was not valid JSON.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Command output must be a JSON object.")
    return result
