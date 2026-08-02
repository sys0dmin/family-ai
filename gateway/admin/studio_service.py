"""Stateless orchestration used by the protected admin test studio."""

import time

from gateway.admin.studio_schemas import AgentTestResponse
from gateway.app.agents import build_agent_system_message
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.memory import MemoryService
from gateway.app.providers.contracts import (
    ChatProvider,
    ImageUnderstandingProvider,
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)
from gateway.app.providers.schemas import (
    ChatMessage,
    ChatRequest,
    ImageUnderstandingRequest,
    ProviderRole,
    ProviderTool,
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)
from gateway.app.safety.contracts import PolicyAction, PolicyOutcome
from gateway.app.services.agent_service import AgentService
from gateway.app.services.safety_service import SafetyService

SAFE_FALLBACK = (
    "Ой, я задумался о чём-то не том. "
    "Давай лучше поиграем или спросим у мамы?"
)


class StudioCapabilityUnavailableError(RuntimeError):
    """Raised when an optional stateless studio provider is not configured."""


class StudioService:
    """Exercise the production prompt and safety pipeline without saving history."""

    def __init__(
        self,
        chat_provider: ChatProvider,
        synthesis_provider: SpeechSynthesisProvider,
        agents: AgentService,
        safety: SafetyService,
        memory: MemoryService | None = None,
        recognition_provider: SpeechRecognitionProvider | None = None,
        image_provider: ImageUnderstandingProvider | None = None,
    ) -> None:
        self._chat_provider = chat_provider
        self._synthesis_provider = synthesis_provider
        self._agents = agents
        self._safety = safety
        self._memory = memory
        self._recognition_provider = recognition_provider
        self._image_provider = image_provider

    async def test_agent(self, agent_id: str, prompt: str) -> AgentTestResponse:
        agent = self._agents.get_active(agent_id)
        input_outcome = self._safety.evaluate_input(
            prompt,
            agent.permissions,
        )
        if input_outcome.action is PolicyAction.BLOCK:
            return self._blocked_without_model(input_outcome)
        if input_outcome.action is PolicyAction.TRANSFORM:
            decision = input_outcome.primary_decision
            return AgentTestResponse(
                raw_response="",
                final_response=input_outcome.text,
                safety_status="guardrail",
                safety_rule_id=decision.rule_id,
                safety_reason=decision.reason,
                llm_duration_ms=None,
            )

        tool_outcome = (
            self._safety.evaluate_tool("web_search", agent.tools)
            if "web_search" in agent.tools
            else None
        )
        tools = (
            (ProviderTool.WEB_SEARCH,)
            if tool_outcome and tool_outcome.action is PolicyAction.ALLOW
            else ()
        )
        messages = [
            build_agent_system_message(
                agent.system_prompt,
                self._agents.get_safety_baseline(),
            )
        ]
        if self._memory:
            memory_context = self._memory.build_prompt_context(LERA_PROFILE_ID)
            if memory_context:
                messages.append(
                    ChatMessage(
                        role=ProviderRole.SYSTEM,
                        content=memory_context,
                    )
                )
        messages.append(ChatMessage(role=ProviderRole.USER, content=prompt))
        request = ChatRequest(messages=messages, tools=tools)
        started_at = time.perf_counter()
        response = await self._chat_provider.generate_response(request)
        llm_duration_ms = round((time.perf_counter() - started_at) * 1000)
        raw_response = response.content.replace("\x00", "")
        output_outcome = self._safety.evaluate_output(
            raw_response,
            agent.permissions,
        )
        final_response = output_outcome.text
        if output_outcome.action is PolicyAction.BLOCK:
            decision = output_outcome.primary_decision
            return AgentTestResponse(
                raw_response=raw_response,
                final_response=output_outcome.safe_response or SAFE_FALLBACK,
                safety_status="blocked",
                safety_rule_id=decision.rule_id,
                safety_reason=decision.reason,
                llm_duration_ms=llm_duration_ms,
            )
        decision = output_outcome.primary_decision
        return AgentTestResponse(
            raw_response=raw_response,
            final_response=final_response,
            safety_status=(
                "guardrail"
                if output_outcome.action is PolicyAction.TRANSFORM
                else "passed"
            ),
            safety_rule_id=(
                decision.rule_id
                if output_outcome.action is PolicyAction.TRANSFORM
                else None
            ),
            safety_reason=(
                decision.reason
                if output_outcome.action is PolicyAction.TRANSFORM
                else None
            ),
            llm_duration_ms=llm_duration_ms,
        )

    async def synthesize(self, text: str, voice: str) -> SpeechResponse:
        return await self._synthesis_provider.synthesize_speech(
            SpeechRequest(text=text, voice=voice)
        )

    async def transcribe(
        self,
        audio_content: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> TranscriptionResponse:
        if self._recognition_provider is None:
            raise StudioCapabilityUnavailableError("Speech recognition is unavailable")
        return await self._recognition_provider.transcribe_audio(
            TranscriptionRequest(
                audio_content=audio_content,
                filename=filename,
                content_type=content_type,
            )
        )

    async def inspect_image(
        self,
        image_content: bytes,
        *,
        content_type: str,
        question: str,
    ) -> str:
        if self._image_provider is None:
            raise StudioCapabilityUnavailableError("Image understanding is unavailable")
        response = await self._image_provider.describe_image(
            ImageUnderstandingRequest(
                image_content=image_content,
                content_type=content_type,
                question=question,
            )
        )
        description = response.description.replace("\x00", "").strip()
        if not description:
            raise StudioCapabilityUnavailableError("Image understanding returned no result")
        return description

    @staticmethod
    def _blocked_without_model(result: PolicyOutcome) -> AgentTestResponse:
        decision = result.primary_decision
        return AgentTestResponse(
            raw_response="",
            final_response=result.safe_response or SAFE_FALLBACK,
            safety_status="blocked",
            safety_rule_id=decision.rule_id,
            safety_reason=decision.reason,
            llm_duration_ms=None,
        )
