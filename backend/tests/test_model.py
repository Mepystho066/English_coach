"""Model selection: local server, OpenRouter and the fallback chain.

Constructing a model does not open any connection, so these tests stay offline.
"""

from __future__ import annotations

import logging

import pytest
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel

from app.agents.model import (
    OPENROUTER_BASE_URL,
    build_local_model,
    build_model,
)
from app.core.config import LLMSettings, OpenRouterSettings, Settings

_OR_KEY = "sk-or-test"
_OR_MODEL = "recursive/flint-v1.0:free"


def _with(
    settings: Settings,
    *,
    provider: str | None = None,
    temperature: float | None = None,
    orouter: OpenRouterSettings | None = None,
) -> Settings:
    """Return a copy of the hermetic test settings with overrides applied."""
    update: dict[str, object] = {}
    llm_changes: dict[str, object] = {}
    if provider is not None:
        llm_changes["provider"] = provider
    if temperature is not None:
        llm_changes["temperature"] = temperature
    if llm_changes:
        update["llm"] = settings.llm.model_copy(update=llm_changes)
    if orouter is not None:
        update["openrouter"] = orouter
    return settings.model_copy(update=update)


def _orouter(*, api_key: str = _OR_KEY, url: str = OPENROUTER_BASE_URL) -> OpenRouterSettings:
    return OpenRouterSettings(
        _env_file=None,
        api_key=api_key,
        url=url,
        model=_OR_MODEL if api_key else "",
    )


def test_provider_defaults_to_fallback():
    assert LLMSettings(_env_file=None).provider == "fallback"


def test_openrouter_key_reads_the_bare_variable(monkeypatch):
    """Some setups name the key `OPEN_ROUTER` instead of `OPEN_ROUTER_API_KEY`."""
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_ROUTER", "sk-or-bare")

    config = OpenRouterSettings(_env_file=None)

    assert config.api_key.get_secret_value() == "sk-or-bare"


def test_openrouter_canonical_variable_wins(monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-or-canonical")
    monkeypatch.setenv("OPEN_ROUTER", "sk-or-bare")

    config = OpenRouterSettings(_env_file=None)

    assert config.api_key.get_secret_value() == "sk-or-canonical"


def test_openrouter_needs_both_key_and_model():
    assert not OpenRouterSettings(_env_file=None).is_configured
    assert not OpenRouterSettings(
        _env_file=None, api_key="key", model=""
    ).is_configured
    assert OpenRouterSettings(
        _env_file=None, api_key="key", model=_OR_MODEL
    ).is_configured


def test_local_mode_returns_a_single_local_model(test_settings):
    model = build_model(_with(test_settings, provider="local"))

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "test-model"
    assert str(model.client.base_url).rstrip("/") == "http://127.0.0.1:1/v1"


def test_openrouter_mode_targets_the_cloud_endpoint(test_settings):
    model = build_model(
        _with(test_settings, provider="openrouter", orouter=_orouter())
    )

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == _OR_MODEL
    assert str(model.client.base_url).rstrip("/") == OPENROUTER_BASE_URL


def test_openrouter_mode_fails_fast_without_credentials(test_settings):
    """A misconfigured deployment should not wait for the first user turn."""
    with pytest.raises(ValueError, match="OPEN_ROUTER_API_KEY"):
        build_model(_with(test_settings, provider="openrouter"))


def test_openrouter_url_cannot_point_somewhere_else(test_settings):
    """pydantic-ai hardcodes the endpoint, so an ignored URL must be an error."""
    with pytest.raises(ValueError, match="OPEN_ROUTER_URL"):
        build_model(
            _with(
                test_settings,
                provider="openrouter",
                orouter=_orouter(url="https://proxy.internal/v1"),
            )
        )


def test_fallback_tries_local_before_openrouter(test_settings):
    model = build_model(
        _with(test_settings, provider="fallback", orouter=_orouter())
    )

    assert isinstance(model, FallbackModel)
    assert [type(m) for m in model.models] == [OpenAIChatModel, OpenAIChatModel]
    assert [m.model_name for m in model.models] == ["test-model", _OR_MODEL]


def test_fallback_degrades_to_local_without_credentials(test_settings, caplog):
    with caplog.at_level(logging.WARNING, logger="app.agents.model"):
        model = build_model(_with(test_settings, provider="fallback"))

    assert isinstance(model, OpenAIChatModel), "no empty fallback slot"
    assert "OpenRouter is not configured" in caplog.text


def test_temperature_reaches_the_model_settings(test_settings):
    model = build_local_model(_with(test_settings, temperature=0.25))

    assert model.settings["temperature"] == 0.25


def test_temperature_reaches_both_models(test_settings):
    model = build_model(
        _with(test_settings, provider="fallback", temperature=0.1, orouter=_orouter())
    )

    assert [m.settings["temperature"] for m in model.models] == [0.1, 0.1]


def test_openrouter_attribution_headers_are_sent(test_settings):
    orouter = OpenRouterSettings(
        _env_file=None,
        api_key=_OR_KEY,
        model=_OR_MODEL,
        app_title="english-coach",
        app_url="https://example.com",
    )
    model = build_model(_with(test_settings, provider="openrouter", orouter=orouter))

    headers = model.client.default_headers
    assert headers["X-Title"] == "english-coach"
    assert headers["HTTP-Referer"] == "https://example.com"
