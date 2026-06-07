"""Model and provider registry helpers."""

from pathlib import Path
from urllib.parse import urlparse

from app.config import Settings
from app.integration.routing_policy import get_latest_policy
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.azure_openai_provider import AzureOpenAIProvider
from app.providers.bedrock_provider import BedrockProvider
from app.providers.cohere_provider import CohereProvider
from app.providers.cloudflare_workers_ai_provider import CloudflareWorkersAIProvider
from app.providers.deepseek_provider import DeepSeekProvider
from app.providers.fireworks_provider import FireworksProvider
from app.providers.google_provider import GoogleProvider
from app.providers.groq_provider import GroqProvider
from app.providers.huggingface_tgi_provider import HuggingFaceTGIProvider
from app.providers.local_openai_compatible import LocalOpenAICompatibleProvider
from app.providers.mistral_provider import MistralProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.perplexity_provider import PerplexityProvider
from app.providers.together_provider import TogetherProvider
from app.providers.vertex_ai_provider import VertexAIProvider
from app.providers.xai_provider import XAIProvider
from app.registry.artifact_store import get_model_package_by_alias, list_model_packages
from app.schemas.provider import ProviderCapability


def _is_model_visible(model_id: str, allowed_models: set[str] | None) -> bool:
    if not allowed_models:
        return True
    if model_id in allowed_models:
        return True
    if model_id.startswith("proxy-"):
        return True
    return False


def _entry_type(entry: dict[str, object]) -> str:
    explicit = str(entry.get("entry_type", "")).strip().lower()
    if explicit in {"frontier", "local"}:
        return explicit
    provider_key = str(entry.get("provider_key", ""))
    provider_family = str(entry.get("provider_family", "")).lower()
    if provider_key.startswith("local:") or provider_family == "local runtime":
        return "local"
    return "frontier"


def _normalize_openai_compatible_base_url(endpoint_url: str) -> str:
    parsed = urlparse(endpoint_url)
    if parsed.path in {"", "/"}:
        return endpoint_url.rstrip("/") + "/v1"
    return endpoint_url.rstrip("/")


def get_provider_registry(settings: Settings, session=None) -> dict[str, object]:
    registry = {
        "openai": OpenAIProvider.from_settings(settings),
        "groq": GroqProvider.from_settings(settings),
        "mistral": MistralProvider.from_settings(settings),
        "deepseek": DeepSeekProvider.from_settings(settings),
        "cohere": CohereProvider.from_settings(settings),
        "together": TogetherProvider.from_settings(settings),
        "fireworks": FireworksProvider.from_settings(settings),
        "perplexity": PerplexityProvider.from_settings(settings),
        "cloudflare_workers_ai": CloudflareWorkersAIProvider.from_settings(settings),
        "huggingface_tgi": HuggingFaceTGIProvider.from_settings(settings),
        "vertex_ai": VertexAIProvider.from_settings(settings),
        "anthropic": AnthropicProvider.from_settings(settings),
        "google": GoogleProvider.from_settings(settings),
        "xai": XAIProvider.from_settings(settings),
        "bedrock": BedrockProvider.from_settings(settings),
        "azure_openai": AzureOpenAIProvider.from_settings(settings),
        "ollama": OllamaProvider.from_settings(settings),
    }
    policy = get_latest_policy(session)
    models_root = Path(settings.llmproxy_models_path)
    for entry in policy.get("entries", []):
        model_alias = str(entry.get("model_alias"))
        provider_key = str(entry.get("provider_key", f"local:{model_alias}"))
        if _entry_type(entry) != "local":
            continue
        package = get_model_package_by_alias(models_root, model_alias)
        if package is None:
            continue
        registry[provider_key] = OllamaProvider.from_settings(settings, model_id=model_alias)
    return registry


