"""Agent selection and published configuration business rules."""

from uuid import UUID

from gateway.app.agents import ActiveAgent, AgentManifest, AgentRepository
from gateway.app.models import Agent, AgentRevision


class AgentNotFoundError(LookupError):
    """Raised when an agent is missing or unavailable to the child."""


class AgentConfigurationError(RuntimeError):
    """Raised when an enabled agent has no valid published revision."""


class AgentService:
    def __init__(self, repository: AgentRepository) -> None:
        self._repository = repository

    def list_available(self) -> list[AgentManifest]:
        return [self._to_manifest(agent) for agent in self._repository.list_enabled()]

    def get_safety_baseline(self) -> str:
        return self._repository.get_safety_baseline()

    def get_active(self, agent_id: str, *, require_enabled: bool = True) -> ActiveAgent:
        agent = self._repository.get(agent_id)
        if agent is None or (require_enabled and not agent.enabled):
            raise AgentNotFoundError(f"Agent is unavailable: {agent_id}")
        revision = agent.active_revision
        if revision is None or not revision.system_prompt.strip():
            raise AgentConfigurationError(f"Agent has no active revision: {agent_id}")
        return self._to_active(agent, revision)

    def get_revision(self, agent_id: str, revision_id: UUID) -> ActiveAgent:
        revision = self._repository.get_revision(agent_id, revision_id)
        if revision is None:
            raise AgentConfigurationError(
                f"Agent revision is unavailable: {agent_id}/{revision_id}"
            )
        return self._to_active(revision.agent, revision)

    @staticmethod
    def _to_manifest(agent: Agent) -> AgentManifest:
        return AgentManifest(
            id=agent.id,
            display_name=agent.display_name,
            description=agent.description,
            icon=agent.icon,
            color=agent.color,
            greeting=agent.greeting,
            tts_voice=agent.tts_voice,
            tools=tuple(agent.tools or ()),
            permissions=tuple(agent.permissions or ()),
        )

    @classmethod
    def _to_active(cls, agent: Agent, revision: AgentRevision) -> ActiveAgent:
        return ActiveAgent(
            **cls._to_manifest(agent).__dict__,
            revision_id=str(revision.id),
            version=revision.version,
            system_prompt=revision.system_prompt,
        )
