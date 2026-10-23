"""Streaming speech-to-text abstraction.

The voice pipeline depends on this protocol, not on AssemblyAI directly, so
tests can inject a fake and other providers can be added later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass(slots=True, frozen=True)
class SttTurn:
    """A transcription update; ``final`` marks the end of a user turn."""

    text: str
    final: bool
    turn_order: int = 0


@dataclass(slots=True, frozen=True)
class SttSpeechStarted:
    """The provider detected the start of user speech."""

    timestamp_ms: int = 0


@dataclass(slots=True, frozen=True)
class SttError:
    """A recoverable-but-fatal-for-this-session STT error."""

    message: str


SttEvent = SttTurn | SttSpeechStarted | SttError


@runtime_checkable
class StreamingSTT(Protocol):
    """Bidirectional streaming transcription session."""

    async def start(self) -> None:
        """Open the provider session."""
        ...

    async def send_audio(self, chunk: bytes) -> None:
        """Forward a chunk of encoded audio to the provider."""
        ...

    def events(self) -> AsyncIterator[SttEvent]:
        """Yield transcription events until the session ends."""
        ...

    async def aclose(self) -> None:
        """Terminate the session, flushing any pending final turn."""
        ...
