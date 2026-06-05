"""Configuration models for llmProxy."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llmproxy_env: str = "development"
    llmproxy_log_level: str = "INFO"
    llmproxy_api_host: str = "0.0.0.0"
    llmproxy_api_port: int = 8000
    llmproxy_database_url: str = "postgresql://llm:llm@localhost:5432/llmproxy"
    llmproxy_redis_url: str = "redis://localhost:6379/0"
    llmproxy_default_route_model: str = "proxy-auto"
    llmproxy_bearer_token: str = "change-me"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
