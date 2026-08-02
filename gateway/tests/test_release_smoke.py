"""Functional release smoke-test orchestration tests."""

import httpx

from gateway.app.config import Settings
from gateway.smoke import ReleaseSmokeRunner, SmokeStageError


def _settings(*, vision_enabled: bool = True) -> Settings:
    return Settings(
        admin_username="smoke-admin",
        admin_password="smoke-password",
        default_agent_id="teacher_friend",
        tts_voice="xenia",
        vision_provider="openai_compatible" if vision_enabled else "disabled",
    )


def _successful_transport(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/":
        return httpx.Response(200, text="<title>Family AI</title>")
    if path in {"/admin-assets/admin.css", "/admin-assets/js/app.js"}:
        return httpx.Response(200, content=b"asset")
    if path == "/v1/agents":
        return httpx.Response(200, json={"items": [{"id": "teacher_friend"}]})
    if path == "/api/studio/agent-test":
        return httpx.Response(200, json={"final_response": "Готово"})
    if path == "/api/studio/speech":
        return httpx.Response(
            200,
            content=b"RIFF" + b"\x00" * 256,
            headers={"content-type": "audio/wav"},
        )
    if path == "/api/studio/transcription":
        return httpx.Response(200, json={"text": "Проверка связи"})
    if path == "/api/studio/vision":
        return httpx.Response(200, json={"description": "Синий квадрат"})
    return httpx.Response(404)


def test_release_smoke_exercises_all_functional_stages() -> None:
    with httpx.Client(transport=httpx.MockTransport(_successful_transport)) as client:
        results = ReleaseSmokeRunner(
            client,
            _settings(),
            gateway_url="http://gateway",
            admin_url="http://admin",
        ).run()

    assert [item.name for item in results] == [
        "admin_ui",
        "gateway_database",
        "llm",
        "tts",
        "stt",
        "vision",
    ]
    assert all(item.status == "passed" for item in results)


def test_release_smoke_reports_the_exact_failed_stage() -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/studio/agent-test":
            return httpx.Response(502)
        return _successful_transport(request)

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        try:
            ReleaseSmokeRunner(
                client,
                _settings(),
                gateway_url="http://gateway",
                admin_url="http://admin",
            ).run()
        except SmokeStageError as exc:
            assert exc.stage == "llm"
            assert exc.reason == "HTTP 502"
        else:
            raise AssertionError("SmokeStageError was not raised")


def test_release_smoke_marks_disabled_vision_as_skipped() -> None:
    requested_paths: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return _successful_transport(request)

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        results = ReleaseSmokeRunner(
            client,
            _settings(vision_enabled=False),
            gateway_url="http://gateway",
            admin_url="http://admin",
        ).run()

    assert results[-1].status == "skipped"
    assert "/api/studio/vision" not in requested_paths
