"""Helpers for command-backed training and evaluation backends."""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import threading
import time
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


def _stream_reader(
    stream: Any,
    *,
    stream_name: str,
    output_queue: queue.Queue[tuple[str, str | None]],
) -> None:
    try:
        for line in stream:
            output_queue.put((stream_name, line))
    finally:
        output_queue.put((stream_name, None))


def run_json_command_streaming(
    *,
    command: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    extra_env: dict[str, str] | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    process = subprocess.Popen(
        shlex.split(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    process.stdin.write(json.dumps(payload))
    process.stdin.close()

    output_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
    stdout_thread = threading.Thread(
        target=_stream_reader,
        args=(process.stdout,),
        kwargs={"stream_name": "stdout", "output_queue": output_queue},
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_reader,
        args=(process.stderr,),
        kwargs={"stream_name": "stderr", "output_queue": output_queue},
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    stdout_closed = False
    stderr_closed = False
    stderr_lines: list[str] = []
    result_payload: dict[str, Any] | None = None
    deadline = time.monotonic() + timeout_seconds

    while not (stdout_closed and stderr_closed):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill()
            process.wait()
            raise RuntimeError(f"Command timed out after {timeout_seconds} seconds.")

        try:
            stream_name, line = output_queue.get(timeout=min(0.25, remaining))
        except queue.Empty:
            continue

        if line is None:
            if stream_name == "stdout":
                stdout_closed = True
            else:
                stderr_closed = True
            continue

        line = line.strip()
        if not line:
            continue

        if stream_name == "stderr":
            stderr_lines.append(line)
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            process.kill()
            process.wait()
            raise RuntimeError("Command output was not valid JSONL.") from exc

        if not isinstance(message, dict):
            process.kill()
            process.wait()
            raise RuntimeError("Command output lines must be JSON objects.")

        if message.get("type") == "progress":
            progress_payload = message.get("payload")
            if not isinstance(progress_payload, dict):
                raise RuntimeError("Progress payload must be a JSON object.")
            if progress_callback is not None:
                progress_callback(progress_payload)
            continue

        if message.get("type") == "result":
            candidate_payload = message.get("payload")
            if not isinstance(candidate_payload, dict):
                raise RuntimeError("Result payload must be a JSON object.")
            result_payload = candidate_payload
            continue

        result_payload = message

    return_code = process.wait()
    stdout_thread.join(timeout=0.1)
    stderr_thread.join(timeout=0.1)
    if return_code != 0:
        detail = "\n".join(stderr_lines).strip() or f"Command failed with exit code {return_code}."
        raise RuntimeError(detail)
    if result_payload is None:
        raise RuntimeError("Command completed successfully but produced no JSON result.")
    return result_payload
