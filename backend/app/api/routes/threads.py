"""Conversation history endpoints shared by the chat and voice channels."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_store
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


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str, store: SessionStore = Depends(get_store)
) -> Response:
    """Forget a thread's history (the "new conversation" button)."""
    await store.clear(thread_id)
    return Response(status_code=204)
