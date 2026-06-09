"""Time-series rollups for LLM request observability."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import ModelResponse, RequestLog, RoutingDecisionRecord
from app.services.cost import estimate_cost_breakdown_usd

OPS_LOG_FILE = "operations.jsonl"


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _bucket_start(value: datetime, bucket_minutes: int) -> datetime:
    utc_value = _coerce_utc(value)
    bucket_seconds = max(1, int(bucket_minutes)) * 60
    bucket_epoch = int(utc_value.timestamp()) // bucket_seconds * bucket_seconds
    return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)


def _first_response_latency_ms(row: ModelResponse) -> int | None:
    payload = row.response_json if isinstance(row.response_json, dict) else {}
    raw = payload.get("first_response_latency_ms")
    if raw is not None:
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return None
    if not bool(payload.get("streamed")):
        return max(0, int(row.latency_ms or 0))
    return None


def _response_cost_breakdown(row: ModelResponse) -> tuple[float, float]:
    payload = row.response_json if isinstance(row.response_json, dict) else {}
    input_cost = payload.get("input_cost_estimate")
    output_cost = payload.get("output_cost_estimate")
    if input_cost is not None or output_cost is not None:
        return (round(float(input_cost or 0.0), 6), round(float(output_cost or 0.0), 6))
    breakdown = estimate_cost_breakdown_usd(
        provider_name=str(row.provider or ""),
        model_id=str(row.model or ""),
        input_tokens=int(row.input_tokens or 0),
        output_tokens=int(row.output_tokens or 0),
    )
    return (
        round(float(breakdown.get("input_cost_estimate") or 0.0), 6),
        round(float(breakdown.get("output_cost_estimate") or 0.0), 6),
    )


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _sum(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values), 6)


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * quantile))))
    return round(ordered[index], 2)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 2)


def _cost_per_thousand_requests(total_cost: float | None, request_count: int) -> float | None:
    if request_count <= 0 or total_cost is None:
        return None
    return round((total_cost / request_count) * 1000, 4)


def _parse_log_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _coerce_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _iter_relevant_ops_records(settings: Settings, *, since: datetime):
    log_path = Path(settings.llmproxy_logs_path) / OPS_LOG_FILE
    if not log_path.exists():
        return
    with log_path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        buffer = b""
        while position > 0:
            read_size = min(8192, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            buffer = chunk + buffer
            lines = buffer.split(b"\n")
            buffer = lines[0]
            for raw_line in reversed(lines[1:]):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                timestamp = _parse_log_timestamp(record.get("timestamp"))
                if timestamp is None:
                    continue
                if timestamp < since:
                    return
                yield record, timestamp
        tail_line = buffer.strip()
        if tail_line:
            try:
                record = json.loads(tail_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
            timestamp = _parse_log_timestamp(record.get("timestamp"))
            if timestamp is not None and timestamp >= since:
                yield record, timestamp


def _series_row(
    bucket_start_at: datetime,
    values: dict[str, list[float]] | None = None,
    *,
    first_response_sla_ms: int,
    total_response_sla_ms: int,
    cost_sla_usd: float,
) -> dict[str, Any]:
    series_values = values or {}
    requests = int(series_values.get("request_count", [0])[0] if "request_count" in series_values else 0)
    success_count = int(series_values.get("success_count", [0])[0] if "success_count" in series_values else 0)
    failure_count = int(series_values.get("failure_count", [0])[0] if "failure_count" in series_values else 0)
    fallback_count = int(series_values.get("fallback_count", [0])[0] if "fallback_count" in series_values else 0)
    redirect_count = int(series_values.get("redirect_count", [0])[0] if "redirect_count" in series_values else 0)
    stream_start_count = int(series_values.get("stream_start_count", [0])[0] if "stream_start_count" in series_values else 0)
    stream_complete_count = int(series_values.get("stream_complete_count", [0])[0] if "stream_complete_count" in series_values else 0)
    stream_failure_count = int(series_values.get("stream_failure_count", [0])[0] if "stream_failure_count" in series_values else 0)
    rate_limit_event_count = int(series_values.get("rate_limit_event_count", [0])[0] if "rate_limit_event_count" in series_values else 0)
    provider_429_count = int(series_values.get("provider_429_count", [0])[0] if "provider_429_count" in series_values else 0)
    provider_429_request_count = int(series_values.get("provider_429_request_count", [0])[0] if "provider_429_request_count" in series_values else 0)
    provider_429_stream_count = int(series_values.get("provider_429_stream_count", [0])[0] if "provider_429_stream_count" in series_values else 0)
    cache_hit_count = int(series_values.get("cache_hit_count", [0])[0] if "cache_hit_count" in series_values else 0)
    cache_miss_count = int(series_values.get("cache_miss_count", [0])[0] if "cache_miss_count" in series_values else 0)
    cache_bypass_count = int(series_values.get("cache_bypass_count", [0])[0] if "cache_bypass_count" in series_values else 0)
    exact_cache_hit_count = int(series_values.get("exact_cache_hit_count", [0])[0] if "exact_cache_hit_count" in series_values else 0)
    semantic_cache_hit_count = int(series_values.get("semantic_cache_hit_count", [0])[0] if "semantic_cache_hit_count" in series_values else 0)
    stream_partial_abort_count = int(series_values.get("stream_partial_abort_count", [0])[0] if "stream_partial_abort_count" in series_values else 0)
    stream_prelude_failure_count = int(series_values.get("stream_prelude_failure_count", [0])[0] if "stream_prelude_failure_count" in series_values else 0)
    total_cost = _sum(series_values.get("cost_per_request", []))
    input_cost_total = _sum(series_values.get("input_cost_usd_total", []))
    output_cost_total = _sum(series_values.get("output_cost_usd_total", []))
    cache_eval_total = cache_hit_count + cache_miss_count
    stream_failure_total = stream_partial_abort_count + stream_prelude_failure_count
    provider_limit_total = provider_429_request_count + provider_429_stream_count
    first_response_breach_count = sum(
        1 for value in series_values.get("first_response_latency_ms", []) if float(value) > float(first_response_sla_ms)
    )
    total_response_breach_count = sum(
        1 for value in series_values.get("total_latency_ms", []) if float(value) > float(total_response_sla_ms)
    )
    cost_breach_count = sum(
        1 for value in series_values.get("cost_per_request", []) if float(value) > float(cost_sla_usd)
    )
    return {
        "bucket_start": bucket_start_at.isoformat(),
        "request_count": requests,
        "success_count": success_count,
        "failure_count": failure_count,
        "fallback_count": fallback_count,
        "redirect_count": redirect_count,
        "stream_start_count": stream_start_count,
        "stream_complete_count": stream_complete_count,
        "stream_failure_count": stream_failure_count,
        "rate_limit_event_count": rate_limit_event_count,
        "provider_429_count": provider_429_count or provider_limit_total,
        "provider_429_request_count": provider_429_request_count,
        "provider_429_stream_count": provider_429_stream_count,
        "cache_hit_count": cache_hit_count,
        "cache_miss_count": cache_miss_count,
        "cache_bypass_count": cache_bypass_count,
        "exact_cache_hit_count": exact_cache_hit_count,
        "semantic_cache_hit_count": semantic_cache_hit_count,
        "stream_partial_abort_count": stream_partial_abort_count,
        "stream_prelude_failure_count": stream_prelude_failure_count,
        "success_rate_pct": _rate(success_count, requests),
        "error_rate_pct": _rate(failure_count, requests),
        "fallback_rate_pct": _rate(fallback_count, requests),
        "redirect_rate_pct": _rate(redirect_count, requests),
        "provider_429_rate_pct": _rate(provider_429_count or provider_limit_total, requests),
        "cache_hit_rate_pct": _rate(cache_hit_count, cache_eval_total),
        "cache_miss_rate_pct": _rate(cache_miss_count, cache_eval_total),
        "exact_cache_hit_rate_pct": _rate(exact_cache_hit_count, cache_eval_total),
        "semantic_cache_hit_rate_pct": _rate(semantic_cache_hit_count, cache_eval_total),
        "stream_complete_rate_pct": _rate(stream_complete_count, stream_start_count),
        "stream_partial_abort_rate_pct": _rate(stream_partial_abort_count, stream_failure_total or stream_start_count),
        "stream_prelude_failure_rate_pct": _rate(stream_prelude_failure_count, stream_failure_total or stream_start_count),
        "p50_first_response_latency_ms": _percentile(series_values.get("first_response_latency_ms", []), 0.50),
        "avg_first_response_latency_ms": _average(series_values.get("first_response_latency_ms", [])),
        "p95_first_response_latency_ms": _percentile(series_values.get("first_response_latency_ms", []), 0.95),
        "p99_first_response_latency_ms": _percentile(series_values.get("first_response_latency_ms", []), 0.99),
        "p50_total_latency_ms": _percentile(series_values.get("total_latency_ms", []), 0.50),
        "avg_total_latency_ms": _average(series_values.get("total_latency_ms", [])),
        "p95_total_latency_ms": _percentile(series_values.get("total_latency_ms", []), 0.95),
        "p99_total_latency_ms": _percentile(series_values.get("total_latency_ms", []), 0.99),
        "avg_input_tokens": _average(series_values.get("input_tokens", [])),
        "avg_output_tokens": _average(series_values.get("output_tokens", [])),
        "avg_total_tokens": _average(series_values.get("total_tokens", [])),
        "avg_output_tokens_per_second": _average(series_values.get("output_tokens_per_second", [])),
        "avg_cost_per_request": _average(series_values.get("cost_per_request", [])),
        "input_cost_usd_total": input_cost_total,
        "output_cost_usd_total": output_cost_total,
        "total_cost_usd": total_cost,
        "cost_per_1k_requests": _cost_per_thousand_requests(total_cost, requests),
        "first_response_sla_breach_rate_pct": _rate(first_response_breach_count, len(series_values.get("first_response_latency_ms", []))),
        "total_response_sla_breach_rate_pct": _rate(total_response_breach_count, len(series_values.get("total_latency_ms", []))),
        "cost_sla_breach_rate_pct": _rate(cost_breach_count, len(series_values.get("cost_per_request", []))),
    }


def build_llm_timeseries(
    session: Session,
    *,
    settings: Settings,
    provider_key: str,
    model_id: str | None = None,
    window_hours: int = 168,
    bucket_minutes: int = 60,
) -> dict[str, Any]:
    normalized_provider_key = str(provider_key or "").strip()
    normalized_model_id = str(model_id or "").strip() or None
    normalized_window_hours = max(1, min(int(window_hours or 168), 24 * 90))
    normalized_bucket_minutes = max(1, min(int(bucket_minutes or 60), 24 * 60))
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=normalized_window_hours)
    bucket_origin = _bucket_start(since, normalized_bucket_minutes)
    bucket_delta = timedelta(minutes=normalized_bucket_minutes)

    routing_statement = (
        select(RoutingDecisionRecord)
        .where(
            RoutingDecisionRecord.selected_provider == normalized_provider_key,
            RoutingDecisionRecord.created_at >= since,
        )
        .order_by(RoutingDecisionRecord.created_at.asc())
    )
    if normalized_model_id:
        routing_statement = routing_statement.where(RoutingDecisionRecord.selected_model == normalized_model_id)
    routing_rows = list(session.execute(routing_statement).scalars())

    response_statement = (
        select(ModelResponse)
        .where(
            ModelResponse.response_role == "selected_response",
            ModelResponse.provider == normalized_provider_key,
            ModelResponse.created_at >= since,
        )
        .order_by(ModelResponse.created_at.asc())
    )
    if normalized_model_id:
        response_statement = response_statement.where(ModelResponse.model == normalized_model_id)
    response_rows = list(session.execute(response_statement).scalars())

    request_ids = sorted(
        {
            str(row.request_log_id)
            for row in routing_rows
            if getattr(row, "request_log_id", None)
        }
        | {
            str(row.request_log_id)
            for row in response_rows
            if getattr(row, "request_log_id", None)
        }
    )
    request_map: dict[str, RequestLog] = {}
    if request_ids:
        request_statement = select(RequestLog).where(RequestLog.id.in_(request_ids))
        request_map = {str(row.id): row for row in session.execute(request_statement).scalars()}

    buckets: dict[datetime, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    model_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    response_by_request = {
        str(row.request_log_id): row
        for row in response_rows
        if getattr(row, "request_log_id", None)
    }

    request_records: dict[str, dict[str, Any]] = {}
    for row in routing_rows:
        request_log_id = str(row.request_log_id or "")
        if not request_log_id:
            continue
        request_records[request_log_id] = {
            "bucket_key": _bucket_start(row.created_at, normalized_bucket_minutes),
            "model_key": str(row.selected_model or ""),
            "selected_mode": str(row.selected_mode or ""),
            "requested_model": str(getattr(request_map.get(request_log_id), "requested_model", "") or ""),
            "response": response_by_request.get(request_log_id),
        }

    for row in response_rows:
        request_log_id = str(row.request_log_id or "")
        if not request_log_id or request_log_id in request_records:
            continue
        request_records[request_log_id] = {
            "bucket_key": _bucket_start(row.created_at, normalized_bucket_minutes),
            "model_key": str(row.model or ""),
            "selected_mode": "",
            "requested_model": str(getattr(request_map.get(request_log_id), "requested_model", "") or ""),
            "response": row,
        }

    for record in request_records.values():
        bucket_key = record["bucket_key"]
        model_key = str(record["model_key"] or "")
        response_row = record.get("response")
        accumulator = buckets[bucket_key]
        accumulator["request_count"] = [int(accumulator.get("request_count", [0])[0]) + 1]
        model_values[model_key]["request_count"] = [int(model_values[model_key].get("request_count", [0])[0]) + 1]

        is_success = response_row is not None
        count_key = "success_count" if is_success else "failure_count"
        accumulator[count_key] = [int(accumulator.get(count_key, [0])[0]) + 1]
        model_values[model_key][count_key] = [int(model_values[model_key].get(count_key, [0])[0]) + 1]

        if str(record.get("selected_mode") or "") == "fallback":
            accumulator["fallback_count"] = [int(accumulator.get("fallback_count", [0])[0]) + 1]
            model_values[model_key]["fallback_count"] = [int(model_values[model_key].get("fallback_count", [0])[0]) + 1]

        requested_model = str(record.get("requested_model") or "")
        if requested_model and requested_model != model_key:
            accumulator["redirect_count"] = [int(accumulator.get("redirect_count", [0])[0]) + 1]
            model_values[model_key]["redirect_count"] = [int(model_values[model_key].get("redirect_count", [0])[0]) + 1]

        if not response_row:
            continue

        total_latency_ms = float(int(response_row.latency_ms or 0))
        input_tokens = float(int(response_row.input_tokens or 0))
        output_tokens = float(int(response_row.output_tokens or 0))
        total_tokens = input_tokens + output_tokens
        cost_per_request = float(response_row.cost_estimate or Decimal("0"))
        input_cost, output_cost = _response_cost_breakdown(response_row)
        output_tokens_per_second = 0.0
        if total_latency_ms > 0:
            output_tokens_per_second = round(output_tokens / max(total_latency_ms / 1000.0, 0.001), 4)

        accumulator["total_latency_ms"].append(total_latency_ms)
        accumulator["input_tokens"].append(input_tokens)
        accumulator["output_tokens"].append(output_tokens)
        accumulator["total_tokens"].append(total_tokens)
        accumulator["output_tokens_per_second"].append(output_tokens_per_second)
        accumulator["cost_per_request"].append(cost_per_request)
        accumulator["input_cost_usd_total"].append(input_cost)
        accumulator["output_cost_usd_total"].append(output_cost)
        model_values[model_key]["total_latency_ms"].append(total_latency_ms)
        model_values[model_key]["input_tokens"].append(input_tokens)
        model_values[model_key]["output_tokens"].append(output_tokens)
        model_values[model_key]["total_tokens"].append(total_tokens)
        model_values[model_key]["output_tokens_per_second"].append(output_tokens_per_second)
        model_values[model_key]["cost_per_request"].append(cost_per_request)
        model_values[model_key]["input_cost_usd_total"].append(input_cost)
        model_values[model_key]["output_cost_usd_total"].append(output_cost)

        first_response_latency = _first_response_latency_ms(response_row)
        if first_response_latency is not None:
            accumulator["first_response_latency_ms"].append(float(first_response_latency))
            model_values[model_key]["first_response_latency_ms"].append(float(first_response_latency))

    for record, timestamp in _iter_relevant_ops_records(settings, since=since) or []:
        if str(record.get("component") or "") != "proxy.chat":
            continue
        category = str(record.get("category") or "")
        if category not in {"stream", "cache", "rate_limit", "provider_limit"}:
            continue
        data = record.get("data") or {}
        if not isinstance(data, dict):
            continue
        provider = str(data.get("provider_key") or data.get("selected_provider") or "").strip()
        model = str(data.get("model_id") or data.get("selected_model") or data.get("requested_model") or "").strip()
        if provider and provider != normalized_provider_key:
            continue
        if normalized_model_id and model and model != normalized_model_id:
            continue
        if not model and normalized_model_id:
            continue
        bucket_key = _bucket_start(timestamp, normalized_bucket_minutes)
        model_key = normalized_model_id or model or "unknown"
        accumulator = buckets[bucket_key]
        model_accumulator = model_values[model_key]
        message = str(record.get("message") or "").lower()
        if category == "stream":
            if "started" in message:
                accumulator["stream_start_count"] = [int(accumulator.get("stream_start_count", [0])[0]) + 1]
                model_accumulator["stream_start_count"] = [int(model_accumulator.get("stream_start_count", [0])[0]) + 1]
            elif "completed" in message:
                accumulator["stream_complete_count"] = [int(accumulator.get("stream_complete_count", [0])[0]) + 1]
                model_accumulator["stream_complete_count"] = [int(model_accumulator.get("stream_complete_count", [0])[0]) + 1]
            elif "failed" in message:
                accumulator["stream_failure_count"] = [int(accumulator.get("stream_failure_count", [0])[0]) + 1]
                model_accumulator["stream_failure_count"] = [int(model_accumulator.get("stream_failure_count", [0])[0]) + 1]
                abort_phase = str(data.get("stream_abort_phase") or "").strip().lower()
                if abort_phase == "partial_abort":
                    accumulator["stream_partial_abort_count"] = [int(accumulator.get("stream_partial_abort_count", [0])[0]) + 1]
                    model_accumulator["stream_partial_abort_count"] = [int(model_accumulator.get("stream_partial_abort_count", [0])[0]) + 1]
                elif abort_phase == "prelude_failure":
                    accumulator["stream_prelude_failure_count"] = [int(accumulator.get("stream_prelude_failure_count", [0])[0]) + 1]
                    model_accumulator["stream_prelude_failure_count"] = [int(model_accumulator.get("stream_prelude_failure_count", [0])[0]) + 1]
        elif category == "cache":
            outcome = str(data.get("cache_outcome") or "").strip().lower()
            layer = str(data.get("cache_layer") or "").strip().lower()
            if outcome == "hit":
                accumulator["cache_hit_count"] = [int(accumulator.get("cache_hit_count", [0])[0]) + 1]
                model_accumulator["cache_hit_count"] = [int(model_accumulator.get("cache_hit_count", [0])[0]) + 1]
                if layer == "exact":
                    accumulator["exact_cache_hit_count"] = [int(accumulator.get("exact_cache_hit_count", [0])[0]) + 1]
                    model_accumulator["exact_cache_hit_count"] = [int(model_accumulator.get("exact_cache_hit_count", [0])[0]) + 1]
                elif layer == "semantic":
                    accumulator["semantic_cache_hit_count"] = [int(accumulator.get("semantic_cache_hit_count", [0])[0]) + 1]
                    model_accumulator["semantic_cache_hit_count"] = [int(model_accumulator.get("semantic_cache_hit_count", [0])[0]) + 1]
            elif outcome == "miss":
                accumulator["cache_miss_count"] = [int(accumulator.get("cache_miss_count", [0])[0]) + 1]
                model_accumulator["cache_miss_count"] = [int(model_accumulator.get("cache_miss_count", [0])[0]) + 1]
            elif outcome == "bypass":
                accumulator["cache_bypass_count"] = [int(accumulator.get("cache_bypass_count", [0])[0]) + 1]
                model_accumulator["cache_bypass_count"] = [int(model_accumulator.get("cache_bypass_count", [0])[0]) + 1]
        elif category == "rate_limit":
            accumulator["rate_limit_event_count"] = [int(accumulator.get("rate_limit_event_count", [0])[0]) + 1]
            model_accumulator["rate_limit_event_count"] = [int(model_accumulator.get("rate_limit_event_count", [0])[0]) + 1]
        elif category == "provider_limit":
            accumulator["provider_429_count"] = [int(accumulator.get("provider_429_count", [0])[0]) + 1]
            model_accumulator["provider_429_count"] = [int(model_accumulator.get("provider_429_count", [0])[0]) + 1]
            phase = str(data.get("phase") or "").strip().lower()
            if phase == "stream":
                accumulator["provider_429_stream_count"] = [int(accumulator.get("provider_429_stream_count", [0])[0]) + 1]
                model_accumulator["provider_429_stream_count"] = [int(model_accumulator.get("provider_429_stream_count", [0])[0]) + 1]
            else:
                accumulator["provider_429_request_count"] = [int(accumulator.get("provider_429_request_count", [0])[0]) + 1]
                model_accumulator["provider_429_request_count"] = [int(model_accumulator.get("provider_429_request_count", [0])[0]) + 1]

    series: list[dict[str, Any]] = []
    bucket_cursor = bucket_origin
    bucket_end = _bucket_start(now, normalized_bucket_minutes)
    while bucket_cursor <= bucket_end:
        series.append(
            _series_row(
                bucket_cursor,
                buckets.get(bucket_cursor),
                first_response_sla_ms=settings.llmproxy_sla_first_response_ms,
                total_response_sla_ms=settings.llmproxy_sla_total_response_ms,
                cost_sla_usd=settings.llmproxy_sla_cost_per_request_usd,
            )
        )
        bucket_cursor += bucket_delta

    overall_values: dict[str, list[float]] = defaultdict(list)
    overall_counts = defaultdict(int)
    for record in request_records.values():
        overall_counts["request_count"] += 1
        if record.get("response") is not None:
            overall_counts["success_count"] += 1
        else:
            overall_counts["failure_count"] += 1
        if str(record.get("selected_mode") or "") == "fallback":
            overall_counts["fallback_count"] += 1
        requested_model = str(record.get("requested_model") or "")
        model_key = str(record.get("model_key") or "")
        if requested_model and requested_model != model_key:
            overall_counts["redirect_count"] += 1

        row = record.get("response")
        if row is None:
            continue
        total_latency_ms = float(int(row.latency_ms or 0))
        input_tokens = float(int(row.input_tokens or 0))
        output_tokens = float(int(row.output_tokens or 0))
        total_tokens = input_tokens + output_tokens
        input_cost, output_cost = _response_cost_breakdown(row)
        overall_values["total_latency_ms"].append(total_latency_ms)
        overall_values["input_tokens"].append(input_tokens)
        overall_values["output_tokens"].append(output_tokens)
        overall_values["total_tokens"].append(total_tokens)
        overall_values["cost_per_request"].append(float(row.cost_estimate or Decimal("0")))
        overall_values["input_cost_usd_total"].append(input_cost)
        overall_values["output_cost_usd_total"].append(output_cost)
        if total_latency_ms > 0:
            overall_values["output_tokens_per_second"].append(round(output_tokens / max(total_latency_ms / 1000.0, 0.001), 4))
        first_response_latency = _first_response_latency_ms(row)
        if first_response_latency is not None:
            overall_values["first_response_latency_ms"].append(float(first_response_latency))

    for record, _timestamp in _iter_relevant_ops_records(settings, since=since) or []:
        if str(record.get("component") or "") != "proxy.chat":
            continue
        category = str(record.get("category") or "")
        if category not in {"stream", "cache", "rate_limit", "provider_limit"}:
            continue
        data = record.get("data") or {}
        if not isinstance(data, dict):
            continue
        provider = str(data.get("provider_key") or data.get("selected_provider") or "").strip()
        model = str(data.get("model_id") or data.get("selected_model") or data.get("requested_model") or "").strip()
        if provider and provider != normalized_provider_key:
            continue
        if normalized_model_id and model and model != normalized_model_id:
            continue
        if category == "stream":
            message = str(record.get("message") or "").lower()
            if "started" in message:
                overall_counts["stream_start_count"] += 1
            elif "completed" in message:
                overall_counts["stream_complete_count"] += 1
            elif "failed" in message:
                overall_counts["stream_failure_count"] += 1
                abort_phase = str(data.get("stream_abort_phase") or "").strip().lower()
                if abort_phase == "partial_abort":
                    overall_counts["stream_partial_abort_count"] += 1
                elif abort_phase == "prelude_failure":
                    overall_counts["stream_prelude_failure_count"] += 1
        elif category == "cache":
            outcome = str(data.get("cache_outcome") or "").strip().lower()
            layer = str(data.get("cache_layer") or "").strip().lower()
            if outcome == "hit":
                overall_counts["cache_hit_count"] += 1
                if layer == "exact":
                    overall_counts["exact_cache_hit_count"] += 1
                elif layer == "semantic":
                    overall_counts["semantic_cache_hit_count"] += 1
            elif outcome == "miss":
                overall_counts["cache_miss_count"] += 1
            elif outcome == "bypass":
                overall_counts["cache_bypass_count"] += 1
        elif category == "rate_limit":
            overall_counts["rate_limit_event_count"] += 1
        elif category == "provider_limit":
            overall_counts["provider_429_count"] += 1
            if str(data.get("phase") or "").strip().lower() == "stream":
                overall_counts["provider_429_stream_count"] += 1
            else:
                overall_counts["provider_429_request_count"] += 1

    total_request_count = int(overall_counts["request_count"])
    total_cost = _sum(overall_values.get("cost_per_request", []))
    input_cost_total = _sum(overall_values.get("input_cost_usd_total", []))
    output_cost_total = _sum(overall_values.get("output_cost_usd_total", []))
    cache_eval_total = int(overall_counts["cache_hit_count"]) + int(overall_counts["cache_miss_count"])
    stream_failure_total = int(overall_counts["stream_partial_abort_count"]) + int(overall_counts["stream_prelude_failure_count"])
    first_response_breach_count = sum(
        1 for value in overall_values.get("first_response_latency_ms", []) if float(value) > float(settings.llmproxy_sla_first_response_ms)
    )
    total_response_breach_count = sum(
        1 for value in overall_values.get("total_latency_ms", []) if float(value) > float(settings.llmproxy_sla_total_response_ms)
    )
    cost_breach_count = sum(
        1 for value in overall_values.get("cost_per_request", []) if float(value) > float(settings.llmproxy_sla_cost_per_request_usd)
    )

    return {
        "provider_key": normalized_provider_key,
        "model_id": normalized_model_id,
        "window_hours": normalized_window_hours,
        "bucket_minutes": normalized_bucket_minutes,
        "generated_at": now.isoformat(),
        "request_count": total_request_count,
        "series": series,
        "summary": {
            "rate_limit_event_count": int(overall_counts["rate_limit_event_count"]),
            "stream_start_count": int(overall_counts["stream_start_count"]),
            "stream_complete_count": int(overall_counts["stream_complete_count"]),
            "stream_failure_count": int(overall_counts["stream_failure_count"]),
            "stream_partial_abort_count": int(overall_counts["stream_partial_abort_count"]),
            "stream_prelude_failure_count": int(overall_counts["stream_prelude_failure_count"]),
            "provider_429_count": int(overall_counts["provider_429_count"]),
            "provider_429_request_count": int(overall_counts["provider_429_request_count"]),
            "provider_429_stream_count": int(overall_counts["provider_429_stream_count"]),
            "cache_hit_count": int(overall_counts["cache_hit_count"]),
            "cache_miss_count": int(overall_counts["cache_miss_count"]),
            "cache_bypass_count": int(overall_counts["cache_bypass_count"]),
            "exact_cache_hit_count": int(overall_counts["exact_cache_hit_count"]),
            "semantic_cache_hit_count": int(overall_counts["semantic_cache_hit_count"]),
            "success_rate_pct": _rate(int(overall_counts["success_count"]), total_request_count),
            "error_rate_pct": _rate(int(overall_counts["failure_count"]), total_request_count),
            "fallback_rate_pct": _rate(int(overall_counts["fallback_count"]), total_request_count),
            "redirect_rate_pct": _rate(int(overall_counts["redirect_count"]), total_request_count),
            "provider_429_rate_pct": _rate(int(overall_counts["provider_429_count"]), total_request_count),
            "cache_hit_rate_pct": _rate(int(overall_counts["cache_hit_count"]), cache_eval_total),
            "cache_miss_rate_pct": _rate(int(overall_counts["cache_miss_count"]), cache_eval_total),
            "exact_cache_hit_rate_pct": _rate(int(overall_counts["exact_cache_hit_count"]), cache_eval_total),
            "semantic_cache_hit_rate_pct": _rate(int(overall_counts["semantic_cache_hit_count"]), cache_eval_total),
            "stream_complete_rate_pct": _rate(int(overall_counts["stream_complete_count"]), int(overall_counts["stream_start_count"])),
            "stream_partial_abort_rate_pct": _rate(int(overall_counts["stream_partial_abort_count"]), stream_failure_total or int(overall_counts["stream_start_count"])),
            "stream_prelude_failure_rate_pct": _rate(int(overall_counts["stream_prelude_failure_count"]), stream_failure_total or int(overall_counts["stream_start_count"])),
            "p50_first_response_latency_ms": _percentile(overall_values.get("first_response_latency_ms", []), 0.50),
            "avg_first_response_latency_ms": _average(overall_values.get("first_response_latency_ms", [])),
            "p95_first_response_latency_ms": _percentile(overall_values.get("first_response_latency_ms", []), 0.95),
            "p99_first_response_latency_ms": _percentile(overall_values.get("first_response_latency_ms", []), 0.99),
            "p50_total_latency_ms": _percentile(overall_values.get("total_latency_ms", []), 0.50),
            "avg_total_latency_ms": _average(overall_values.get("total_latency_ms", [])),
            "p95_total_latency_ms": _percentile(overall_values.get("total_latency_ms", []), 0.95),
            "p99_total_latency_ms": _percentile(overall_values.get("total_latency_ms", []), 0.99),
            "avg_input_tokens": _average(overall_values.get("input_tokens", [])),
            "avg_output_tokens": _average(overall_values.get("output_tokens", [])),
            "avg_total_tokens": _average(overall_values.get("total_tokens", [])),
            "avg_output_tokens_per_second": _average(overall_values.get("output_tokens_per_second", [])),
            "avg_cost_per_request": _average(overall_values.get("cost_per_request", [])),
            "input_cost_usd_total": input_cost_total,
            "output_cost_usd_total": output_cost_total,
            "total_cost_usd": total_cost,
            "cost_per_1k_requests": _cost_per_thousand_requests(total_cost, total_request_count),
            "first_response_sla_breach_rate_pct": _rate(first_response_breach_count, len(overall_values.get("first_response_latency_ms", []))),
            "total_response_sla_breach_rate_pct": _rate(total_response_breach_count, len(overall_values.get("total_latency_ms", []))),
            "cost_sla_breach_rate_pct": _rate(cost_breach_count, len(overall_values.get("cost_per_request", []))),
        },
        "model_rollups": [
            {
                "model_id": key,
                "request_count": int(values.get("request_count", [0])[0] if "request_count" in values else 0),
                "rate_limit_event_count": int(values.get("rate_limit_event_count", [0])[0] if "rate_limit_event_count" in values else 0),
                "stream_start_count": int(values.get("stream_start_count", [0])[0] if "stream_start_count" in values else 0),
                "stream_complete_count": int(values.get("stream_complete_count", [0])[0] if "stream_complete_count" in values else 0),
                "stream_failure_count": int(values.get("stream_failure_count", [0])[0] if "stream_failure_count" in values else 0),
                "stream_partial_abort_count": int(values.get("stream_partial_abort_count", [0])[0] if "stream_partial_abort_count" in values else 0),
                "stream_prelude_failure_count": int(values.get("stream_prelude_failure_count", [0])[0] if "stream_prelude_failure_count" in values else 0),
                "provider_429_count": int(values.get("provider_429_count", [0])[0] if "provider_429_count" in values else 0),
                "provider_429_request_count": int(values.get("provider_429_request_count", [0])[0] if "provider_429_request_count" in values else 0),
                "provider_429_stream_count": int(values.get("provider_429_stream_count", [0])[0] if "provider_429_stream_count" in values else 0),
                "cache_hit_count": int(values.get("cache_hit_count", [0])[0] if "cache_hit_count" in values else 0),
                "cache_miss_count": int(values.get("cache_miss_count", [0])[0] if "cache_miss_count" in values else 0),
                "cache_bypass_count": int(values.get("cache_bypass_count", [0])[0] if "cache_bypass_count" in values else 0),
                "exact_cache_hit_count": int(values.get("exact_cache_hit_count", [0])[0] if "exact_cache_hit_count" in values else 0),
                "semantic_cache_hit_count": int(values.get("semantic_cache_hit_count", [0])[0] if "semantic_cache_hit_count" in values else 0),
                "success_rate_pct": _rate(int(values.get("success_count", [0])[0] if "success_count" in values else 0), int(values.get("request_count", [0])[0] if "request_count" in values else 0)),
                "error_rate_pct": _rate(int(values.get("failure_count", [0])[0] if "failure_count" in values else 0), int(values.get("request_count", [0])[0] if "request_count" in values else 0)),
                "fallback_rate_pct": _rate(int(values.get("fallback_count", [0])[0] if "fallback_count" in values else 0), int(values.get("request_count", [0])[0] if "request_count" in values else 0)),
                "redirect_rate_pct": _rate(int(values.get("redirect_count", [0])[0] if "redirect_count" in values else 0), int(values.get("request_count", [0])[0] if "request_count" in values else 0)),
                "provider_429_rate_pct": _rate(int(values.get("provider_429_count", [0])[0] if "provider_429_count" in values else 0), int(values.get("request_count", [0])[0] if "request_count" in values else 0)),
                "cache_hit_rate_pct": _rate(
                    int(values.get("cache_hit_count", [0])[0] if "cache_hit_count" in values else 0),
                    int(values.get("cache_hit_count", [0])[0] if "cache_hit_count" in values else 0)
                    + int(values.get("cache_miss_count", [0])[0] if "cache_miss_count" in values else 0),
                ),
                "exact_cache_hit_rate_pct": _rate(
                    int(values.get("exact_cache_hit_count", [0])[0] if "exact_cache_hit_count" in values else 0),
                    int(values.get("cache_hit_count", [0])[0] if "cache_hit_count" in values else 0)
                    + int(values.get("cache_miss_count", [0])[0] if "cache_miss_count" in values else 0),
                ),
                "semantic_cache_hit_rate_pct": _rate(
                    int(values.get("semantic_cache_hit_count", [0])[0] if "semantic_cache_hit_count" in values else 0),
                    int(values.get("cache_hit_count", [0])[0] if "cache_hit_count" in values else 0)
                    + int(values.get("cache_miss_count", [0])[0] if "cache_miss_count" in values else 0),
                ),
                "stream_complete_rate_pct": _rate(
                    int(values.get("stream_complete_count", [0])[0] if "stream_complete_count" in values else 0),
                    int(values.get("stream_start_count", [0])[0] if "stream_start_count" in values else 0),
                ),
                "stream_partial_abort_rate_pct": _rate(
                    int(values.get("stream_partial_abort_count", [0])[0] if "stream_partial_abort_count" in values else 0),
                    (
                        int(values.get("stream_partial_abort_count", [0])[0] if "stream_partial_abort_count" in values else 0)
                        + int(values.get("stream_prelude_failure_count", [0])[0] if "stream_prelude_failure_count" in values else 0)
                    ) or int(values.get("stream_start_count", [0])[0] if "stream_start_count" in values else 0),
                ),
                "stream_prelude_failure_rate_pct": _rate(
                    int(values.get("stream_prelude_failure_count", [0])[0] if "stream_prelude_failure_count" in values else 0),
                    (
                        int(values.get("stream_partial_abort_count", [0])[0] if "stream_partial_abort_count" in values else 0)
                        + int(values.get("stream_prelude_failure_count", [0])[0] if "stream_prelude_failure_count" in values else 0)
                    ) or int(values.get("stream_start_count", [0])[0] if "stream_start_count" in values else 0),
                ),
                "p50_first_response_latency_ms": _percentile(values.get("first_response_latency_ms", []), 0.50),
                "avg_first_response_latency_ms": _average(values.get("first_response_latency_ms", [])),
                "p95_first_response_latency_ms": _percentile(values.get("first_response_latency_ms", []), 0.95),
                "p99_first_response_latency_ms": _percentile(values.get("first_response_latency_ms", []), 0.99),
                "p50_total_latency_ms": _percentile(values.get("total_latency_ms", []), 0.50),
                "avg_total_latency_ms": _average(values.get("total_latency_ms", [])),
                "p95_total_latency_ms": _percentile(values.get("total_latency_ms", []), 0.95),
                "p99_total_latency_ms": _percentile(values.get("total_latency_ms", []), 0.99),
                "avg_input_tokens": _average(values.get("input_tokens", [])),
                "avg_output_tokens": _average(values.get("output_tokens", [])),
                "avg_total_tokens": _average(values.get("total_tokens", [])),
                "avg_output_tokens_per_second": _average(values.get("output_tokens_per_second", [])),
                "avg_cost_per_request": _average(values.get("cost_per_request", [])),
                "input_cost_usd_total": _sum(values.get("input_cost_usd_total", [])),
                "output_cost_usd_total": _sum(values.get("output_cost_usd_total", [])),
                "total_cost_usd": _sum(values.get("cost_per_request", [])),
                "cost_per_1k_requests": _cost_per_thousand_requests(
                    _sum(values.get("cost_per_request", [])),
                    int(values.get("request_count", [0])[0] if "request_count" in values else 0),
                ),
                "first_response_sla_breach_rate_pct": _rate(
                    sum(1 for value in values.get("first_response_latency_ms", []) if float(value) > float(settings.llmproxy_sla_first_response_ms)),
                    len(values.get("first_response_latency_ms", [])),
                ),
                "total_response_sla_breach_rate_pct": _rate(
                    sum(1 for value in values.get("total_latency_ms", []) if float(value) > float(settings.llmproxy_sla_total_response_ms)),
                    len(values.get("total_latency_ms", [])),
                ),
                "cost_sla_breach_rate_pct": _rate(
                    sum(1 for value in values.get("cost_per_request", []) if float(value) > float(settings.llmproxy_sla_cost_per_request_usd)),
                    len(values.get("cost_per_request", [])),
                ),
            }
            for key, values in sorted(
                model_values.items(),
                key=lambda item: (-(int(item[1].get("request_count", [0])[0]) if "request_count" in item[1] else 0), item[0]),
            )
            if key and key != "unknown"
        ],
    }
