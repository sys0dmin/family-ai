"""Backward-compatible composite provider interface.

New application code must depend on one narrow contract from ``contracts``.
"""

from gateway.app.providers.contracts import (
    ChatProvider,
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)


class AIProvider(
    ChatProvider,
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
):
    """Legacy facade combining all provider capabilities."""
