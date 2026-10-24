"""The English-coach agent.

One agent instance is shared by every channel (text chat and voice). Channel
specific tweaks are injected through dynamic instructions so we do not maintain
two divergent prompts.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai import Agent, RunContext

from app.agents.deps import AgentDeps
from app.agents.model import build_model
from app.core.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "coach.md"

_VOICE_ADDENDUM = """

"""


def load_instructions() -> str:
    """Load the base system instructions from `app/prompts/coach.md`."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def build_coach_agent(model: "Model | None" = None) -> Agent[AgentDeps, str]:
    """Build the coach agent, reusing a shared model instance."""
    agent: Agent[AgentDeps, str] = Agent(
        model or build_model(),
        deps_type=AgentDeps,
        instructions=load_instructions(),
        name="coach",
    )

    @agent.instructions
    def _channel_instructions(ctx: RunContext[AgentDeps]) -> str | None:
        if ctx.deps.channel == "voice":
            return _VOICE_ADDENDUM
        return None

    @agent.tool_plain
    def get_current_datetime() -> str:
        """Return the current local date and time in ISO-8601 format."""
        return datetime.now().isoformat(timespec="seconds")

    return agent


__all__ = ["build_coach_agent", "load_instructions"]
