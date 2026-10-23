"""Provider factories for the voice pipeline.

Isolated in one module so the concrete providers can be swapped (or replaced by
fakes in tests) without touching the routes or the pipeline.
"""

from __future__ import annotations

from app.core.config import Settings
from app.services.stt.assemblyai import AssemblyAIStreamingSTT
from app.services.stt.base import StreamingSTT
from app.services.tts.base import StreamingTTS
from app.services.tts.elevenlabs import ElevenLabsStreamingTTS


def build_stt(config: Settings) -> StreamingSTT:
    return AssemblyAIStreamingSTT(
        config.assemblyai, sample_rate=config.voice.input_sample_rate
    )


def build_tts(config: Settings) -> StreamingTTS:
    return ElevenLabsStreamingTTS(config.elevenlabs)


__all__ = ["build_stt", "build_tts"]
