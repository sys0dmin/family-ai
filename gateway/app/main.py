"""ASGI application factory for the Family AI Gateway."""

from fastapi import FastAPI

from gateway.app.config import get_settings
from gateway.app.routers.health import router as health_router


def create_app() -> FastAPI:
    """Create the Gateway API without binding it to infrastructure details."""

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Internal API for the Family AI Mentor Gateway.",
    )
    app.include_router(health_router)
    return app


app = create_app()

