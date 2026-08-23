"""Provider-neutral prompt assembly for one safe conversation turn."""

from dataclasses import dataclass
from uuid import UUID

from gateway.app.agents import ActiveAgent, build_agent_system_message
from gateway.app.models import Message, MessageRole
from gateway.app.providers.schemas import ChatMessage, ChatRequest, ProviderRole, ProviderTool
from gateway.app.safety.contracts import PolicyAction
from gateway.app.services.safety_service import SafetyService

CONTINUING_CONVERSATION_CONTEXT = (
    "Это продолжение уже начатого разговора с Лерой. Не здоровайся заново, не "
    "представляйся повторно и не начинай беседу с чистого листа. Учитывай последние "
    "реплики. Если Лера исправляет твою ошибку, коротко признай поправку, поблагодари "
    "и продолжай с учётом верного факта."
)
UNVERIFIED_MUSIC_TEXT_CONTEXT = (
    "В этом текстовом ходе инструмент распознавания музыки не возвращал результата. "
    "Если доступен веб-поиск, обязательно используй его для проверки фрагмента перед "
    "ответом. Не выдавай догадку языковой модели за распознанную песню и не выдумывай "
    "правдоподобные названия, исполнителей или источники. Назови ровно одну песню "
    "только при высокой уверенности, что все данные совпадают; иначе честно попроси "
    "ещё одну строку или голосовой напев."
)
SUPERVISED_OUTDOOR_CONTEXT = (
    "Этот агент может обсуждать походную безопасность, но это не разрешение "
    "ребёнку выполнять опасную часть. Всегда давай полезный ответ и явно разделяй "
    "роли. Ребёнок не берёт, не достаёт и не держит спички, нож, точило, крючок или "
    "горячую посуду — это делает взрослый. Не давай ребёнку углы заточки и не учи его "
    "проверять остроту. Отвечай обычным текстом без Markdown."
)


@dataclass(frozen=True)
class ConversationPromptContext:
    """All bounded inputs required to assemble a provider request."""

    active_agent: ActiveAgent
    safety_baseline: str
    history: tuple[Message, ...]
    memory_context: str | None = None
    runtime_context: str | None = None
    activity_context: str | None = None


def build_conversation_request(
    context: ConversationPromptContext,
    safety: SafetyService | None,
    request_id: UUID | None,
) -> ChatRequest:
    """Build one bounded chat request without persistence or provider calls."""

    agent = context.active_agent
    messages = [
        build_agent_system_message(agent.system_prompt, context.safety_baseline)
    ]
    for optional_context in (
        context.memory_context,
        context.runtime_context,
        context.activity_context,
    ):
        if optional_context:
            messages.append(
                ChatMessage(role=ProviderRole.SYSTEM, content=optional_context)
            )
    if "music_recognition" in agent.tools:
        messages.append(
            ChatMessage(
                role=ProviderRole.SYSTEM,
                content=UNVERIFIED_MUSIC_TEXT_CONTEXT,
            )
        )
    if _outdoor_guidance_allowed(agent, safety):
        messages.append(
            ChatMessage(
                role=ProviderRole.SYSTEM,
                content=SUPERVISED_OUTDOOR_CONTEXT,
            )
        )
    if any(message.role == MessageRole.ASSISTANT for message in context.history):
        messages.append(
            ChatMessage(
                role=ProviderRole.SYSTEM,
                content=CONTINUING_CONVERSATION_CONTEXT,
            )
        )
    for message in context.history[-10:]:
        role = (
            ProviderRole.USER
            if message.role == MessageRole.CHILD
            else ProviderRole.ASSISTANT
        )
        messages.append(ChatMessage(role=role, content=message.content))

    tools = (
        (ProviderTool.WEB_SEARCH,)
        if _web_search_allowed(agent, safety)
        else ()
    )
    return ChatRequest(messages=messages, tools=tools, request_id=request_id)


def _outdoor_guidance_allowed(
    agent: ActiveAgent,
    safety: SafetyService | None,
) -> bool:
    if safety is None or "supervised_outdoor_safety" not in agent.permissions:
        return False
    outcome = safety.evaluate_permission(
        "supervised_outdoor_safety",
        agent.permissions,
    )
    return outcome.action is PolicyAction.ALLOW


def _web_search_allowed(
    agent: ActiveAgent,
    safety: SafetyService | None,
) -> bool:
    if safety is None or "web_search" not in agent.tools:
        return False
    outcome = safety.evaluate_tool("web_search", agent.tools)
    return outcome.action is PolicyAction.ALLOW
