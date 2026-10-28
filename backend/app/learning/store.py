"""Persistence for :class:`LearningState`, keyed by ``thread_id``."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from pathlib import Path
from typing import Protocol

from app.learning.models import LearningState


class LearningStore(Protocol):
    async def get(self, thread_id: str) -> LearningState: ...

    async def set(self, thread_id: str, state: LearningState) -> None: ...

    async def clear(self, thread_id: str) -> None: ...

    async def aclose(self) -> None: ...


class InMemoryLearningStore:
    def __init__(self) -> None:
        self._states: dict[str, str] = {}

    async def get(self, thread_id: str) -> LearningState:
        raw = self._states.get(thread_id)
        if raw is None:
            return LearningState()
        return LearningState.model_validate_json(raw)

    async def set(self, thread_id: str, state: LearningState) -> None:
        # ``enabled`` describes the service, not the conversation.
        self._states[thread_id] = state.model_dump_json(exclude={"enabled"})

    async def clear(self, thread_id: str) -> None:
        self._states.pop(thread_id, None)

    async def aclose(self) -> None:
        self._states.clear()


class SqliteLearningStore:
    """Stores each thread's state as JSON in the same SQLite file as the history."""

    def __init__(self, path: str | Path) -> None:
        self._db_lock = threading.Lock()
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._db_lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS learning ("
                "thread_id TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at REAL NOT NULL)"
            )

    def _read(self, thread_id: str) -> LearningState:
        with self._db_lock:
            row = self._conn.execute(
                "SELECT state FROM learning WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        if row is None:
            return LearningState()
        return LearningState.model_validate_json(row[0])

    def _write(self, thread_id: str, state: LearningState) -> None:
        with self._db_lock, self._conn:
            self._conn.execute(
                "INSERT INTO learning (thread_id, state, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(thread_id) DO UPDATE SET "
                "state = excluded.state, updated_at = excluded.updated_at",
                (thread_id, state.model_dump_json(exclude={"enabled"}), time.time()),
            )

    def _delete(self, thread_id: str) -> None:
        with self._db_lock, self._conn:
            self._conn.execute("DELETE FROM learning WHERE thread_id = ?", (thread_id,))

    async def get(self, thread_id: str) -> LearningState:
        return await asyncio.to_thread(self._read, thread_id)

    async def set(self, thread_id: str, state: LearningState) -> None:
        await asyncio.to_thread(self._write, thread_id, state)

    async def clear(self, thread_id: str) -> None:
        await asyncio.to_thread(self._delete, thread_id)

    async def aclose(self) -> None:
        with self._db_lock:
            self._conn.close()


__all__ = [
    "InMemoryLearningStore",
    "LearningStore",
    "SqliteLearningStore",
]
