"""End-to-end tests for the voice pipeline using fake providers and socket."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.coach import build_coach_agent
from app.agents.deps import AgentDeps
from app.services.stt.base import SttSpeechStarted
from app.services.voice.pipeline import VoiceSession
from app.sessions.store import InMemorySessionStore
from tests.fakes import FakeSTT, FakeTTSFactory, FakeWebSocket, make_turn

pytestmark = pytest.mark.asyncio


def _render_history(history) -> str:
    """Flatten a pydantic-ai history into a searchable string.

    `ModelMessage` types are dataclasses (not pydantic models), so there is no
    `model_dump`; walking the parts is the portable way to assert on content.
    """
    chunks: list[str] = []
    for message in history:
        chunks.append(type(message).__name__)
        for part in getattr(message, "parts", ()):
            content = getattr(part, "content", None)
            if isinstance(content, str):
                chunks.append(content)
            elif content is not None:
                chunks.append(str(content))
    return "\n".join(chunks)


def _build_session(
    *,
    agent: Agent[AgentDeps, str],
    store: InMemorySessionStore,
    settings,
    stt: FakeSTT,
    tts_factory: FakeTTSFactory,
    thread_id: str = "voice-thread",
) -> tuple[VoiceSession, FakeWebSocket]:
    websocket = FakeWebSocket()
    session = VoiceSession(
        websocket=websocket,
        agent=agent,
        store=store,
        settings=settings,
        thread_id=thread_id,
        stt=stt,
        tts_factory=tts_factory,
    )
    return session, websocket


async def test_text_turn_streams_ag_ui_and_audio(
    agent, store, test_settings, wait_until
):
    stt = FakeSTT()
    tts_factory = FakeTTSFactory(chunks=(b"\x10\x20", b"\x30\x40"))
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    await websocket.feed(json.dumps({"type": "text", "text": "Hi coach"}))
    await wait_until(lambda: websocket.contains_text("RUN_FINISHED"))
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    texts = websocket.texts
    assert any('"TEXT_MESSAGE_CONTENT"' in text for text in texts)
    assert websocket.contains_text("How was your day?")
    assert any('"voice.audio.start"' in text for text in texts)
    assert any('"voice.audio.end"' in text for text in texts)

    assert websocket.binaries == [b"\x10\x20", b"\x30\x40"]

    tts = tts_factory.last
    assert tts.started and tts.finished and tts.closed
    # Text is streamed to the TTS engine before the turn finishes.
    assert "".join(tts.texts).startswith("Hello there!")

    history = await store.get_history("voice-thread")
    assert history, "voice turns must be persisted to the session store"


async def test_audio_start_announces_the_format_the_client_must_use(
    agent, store, test_settings, wait_until
):
    """The browser declares its AudioBuffer from this payload; if it drifts,
    playback speed drifts with it."""
    stt = FakeSTT()
    tts_factory = FakeTTSFactory()
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    await websocket.feed(json.dumps({"type": "text", "text": "Hi"}))
    await wait_until(lambda: websocket.contains_text("RUN_FINISHED"))
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    events = [json.loads(text) for text in websocket.texts if text.startswith("{")]
    start = next(e for e in events if e.get("name") == "voice.audio.start")
    assert start["value"]["sampleRate"] == 24_000
    assert start["value"]["channels"] == 1
    assert start["value"]["format"] == "pcm_s16le"


async def test_client_audio_is_forwarded_to_stt(
    agent, store, test_settings, wait_until
):
    stt = FakeSTT()
    tts_factory = FakeTTSFactory()
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    await websocket.feed(json.dumps({"type": "session.start", "sampleRate": 16000}))
    await websocket.feed(b"\x00\x01" * 16)
    await wait_until(lambda: stt.started and bool(stt.chunks))

    # A final transcription turn triggers a full agent + TTS response.
    stt.push(make_turn("Please correct my sentence", final=True, order=1))
    await wait_until(lambda: websocket.contains_text("RUN_FINISHED"))
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    assert stt.chunks == [b"\x00\x01" * 16]
    assert websocket.contains_text('"voice.transcript"')


async def test_partial_transcript_does_not_start_a_turn(
    agent, store, test_settings, wait_until
):
    stt = FakeSTT()
    tts_factory = FakeTTSFactory()
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("Please correct", final=False))
    await wait_until(lambda: websocket.contains_text('"voice.transcript"'))
    await asyncio.sleep(0.05)

    assert not websocket.contains_text("RUN_STARTED")
    assert tts_factory.created == []

    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)


async def test_barge_in_interrupts_the_assistant(
    store, test_settings, wait_until
):
    gate = asyncio.Event()

    async def slow_stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        yield "Let me think about "
        await gate.wait()
        yield "that for a moment."

    agent = build_coach_agent(FunctionModel(stream_function=slow_stream))
    stt = FakeSTT()
    tts_factory = FakeTTSFactory(chunks=(b"\x01\x02",))
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("Tell me about London", final=True))
    await wait_until(lambda: websocket.contains_text("TEXT_MESSAGE_CONTENT"))

    stt.push(SttSpeechStarted(timestamp_ms=1))
    await wait_until(lambda: websocket.contains_text('"voice.interrupted"'))

    assert tts_factory.last.closed, "the TTS context must be torn down on barge-in"

    gate.set()
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)


async def test_pause_split_fragments_are_answered_as_one_utterance(
    agent, store, test_settings, wait_until
):
    """A sentence spoken with "medias" arrives as several finals.

    Regression: each fragment used to trigger its own turn, cancelling the
    previous one, so the coach only ever answered the last fragment and the
    earlier text never reached the history.
    """
    stt = FakeSTT()
    tts_factory = FakeTTSFactory()
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("I went to the", final=True, order=1))
    stt.push(make_turn("market yesterday", final=True, order=2))
    stt.push(make_turn("and bought some fruit", final=True, order=3))

    await wait_until(lambda: websocket.contains_text("RUN_FINISHED"))
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    runs = [e for e in websocket.events() if '"RUN_STARTED"' in e]
    assert len(runs) == 1, "one pause-free reply per utterance, not one per fragment"
    assert len(tts_factory.created) == 1

    history = await store.get_history("voice-thread")
    joined = " ".join(
        part.content
        for message in history
        for part in getattr(message, "parts", ())
        if hasattr(part, "content")
    )
    assert "I went to the market yesterday" in joined
    assert "and bought some fruit" in joined, "the whole utterance must reach the LLM"


async def test_separate_utterances_get_separate_replies(
    agent, store, test_settings, wait_until
):
    """Once the grace period elapses, the next fragment is a new turn."""
    stt = FakeSTT()
    tts_factory = FakeTTSFactory()
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("First question", final=True, order=1))
    await wait_until(lambda: len(tts_factory.created) == 1)
    await wait_until(lambda: websocket.contains_text("RUN_FINISHED"))
    # A real pause: longer than `turn_grace_ms` (30 ms in the test settings).
    await asyncio.sleep(0.2)
    stt.push(make_turn("Second question", final=True, order=2))
    await wait_until(lambda: len(tts_factory.created) == 2)
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    assert len(tts_factory.created) == 2, "a real pause must start a new turn"


async def test_transcript_accumulates_until_the_reply(
    agent, store, test_settings, wait_until
):
    """The client must be able to keep the whole sentence on screen."""
    stt = FakeSTT()
    tts_factory = FakeTTSFactory()
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("I was thinking", final=True, order=1))
    stt.push(make_turn("about the past", final=True, order=2))
    await wait_until(lambda: websocket.contains_text('"utterance"'))

    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    transcripts = [
        e["value"]
        for e in (json.loads(text) for text in websocket.events())
        if e.get("name") == "voice.transcript"
    ]
    assert transcripts[-1]["text"] == "about the past"
    assert transcripts[-1]["utterance"] == "I was thinking about the past"


async def test_fragment_arriving_during_the_reply_is_merged_not_dropped(
    agent, store, test_settings, wait_until
):
    """A pause right after the coach starts answering must still be understood.

    The old code cancelled the in-flight turn, losing the fragment entirely.
    """
    stt = FakeSTT()
    tts_factory = FakeTTSFactory()
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("Can you explain", final=True, order=1))
    stt.push(make_turn("the past perfect", final=True, order=2))

    await wait_until(lambda: websocket.contains_text("RUN_FINISHED"))
    await asyncio.sleep(0.2)
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    assert len(tts_factory.created) == 1, "the fragments form a single utterance"


async def test_barge_in_keeps_what_the_user_said(
    store, test_settings, wait_until
):
    """The words spoken before an interruption must reach the history.

    Regression: a cancelled turn skipped `set_history` entirely, so barge-in
    silently erased both the user's sentence and the coach's partial reply.
    With several interruptions in a row the model lost the thread of the
    conversation completely.
    """
    gate = asyncio.Event()

    async def slow_stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        yield "London is "
        await gate.wait()
        yield "the capital of England."

    agent = build_coach_agent(FunctionModel(stream_function=slow_stream))
    stt = FakeSTT()
    tts_factory = FakeTTSFactory(chunks=(b"\x01\x02",))
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("Tell me about London", final=True))
    await wait_until(lambda: websocket.contains_text("TEXT_MESSAGE_CONTENT"))

    stt.push(SttSpeechStarted(timestamp_ms=1))
    await wait_until(lambda: websocket.contains_text('"voice.interrupted"'))
    await asyncio.sleep(0.05)

    history = await store.get_history("voice-thread")
    rendered = _render_history(history)
    assert "Tell me about London" in rendered, (
        "the user's sentence must survive a barge-in"
    )
    assert "London is " in rendered, (
        "the interrupted reply must be recorded so the model knows it spoke"
    )

    gate.set()
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)


async def test_next_turn_receives_the_interrupted_context(
    store, test_settings, wait_until
):
    """The turn after a barge-in must be told what was already said."""
    seen: list[str] = []
    gate = asyncio.Event()

    async def recording_stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        seen.append(_render_history(messages))
        yield "First answer."
        await gate.wait()

    agent = build_coach_agent(FunctionModel(stream_function=recording_stream))
    stt = FakeSTT()
    tts_factory = FakeTTSFactory(chunks=(b"\x01\x02",))
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("My name is Ana", final=True, order=1))
    await wait_until(lambda: websocket.contains_text("TEXT_MESSAGE_CONTENT"))

    stt.push(SttSpeechStarted(timestamp_ms=1))
    await wait_until(lambda: websocket.contains_text('"voice.interrupted"'))
    await asyncio.sleep(0.05)

    stt.push(make_turn("What is my name?", final=True, order=2))
    await wait_until(lambda: len(seen) >= 2)

    assert "My name is Ana" in seen[-1], (
        "the second turn must see the sentence lost by the barge-in"
    )
    assert "First answer." in seen[-1], (
        "the second turn must see the reply that was cut off"
    )

    gate.set()
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)


async def test_interruption_before_any_token_records_only_the_user(
    store, test_settings, wait_until
):
    """Nothing to save for the reply, and no half-empty assistant message."""
    gate = asyncio.Event()

    async def blocked_stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        await gate.wait()
        yield "Too late."

    agent = build_coach_agent(FunctionModel(stream_function=blocked_stream))
    stt = FakeSTT()
    tts_factory = FakeTTSFactory(chunks=(b"\x01\x02",))
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("Are you there?", final=True))
    await wait_until(lambda: websocket.contains_text('"voice.listening"'))
    await asyncio.sleep(0.05)

    stt.push(SttSpeechStarted(timestamp_ms=1))
    await wait_until(lambda: websocket.contains_text('"voice.interrupted"'))
    await asyncio.sleep(0.05)

    history = await store.get_history("voice-thread")
    rendered = _render_history(history)
    assert "Are you there?" in rendered
    assert "Too late." not in rendered

    gate.set()
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)


async def test_barge_in_discards_the_pending_utterance(
    store, test_settings, wait_until
):
    """Barge-in resets the buffer so the next sentence starts clean."""
    gate = asyncio.Event()

    async def slow_stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        yield "Let me think about "
        await gate.wait()
        yield "that."

    agent = build_coach_agent(FunctionModel(stream_function=slow_stream))
    stt = FakeSTT()
    tts_factory = FakeTTSFactory(chunks=(b"\x01\x02",))
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    stt.push(make_turn("Tell me about London", final=True))
    await wait_until(lambda: websocket.contains_text("TEXT_MESSAGE_CONTENT"))

    # Speech while the assistant talks, then a fragment that must NOT be
    # concatenated with the interrupted sentence.
    stt.push(SttSpeechStarted(timestamp_ms=1))
    await wait_until(lambda: websocket.contains_text('"voice.interrupted"'))
    stt.push(make_turn("Actually never mind", final=True, order=2))

    gate.set()
    await wait_until(lambda: len(tts_factory.created) == 2)
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    transcripts = [
        e["value"]
        for e in (json.loads(text) for text in websocket.events())
        if e.get("name") == "voice.transcript"
    ]
    assert transcripts[-1]["utterance"] == "Actually never mind", (
        "the interrupted sentence must not bleed into the next one"
    )


async def test_session_rejects_unknown_control_frames_without_crashing(
    agent, store, test_settings, wait_until
):
    stt = FakeSTT()
    tts_factory = FakeTTSFactory()
    session, websocket = _build_session(
        agent=agent,
        store=store,
        settings=test_settings,
        stt=stt,
        tts_factory=tts_factory,
    )

    task = asyncio.create_task(session.run())
    await websocket.feed("not-json")
    await websocket.feed(json.dumps({"type": "nonsense"}))
    await websocket.feed(json.dumps({"type": "text", "text": "Hi"}))
    await wait_until(lambda: websocket.contains_text("RUN_FINISHED"))
    await websocket.disconnect()
    await asyncio.wait_for(task, timeout=2)

    assert websocket.contains_text("TEXT_MESSAGE_CONTENT")
