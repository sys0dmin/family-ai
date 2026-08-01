"""Read-only projections for the parent history dashboard."""

import math
import re
import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from gateway.admin.history_schemas import (
    ConversationHistoryItem,
    ConversationHistoryResponse,
    DailyActivityPoint,
    FrequentQuestion,
    HistoryFeedbackResponse,
    HistoryMessageResponse,
    HistorySummaryResponse,
)
from gateway.app.models import Conversation, Message, MessageRole

QUESTION_PREFIXES = (
    "как ",
    "где ",
    "зачем ",
    "когда ",
    "кто ",
    "можно ",
    "почему ",
    "расскажи ",
    "что ",
)


class HistoryService:
    """Build bounded, read-only views over retained conversation messages."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_summary(
        self,
        *,
        days: int,
        now: datetime | None = None,
    ) -> HistorySummaryResponse:
        current_time = now or datetime.now(UTC)
        first_day, cutoff = self._period_start(current_time, days)
        messages = list(
            self._session.scalars(
                select(Message)
                .where(Message.created_at >= cutoff)
                .order_by(Message.created_at.asc())
            )
        )

        child_messages = [message for message in messages if message.role == MessageRole.CHILD]
        assistant_messages = [
            message for message in messages if message.role == MessageRole.ASSISTANT
        ]
        daily_counts: dict[date, Counter[str]] = defaultdict(Counter)
        for message in messages:
            daily_counts[message.created_at.date()][str(message.role)] += 1

        active_days = len(daily_counts)
        daily_activity = []
        for day_offset in range(days):
            activity_day = first_day + timedelta(days=day_offset)
            counts = daily_counts[activity_day]
            daily_activity.append(
                DailyActivityPoint(
                    day=activity_day,
                    child_messages=counts[MessageRole.CHILD],
                    assistant_messages=counts[MessageRole.ASSISTANT],
                )
            )

        return HistorySummaryResponse(
            days=days,
            total_messages=len(messages),
            child_messages=len(child_messages),
            assistant_messages=len(assistant_messages),
            conversations=len({message.conversation_id for message in messages}),
            active_days=active_days,
            average_response_seconds=self._average_response_seconds(messages),
            daily_activity=daily_activity,
            frequent_questions=self._frequent_questions(child_messages),
        )

    def get_conversations(
        self,
        *,
        days: int,
        page: int,
        page_size: int,
        search: str | None = None,
        now: datetime | None = None,
    ) -> ConversationHistoryResponse:
        current_time = now or datetime.now(UTC)
        _first_day, cutoff = self._period_start(current_time, days)
        conditions = [Message.created_at >= cutoff]
        normalized_search = (search or "").strip()
        if normalized_search:
            matching_conversations = select(Message.conversation_id).where(
                Message.created_at >= cutoff,
                Message.content.ilike(f"%{normalized_search}%"),
            )
            conditions.append(Message.conversation_id.in_(matching_conversations))

        grouped = (
            select(
                Message.conversation_id.label("conversation_id"),
                func.max(Message.created_at).label("last_message_at"),
                func.count(Message.id).label("message_count"),
            )
            .where(*conditions)
            .group_by(Message.conversation_id)
            .subquery()
        )
        total = int(
            self._session.scalar(select(func.count()).select_from(grouped)) or 0
        )
        rows = self._session.execute(
            select(
                grouped.c.conversation_id,
                grouped.c.last_message_at,
                grouped.c.message_count,
                Conversation.started_at,
            )
            .join(Conversation, Conversation.id == grouped.c.conversation_id)
            .order_by(grouped.c.last_message_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        conversation_ids = [row.conversation_id for row in rows]
        messages_by_conversation: dict[uuid.UUID, list[HistoryMessageResponse]] = defaultdict(list)
        if conversation_ids:
            page_messages = self._session.scalars(
                select(Message)
                .options(selectinload(Message.feedback))
                .where(
                    Message.conversation_id.in_(conversation_ids),
                    Message.created_at >= cutoff,
                )
                .order_by(Message.created_at.asc())
            )
            for message in page_messages:
                messages_by_conversation[message.conversation_id].append(
                    HistoryMessageResponse(
                        id=message.id,
                        role=str(message.role),
                        content=message.content,
                        created_at=message.created_at,
                        feedback=(
                            HistoryFeedbackResponse(
                                id=message.feedback.id,
                                reason=message.feedback.reason,
                                note=message.feedback.note,
                            )
                            if message.feedback is not None
                            else None
                        ),
                    )
                )

        items = [
            ConversationHistoryItem(
                conversation_id=row.conversation_id,
                started_at=row.started_at,
                last_message_at=row.last_message_at,
                message_count=row.message_count,
                messages=messages_by_conversation[row.conversation_id],
            )
            for row in rows
        ]
        return ConversationHistoryResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

    @staticmethod
    def _period_start(current_time: datetime, days: int) -> tuple[date, datetime]:
        first_day = current_time.date() - timedelta(days=days - 1)
        timezone = current_time.tzinfo or UTC
        return first_day, datetime.combine(first_day, time.min, tzinfo=timezone)

    @staticmethod
    def _average_response_seconds(messages: list[Message]) -> float | None:
        pending_child: dict[uuid.UUID, datetime] = {}
        response_times: list[float] = []
        for message in messages:
            if message.role == MessageRole.CHILD:
                pending_child[message.conversation_id] = message.created_at
                continue
            child_created_at = pending_child.pop(message.conversation_id, None)
            if child_created_at is not None:
                response_times.append(
                    max(0.0, (message.created_at - child_created_at).total_seconds())
                )
        if not response_times:
            return None
        return round(sum(response_times) / len(response_times), 1)

    @staticmethod
    def _frequent_questions(messages: list[Message]) -> list[FrequentQuestion]:
        counts: Counter[str] = Counter()
        examples: dict[str, str] = {}
        for message in messages:
            compact = " ".join(message.content.split()).strip()
            normalized = re.sub(r"[^\w\s]", "", compact.casefold()).strip()
            if len(normalized) < 3:
                continue
            if "?" not in compact and not normalized.startswith(QUESTION_PREFIXES):
                continue
            counts[normalized] += 1
            examples.setdefault(normalized, compact)

        return [
            FrequentQuestion(text=examples[text], count=count)
            for text, count in counts.most_common(8)
        ]
