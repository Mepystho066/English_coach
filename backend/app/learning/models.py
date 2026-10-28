"""Data model for what the learner gets out of a conversation."""

from __future__ import annotations

import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Category = Literal["grammar", "vocabulary", "naturalness"]


class AnalysisCorrection(BaseModel):
    """One mistake reported by the analyzer."""

    original: str = Field(description="The exact fragment the learner said.")
    corrected: str = Field(description="The corrected, natural version.")
    explanation: str = Field(description="One short sentence, in Spanish, saying why.")
    category: Category = Field(
        description="grammar, vocabulary (wrong word) or naturalness (correct but unnatural)."
    )


class AnalysisVocabulary(BaseModel):
    """A word or expression worth learning, reported by the analyzer."""

    term: str = Field(description="The English word or expression.")
    meaning: str = Field(description="Its meaning, in Spanish.")
    example: str = Field(description="A short example sentence in English.")


class Analysis(BaseModel):
    """What the analyzer returns for one learner message."""

    corrections: list[AnalysisCorrection] = Field(default_factory=list)
    vocabulary: list[AnalysisVocabulary] = Field(default_factory=list)


class Correction(AnalysisCorrection):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    # Full learner message the correction came from; the UI uses it to show
    # the card under the right bubble.
    source: str = ""
    turn: int = 0
    created_at: float = Field(default_factory=time.time)


class VocabularyItem(AnalysisVocabulary):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    turn: int = 0
    created_at: float = Field(default_factory=time.time)


class Progress(BaseModel):
    turns: int = 0
    corrections: int = 0
    vocabulary: int = 0
    by_category: dict[str, int] = Field(
        default_factory=lambda: {"grammar": 0, "vocabulary": 0, "naturalness": 0}
    )


class LearningState(BaseModel):
    """Everything learned in one thread. ``progress`` is derived, never stored."""

    turns: int = 0
    corrections: list[Correction] = Field(default_factory=list)
    vocabulary: list[VocabularyItem] = Field(default_factory=list)
    progress: Progress = Field(default_factory=Progress)
    # Set from the service and excluded from storage: lets the client know
    # whether to wait for an analysis that will never come.
    enabled: bool = True

    def refresh_progress(self) -> "LearningState":
        by_category = {"grammar": 0, "vocabulary": 0, "naturalness": 0}
        for correction in self.corrections:
            by_category[correction.category] += 1
        self.progress = Progress(
            turns=self.turns,
            corrections=len(self.corrections),
            vocabulary=len(self.vocabulary),
            by_category=by_category,
        )
        return self


__all__ = [
    "Analysis",
    "AnalysisCorrection",
    "AnalysisVocabulary",
    "Category",
    "Correction",
    "LearningState",
    "Progress",
    "VocabularyItem",
]
