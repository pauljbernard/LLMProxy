"""Routing engine."""

from dataclasses import dataclass, field
from hashlib import sha256

from app.config import Settings
from app.integration.routing_policy import get_latest_policy_record
from app.proxy.policy import build_routing_decision
from app.schemas.chat import ChatCompletionRequest
from app.schemas.routing import FallbackTarget, RankedAlternative, RoutingDecision


@dataclass
class SelectedRoute:
    provider_key: str
    decision: RoutingDecision
    shadow_provider_keys: list[str]
    selected_entry: dict[str, object] | None = None
    entry_index: dict[str, dict[str, object]] = field(default_factory=dict)


def _is_canary_session(session_id: str, canary_percent: float) -> bool:
    bucket = int(sha256(session_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < int(canary_percent * 100)


def _entry_tags(entry: dict[str, object]) -> list[str]:
    values = list(entry.get("tags", [])) + list(entry.get("labels", []))
    seen: list[str] = []
    for item in values:
        value = str(item).strip().lower()
        if value and value not in seen:
            seen.append(value)
    return seen


def _entry_regions(entry: dict[str, object]) -> list[str]:
    return [str(item).strip().lower() for item in entry.get("regions", []) if str(item).strip()]


def _match_policy_entries(
    policy: dict[str, object],
    *,
    domain: str,
    task_type: str,
    route_tags: list[str] | None = None,
    region: str = "",
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    route_tags = [str(item).strip().lower() for item in (route_tags or []) if str(item).strip()]
    entries = [
        entry
        for entry in policy.get("entries", [])
        if (not entry.get("domains") or domain in entry.get("domains", []))
        and (not entry.get("task_types") or task_type in entry.get("task_types", []))
        and (not _entry_tags(entry) or bool(set(_entry_tags(entry)) & set(route_tags)))
        and (not _entry_regions(entry) or (region and region in _entry_regions(entry)))
    ]
    production = [entry for entry in entries if entry.get("deployment_mode") == "production"]
    canary = [entry for entry in entries if entry.get("deployment_mode") == "canary"]
    shadow = [entry for entry in entries if entry.get("deployment_mode") == "shadow"]
    return production, canary, shadow


def _entry_type(entry: dict[str, object]) -> str:
    explicit = str(entry.get("entry_type", "")).strip().lower()
    if explicit in {"frontier", "local"}:
        return explicit
    provider_key = str(entry.get("provider_key", ""))
    provider_family = str(entry.get("provider_family", "")).lower()
    if provider_key.startswith("local:") or provider_family == "local runtime":
        return "local"
    return "frontier"


def _entry_specificity(entry: dict[str, object], *, task_type: str) -> int:
    task_types = [str(item) for item in entry.get("task_types", [])]
    return 1 if task_types and task_type in task_types else 0


def _entry_tag_specificity(entry: dict[str, object], *, route_tags: list[str]) -> int:
    entry_tags = _entry_tags(entry)
    return len(set(entry_tags) & set(route_tags)) if entry_tags else 0


def _entry_region_specificity(entry: dict[str, object], *, region: str) -> int:
    entry_regions = _entry_regions(entry)
    return 1 if region and region in entry_regions else 0


def _provider_cost_hint(provider_key: str) -> float:
    return {
        "local": 0.0,
        "ollama": 0.0,
        "huggingface_tgi": 0.0,
        "fireworks": 0.000003,
        "groq": 0.000003,
        "cloudflare_workers_ai": 0.000004,
        "deepseek": 0.000002,
        "together": 0.000004,
        "mistral": 0.000008,
        "perplexity": 0.00001,
        "vertex_ai": 0.00001,
        "cohere": 0.000015,
        "google": 0.000018,
        "xai": 0.000019,
        "openai": 0.00002,
        "azure_openai": 0.000021,
        "bedrock": 0.000023,
        "anthropic": 0.000024,
    }.get(provider_key, 0.00002)


def _provider_latency_hint(provider_key: str) -> float:
    return {
        "local": 35.0,
        "ollama": 35.0,
        "huggingface_tgi": 45.0,
        "groq": 60.0,
        "fireworks": 70.0,
        "cloudflare_workers_ai": 75.0,
        "deepseek": 90.0,
        "together": 100.0,
        "openai": 140.0,
        "azure_openai": 145.0,
        "xai": 150.0,
        "cohere": 160.0,
        "vertex_ai": 170.0,
        "google": 180.0,
        "mistral": 185.0,
        "anthropic": 220.0,
        "bedrock": 240.0,
    }.get(provider_key, 150.0)


def _entry_quality_score(entry: dict[str, object]) -> float:
    quality_summary = entry.get("quality_summary", {})
    if isinstance(quality_summary, dict):
        value = quality_summary.get("overall_score")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _entry_cost_score(entry: dict[str, object]) -> float:
    for key in ("price_per_token", "cost_per_token", "estimated_cost_per_token"):
        value = entry.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                break
    cost_summary = entry.get("cost_summary", {})
    if isinstance(cost_summary, dict):
        for key in ("price_per_token", "estimated_cost_per_token"):
            value = cost_summary.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    break
    provider_key = str(entry.get("provider_key", ""))
    if provider_key.startswith("local:"):
        return _provider_cost_hint("local")
    return _provider_cost_hint(provider_key)


def _entry_latency_score(entry: dict[str, object]) -> float:
    for key in ("latency_ms", "median_latency_ms", "p50_latency_ms"):
        value = entry.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                break
    latency_summary = entry.get("latency_summary", {})
    if isinstance(latency_summary, dict):
        for key in ("p50_ms", "median_ms"):
            value = latency_summary.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    break
    provider_key = str(entry.get("provider_key", ""))
    if provider_key.startswith("local:"):
        return _provider_latency_hint("local")
    return _provider_latency_hint(provider_key)


def _entry_recency(entry: dict[str, object]) -> str:
    return str(entry.get("deployed_at") or entry.get("created_at") or entry.get("policy_version") or entry.get("model_alias") or "")


def _entry_sort_key(
    entry: dict[str, object],
    *,
    task_type: str,
    route_tags: list[str],
    region: str,
    strategy: str,
) -> tuple[float, ...] | tuple[float, ... , str]:
    specificity = float(_entry_specificity(entry, task_type=task_type))
    tag_specificity = float(_entry_tag_specificity(entry, route_tags=route_tags))
    region_specificity = float(_entry_region_specificity(entry, region=region))
    quality = _entry_quality_score(entry)
    cost = _entry_cost_score(entry)
    latency = _entry_latency_score(entry)
    recency = _entry_recency(entry)
    if strategy == "latency":
        return (specificity, tag_specificity, region_specificity, -latency, quality, -cost, recency)
    if strategy == "cost":
        return (specificity, tag_specificity, region_specificity, -cost, quality, -latency, recency)
    if strategy == "quality":
        return (specificity, tag_specificity, region_specificity, quality, -cost, -latency, recency)
    balanced = quality - (cost * 1000.0) - (latency / 1000.0)
    return (specificity, tag_specificity, region_specificity, balanced, quality, -cost, -latency, recency)


def _select_best_entry(
    entries: list[dict[str, object]],
    *,
    task_type: str,
    route_tags: list[str],
    region: str,
    strategy: str,
) -> dict[str, object] | None:
    if not entries:
        return None
    ranked = sorted(
        entries,
        key=lambda entry: _entry_sort_key(entry, task_type=task_type, route_tags=route_tags, region=region, strategy=strategy),
        reverse=True,
    )
    return ranked[0]


def _entry_index(policy: dict[str, object]) -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    for entry in policy.get("entries", []):
        provider_key = str(entry.get("provider_key", ""))
        if provider_key:
            index[provider_key] = entry
    return index


def _default_fallbacks(*, settings: Settings, primary_provider: str) -> list[FallbackTarget]:
    ordered = [
        ("openai", settings.llmproxy_openai_model),
        ("anthropic", settings.llmproxy_anthropic_model),
        ("google", settings.llmproxy_google_model),
        ("xai", settings.llmproxy_xai_model),
        ("ollama", settings.llmproxy_ollama_model),
    ]
    fallbacks: list[FallbackTarget] = []
    order = 1
    for provider, model in ordered:
        if provider == primary_provider:
            continue
        fallbacks.append(FallbackTarget(order=order, provider=provider, model=model))
        order += 1
    return fallbacks


def _default_frontier_entries(settings: Settings) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    model_by_provider = {
        "openai": settings.llmproxy_openai_model,
        "anthropic": settings.llmproxy_anthropic_model,
        "google": settings.llmproxy_google_model,
        "xai": settings.llmproxy_xai_model,
        "groq": settings.llmproxy_groq_model,
        "mistral": settings.llmproxy_mistral_model,
        "deepseek": settings.llmproxy_deepseek_model,
        "cohere": settings.llmproxy_cohere_model,
        "together": settings.llmproxy_together_model,
        "fireworks": settings.llmproxy_fireworks_model,
        "perplexity": settings.llmproxy_perplexity_model,
        "cloudflare_workers_ai": settings.llmproxy_cloudflare_workers_ai_model,
        "huggingface_tgi": settings.llmproxy_huggingface_tgi_model,
        "vertex_ai": settings.llmproxy_vertex_ai_model,
        "azure_openai": settings.llmproxy_azure_openai_model,
        "bedrock": settings.llmproxy_bedrock_model,
    }
    configured = settings.provider_configuration
    for item in settings.llmproxy_frontier_default_entries:
        entry = dict(item)
        provider_key = str(entry.get("provider_key", ""))
        if not provider_key:
            continue
        if configured.get(provider_key, False) is False and any(configured.values()):
            continue
        entry.setdefault("model_id", model_by_provider.get(provider_key, settings.llmproxy_openai_model))
        entries.append(entry)
    if entries:
        return {"entries": entries}
    return {
        "entries": [
            {
                "entry_type": "frontier",
                "provider_key": "openai",
                "provider_family": "OpenAI",
                "model_id": settings.llmproxy_openai_model,
                "domains": [],
                "task_types": [],
                "deployment_mode": "production",
                "decision_rationale": "Fallback default frontier entry for general-purpose coverage.",
            }
        ]
    }


def _policy_ranked_alternatives(
    *,
    selected_entry: dict[str, object],
    shadow_entries: list[dict[str, object]],
    settings: Settings,
) -> list[RankedAlternative]:
    alternatives = list(selected_entry.get("ranked_alternatives", []))
    if alternatives:
        return [
            RankedAlternative(
                rank=int(item["rank"]),
                provider=str(item["provider"]),
                model=str(item["model"]),
                score=float(item["score"]),
            )
            for item in alternatives
        ]
    ranked: list[RankedAlternative] = [
        RankedAlternative(
            rank=1,
            provider=str(selected_entry.get("provider_key", "ollama")),
            model=str(selected_entry.get("model_alias", selected_entry.get("model_id", settings.llmproxy_ollama_model))),
            score=0.96,
        )
    ]
    for index, entry in enumerate(shadow_entries, start=2):
        ranked.append(
            RankedAlternative(
                rank=index,
                provider=str(entry.get("provider_key", "ollama")),
                model=str(entry.get("model_alias", entry.get("model_id", settings.llmproxy_ollama_model))),
                score=max(0.7, 0.96 - (index * 0.04)),
            )
        )
    return ranked


def _policy_fallback_chain(selected_entry: dict[str, object], settings: Settings) -> list[FallbackTarget]:
    configured = list(selected_entry.get("fallback_chain", []))
    if configured:
        return [
            FallbackTarget(
                order=int(item["order"]),
                provider=str(item["provider"]),
                model=str(item["model"]),
            )
            for item in configured
        ]
    return _default_fallbacks(
        settings=settings,
        primary_provider=str(selected_entry.get("provider_key", "ollama")),
    )


def _route_from_policy(
    *,
    request_id: str,
    session_id: str,
    policy_version: str,
    selected_entry: dict[str, object],
    shadow_entries: list[dict[str, object]],
    complexity: str,
    settings: Settings,
    mode: str,
) -> SelectedRoute:
    provider_key = str(selected_entry.get("provider_key", "ollama"))
    selected_model = str(selected_entry.get("model_alias", selected_entry.get("model_id", settings.llmproxy_ollama_model)))
    provider_family = str(selected_entry.get("provider_family", "local runtime"))
    rationale = str(
        selected_entry.get(
            "decision_rationale",
            f"Selected routing policy entry in {mode} mode.",
        )
    )
    fallback_chain = _policy_fallback_chain(selected_entry, settings)
    ranked_alternatives = _policy_ranked_alternatives(
        selected_entry=selected_entry,
        shadow_entries=shadow_entries,
        settings=settings,
    )
    shadow_provider_keys = [str(entry.get("provider_key", "ollama")) for entry in shadow_entries]
    selected_mode = f"local_{mode}" if provider_family == "local runtime" and mode in {"production", "canary"} else mode
    return SelectedRoute(
        provider_key=provider_key,
        decision=build_routing_decision(
            request_id=request_id,
            session_id=session_id,
            policy_version=policy_version,
            selected_provider=provider_key,
            selected_provider_family=provider_family,
            selected_model=selected_model,
            selected_mode=selected_mode,
            rationale=rationale,
            predicted_cost_class="low" if provider_family == "local runtime" else "medium",
            predicted_latency_class="medium" if complexity == "high" else "low",
            ranked_alternatives=ranked_alternatives,
                fallback_chain=fallback_chain,
        ),
        shadow_provider_keys=shadow_provider_keys,
        selected_entry=selected_entry,
    )


def _build_frontier_default_route(
    *,
    request_id: str,
    session_id: str,
    policy_version: str,
    provider_key: str,
    provider_family: str,
    model_id: str,
    rationale: str,
    predicted_cost_class: str,
    predicted_latency_class: str,
    ranked_alternatives: list[RankedAlternative],
    fallback_chain: list[FallbackTarget],
) -> SelectedRoute:
    return SelectedRoute(
        provider_key=provider_key,
        decision=build_routing_decision(
            request_id=request_id,
            session_id=session_id,
            policy_version=policy_version,
            selected_provider=provider_key,
            selected_provider_family=provider_family,
            selected_model=model_id,
            selected_mode="frontier_single",
            rationale=rationale,
            predicted_cost_class=predicted_cost_class,
            predicted_latency_class=predicted_latency_class,
            ranked_alternatives=ranked_alternatives,
            fallback_chain=fallback_chain,
        ),
        shadow_provider_keys=[],
        selected_entry=None,
    )


def select_route(
    request_id: str,
    request: ChatCompletionRequest,
    classification: dict[str, str],
    settings: Settings,
    session=None,
) -> SelectedRoute:
    domain = classification["domain"]
    task_type = classification["task_type"]
    privacy_level = classification["privacy_level"]
    complexity = classification["complexity"]
    route_tags = [str(item) for item in classification.get("route_tags", [])]
    region = str(classification.get("region", ""))
    policy_record = get_latest_policy_record(session)
    if policy_record is None:
        policy = {"entries": []}
        resolved_policy_version = "unversioned"
    else:
        policy = dict(policy_record.policy_json)
        resolved_policy_version = policy_record.policy_version
    policy_entries_by_provider = _entry_index(policy)
    production_entries, canary_entries, shadow_entries = _match_policy_entries(
        policy,
        domain=domain,
        task_type=task_type,
        route_tags=route_tags,
        region=region,
    )
    if (
        request.model == "proxy-local"
        or privacy_level == "private"
        or (
            request.model == settings.llmproxy_default_route_model
            and domain in {"coding", "software_architecture"}
        )
    ):
        provider_key = "ollama"
        provider_family = "local runtime"
        model_id = settings.llmproxy_ollama_model
        selected_mode = "local_only"
        rationale = "Selected local runtime for privacy-sensitive or code-specialist traffic."
        predicted_cost_class = "low"
        predicted_latency_class = "medium" if complexity == "high" else "low"
        ranked_alternatives = [
            RankedAlternative(rank=1, provider="ollama", model=settings.llmproxy_ollama_model, score=0.93),
        ]
        fallback_chain: list[FallbackTarget] = []
        return SelectedRoute(
            provider_key=provider_key,
            decision=build_routing_decision(
                request_id=request_id,
                session_id=request.metadata.session_id,
                policy_version=resolved_policy_version,
                selected_provider=provider_key,
                selected_provider_family=provider_family,
                selected_model=model_id,
                selected_mode=selected_mode,
                rationale=rationale,
                predicted_cost_class=predicted_cost_class,
                predicted_latency_class=predicted_latency_class,
                ranked_alternatives=ranked_alternatives,
                fallback_chain=fallback_chain,
            ),
            shadow_provider_keys=[],
            selected_entry=None,
            entry_index=policy_entries_by_provider,
        )
    local_production = [entry for entry in production_entries if _entry_type(entry) == "local"]
    frontier_production = [entry for entry in production_entries if _entry_type(entry) == "frontier"]
    local_canary = [entry for entry in canary_entries if _entry_type(entry) == "local"]
    frontier_canary = [entry for entry in canary_entries if _entry_type(entry) == "frontier"]
    strategy = str(settings.llmproxy_routing_strategy or "balanced").strip().lower()

    selected_policy_entry = None
    mode = None
    canary_candidate = _select_best_entry(local_canary, task_type=task_type, route_tags=route_tags, region=region, strategy=strategy) or _select_best_entry(frontier_canary, task_type=task_type, route_tags=route_tags, region=region, strategy=strategy)
    if canary_candidate is not None and _is_canary_session(request.metadata.session_id, float(canary_candidate.get("canary_percent", 0.0))):
        selected_policy_entry = canary_candidate
        mode = "canary"
    if selected_policy_entry is None:
        selected_policy_entry = _select_best_entry(local_production, task_type=task_type, route_tags=route_tags, region=region, strategy=strategy)
        if selected_policy_entry is not None:
            mode = "production"
    if selected_policy_entry is None:
        selected_policy_entry = _select_best_entry(frontier_production, task_type=task_type, route_tags=route_tags, region=region, strategy=strategy)
        if selected_policy_entry is not None:
            mode = "production"

    shadow_provider_keys = [str(entry.get("provider_key")) for entry in shadow_entries]

    if selected_policy_entry is not None:
        route = _route_from_policy(
            request_id=request_id,
            session_id=request.metadata.session_id,
            policy_version=resolved_policy_version,
            selected_entry=selected_policy_entry,
            shadow_entries=shadow_entries,
            complexity=complexity,
            settings=settings,
            mode=mode or "production",
        )
        route.entry_index = policy_entries_by_provider
        return route

    default_frontier_policy = _default_frontier_entries(settings)
    default_production, _, _ = _match_policy_entries(
        default_frontier_policy,
        domain=domain,
        task_type=task_type,
        route_tags=route_tags,
        region=region,
    )
    default_entry = _select_best_entry(default_production, task_type=task_type, route_tags=route_tags, region=region, strategy=strategy)
    if default_entry is None and request.model == "proxy-teacher":
        teacher_candidates = [
            entry
            for entry in default_frontier_policy.get("entries", [])
            if str(entry.get("provider_key")) in {"anthropic", "openai", "google"}
        ]
        default_entry = _select_best_entry(teacher_candidates, task_type=task_type, route_tags=route_tags, region=region, strategy="quality")
    if default_entry is None:
        raise ValueError("No default frontier route is available for the current configuration.")
    route = _route_from_policy(
        request_id=request_id,
        session_id=request.metadata.session_id,
        policy_version=resolved_policy_version,
        selected_entry=default_entry,
        shadow_entries=shadow_entries,
        complexity=complexity,
        settings=settings,
        mode="production",
    )

    route.shadow_provider_keys = shadow_provider_keys
    route.entry_index = policy_entries_by_provider
    return route
