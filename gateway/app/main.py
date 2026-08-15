"""ASGI application factory for the Family AI Gateway."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gateway.app.config import get_settings
from gateway.app.observability.runtime_identity import client_build_registry
from gateway.app.routers.activities import router as activities_router
from gateway.app.routers.agents import router as agents_router
from gateway.app.routers.calibration import router as calibration_router
from gateway.app.routers.conversations import router as conversations_router
from gateway.app.routers.health import router as health_router
from gateway.app.routers.internal_metrics import router as internal_metrics_router
from gateway.app.routers.media import router as media_router
from gateway.app.routers.multimodal import router as multimodal_router
from gateway.app.routers.vision import router as vision_router
from gateway.app.routers.voice import router as voice_router


def create_app() -> FastAPI:
    """Create the Gateway API without binding it to infrastructure details."""

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Internal API for the Family AI Mentor Gateway.",
    )

    static_dir = Path(__file__).resolve().parents[1] / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def observe_client_build(request: Request, call_next):
        client_build_registry.observe(
            request.headers.get("X-Family-AI-App-Version"),
            request.headers.get("X-Family-AI-App-Commit"),
        )
        return await call_next(request)

    @app.get("/")
    async def read_index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    app.include_router(health_router)
    app.include_router(agents_router)
    app.include_router(activities_router)
    app.include_router(conversations_router)
    app.include_router(media_router)
    app.include_router(voice_router)
    app.include_router(vision_router)
    app.include_router(multimodal_router)
    app.include_router(calibration_router)
    app.include_router(internal_metrics_router)
    return app


app = create_app()
