"""Chat endpoint.

Exposes the standard AG-UI HTTP contract: a ``POST`` whose body is a
``RunAgentInput`` and whose response is an SSE stream of AG-UI events. Any
AG-UI-compatible client (for example CopilotKit) can talk to it unchanged.

Conversation history is kept server-side, keyed by ``RunAgentInput.threadId``.
The AG-UI protocol allows clients to send their own history; when they do, it
takes precedence for that run because it is merged by the adapter.

Besides the reply, each run carries a ``STATE_SNAPSHOT`` event with the
learner's corrections, vocabulary and progress.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from ag_ui.core import StateSnapshotEvent
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Depends, Request
from pydantic_ai import Agent
from pydantic_ai.ui.ag_ui import AGUIAdapter

from app.agents.deps import AgentDeps
from app.api.deps import get_agent, get_learning, get_store
from app.learning.service import LearningService
from app.sessions.store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# How long the end of a run waits for the analysis. A slower one still gets
# saved; the client picks it up from ``GET /threads/{id}/state``.
_SNAPSHOT_WAIT_SECONDS = 1.5

_encoder = EventEncoder()


def _last_user_text(run_input: Any) -> str:
    """Text of the newest user message in the run, or an empty string."""
    for message in reversed(run_input.messages):
        if getattr(message, "role", None) != "user":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        return " ".join(
            part.text for part in content or [] if getattr(part, "type", "") == "text"
        )
    return ""


@router.post("")
async def chat(
    request: Request,
    agent: Agent[AgentDeps, str] = Depends(get_agent),
    store: SessionStore = Depends(get_store),
    learning: LearningService = Depends(get_learning),
):
    """Run the agent for one AG-UI turn and stream the events back as SSE."""
    run_input = AGUIAdapter.build_run_input(await request.body())
    thread_id = run_input.thread_id or "default"

    lock = store.lock(thread_id)
    await lock.acquire()
    released = False

    async def on_complete(result) -> None:
        await store.set_history(thread_id, result.all_messages())

    user_text = _last_user_text(run_input)
    analysis: asyncio.Task | None = None

    def start_analysis() -> None:
        """Start analyzing the learner's message, once.

        It starts after the coach's text is complete: a local server handles one
        request at a time, so starting earlier would delay the reply itself.
        """
        nonlocal analysis
        if analysis is not None or not learning.enabled or not user_text.strip():
            return
        analysis = asyncio.create_task(learning.record_turn(thread_id, user_text))
        # Mark failures as seen even if the run ends before anyone awaits it.
        analysis.add_done_callback(lambda t: t.cancelled() or t.exception())

    try:
        response = await AGUIAdapter.dispatch_request(
            request,
            agent=agent,
            message_history=await store.get_history(thread_id),
            on_complete=on_complete,
            deps=AgentDeps(thread_id=thread_id, channel="chat"),
        )
    except Exception:
        released = True
        lock.release()
        raise

    original_body = response.body_iterator

    async def snapshot() -> str | None:
        """Encode the state snapshot to emit just before ``RUN_FINISHED``."""
        start_analysis()
        if analysis is None:
            return None
        try:
            state = await asyncio.wait_for(
                asyncio.shield(analysis), timeout=_SNAPSHOT_WAIT_SECONDS
            )
        except TimeoutError:
            logger.info("Learning analysis still running; the client will refetch it")
            return None
        except Exception:
            logger.exception("Learning analysis failed")
            return None
        if state is None:
            return None
        return _encoder.encode(StateSnapshotEvent(snapshot=state.model_dump(mode="json")))

    async def body_with_release() -> AsyncIterator[str]:
        nonlocal released
        has_text = False
        try:
            async for chunk in original_body:
                text = chunk.decode() if isinstance(chunk, bytes) else chunk
                if '"type":"TEXT_MESSAGE_START"' in text:
                    has_text = False
                elif '"type":"TEXT_MESSAGE_CONTENT"' in text:
                    has_text = True
                elif '"type":"TEXT_MESSAGE_END"' in text and has_text:
                    # Models often open with an empty message before a tool call;
                    # only a message that carried text is the actual reply.
                    yield chunk
                    start_analysis()
                    continue
                if '"type":"RUN_FINISHED"' in text:
                    event = await snapshot()
                    if event:
                        yield event
                yield chunk
        finally:
            if not released:
                released = True
                lock.release()

    response.body_iterator = body_with_release()
    return response
