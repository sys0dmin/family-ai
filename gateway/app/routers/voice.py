from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from uuid import UUID
from fastapi.responses import Response

from gateway.app.dependencies import get_voice_service
from gateway.app.services.voice_service import VoiceService

router = APIRouter(prefix="/v1/voice", tags=["voice"])

@router.post("/{conversation_id}/turn")
async def voice_turn(
    conversation_id: UUID,
    file: UploadFile = File(...),
    voice_service: VoiceService = Depends(get_voice_service)
):
    """
    Принимает аудиофайл, возвращает аудио-ответ ассистента.
    """
    content = await file.read()
    
    # Определяем расширение файла
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "wav"
    
    audio_response = await voice_service.process_voice_turn(
        conversation_id=conversation_id,
        audio_content=content,
        extension=ext
    )
    
    if not audio_response:
        raise HTTPException(status_code=500, detail="Ошибка обработки голосового сообщения")

    # Возвращаем аудио (OpenAI обычно отдает mp3)
    return Response(content=audio_response, media_type="audio/mpeg")
