"""ASGI application factory for the Family AI Gateway."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gateway.app.config import get_settings
from gateway.app.routers.conversations import router as conversations_router
from gateway.app.routers.health import router as health_router
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

    @app.get("/")
    async def read_index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    app.include_router(health_router)
    app.include_router(conversations_router)
    app.include_router(voice_router)
    return app


app = create_app()
