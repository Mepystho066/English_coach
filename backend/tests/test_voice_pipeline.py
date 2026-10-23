"""Unit tests for the Pipecat voice pipeline wiring (no network access)."""

from __future__ import annotations

import httpx
import pytest
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.utils.types import NotGiven

from app.agents.coach import load_instructions
from app.agents.model import OPENROUTER_BASE_URL
from app.core.config import AssemblyAISettings, OpenRouterSettings
from app.services.voice.llm import (
    build_local_llm,
    build_voice_llm,
    local_model_usable,
)
from app.services.voice.pipecat_pipeline import (
    _assemblyai_settings,
    build_context,
    build_pipeline,
    build_stt,
    build_transport,
    build_tts,
)


class _FakeWebSocket:
    """The transport only reads headers during construction."""

    headers: dict[str, str] = {}


def _openrouter_config(test_settings, *, provider: str = "openrouter"):
    return test_settings.model_copy(
        update={
            "llm": test_settings.llm.model_copy(update={"provider": provider}),
            "openrouter": OpenRouterSettings(
                _env_file=None,
                api_key="openrouter-key",
                model="recursive/flint-v1.0:free",
                url=OPENROUTER_BASE_URL,
            ),
        }
    )


def _sample_config(assemblyai: AssemblyAISettings):
    from app.core.config import Settings

    return Settings(assemblyai=assemblyai, _env_file=None)


def test_assemblyai_settings_omit_unset_turn_detection():
    settings = _assemblyai_settings(
        _sample_config(
            AssemblyAISettings(_env_file=None, api_key="key")
        )
    )

    assert settings.model == "universal-3-6-pro"
    assert isinstance(settings.min_turn_silence, NotGiven)
    assert isinstance(settings.max_turn_silence, NotGiven)


def test_assemblyai_settings_map_turn_detection():
    settings = _assemblyai_settings(
        _sample_config(
            AssemblyAISettings(
                _env_file=None,
                api_key="key",
                min_turn_silence=350,
                max_turn_silence=2000,
            )
        )
    )

    assert settings.min_turn_silence == 350
    assert settings.max_turn_silence == 2000


def test_build_stt_requires_an_api_key(test_settings):
    config = test_settings.model_copy(
        update={"assemblyai": AssemblyAISettings(_env_file=None)}
    )

    with pytest.raises(ValueError, match="ASSEMBLYAI_API_KEY"):
        build_stt(config)


def test_build_tts_requires_credentials(test_settings):
    from app.core.config import ElevenLabsSettings

    config = test_settings.model_copy(
        update={"elevenlabs": ElevenLabsSettings(_env_file=None)}
    )

    with pytest.raises(ValueError, match="ELEVENLABS"):
        build_tts(config)


def test_build_stt_and_tts_use_the_configured_rates(test_settings):
    stt = build_stt(test_settings)
    tts = build_tts(test_settings)

    assert stt._settings.model == "universal-3-6-pro"
    # ElevenLabs resolves the wire format when the session starts; the
    # configured rate is what the transport must announce.
    assert tts._init_sample_rate == test_settings.elevenlabs.sample_rate


def test_transport_announces_the_rates_the_client_uses(test_settings):
    transport = build_transport(_FakeWebSocket(), test_settings)  # type: ignore[arg-type]

    assert transport._params.audio_in_sample_rate == 16_000
    assert transport._params.audio_out_sample_rate == 24_000
    assert transport._params.audio_in_enabled
    assert transport._params.audio_out_enabled


def test_context_starts_with_the_prompt_and_prior_turns():
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart

    context = build_context(
        [
            ModelRequest.user_text_prompt("Hello"),
            ModelResponse(parts=[TextPart("Hi there")]),
        ],
    )

    messages = context.get_messages()
    assert messages[0] == {
        "role": "system",
        "content": load_instructions(),
    }
    assert {"role": "user", "content": "Hello"} in messages
    assert {"role": "assistant", "content": "Hi there"} in messages
    assert context.tools


def test_pipeline_wires_every_processor(test_settings):
    transport = build_transport(_FakeWebSocket(), test_settings)  # type: ignore[arg-type]
    context = build_context([])
    stt = build_stt(test_settings)
    llm = build_local_llm(test_settings)
    tts = build_tts(test_settings)

    pipeline, aggregators = build_pipeline(
        transport=transport,
        stt=stt,
        llm=llm,
        tts=tts,
        context=context,
        config=test_settings,
    )

    assert isinstance(pipeline, Pipeline)
    assert isinstance(aggregators, LLMContextAggregatorPair)

    processors = pipeline.processors
    # Pipeline adds a Source and a Sink around the seven configured stages.
    assert len(processors) == 9
    middle = processors[1:-1]
    assert [type(processor) for processor in middle] == [
        type(transport.input()),
        type(stt),
        type(aggregators.user()),
        type(llm),
        type(tts),
        type(transport.output()),
        type(aggregators.assistant()),
    ]


