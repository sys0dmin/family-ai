"""Read-only parent history viewer routes."""

from collections.abc import Generator

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.history_schemas import (
    ConversationHistoryResponse,
    HistorySummaryResponse,
)
from gateway.admin.history_service import HistoryService
from gateway.app.db.session import get_session_factory

router = APIRouter(prefix="/api/history", tags=["history"])


def get_history_session() -> Generator[Session]:
    """Yield a read-only session without committing a GET request."""

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_history_service(
    session: Session = Depends(get_history_session),
) -> HistoryService:
    return HistoryService(session)


@router.get("/summary", response_model=HistorySummaryResponse)
def get_history_summary(
    days: int = Query(default=10, ge=1, le=30),
    _user: str = Depends(verify_admin),
    service: HistoryService = Depends(get_history_service),
) -> HistorySummaryResponse:
    """Return aggregate activity without writing or logging message content."""

    return service.get_summary(days=days)


@router.get("/conversations", response_model=ConversationHistoryResponse)
def get_conversation_history(
    days: int = Query(default=10, ge=1, le=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    search: str | None = Query(default=None, max_length=200),
    _user: str = Depends(verify_admin),
    service: HistoryService = Depends(get_history_service),
) -> ConversationHistoryResponse:
    """Return retained transcripts for the protected parent viewer."""

    return service.get_conversations(
        days=days,
        page=page,
        page_size=page_size,
        search=search,
    )
