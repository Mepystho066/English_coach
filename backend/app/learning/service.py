"""Learning service shared by the chat (AG-UI) and voice (RTVI) channels."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import Settings
from app.learning.analyzer import AnalyzeFn, build_analyzer, build_analyzer_model
from app.learning.models import (
    Analysis,
    Correction,
    LearningState,
    VocabularyItem,
)
from app.learning.store import (
    InMemoryLearningStore,
    LearningStore,
    SqliteLearningStore,
)

logger = logging.getLogger(__name__)

# One-word turns ("yes", "hello") have nothing to correct or teach.
_MIN_WORDS = 2

_QUOTES = "\"'“”‘’"


def _clean(value: str) -> str:
    """Trim spaces and the quotes small models like to wrap answers in."""
    value = value.strip()
    if len(value) >= 2 and value[0] in _QUOTES and value[-1] in _QUOTES:
        value = value[1:-1].strip()
    return value


class LearningService:
    def __init__(
        self,
        store: LearningStore,
        analyze: AnalyzeFn | None,
        *,
        timeout: float = 60.0,
        max_corrections: int = 200,
        max_vocabulary: int = 300,
    ) -> None:
        self._store = store
        self._analyze = analyze
        self._timeout = timeout
        self._max_corrections = max_corrections
        self._max_vocabulary = max_vocabulary
        self._locks: dict[str, asyncio.Lock] = {}
        # A local model serves one request at a time. Analyzing two turns in
        # parallel would make the next coach reply wait behind both, so
        # analyses are serialized across the process.
        self._analyze_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._analyze is not None

    async def get_state(self, thread_id: str) -> LearningState:
        state = (await self._store.get(thread_id)).refresh_progress()
        state.enabled = self.enabled
        return state

    async def clear(self, thread_id: str) -> None:
        await self._store.clear(thread_id)

    async def aclose(self) -> None:
        await self._store.aclose()

    async def record_turn(self, thread_id: str, text: str) -> LearningState | None:
        """Analyze one learner message and fold the result into the thread state.

        Returns the new state, or ``None`` when learning is off or the message
        was empty. A failed or slow analysis still counts the turn.
        """
        text = text.strip()
        if self._analyze is None or not text:
            return None

        analysis: Analysis | None = None
        if len(text.split()) >= _MIN_WORDS:
            try:
                async with self._analyze_lock:
                    analysis = await asyncio.wait_for(self._analyze(text), self._timeout)
            except TimeoutError:
                logger.warning("Learning analysis timed out after %ss", self._timeout)

        lock = self._locks.setdefault(thread_id, asyncio.Lock())
        async with lock:
            state = await self._store.get(thread_id)
            state.turns += 1
            if analysis is not None:
                self._merge(state, analysis, text)
            state.refresh_progress()
            await self._store.set(thread_id, state)
        state.enabled = True
        return state

    def _merge(self, state: LearningState, analysis: Analysis, source: str) -> None:
        known_fixes = {c.original.strip().lower() for c in state.corrections}
        for item in analysis.corrections:
            original = _clean(item.original)
            corrected = _clean(item.corrected)
            if not original or not corrected or original.lower() == corrected.lower():
                continue
            if original.lower() in known_fixes:
                continue
            known_fixes.add(original.lower())
            state.corrections.append(
                Correction(
                    original=original,
                    corrected=corrected,
                    explanation=_clean(item.explanation),
                    category=item.category,
                    source=source,
                    turn=state.turns,
                )
            )

        known_terms = {v.term.strip().lower() for v in state.vocabulary}
        for item in analysis.vocabulary:
            term = _clean(item.term)
            if not term or term.lower() in known_terms:
                continue
            known_terms.add(term.lower())
            state.vocabulary.append(
                VocabularyItem(
                    term=term,
                    meaning=_clean(item.meaning),
                    example=_clean(item.example),
                    turn=state.turns,
                )
            )

        del state.corrections[: -self._max_corrections]
        del state.vocabulary[: -self._max_vocabulary]


def build_learning_service(config: Settings, db_path: Path | None) -> LearningService:
    """Build the service for the app: SQLite when a path is set, else memory."""
    store: LearningStore = (
        SqliteLearningStore(db_path) if db_path is not None else InMemoryLearningStore()
    )
    analyze = (
        build_analyzer(build_analyzer_model(config)) if config.learning.enabled else None
    )
    return LearningService(
        store,
        analyze,
        timeout=config.learning.timeout,
        max_corrections=config.learning.max_corrections,
        max_vocabulary=config.learning.max_vocabulary,
    )


__all__ = ["LearningService", "build_learning_service"]