async def test_worker_installs_the_rtvi_processor(test_settings):
    transport = build_transport(_FakeWebSocket(), test_settings)  # type: ignore[arg-type]
    pipeline, _ = build_pipeline(
        transport=transport,
        stt=build_stt(test_settings),
        llm=build_local_llm(test_settings),
        tts=build_tts(test_settings),
        context=build_context([]),
        config=test_settings,
    )

    rtvi = RTVIProcessor()
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=test_settings.voice.input_sample_rate,
            audio_out_sample_rate=test_settings.elevenlabs.sample_rate,
            enable_metrics=True,
        ),
        rtvi_processor=rtvi,
    )

    assert worker.rtvi is rtvi


async def test_voice_llm_local_mode(test_settings):
    config = test_settings.model_copy(
        update={"llm": test_settings.llm.model_copy(update={"provider": "local"})}
    )

    assert isinstance(await build_voice_llm(config), OpenAILLMService)


async def test_voice_llm_openrouter_mode(test_settings):
    llm = await build_voice_llm(_openrouter_config(test_settings))

    assert isinstance(llm, OpenRouterLLMService)


async def test_voice_llm_openrouter_needs_credentials(test_settings):
    config = test_settings.model_copy(
        update={"llm": test_settings.llm.model_copy(update={"provider": "openrouter"})}
    )

    with pytest.raises(ValueError, match="OpenRouter is not configured"):
        await build_voice_llm(config)


def _patch_probe_client(monkeypatch, handler):
    """Replace ``httpx.AsyncClient`` so the probe never touches the network."""

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url, *, json=None, headers=None):
            return handler(url, json, headers)

    monkeypatch.setattr("app.services.voice.llm.httpx.AsyncClient", _Client)


async def test_probe_accepts_a_local_completion(test_settings, monkeypatch):
    _patch_probe_client(
        monkeypatch,
        lambda *_: httpx.Response(
            200, json={"choices": [{"message": {"content": "p"}}]}
        ),
    )

    usable, reason = await local_model_usable(test_settings)

    assert usable is True
    assert reason == "ok"


async def test_probe_reports_lm_studio_without_a_model(test_settings, monkeypatch):
    _patch_probe_client(
        monkeypatch,
        lambda *_: httpx.Response(
            400,
            json={
                "error": {
                    "message": (
                        "No models loaded. Please load a model in the "
                        "developer page or use the 'lms load' command."
                    )
                }
            },
        ),
    )

    usable, reason = await local_model_usable(test_settings)

    assert usable is False
    assert "No models loaded" in reason


async def test_probe_rejects_an_empty_completion(test_settings, monkeypatch):
    _patch_probe_client(
        monkeypatch, lambda *_: httpx.Response(200, json={"choices": []})
    )

    usable, reason = await local_model_usable(test_settings)

    assert usable is False
    assert "empty completion" in reason


async def test_probe_handles_a_dead_server(test_settings, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise httpx.ConnectError("connection refused")

    _patch_probe_client(monkeypatch, _boom)

    usable, reason = await local_model_usable(test_settings)

    assert usable is False
    assert "ConnectError" in reason


async def test_fallback_prefers_a_usable_local_model(test_settings, monkeypatch):
    async def _usable(*_args, **_kwargs) -> tuple[bool, str]:
        return True, "ok"

    monkeypatch.setattr("app.services.voice.llm.local_model_usable", _usable)

    llm = await build_voice_llm(_openrouter_config(test_settings, provider="fallback"))

    assert isinstance(llm, OpenAILLMService)


async def test_fallback_switches_to_openrouter_when_local_is_unusable(
    test_settings, monkeypatch
):
    async def _unusable(*_args, **_kwargs) -> tuple[bool, str]:
        return False, "HTTP 400: No models loaded"

    monkeypatch.setattr("app.services.voice.llm.local_model_usable", _unusable)

    llm = await build_voice_llm(_openrouter_config(test_settings, provider="fallback"))

    assert isinstance(llm, OpenRouterLLMService)


async def test_fallback_degrades_to_local_without_openrouter(test_settings):
    assert isinstance(await build_voice_llm(test_settings), OpenAILLMService)


async def test_closed_local_port_is_unusable(test_settings):
    config = test_settings.model_copy(
        update={
            "llm": test_settings.llm.model_copy(
                update={
                    "base_url": "http://127.0.0.1:1/v1",
                    "probe_timeout": 0.2,
                }
            )
        }
    )

    usable, reason = await local_model_usable(config)

    assert usable is False
    assert reason
