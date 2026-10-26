"""Conversation history storage.

The store is deliberately small and interface-first: ``SessionStore`` is a
``Protocol`` so the in-memory implementation can be swapped for Redis, SQLite or
Postgres without touching the routes.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelRequest


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


def trim_history(messages: list[ModelMessage], max_messages: int) -> list[ModelMessage]:
    """Keep the last ``max_messages`` messages, starting on a user request."""
    if len(messages) <= max_messages:
        return messages
    trimmed = messages[-max_messages:]
    # Never start a history mid-turn: orphaned tool results would make the
    # next model request invalid on strict providers.
    for index, message in enumerate(trimmed):
        if isinstance(message, ModelRequest):
            return trimmed[index:]
    return trimmed


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
        return trim_history(messages, self._max_messages)

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


class SqliteSessionStore:
    """``SessionStore`` persisted in a SQLite file, so history survives restarts.

    There is no TTL: a conversation lives until it is cleared. Locks stay
    process-local, which is enough for a single-process deployment.
    """

    def __init__(self, path: str | Path, max_messages: int = 200) -> None:
        self._max_messages = max_messages
        self._locks: dict[str, asyncio.Lock] = {}
        self._db_lock = threading.Lock()
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._db_lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS threads ("
                "thread_id TEXT PRIMARY KEY, messages TEXT NOT NULL, updated_at REAL NOT NULL)"
            )

    def _read(self, thread_id: str) -> list[ModelMessage]:
        with self._db_lock:
            row = self._conn.execute(
                "SELECT messages FROM threads WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        if row is None:
            return []
        return list(ModelMessagesTypeAdapter.validate_json(row[0]))

    def _write(self, thread_id: str, messages: list[ModelMessage]) -> None:
        payload = ModelMessagesTypeAdapter.dump_json(messages).decode()
        with self._db_lock, self._conn:
            self._conn.execute(
                "INSERT INTO threads (thread_id, messages, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(thread_id) DO UPDATE SET "
                "messages = excluded.messages, updated_at = excluded.updated_at",
                (thread_id, payload, time.time()),
            )

    def _delete(self, thread_id: str) -> None:
        with self._db_lock, self._conn:
            self._conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))

    async def get_history(self, thread_id: str) -> list[ModelMessage]:
        return await asyncio.to_thread(self._read, thread_id)

    async def set_history(self, thread_id: str, messages: Sequence[ModelMessage]) -> None:
        trimmed = trim_history(list(messages), self._max_messages)
        await asyncio.to_thread(self._write, thread_id, trimmed)

    async def append(self, thread_id: str, message: ModelMessage) -> None:
        history = await self.get_history(thread_id)
        await self.set_history(thread_id, [*history, message])

    async def clear(self, thread_id: str) -> None:
        await asyncio.to_thread(self._delete, thread_id)

    def lock(self, thread_id: str) -> asyncio.Lock:
        return self._locks.setdefault(thread_id, asyncio.Lock())

    async def aclose(self) -> None:
        with self._db_lock:
            self._conn.close()


__all__ = ["InMemorySessionStore", "SessionStore", "SqliteSessionStore", "trim_history"]
