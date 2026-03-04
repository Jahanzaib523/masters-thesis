"""
Voice service interfaces for future speech-to-text (STT) and text-to-speech (TTS) integration.

For now these are stubs so that the API surface is defined without committing to
any specific provider or model. Actual audio handling can be added in a later
milestone.
"""

from __future__ import annotations

from typing import Protocol


class SpeechToText(Protocol):
    def transcribe(self, audio_bytes: bytes) -> str:
        """Convert raw audio bytes into text."""

        ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> bytes:
        """Convert text into raw audio bytes."""

        ...


class StubSpeechToText:
    """Placeholder STT implementation.

    Currently this does not perform real transcription; it only raises a
    NotImplementedError to signal that voice is not yet configured.
    """

    def transcribe(self, audio_bytes: bytes) -> str:  # noqa: ARG002
        raise NotImplementedError("Speech-to-text is not configured for this prototype.")


class StubTextToSpeech:
    """Placeholder TTS implementation.

    Currently this does not perform real synthesis; it only raises a
    NotImplementedError to signal that voice is not yet configured.
    """

    def synthesize(self, text: str) -> bytes:  # noqa: ARG002
        raise NotImplementedError("Text-to-speech is not configured for this prototype.")


stt: SpeechToText = StubSpeechToText()
tts: TextToSpeech = StubTextToSpeech()

