"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request
from pydantic_ai import Agent

from app.agents.deps import AgentDeps
from app.core.config import Settings
from app.sessions.store import SessionStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_agent(request: Request) -> Agent[AgentDeps, str]:
    return request.app.state.agent


def get_store(request: Request) -> SessionStore:
    return request.app.state.store
