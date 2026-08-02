"""Protected endpoints for stateless agent and speech testing."""

from collections.abc import Generator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.studio_schemas import (
    AgentTestRequest,
    AgentTestResponse,
    SpeechPreviewRequest,
    TranscriptionTestResponse,
    VisionTestResponse,
)
from gateway.admin.studio_service import StudioCapabilityUnavailableError, StudioService
from gateway.app.agents import SqlAlchemyAgentRepository
from gateway.app.config import Settings, get_settings
from gateway.app.db.session import get_session_factory
from gateway.app.dependencies import (
    get_chat_provider,
    get_image_understanding_provider,
    get_safety_service,
    get_speech_recognition_provider,
    get_speech_synthesis_provider,
)
from gateway.app.memory import MemoryService, SqlAlchemyMemoryRepository
from gateway.app.providers.contracts import (
    ChatProvider,
    ImageUnderstandingProvider,
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)
from gateway.app.services.agent_service import (
    AgentConfigurationError,
    AgentNotFoundError,
    AgentService,
)
from gateway.app.services.image_understanding_service import (
    ALLOWED_IMAGE_TYPES,
    matches_image_signature,
)
from gateway.app.services.safety_service import SafetyService
from gateway.app.upload_formats import normalized_content_type, safe_audio_filename

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
    recognition_provider: SpeechRecognitionProvider = Depends(
        get_speech_recognition_provider
    ),
    image_provider: ImageUnderstandingProvider | None = Depends(
        get_image_understanding_provider
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
        recognition_provider=recognition_provider,
        image_provider=image_provider,
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


@router.post("/transcription", response_model=TranscriptionTestResponse)
async def test_transcription(
    file: UploadFile = File(...),
    _user: str = Depends(verify_admin),
    service: StudioService = Depends(get_studio_service),
    settings: Settings = Depends(get_settings),
) -> TranscriptionTestResponse:
    content_type = normalized_content_type(file.content_type)
    filename = safe_audio_filename(file.filename, content_type)
    if filename is None:
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported synthetic audio format",
        )
    content = await file.read(settings.voice_max_audio_bytes + 1)
    await file.close()
    if not content or len(content) > settings.voice_max_audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Synthetic audio is empty or too large",
        )
    try:
        result = await service.transcribe(
            content,
            filename=filename,
            content_type=content_type,
        )
    except StudioCapabilityUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return TranscriptionTestResponse(
        text=result.text.strip(),
        confidence=result.confidence,
        duration_ms=result.duration_ms,
    )


@router.post("/vision", response_model=VisionTestResponse)
async def test_vision(
    file: UploadFile = File(...),
    question: str = Form(min_length=1, max_length=500),
    _user: str = Depends(verify_admin),
    service: StudioService = Depends(get_studio_service),
    settings: Settings = Depends(get_settings),
) -> VisionTestResponse:
    content_type = normalized_content_type(file.content_type)
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG and WebP images are supported",
        )
    content = await file.read(settings.vision_max_image_bytes + 1)
    await file.close()
    if (
        not content
        or len(content) > settings.vision_max_image_bytes
        or not matches_image_signature(content, content_type)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Synthetic image is empty, too large or invalid",
        )
    normalized_question = question.strip()
    if not normalized_question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question must not be blank",
        )
    try:
        description = await service.inspect_image(
            content,
            content_type=content_type,
            question=normalized_question,
        )
    except StudioCapabilityUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return VisionTestResponse(description=description)
