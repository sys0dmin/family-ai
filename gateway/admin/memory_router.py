"""Parent-only CRUD API for confirmed long-term memory."""

import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.memory_schemas import (
    MemoryListResponse,
    MemoryResponse,
    MemoryWriteRequest,
)
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.db.session import get_session_factory
from gateway.app.memory import (
    MemoryNotFoundError,
    MemoryService,
    SqlAlchemyMemoryRepository,
)
from gateway.app.memory.service import MemoryDraft
from gateway.app.models import LongTermMemory, MemoryCategory

router = APIRouter(prefix="/api/memories", tags=["parent-managed memory"])


def get_memory_admin_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_memory_admin_service(
    session: Session = Depends(get_memory_admin_session),
) -> MemoryService:
    return MemoryService(SqlAlchemyMemoryRepository(session))


def _draft(payload: MemoryWriteRequest) -> MemoryDraft:
    return MemoryDraft(
        category=payload.category,
        topic=payload.topic,
        summary=payload.summary,
        source_type=payload.source_type,
        source_date=payload.source_date,
        source_note=payload.source_note,
    )


def _response(memory: LongTermMemory) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        category=MemoryCategory(memory.category),
        topic=memory.topic,
        summary=memory.summary,
        source_type=memory.source_type,
        source_date=memory.source_date,
        source_note=memory.source_note,
        created_by=memory.created_by,
        updated_by=memory.updated_by,
        confirmed_at=memory.confirmed_at,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


@router.get("", response_model=MemoryListResponse)
def list_memories(
    category: MemoryCategory | None = Query(default=None),
    _parent: str = Depends(verify_admin),
    service: MemoryService = Depends(get_memory_admin_service),
) -> MemoryListResponse:
    items = service.list(LERA_PROFILE_ID, category=category)
    return MemoryListResponse(
        items=[_response(item) for item in items],
        total=len(items),
    )


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryWriteRequest,
    parent: str = Depends(verify_admin),
    service: MemoryService = Depends(get_memory_admin_service),
) -> MemoryResponse:
    memory = service.create(LERA_PROFILE_ID, _draft(payload), parent)
    return _response(memory)


@router.put("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryWriteRequest,
    parent: str = Depends(verify_admin),
    service: MemoryService = Depends(get_memory_admin_service),
) -> MemoryResponse:
    try:
        memory = service.update(
            memory_id,
            LERA_PROFILE_ID,
            _draft(payload),
            parent,
        )
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory record not found") from exc
    return _response(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: uuid.UUID,
    _parent: str = Depends(verify_admin),
    service: MemoryService = Depends(get_memory_admin_service),
) -> Response:
    try:
        service.delete(memory_id, LERA_PROFILE_ID)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory record not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
