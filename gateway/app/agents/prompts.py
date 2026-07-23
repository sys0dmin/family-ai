"""Safety baseline combined with a versioned agent personality."""

from gateway.app.providers.schemas import ChatMessage, ProviderRole

CHILD_SAFETY_BASE_PROMPT = (
    "Ты — AI-помощник для Леры, ребёнка шести лет. "
    "Всегда отвечай на русском языке короткими и понятными фразами. "
    "Не притворяйся человеком и не называй себя единственным или лучшим другом. "
    "Не проси хранить секреты от родителей и не запрашивай персональные данные. "
    "Не давай опасных инструкций. Для риска, здоровья, незнакомцев и сложных "
    "жизненных ситуаций спокойно предложи обратиться к родителю. "
    "Не поощряй бесконечное общение: поддерживай отдых, движение и занятия вне экрана."
)


def build_agent_system_message(
    personality_prompt: str,
    safety_baseline: str = CHILD_SAFETY_BASE_PROMPT,
) -> ChatMessage:
    """Combine mandatory safety constraints with the published personality."""

    content = (
        f"{safety_baseline.strip()}\n\n"
        "Роль и методика выбранного персонажа:\n"
        f"{personality_prompt.strip()}"
    )
    return ChatMessage(role=ProviderRole.SYSTEM, content=content)
