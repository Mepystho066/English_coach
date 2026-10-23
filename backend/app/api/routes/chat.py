"""Chat endpoint.

Exposes the standard AG-UI HTTP contract: a ``POST`` whose body is a
``RunAgentInput`` and whose response is an SSE stream of AG-UI events. Any
AG-UI-compatible client (for example CopilotKit) can talk to it unchanged.

Conversation history is kept server-side, keyed by ``RunAgentInput.threadId``.
The AG-UI protocol allows clients to send their own history; when they do, it
takes precedence for that run because it is merged by the adapter.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from pydantic_ai import Agent
from pydantic_ai.ui.ag_ui import AGUIAdapter

from app.agents.deps import AgentDeps
from app.api.deps import get_agent, get_store
from app.sessions.store import SessionStore

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(
    request: Request,
    agent: Agent[AgentDeps, str] = Depends(get_agent),
    store: SessionStore = Depends(get_store),
):
    """Run the agent for one AG-UI turn and stream the events back as SSE."""
    run_input = AGUIAdapter.build_run_input(await request.body())
    thread_id = run_input.thread_id or "default"

    lock = store.lock(thread_id)
    await lock.acquire()
    released = False

    async def on_complete(result) -> None:
        await store.set_history(thread_id, result.all_messages())

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

    async def body_with_release() -> AsyncIterator[str]:
        nonlocal released
        try:
            async for chunk in original_body:
                yield chunk
        finally:
            if not released:
                released = True
                lock.release()

    response.body_iterator = body_with_release()
    return response
