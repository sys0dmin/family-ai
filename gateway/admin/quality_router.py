"""Protected parent quality and confirmed regression case endpoints."""

import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.quality_schemas import (
    FeedbackResponse,
    FeedbackWriteRequest,
    QualitySummaryResponse,
    RegressionCaseListResponse,
    RegressionCasePreviewResponse,
    RegressionCaseResponse,
    RegressionCaseWriteRequest,
    RegressionRunResponse,
)
from gateway.admin.quality_service import (
    InvalidFeedbackTargetError,
    QualityRecordNotFoundError,
    QualityService,
)
from gateway.admin.studio_router import get_studio_service
from gateway.admin.studio_service import StudioService
from gateway.app.db.session import get_session_factory

router = APIRouter(prefix="/api/quality", tags=["parent quality"])


def get_quality_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_quality_service(
    session: Session = Depends(get_quality_session),
) -> QualityService:
    return QualityService(session)


def _not_found(exc: QualityRecordNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/summary", response_model=QualitySummaryResponse)
def get_quality_summary(
    days: int = Query(default=10, ge=1, le=365),
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
) -> QualitySummaryResponse:
    return service.get_summary(days=days)


@router.post("/feedback", response_model=FeedbackResponse)
def upsert_feedback(
    payload: FeedbackWriteRequest,
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
) -> FeedbackResponse:
    try:
        return service.upsert_feedback(payload)
    except QualityRecordNotFoundError as exc:
        raise _not_found(exc) from exc
    except InvalidFeedbackTargetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback(
    feedback_id: uuid.UUID,
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
) -> Response:
    try:
        service.delete_feedback(feedback_id)
    except QualityRecordNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/feedback/{feedback_id}/regression-preview",
    response_model=RegressionCasePreviewResponse,
)
def preview_regression_case(
    feedback_id: uuid.UUID,
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
) -> RegressionCasePreviewResponse:
    try:
        return service.preview_regression_case(feedback_id)
    except QualityRecordNotFoundError as exc:
        raise _not_found(exc) from exc
    except InvalidFeedbackTargetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/regression-cases", response_model=RegressionCaseListResponse)
def list_regression_cases(
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
) -> RegressionCaseListResponse:
    items = service.list_regression_cases()
    return RegressionCaseListResponse(items=items, total=len(items))


@router.post(
    "/regression-cases",
    response_model=RegressionCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_regression_case(
    payload: RegressionCaseWriteRequest,
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
) -> RegressionCaseResponse:
    try:
        return service.create_regression_case(payload)
    except QualityRecordNotFoundError as exc:
        raise _not_found(exc) from exc


@router.delete(
    "/regression-cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_regression_case(
    case_id: uuid.UUID,
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
) -> Response:
    try:
        service.delete_regression_case(case_id)
    except QualityRecordNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/regression-cases/{case_id}/run",
    response_model=RegressionRunResponse,
)
async def run_regression_case(
    case_id: uuid.UUID,
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
    studio: StudioService = Depends(get_studio_service),
) -> RegressionRunResponse:
    try:
        return await service.run_regression_case(case_id, studio)
    except QualityRecordNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/regression-cases-export")
def export_regression_cases(
    _parent: str = Depends(verify_admin),
    service: QualityService = Depends(get_quality_service),
) -> JSONResponse:
    return JSONResponse(
        service.export_regression_cases(),
        headers={
            "Content-Disposition": (
                'attachment; filename="family-ai-regression-cases.json"'
            ),
            "Cache-Control": "no-store",
        },
    )
