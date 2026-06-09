import asyncio

from app.config import Settings
from app.schemas.provider import ProviderCapability
from app.providers.local_openai_compatible import LocalOpenAICompatibleProvider
from app.providers.ollama import OllamaProvider
from app.registry import model_registry
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


def test_resolve_provider_uses_openai_compatible_runtime_for_tgi_local_entry() -> None:
    provider = resolve_provider(
        Settings(),
        {},
        provider_key="local:coding-tgi",
        entry={
            "entry_type": "local",
            "runtime": "tgi",
            "provider_key": "local:coding-tgi",
            "model_alias": "coding-tgi",
            "endpoint_url": "http://gpu-node-3:8080",
        },
    )

    assert isinstance(provider, LocalOpenAICompatibleProvider)
    assert provider.provider_name == "huggingface_tgi"
    assert provider.model_id == "coding-tgi"
    assert provider.base_url == "http://gpu-node-3:8080/v1"


def test_resolve_provider_uses_vllm_runtime_default_when_endpoint_missing() -> None:
    settings = Settings(llmproxy_vllm_base_url="http://runtime-node:9000/v1")
    provider = resolve_provider(
        settings,
        {},
        provider_key="local:coding-vllm",
        entry={
            "entry_type": "local",
            "runtime": "vllm",
            "provider_key": "local:coding-vllm",
            "model_alias": "coding-vllm",
        },
    )

    assert isinstance(provider, LocalOpenAICompatibleProvider)
    assert provider.provider_name == "vllm"
    assert provider.base_url == "http://runtime-node:9000/v1"


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


def test_list_provider_capabilities_async_expands_discovered_provider_models(monkeypatch) -> None:
    class _FakeProvider:
        provider_name = "anthropic"
        provider_family = "Anthropic"
        model_id = "claude-sonnet-4-6"

        @property
        def capability(self) -> ProviderCapability:
            return ProviderCapability(
                provider_family=self.provider_family,
                provider_name=self.provider_name,
                model_id=self.model_id,
                supports_streaming=True,
                supports_tools=True,
            )

        async def list_models(self) -> list[ProviderCapability]:
            return [
                ProviderCapability(
                    provider_family=self.provider_family,
                    provider_name=self.provider_name,
                    model_id="claude-sonnet-4-6",
                    supports_streaming=True,
                    supports_tools=True,
                ),
                ProviderCapability(
                    provider_family=self.provider_family,
                    provider_name=self.provider_name,
                    model_id="claude-haiku-4-5",
                    supports_streaming=True,
                    supports_tools=True,
                ),
            ]

    monkeypatch.setattr(
        model_registry,
        "get_provider_registry",
        lambda settings, session=None: {"anthropic": _FakeProvider()},
    )

    capabilities = asyncio.run(
        model_registry.list_provider_capabilities_async(Settings(llmproxy_anthropic_api_key="test-key"))
    )

    assert {item.model_id for item in capabilities} == {"claude-sonnet-4-6", "claude-haiku-4-5"}
