"""Server-controlled phrases with known ground truth for STT calibration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationPromptDefinition:
    id: str
    expected_text: str
    kind: str
    spoken_instruction: str
    icon: str


CALIBRATION_PROMPTS = (
    CalibrationPromptDefinition(
        "speech_01",
        "Привет, меня зовут Лера.",
        "speech",
        "Повтори за мной: Привет, меня зовут Лера.",
        "👋",
    ),
    CalibrationPromptDefinition(
        "speech_02",
        "Мурка взяла бинокль и пошла в лес.",
        "speech",
        "Повтори за мной: Мурка взяла бинокль и пошла в лес.",
        "🐱",
    ),
    CalibrationPromptDefinition(
        "speech_03",
        "Байтик рассказывает, как работает сервер.",
        "speech",
        "Повтори за мной: Байтик рассказывает, как работает сервер.",
        "🦝",
    ),
    CalibrationPromptDefinition(
        "speech_04",
        "Учитель-друг объясняет трудный вопрос.",
        "speech",
        "Повтори за мной: Учитель-друг объясняет трудный вопрос.",
        "🐻",
    ),
    CalibrationPromptDefinition(
        "speech_05",
        "Почему облака плывут по небу?",
        "speech",
        "Повтори за мной: Почему облака плывут по небу?",
        "☁️",
    ),
    CalibrationPromptDefinition(
        "speech_06",
        "У компьютера есть процессор и память.",
        "speech",
        "Повтори за мной: У компьютера есть процессор и память.",
        "💻",
    ),
    CalibrationPromptDefinition(
        "speech_07",
        "Я хочу узнать про грибы и ягоды.",
        "speech",
        "Повтори за мной: Я хочу узнать про грибы и ягоды.",
        "🍄",
    ),
    CalibrationPromptDefinition(
        "speech_08",
        "Красная машина едет по мокрой дороге.",
        "speech",
        "Повтори за мной: Красная машина едет по мокрой дороге.",
        "🚗",
    ),
    CalibrationPromptDefinition(
        "speech_09",
        "В аквариуме плавают маленькие рыбки.",
        "speech",
        "Повтори за мной: В аквариуме плавают маленькие рыбки.",
        "🐠",
    ),
    CalibrationPromptDefinition(
        "speech_10",
        "Семь весёлых енотов считают звёзды.",
        "speech",
        "Повтори за мной: Семь весёлых енотов считают звёзды.",
        "⭐",
    ),
    CalibrationPromptDefinition(
        "speech_11",
        "Можно ли поставить палатку у реки?",
        "speech",
        "Повтори за мной: Можно ли поставить палатку у реки?",
        "⛺",
    ),
    CalibrationPromptDefinition(
        "speech_12",
        "Расскажи сказку про доброго дракона.",
        "speech",
        "Повтори за мной: Расскажи сказку про доброго дракона.",
        "🐉",
    ),
    CalibrationPromptDefinition(
        "silence_01",
        "",
        "silence",
        "А теперь ничего не говори. Три секунды слушаем тишину.",
        "🤫",
    ),
    CalibrationPromptDefinition(
        "silence_02",
        "",
        "silence",
        "Ещё раз помолчим и послушаем комнату.",
        "👂",
    ),
    CalibrationPromptDefinition(
        "silence_03",
        "",
        "silence",
        "Последняя тихая проверка. Ничего не говори.",
        "🌙",
    ),
)
