"""Application entrypoint for llmProxy."""

import asyncio

from fastapi import Depends, FastAPI, Response

from app.api.dependencies import require_admin_listener
from app.config import get_settings
from app.api.admin import router as admin_router
from app.api.datasets import router as datasets_router
from app.api.deployment import router as deployment_router
from app.api.evaluation import router as evaluation_router
from app.api.models import router as models_router
from app.api.openai_compatible import router as openai_router
from app.api.proxy_native import router as proxy_router
from app.api.prompts import router as prompts_router
from app.api.training import router as training_router
from app.db.session import get_session_factory
from app.registry.model_registry import get_provider_registry
from app.services.observability import build_operations_summary
from app.services.provider_health import provider_health_snapshot
from app.services.provider_readiness import build_provider_readiness
from app.services.telemetry import configure_telemetry, prometheus_metrics_content_type, prometheus_metrics_payload


def create_app() -> FastAPI:
    app = FastAPI(title="llmProxy", version="0.1.0")
    settings = get_settings()
    configure_telemetry(settings)

    @app.get("/health")
    async def health() -> dict[str, object]:
        provider_registry = {}
        provider_readiness: list[dict[str, object]] = []
        try:
            session = get_session_factory()()
            try:
                provider_registry = get_provider_registry(settings, session=session)
                provider_readiness = await build_provider_readiness(settings, session=session)
            finally:
                session.close()
        except Exception:
            provider_registry = get_provider_registry(settings, session=None)
            provider_readiness = await build_provider_readiness(settings, session=None)
        ping_results = await asyncio.gather(
            *(provider.healthcheck() for provider in provider_registry.values()),
            return_exceptions=True,
        )
        provider_ping: dict[str, object] = {}
        for provider_key, result in zip(provider_registry.keys(), ping_results, strict=False):
            if isinstance(result, Exception):
                provider_ping[provider_key] = {"ok": False, "error": str(result)}
            else:
                provider_ping[provider_key] = result
        return {
            "status": "ok",
            "environment": settings.llmproxy_env,
            "database_backend": settings.database_backend,
            "redis_configured": bool(settings.llmproxy_redis_url),
            "provider_families_configured": settings.provider_configuration,
            "provider_ping": provider_ping,
            "provider_readiness": provider_readiness,
            "logs_path": settings.llmproxy_logs_path,
        }

    @app.get("/metrics", dependencies=[Depends(require_admin_listener)])
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
                "topology_counts": {},
                "request_count": 0,
                "recent_error_count": 0,
                "recent_audit_count": 0,
                "latest_request_id": None,
                "latest_evaluation_run_id": None,
                "provider_health": provider_health_snapshot(),
                "provider_configuration": settings.provider_configuration,
            }

    @app.get("/metrics/prometheus", dependencies=[Depends(require_admin_listener)])
    async def metrics_prometheus() -> Response:
        return Response(
            content=prometheus_metrics_payload(),
            media_type=prometheus_metrics_content_type(),
        )

    app.include_router(openai_router)
    app.include_router(prompts_router)
    app.include_router(admin_router)
    app.include_router(proxy_router)
    app.include_router(datasets_router)
    app.include_router(training_router)
    app.include_router(evaluation_router)
    app.include_router(models_router)
    app.include_router(deployment_router)
    return app


app = create_app()
