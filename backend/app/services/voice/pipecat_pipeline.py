"""Pipecat voice pipeline.

One pipeline per WebSocket connection:

    transport.input()
      -> AssemblyAI STT
      -> user context aggregator (VAD start + smart-turn stop)
      -> LLM (local or OpenRouter)
      -> ElevenLabs TTS
      -> transport.output()
      -> assistant context aggregator

RTVI is enabled by ``PipelineWorker``: it installs the processor that performs the
``client-ready``/``bot-ready`` handshake and the observer that emits transcript
and speaking events to the browser.

Turn detection is delegated to Pipecat (Silero VAD + Local Smart Turn v3), not
to AssemblyAI. ``vad_force_turn_endpoint=True`` keeps AssemblyAI from ending the
turn on its own, so the semantic analyzer can wait through a thinking pause
instead of answering one fragment at a time.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import WebSocket
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import InterruptionFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.assemblyai.stt import (
    AssemblyAISTTService,
    AssemblyAISTTSettings,
)
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner
from pydantic_ai.messages import ModelMessage

from app.agents.coach import load_instructions
from app.core.config import Settings
from app.services.voice.history import to_llm_messages, to_model_messages
from app.services.voice.llm import build_voice_llm
from app.sessions.store import SessionStore
from pipecat.services.elevenlabs.dialogue.tts import ElevenLabsDialogueTTSService
logger = logging.getLogger(__name__)

GET_DATETIME_TOOL = FunctionSchema(
    name="get_current_datetime",
    description="Return the current local date and time in ISO-8601 format.",
    properties={},
    required=[],
)


async def _get_current_datetime(params: FunctionCallParams) -> None:
    await params.result_callback(datetime.now().isoformat(timespec="seconds"))


def _assemblyai_settings(config: Settings) -> AssemblyAISTTSettings:
    """Map ``ASSEMBLYAI_*`` settings, omitting unset values.

    Pipecat distinguishes "not given" from ``None``, so only fields that are
    actually configured are passed through.
    """
    values: dict[str, Any] = {"model": config.assemblyai.speech_model}
    if config.assemblyai.min_turn_silence is not None:
        values["min_turn_silence"] = config.assemblyai.min_turn_silence
    if config.assemblyai.max_turn_silence is not None:
        values["max_turn_silence"] = config.assemblyai.max_turn_silence
    if config.assemblyai.end_of_turn_confidence_threshold is not None:
        values["end_of_turn_confidence_threshold"] = (
            config.assemblyai.end_of_turn_confidence_threshold
        )
    return AssemblyAISTTSettings(**values)


def build_transport(
    websocket: WebSocket, config: Settings
) -> FastAPIWebsocketTransport:
    """Build the WebSocket transport used by ``@pipecat-ai/client-js``."""
    return FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=config.voice.input_sample_rate,
            audio_out_sample_rate=config.elevenlabs.sample_rate,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        ),
    )


def build_stt(config: Settings) -> AssemblyAISTTService:
    """Build the streaming AssemblyAI service."""
    if not config.assemblyai.is_configured:
        raise ValueError("ASSEMBLYAI_API_KEY is not set")
    return AssemblyAISTTService(
        api_key=config.assemblyai.api_key.get_secret_value(),
        sample_rate=config.voice.input_sample_rate,
        encoding=config.assemblyai.encoding,
        # Pipecat's VAD + smart turn own turn detection; see module docstring.
        vad_force_turn_endpoint=True,
        settings=_assemblyai_settings(config),
    )


def build_tts(config: Settings) -> ElevenLabsDialogueTTSService:
    """Build the streaming ElevenLabs Dialogue service for v3/v4."""
    if not config.elevenlabs.is_configured:
        raise ValueError("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID must be set")
    return ElevenLabsDialogueTTSService(
        api_key=config.elevenlabs.api_key.get_secret_value(),
        settings=ElevenLabsDialogueTTSService.Settings(
            voice=config.elevenlabs.voice_id,
            model="eleven_v4_turbo",  # o "eleven_v4"
            stability=0.5,
        ),
    )

def build_tts_v2(config: Settings) -> ElevenLabsTTSService:
    """Build the streaming ElevenLabs service."""
    if not config.elevenlabs.is_configured:
        raise ValueError("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID must be set")
    return ElevenLabsTTSService(
        api_key=config.elevenlabs.api_key.get_secret_value(),
        url=config.elevenlabs.base_url,
        sample_rate=config.elevenlabs.sample_rate,
        settings=ElevenLabsTTSService.Settings(
            voice=config.elevenlabs.voice_id,
            model=config.elevenlabs.model_id,
        ),
    )


def build_context(history: list[ModelMessage]) -> LLMContext:
    """Build the LLM context seeded with instructions and prior turns."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": load_instructions()}
    ]
    messages.extend(to_llm_messages(history))
    return LLMContext(messages=messages, tools=[GET_DATETIME_TOOL])


def build_pipeline(
    *,
    transport: FastAPIWebsocketTransport,
    stt: AssemblyAISTTService,
    llm: Any,
    tts: ElevenLabsTTSService,
    context: LLMContext,
    config: Settings,
) -> tuple[Pipeline, LLMContextAggregatorPair]:
    """Assemble the frame processors in the order Pipecat expects."""
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                sample_rate=config.voice.input_sample_rate
            ),
        ),
    )
    llm.register_function("get_current_datetime", _get_current_datetime)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            aggregators.assistant(),
        ]
    )
    return pipeline, aggregators


async def run_voice_session(
    *,
    websocket: WebSocket,
    config: Settings,
    store: SessionStore,
    thread_id: str,
) -> None:
    """Run one voice conversation until the client leaves or the cap is hit."""
    history = await store.get_history(thread_id)
    llm = await build_voice_llm(config)

    transport = build_transport(websocket, config)
    stt = build_stt(config)
    tts = build_tts(config)
    context = build_context(history)

    pipeline, _ = build_pipeline(
        transport=transport,
        stt=stt,
        llm=llm,
        tts=tts,
        context=context,
        config=config,
    )

    rtvi = RTVIProcessor()
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=config.voice.input_sample_rate,
            audio_out_sample_rate=config.elevenlabs.sample_rate,
            enable_metrics=True,
        ),
        rtvi_processor=rtvi,
    )

    @transport.event_handler("on_client_connected")
    async def _on_client_connected(_transport, _client) -> None:
        logger.info("Voice client connected (thread=%s)", thread_id)

    @transport.event_handler("on_client_disconnected")
    async def _on_client_disconnected(_transport, _client) -> None:
        logger.info("Voice client disconnected (thread=%s)", thread_id)
        await worker.cancel()

    @rtvi.event_handler("on_client_message")
    async def _on_client_message(_rtvi, message) -> None:
        # The UI's "interrupt" button; barge-in by voice is handled by VAD.
        if message.type == "interrupt":
            await worker.queue_frames([InterruptionFrame()])

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    try:
        async with asyncio.timeout(config.voice.max_session_seconds):
            await runner.run()
    except TimeoutError:
        logger.info(
            "Voice session reached VOICE_MAX_SESSION_SECONDS=%s (thread=%s)",
            config.voice.max_session_seconds,
            thread_id,
        )
    finally:
        await store.set_history(
            thread_id, to_model_messages(context.get_messages())
        )
        logger.info(
            "Voice history saved (thread=%s, messages=%s)",
            thread_id,
            len(context.get_messages()),
        )


__all__ = [
    "GET_DATETIME_TOOL",
    "build_context",
    "build_pipeline",
    "build_stt",
    "build_transport",
    "build_tts",
    "run_voice_session",
]
