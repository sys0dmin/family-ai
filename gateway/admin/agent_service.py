"""Transactional operations for versioned agent administration."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from gateway.admin.agent_schemas import AgentUpdateRequest
from gateway.app.models import Agent, AgentRevision


class AdminAgentNotFoundError(LookupError):
    """Raised when an agent or one of its revisions does not exist."""


class AdminAgentService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_agents(self) -> list[Agent]:
        return list(
            self._session.scalars(
                select(Agent)
                .options(selectinload(Agent.revisions))
                .order_by(Agent.sort_order.asc(), Agent.id.asc())
            )
        )

    def update_agent(self, agent_id: str, payload: AgentUpdateRequest) -> Agent:
        agent = self._get_agent_for_update(agent_id)
        for field, value in payload.model_dump().items():
            if isinstance(value, str):
                value = value.strip()
            if field == "tts_voice" and not value:
                value = None
            setattr(agent, field, value)
        self._session.flush()
        return agent

    def create_revision(
        self,
        agent_id: str,
        system_prompt: str,
        created_by: str,
    ) -> AgentRevision:
        self._get_agent_for_update(agent_id)
        latest_version = self._session.scalar(
            select(func.max(AgentRevision.version)).where(
                AgentRevision.agent_id == agent_id
            )
        )
        revision = AgentRevision(
            id=uuid.uuid4(),
            agent_id=agent_id,
            version=(latest_version or 0) + 1,
            system_prompt=system_prompt.strip(),
            created_by=created_by,
        )
        self._session.add(revision)
        self._session.flush()
        return revision

    def publish_revision(self, agent_id: str, revision_id: uuid.UUID) -> Agent:
        agent = self._get_agent_for_update(agent_id)
        revision = self._session.scalar(
            select(AgentRevision).where(
                AgentRevision.id == revision_id,
                AgentRevision.agent_id == agent_id,
            )
        )
        if revision is None:
            raise AdminAgentNotFoundError(
                f"Agent revision does not exist: {agent_id}/{revision_id}"
            )
        agent.active_revision_id = revision.id
        self._session.flush()
        return agent

    def _get_agent_for_update(self, agent_id: str) -> Agent:
        agent = self._session.scalar(
            select(Agent).where(Agent.id == agent_id).with_for_update()
        )
        if agent is None:
            raise AdminAgentNotFoundError(f"Agent does not exist: {agent_id}")
        return agent
