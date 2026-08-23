"""Composition root for the standalone Family AI parent control room."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from gateway.admin.activity_router import router as activity_router
from gateway.admin.agents_router import router as agents_router
from gateway.admin.auth import verify_admin
from gateway.admin.calibration_router import router as calibration_router
from gateway.admin.diagnostics_router import router as diagnostics_router
from gateway.admin.history_router import router as history_router
from gateway.admin.memory_router import router as memory_router
from gateway.admin.monitoring_router import router as monitoring_router
from gateway.admin.quality_router import router as quality_router
from gateway.admin.release_passport_router import router as release_passport_router
from gateway.admin.safety_policy_router import router as safety_policy_router
from gateway.admin.session_router import router as session_router
from gateway.admin.settings_router import router as settings_router
from gateway.admin.speech_runtime_router import router as speech_runtime_router
from gateway.admin.studio_router import router as studio_router
from gateway.admin.system_router import router as system_router
from gateway.admin.voice_observability_router import router as voice_observability_router

# Backward-compatible dependency identity used by existing Admin integration tests.
_verify_admin = verify_admin


class RevalidatingStaticFiles(StaticFiles):
    """Prevent stale Admin modules from surviving a release switch."""

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


def create_app() -> FastAPI:
    """Assemble Admin routes without owning their business logic."""

    application = FastAPI(title="Family AI Admin", version="0.1.0")
    application.mount(
        "/admin-assets",
        RevalidatingStaticFiles(directory=Path(__file__).with_name("static")),
        name="admin-assets",
    )
    for router in (
        session_router,
        settings_router,
        history_router,
        agents_router,
        activity_router,
        monitoring_router,
        release_passport_router,
        system_router,
        studio_router,
        voice_observability_router,
        calibration_router,
        diagnostics_router,
        speech_runtime_router,
        safety_policy_router,
        memory_router,
        quality_router,
    ):
        application.include_router(router)

    @application.get("/", response_class=HTMLResponse)
    def admin_index() -> HTMLResponse:
        admin_page = Path(__file__).with_name("panel.html")
        return HTMLResponse(
            admin_page.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/api/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gateway.admin.main:app", host="0.0.0.0", port=8001)
