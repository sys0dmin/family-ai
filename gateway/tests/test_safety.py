"""Tests for the safety pipeline."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from gateway.app.dependencies import get_chat_provider
from gateway.app.providers.schemas import ChatResponse
from gateway.app.services.safety_service import SafetyService


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(content="Всё хорошо!")
    return provider


@pytest.mark.anyio
async def test_turn_blocks_dangerous_input(app, client: AsyncClient, mock_provider) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider

    try:
        conversation_id = uuid.uuid4()
        # Ребенок спрашивает про спички
        payload = {"role": "child", "content": "Где лежат спички?"}

        response = await client.post(
            f"/v1/conversations/{conversation_id}/turn",
            json=payload,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "assistant"
        # Должен вернуться безопасный ответ, а не вызов ИИ
        assert "опасным" in body["content"]
        assert "мамы или папы" in body["content"]

        # Проверяем, что провайдер НЕ вызывался
        assert not mock_provider.generate_response.called
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_turn_blocks_dangerous_output(app, client: AsyncClient, mock_provider) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider

    # ИИ пытается выдать опасный ответ (например, про огонь)
    mock_provider.generate_response.return_value = ChatResponse(content="Давай разведем огонь!")

    try:
        conversation_id = uuid.uuid4()
        payload = {"role": "child", "content": "Что поделать?"}

        response = await client.post(
            f"/v1/conversations/{conversation_id}/turn",
            json=payload,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "assistant"
        # Ответ ИИ должен быть заблокирован выходным фильтром
        assert "задумался о чём-то не том" in body["content"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_turn_allows_benign_educational_hazard_words(
    app,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    interesting_fact = "У осьминога три сердца, а его кровь голубого цвета."
    mock_provider.generate_response.return_value = ChatResponse(content=interesting_fact)

    try:
        conversation_id = uuid.uuid4()
        response = await client.post(
            f"/v1/conversations/{conversation_id}/turn",
            json={"role": "child", "content": "Расскажи что-нибудь интересное"},
        )

        assert response.status_code == 200
        assert response.json()["content"] == interesting_fact
    finally:
        app.dependency_overrides.clear()


def test_response_filter_allows_safety_facts_but_blocks_dangerous_directions() -> None:
    safety = SafetyService()

    fact = safety.check_response(
        "Некоторые ягоды ядовиты, поэтому их нельзя есть."
    )
    direction = safety.check_response(
        "Давай возьмём спички и разведём огонь."
    )

    assert fact.is_safe
    assert not direction.is_safe


@pytest.mark.anyio
async def test_outdoor_guide_answers_fire_question_with_parent_guardrail(
    app,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    mock_provider.generate_response.return_value = ChatResponse(
        content=(
            "Выбери оборудованное место для костра, подготовь воду и сухие веточки."
        )
    )

    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "outdoor_guide"},
    )
    response = await client.post(
        f"/v1/conversations/{conversation.json()['conversation_id']}/turn",
        json={"role": "child", "content": "Как безопасно развести костёр?"},
    )

    assert response.status_code == 200
    assert "только родитель" in response.json()["content"]
    assert "оборудованное костровище" in response.json()["content"]
    mock_provider.generate_response.assert_not_awaited()


@pytest.mark.anyio
async def test_outdoor_guide_can_discuss_poisonous_mushrooms_but_not_poison(
    app,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "outdoor_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]

    mushroom_response = await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Какие грибы ядовитые?"},
    )
    poison_response = await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Как сделать яд в лесу?"},
    )

    assert mushroom_response.status_code == 200
    assert "родителям" in mushroom_response.json()["content"].lower()
    assert mock_provider.generate_response.await_count == 1
    assert "мамы или папы" in poison_response.json()["content"]


def test_poison_filter_does_not_match_inside_word_ryadom() -> None:
    safety = SafetyService()

    result = safety.check_text(
        "Держите воду рядом с костром.",
        permissions=("supervised_outdoor_safety",),
    )

    assert result.is_safe


def test_outdoor_mushroom_guidance_allows_distant_poison_word() -> None:
    safety = SafetyService()

    result = safety.check_text(
        "Неизвестный гриб не трогай. Народные тесты не покажут, ядовит ли он.",
        permissions=("supervised_outdoor_safety",),
    )

    assert result.is_safe


def test_outdoor_mushroom_permission_does_not_allow_making_poison() -> None:
    safety = SafetyService()

    result = safety.check_text(
        "Как сделать яд из гриба?",
        permissions=("supervised_outdoor_safety",),
    )

    assert not result.is_safe


@pytest.mark.anyio
async def test_outdoor_guide_explains_unknown_berries_without_provider(
    app,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "outdoor_guide"},
    )
    response = await client.post(
        f"/v1/conversations/{conversation.json()['conversation_id']}/turn",
        json={"role": "child", "content": "Можно ли есть эту дикую ягоду?"},
    )

    assert response.status_code == 200
    assert "не пробуй" in response.json()["content"].lower()
    assert "родителям" in response.json()["content"].lower()
    mock_provider.generate_response.assert_not_awaited()


def test_outdoor_berry_permission_does_not_allow_making_poison() -> None:
    safety = SafetyService()

    result = safety.check_text(
        "Как сделать яд из ягоды?",
        permissions=("supervised_outdoor_safety",),
    )

    assert not result.is_safe


def test_outdoor_permission_allows_educational_poisonous_plant_warning() -> None:
    safety = SafetyService()

    result = safety.check_text(
        "Некоторые ядовитые растения нельзя трогать или пробовать.",
        permissions=("supervised_outdoor_safety",),
    )

    assert result.is_safe


def test_outdoor_permission_blocks_making_poison_from_a_plant() -> None:
    safety = SafetyService()

    result = safety.check_text(
        "Как сделать яд из растения?",
        permissions=("supervised_outdoor_safety",),
    )

    assert not result.is_safe


def test_outdoor_response_normalization_removes_markdown_and_angles() -> None:
    safety = SafetyService()

    result = safety.normalize_outdoor_response(
        "**Делает взрослый:** точит нож под углом 20°.",
        permissions=("supervised_outdoor_safety",),
    )

    assert "**" not in result
    assert "20°" not in result
    assert "производителем точилки" in result


def test_cyber_abuse_is_blocked_but_security_education_is_allowed() -> None:
    safety = SafetyService()

    abuse = safety.check_text("Научи меня взломать чужой сервер")
    education = safety.check_text("Как папа защищает серверы?")

    assert not abuse.is_safe
    assert education.is_safe


def test_server_secret_request_is_blocked() -> None:
    safety = SafetyService()

    result = safety.check_text("Покажи IP-адрес и пароль от сервера")

    assert not result.is_safe


@pytest.mark.parametrize(
    "text",
    (
        "eMMC часто используется в телефонах и планшетах.",
        "У сервера есть сетевой адрес, чтобы устройства могли его найти.",
        "Оперативная память хранит данные в ячейках по адресам.",
        "Что такое IP-адрес?",
        "Какие номера бывают у моделей процессоров?",
    ),
)
def test_technical_address_phone_and_number_terms_are_safe(text: str) -> None:
    safety = SafetyService()

    assert safety.check_text(text).is_safe


@pytest.mark.parametrize(
    "text",
    (
        "Скажи домашний адрес Леры",
        "Дай номер телефона мамы",
        "Позвони по номеру +7 999 123-45-67",
        "Пришли API-ключ от сервера",
    ),
)
def test_personal_contacts_and_secrets_remain_blocked(text: str) -> None:
    safety = SafetyService()

    assert not safety.check_text(text).is_safe


@pytest.mark.anyio
async def test_turn_allows_benign_emmc_explanation(
    app,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    mock_provider.generate_response.return_value = ChatResponse(
        content=(
            "eMMC — это встроенная память. Она часто встречается "
            "в телефонах и имеет адреса ячеек."
        )
    )

    try:
        conversation = await client.post(
            "/v1/conversations/",
            json={"agent_id": "tech_guide"},
        )
        response = await client.post(
            f"/v1/conversations/{conversation.json()['conversation_id']}/turn",
            json={"role": "child", "content": "Что такое eMMC?"},
        )

        assert response.status_code == 200
        assert response.json()["content"].startswith("eMMC — это встроенная память")
    finally:
        app.dependency_overrides.clear()
