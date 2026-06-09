"""Routing engine."""

from dataclasses import dataclass, field
from hashlib import sha256

from app.config import Settings
from app.integration.routing_policy import get_latest_policy_record
from app.proxy.policy import build_routing_decision
from app.schemas.chat import ChatCompletionRequest
from app.schemas.routing import FallbackTarget, RankedAlternative, RoutingDecision

RESERVED_ROUTE_MODELS = {"proxy-auto", "proxy-local", "proxy-teacher"}


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


def _entry_listener_ids(entry: dict[str, object]) -> list[str]:
    return [str(item).strip().lower() for item in entry.get("listener_ids", []) if str(item).strip()]


def _entry_requested_models(entry: dict[str, object]) -> list[str]:
    return [
        str(item).strip()
        for item in (entry.get("requested_models") or entry.get("requested_model_ids") or [])
        if str(item).strip()
    ]


def _entry_targets_requested_model(
    entry: dict[str, object],
    *,
    requested_model: str,
    settings: Settings,
) -> bool:
    if not requested_model:
        return True
    requested_models = _entry_requested_models(entry)
    if requested_models:
        return requested_model in requested_models
    target_models = {
        str(entry.get("model_id") or "").strip(),
        str(entry.get("model_alias") or "").strip(),
        _entry_model(entry, settings).strip(),
    }
    return requested_model in {item for item in target_models if item}


def _entry_matches_requested_model(
    entry: dict[str, object],
    *,
    requested_model: str,
    settings: Settings,
) -> bool:
    normalized = str(requested_model or "").strip()
    if not normalized or normalized in RESERVED_ROUTE_MODELS:
        return True
    return _entry_targets_requested_model(entry, requested_model=normalized, settings=settings)


def _entry_pool_id(entry: dict[str, object]) -> str:
    return str(entry.get("pool_id", "")).strip()


def _entry_pool_weight(entry: dict[str, object]) -> float:
    try:
        weight = float(entry.get("pool_weight", 1.0))
    except (TypeError, ValueError):
        return 1.0
    return weight if weight > 0 else 1.0


def _entry_balancing_strategy(entry: dict[str, object]) -> str:
    return str(entry.get("balancing_strategy") or "session_affinity").strip().lower()


def _entry_affinity_key(entry: dict[str, object]) -> str:
    return str(entry.get("affinity_key") or "session_id").strip().lower()


def _entry_hash_seed(*, request_id: str, session_id: str, entry: dict[str, object]) -> str:
    affinity_key = _entry_affinity_key(entry)
    if affinity_key == "request_id":
        return request_id
    return session_id


def _hash_bucket(seed: str, modulus: float) -> float:
    if modulus <= 0:
        return 0.0
    value = int(sha256(seed.encode("utf-8")).hexdigest()[:12], 16)
    return float(value % int(modulus * 10_000)) / 10_000.0


def _weighted_member_choice(
    entries: list[dict[str, object]],
    *,
    seed: str,
) -> dict[str, object] | None:
    if not entries:
        return None
    total_weight = sum(_entry_pool_weight(entry) for entry in entries)
    if total_weight <= 0:
        return entries[0]
    cursor = _hash_bucket(seed, total_weight)
    running = 0.0
    for entry in entries:
        running += _entry_pool_weight(entry)
        if cursor < running:
            return entry
    return entries[-1]


