"""Routing engine."""

from hashlib import sha256
from typing import NamedTuple

from app.config import Settings
from app.integration.routing_policy import get_latest_policy
from app.proxy.policy import build_routing_decision
from app.schemas.chat import ChatCompletionRequest
from app.schemas.routing import FallbackTarget, RankedAlternative, RoutingDecision


class SelectedRoute(NamedTuple):
    provider_key: str
    decision: RoutingDecision
    shadow_provider_keys: list[str]


def _is_canary_session(session_id: str, canary_percent: float) -> bool:
    bucket = int(sha256(session_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < int(canary_percent * 100)


def _match_policy_entries(policy: dict[str, object], *, domain: str, task_type: str) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    entries = [
        entry
        for entry in policy.get("entries", [])
        if domain in entry.get("domains", [])
        and (not entry.get("task_types") or task_type in entry.get("task_types", []))
    ]
    production = [entry for entry in entries if entry.get("deployment_mode") == "production"]
    canary = [entry for entry in entries if entry.get("deployment_mode") == "canary"]
    shadow = [entry for entry in entries if entry.get("deployment_mode") == "shadow"]
    return production, canary, shadow


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
            selected_provider="ollama" if provider_key.startswith("local:") else provider_key,
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
    policy = get_latest_policy(session)
    production_entries, canary_entries, shadow_entries = _match_policy_entries(
        policy,
        domain=domain,
        task_type=task_type,
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
            RankedAlternative(rank=2, provider="openai", model=settings.llmproxy_openai_model, score=0.90),
            RankedAlternative(rank=3, provider="anthropic", model=settings.llmproxy_anthropic_model, score=0.87),
        ]
        fallback_chain = [
            FallbackTarget(order=1, provider="openai", model=settings.llmproxy_openai_model),
            FallbackTarget(order=2, provider="anthropic", model=settings.llmproxy_anthropic_model),
        ]
        return SelectedRoute(
            provider_key=provider_key,
            decision=build_routing_decision(
                request_id=request_id,
                session_id=request.metadata.session_id,
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
        )
    selected_local_entry = None
    mode = None
    if canary_entries:
        canary_candidate = canary_entries[0]
        if _is_canary_session(request.metadata.session_id, float(canary_candidate.get("canary_percent", 0.0))):
            selected_local_entry = canary_candidate
            mode = "canary"
    if selected_local_entry is None and production_entries:
        selected_local_entry = production_entries[0]
        mode = "production"

    shadow_provider_keys = [str(entry.get("provider_key")) for entry in shadow_entries]

    if selected_local_entry is not None:
        return _route_from_policy(
            request_id=request_id,
            session_id=request.metadata.session_id,
            selected_entry=selected_local_entry,
            shadow_entries=shadow_entries,
            complexity=complexity,
            settings=settings,
            mode=mode or "production",
        )

    if domain == "software_architecture" or request.model == "proxy-teacher":
        provider_key = "anthropic"
        provider_family = "Anthropic"
        model_id = settings.llmproxy_anthropic_model
        selected_mode = "frontier_single"
        rationale = "Selected Anthropic for architecture-heavy or teacher-routed traffic."
        predicted_cost_class = "high"
        predicted_latency_class = "medium"
        ranked_alternatives = [
            RankedAlternative(rank=1, provider="anthropic", model=settings.llmproxy_anthropic_model, score=0.95),
            RankedAlternative(rank=2, provider="openai", model=settings.llmproxy_openai_model, score=0.91),
            RankedAlternative(rank=3, provider="google", model=settings.llmproxy_google_model, score=0.89),
        ]
        fallback_chain = [
            FallbackTarget(order=1, provider="openai", model=settings.llmproxy_openai_model),
            FallbackTarget(order=2, provider="google", model=settings.llmproxy_google_model),
        ]
    elif domain in {"research", "analysis"}:
        provider_key = "google"
        provider_family = "Google Gemini"
        model_id = settings.llmproxy_google_model
        selected_mode = "frontier_single"
        rationale = "Selected Google Gemini for research-oriented traffic."
        predicted_cost_class = "medium"
        predicted_latency_class = "medium"
        ranked_alternatives = [
            RankedAlternative(rank=1, provider="google", model=settings.llmproxy_google_model, score=0.94),
            RankedAlternative(rank=2, provider="openai", model=settings.llmproxy_openai_model, score=0.90),
            RankedAlternative(rank=3, provider="xai", model=settings.llmproxy_xai_model, score=0.86),
        ]
        fallback_chain = [
            FallbackTarget(order=1, provider="openai", model=settings.llmproxy_openai_model),
            FallbackTarget(order=2, provider="xai", model=settings.llmproxy_xai_model),
        ]
    else:
        provider_key = "openai"
        provider_family = "OpenAI"
        model_id = settings.llmproxy_openai_model
        selected_mode = "frontier_single"
        rationale = "Selected OpenAI for general-purpose coverage and balanced quality."
        predicted_cost_class = "medium" if complexity == "medium" else "high"
        predicted_latency_class = "medium"
        ranked_alternatives = [
            RankedAlternative(rank=1, provider="openai", model=settings.llmproxy_openai_model, score=0.95),
            RankedAlternative(rank=2, provider="anthropic", model=settings.llmproxy_anthropic_model, score=0.90),
            RankedAlternative(rank=3, provider="google", model=settings.llmproxy_google_model, score=0.88),
        ]
        fallback_chain = [
            FallbackTarget(order=1, provider="anthropic", model=settings.llmproxy_anthropic_model),
            FallbackTarget(order=2, provider="google", model=settings.llmproxy_google_model),
        ]

    return SelectedRoute(
        provider_key=provider_key,
        decision=build_routing_decision(
            request_id=request_id,
            session_id=request.metadata.session_id,
            selected_provider="ollama" if provider_key.startswith("local:") else provider_key,
            selected_provider_family=provider_family,
            selected_model=model_id,
            selected_mode=selected_mode,
            rationale=rationale,
            predicted_cost_class=predicted_cost_class,
            predicted_latency_class=predicted_latency_class,
            ranked_alternatives=ranked_alternatives,
            fallback_chain=fallback_chain,
        ),
        shadow_provider_keys=shadow_provider_keys,
    )
