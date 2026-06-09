"""Prompt template rendering and storage helpers."""

from __future__ import annotations

import hashlib
import re
from difflib import unified_diff
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import ModelResponse, PromptTemplate, RequestLog, TrainingCandidate

_VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
PROMPT_TEMPLATE_STATUSES = {"draft", "active", "deprecated", "archived"}
PROMPT_TEMPLATE_ROLLOUT_MODES = {"disabled", "canary"}
PROMPT_AUTO_PROMOTION_POLICY_DEFAULTS = {
    "enabled": False,
    "minimum_challenger_requests": 10,
    "min_candidate_yield_improvement_pct": 2.0,
    "max_error_rate_regression_pct": 1.0,
    "max_latency_regression_ms": 250.0,
    "max_cost_regression_usd": 0.001,
}


class PromptTemplateError(ValueError):
    """Raised when prompt templates cannot be rendered or resolved."""


@dataclass
class PromptTemplateRuntimeResolution:
    record: PromptTemplate
    selection_mode: str
    active_version: int | None = None
    challenger_version: int | None = None
    rollout_mode: str | None = None
    rollout_percentage: float | None = None


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        raise PromptTemplateError(f"Missing prompt variable: {key}")


def infer_template_variables(template_text: str) -> list[str]:
    seen: list[str] = []
    for match in _VARIABLE_PATTERN.findall(template_text):
        if match not in seen:
            seen.append(match)
    return seen


def render_template_text(template_text: str, variables: dict[str, Any]) -> str:
    try:
        return template_text.format_map(_SafeFormatDict(variables))
    except PromptTemplateError:
        raise
    except Exception as exc:
        raise PromptTemplateError(str(exc)) from exc


@dataclass
class PromptTemplateCreateInput:
    name: str
    template_text: str
    description: str | None = None
    variables: list[str] | None = None
    model_override: str | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None


def normalize_prompt_template_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower() or "draft"
    if normalized not in PROMPT_TEMPLATE_STATUSES:
        allowed = ", ".join(sorted(PROMPT_TEMPLATE_STATUSES))
        raise PromptTemplateError(f"Invalid prompt template status '{value}'. Allowed values: {allowed}.")
    return normalized


def normalize_prompt_rollout_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower() or "disabled"
    if normalized not in PROMPT_TEMPLATE_ROLLOUT_MODES:
        allowed = ", ".join(sorted(PROMPT_TEMPLATE_ROLLOUT_MODES))
        raise PromptTemplateError(f"Invalid prompt rollout mode '{value}'. Allowed values: {allowed}.")
    return normalized


def _prompt_metadata(record: PromptTemplate) -> dict[str, Any]:
    return dict(record.metadata_json or {})


def _prompt_rollout_payload(record: PromptTemplate) -> dict[str, Any] | None:
    metadata = _prompt_metadata(record)
    rollout = metadata.get("rollout")
    if not isinstance(rollout, dict):
        return None
    mode = normalize_prompt_rollout_mode(rollout.get("mode"))
    if mode == "disabled":
        return None
    try:
        traffic_percentage = float(rollout.get("traffic_percentage", 0))
    except (TypeError, ValueError):
        traffic_percentage = 0.0
    if traffic_percentage <= 0:
        return None
    return {
        "role": "challenger",
        "mode": mode,
        "traffic_percentage": round(traffic_percentage, 2),
    }


def _set_prompt_rollout_payload(record: PromptTemplate, rollout: dict[str, Any] | None) -> None:
    metadata = _prompt_metadata(record)
    if rollout:
        metadata["rollout"] = rollout
    else:
        metadata.pop("rollout", None)
    record.metadata_json = metadata


