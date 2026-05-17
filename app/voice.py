"""Voice stuff (STT and TTS).

For now these are stubs so that the API surface is defined without committing to
any specific provider or model. Actual audio handling can be added in a later
milestone.
"""

from __future__ import annotations

from typing import Protocol


class SpeechToText(Protocol):
    def transcribe(self, audio_bytes: bytes) -> str:
        """Turn audio into text."""

        ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> bytes:
        """Turn text into audio."""

        ...


class StubSpeechToText:
    """Base STT interface.

    Currently this does not perform real transcription; it only raises a
    NotImplementedError to signal that voice is not yet configured.
    """

    def transcribe(self, audio_bytes: bytes) -> str:  # noqa: ARG002
        raise NotImplementedError("Speech-to-text is not configured for this prototype.")


class StubTextToSpeech:
    """Base TTS interface.

    Currently this does not perform real synthesis; it only raises a
    NotImplementedError to signal that voice is not yet configured.
    """

    def synthesize(self, text: str) -> bytes:  # noqa: ARG002
        raise NotImplementedError("Text-to-speech is not configured for this prototype.")


stt: SpeechToText = StubSpeechToText()
tts: TextToSpeech = StubTextToSpeech()

