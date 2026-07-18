"""Repository contract and SQLAlchemy adapter for versioned agents."""

from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from gateway.app.models import Agent, AgentRevision


class AgentRepository(ABC):
    @abstractmethod
    def list_enabled(self) -> list[Agent]:
        raise NotImplementedError

    @abstractmethod
    def get(self, agent_id: str) -> Agent | None:
        raise NotImplementedError

    @abstractmethod
    def get_revision(
        self,
        agent_id: str,
        revision_id: UUID,
    ) -> AgentRevision | None:
        raise NotImplementedError


class SqlAlchemyAgentRepository(AgentRepository):
    """Load agents without leaking SQLAlchemy into conversation business logic."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_enabled(self) -> list[Agent]:
        return list(
            self._session.scalars(
                select(Agent)
                .options(joinedload(Agent.active_revision))
                .where(Agent.enabled.is_(True))
                .order_by(Agent.sort_order.asc(), Agent.id.asc())
            ).unique()
        )

    def get(self, agent_id: str) -> Agent | None:
        return self._session.scalar(
            select(Agent)
            .options(joinedload(Agent.active_revision))
            .where(Agent.id == agent_id)
        )

    def get_revision(self, agent_id: str, revision_id: UUID) -> AgentRevision | None:
        return self._session.scalar(
            select(AgentRevision)
            .options(joinedload(AgentRevision.agent))
            .where(
                AgentRevision.agent_id == agent_id,
                AgentRevision.id == revision_id,
            )
        )
