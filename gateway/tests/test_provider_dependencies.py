"""Tests for independently replaceable AI provider dependencies."""

from gateway.app import dependencies
from gateway.app.config import Settings
from gateway.app.providers.contracts import (
    ChatProvider,
    ImageUnderstandingProvider,
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)
from gateway.app.providers.openai_chat import OpenAIChatProvider
from gateway.app.providers.openai_stt import OpenAISpeechRecognitionProvider
from gateway.app.providers.openai_tts import OpenAISpeechSynthesisProvider
from gateway.app.providers.openai_vision import OpenAIImageUnderstandingProvider


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


def test_vision_factory_is_independent_and_can_reuse_chat_credentials(monkeypatch) -> None:
    settings = Settings(
        openai_api_key="chat-key",
        openai_base_url="https://api.groq.com/openai/v1",
        vision_provider="openai_compatible",
        vision_model="meta-llama/llama-4-scout-17b-16e-instruct",
    )
    monkeypatch.setattr(dependencies, "Settings", lambda: settings)

    vision = dependencies.get_image_understanding_provider()

    assert isinstance(vision, ImageUnderstandingProvider)
    assert isinstance(vision, OpenAIImageUnderstandingProvider)
    assert vision._model == "meta-llama/llama-4-scout-17b-16e-instruct"
    assert str(vision._client.base_url) == "https://api.groq.com/openai/v1/"
    assert vision._client.api_key == "chat-key"
