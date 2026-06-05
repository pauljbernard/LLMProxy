"""Application entrypoint for llmProxy."""

from fastapi import FastAPI

from app.api.datasets import router as datasets_router
from app.api.deployment import router as deployment_router
from app.api.evaluation import router as evaluation_router
from app.api.models import router as models_router
from app.api.openai_compatible import router as openai_router
from app.api.proxy_native import router as proxy_router
from app.api.training import router as training_router


def create_app() -> FastAPI:
    app = FastAPI(title="llmProxy", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(openai_router)
    app.include_router(proxy_router)
    app.include_router(datasets_router)
    app.include_router(training_router)
    app.include_router(evaluation_router)
    app.include_router(models_router)
    app.include_router(deployment_router)
    return app


app = create_app()
