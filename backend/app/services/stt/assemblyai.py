"""AssemblyAI streaming (v3 WebSocket) speech-to-text."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from assemblyai.streaming.v3 import (
    AsyncRealTimeTranscriber,
    BeginEvent,
    Encoding,
    RealTimeError,
    RealTimeEvents,
    RealTimeParameters,
    RealTimeTranscriberOptions,
    SpeechStartedEvent,
    TerminationEvent,
    TurnEvent,
)

from app.core.config import AssemblyAISettings
from app.services.stt.base import SttError, SttEvent, SttSpeechStarted, SttTurn

logger = logging.getLogger(__name__)

_STOP = object()


class AssemblyAIStreamingSTT:
    """`StreamingSTT` backed by AssemblyAI's async v3 transcriber.

    Event handlers run on the SDK's read task synchronously, so they only push
    onto an unbounded queue; all awaiting happens in :meth:`events`.
    """

    def __init__(
        self,
        config: AssemblyAISettings,
        *,
        sample_rate: int | None = None,
    ) -> None:
        if not config.is_configured:
            raise ValueError("ASSEMBLYAI_API_KEY is not configured")
        self._config = config
        self._sample_rate = sample_rate or config.sample_rate
        self._queue: asyncio.Queue[SttEvent | object] = asyncio.Queue()
        self._client = AsyncRealTimeTranscriber(
            RealTimeTranscriberOptions(terminate_timeout=config.terminator_timeout),
            api_key=config.api_key.get_secret_value() if config.api_key else None,
        )
        self._started = False
        self._closed = False

    # -- handlers ---------------------------------------------------------
    def _register_handlers(self) -> None:
        self._client.on(RealTimeEvents.Begin, self._on_begin)
        self._client.on(RealTimeEvents.Turn, self._on_turn)
        self._client.on(RealTimeEvents.SpeechStarted, self._on_speech_started)
        self._client.on(RealTimeEvents.Error, self._on_error)
        self._client.on(RealTimeEvents.Termination, self._on_termination)

    def _emit(self, event: SttEvent) -> None:
        if not self._closed:
            self._queue.put_nowait(event)

    def _on_begin(self, _client: AsyncRealTimeTranscriber, event: BeginEvent) -> None:
        logger.debug("AssemblyAI session started: %s", event.id)

    def _on_turn(self, _client: AsyncRealTimeTranscriber, event: TurnEvent) -> None:
        if not event.transcript:
            return
        self._emit(
            SttTurn(
                text=event.transcript,
                final=event.end_of_turn,
                turn_order=event.turn_order,
            )
        )

    def _on_speech_started(
        self, _client: AsyncRealTimeTranscriber, event: SpeechStartedEvent
    ) -> None:
        self._emit(SttSpeechStarted(timestamp_ms=event.timestamp))

    def _on_error(self, _client: AsyncRealTimeTranscriber, error: RealTimeError) -> None:
        logger.warning("AssemblyAI error: %s", error)
        self._emit(SttError(message=str(error)))

    def _on_termination(
        self, _client: AsyncRealTimeTranscriber, _event: TerminationEvent
    ) -> None:
        self._closed = True
        self._queue.put_nowait(_STOP)

    # -- StreamingSTT -----------------------------------------------------
    async def start(self) -> None:
        self._register_handlers()
        params = RealTimeParameters(
            speech_model=self._config.speech_model,
            encoding=Encoding(self._config.encoding),
            sample_rate=self._sample_rate,
            min_turn_silence=self._config.min_turn_silence,
            max_turn_silence=self._config.max_turn_silence,
            end_of_turn_confidence_threshold=(
                self._config.end_of_turn_confidence_threshold
            ),
        )
        await self._client.connect(params)
        self._started = True
        logger.info(
            "STT session open (model=%s, %s Hz, %s)",
            self._config.speech_model,
            self._sample_rate,
            self._config.encoding,
        )

    async def send_audio(self, chunk: bytes) -> None:
        if not self._started or self._closed:
            return
        await self._client.stream(chunk)

    async def events(self) -> AsyncIterator[SttEvent]:
        while True:
            item = await self._queue.get()
            if item is _STOP:
                return
            yield item  # type: ignore[misc]

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._client.disconnect(terminate=True)
        except Exception:  # pragma: no cover - best-effort teardown
            logger.debug("STT teardown raised", exc_info=True)
        finally:
            self._queue.put_nowait(_STOP)


__all__ = ["AssemblyAIStreamingSTT"]
