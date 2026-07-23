"""Stateless orchestration used by the protected admin test studio."""

import time

from gateway.admin.studio_schemas import AgentTestResponse
from gateway.app.agents import build_agent_system_message
from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import (
    ChatMessage,
    ChatRequest,
    ProviderRole,
    ProviderTool,
    SpeechRequest,
    SpeechResponse,
)
from gateway.app.services.agent_service import AgentService
from gateway.app.services.safety_service import SafetyResult, SafetyService

SAFE_FALLBACK = (
    "Ой, я задумался о чём-то не том. "
    "Давай лучше поиграем или спросим у мамы?"
)


class StudioService:
    """Exercise the production prompt and safety pipeline without saving history."""

    def __init__(
        self,
        provider: AIProvider,
        agents: AgentService,
        safety: SafetyService,
    ) -> None:
        self._provider = provider
        self._agents = agents
        self._safety = safety

    async def test_agent(self, agent_id: str, prompt: str) -> AgentTestResponse:
        agent = self._agents.get_active(agent_id)
        input_safety = self._safety.check_text(prompt, agent.permissions)
        if not input_safety.is_safe:
            return self._blocked_without_model(input_safety)

        supervised_guidance = self._safety.get_supervised_outdoor_guidance(
            prompt,
            agent.permissions,
        )
        if supervised_guidance:
            return AgentTestResponse(
                raw_response="",
                final_response=supervised_guidance,
                safety_status="guardrail",
                safety_rule_id="input.supervised_guidance",
                safety_reason="Ответ сформирован проверенным правилом безопасности.",
                llm_duration_ms=None,
            )

        tools = (
            (ProviderTool.WEB_SEARCH,)
            if "web_search" in agent.tools
            else ()
        )
        request = ChatRequest(
            messages=[
                build_agent_system_message(
                    agent.system_prompt,
                    self._agents.get_safety_baseline(),
                ),
                ChatMessage(role=ProviderRole.USER, content=prompt),
            ],
            tools=tools,
        )
        started_at = time.perf_counter()
        response = await self._provider.generate_response(request)
        llm_duration_ms = round((time.perf_counter() - started_at) * 1000)
        raw_response = response.content.replace("\x00", "")
        final_response = self._safety.normalize_outdoor_response(
            raw_response,
            agent.permissions,
        )
        final_response = self._safety.apply_required_guardrails(
            final_response,
            agent.permissions,
        )
        output_safety = self._safety.check_response(
            final_response,
            agent.permissions,
        )
        if not output_safety.is_safe:
            return AgentTestResponse(
                raw_response=raw_response,
                final_response=SAFE_FALLBACK,
                safety_status="blocked",
                safety_rule_id=output_safety.rule_id,
                safety_reason=output_safety.reason,
                llm_duration_ms=llm_duration_ms,
            )
        return AgentTestResponse(
            raw_response=raw_response,
            final_response=final_response,
            safety_status="passed",
            llm_duration_ms=llm_duration_ms,
        )

    async def synthesize(self, text: str, voice: str) -> SpeechResponse:
        return await self._provider.synthesize_speech(
            SpeechRequest(text=text, voice=voice)
        )

    @staticmethod
    def _blocked_without_model(result: SafetyResult) -> AgentTestResponse:
        return AgentTestResponse(
            raw_response="",
            final_response=result.suggested_response or SAFE_FALLBACK,
            safety_status="blocked",
            safety_rule_id=result.rule_id,
            safety_reason=result.reason,
            llm_duration_ms=None,
        )