def _match_policy_entries(
    policy: dict[str, object],
    *,
    settings: Settings,
    domain: str,
    task_type: str,
    route_tags: list[str] | None = None,
    region: str = "",
    listener_id: str = "",
    requested_model: str = "",
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    route_tags = [str(item).strip().lower() for item in (route_tags or []) if str(item).strip()]
    entries = [
        entry
        for entry in policy.get("entries", [])
        if (not entry.get("domains") or domain in entry.get("domains", []))
        and (not entry.get("task_types") or task_type in entry.get("task_types", []))
        and (not _entry_tags(entry) or bool(set(_entry_tags(entry)) & set(route_tags)))
        and (not _entry_regions(entry) or (region and region in _entry_regions(entry)))
        and (not _entry_listener_ids(entry) or (listener_id and listener_id in _entry_listener_ids(entry)))
        and _entry_matches_requested_model(entry, requested_model=requested_model, settings=settings)
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


def _entry_model(entry: dict[str, object], settings: Settings) -> str:
    return str(entry.get("model_alias", entry.get("model_id", settings.llmproxy_ollama_model)))


def _entry_provider_family(entry: dict[str, object]) -> str:
    return str(entry.get("provider_family", "local runtime"))


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


def _pool_members(entries: list[dict[str, object]], selected_entry: dict[str, object]) -> list[dict[str, object]]:
    pool_id = _entry_pool_id(selected_entry)
    if not pool_id:
        return [selected_entry]
    return [
        entry
        for entry in entries
        if _entry_pool_id(entry) == pool_id
        and str(entry.get("deployment_mode", "production")) == str(selected_entry.get("deployment_mode", "production"))
    ] or [selected_entry]


def _resolve_pooled_entry(
    entries: list[dict[str, object]],
    selected_entry: dict[str, object],
    *,
    request_id: str,
    session_id: str,
) -> dict[str, object]:
    members = _pool_members(entries, selected_entry)
    if len(members) <= 1:
        return selected_entry
    strategy = _entry_balancing_strategy(selected_entry)
    if strategy in {"least_latency", "latency"}:
        return min(members, key=_entry_latency_score)
    if strategy in {"lowest_cost", "cost"}:
        return min(members, key=_entry_cost_score)
    if strategy in {"highest_quality", "quality"}:
        return max(members, key=_entry_quality_score)
    seed = _entry_hash_seed(request_id=request_id, session_id=session_id, entry=selected_entry)
    return _weighted_member_choice(members, seed=seed) or selected_entry


def _entry_index(policy: dict[str, object]) -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    for entry in policy.get("entries", []):
        provider_key = str(entry.get("provider_key", ""))
        entry_id = str(entry.get("entry_id") or "").strip()
        if provider_key and provider_key not in index:
            index[provider_key] = entry
        if entry_id:
            index[f"entry:{entry_id}"] = entry
    return index


def _fallback_target_from_entry(
    *,
    order: int,
    entry: dict[str, object],
    settings: Settings,
) -> FallbackTarget:
    pool_id = _entry_pool_id(entry) or None
    return FallbackTarget(
        order=order,
        provider=str(entry.get("provider_key", "ollama")),
        model=_entry_model(entry, settings),
        entry_id=str(entry.get("entry_id") or "") or None,
        pool_id=pool_id,
        node_id=str(entry.get("node_id") or "") or None,
        node_role=str(entry.get("node_role") or "") or None,
        node_labels=[str(item) for item in entry.get("node_labels", []) if str(item).strip()],
        capacity_class=str(entry.get("capacity_class") or "") or None,
        provider_family=_entry_provider_family(entry),
        balancing_strategy=_entry_balancing_strategy(entry) if pool_id else None,
        affinity_key=_entry_affinity_key(entry) if pool_id else None,
    )


def _pool_fallback_entries(
    *,
    selected_entry: dict[str, object],
    eligible_entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    members = [
        entry
        for entry in _pool_members(eligible_entries, selected_entry)
        if str(entry.get("entry_id") or "") != str(selected_entry.get("entry_id") or "")
    ]
    if not members:
        return []
    strategy = _entry_balancing_strategy(selected_entry)
    if strategy in {"least_latency", "latency"}:
        return sorted(members, key=_entry_latency_score)
    if strategy in {"lowest_cost", "cost"}:
        return sorted(members, key=_entry_cost_score)
    if strategy in {"highest_quality", "quality"}:
        return sorted(members, key=_entry_quality_score, reverse=True)
    return sorted(members, key=lambda entry: (_entry_pool_weight(entry) * -1.0, str(entry.get("entry_id") or "")))


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


def _direct_model_policy_entries(
    policy: dict[str, object],
    *,
    settings: Settings,
    requested_model: str,
    region: str = "",
    listener_id: str = "",
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    normalized = str(requested_model or "").strip()
    if not normalized or normalized in RESERVED_ROUTE_MODELS:
        return [], [], []
    entries = [
        entry
        for entry in policy.get("entries", [])
        if not _entry_requested_models(entry)
        and _entry_targets_requested_model(entry, requested_model=normalized, settings=settings)
        and (not _entry_regions(entry) or (region and region in _entry_regions(entry)))
        and (not _entry_listener_ids(entry) or (listener_id and listener_id in _entry_listener_ids(entry)))
    ]
    production = [entry for entry in entries if entry.get("deployment_mode") == "production"]
    canary = [entry for entry in entries if entry.get("deployment_mode") == "canary"]
    shadow = [entry for entry in entries if entry.get("deployment_mode") == "shadow"]
    return production, canary, shadow


def _provider_family_label(provider_key: str) -> str:
    return {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google Gemini",
        "xai": "xAI",
        "groq": "Groq",
        "mistral": "Mistral",
        "deepseek": "DeepSeek",
        "cohere": "Cohere",
        "together": "Together",
        "fireworks": "Fireworks",
        "perplexity": "Perplexity",
        "cloudflare_workers_ai": "Cloudflare Workers AI",
        "huggingface_tgi": "Hugging Face TGI",
        "vertex_ai": "Vertex AI",
        "azure_openai": "Azure OpenAI",
        "bedrock": "Amazon Bedrock",
        "ollama": "local runtime",
    }.get(provider_key, provider_key)


def _implicit_direct_route_entry(
    requested_model: str,
    settings: Settings,
    *,
    requested_model_provider_key: str | None = None,
) -> dict[str, object] | None:
    normalized = str(requested_model or "").strip()
    if not normalized or normalized in RESERVED_ROUTE_MODELS:
        return None
    provider_override = str(requested_model_provider_key or "").strip()
    if provider_override and settings.provider_configuration.get(provider_override, False):
        return {
            "entry_type": "frontier",
            "provider_key": provider_override,
            "provider_family": _provider_family_label(provider_override),
            "model_id": normalized,
            "deployment_mode": "production",
            "decision_rationale": f"Direct model access for discovered provider model '{normalized}'.",
        }
    if normalized == settings.llmproxy_ollama_model and settings.provider_configuration.get("ollama", False):
        return {
            "entry_type": "local",
            "provider_key": "ollama",
            "provider_family": "local runtime",
            "model_id": settings.llmproxy_ollama_model,
            "runtime": "ollama",
            "deployment_mode": "production",
            "decision_rationale": f"Direct model access for configured local model '{normalized}'.",
        }
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
    for provider_key, model_id in model_by_provider.items():
        if normalized != model_id:
            continue
        if settings.provider_configuration.get(provider_key, False) is False:
            return None
        return {
            "entry_type": "frontier",
            "provider_key": provider_key,
            "provider_family": _provider_family_label(provider_key),
            "model_id": model_id,
            "deployment_mode": "production",
            "decision_rationale": f"Direct model access for configured provider model '{normalized}'.",
        }
    return None


def _should_honor_requested_model(
    policy: dict[str, object],
    *,
    settings: Settings,
    requested_model: str,
    requested_model_provider_key: str | None = None,
) -> bool:
    normalized = str(requested_model or "").strip()
    if not normalized or normalized in RESERVED_ROUTE_MODELS:
        return False
    if _implicit_direct_route_entry(
        normalized,
        settings,
        requested_model_provider_key=requested_model_provider_key,
    ) is not None:
        return True
    return any(
        _entry_targets_requested_model(entry, requested_model=normalized, settings=settings)
        for entry in policy.get("entries", [])
    )


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


def _policy_fallback_chain(
    selected_entry: dict[str, object],
    eligible_entries: list[dict[str, object]],
    settings: Settings,
) -> list[FallbackTarget]:
    seen: set[tuple[str, str, str, str]] = set()

    def _append_unique(targets: list[FallbackTarget], item: FallbackTarget, *, order: int) -> int:
        key = (
            item.entry_id or "",
            item.provider,
            item.model,
            item.node_id or item.pool_id or "",
        )
        if key in seen:
            return order
        seen.add(key)
        item.order = order
        targets.append(item)
        return order + 1

    pool_fallbacks = [
        _fallback_target_from_entry(order=index, entry=entry, settings=settings)
        for index, entry in enumerate(
            _pool_fallback_entries(selected_entry=selected_entry, eligible_entries=eligible_entries),
            start=1,
        )
    ]
    fallbacks: list[FallbackTarget] = []
    order = 1
    for item in pool_fallbacks:
        order = _append_unique(fallbacks, item, order=order)
    configured = list(selected_entry.get("fallback_chain", []))
    if configured:
        for item in configured:
            order = _append_unique(
                fallbacks,
                FallbackTarget(
                    order=0,
                    provider=str(item["provider"]),
                    model=str(item["model"]),
                    entry_id=str(item.get("entry_id") or "") or None,
                    pool_id=str(item.get("pool_id") or "") or None,
                    node_id=str(item.get("node_id") or "") or None,
                    node_role=str(item.get("node_role") or "") or None,
                    node_labels=[str(label) for label in item.get("node_labels", []) if str(label).strip()],
                    capacity_class=str(item.get("capacity_class") or "") or None,
                    provider_family=str(item.get("provider_family") or "") or None,
                    balancing_strategy=str(item.get("balancing_strategy") or "") or None,
                    affinity_key=str(item.get("affinity_key") or "") or None,
                ),
                order=order,
            )
        return fallbacks
    defaults = _default_fallbacks(
        settings=settings,
        primary_provider=str(selected_entry.get("provider_key", "ollama")),
    )
    for item in defaults:
        order = _append_unique(fallbacks, item, order=order)
    return fallbacks


def _route_from_policy(
    *,
    request_id: str,
    session_id: str,
    policy_version: str,
    selected_entry: dict[str, object],
    eligible_entries: list[dict[str, object]],
    shadow_entries: list[dict[str, object]],
    complexity: str,
    settings: Settings,
    mode: str,
) -> SelectedRoute:
    resolved_entry = _resolve_pooled_entry(
        eligible_entries,
        selected_entry,
        request_id=request_id,
        session_id=session_id,
    )
    provider_key = str(resolved_entry.get("provider_key", "ollama"))
    selected_model = str(resolved_entry.get("model_alias", resolved_entry.get("model_id", settings.llmproxy_ollama_model)))
    provider_family = str(resolved_entry.get("provider_family", "local runtime"))
    rationale = str(
        resolved_entry.get(
            "decision_rationale",
            f"Selected routing policy entry in {mode} mode.",
        )
    )
    fallback_chain = _policy_fallback_chain(resolved_entry, eligible_entries, settings)
    ranked_alternatives = _policy_ranked_alternatives(
        selected_entry=resolved_entry,
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
            selected_entry_id=str(resolved_entry.get("entry_id") or "") or None,
            selected_pool_id=_entry_pool_id(resolved_entry) or None,
            selected_node_id=str(resolved_entry.get("node_id") or "") or None,
            selected_node_role=str(resolved_entry.get("node_role") or "") or None,
            selected_node_labels=[str(item) for item in resolved_entry.get("node_labels", []) if str(item).strip()],
            selected_capacity_class=str(resolved_entry.get("capacity_class") or "") or None,
            selected_balancing_strategy=_entry_balancing_strategy(resolved_entry) if _entry_pool_id(resolved_entry) else None,
            selected_affinity_key=_entry_affinity_key(resolved_entry) if _entry_pool_id(resolved_entry) else None,
        ),
        shadow_provider_keys=shadow_provider_keys,
        selected_entry=resolved_entry,
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
    requested_model_provider_key: str | None = None,
) -> SelectedRoute:
    domain = classification["domain"]
    task_type = classification["task_type"]
    privacy_level = classification["privacy_level"]
    complexity = classification["complexity"]
    route_tags = [str(item) for item in classification.get("route_tags", [])]
    region = str(classification.get("region", ""))
    listener_id = str(request.metadata.listener_id or "").strip().lower()
    requested_model = str(request.model or "").strip()
    policy_record = get_latest_policy_record(session)
    if policy_record is None:
        policy = {"entries": []}
        resolved_policy_version = "unversioned"
    else:
        policy = dict(policy_record.policy_json)
        resolved_policy_version = policy_record.policy_version
    requested_model_constraint = (
        requested_model
        if _should_honor_requested_model(
            policy,
            settings=settings,
            requested_model=requested_model,
            requested_model_provider_key=requested_model_provider_key,
        )
        else ""
    )
    policy_entries_by_provider = _entry_index(policy)
    production_entries, canary_entries, shadow_entries = _match_policy_entries(
        policy,
        settings=settings,
        domain=domain,
        task_type=task_type,
        route_tags=route_tags,
        region=region,
        listener_id=listener_id,
        requested_model=requested_model_constraint,
    )
    if requested_model_constraint:
        direct_production, direct_canary, direct_shadow = _direct_model_policy_entries(
            policy,
            settings=settings,
            requested_model=requested_model_constraint,
            region=region,
            listener_id=listener_id,
        )
        direct_local_canary = [entry for entry in direct_canary if _entry_type(entry) == "local"]
        direct_frontier_canary = [entry for entry in direct_canary if _entry_type(entry) == "frontier"]
        direct_local_production = [entry for entry in direct_production if _entry_type(entry) == "local"]
        direct_frontier_production = [entry for entry in direct_production if _entry_type(entry) == "frontier"]
        direct_canary_candidate = _select_best_entry(
            direct_local_canary,
            task_type=task_type,
            route_tags=route_tags,
            region=region,
            strategy=str(settings.llmproxy_routing_strategy or "balanced").strip().lower(),
        ) or _select_best_entry(
            direct_frontier_canary,
            task_type=task_type,
            route_tags=route_tags,
            region=region,
            strategy=str(settings.llmproxy_routing_strategy or "balanced").strip().lower(),
        )
        if direct_canary_candidate is not None and _is_canary_session(
            request.metadata.session_id,
            float(direct_canary_candidate.get("canary_percent", 0.0)),
        ):
            route = _route_from_policy(
                request_id=request_id,
                session_id=request.metadata.session_id,
                policy_version=resolved_policy_version,
                selected_entry=direct_canary_candidate,
                eligible_entries=direct_local_canary + direct_frontier_canary,
                shadow_entries=direct_shadow,
                complexity=complexity,
                settings=settings,
                mode="canary",
            )
            route.entry_index = policy_entries_by_provider
            return route
        direct_candidate = _select_best_entry(
            direct_local_production,
            task_type=task_type,
            route_tags=route_tags,
            region=region,
            strategy=str(settings.llmproxy_routing_strategy or "balanced").strip().lower(),
        ) or _select_best_entry(
            direct_frontier_production,
            task_type=task_type,
            route_tags=route_tags,
            region=region,
            strategy=str(settings.llmproxy_routing_strategy or "balanced").strip().lower(),
        )
        if direct_candidate is not None:
            route = _route_from_policy(
                request_id=request_id,
                session_id=request.metadata.session_id,
                policy_version=resolved_policy_version,
                selected_entry=direct_candidate,
                eligible_entries=direct_local_production + direct_frontier_production,
                shadow_entries=direct_shadow,
                complexity=complexity,
                settings=settings,
                mode="production",
            )
            route.entry_index = policy_entries_by_provider
            return route
        implicit_direct_entry = _implicit_direct_route_entry(
            requested_model_constraint,
            settings,
            requested_model_provider_key=requested_model_provider_key,
        )
        if implicit_direct_entry is not None:
            route = _route_from_policy(
                request_id=request_id,
                session_id=request.metadata.session_id,
                policy_version=resolved_policy_version,
                selected_entry=implicit_direct_entry,
                eligible_entries=[implicit_direct_entry],
                shadow_entries=[],
                complexity=complexity,
                settings=settings,
                mode="production",
            )
            route.entry_index = policy_entries_by_provider
            return route
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
            eligible_entries=local_canary + frontier_canary if mode == "canary" else local_production + frontier_production,
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
        settings=settings,
        domain=domain,
        task_type=task_type,
        route_tags=route_tags,
        region=region,
        listener_id=listener_id,
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
        eligible_entries=default_production,
        shadow_entries=shadow_entries,
        complexity=complexity,
        settings=settings,
        mode="production",
    )

    route.shadow_provider_keys = shadow_provider_keys
    route.entry_index = policy_entries_by_provider
    return route
