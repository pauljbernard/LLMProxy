"""Model and provider registry helpers."""

from pathlib import Path

from app.config import Settings
from app.integration.routing_policy import get_latest_policy
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.azure_openai_provider import AzureOpenAIProvider
from app.providers.bedrock_provider import BedrockProvider
from app.providers.google_provider import GoogleProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.xai_provider import XAIProvider
from app.registry.artifact_store import get_model_package_by_alias, list_model_packages
from app.schemas.provider import ProviderCapability


def get_provider_registry(settings: Settings, session=None) -> dict[str, object]:
    registry = {
        "openai": OpenAIProvider.from_settings(settings),
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
        package = get_model_package_by_alias(models_root, model_alias)
        if package is None:
            continue
        registry[provider_key] = OllamaProvider.from_settings(settings, model_id=model_alias)
    return registry


def list_proxy_models(settings: Settings, session=None) -> list[dict[str, str]]:
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
        seen.add(model_id)
        models.append({"id": model_id, "object": "model"})
    for manifest in list_model_packages(Path(settings.llmproxy_models_path)):
        model_alias = str(manifest["model_alias"])
        if model_alias in seen:
            continue
        seen.add(model_alias)
        models.append({"id": model_alias, "object": "model"})
    return models


def list_provider_capabilities(settings: Settings, session=None) -> list[ProviderCapability]:
    return [provider.capability for provider in get_provider_registry(settings, session=session).values()]
