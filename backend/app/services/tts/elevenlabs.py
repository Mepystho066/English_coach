"""ElevenLabs streaming text-to-speech over WebSocket.

Uses the ``/v1/text-to-speech/{voice_id}/stream-input`` endpoint directly so we
control text chunking and flushing, which is where the perceived latency of a
voice assistant is decided.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, AsyncIterator
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from app.core.config import ElevenLabsSettings

logger = logging.getLogger(__name__)

_STOP = object()


class ElevenLabsStreamingTTS:
    """`StreamingTTS` for one assistant turn."""

    def __init__(self, config: ElevenLabsSettings) -> None:
        if not config.is_configured:
            raise ValueError("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID are not configured")
        self._config = config
        self._ws: ClientConnection | None = None
        self._reader: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[bytes | object] = asyncio.Queue()
        self._error: Exception | None = None
        self._closed = False

    # -- properties -------------------------------------------------------
    @property
    def output_format(self) -> str:
        return self._config.output_format

    @property
    def sample_rate(self) -> int:
        return self._config.sample_rate

    def _url(self) -> str:
        query = urlencode(
            {
                "model_id": self._config.model_id,
                "output_format": self._config.output_format,
                "auto_mode": "true",
            }
        )
        return (
            f"{self._config.base_url}/v1/text-to-speech/"
            f"{self._config.voice_id}/stream-input?{query}"
        )

    # -- StreamingTTS -----------------------------------------------------
    async def start(self) -> None:
        assert self._config.api_key is not None
        self._ws = await connect(
            self._url(),
            additional_headers={"xi-api-key": self._config.api_key.get_secret_value()},
            open_timeout=self._config.request_timeout,
            max_size=None,
        )
        # The first message must be an init message; ElevenLabs requires the
        # text to be a single space.
        await self._send(
            {
                "text": " ",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "use_speaker_boost": True,
                },
                "generation_config": {
                    "chunk_length_schedule": self._config.chunk_schedule
                },
            }
        )
        self._reader = asyncio.create_task(self._read_loop())
        logger.debug("ElevenLabs TTS context open (%s)", self._config.output_format)

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("TTS is not started")
        await self._ws.send(json.dumps(payload))

    async def send_text(self, text: str) -> None:
        if not text or self._closed:
            return
        await self._send({"text": text})

    async def flush(self) -> None:
        if self._closed:
            return
        # " " with flush=true forces generation of the remaining buffer without
        # closing the context.
        await self._send({"text": " ", "flush": True})

    async def finish(self) -> None:
        if self._closed:
            return
        # Flush the tail, then close the input side. The server still streams
        # the remaining audio followed by `isFinal`, so the read loop stays
        # alive until `audio_chunks()` is drained.
        await self.flush()
        if self._ws is not None:
            await self._send({"text": ""})

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                payload = json.loads(raw)
                if audio := payload.get("audio"):
                    self._queue.put_nowait(base64.b64decode(audio))
                if payload.get("isFinal"):
                    break
                if error := payload.get("error"):
                    raise RuntimeError(f"ElevenLabs error: {error}")
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            logger.debug("ElevenLabs socket closed")
        except Exception as exc:  # pragma: no cover - network dependent
            self._error = exc
            logger.warning("ElevenLabs read loop failed: %s", exc)
        finally:
            self._queue.put_nowait(_STOP)

    async def audio_chunks(self) -> AsyncIterator[bytes]:
        while True:
            item = await self._queue.get()
            if item is _STOP:
                break
            yield item  # type: ignore[misc]
        if self._error is not None:
            raise self._error

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                # Empty text closes the context gracefully.
                await ws.send(json.dumps({"text": ""}))
                await ws.close()
            except Exception:  # pragma: no cover - best-effort teardown
                logger.debug("ElevenLabs teardown raised", exc_info=True)
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except (asyncio.CancelledError, Exception):  # noqa: B014 - swallow teardown
                pass
            self._reader = None
        self._queue.put_nowait(_STOP)


__all__ = ["ElevenLabsStreamingTTS"]
