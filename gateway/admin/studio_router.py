"""Protected endpoints for stateless agent and speech testing."""

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.studio_schemas import (
    AgentTestRequest,
    AgentTestResponse,
    SpeechPreviewRequest,
)
from gateway.admin.studio_service import StudioService
from gateway.app.agents import SqlAlchemyAgentRepository
from gateway.app.db.session import get_session_factory
from gateway.app.dependencies import (
    get_chat_provider,
    get_safety_service,
    get_speech_synthesis_provider,
)
from gateway.app.memory import MemoryService, SqlAlchemyMemoryRepository
from gateway.app.providers.contracts import ChatProvider, SpeechSynthesisProvider
from gateway.app.services.agent_service import (
    AgentConfigurationError,
    AgentNotFoundError,
    AgentService,
)
from gateway.app.services.safety_service import SafetyService

router = APIRouter(prefix="/api/studio", tags=["studio"])


def get_studio_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_studio_service(
    session: Session = Depends(get_studio_session),
    chat_provider: ChatProvider = Depends(get_chat_provider),
    synthesis_provider: SpeechSynthesisProvider = Depends(
        get_speech_synthesis_provider
    ),
    safety: SafetyService = Depends(get_safety_service),
) -> StudioService:
    agents = AgentService(SqlAlchemyAgentRepository(session))
    memory = MemoryService(SqlAlchemyMemoryRepository(session))
    return StudioService(
        chat_provider,
        synthesis_provider,
        agents,
        safety,
        memory,
    )


@router.post("/agent-test", response_model=AgentTestResponse)
async def test_agent(
    payload: AgentTestRequest,
    _user: str = Depends(verify_admin),
    service: StudioService = Depends(get_studio_service),
) -> AgentTestResponse:
    try:
        return await service.test_agent(payload.agent_id, payload.prompt.strip())
    except (AgentNotFoundError, AgentConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent is unavailable",
        ) from exc


@router.post("/speech", response_class=Response)
async def preview_speech(
    payload: SpeechPreviewRequest,
    _user: str = Depends(verify_admin),
    service: StudioService = Depends(get_studio_service),
) -> Response:
    speech = await service.synthesize(payload.text.strip(), payload.voice.strip())
    return Response(
        content=speech.audio_content,
        media_type=speech.content_type,
        headers={"Cache-Control": "no-store"},
    )
