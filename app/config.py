"""Configuration models for llmProxy."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    llmproxy_env: str = "development"
    llmproxy_log_level: str = "INFO"
    llmproxy_api_host: str = "0.0.0.0"
    llmproxy_api_port: int = 8000
    llmproxy_database_url: str = "postgresql+psycopg://llm:llm@localhost:5432/llmproxy"
    llmproxy_redis_url: str = "redis://localhost:6379/0"
    llmproxy_db_pool_size: int = 10
    llmproxy_db_max_overflow: int = 20
    llmproxy_database_wait_timeout_seconds: int = 30
    llmproxy_run_migrations_on_start: bool = True
    llmproxy_provider_timeout_seconds: float = 60.0
    llmproxy_training_backend_timeout_seconds: int = 14400
    llmproxy_evaluation_timeout_seconds: int = 3600
    llmproxy_worker_include_job_types: str | None = None
    llmproxy_worker_exclude_job_types: str | None = None
    llmproxy_default_route_model: str = "proxy-auto"
    llmproxy_bearer_token: str = "change-me"
    llmproxy_openai_api_key: str | None = None
    llmproxy_openai_base_url: str = "https://api.openai.com/v1"
    llmproxy_openai_model: str = "gpt-5.5"
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
    llmproxy_azure_openai_model: str = "gpt-5.5"
    llmproxy_ollama_base_url: str = "http://localhost:11434"
    llmproxy_ollama_model: str = "qwen2.5-coder:14b"
    llmproxy_lora_trainer_command: str | None = None
    llmproxy_qlora_trainer_command: str | None = None
    llmproxy_evaluation_command: str | None = None
    llmproxy_frontier_baseline_names: dict[str, str] = Field(
        default_factory=lambda: {
            "coding": "claude-3-5-sonnet",
            "software_architecture": "claude-3-5-sonnet",
            "writing_style": "gpt-5.5",
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
