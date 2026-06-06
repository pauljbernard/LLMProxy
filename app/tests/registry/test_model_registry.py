from app.config import Settings
from app.providers.local_openai_compatible import LocalOpenAICompatibleProvider
from app.providers.ollama import OllamaProvider
from app.registry.model_registry import resolve_provider


def test_resolve_provider_uses_policy_endpoint_for_ollama_local_entry() -> None:
    provider = resolve_provider(
        Settings(),
        {},
        provider_key="local:coding-v4",
        entry={
            "entry_type": "local",
            "runtime": "ollama",
            "provider_key": "local:coding-v4",
            "model_alias": "coding-v4",
            "endpoint_url": "http://gpu-node-1:11434",
        },
    )

    assert isinstance(provider, OllamaProvider)
    assert provider.model_id == "coding-v4"
    assert provider.base_url == "http://gpu-node-1:11434"


def test_resolve_provider_uses_openai_compatible_runtime_for_vllm_local_entry() -> None:
    provider = resolve_provider(
        Settings(),
        {},
        provider_key="local:coding-vllm",
        entry={
            "entry_type": "local",
            "runtime": "vllm",
            "provider_key": "local:coding-vllm",
            "model_alias": "coding-vllm",
            "endpoint_url": "http://gpu-node-2:8001",
        },
    )

    assert isinstance(provider, LocalOpenAICompatibleProvider)
    assert provider.provider_name == "vllm"
    assert provider.model_id == "coding-vllm"
    assert provider.base_url == "http://gpu-node-2:8001/v1"


def test_resolve_provider_uses_frontier_policy_model_override() -> None:
    settings = Settings()
    provider = resolve_provider(
        settings,
        {},
        provider_key="anthropic",
        entry={
            "entry_type": "frontier",
            "provider_key": "anthropic",
            "model_id": "claude-opus-4-5",
            "domains": ["software_architecture"],
        },
    )

    assert provider.provider_name == "anthropic"
    assert provider.model_id == "claude-opus-4-5"
