"""Turns one learner message into corrections and vocabulary."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models import Model
from pydantic_ai.output import NativeOutput

from app.agents.model import build_local_model, build_openrouter_model
from app.core.config import Settings
from app.learning.models import Analysis

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "analyzer.md"

AnalyzeFn = Callable[[str], Awaitable[Analysis | None]]


def build_analyzer_model(config: Settings) -> Model:
    """Pick the model that analyzes turns.

    With ``LLM_PROVIDER=fallback`` the analyzer stays on the local model: it is
    an extra call per turn, so sending it to OpenRouter would spend the daily
    free quota twice as fast and, worse, compete with the coach's own replies.
    """
    if config.llm.provider == "openrouter":
        return build_openrouter_model(config)
    return build_local_model(config)


def build_analyzer(model: Model) -> AnalyzeFn:
    """Return an ``analyze(text)`` coroutine backed by ``model``."""
    agent: Agent[None, Analysis] = Agent(
        model,
        # LM Studio only accepts ``json_schema`` structured output, and small
        # local models call tools unreliably, so ask for the schema natively.
        output_type=NativeOutput(Analysis),
        instructions=_PROMPT_PATH.read_text(encoding="utf-8"),
        model_settings=ModelSettings(temperature=0),
        name="analyzer",
        retries=1,
    )

    async def analyze(text: str) -> Analysis | None:
        try:
            result = await agent.run(text)
        except Exception as exc:
            # Analysis is a bonus: never let it break a conversation.
            logger.warning("Learning analysis failed: %s: %s", type(exc).__name__, exc)
            return None
        return result.output

    return analyze


__all__ = ["AnalyzeFn", "build_analyzer", "build_analyzer_model"]
