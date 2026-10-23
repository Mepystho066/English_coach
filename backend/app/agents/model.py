"""Model construction.

Two backends are supported:

* a local OpenAI-compatible server (LM Studio, Ollama, vLLM, ...), and
* OpenRouter, which aggregates many providers behind the same wire format.

``LLM_PROVIDER`` decides which one answers:

* ``fallback``   - the local server first, OpenRouter only if it fails. This is
                   the default: nothing leaves the machine while LM Studio is
                   up, but a stopped server no longer breaks the conversation.
* ``local``      - local server only.
* ``openrouter`` - OpenRouter only.

A fallback only applies before the first token of a stream: once a reply has
started, a provider error propagates to the caller.
"""

from __future__ import annotations

import logging

from pydantic_ai import ModelSettings
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

# pydantic-ai's OpenRouterProvider hardcodes this endpoint; the env setting is
# validated against it instead of being silently ignored.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def build_local_model(config: Settings | None = None) -> Model:
    """Build the model for the local OpenAI-compatible server."""
    config = config or settings
    provider = OpenAIProvider(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key.get_secret_value(),
    )
    return OpenAIChatModel(
        config.llm.base_model,
        provider=provider,
        settings=ModelSettings(temperature=config.llm.temperature),
    )


def build_openrouter_model(config: Settings | None = None) -> Model:
    """Build the OpenRouter model.

    Raises:
        ValueError: if credentials are missing or ``OPEN_ROUTER_URL`` points
            somewhere OpenRouter's fixed endpoint would ignore.
    """
    config = config or settings
    orouter = config.openrouter

    if not orouter.is_configured:
        raise ValueError(
            "OpenRouter is not configured: set OPEN_ROUTER_API_KEY (or "
            "OPEN_ROUTER) and OPEN_ROUTER_MODEL."
        )
    if orouter.url.rstrip("/") != OPENROUTER_BASE_URL:
        raise ValueError(
            f"OPEN_ROUTER_URL must be {OPENROUTER_BASE_URL!r}; pydantic-ai's "
            f"OpenRouterProvider cannot target a different endpoint "
            f"(got {orouter.url!r})."
        )

    provider = OpenRouterProvider(
        api_key=orouter.api_key.get_secret_value(),
        app_url=orouter.app_url or None,
        app_title=orouter.app_title or None,
    )
    return OpenAIChatModel(
        orouter.model,
        provider=provider,
        settings=ModelSettings(temperature=config.llm.temperature),
    )


def build_model(config: Settings | None = None) -> Model:
    """Build the chat model selected by ``LLM_PROVIDER``."""
    config = config or settings

    match config.llm.provider:
        case "local":
            return build_local_model(config)
        case "openrouter":
            return build_openrouter_model(config)
        case _:
            local = build_local_model(config)
            if not config.openrouter.is_configured:
                logger.warning(
                    "LLM_PROVIDER=fallback but OpenRouter is not configured "
                    "(OPEN_ROUTER_API_KEY/OPEN_ROUTER + OPEN_ROUTER_MODEL); "
                    "using the local model only"
                )
                return local
            return FallbackModel(
                local,
                build_openrouter_model(config),
                # ModelAPIError covers connection refused, timeouts and 4xx/5xx,
                # which is exactly the "LM Studio is not running" case.
                fallback_on=(ModelAPIError,),
            )


__all__ = [
    "OPENROUTER_BASE_URL",
    "build_local_model",
    "build_model",
    "build_openrouter_model",
]