def normalize_prompt_auto_promotion_policy(value: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(PROMPT_AUTO_PROMOTION_POLICY_DEFAULTS)
    if isinstance(value, dict):
        payload.update(value)

    try:
        minimum_challenger_requests = int(payload.get("minimum_challenger_requests", 10) or 10)
    except (TypeError, ValueError) as exc:
        raise PromptTemplateError("Auto-promotion minimum challenger requests must be an integer.") from exc
    if minimum_challenger_requests < 1:
        raise PromptTemplateError("Auto-promotion minimum challenger requests must be at least 1.")

    def _float_field(key: str, label: str) -> float:
        try:
            return float(payload.get(key, PROMPT_AUTO_PROMOTION_POLICY_DEFAULTS[key]))
        except (TypeError, ValueError) as exc:
            raise PromptTemplateError(f"{label} must be numeric.") from exc

    return {
        "enabled": bool(payload.get("enabled", False)),
        "minimum_challenger_requests": minimum_challenger_requests,
        "min_candidate_yield_improvement_pct": _float_field(
            "min_candidate_yield_improvement_pct",
            "Auto-promotion minimum candidate-yield improvement",
        ),
        "max_error_rate_regression_pct": _float_field(
            "max_error_rate_regression_pct",
            "Auto-promotion maximum error-rate regression",
        ),
        "max_latency_regression_ms": _float_field(
            "max_latency_regression_ms",
            "Auto-promotion maximum latency regression",
        ),
        "max_cost_regression_usd": _float_field(
            "max_cost_regression_usd",
            "Auto-promotion maximum cost regression",
        ),
    }


def _prompt_auto_promotion_policy(record: PromptTemplate | None) -> dict[str, Any]:
    metadata = _prompt_metadata(record) if record is not None else {}
    return normalize_prompt_auto_promotion_policy(metadata.get("auto_promotion_policy"))


def _set_prompt_auto_promotion_policy(record: PromptTemplate, policy: dict[str, Any] | None) -> None:
    metadata = _prompt_metadata(record)
    if policy is not None:
        metadata["auto_promotion_policy"] = normalize_prompt_auto_promotion_policy(policy)
    else:
        metadata.pop("auto_promotion_policy", None)
    record.metadata_json = metadata


def list_prompt_template_versions(session: Session, *, name: str) -> list[PromptTemplate]:
    statement = (
        select(PromptTemplate)
        .where(PromptTemplate.name == name)
        .order_by(PromptTemplate.version.desc())
    )
    return list(session.execute(statement).scalars().all())


def prompt_family_rollout_payload(session: Session, *, name: str) -> dict[str, Any]:
    versions = list_prompt_template_versions(session, name=name)
    if not versions:
        raise PromptTemplateError("Prompt template not found.")
    active_record = next((row for row in versions if str(row.status or "").strip().lower() == "active"), None)
    challenger_record = next((row for row in versions if _prompt_rollout_payload(row)), None)
    challenger_rollout = _prompt_rollout_payload(challenger_record) if challenger_record else None
    policy_record = active_record or versions[0]
    return {
        "name": name,
        "active_version": active_record.version if active_record else None,
        "challenger_version": challenger_record.version if challenger_record else None,
        "mode": challenger_rollout.get("mode") if challenger_rollout else "disabled",
        "traffic_percentage": challenger_rollout.get("traffic_percentage") if challenger_rollout else 0.0,
        "auto_promotion_policy": _prompt_auto_promotion_policy(policy_record),
    }


def list_prompt_templates(session: Session) -> list[PromptTemplate]:
    statement: Select[tuple[PromptTemplate]] = select(PromptTemplate).order_by(PromptTemplate.name.asc(), PromptTemplate.version.desc())
    return list(session.execute(statement).scalars().all())


def get_prompt_template(session: Session, *, name: str, version: int | None = None) -> PromptTemplate | None:
    statement = select(PromptTemplate).where(PromptTemplate.name == name)
    if version is not None:
        statement = statement.where(PromptTemplate.version == version)
    else:
        active_statement = (
            statement.where(PromptTemplate.status == "active")
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        )
        active_record = session.execute(active_statement).scalars().first()
        if active_record is not None:
            return active_record
        statement = statement.order_by(PromptTemplate.version.desc())
    return session.execute(statement.limit(1)).scalars().first()


def create_prompt_template(session: Session, payload: PromptTemplateCreateInput) -> PromptTemplate:
    existing_records = list(
        session.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == payload.name)
            .order_by(PromptTemplate.version.desc())
        ).scalars().all()
    )
    next_version = (
        session.execute(select(func.coalesce(func.max(PromptTemplate.version), 0)).where(PromptTemplate.name == payload.name))
        .scalar_one()
        + 1
    )
    variables = payload.variables or infer_template_variables(payload.template_text)
    has_existing_active = any(str(record.status or "").strip().lower() == "active" for record in existing_records)
    requested_status = payload.status.strip().lower() if isinstance(payload.status, str) and payload.status.strip() else None
    resolved_status = normalize_prompt_template_status(requested_status or ("active" if not has_existing_active else "draft"))
    if resolved_status == "active":
        for record in existing_records:
            if str(record.status or "").strip().lower() == "active":
                record.status = "deprecated"
    record = PromptTemplate(
        id=f"prompttpl_{uuid4().hex}",
        name=payload.name,
        version=int(next_version),
        description=payload.description,
        template_text=payload.template_text,
        variables_json=variables,
        model_override=payload.model_override,
        status=resolved_status,
        metadata_json=payload.metadata or {},
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def set_prompt_template_status(
    session: Session,
    *,
    name: str,
    version: int,
    status: str,
) -> PromptTemplate:
    record = get_prompt_template(session, name=name, version=version)
    if record is None:
        raise PromptTemplateError("Prompt template version not found.")
    normalized_status = normalize_prompt_template_status(status)
    if normalized_status == "active":
        sibling_records = list(
            session.execute(
                select(PromptTemplate).where(
                    PromptTemplate.name == name,
                    PromptTemplate.version != version,
                    PromptTemplate.status == "active",
                )
            ).scalars().all()
        )
        for sibling in sibling_records:
            sibling.status = "deprecated"
    record.status = normalized_status
    session.commit()
    session.refresh(record)
    return record


def set_prompt_template_rollout(
    session: Session,
    *,
    name: str,
    challenger_version: int | None,
    mode: str,
    traffic_percentage: float | None = None,
) -> dict[str, Any]:
    normalized_mode = normalize_prompt_rollout_mode(mode)
    versions = list_prompt_template_versions(session, name=name)
    if not versions:
        raise PromptTemplateError("Prompt template not found.")
    active_record = next((row for row in versions if str(row.status or "").strip().lower() == "active"), None)
    if active_record is None:
        raise PromptTemplateError("Prompt template has no active version to compare against.")
    challenger_record = None
    if challenger_version is not None:
        challenger_record = next((row for row in versions if row.version == challenger_version), None)
        if challenger_record is None:
            raise PromptTemplateError("Prompt challenger version not found.")
        if challenger_record.version == active_record.version:
            raise PromptTemplateError("Active version cannot also be configured as the challenger.")
    for row in versions:
        _set_prompt_rollout_payload(row, None)
    if normalized_mode != "disabled":
        if challenger_record is None:
            raise PromptTemplateError("A challenger version is required when rollout mode is enabled.")
        percentage = float(traffic_percentage or 0)
        if percentage <= 0 or percentage >= 100:
            raise PromptTemplateError("Canary rollout percentage must be greater than 0 and less than 100.")
        _set_prompt_rollout_payload(
            challenger_record,
            {
                "mode": normalized_mode,
                "traffic_percentage": round(percentage, 2),
            },
        )
    session.commit()
    for row in versions:
        session.refresh(row)
    return prompt_family_rollout_payload(session, name=name)


def set_prompt_auto_promotion_policy(
    session: Session,
    *,
    name: str,
    enabled: bool,
    minimum_challenger_requests: int = 10,
    min_candidate_yield_improvement_pct: float = 2.0,
    max_error_rate_regression_pct: float = 1.0,
    max_latency_regression_ms: float = 250.0,
    max_cost_regression_usd: float = 0.001,
) -> dict[str, Any]:
    versions = list_prompt_template_versions(session, name=name)
    if not versions:
        raise PromptTemplateError("Prompt template not found.")
    policy = normalize_prompt_auto_promotion_policy(
        {
            "enabled": enabled,
            "minimum_challenger_requests": minimum_challenger_requests,
            "min_candidate_yield_improvement_pct": min_candidate_yield_improvement_pct,
            "max_error_rate_regression_pct": max_error_rate_regression_pct,
            "max_latency_regression_ms": max_latency_regression_ms,
            "max_cost_regression_usd": max_cost_regression_usd,
        }
    )
    for row in versions:
        _set_prompt_auto_promotion_policy(row, policy)
    session.commit()
    for row in versions:
        session.refresh(row)
    return prompt_family_rollout_payload(session, name=name)


def prompt_template_payload(item: PromptTemplate) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "version": item.version,
        "description": item.description,
        "template_text": item.template_text,
        "variables": list(item.variables_json or []),
        "model_override": item.model_override,
        "status": item.status,
        "is_active": str(item.status or "").strip().lower() == "active",
        "rollout": _prompt_rollout_payload(item),
        "metadata": item.metadata_json or {},
        "created_at": item.created_at,
    }


