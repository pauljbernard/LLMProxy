"""Configuration models for llmProxy."""

from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    llmproxy_env: str = "development"
    llmproxy_log_level: str = "INFO"
    llmproxy_node_id: str = "llmproxy-local"
    llmproxy_api_host: str = "0.0.0.0"
    llmproxy_api_port: int = 8000
    llmproxy_inbound_listeners: list[dict[str, object]] = Field(default_factory=list)
    llmproxy_model_monitors: list[dict[str, object]] = Field(default_factory=list)
    llmproxy_database_url: str = "postgresql+psycopg://llm:llm@localhost:5432/llmproxy"
    llmproxy_redis_url: str = "redis://localhost:6379/0"
    llmproxy_prometheus_metrics_enabled: bool = True
    llmproxy_otel_enabled: bool = False
    llmproxy_otel_service_name: str = "llmproxy"
    llmproxy_otel_exporter_otlp_endpoint: str | None = None
    llmproxy_jaeger_ui_url: str | None = None
    llmproxy_db_pool_size: int = 10
    llmproxy_db_max_overflow: int = 20
    llmproxy_database_wait_timeout_seconds: int = 30
    llmproxy_run_migrations_on_start: bool = True
    llmproxy_provider_timeout_seconds: float = 60.0
    llmproxy_provider_max_retries: int = 2
    llmproxy_provider_retry_backoff_seconds: float = 0.25
    llmproxy_provider_allowed_fails: int = 3
    llmproxy_provider_cooldown_seconds: int = 60
    llmproxy_sla_first_response_ms: int = 2000
    llmproxy_sla_total_response_ms: int = 10000
    llmproxy_sla_cost_per_request_usd: float = 0.05
    llmproxy_response_cache_enabled: bool = False
    llmproxy_response_cache_ttl_seconds: int = 300
    llmproxy_semantic_cache_enabled: bool = False
    llmproxy_semantic_cache_similarity_threshold: float = 0.97
    llmproxy_semantic_cache_max_candidates: int = 50
    llmproxy_semantic_cache_embedding_model: str = "text-embedding-3-small"
    llmproxy_guardrail_pre_hooks: list[str] = Field(default_factory=list)
    llmproxy_guardrail_post_hooks: list[str] = Field(default_factory=list)
    llmproxy_guardrail_block_prompt_injection: bool = True
    llmproxy_guardrail_mask_pii_output: bool = True
    llmproxy_guardrail_blocked_output_patterns: list[str] = Field(
        default_factory=lambda: [
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            r"\bsk-[A-Za-z0-9]{12,}\b",
            r"\bAKIA[0-9A-Z]{16}\b",
        ]
    )
    llmproxy_mcp_servers: dict[str, dict[str, object]] = Field(default_factory=dict)
    llmproxy_a2a_peers: dict[str, dict[str, object]] = Field(default_factory=dict)
    llmproxy_rest_endpoints: dict[str, dict[str, object]] = Field(default_factory=dict)
    llmproxy_mcp_max_tool_roundtrips: int = 3
    llmproxy_mcp_tool_inventory_ttl_seconds: int = 60
    llmproxy_training_backend_timeout_seconds: int = 14400
    llmproxy_evaluation_timeout_seconds: int = 3600
    llmproxy_worker_include_job_types: str | None = None
    llmproxy_worker_exclude_job_types: str | None = None
    llmproxy_default_route_model: str = "proxy-auto"
    llmproxy_routing_strategy: str = "balanced"
    llmproxy_frontier_default_entries: list[dict[str, object]] = Field(
        default_factory=lambda: [
            {
                "entry_type": "frontier",
                "provider_key": "anthropic",
                "provider_family": "Anthropic",
                "model_id": "claude-3-5-sonnet",
                "domains": ["software_architecture"],
                "task_types": [],
                "deployment_mode": "production",
                "decision_rationale": "Configured default frontier entry for architecture-heavy traffic.",
            },
            {
                "entry_type": "frontier",
                "provider_key": "google",
                "provider_family": "Google Gemini",
                "model_id": "gemini-2.5-pro",
                "domains": ["research", "analysis"],
                "task_types": [],
                "deployment_mode": "production",
                "decision_rationale": "Configured default frontier entry for research-oriented traffic.",
            },
            {
                "entry_type": "frontier",
                "provider_key": "openai",
                "provider_family": "OpenAI",
                "model_id": "gpt-5",
                "domains": [],
                "task_types": [],
                "deployment_mode": "production",
                "decision_rationale": "Configured default frontier entry for general-purpose coverage.",
            },
        ]
    )
    llmproxy_bearer_token: str = "change-me"
    llmproxy_openai_api_key: str | None = None
    llmproxy_openai_base_url: str = "https://api.openai.com/v1"
    llmproxy_openai_model: str = "gpt-5"
    llmproxy_openai_image_model: str = "gpt-image-1"
    llmproxy_openai_transcription_model: str = "whisper-1"
    llmproxy_openai_speech_model: str = "gpt-4o-mini-tts"
    llmproxy_openai_moderation_model: str = "omni-moderation-latest"
    llmproxy_groq_api_key: str | None = None
    llmproxy_groq_base_url: str = "https://api.groq.com/openai/v1"
    llmproxy_groq_model: str = "llama-3.3-70b-versatile"
    llmproxy_mistral_api_key: str | None = None
    llmproxy_mistral_base_url: str = "https://api.mistral.ai/v1"
    llmproxy_mistral_model: str = "mistral-large-latest"
    llmproxy_deepseek_api_key: str | None = None
    llmproxy_deepseek_base_url: str = "https://api.deepseek.com"
    llmproxy_deepseek_model: str = "deepseek-v4-flash"
    llmproxy_cohere_api_key: str | None = None
    llmproxy_cohere_base_url: str = "https://api.cohere.ai/compatibility/v1"
    llmproxy_cohere_model: str = "command-a-plus-05-2026"
    llmproxy_together_api_key: str | None = None
    llmproxy_together_base_url: str = "https://api.together.ai/v1"
    llmproxy_together_model: str = "openai/gpt-oss-20b"
    llmproxy_fireworks_api_key: str | None = None
    llmproxy_fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    llmproxy_fireworks_model: str = "accounts/fireworks/models/llama-v3p1-8b-instruct"
    llmproxy_perplexity_api_key: str | None = None
    llmproxy_perplexity_base_url: str = "https://api.perplexity.ai/v1"
    llmproxy_perplexity_model: str = "sonar-pro"
    llmproxy_cloudflare_api_token: str | None = None
    llmproxy_cloudflare_account_id: str | None = None
    llmproxy_cloudflare_base_url: str = "https://api.cloudflare.com/client/v4"
    llmproxy_cloudflare_gateway_id: str | None = None
    llmproxy_cloudflare_workers_ai_model: str = "@cf/moonshotai/kimi-k2.5"
    llmproxy_huggingface_tgi_api_key: str | None = None
    llmproxy_huggingface_tgi_base_url: str = "http://localhost:3000/v1"
    llmproxy_huggingface_tgi_model: str = "tgi"
    llmproxy_replicate_api_token: str | None = None
    llmproxy_replicate_base_url: str = "https://api.replicate.com/v1"
    llmproxy_vertex_ai_access_token: str | None = None
    llmproxy_vertex_ai_base_url: str | None = None
    llmproxy_vertex_ai_project_id: str | None = None
    llmproxy_vertex_ai_location: str = "global"
    llmproxy_vertex_ai_model: str = "google/gemini-2.5-pro"
    llmproxy_anthropic_api_key: str | None = None
    llmproxy_anthropic_base_url: str = "https://api.anthropic.com/v1"
    llmproxy_anthropic_model: str = "claude-3-5-sonnet"
    llmproxy_google_api_key: str | None = None
    llmproxy_google_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    llmproxy_google_model: str = "gemini-2.5-pro"
    llmproxy_xai_api_key: str | None = None
    llmproxy_xai_base_url: str = "https://api.x.ai/v1"
    llmproxy_xai_model: str = "grok-3-mini"
    llmproxy_bedrock_region: str | None = None
    llmproxy_bedrock_access_key_id: str | None = None
    llmproxy_bedrock_secret_access_key: str | None = None
    llmproxy_bedrock_session_token: str | None = None
    llmproxy_bedrock_runtime_model_id: str | None = None
    llmproxy_bedrock_model: str = "anthropic.claude-3-5-sonnet"
    llmproxy_azure_openai_api_key: str | None = None
    llmproxy_azure_openai_endpoint: str | None = None
    llmproxy_azure_openai_api_version: str = "2024-10-21"
    llmproxy_azure_openai_model: str = "gpt-5"
    llmproxy_ollama_base_url: str = "http://localhost:11434"
    llmproxy_ollama_model: str = "qwen2.5-coder:14b"
    llmproxy_vllm_base_url: str = "http://localhost:8001/v1"
    llmproxy_llama_cpp_base_url: str = "http://localhost:8080/v1"
    llmproxy_mlx_base_url: str = "http://localhost:8081/v1"
    llmproxy_internal_api_base_url: str = "http://127.0.0.1:8000"
    llmproxy_lora_trainer_command: str | None = None
    llmproxy_qlora_trainer_command: str | None = None
    llmproxy_unsloth_trainer_command: str | None = None
    llmproxy_unsloth_studio_enabled: bool = False
    llmproxy_unsloth_studio_url: str = "http://127.0.0.1:8888"
    llmproxy_unsloth_studio_internal_url: str = "http://unsloth-studio:8000"
    llmproxy_unsloth_studio_password: str | None = None
    llmproxy_evaluation_command: str | None = None
    llmproxy_frontier_baseline_names: dict[str, str] = Field(
        default_factory=lambda: {
            "coding": "claude-3-5-sonnet",
            "software_architecture": "claude-3-5-sonnet",
            "writing_style": "gpt-5",
            "agent_systems": "gemini-2.5-pro",
        }
    )
    llmproxy_frontier_baseline_scores: dict[str, float] = Field(
        default_factory=lambda: {
            "coding": 0.92,
            "software_architecture": 0.91,
            "writing_style": 0.88,
            "agent_systems": 0.90,
        }
    )
    llmproxy_frontier_baseline_costs: dict[str, float] = Field(
        default_factory=lambda: {
            "coding": 0.12,
            "software_architecture": 0.14,
            "writing_style": 0.10,
            "agent_systems": 0.13,
        }
    )
    llmproxy_benchmarks_path: str = Field(
        default_factory=lambda: (
            str(path)
            if (path := Path(__file__).resolve().parent.parent / "benchmarks").exists()
            else ("/app/benchmarks" if Path("/app/benchmarks").exists() else "benchmarks")
        )
    )
    llmproxy_promotion_min_overall_score: float = 0.85
    llmproxy_promotion_domain_min_scores: dict[str, float] = Field(
        default_factory=lambda: {
            "coding": 0.80,
            "software_architecture": 0.85,
            "writing_style": 0.80,
        }
    )
    llmproxy_promotion_max_quality_delta_vs_frontier: float = 0.05
    llmproxy_promotion_min_value_per_dollar_gain_vs_frontier: float = 3.0
    llmproxy_auto_deploy_approved_evaluations: bool = False
    llmproxy_auto_deploy_deployment_mode: str = "production"
    llmproxy_exports_path: str = "/data/exports"
    llmproxy_datasets_path: str = "/data/datasets"
    llmproxy_models_path: str = "/data/models"
    llmproxy_checkpoints_path: str = "/data/checkpoints"
    llmproxy_reports_path: str = "/data/reports"
    llmproxy_logs_path: str = "/data/logs"
    llmproxy_trusted_operator_tokens: list[str] = Field(default_factory=list)
    llmproxy_automation_tokens: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def auth_tokens(self) -> set[str]:
        tokens = {self.llmproxy_bearer_token}
        tokens.update(token for token in self.llmproxy_trusted_operator_tokens if token)
        tokens.update(token for token in self.llmproxy_automation_tokens if token)
        return {token for token in tokens if token}

    @property
    def operator_tokens(self) -> set[str]:
        tokens = {self.llmproxy_bearer_token}
        tokens.update(token for token in self.llmproxy_trusted_operator_tokens if token)
        return {token for token in tokens if token}

    @property
    def automation_tokens(self) -> set[str]:
        return {token for token in self.llmproxy_automation_tokens if token}

    @property
    def database_backend(self) -> str:
        return make_url(self.llmproxy_database_url).get_backend_name()

    @staticmethod
    def _parse_job_type_filter(value: str | None) -> set[str]:
        if not value:
            return set()
        return {item.strip() for item in value.split(",") if item.strip()}

    @property
    def worker_include_job_types(self) -> set[str]:
        return self._parse_job_type_filter(self.llmproxy_worker_include_job_types)

    @property
    def worker_exclude_job_types(self) -> set[str]:
        return self._parse_job_type_filter(self.llmproxy_worker_exclude_job_types)

    @property
    def provider_configuration(self) -> dict[str, bool]:
        return {
            "openai": bool(self.llmproxy_openai_api_key),
            "groq": bool(self.llmproxy_groq_api_key),
            "mistral": bool(self.llmproxy_mistral_api_key),
            "deepseek": bool(self.llmproxy_deepseek_api_key),
            "cohere": bool(self.llmproxy_cohere_api_key),
            "together": bool(self.llmproxy_together_api_key),
            "fireworks": bool(self.llmproxy_fireworks_api_key),
            "perplexity": bool(self.llmproxy_perplexity_api_key),
            "cloudflare_workers_ai": bool(
                self.llmproxy_cloudflare_api_token
                and self.llmproxy_cloudflare_account_id
            ),
            "huggingface_tgi": bool(self.llmproxy_huggingface_tgi_base_url),
            "replicate": bool(self.llmproxy_replicate_api_token),
            "vertex_ai": bool(
                self.llmproxy_vertex_ai_access_token
                and (
                    self.llmproxy_vertex_ai_base_url
                    or self.llmproxy_vertex_ai_project_id
                )
            ),
            "anthropic": bool(self.llmproxy_anthropic_api_key),
            "google": bool(self.llmproxy_google_api_key),
            "xai": bool(self.llmproxy_xai_api_key),
            "azure_openai": bool(self.llmproxy_azure_openai_api_key and self.llmproxy_azure_openai_endpoint),
            "bedrock": bool(
                self.llmproxy_bedrock_region
                and self.llmproxy_bedrock_access_key_id
                and self.llmproxy_bedrock_secret_access_key
            ),
            "ollama": bool(self.llmproxy_ollama_base_url),
        }

    def configured_inbound_listeners(self) -> list[dict[str, Any]]:
        listeners = self.llmproxy_inbound_listeners or []
        if not listeners:
            return [
                {
                    "listener_id": "default",
                    "name": "Default API Listener",
                    "host": self.llmproxy_api_host,
                    "port": self.llmproxy_api_port,
                    "protocol": "http",
                    "published_host": "127.0.0.1",
                    "published_port": self.llmproxy_api_port,
                    "exposes_admin": True,
                    "exposes_platform_api": True,
                    "exposes_proxy": True,
                }
            ]
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(listeners):
            if not isinstance(item, dict):
                continue
            try:
                port = int(item.get("port", self.llmproxy_api_port))
            except (TypeError, ValueError):
                port = self.llmproxy_api_port
            try:
                published_port = int(item.get("published_port", port))
            except (TypeError, ValueError):
                published_port = port
            listener_id = str(item.get("listener_id") or item.get("id") or f"listener-{index + 1}").strip()
            host = str(item.get("host") or self.llmproxy_api_host).strip() or self.llmproxy_api_host
            protocol = str(item.get("protocol") or "http").strip().lower() or "http"
            published_host = str(item.get("published_host") or "127.0.0.1").strip() or "127.0.0.1"
            exposes_admin = bool(item.get("exposes_admin", True))
            exposes_platform_api = bool(item.get("exposes_platform_api", True))
            exposes_proxy = bool(item.get("exposes_proxy", True))
            normalized.append(
                {
                    "listener_id": listener_id,
                    "name": str(item.get("name") or listener_id).strip() or listener_id,
                    "host": host,
                    "port": port,
                    "protocol": protocol,
                    "published_host": published_host,
                    "published_port": published_port,
                    "exposes_admin": exposes_admin,
                    "exposes_platform_api": exposes_platform_api,
                    "exposes_proxy": exposes_proxy,
                }
            )
        return normalized

    def configured_model_monitors(self) -> list[dict[str, Any]]:
        monitors = self.llmproxy_model_monitors or []
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(monitors):
            if not isinstance(item, dict):
                continue
            provider_key = str(item.get("provider_key") or "").strip()
            model_id = str(item.get("model_id") or "").strip()
            if not provider_key or not model_id:
                continue
            try:
                frequency_minutes = int(item.get("frequency_minutes", 60))
            except (TypeError, ValueError):
                frequency_minutes = 60
            frequency_minutes = min(max(frequency_minutes, 5), 10_080)
            monitor_mode = str(item.get("monitor_mode") or "frontdoor_stream").strip().lower() or "frontdoor_stream"
            if monitor_mode not in {"frontdoor_stream", "provider_healthcheck"}:
                monitor_mode = "frontdoor_stream"
            monitor_id = str(item.get("monitor_id") or f"monitor-{index + 1}").strip() or f"monitor-{index + 1}"
            normalized.append(
                {
                    "monitor_id": monitor_id,
                    "label": str(item.get("label") or model_id).strip() or model_id,
                    "provider_key": provider_key,
                    "model_id": model_id,
                    "enabled": bool(item.get("enabled", True)),
                    "frequency_minutes": frequency_minutes,
                    "monitor_mode": monitor_mode,
                    "listener_id": str(item.get("listener_id") or "").strip() or None,
                    "prompt": str(item.get("prompt") or "Respond with OK.").strip() or "Respond with OK.",
                }
            )
        return normalized

    def admin_inbound_listeners(self) -> list[dict[str, Any]]:
        listeners = [listener for listener in self.configured_inbound_listeners() if bool(listener.get("exposes_admin"))]
        return listeners or self.configured_inbound_listeners()[:1]

    def platform_inbound_listeners(self) -> list[dict[str, Any]]:
        listeners = [listener for listener in self.configured_inbound_listeners() if bool(listener.get("exposes_platform_api"))]
        return listeners or self.admin_inbound_listeners()

    def proxy_inbound_listeners(self) -> list[dict[str, Any]]:
        listeners = [listener for listener in self.configured_inbound_listeners() if bool(listener.get("exposes_proxy"))]
        return listeners or self.configured_inbound_listeners()

    def resolve_inbound_listener(
        self,
        *,
        listener_id: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> dict[str, Any]:
        listeners = self.configured_inbound_listeners()
        if listener_id:
            target = listener_id.strip().lower()
            for listener in listeners:
                if str(listener.get("listener_id") or "").strip().lower() == target:
                    return listener
        normalized_host = str(host or "").strip().lower()
        for listener in listeners:
            listener_host = str(listener.get("host") or "").strip().lower()
            listener_port = int(listener.get("port") or 0)
            if port is not None and listener_port != int(port):
                continue
            if normalized_host and listener_host not in {normalized_host, "0.0.0.0", "::", "*"}:
                continue
            return listener
        return listeners[0]

    @staticmethod
    def _resolve_dotted_callable(path: str):
        module_name, _, attr_name = path.rpartition(".")
        if not module_name or not attr_name:
            raise ValueError(f"Invalid dotted callable path: {path}")
        module = import_module(module_name)
        value = getattr(module, attr_name)
        if not callable(value):
            raise TypeError(f"Configured guardrail hook is not callable: {path}")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
