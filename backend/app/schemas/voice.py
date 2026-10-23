"""WebSocket contract for the voice channel.

Client -> server control messages are JSON text frames. Audio from the client
travels as raw binary frames (PCM16, mono, ``session.start.sample_rate``).

Server -> client uses two frame kinds:

* **Text frames** carry AG-UI events. Standard AG-UI event types are emitted
  as-is; voice-specific data rides on ``CUSTOM`` events with the names declared
  in :class:`VoiceCustomEvent`.
* **Binary frames** carry assistant audio in the format announced by
  ``voice.audio.start`` (PCM16, mono, ``VoiceCustomEvent`` payload sample rate).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator
from pydantic.alias_generators import to_camel


class VoiceModel(BaseModel):
    """Base for every model on the voice wire format.

    AG-UI serialises with camelCase aliases, so our own payloads must do the
    same: the browser reads ``value.sampleRate``. Serialising ``sample_rate``
    means the client sees ``undefined`` and plays PCM at the wrong speed.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class VoiceCustomEvent(str, Enum):
    """Names of the ``CUSTOM`` AG-UI events emitted by the voice channel."""

    TRANSCRIPT = "voice.transcript"
    """User speech transcription. Emitted on every partial and final turn."""

    AUDIO_START = "voice.audio.start"
    """Announces the format of the binary frames that follow."""

    AUDIO_END = "voice.audio.end"
    """The assistant finished speaking; no more audio frames for this turn."""

    INTERRUPTED = "voice.interrupted"
    """Playback was cancelled (barge-in or explicit interrupt)."""

    LISTENING = "voice.listening"
    """Turn state change: the client may (``active=true``) or must not send audio."""

    SESSION_END = "voice.session.end"
    """The server closed the session; ``reason`` explains why."""


class _ClientMessage(VoiceModel):
    pass


class SessionStart(_ClientMessage):
    type: Literal["session.start"] = "session.start"
    sample_rate: int | None = Field(default=None, ge=8000, le=48000)
    """Sample rate of the client's microphone PCM frames."""


class ChatText(_ClientMessage):
    type: Literal["text"] = "text"
    text: str

    @field_validator("text")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty")
        return value


class Interrupt(_ClientMessage):
    type: Literal["response.interrupt"] = "response.interrupt"


class SessionStop(_ClientMessage):
    type: Literal["session.stop"] = "session.stop"


ClientMessage = Annotated[
    Union[SessionStart, ChatText, Interrupt, SessionStop],
    Field(discriminator="type"),
]

CLIENT_MESSAGE_ADAPTER: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


class TranscriptPayload(VoiceModel):
    """Payload of :attr:`VoiceCustomEvent.TRANSCRIPT`."""

    text: str
    """Transcript of the provider's current turn only."""

    final: bool
    turn_order: int = 0

    utterance: str = ""
    """Everything the user has said since the assistant last replied.

    The provider ends a turn at the first pause, so ``text`` may be a fragment.
    This field accumulates consecutive fragments so the client can keep the
    full sentence on screen instead of replacing it every few words.
    """


class AudioStartPayload(VoiceModel):
    """Payload of :attr:`VoiceCustomEvent.AUDIO_START`."""

    format: str = "pcm_s16le"
    sample_rate: int
    channels: int = 1


class ListeningPayload(VoiceModel):
    """Payload of :attr:`VoiceCustomEvent.LISTENING`."""

    active: bool


class SessionEndPayload(VoiceModel):
    """Payload of :attr:`VoiceCustomEvent.SESSION_END`."""

    reason: str


def parse_client_message(raw: str | bytes) -> ClientMessage:
    """Parse and validate an inbound client text frame."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return CLIENT_MESSAGE_ADAPTER.validate_json(raw)


__all__ = [
    "CLIENT_MESSAGE_ADAPTER",
    "AudioStartPayload",
    "ChatText",
    "ClientMessage",
    "Interrupt",
    "ListeningPayload",
    "SessionEndPayload",
    "SessionStart",
    "SessionStop",
    "TranscriptPayload",
    "VoiceCustomEvent",
    "parse_client_message",
]
