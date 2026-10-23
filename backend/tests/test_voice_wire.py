"""Integration test over the real WebSocket route with fake providers.

Everything else in the suite drives `VoiceSession` directly. This one goes
through FastAPI, Starlette's WebSocket layer and the JSON serialisation, so it
is the only test that proves what the *browser* actually receives on the wire.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.voice import AudioStartPayload, VoiceCustomEvent
from app.services.stt.base import SttTurn
from tests.fakes import FakeSTT, FakeTTSFactory


def _collect_until(session, predicate, *, limit: int = 200):
    """Read frames in order, preserving text/binary interleaving.

    Returns a list of ``("text", dict)`` / ``("binary", bytes)`` tuples.
    """
    frames: list[tuple[str, object]] = []
    for _ in range(limit):
        message = session.receive()
        if message["type"] == "websocket.close":
            break
        if (text := message.get("text")) is not None:
            event = json.loads(text)
            frames.append(("text", event))
            if predicate(event):
                break
        elif (data := message.get("bytes")) is not None:
            frames.append(("binary", data))
    return frames


def test_voice_wire_format_over_the_real_websocket(test_settings, agent):
    app = create_app(test_settings)
    stt = FakeSTT([SttTurn(text="Hello coach", final=True, turn_order=1)])
    tts_factory = FakeTTSFactory(chunks=(b"\x01\x02" * 8,))

    with TestClient(app) as client:
        app.state.agent = agent
        app.state.stt_factory = lambda _config: stt
        app.state.tts_factory = lambda _config: tts_factory()

        with client.websocket_connect("/api/v1/voice/wire-format") as session:
            session.send_text(json.dumps({"type": "session.start", "sampleRate": 16000}))
            session.send_bytes(b"\x00\x01" * 32)

            frames = _collect_until(
                session, lambda event: event["type"] == "RUN_FINISHED"
            )

    texts = [payload for kind, payload in frames if kind == "text"]
    binaries = [payload for kind, payload in frames if kind == "binary"]
    order = [
        payload["name"] if kind == "text" and "name" in payload else kind
        if kind == "binary"
        else payload["type"]
        for kind, payload in frames
    ]

    assert binaries, "the assistant audio must arrive as raw binary frames"
    assert stt.chunks == [b"\x00\x01" * 32], "client audio must reach STT"

    names = [e.get("name") for e in texts if e["type"] == "CUSTOM"]
    assert VoiceCustomEvent.TRANSCRIPT.value in names
    assert VoiceCustomEvent.AUDIO_START.value in names
    assert VoiceCustomEvent.AUDIO_END.value in names

    start = next(
        e for e in texts if e.get("name") == VoiceCustomEvent.AUDIO_START.value
    )
    # The exact keys the browser reads: camelCase, per the AG-UI convention.
    # snake_case here is what made the coach sound like a chipmunk.
    assert start["value"] == {
        "format": "pcm_s16le",
        "sampleRate": 24_000,
        "channels": 1,
    }

    # `voice.audio.start` must precede the first audio frame, otherwise the
    # browser cannot know which sample rate the incoming PCM uses.
    assert order.index(VoiceCustomEvent.AUDIO_START.value) < order.index("binary")

    transcript = next(
        e for e in texts if e.get("name") == VoiceCustomEvent.TRANSCRIPT.value
    )
    assert transcript["value"]["text"] == "Hello coach"
    assert transcript["value"]["final"] is True
    assert transcript["value"]["turnOrder"] == 1

    # AG-UI standard events are present and use their own camelCase fields.
    types = [e["type"] for e in texts]
    assert types.index("RUN_STARTED") < types.index("TEXT_MESSAGE_START")
    assert types.index("TEXT_MESSAGE_START") < types.index("TEXT_MESSAGE_CONTENT")
    assert types.index("TEXT_MESSAGE_CONTENT") < types.index("TEXT_MESSAGE_END")
    assert types.index("TEXT_MESSAGE_END") < types.index("RUN_FINISHED")

    run_started = next(e for e in texts if e["type"] == "RUN_STARTED")
    assert run_started["threadId"] == "wire-format"

    content = "".join(
        e["delta"] for e in texts if e["type"] == "TEXT_MESSAGE_CONTENT"
    )
    assert content == "Hello there! How was your day?"


def test_voice_payload_model_matches_the_wire(test_settings, agent):
    """Belt and braces: the schema we assert on is the schema the browser sees."""
    payload = AudioStartPayload(sample_rate=24_000).model_dump(by_alias=True)

    assert set(payload) == {"format", "sampleRate", "channels"}
