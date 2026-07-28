"""Persistence contract for parent-confirmed long-term memory."""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.models import LongTermMemory, MemoryCategory


class MemoryRepository(Protocol):
    """Replaceable persistence boundary owned by the memory domain."""

    def list_for_profile(
        self,
        child_profile_id: uuid.UUID,
        *,
        category: MemoryCategory | None = None,
        limit: int | None = None,
    ) -> list[LongTermMemory]: ...

    def get_for_profile(
        self,
        memory_id: uuid.UUID,
        child_profile_id: uuid.UUID,
    ) -> LongTermMemory | None: ...

    def add(self, memory: LongTermMemory) -> None: ...

    def delete(self, memory: LongTermMemory) -> None: ...

    def flush(self) -> None: ...


class SqlAlchemyMemoryRepository:
    """PostgreSQL/SQLAlchemy adapter for the memory contract."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_profile(
        self,
        child_profile_id: uuid.UUID,
        *,
        category: MemoryCategory | None = None,
        limit: int | None = None,
    ) -> list[LongTermMemory]:
        statement = (
            select(LongTermMemory)
            .where(LongTermMemory.child_profile_id == child_profile_id)
            .order_by(LongTermMemory.updated_at.desc(), LongTermMemory.id.desc())
        )
        if category is not None:
            statement = statement.where(LongTermMemory.category == category.value)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement))

    def get_for_profile(
        self,
        memory_id: uuid.UUID,
        child_profile_id: uuid.UUID,
    ) -> LongTermMemory | None:
        return self._session.scalar(
            select(LongTermMemory).where(
                LongTermMemory.id == memory_id,
                LongTermMemory.child_profile_id == child_profile_id,
            )
        )

    def add(self, memory: LongTermMemory) -> None:
        self._session.add(memory)

    def delete(self, memory: LongTermMemory) -> None:
        self._session.delete(memory)

    def flush(self) -> None:
        self._session.flush()
