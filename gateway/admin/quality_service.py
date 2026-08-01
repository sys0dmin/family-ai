"""Parent-controlled quality workflow over retained history and test studio."""

import logging
import re
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from gateway.admin.quality_schemas import (
    ExpectedTechnicalError,
    FeedbackReasonCount,
    FeedbackResponse,
    FeedbackWriteRequest,
    QualitySummaryResponse,
    RegressionCasePreviewResponse,
    RegressionCaseResponse,
    RegressionCaseWriteRequest,
    RegressionComparison,
    RegressionRunResponse,
)
from gateway.admin.studio_service import StudioService
from gateway.app.models import (
    Agent,
    Conversation,
    FeedbackReason,
    Message,
    MessageFeedback,
    MessageRole,
    RegressionCase,
)

logger = logging.getLogger(__name__)


class QualityRecordNotFoundError(LookupError):
    """Requested message, feedback, or regression case does not exist."""


class InvalidFeedbackTargetError(ValueError):
    """Feedback cannot be converted into the requested quality artifact."""


class QualityService:
    """Own quality persistence without coupling it to conversation writes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_feedback(self, payload: FeedbackWriteRequest) -> FeedbackResponse:
        message = self._session.get(Message, payload.message_id)
        if message is None:
            raise QualityRecordNotFoundError("Message not found")
        if message.role != MessageRole.ASSISTANT:
            raise InvalidFeedbackTargetError(
                "Only an assistant reply can receive parent feedback"
            )
        feedback = self._session.scalar(
            select(MessageFeedback).where(
                MessageFeedback.message_id == payload.message_id
            )
        )
        if feedback is None:
            feedback = MessageFeedback(
                id=uuid.uuid4(),
                message_id=payload.message_id,
                reason=payload.reason.value,
                note=payload.note,
            )
            self._session.add(feedback)
        else:
            feedback.reason = payload.reason.value
            feedback.note = payload.note
        self._session.flush()
        self._session.refresh(feedback)
        return self._feedback_response(feedback)

    def delete_feedback(self, feedback_id: uuid.UUID) -> None:
        feedback = self._session.get(MessageFeedback, feedback_id)
        if feedback is None:
            raise QualityRecordNotFoundError("Feedback not found")
        self._session.execute(
            update(RegressionCase)
            .where(RegressionCase.source_feedback_id == feedback_id)
            .values(source_feedback_id=None)
        )
        self._session.delete(feedback)
        self._session.flush()

    def get_summary(self, *, days: int) -> QualitySummaryResponse:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        reasons = Counter(
            self._session.scalars(
                select(MessageFeedback.reason).where(
                    MessageFeedback.created_at >= cutoff
                )
            )
        )
        return QualitySummaryResponse(
            days=days,
            total_feedback=sum(reasons.values()),
            regression_cases=int(
                self._session.scalar(select(func.count(RegressionCase.id))) or 0
            ),
            reasons=[
                FeedbackReasonCount(reason=FeedbackReason(reason), count=count)
                for reason, count in reasons.most_common()
            ],
        )

    def preview_regression_case(
        self,
        feedback_id: uuid.UUID,
    ) -> RegressionCasePreviewResponse:
        feedback = self._session.get(MessageFeedback, feedback_id)
        if feedback is None:
            raise QualityRecordNotFoundError("Feedback not found")
        assistant_message = self._session.get(Message, feedback.message_id)
        if assistant_message is None:
            raise QualityRecordNotFoundError("Message not found")
        if assistant_message.role != MessageRole.ASSISTANT:
            raise InvalidFeedbackTargetError(
                "Only an assistant reply can seed a regression case"
            )
        conversation = self._session.get(
            Conversation,
            assistant_message.conversation_id,
        )
        if conversation is None:
            raise QualityRecordNotFoundError("Conversation not found")
        child_message = self._session.scalar(
            select(Message)
            .where(
                Message.conversation_id == assistant_message.conversation_id,
                Message.role == MessageRole.CHILD,
                Message.created_at <= assistant_message.created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        if child_message is None:
            raise InvalidFeedbackTargetError(
                "Assistant reply does not have a preceding child prompt"
            )
        title_source = " ".join(child_message.content.split())
        return RegressionCasePreviewResponse(
            source_feedback_id=feedback.id,
            agent_id=conversation.agent_id,
            title=(title_source[:77] + "…" if len(title_source) > 78 else title_source),
            prompt=child_message.content,
            expected_response=assistant_message.content,
        )

    def create_regression_case(
        self,
        payload: RegressionCaseWriteRequest,
    ) -> RegressionCaseResponse:
        if self._session.get(Agent, payload.agent_id) is None:
            raise QualityRecordNotFoundError("Agent not found")
        if (
            payload.source_feedback_id is not None
            and self._session.get(MessageFeedback, payload.source_feedback_id) is None
        ):
            raise QualityRecordNotFoundError("Source feedback not found")
        case = RegressionCase(
            id=uuid.uuid4(),
            source_feedback_id=payload.source_feedback_id,
            agent_id=payload.agent_id,
            title=payload.title,
            prompt=payload.prompt,
            expected_response=payload.expected_response,
            expected_safety_status=payload.expected_safety_status,
            expected_safety_rule_id=payload.expected_safety_rule_id,
            expected_technical_error=payload.expected_technical_error.value,
        )
        self._session.add(case)
        self._session.flush()
        self._session.refresh(case)
        return self._case_response(case)

    def list_regression_cases(self) -> list[RegressionCaseResponse]:
        cases = self._session.scalars(
            select(RegressionCase).order_by(RegressionCase.created_at.desc())
        )
        return [self._case_response(case) for case in cases]

    def delete_regression_case(self, case_id: uuid.UUID) -> None:
        case = self._session.get(RegressionCase, case_id)
        if case is None:
            raise QualityRecordNotFoundError("Regression case not found")
        self._session.delete(case)
        self._session.flush()

    async def run_regression_case(
        self,
        case_id: uuid.UUID,
        studio: StudioService,
    ) -> RegressionRunResponse:
        case = self._session.get(RegressionCase, case_id)
        if case is None:
            raise QualityRecordNotFoundError("Regression case not found")
        technical_error = ExpectedTechnicalError.NONE
        actual_response = ""
        actual_safety_status: str | None = None
        actual_safety_rule_id: str | None = None
        llm_duration_ms: int | None = None
        try:
            result = await studio.test_agent(case.agent_id, case.prompt)
            actual_response = result.final_response
            actual_safety_status = result.safety_status
            actual_safety_rule_id = result.safety_rule_id
            llm_duration_ms = result.llm_duration_ms
        except Exception:
            technical_error = ExpectedTechnicalError.PROVIDER_ERROR
            logger.exception(
                "regression_case_run_failed",
                extra={"regression_case_id": str(case.id)},
            )

        response_matches = self._normalize_text(actual_response) == self._normalize_text(
            case.expected_response
        )
        safety_status_matches = actual_safety_status == case.expected_safety_status
        safety_rule_matches = actual_safety_rule_id == case.expected_safety_rule_id
        technical_error_matches = technical_error.value == case.expected_technical_error
        comparison = RegressionComparison(
            response_matches=response_matches,
            safety_status_matches=safety_status_matches,
            safety_rule_matches=safety_rule_matches,
            technical_error_matches=technical_error_matches,
            overall_matches=(
                response_matches
                and safety_status_matches
                and safety_rule_matches
                and technical_error_matches
            ),
        )
        return RegressionRunResponse(
            case_id=case.id,
            actual_response=actual_response,
            actual_safety_status=actual_safety_status,
            actual_safety_rule_id=actual_safety_rule_id,
            actual_technical_error=technical_error,
            llm_duration_ms=llm_duration_ms,
            comparison=comparison,
        )

    def export_regression_cases(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
            "cases": [
                response.model_dump(mode="json")
                for response in self.list_regression_cases()
            ],
        }

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    @staticmethod
    def _feedback_response(feedback: MessageFeedback) -> FeedbackResponse:
        return FeedbackResponse(
            id=feedback.id,
            message_id=feedback.message_id,
            reason=FeedbackReason(feedback.reason),
            note=feedback.note,
            created_at=feedback.created_at,
            updated_at=feedback.updated_at,
        )

    @staticmethod
    def _case_response(case: RegressionCase) -> RegressionCaseResponse:
        return RegressionCaseResponse(
            id=case.id,
            source_feedback_id=case.source_feedback_id,
            agent_id=case.agent_id,
            title=case.title,
            prompt=case.prompt,
            expected_response=case.expected_response,
            expected_safety_status=case.expected_safety_status,
            expected_safety_rule_id=case.expected_safety_rule_id,
            expected_technical_error=case.expected_technical_error,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )
