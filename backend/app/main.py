"""Application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agents.coach import build_coach_agent
from app.agents.model import build_model
from app.api.routes import chat, health, threads, voice
from app.core.config import Settings, settings as default_settings
from app.core.logging import configure_logging, get_logger
from app.sessions.store import InMemorySessionStore, SqliteSessionStore

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_STATIC_DIR = _BACKEND_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger = get_logger(__name__)

    config: Settings = app.state.settings
    app.state.agent = build_coach_agent(build_model(config))
    max_messages = config.session.max_turns * 2
    if config.session.db_path.strip():
        db_path = Path(config.session.db_path)
        if not db_path.is_absolute():
            db_path = _BACKEND_DIR / db_path
        app.state.store = SqliteSessionStore(db_path, max_messages=max_messages)
        logger.info("Session history persisted in %s", db_path)
    else:
        app.state.store = InMemorySessionStore(
            ttl_seconds=config.session.ttl_seconds, max_messages=max_messages
        )
        logger.info("Session history kept in memory (ttl=%ss)", config.session.ttl_seconds)

    logger.info(
        "LLM ready (provider=%s, local=%s @ %s, openrouter=%s)",
        config.llm.provider,
        config.llm.base_model,
        config.llm.base_url,
        config.openrouter.model if config.openrouter.is_configured else "not configured",
    )
    logger.info(
        "Voice pipeline ready (pipecat, in=%s Hz, out=%s Hz)",
        config.voice.input_sample_rate,
        config.elevenlabs.sample_rate,
    )
    if not config.assemblyai.is_configured:
        logger.warning(
            "ASSEMBLYAI_API_KEY is not set; /api/v1/voice will reject new sessions"
        )
    if not config.elevenlabs.is_configured:
        logger.warning(
            "ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID are not set; "
            "/api/v1/voice will reject new sessions"
        )

    try:
        yield
    finally:
        await app.state.store.aclose()


def create_app(config: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    ``config`` defaults to the process-wide settings singleton and can be
    overridden in tests.
    """
    resolved = config or default_settings
    app = FastAPI(
        title="english-coach backend",
        version="0.1.0",
        description="Streaming chat (AG-UI) and voice (Pipecat + AssemblyAI + ElevenLabs).",
        lifespan=lifespan,
    )
    app.state.settings = resolved

    origins = resolved.app.cors_origins
    allow_all = "*" in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1")
    app.include_router(threads.router, prefix="/api/v1")

    if _STATIC_DIR.is_dir():
        app.mount(
            "/static", StaticFiles(directory=_STATIC_DIR, html=True), name="static"
        )

    return app


__all__ = ["create_app", "lifespan"]