def _prompt_template_identity_from_payload(
    payload: dict[str, Any] | None,
    effective_payload: dict[str, Any] | None = None,
) -> tuple[str | None, int | None]:
    metadata = payload.get("metadata") if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else {}
    effective_metadata = (
        effective_payload.get("metadata")
        if isinstance(effective_payload, dict) and isinstance(effective_payload.get("metadata"), dict)
        else {}
    )
    name = metadata.get("prompt_template_name") or effective_metadata.get("prompt_template_name")
    version_raw = metadata.get("prompt_template_version") or effective_metadata.get("prompt_template_version")
    version: int | None = None
    if version_raw not in (None, ""):
        try:
            version = int(version_raw)
        except (TypeError, ValueError):
            version = None
    return (str(name) if name else None, version)


def build_prompt_template_metrics(session: Session) -> dict[tuple[str, int], dict[str, Any]]:
    request_rows = list(session.execute(select(RequestLog)).scalars().all())
    response_rows = list(
        session.execute(
            select(ModelResponse)
            .where(ModelResponse.response_role == "selected_response")
            .order_by(ModelResponse.created_at.desc())
        ).scalars().all()
    )
    candidate_rows = list(session.execute(select(TrainingCandidate)).scalars().all())

    latest_responses: dict[str, ModelResponse] = {}
    for row in response_rows:
        if row.request_log_id and row.request_log_id not in latest_responses:
            latest_responses[row.request_log_id] = row

    metrics: dict[tuple[str, int], dict[str, Any]] = {}

    def _ensure_metric(key: tuple[str, int]) -> dict[str, Any]:
        bucket = metrics.get(key)
        if bucket is None:
            bucket = {
                "request_count": 0,
                "successful_request_count": 0,
                "error_count": 0,
                "candidate_count": 0,
                "approved_candidate_count": 0,
                "total_latency_ms": 0.0,
                "total_cost_estimate": 0.0,
            }
            metrics[key] = bucket
        return bucket

    for request in request_rows:
        name, version = _prompt_template_identity_from_payload(request.request_json or {}, request.effective_request_json or {})
        if not name or version is None:
            continue
        key = (name, version)
        bucket = _ensure_metric(key)
        bucket["request_count"] += 1
        response = latest_responses.get(request.id)
        if response is None:
            continue
        bucket["successful_request_count"] += 1
        bucket["total_latency_ms"] += float(response.latency_ms or 0)
        cost_value = response.cost_estimate
        if isinstance(cost_value, Decimal):
            bucket["total_cost_estimate"] += float(cost_value)
        elif cost_value is not None:
            try:
                bucket["total_cost_estimate"] += float(cost_value)
            except (TypeError, ValueError):
                pass

    for candidate in candidate_rows:
        metadata = candidate.metadata_json or {}
        name = metadata.get("prompt_template_name")
        version_raw = metadata.get("prompt_template_version")
        if not name or version_raw in (None, ""):
            continue
        try:
            version = int(version_raw)
        except (TypeError, ValueError):
            continue
        key = (str(name), version)
        bucket = _ensure_metric(key)
        bucket["candidate_count"] += 1
        if str(candidate.approval_status or "").strip().lower() == "approved":
            bucket["approved_candidate_count"] += 1

    for bucket in metrics.values():
        request_count = int(bucket["request_count"])
        success_count = int(bucket["successful_request_count"])
        candidate_count = int(bucket["candidate_count"])
        approved_candidate_count = int(bucket["approved_candidate_count"])
        bucket["error_count"] = max(request_count - success_count, 0)
        bucket["error_rate_pct"] = round((bucket["error_count"] / request_count) * 100, 2) if request_count else 0.0
        bucket["candidate_yield_rate_pct"] = round((candidate_count / request_count) * 100, 2) if request_count else 0.0
        bucket["approval_rate_pct"] = round((approved_candidate_count / candidate_count) * 100, 2) if candidate_count else 0.0
        bucket["avg_latency_ms"] = round(bucket["total_latency_ms"] / success_count, 2) if success_count else None
        bucket["avg_cost_estimate"] = round(bucket["total_cost_estimate"] / success_count, 6) if success_count else None
        bucket["total_cost_estimate"] = round(bucket["total_cost_estimate"], 6)
        del bucket["total_latency_ms"]
    return metrics


