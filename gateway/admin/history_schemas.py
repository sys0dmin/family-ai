"""Read models exposed by the protected history API."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from gateway.app.models import FeedbackReason


class HistoryFeedbackResponse(BaseModel):
    id: uuid.UUID
    reason: FeedbackReason
    note: str | None


class HistoryMessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    feedback: HistoryFeedbackResponse | None = None


class ConversationHistoryItem(BaseModel):
    conversation_id: uuid.UUID
    started_at: datetime
    last_message_at: datetime
    message_count: int
    messages: list[HistoryMessageResponse]


class ConversationHistoryResponse(BaseModel):
    items: list[ConversationHistoryItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class DailyActivityPoint(BaseModel):
    day: date
    child_messages: int
    assistant_messages: int


class FrequentQuestion(BaseModel):
    text: str
    count: int


class HistorySummaryResponse(BaseModel):
    days: int
    total_messages: int
    child_messages: int
    assistant_messages: int
    conversations: int
    active_days: int
    average_response_seconds: float | None
    daily_activity: list[DailyActivityPoint]
    frequent_questions: list[FrequentQuestion]
