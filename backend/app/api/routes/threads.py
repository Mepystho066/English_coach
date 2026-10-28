"""Conversation history endpoints shared by the chat and voice channels."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_learning, get_store
from app.learning.models import LearningState
from app.learning.service import LearningService
from app.services.voice.history import to_llm_messages
from app.sessions.store import SessionStore

router = APIRouter(prefix="/threads", tags=["threads"])


@router.get("/{thread_id}/messages")
async def list_messages(
    thread_id: str, store: SessionStore = Depends(get_store)
) -> dict[str, object]:
    """Return the user/assistant text turns stored for a thread."""
    history = await store.get_history(thread_id)
    return {"threadId": thread_id, "messages": to_llm_messages(history)}


@router.get("/{thread_id}/state")
async def get_state(
    thread_id: str, learning: LearningService = Depends(get_learning)
) -> LearningState:
    """Corrections, vocabulary and progress collected for a thread."""
    return await learning.get_state(thread_id)


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str,
    store: SessionStore = Depends(get_store),
    learning: LearningService = Depends(get_learning),
) -> Response:
    """Forget a thread's history and learning state ("new conversation")."""
    await store.clear(thread_id)
    await learning.clear(thread_id)
    return Response(status_code=204)
