"""Tests for independently replaceable AI provider dependencies."""

from gateway.app import dependencies
from gateway.app.config import Settings
from gateway.app.providers.contracts import (
    ChatProvider,
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)
from gateway.app.providers.openai_chat import OpenAIChatProvider
from gateway.app.providers.openai_stt import OpenAISpeechRecognitionProvider
from gateway.app.providers.openai_tts import OpenAISpeechSynthesisProvider


def test_provider_factories_build_three_narrow_adapters(monkeypatch) -> None:
    settings = Settings(
        openai_api_key="chat-key",
        openai_base_url="https://chat.example/v1",
        speech_api_key="shared-speech-key",
        speech_base_url="https://speech.example/v1",
        stt_api_key="stt-key",
        stt_base_url="https://stt.example/v1",
        tts_api_key="tts-key",
        tts_base_url="https://tts.example/v1",
    )
    monkeypatch.setattr(dependencies, "Settings", lambda: settings)

    chat = dependencies.get_chat_provider()
    recognition = dependencies.get_speech_recognition_provider()
    synthesis = dependencies.get_speech_synthesis_provider()

    assert isinstance(chat, ChatProvider)
    assert isinstance(chat, OpenAIChatProvider)
    assert isinstance(recognition, SpeechRecognitionProvider)
    assert isinstance(recognition, OpenAISpeechRecognitionProvider)
    assert isinstance(synthesis, SpeechSynthesisProvider)
    assert isinstance(synthesis, OpenAISpeechSynthesisProvider)
    assert str(chat._client.base_url) == "https://chat.example/v1/"
    assert str(recognition._client.base_url) == "https://stt.example/v1/"
    assert str(synthesis._client.base_url) == "https://tts.example/v1/"
    assert recognition._client.api_key == "stt-key"
    assert synthesis._client.api_key == "tts-key"


def test_speech_factories_preserve_shared_configuration_fallback(monkeypatch) -> None:
    settings = Settings(
        openai_api_key="chat-key",
        speech_api_key="shared-speech-key",
        speech_base_url="https://speech.example/v1",
    )
    monkeypatch.setattr(dependencies, "Settings", lambda: settings)

    recognition = dependencies.get_speech_recognition_provider()
    synthesis = dependencies.get_speech_synthesis_provider()

    assert str(recognition._client.base_url) == "https://speech.example/v1/"
    assert str(synthesis._client.base_url) == "https://speech.example/v1/"
    assert recognition._client.api_key == "shared-speech-key"
    assert synthesis._client.api_key == "shared-speech-key"
