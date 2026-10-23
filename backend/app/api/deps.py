"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request
from pydantic_ai import Agent
from starlette.websockets import WebSocket

from app.agents.deps import AgentDeps
from app.core.config import Settings
from app.sessions.store import InMemorySessionStore, SessionStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_agent(request: Request) -> Agent[AgentDeps, str]:
    return request.app.state.agent


def get_store(request: Request) -> InMemorySessionStore:
    return request.app.state.store


def get_agent_ws(websocket: WebSocket) -> Agent[AgentDeps, str]:
    return websocket.app.state.agent


def get_store_ws(websocket: WebSocket) -> SessionStore:
    return websocket.app.state.store
