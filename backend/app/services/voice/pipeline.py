"""Voice-session orchestration.

Pipelines one WebSocket connection: client audio -> STT -> agent -> TTS ->
client audio, while translating AG-UI events to the client and handling
barge-in.

Concurrency model, per session:

* ``_receive_loop``  reads client frames and forwards audio to the STT.
* ``_stt_loop``      consumes transcription events and starts agent turns.
* ``_response_task`` one per agent turn; streams text into a TTS context while
  ``_audio_task`` drains the synthesised audio back to the client.

Everything that writes to the socket goes through ``_send_*`` helpers guarded
by ``_send_lock``; a cancelled turn never interleaves frames with the next one.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Callable
from typing import Any

from ag_ui.core import (
    CustomEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from pydantic_ai import Agent, AgentRunResultEvent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.agents.deps import AgentDeps
from app.core.config import Settings
from app.schemas.voice import (
    AudioStartPayload,
    ChatText,
    Interrupt,
    ListeningPayload,
    SessionEndPayload,
    SessionStart,
    SessionStop,
    TranscriptPayload,
    VoiceCustomEvent,
    parse_client_message,
)
from app.services.stt.base import (
    SttError,
    SttEvent,
    SttSpeechStarted,
    SttTurn,
    StreamingSTT,
)
from app.services.tts.base import StreamingTTS
from app.sessions.store import SessionStore

logger = logging.getLogger(__name__)

# Split the LLM stream into TTS-sized pieces at natural boundaries.
_BOUNDARY_RE = re.compile(r"[.!?…][\"')\]]*\s+|\n+")
_MAX_TTS_BUFFER = 220


def _split_for_tts(buffer: str, *, force: bool) -> tuple[str, str]:
    """Return ``(ready, remaining)`` where ``ready`` can be synthesised now."""
    matches = list(_BOUNDARY_RE.finditer(buffer))
    if matches:
        cut = matches[-1].end()
        return buffer[:cut], buffer[cut:]
    if len(buffer) >= _MAX_TTS_BUFFER:
        cut = buffer.rfind(" ", 0, _MAX_TTS_BUFFER)
        cut = len(buffer) if cut == -1 else cut + 1
        return buffer[:cut], buffer[cut:]
    if force and buffer.strip():
        return buffer, ""
    return "", buffer


def _dump(event: Any) -> str:
    return event.model_dump_json(by_alias=True)


class VoiceSession:
    """Drives one voice conversation over a WebSocket."""

    def __init__(
        self,
        *,
        websocket: WebSocket,
        agent: Agent[AgentDeps, str],
        store: SessionStore,
        settings: Settings,
        thread_id: str,
        stt: StreamingSTT,
        tts_factory: Callable[[], StreamingTTS],
    ) -> None:
        self._ws = websocket
        self._agent = agent
        self._store = store
        self._settings = settings
        self._thread_id = thread_id
        self._stt = stt
        self._tts_factory = tts_factory

        self._send_lock = asyncio.Lock()
        self._response_task: asyncio.Task[None] | None = None
        self._audio_task: asyncio.Task[None] | None = None
        self._stt_started = False
        self._stt_start_lock = asyncio.Lock()
        self._speaking = False
        self._closed = False
        # Transcript fragments collected since the assistant last replied, plus
        # the debounce task deciding when the user is actually done speaking.
        self._pending_text = ""
        self._pending_task: asyncio.Task[None] | None = None

    # -- socket helpers ---------------------------------------------------
    async def _send_json(self, payload: str) -> None:
        if self._closed:
            return
        async with self._send_lock:
            try:
                await self._ws.send_text(payload)
            except (WebSocketDisconnect, RuntimeError):
                self._closed = True

    async def _send_bytes(self, data: bytes) -> None:
        if self._closed:
            return
        async with self._send_lock:
            try:
                await self._ws.send_bytes(data)
            except (WebSocketDisconnect, RuntimeError):
                self._closed = True

    async def _send_event(self, event: Any) -> None:
        await self._send_json(_dump(event))

    async def _send_custom(self, name: VoiceCustomEvent, value: Any) -> None:
        if hasattr(value, "model_dump"):
            # `by_alias=True` is what produces the camelCase keys AG-UI clients
            # expect (`sampleRate`, `turnOrder`); without it they read undefined.
            payload = value.model_dump(by_alias=True)
        else:
            payload = value
        await self._send_event(CustomEvent(name=name.value, value=payload))

    # -- lifecycle --------------------------------------------------------
    async def run(self) -> None:
        """Run until the client disconnects or the session is closed."""
        receive = asyncio.create_task(self._receive_loop())
        transcript = asyncio.create_task(self._stt_loop())
        try:
            await asyncio.wait(
                {receive, transcript}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            self._closed = True
            pending = [receive, transcript]
            for task in (self._response_task, self._pending_task):
                if task is not None:
                    pending.append(task)
            for task in pending:
                task.cancel()
            await self._cancel_audio()
            await asyncio.gather(*pending, return_exceptions=True)
            await self._stt.aclose()

    async def _ensure_stt_started(self) -> None:
        async with self._stt_start_lock:
            if self._stt_started:
                return
            await self._stt.start()
            self._stt_started = True

    # -- inbound ----------------------------------------------------------
    async def _receive_loop(self) -> None:
        try:
            while True:
                message = await self._ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                text = message.get("text")
                if text is not None:
                    await self._handle_text_message(text)
                    continue
                data = message.get("bytes")
                if data is not None:
                    await self._ensure_stt_started()
                    await self._stt.send_audio(data)
        except WebSocketDisconnect:
            logger.debug("Voice client disconnected (thread=%s)", self._thread_id)
        finally:
            if self._stt_started:
                await self._stt.aclose()

    async def _handle_text_message(self, raw: str) -> None:
        try:
            message = parse_client_message(raw)
        except Exception:
            logger.warning("Ignoring malformed voice message: %r", raw[:200])
            return

        match message:
            case SessionStart():
                if (
                    message.sample_rate is not None
                    and message.sample_rate != self._settings.voice.input_sample_rate
                ):
                    logger.warning(
                        "Client sample rate %s differs from configured %s",
                        message.sample_rate,
                        self._settings.voice.input_sample_rate,
                    )
                await self._ensure_stt_started()
                await self._send_custom(
                    VoiceCustomEvent.LISTENING, ListeningPayload(active=True)
                )
            case ChatText():
                await self._start_response(message.text)
            case Interrupt():
                await self._interrupt(reason="client_interrupt")
            case SessionStop():
                await self._send_custom(
                    VoiceCustomEvent.SESSION_END, SessionEndPayload(reason="client_stop")
                )
                self._closed = True
                await self._ws.close()

    # -- transcription ----------------------------------------------------
    async def _stt_loop(self) -> None:
        async for event in self._stt.events():
            if self._closed:
                break
            await self._handle_stt_event(event)

    async def _handle_stt_event(self, event: SttEvent) -> None:
        match event:
            case SttTurn(text=text, final=final, turn_order=order):
                # The provider ends a turn at the first pause, so consecutive
                # finals are usually one sentence split in two. Accumulate them
                # and let the grace period decide when the user is done.
                spoken = f"{self._pending_text} {text}".strip()
                await self._send_custom(
                    VoiceCustomEvent.TRANSCRIPT,
                    TranscriptPayload(
                        text=text,
                        final=final,
                        turn_order=order,
                        utterance=spoken,
                    ),
                )
                if final:
                    self._pending_text = spoken
                    self._schedule_response()
            case SttSpeechStarted():
                if self._speaking and self._settings.voice.barge_in:
                    await self._interrupt(reason="barge_in")
            case SttError(message=message):
                logger.error("STT error: %s", message)
                await self._send_event(RunErrorEvent(message=message, code="stt_error"))

    def _schedule_response(self) -> None:
        """(Re)start the grace period that ends the user's utterance.

        Every new final fragment resets it, so a sentence spoken with pauses
        yields one reply once the user really stops talking.
        """
        if self._pending_task is not None:
            self._pending_task.cancel()
        self._pending_task = asyncio.create_task(self._respond_after_pause())

    async def _respond_after_pause(self) -> None:
        grace = self._settings.voice.turn_grace_ms / 1000
        if grace:
            await asyncio.sleep(grace)
        text, self._pending_text = self._pending_text, ""
        self._pending_task = None
        if text.strip():
            await self._start_response(text)

    def _discard_pending(self) -> None:
        """Drop the collected fragments and the debounce timer."""
        if self._pending_task is not None:
            self._pending_task.cancel()
            self._pending_task = None
        self._pending_text = ""

    # -- turn handling ----------------------------------------------------
    async def _start_response(self, user_text: str) -> None:
        if not user_text.strip():
            return
        await self._cancel_turn()
        self._response_task = asyncio.create_task(self._respond(user_text))

    async def _cancel_turn(self) -> bool:
        """Cancel the in-flight turn, if any. Returns whether one was running."""
        task = self._response_task
        self._response_task = None
        if task is None or task.done():
            await self._cancel_audio()
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await self._cancel_audio()
        return True

    async def _interrupt(self, *, reason: str) -> None:
        """Cancel the in-flight turn and stop playback.

        The ``voice.interrupted`` event is sent *before* cancelling so the
        client stops playing audio as soon as possible.
        """
        task = self._response_task
        if task is not None and not task.done():
            await self._send_custom(VoiceCustomEvent.INTERRUPTED, {"reason": reason})
        await self._cancel_turn()
        self._discard_pending()
        self._speaking = False
        await self._send_custom(
            VoiceCustomEvent.LISTENING, ListeningPayload(active=True)
        )

    async def _cancel_audio(self) -> None:
        task = self._audio_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._audio_task = None

    async def _respond(self, user_text: str) -> None:
        run_id = uuid.uuid4().hex
        message_id = uuid.uuid4().hex
        deps = AgentDeps(thread_id=self._thread_id, channel="voice")

        await self._send_event(
            RunStartedEvent(thread_id=self._thread_id, run_id=run_id)
        )
        await self._send_custom(
            VoiceCustomEvent.LISTENING, ListeningPayload(active=False)
        )

        tts: StreamingTTS | None = None
        text_started = False
        buffer = ""
        spoken = ""
        result = None

        try:
            tts = self._tts_factory()
            await tts.start()
            self._speaking = True
            self._audio_task = asyncio.create_task(self._pump_audio(tts))

            history = await self._store.get_history(self._thread_id)
            # Persist what the user said *before* running the agent. A barge-in
            # cancels this task, so anything written afterwards would be lost
            # and the model would never learn that the user spoke at all.
            await self._store.append(
                self._thread_id,
                ModelRequest(parts=[UserPromptPart(content=user_text)]),
            )

            async with self._agent.run_stream_events(
                user_text,
                message_history=history,
                deps=deps,
            ) as events:
                async for event in events:
                    if isinstance(event, AgentRunResultEvent):
                        result = event.result
                        continue
                    delta = self._text_delta(event)
                    if delta is None:
                        continue
                    spoken += delta
                    if not text_started:
                        text_started = True
                        await self._send_event(
                            TextMessageStartEvent(message_id=message_id, role="assistant")
                        )
                    await self._send_event(
                        TextMessageContentEvent(message_id=message_id, delta=delta)
                    )
                    buffer += delta
                    ready, buffer = _split_for_tts(buffer, force=False)
                    if ready:
                        await tts.send_text(ready)

            ready, buffer = _split_for_tts(buffer, force=True)
            if ready:
                await tts.send_text(ready)
            await tts.finish()

            if text_started:
                await self._send_event(TextMessageEndEvent(message_id=message_id))

            # Wait for the synthesised audio to finish playing out.
            if self._audio_task is not None:
                await asyncio.shield(self._audio_task)

            if result is not None:
                await self._store.set_history(self._thread_id, result.all_messages())

            await self._send_event(
                RunFinishedEvent(thread_id=self._thread_id, run_id=run_id)
            )
        except asyncio.CancelledError:
            # Barge-in. Keep whatever the coach managed to say so the next turn
            # knows the reply was cut off instead of pretending it never spoke.
            await self._save_partial(spoken)
            raise
        except Exception as exc:  # noqa: BLE001 - surface failures to the client
            logger.exception("Voice turn failed")
            if text_started:
                await self._send_event(TextMessageEndEvent(message_id=message_id))
            await self._send_event(
                RunErrorEvent(message=str(exc), code="agent_error")
            )
        finally:
            self._speaking = False
            await self._cancel_audio()
            if tts is not None:
                await tts.aclose()
            if self._settings.voice.barge_in:
                await self._send_custom(
                    VoiceCustomEvent.LISTENING, ListeningPayload(active=True)
                )

    async def _save_partial(self, spoken: str) -> None:
        """Persist the assistant text produced before the turn was cancelled.

        The user's message was already appended when the turn started, so here
        we only need to record how far the reply got. An empty ``spoken`` means
        the agent was cut off before emitting a single token: there is nothing
        to record, and the trailing user message is left for the next turn.
        """
        if not spoken.strip():
            return
        await self._store.append(
            self._thread_id,
            ModelResponse(parts=[TextPart(content=spoken)]),
        )

    @staticmethod
    def _text_delta(event: Any) -> str | None:
        """Extract streamed assistant text from a pydantic-ai event."""
        if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
            return event.part.content or None
        if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            return event.delta.content_delta or None
        return None

    async def _pump_audio(self, tts: StreamingTTS) -> None:
        started = False
        total_bytes = 0
        try:
            async for chunk in tts.audio_chunks():
                if not chunk:
                    continue
                if not started:
                    started = True
                    await self._send_custom(
                        VoiceCustomEvent.AUDIO_START,
                        AudioStartPayload(
                            format=tts.output_format, sample_rate=tts.sample_rate
                        ),
                    )
                total_bytes += len(chunk)
                await self._send_bytes(chunk)
        finally:
            if started:
                # Sanity check: if the announced rate were wrong, this duration
                # would not match how long the reply actually takes to speak.
                seconds = total_bytes / 2 / max(tts.sample_rate, 1)
                logger.info(
                    "TTS turn: %d bytes @ %d Hz (%.2fs of audio)",
                    total_bytes,
                    tts.sample_rate,
                    seconds,
                )
                await self._send_custom(VoiceCustomEvent.AUDIO_END, {})


__all__ = ["VoiceSession"]