def recommend_prompt_template_rollout(
    comparison: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline_metrics = comparison.get("baseline", {}).get("metrics", {}) if isinstance(comparison.get("baseline"), dict) else {}
    challenger_metrics = comparison.get("comparison", {}).get("metrics", {}) if isinstance(comparison.get("comparison"), dict) else {}
    deltas = comparison.get("deltas", {}) if isinstance(comparison.get("deltas"), dict) else {}
    normalized_policy = normalize_prompt_auto_promotion_policy(policy)
    minimum_requests = int(normalized_policy.get("minimum_challenger_requests", 10) or 10)
    max_error_regression = float(normalized_policy.get("max_error_rate_regression_pct", 1.0) or 0.0)
    max_latency_regression = float(normalized_policy.get("max_latency_regression_ms", 250.0) or 0.0)
    max_cost_regression = float(normalized_policy.get("max_cost_regression_usd", 0.001) or 0.0)
    min_yield_improvement = float(normalized_policy.get("min_candidate_yield_improvement_pct", 2.0) or 0.0)

    baseline_requests = int(baseline_metrics.get("request_count") or 0)
    challenger_requests = int(challenger_metrics.get("request_count") or 0)
    total_requests = baseline_requests + challenger_requests
    candidate_yield_delta = float(deltas.get("candidate_yield_rate_pct") or 0.0)
    error_rate_delta = float(deltas.get("error_rate_pct") or 0.0)
    latency_delta = deltas.get("avg_latency_ms")
    cost_delta = deltas.get("avg_cost_estimate")
    latency_delta_value = float(latency_delta) if latency_delta not in (None, "") else None
    cost_delta_value = float(cost_delta) if cost_delta not in (None, "") else None

    recommendation = {
        "action": "continue_canary",
        "confidence": "low",
        "summary": "More evidence is required before changing the live prompt version.",
        "reasons": [],
        "guards": {
            "minimum_challenger_requests": minimum_requests,
            "max_error_rate_regression_pct": max_error_regression,
            "max_latency_regression_ms": max_latency_regression,
            "max_cost_regression_usd": max_cost_regression,
            "min_candidate_yield_improvement_pct": min_yield_improvement,
        },
    }

    if challenger_requests < minimum_requests:
        recommendation["reasons"].append(
            f"Challenger traffic is still light ({challenger_requests} requests); keep canarying until it reaches at least {minimum_requests} requests."
        )
        if total_requests < 10:
            recommendation["summary"] = "The prompt family has not seen enough traffic for a guarded recommendation yet."
        return recommendation

    severe_regression = False
    if error_rate_delta > max_error_regression:
        severe_regression = True
        recommendation["reasons"].append(
            f"Error rate regressed by {round(error_rate_delta, 2)} percentage points, above the {round(max_error_regression, 2)}-point guard."
        )
    if latency_delta_value is not None and latency_delta_value > max_latency_regression:
        severe_regression = True
        recommendation["reasons"].append(
            f"Average latency increased by {round(latency_delta_value, 2)} ms, above the {round(max_latency_regression, 2)} ms guard."
        )
    if cost_delta_value is not None and cost_delta_value > max_cost_regression:
        severe_regression = True
        recommendation["reasons"].append(
            f"Average request cost increased by ${round(cost_delta_value, 6)}, above the ${round(max_cost_regression, 6)} guard."
        )
    if severe_regression:
        recommendation["action"] = "keep_active"
        recommendation["confidence"] = "high"
        recommendation["summary"] = "Keep the active baseline. The challenger is materially worse on guarded rollout checks."
        return recommendation

    improvement_signals = 0
    if candidate_yield_delta >= min_yield_improvement:
        improvement_signals += 1
        recommendation["reasons"].append(
            f"Candidate yield improved by {round(candidate_yield_delta, 2)} percentage points, clearing the {round(min_yield_improvement, 2)}-point promotion target."
        )
    if error_rate_delta <= 0:
        improvement_signals += 1
        recommendation["reasons"].append("Error rate did not regress.")
    if latency_delta_value is None or latency_delta_value <= 0:
        improvement_signals += 1
        recommendation["reasons"].append("Average latency stayed flat or improved.")
    if cost_delta_value is None or cost_delta_value <= 0:
        improvement_signals += 1
        recommendation["reasons"].append("Average cost stayed flat or improved.")

    if improvement_signals >= 3:
        recommendation["action"] = "promote_challenger"
        recommendation["confidence"] = "medium" if challenger_requests < max(25, minimum_requests * 2) else "high"
        recommendation["summary"] = "The challenger is outperforming the active baseline within the guarded rollout limits."
        return recommendation

    recommendation["confidence"] = "medium"
    recommendation["summary"] = "The challenger is viable, but the measured gains are not yet decisive enough to promote."
    if not recommendation["reasons"]:
        recommendation["reasons"].append("Signals are mixed across yield, latency, cost, and error rate.")
    return recommendation


def compare_prompt_template_versions(
    session: Session,
    *,
    name: str,
    baseline_version: int | None = None,
    compare_version: int | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    versions = list_prompt_template_versions(session, name=name)
    if not versions:
        raise PromptTemplateError("Prompt template not found.")
    active_record = next((row for row in versions if str(row.status or "").strip().lower() == "active"), None)
    challenger_record = next((row for row in versions if _prompt_rollout_payload(row)), None)
    baseline_record = get_prompt_template(session, name=name, version=baseline_version) if baseline_version is not None else active_record or versions[0]
    if baseline_record is None:
        raise PromptTemplateError("Baseline prompt version not found.")
    if compare_version is not None:
        compare_record = get_prompt_template(session, name=name, version=compare_version)
    else:
        compare_record = challenger_record or next((row for row in versions if row.version != baseline_record.version), None)
    if compare_record is None:
        raise PromptTemplateError("No comparison prompt version is available for this template.")
    metrics = build_prompt_template_metrics(session)
    baseline_payload = prompt_template_payload(baseline_record)
    compare_payload = prompt_template_payload(compare_record)
    baseline_metrics = metrics.get((baseline_record.name, baseline_record.version), {})
    compare_metrics = metrics.get((compare_record.name, compare_record.version), {})
    baseline_payload["metrics"] = baseline_metrics
    compare_payload["metrics"] = compare_metrics
    metric_keys = (
        "request_count",
        "candidate_count",
        "candidate_yield_rate_pct",
        "avg_latency_ms",
        "avg_cost_estimate",
        "error_rate_pct",
    )
    deltas: dict[str, float | int | None] = {}
    for key in metric_keys:
        left = baseline_metrics.get(key)
        right = compare_metrics.get(key)
        if left is None or right is None:
            deltas[key] = None
            continue
        delta = float(right) - float(left)
        if key in {"request_count", "candidate_count"}:
            deltas[key] = int(round(delta))
        else:
            deltas[key] = round(delta, 4)
    return {
        "name": name,
        "baseline": baseline_payload,
        "comparison": compare_payload,
        "deltas": deltas,
        "family_rollout": prompt_family_rollout_payload(session, name=name),
        "recommendation": recommend_prompt_template_rollout(
            {
                "baseline": baseline_payload,
                "comparison": compare_payload,
                "deltas": deltas,
            },
            policy=policy,
        ),
    }


def promote_prompt_template_challenger(
    session: Session,
    *,
    name: str,
    challenger_version: int | None = None,
    guarded: bool = True,
) -> dict[str, Any]:
    family_rollout = prompt_family_rollout_payload(session, name=name)
    target_version = challenger_version if challenger_version is not None else family_rollout.get("challenger_version")
    if target_version is None:
        raise PromptTemplateError("Prompt template has no challenger version to promote.")
    comparison = compare_prompt_template_versions(session, name=name, compare_version=int(target_version))
    recommendation = comparison.get("recommendation", {})
    if guarded and str(recommendation.get("action") or "").strip().lower() != "promote_challenger":
        raise PromptTemplateError(str(recommendation.get("summary") or "The challenger is not eligible for guarded promotion."))
    baseline_version = comparison.get("baseline", {}).get("version")
    promoted_record = set_prompt_template_status(
        session,
        name=name,
        version=int(target_version),
        status="active",
    )
    updated_rollout = set_prompt_template_rollout(
        session,
        name=name,
        challenger_version=None,
        mode="disabled",
        traffic_percentage=None,
    )
    return {
        "name": name,
        "promoted_version": promoted_record.version,
        "previous_active_version": baseline_version,
        "family_rollout": updated_rollout,
        "recommendation": recommendation,
        "comparison": comparison,
    }


def evaluate_prompt_auto_promotion(
    session: Session,
    *,
    name: str,
) -> dict[str, Any]:
    family_rollout = prompt_family_rollout_payload(session, name=name)
    policy = normalize_prompt_auto_promotion_policy(family_rollout.get("auto_promotion_policy"))
    challenger_version = family_rollout.get("challenger_version")
    if not policy.get("enabled"):
        return {
            "name": name,
            "executed": False,
            "eligible": False,
            "policy": policy,
            "family_rollout": family_rollout,
            "summary": "Auto-promotion is disabled for this prompt family.",
        }
    if challenger_version is None:
        return {
            "name": name,
            "executed": False,
            "eligible": False,
            "policy": policy,
            "family_rollout": family_rollout,
            "summary": "No challenger is configured for this prompt family.",
        }
    comparison = compare_prompt_template_versions(
        session,
        name=name,
        compare_version=int(challenger_version),
        policy=policy,
    )
    recommendation = comparison.get("recommendation", {})
    eligible = str(recommendation.get("action") or "").strip().lower() == "promote_challenger"
    if not eligible:
        return {
            "name": name,
            "executed": False,
            "eligible": False,
            "policy": policy,
            "family_rollout": family_rollout,
            "comparison": comparison,
            "recommendation": recommendation,
            "summary": str(recommendation.get("summary") or "The challenger is not yet eligible for auto-promotion."),
        }
    promotion = promote_prompt_template_challenger(
        session,
        name=name,
        challenger_version=int(challenger_version),
        guarded=False,
    )
    return {
        "name": name,
        "executed": True,
        "eligible": True,
        "policy": policy,
        "promotion": promotion,
        "recommendation": recommendation,
        "comparison": comparison,
        "family_rollout": promotion.get("family_rollout"),
        "summary": f"Auto-promoted challenger v{promotion.get('promoted_version')} for prompt family {name}.",
    }


def resolve_runtime_prompt_template(
    session: Session,
    *,
    name: str,
    version: int | None = None,
    selection_key: str | None = None,
) -> PromptTemplateRuntimeResolution:
    if version is not None:
        record = get_prompt_template(session, name=name, version=version)
        if record is None:
            raise PromptTemplateError("Prompt template not found.")
        family_rollout = prompt_family_rollout_payload(session, name=name)
        return PromptTemplateRuntimeResolution(
            record=record,
            selection_mode="explicit",
            active_version=family_rollout.get("active_version"),
            challenger_version=family_rollout.get("challenger_version"),
            rollout_mode=family_rollout.get("mode"),
            rollout_percentage=family_rollout.get("traffic_percentage"),
        )
    versions = list_prompt_template_versions(session, name=name)
    if not versions:
        raise PromptTemplateError("Prompt template not found.")
    active_record = next((row for row in versions if str(row.status or "").strip().lower() == "active"), None)
    if active_record is None:
        raise PromptTemplateError("Prompt template has no active version.")
    challenger_record = next((row for row in versions if _prompt_rollout_payload(row)), None)
    challenger_rollout = _prompt_rollout_payload(challenger_record) if challenger_record else None
    if challenger_record and challenger_rollout and selection_key:
        percentage = float(challenger_rollout.get("traffic_percentage") or 0)
        if percentage > 0:
            digest = hashlib.sha256(f"{name}:{selection_key}".encode("utf-8")).hexdigest()
            bucket = int(digest[:8], 16) % 10000
            threshold = int(round((percentage / 100.0) * 10000))
            if bucket < threshold:
                return PromptTemplateRuntimeResolution(
                    record=challenger_record,
                    selection_mode="challenger_canary",
                    active_version=active_record.version,
                    challenger_version=challenger_record.version,
                    rollout_mode=str(challenger_rollout.get("mode") or "canary"),
                    rollout_percentage=percentage,
                )
    return PromptTemplateRuntimeResolution(
        record=active_record,
        selection_mode="active",
        active_version=active_record.version,
        challenger_version=challenger_record.version if challenger_record else None,
        rollout_mode=str(challenger_rollout.get("mode") or "disabled") if challenger_rollout else "disabled",
        rollout_percentage=float(challenger_rollout.get("traffic_percentage") or 0) if challenger_rollout else 0.0,
    )


def render_prompt_template(
    session: Session,
    *,
    name: str,
    version: int | None = None,
    variables: dict[str, Any] | None = None,
) -> tuple[PromptTemplate, str]:
    record = get_prompt_template(session, name=name, version=version)
    if record is None:
        raise PromptTemplateError("Prompt template not found.")
    rendered = render_template_text(record.template_text, variables or {})
    return record, rendered


def diff_prompt_templates(
    session: Session,
    *,
    name: str,
    from_version: int,
    to_version: int,
) -> dict[str, Any]:
    left = get_prompt_template(session, name=name, version=from_version)
    right = get_prompt_template(session, name=name, version=to_version)
    if left is None or right is None:
        raise PromptTemplateError("Prompt template version not found.")
    diff_lines = list(
        unified_diff(
            left.template_text.splitlines(),
            right.template_text.splitlines(),
            fromfile=f"{name}@v{from_version}",
            tofile=f"{name}@v{to_version}",
            lineterm="",
        )
    )
    return {
        "name": name,
        "from_version": from_version,
        "to_version": to_version,
        "from_variables": list(left.variables_json or []),
        "to_variables": list(right.variables_json or []),
        "from_model_override": left.model_override,
        "to_model_override": right.model_override,
        "unified_diff": "\n".join(diff_lines),
    }
