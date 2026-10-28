"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import ModelMessage

from app.agents.coach import build_coach_agent
from app.agents.deps import AgentDeps
from app.core.config import (
    AppSettings,
    AssemblyAISettings,
    ElevenLabsSettings,
    LearningSettings,
    LLMSettings,
    OpenRouterSettings,
    SessionSettings,
    Settings,
    VoiceSettings,
)
from app.sessions.store import InMemorySessionStore

REPLY_PARTS = ("Hello ", "there! ", "How was your day?")


async def _stream_reply(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str]:
    for part in REPLY_PARTS:
        yield part


@pytest.fixture
def test_settings() -> Settings:
    """Settings wired with dummy provider credentials (no network access).

    ``_env_file=None`` keeps the tests independent from the developer's ``.env``.
    """
    return Settings(
        llm=LLMSettings(
            _env_file=None,
            base_url="http://127.0.0.1:1/v1",
            base_model="test-model",
            api_key="test-key",
        ),
        assemblyai=AssemblyAISettings(_env_file=None, api_key="test-assemblyai-key"),
        # Empty on purpose: the developer's real .env may hold an OpenRouter key
        # and tests must never depend on (or leak) it.
        openrouter=OpenRouterSettings(_env_file=None),
        elevenlabs=ElevenLabsSettings(
            _env_file=None, api_key="test-elevenlabs-key", voice_id="test-voice"
        ),
        voice=VoiceSettings(_env_file=None),
        session=SessionSettings(_env_file=None),
        # The analyzer is a separate model call; tests turn it on explicitly.
        learning=LearningSettings(_env_file=None, enabled=False),
        app=AppSettings(_env_file=None),
    )


@pytest.fixture
def agent() -> Agent[AgentDeps, str]:
    return build_coach_agent(FunctionModel(stream_function=_stream_reply))


@pytest.fixture
def store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
async def wait_until() -> AsyncIterator[Callable[..., None]]:
    """Poll ``predicate`` until it is true, failing on timeout."""

    async def _wait(predicate: Callable[[], bool], *, timeout: float = 2.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return
            await asyncio.sleep(0.01)
        raise AssertionError("condition not met before timeout")

    yield _wait
