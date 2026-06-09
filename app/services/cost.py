"""Cost helpers and model pricing registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_cost_per_token: float
    output_cost_per_token: float


_MODEL_PRICING: dict[tuple[str, str], ModelPricing] = {
    ("openai", "gpt-5.5"): ModelPricing(0.00000125, 0.00001),
    ("openai", "gpt-4o"): ModelPricing(0.0000025, 0.00001),
    ("openai", "gpt-4o-mini"): ModelPricing(0.00000015, 0.0000006),
    ("openai", "o3"): ModelPricing(0.00001, 0.00004),
    ("openai", "text-embedding-3-small"): ModelPricing(0.00000002, 0.0),
    ("azure_openai", "gpt-5.5"): ModelPricing(0.00000125, 0.00001),
    ("azure_openai", "gpt-4o"): ModelPricing(0.0000025, 0.00001),
    ("azure_openai", "gpt-4o-mini"): ModelPricing(0.00000015, 0.0000006),
    ("anthropic", "claude-3-5-sonnet"): ModelPricing(0.000003, 0.000015),
    ("google", "gemini-2.5-pro"): ModelPricing(0.00000125, 0.00001),
    ("xai", "grok-3-mini"): ModelPricing(0.0000003, 0.0000005),
    ("groq", "llama-3.3-70b-versatile"): ModelPricing(0.00000059, 0.00000079),
    ("mistral", "mistral-large-latest"): ModelPricing(0.000002, 0.000006),
    ("deepseek", "deepseek-v4-flash"): ModelPricing(0.00000027, 0.0000011),
    ("cohere", "command-a-plus-05-2026"): ModelPricing(0.0000025, 0.00001),
    ("together", "openai/gpt-oss-20b"): ModelPricing(0.0000002, 0.0000002),
    ("fireworks", "accounts/fireworks/models/llama-v3p1-8b-instruct"): ModelPricing(0.0000002, 0.0000002),
    ("perplexity", "sonar-pro"): ModelPricing(0.000001, 0.000001),
    ("vertex_ai", "google/gemini-2.5-pro"): ModelPricing(0.00000125, 0.00001),
    ("cloudflare_workers_ai", "@cf/moonshotai/kimi-k2.5"): ModelPricing(0.0000004, 0.0000004),
    ("bedrock", "anthropic.claude-3-5-sonnet"): ModelPricing(0.000003, 0.000015),
    ("ollama", "qwen2.5-coder:14b"): ModelPricing(0.0, 0.0),
    ("huggingface_tgi", "tgi"): ModelPricing(0.0, 0.0),
}

_PROVIDER_DEFAULT_PRICING: dict[str, ModelPricing] = {
    "openai": ModelPricing(0.0000025, 0.00001),
    "azure_openai": ModelPricing(0.0000025, 0.00001),
    "anthropic": ModelPricing(0.000003, 0.000015),
    "google": ModelPricing(0.00000125, 0.00001),
    "xai": ModelPricing(0.0000003, 0.0000005),
    "groq": ModelPricing(0.00000059, 0.00000079),
    "mistral": ModelPricing(0.000002, 0.000006),
    "deepseek": ModelPricing(0.00000027, 0.0000011),
    "cohere": ModelPricing(0.0000025, 0.00001),
    "together": ModelPricing(0.0000002, 0.0000002),
    "fireworks": ModelPricing(0.0000002, 0.0000002),
    "perplexity": ModelPricing(0.000001, 0.000001),
    "vertex_ai": ModelPricing(0.00000125, 0.00001),
    "cloudflare_workers_ai": ModelPricing(0.0000004, 0.0000004),
    "bedrock": ModelPricing(0.000003, 0.000015),
    "ollama": ModelPricing(0.0, 0.0),
    "huggingface_tgi": ModelPricing(0.0, 0.0),
    "local runtime": ModelPricing(0.0, 0.0),
}


def resolve_model_pricing(*, provider_name: str, model_id: str) -> ModelPricing:
    pricing = _MODEL_PRICING.get((provider_name, model_id))
    if pricing is not None:
        return pricing
    return _PROVIDER_DEFAULT_PRICING.get(provider_name, ModelPricing(0.0, 0.0))


def pricing_catalog() -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for (provider_name, model_id), pricing in sorted(_MODEL_PRICING.items()):
        rows.append(
            {
                "provider": provider_name,
                "model": model_id,
                "input_cost_per_token": pricing.input_cost_per_token,
                "output_cost_per_token": pricing.output_cost_per_token,
            }
        )
    return rows


def estimate_cost_usd(*, provider_name: str, model_id: str, input_tokens: int, output_tokens: int) -> float:
    pricing = resolve_model_pricing(provider_name=provider_name, model_id=model_id)
    return round(
        (max(0, int(input_tokens)) * pricing.input_cost_per_token)
        + (max(0, int(output_tokens)) * pricing.output_cost_per_token),
        6,
    )


def estimate_cost_breakdown_usd(*, provider_name: str, model_id: str, input_tokens: int, output_tokens: int) -> dict[str, float]:
    pricing = resolve_model_pricing(provider_name=provider_name, model_id=model_id)
    input_cost = round(max(0, int(input_tokens)) * pricing.input_cost_per_token, 6)
    output_cost = round(max(0, int(output_tokens)) * pricing.output_cost_per_token, 6)
    return {
        "input_cost_estimate": input_cost,
        "output_cost_estimate": output_cost,
        "total_cost_estimate": round(input_cost + output_cost, 6),
    }


def value_per_dollar(score: float, cost: float) -> float:
    if cost <= 0:
        return 0.0
    return score / cost
