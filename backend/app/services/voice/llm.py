"""Pipecat LLM services, mirroring the chat provider policy.

``LLM_PROVIDER`` keeps the same meaning as on the chat channel:

* ``local``      - the local OpenAI-compatible server only.
* ``openrouter`` - OpenRouter only.
* ``fallback``   - the local server when it can answer, OpenRouter otherwise.

Pipecat has no ``FallbackModel`` equivalent, so for voice the fallback is
resolved once when the session starts. A TCP connection is not enough: LM
Studio keeps listening with no model loaded and rejects the first completion
with HTTP 400, so the probe sends a real one-token completion. A server that
dies mid-conversation fails the turn instead of switching providers, which is
the same trade-off the chat channel already makes after the first token.
"""

from __future__ import annotations

import logging

import httpx
from pipecat.services.llm_service import LLMService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openrouter.llm import OpenRouterLLMService

from app.agents.model import OPENROUTER_BASE_URL
from app.core.config import Settings

logger = logging.getLogger(__name__)


def build_local_llm(config: Settings) -> LLMService:
    """Build the Pipecat service for the local OpenAI-compatible server."""
    return OpenAILLMService(
        api_key=config.llm.api_key.get_secret_value(),
        base_url=config.llm.base_url,
        settings=OpenAILLMService.Settings(
            model=config.llm.base_model,
            temperature=config.llm.temperature,
        ),
    )


def build_openrouter_llm(config: Settings) -> LLMService:
    """Build the Pipecat service for OpenRouter.

    Raises:
        ValueError: if credentials are missing or ``OPEN_ROUTER_URL`` points
            somewhere other than OpenRouter's endpoint.
    """
    orouter = config.openrouter

    if not orouter.is_configured:
        raise ValueError(
            "OpenRouter is not configured: set OPEN_ROUTER_API_KEY (or "
            "OPEN_ROUTER) and OPEN_ROUTER_MODEL."
        )
    if orouter.url.rstrip("/") != OPENROUTER_BASE_URL:
        raise ValueError(
            f"OPEN_ROUTER_URL must be {OPENROUTER_BASE_URL!r} for the voice "
            f"pipeline (got {orouter.url!r})."
        )

    return OpenRouterLLMService(
        api_key=orouter.api_key.get_secret_value(),
        base_url=OPENROUTER_BASE_URL,
        settings=OpenRouterLLMService.Settings(
            model=orouter.model,
            temperature=config.llm.temperature,
        ),
    )


def _error_reason(response: httpx.Response) -> str:
    """Extract a short, human-readable reason from an error response."""
    message: str | None = None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            value = error.get("message")
            if isinstance(value, str):
                message = value

    message = message or response.text or response.reason_phrase
    return f"HTTP {response.status_code}: {message.strip()}"[:300]


async def local_model_usable(
    config: Settings, *, timeout: float | None = None
) -> tuple[bool, str]:
    """Return whether the local model can answer a completion.

    Args:
        config: Application settings.
        timeout: Optional override for ``LLM_PROBE_TIMEOUT``.

    Returns:
        A ``(usable, reason)`` pair; ``reason`` is ``"ok"`` on success.
    """
    probe_timeout = config.llm.probe_timeout if timeout is None else timeout
    url = f"{config.llm.base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": config.llm.base_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {config.llm.api_key.get_secret_value()}",
    }

    try:
        async with httpx.AsyncClient(
            timeout=probe_timeout, trust_env=False
        ) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        return False, f"timeout after {probe_timeout:g}s"
    except httpx.HTTPError as exc:
        return False, f"connection failed: {type(exc).__name__}"

    if response.status_code != 200:
        return False, _error_reason(response)

    try:
        body = response.json()
    except ValueError:
        return False, "invalid JSON from the local server"

    if not isinstance(body, dict) or not body.get("choices"):
        return False, "empty completion from the local server"

    return True, "ok"


async def build_voice_llm(config: Settings) -> LLMService:
    """Build the LLM service selected by ``LLM_PROVIDER``."""
    match config.llm.provider:
        case "local":
            return build_local_llm(config)
        case "openrouter":
            return build_openrouter_llm(config)
        case _:
            if not config.openrouter.is_configured:
                logger.warning(
                    "LLM_PROVIDER=fallback but OpenRouter is not configured; "
                    "using the local voice model only"
                )
                return build_local_llm(config)

            usable, reason = await local_model_usable(config)
            if usable:
                logger.info("Voice LLM: local (model=%s)", config.llm.base_model)
                return build_local_llm(config)

            logger.warning(
                "Local LLM unusable (%s); using OpenRouter for this voice "
                "session",
                reason,
            )
            return build_openrouter_llm(config)


__all__ = [
    "build_local_llm",
    "build_openrouter_llm",
    "build_voice_llm",
    "local_model_usable",
]
