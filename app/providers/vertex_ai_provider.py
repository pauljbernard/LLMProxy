"""Vertex AI OpenAI-compatible provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class VertexAIProvider(OpenAIProvider):
    provider_family = "Vertex AI"
    provider_name = "vertex_ai"
    price_per_token = 0.00001
    api_key_config_field = "llmproxy_vertex_ai_access_token"

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "VertexAIProvider":
        return cls(
            settings.llmproxy_vertex_ai_model,
            api_key=settings.llmproxy_vertex_ai_access_token,
            base_url=cls._base_url_from_settings(settings),
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )

    @staticmethod
    def _base_url_from_settings(settings: Settings) -> str:
        if settings.llmproxy_vertex_ai_base_url:
            return settings.llmproxy_vertex_ai_base_url
        project_id = settings.llmproxy_vertex_ai_project_id
        if not project_id:
            return "https://aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/global/endpoints/openapi"
        location = settings.llmproxy_vertex_ai_location or "global"
        return (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{project_id}/locations/{location}/endpoints/openapi"
        )