def resolve_provider(
    settings: Settings,
    provider_registry: dict[str, object],
    *,
    provider_key: str,
    entry: dict[str, object] | None = None,
):
    if entry is None:
        return provider_registry.get(provider_key)

    entry_kind = _entry_type(entry)
    model_id = str(
        entry.get("model_alias")
        or entry.get("model_id")
        or provider_key.removeprefix("local:")
    )
    timeout_seconds = settings.llmproxy_provider_timeout_seconds

    if entry_kind == "local":
        runtime = str(entry.get("runtime", "ollama"))
        endpoint_url = str(entry.get("endpoint_url") or settings.llmproxy_ollama_base_url)
        if runtime == "ollama":
            return OllamaProvider(
                model_id,
                base_url=endpoint_url,
                timeout_seconds=timeout_seconds,
            )
        if runtime in {"vllm", "llama_cpp", "mlx", "tgi"}:
            return LocalOpenAICompatibleProvider(
                model_id,
                runtime_name="huggingface_tgi" if runtime == "tgi" else runtime,
                base_url=_normalize_openai_compatible_base_url(endpoint_url),
                timeout_seconds=timeout_seconds,
            )
        raise ValueError(f"Runtime '{runtime}' is not supported for local provider resolution.")

    if provider_key == "openai":
        return OpenAIProvider(
            model_id,
            api_key=settings.llmproxy_openai_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_openai_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "groq":
        return GroqProvider(
            model_id,
            api_key=settings.llmproxy_groq_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_groq_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "mistral":
        return MistralProvider(
            model_id,
            api_key=settings.llmproxy_mistral_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_mistral_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "deepseek":
        return DeepSeekProvider(
            model_id,
            api_key=settings.llmproxy_deepseek_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_deepseek_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "cohere":
        return CohereProvider(
            model_id,
            api_key=settings.llmproxy_cohere_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_cohere_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "together":
        return TogetherProvider(
            model_id,
            api_key=settings.llmproxy_together_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_together_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "fireworks":
        return FireworksProvider(
            model_id,
            api_key=settings.llmproxy_fireworks_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_fireworks_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "perplexity":
        return PerplexityProvider(
            model_id,
            api_key=settings.llmproxy_perplexity_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_perplexity_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "cloudflare_workers_ai":
        return CloudflareWorkersAIProvider(
            model_id,
            account_id=settings.llmproxy_cloudflare_account_id,
            api_token=settings.llmproxy_cloudflare_api_token,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_cloudflare_base_url),
            gateway_id=settings.llmproxy_cloudflare_gateway_id,
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "huggingface_tgi":
        return HuggingFaceTGIProvider(
            model_id,
            api_key=settings.llmproxy_huggingface_tgi_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_huggingface_tgi_base_url),
            timeout_seconds=timeout_seconds,
            require_api_key=False,
        )
    if provider_key == "vertex_ai":
        base_url = str(entry.get("endpoint_url") or entry.get("base_url") or VertexAIProvider._base_url_from_settings(settings))
        return VertexAIProvider(
            model_id,
            api_key=settings.llmproxy_vertex_ai_access_token,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "anthropic":
        return AnthropicProvider(
            model_id,
            api_key=settings.llmproxy_anthropic_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_anthropic_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "google":
        return GoogleProvider(
            model_id,
            api_key=settings.llmproxy_google_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_google_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "xai":
        return XAIProvider(
            model_id,
            api_key=settings.llmproxy_xai_api_key,
            base_url=str(entry.get("endpoint_url") or entry.get("base_url") or settings.llmproxy_xai_base_url),
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "azure_openai":
        return AzureOpenAIProvider(
            model_id,
            api_key=settings.llmproxy_azure_openai_api_key,
            endpoint=str(entry.get("endpoint_url") or settings.llmproxy_azure_openai_endpoint),
            api_version=settings.llmproxy_azure_openai_api_version,
            timeout_seconds=timeout_seconds,
        )
    if provider_key == "bedrock":
        return BedrockProvider(
            model_id,
            region=settings.llmproxy_bedrock_region,
            access_key_id=settings.llmproxy_bedrock_access_key_id,
            secret_access_key=settings.llmproxy_bedrock_secret_access_key,
            session_token=settings.llmproxy_bedrock_session_token,
            timeout_seconds=timeout_seconds,
        )
    return provider_registry.get(provider_key)


def list_proxy_models(settings: Settings, session=None, *, allowed_models: set[str] | None = None) -> list[dict[str, str]]:
    models: list[dict[str, str]] = [
        {"id": "proxy-auto", "object": "model"},
        {"id": "proxy-local", "object": "model"},
        {"id": "proxy-teacher", "object": "model"},
    ]
    seen = {item["id"] for item in models}
    for provider in get_provider_registry(settings, session=session).values():
        model_id = provider.capability.model_id
        if model_id in seen:
            continue
        if _is_model_visible(model_id, allowed_models):
            seen.add(model_id)
            models.append({"id": model_id, "object": "model"})
    for manifest in list_model_packages(Path(settings.llmproxy_models_path)):
        model_alias = str(manifest["model_alias"])
        if model_alias in seen:
            continue
        if _is_model_visible(model_alias, allowed_models):
            seen.add(model_alias)
            models.append({"id": model_alias, "object": "model"})
    return models


def list_provider_capabilities(
    settings: Settings,
    session=None,
    *,
    allowed_models: set[str] | None = None,
) -> list[ProviderCapability]:
    capabilities: list[ProviderCapability] = []
    for provider in get_provider_registry(settings, session=session).values():
        capability = provider.capability
        if not _is_model_visible(capability.model_id, allowed_models):
            continue
        capabilities.append(capability)
    return capabilities
