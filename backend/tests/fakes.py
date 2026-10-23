"""In-test doubles for the external providers and for Starlette's WebSocket."""

from __future__ import annotations

import asyncio
from typing import Iterable

from app.services.stt.base import SttEvent, SttTurn

_STOP = object()


class FakeSTT:
    """Scripted `StreamingSTT`.

    Events passed at construction are emitted as soon as :meth:`start` is
    called. Audio frames are recorded in :attr:`chunks` for assertions.
    """

    def __init__(self, events: Iterable[SttEvent] = ()) -> None:
        self._events = list(events)
        self.chunks: list[bytes] = []
        self.started = False
        self.closed = False
        self._queue: asyncio.Queue[object] = asyncio.Queue()

    async def start(self) -> None:
        self.started = True
        for event in self._events:
            self._queue.put_nowait(event)

    async def send_audio(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def events(self):
        while True:
            item = await self._queue.get()
            if item is _STOP:
                return
            yield item

    def push(self, event: SttEvent) -> None:
        self._queue.put_nowait(event)

    async def aclose(self) -> None:
        self.closed = True
        self._queue.put_nowait(_STOP)


class FakeTTS:
    """Deterministic `StreamingTTS`.

    Yields its canned chunks immediately, then waits until :meth:`finish` (end
    of turn) or :meth:`aclose` (interrupt/teardown) is called.
    """

    def __init__(self, chunks: Iterable[bytes] = (b"\x01\x02\x03\x04",)) -> None:
        self._chunks = list(chunks)
        self.texts: list[str] = []
        self.started = False
        self.finished = False
        self.flushed = False
        self.closed = False
        self._done = asyncio.Event()

    @property
    def output_format(self) -> str:
        return "pcm_s16le"

    @property
    def sample_rate(self) -> int:
        return 24_000

    async def start(self) -> None:
        self.started = True

    async def send_text(self, text: str) -> None:
        self.texts.append(text)

    async def flush(self) -> None:
        self.flushed = True

    async def finish(self) -> None:
        self.finished = True
        self._done.set()

    async def audio_chunks(self):
        for chunk in self._chunks:
            yield chunk
        await self._done.wait()

    async def aclose(self) -> None:
        self.closed = True
        self._done.set()


class FakeTTSFactory:
    """Callable factory recording every :class:`FakeTTS` it hands out."""

    def __init__(self, chunks: Iterable[bytes] = (b"\x01\x02\x03\x04",)) -> None:
        self._chunks = list(chunks)
        self.created: list[FakeTTS] = []

    def __call__(self) -> FakeTTS:
        tts = FakeTTS(self._chunks)
        self.created.append(tts)
        return tts

    @property
    def last(self) -> FakeTTS:
        return self.created[-1]


class FakeWebSocket:
    """Minimal stand-in for `starlette.websockets.WebSocket`."""

    def __init__(self) -> None:
        self.inbound: asyncio.Queue[object] = asyncio.Queue()
        self.texts: list[str] = []
        self.binaries: list[bytes] = []
        self.closed = False
        self.close_code: int | None = None

    async def send_text(self, data: str) -> None:
        self.texts.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.binaries.append(data)

    async def send_json(self, data: object) -> None:
        import json

        self.texts.append(json.dumps(data))

    async def close(self, code: int = 1000) -> None:
        self.closed = True
        self.close_code = code
        self.inbound.put_nowait(_STOP)

    async def receive(self) -> dict:
        item = await self.inbound.get()
        if item is _STOP:
            return {"type": "websocket.disconnect", "code": 1000}
        if isinstance(item, bytes):
            return {"type": "websocket.receive", "bytes": item}
        return {"type": "websocket.receive", "text": item}

    async def feed(self, item: str | bytes) -> None:
        self.inbound.put_nowait(item)

    async def disconnect(self) -> None:
        self.inbound.put_nowait(_STOP)

    # -- assertions helpers --
    def events(self) -> list[str]:
        return [text for text in self.texts if text.startswith("{")]

    def event_names(self) -> list[str]:
        import json

        return [json.loads(text).get("name") or json.loads(text)["type"] for text in self.events()]

    def contains_text(self, needle: str) -> bool:
        return any(needle in text for text in self.texts)


__all__ = ["FakeSTT", "FakeTTS", "FakeTTSFactory", "FakeWebSocket"]


def make_turn(text: str, *, final: bool = True, order: int = 0) -> SttTurn:
    return SttTurn(text=text, final=final, turn_order=order)
