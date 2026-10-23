"""Conversation history storage.

The store is deliberately small and interface-first: ``SessionStore`` is a
``Protocol`` so the in-memory implementation can be swapped for Redis, SQLite or
Postgres without touching the routes.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

from pydantic_ai.messages import ModelMessage, ModelRequest


@runtime_checkable
class SessionStore(Protocol):
    """Persistence boundary for per-conversation message history."""

    async def get_history(self, thread_id: str) -> list[ModelMessage]:
        """Return the stored history for a thread (empty list if unknown)."""
        ...

    async def set_history(self, thread_id: str, messages: Sequence[ModelMessage]) -> None:
        """Replace the stored history for a thread."""
        ...

    async def append(self, thread_id: str, message: ModelMessage) -> None:
        """Add one message to a thread's history."""
        ...

    async def clear(self, thread_id: str) -> None:
        """Drop a thread's history."""
        ...

    def lock(self, thread_id: str) -> asyncio.Lock:
        """Return the lock serialising runs for a thread."""
        ...


@dataclass
class _Session:
    messages: list[ModelMessage] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    updated_at: float = field(default_factory=time.monotonic)


class InMemorySessionStore:
    """Process-local ``SessionStore`` with TTL eviction and per-thread locks.

    Eviction is lazy: expired sessions are dropped whenever a session is
    touched, which is enough for a single-process deployment and avoids a
    background task.
    """

    def __init__(self, ttl_seconds: int = 3600, max_messages: int = 200) -> None:
        self._ttl = ttl_seconds
        self._max_messages = max_messages
        self._sessions: dict[str, _Session] = {}

    def _get_session(self, thread_id: str) -> _Session:
        now = time.monotonic()
        session = self._sessions.get(thread_id)
        if session is not None and now - session.updated_at > self._ttl:
            self._sessions.pop(thread_id, None)
            session = None
        if session is None:
            session = _Session()
            self._sessions[thread_id] = session
        return session

    def _trim(self, messages: list[ModelMessage]) -> list[ModelMessage]:
        if len(messages) <= self._max_messages:
            return messages
        trimmed = messages[-self._max_messages :]
        # Never start a history mid-turn: orphaned tool results would make the
        # next model request invalid on strict providers.
        for index, message in enumerate(trimmed):
            if isinstance(message, ModelRequest):
                return trimmed[index:]
        return trimmed

    async def get_history(self, thread_id: str) -> list[ModelMessage]:
        return list(self._get_session(thread_id).messages)

    async def set_history(self, thread_id: str, messages: Sequence[ModelMessage]) -> None:
        session = self._get_session(thread_id)
        session.messages = self._trim(list(messages))
        session.updated_at = time.monotonic()

    async def append(self, thread_id: str, message: ModelMessage) -> None:
        session = self._get_session(thread_id)
        session.messages = self._trim([*session.messages, message])
        session.updated_at = time.monotonic()

    async def clear(self, thread_id: str) -> None:
        self._sessions.pop(thread_id, None)

    def lock(self, thread_id: str) -> asyncio.Lock:
        return self._get_session(thread_id).lock

    async def aclose(self) -> None:
        """Drop every session (used on application shutdown)."""
        self._sessions.clear()


__all__ = ["InMemorySessionStore", "SessionStore"]
