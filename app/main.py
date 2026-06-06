"""Application entrypoint for llmProxy."""

from fastapi import FastAPI

from app.config import get_settings
from app.api.admin import router as admin_router
from app.api.datasets import router as datasets_router
from app.api.deployment import router as deployment_router
from app.api.evaluation import router as evaluation_router
from app.api.models import router as models_router
from app.api.openai_compatible import router as openai_router
from app.api.proxy_native import router as proxy_router
from app.api.training import router as training_router
from app.db.session import get_session_factory
from app.services.observability import build_operations_summary
from app.services.provider_health import provider_health_snapshot


def create_app() -> FastAPI:
    app = FastAPI(title="llmProxy", version="0.1.0")
    settings = get_settings()

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "environment": settings.llmproxy_env,
            "database_backend": settings.database_backend,
            "redis_configured": bool(settings.llmproxy_redis_url),
            "provider_families_configured": {
                "openai": bool(settings.llmproxy_openai_api_key),
                "anthropic": bool(settings.llmproxy_anthropic_api_key),
                "google": bool(settings.llmproxy_google_api_key),
                "xai": bool(settings.llmproxy_xai_api_key),
                "azure_openai": bool(settings.llmproxy_azure_openai_api_key and settings.llmproxy_azure_openai_endpoint),
                "bedrock": bool(
                    settings.llmproxy_bedrock_region
                    and settings.llmproxy_bedrock_access_key_id
                    and settings.llmproxy_bedrock_secret_access_key
                ),
                "ollama": bool(settings.llmproxy_ollama_base_url),
            },
            "logs_path": settings.llmproxy_logs_path,
        }

    @app.get("/metrics")
    async def metrics() -> dict[str, object]:
        try:
            session = get_session_factory()()
            try:
                return build_operations_summary(session, settings=settings)
            finally:
                session.close()
        except Exception as exc:
            return {
                "generated_at": None,
                "degraded": True,
                "error": str(exc),
                "logs_path": settings.llmproxy_logs_path,
                "job_counts": {},
                "event_counts": {},
                "route_counts": {},
                "request_count": 0,
                "recent_error_count": 0,
                "recent_audit_count": 0,
                "latest_request_id": None,
                "latest_evaluation_run_id": None,
                "provider_health": provider_health_snapshot(),
                "provider_configuration": {
                    "openai": bool(settings.llmproxy_openai_api_key),
                    "anthropic": bool(settings.llmproxy_anthropic_api_key),
                    "google": bool(settings.llmproxy_google_api_key),
                    "xai": bool(settings.llmproxy_xai_api_key),
                    "azure_openai": bool(settings.llmproxy_azure_openai_api_key and settings.llmproxy_azure_openai_endpoint),
                    "bedrock": bool(
                        settings.llmproxy_bedrock_region
                        and settings.llmproxy_bedrock_access_key_id
                        and settings.llmproxy_bedrock_secret_access_key
                    ),
                    "ollama": bool(settings.llmproxy_ollama_base_url),
                },
            }

    app.include_router(openai_router)
    app.include_router(admin_router)
    app.include_router(proxy_router)
    app.include_router(datasets_router)
    app.include_router(training_router)
    app.include_router(evaluation_router)
    app.include_router(models_router)
    app.include_router(deployment_router)
    return app


app = create_app()
