"""Application configuration.

Settings are grouped into small ``BaseSettings`` classes, one per external
dependency, each reading its own ``env_prefix``. ``Settings`` simply composes
them, so a single ``settings`` object exposes everything as
``settings.llm.base_url``, ``settings.assemblyai.api_key``, etc.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/.env - resolved relative to this file so the app works from any cwd.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

_BASE_CONFIG = SettingsConfigDict(
    env_file=_ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
    case_sensitive=False,
)


def _blank_to_none(value: Any) -> Any:
    """Treat ``VAR=`` in a .env file as "unset" rather than as an empty string."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


# Raw PCM formats the browser client can play without decoding. Anything else
# (mp3, ulaw, opus) would be interpreted as PCM16 and produce noise, so we
# reject it at startup instead of failing mysteriously at playback time.
SUPPORTED_PCM_FORMATS = frozenset(
    {
        "pcm_8000",
        "pcm_16000",
        "pcm_22050",
        "pcm_24000",
        "pcm_44100",
        "pcm_48000",
    }
)


class LLMSettings(BaseSettings):
    """OpenAI-compatible chat model (local server or cloud provider)."""

    model_config = SettingsConfigDict(env_prefix="LLM_", **_BASE_CONFIG)

    base_url: str = "http://127.0.0.1:1234/v1"
    base_model: str = "localmodel"
    api_key: SecretStr = SecretStr("local")
    temperature: float = 0.7
    request_timeout: float = 120.0
    # The voice fallback probes the local model with a one-token completion.
    # This also bounds a model that is still loading.
    probe_timeout: float = 4.0

    # Which backend answers chat turns:
    #
    # * ``fallback``   - local server first, OpenRouter if it fails. Nothing is
    #                    sent to OpenRouter while the local server answers.
    # * ``local``      - only the local OpenAI-compatible server.
    # * ``openrouter`` - only OpenRouter; requires credentials, fails at startup
    #                    without them.
    provider: Literal["fallback", "local", "openrouter"] = "fallback"


class OpenRouterSettings(BaseSettings):
    """OpenRouter credentials, used as the cloud model or as a fallback."""

    model_config = SettingsConfigDict(
        env_prefix="OPEN_ROUTER_",
        # `api_key` is addressed through an explicit alias list below, which
        # bypasses the prefix; this keeps the field constructible by name too.
        populate_by_name=True,
        **_BASE_CONFIG,
    )

    # OpenRouter exposes a single endpoint and pydantic-ai's provider hardcodes
    # it, so this is validated rather than passed through (see build_model).
    url: str = "https://openrouter.ai/api/v1"
    # Model ids are namespaced: "<provider>/<model>", optionally ":free".
    model: str = ""
    api_key: SecretStr = Field(
        default=SecretStr(""),
        # Accepts both the conventional name and the bare `OPEN_ROUTER` some
        # setups use for the key.
        validation_alias=AliasChoices("OPEN_ROUTER_API_KEY", "OPEN_ROUTER"),
    )
    # Optional attribution headers OpenRouter uses for its rankings.
    app_url: str = ""
    app_title: str = "english-coach"

    @property
    def is_configured(self) -> bool:
        """Whether both a key and a model are present."""
        return bool(self.api_key.get_secret_value()) and bool(self.model.strip())


class AssemblyAISettings(BaseSettings):
    """Streaming speech-to-text configuration."""

    model_config = SettingsConfigDict(env_prefix="ASSEMBLYAI_", **_BASE_CONFIG)

    api_key: SecretStr | None = None
    speech_model: str = "universal-3-6-pro"
    encoding: str = "pcm_s16le"
    # ``None`` lets AssemblyAI pick its own defaults for turn detection.
    #
    # `min_turn_silence` is the silence before a *speculative* end-of-turn
    # check. With Pipecat's turn tracking it is also sent as the forced
    # ``max_turn_silence`` (see ``vad_force_turn_endpoint`` in the pipeline),
    # so AssemblyAI does not end turns behind the smart-turn analyzer's back.
    min_turn_silence: int | None = None
    # Hard ceiling used only outside Pipecat's turn tracking mode. Kept so the
    # value is available if turn detection is switched back to AssemblyAI.
    max_turn_silence: int | None = None
    # Only applies to the ``universal-streaming-*`` models, not to
    # ``universal-3-*``. Harmless elsewhere, but it has no effect there.
    end_of_turn_confidence_threshold: float | None = None

    @property
    def is_configured(self) -> bool:
        return self.api_key is not None and bool(self.api_key.get_secret_value())

    @field_validator(
        "min_turn_silence",
        "max_turn_silence",
        "end_of_turn_confidence_threshold",
        mode="before",
    )
    @classmethod
    def _optional_numbers(cls, value: Any) -> Any:
        return _blank_to_none(value)


class ElevenLabsSettings(BaseSettings):
    """Streaming text-to-speech configuration."""

    model_config = SettingsConfigDict(env_prefix="ELEVENLABS_", **_BASE_CONFIG)

    api_key: SecretStr | None = None
    voice_id: str | None = None
    model_id: str = "eleven_v4_turbo"
    output_format: str = "pcm_24000"
    base_url: str = "wss://api.elevenlabs.io"

    @property
    def is_configured(self) -> bool:
        return (
            self.api_key is not None
            and bool(self.api_key.get_secret_value())
            and bool(self.voice_id)
        )

    @field_validator("output_format")
    @classmethod
    def _validate_output_format(cls, value: str) -> str:
        if value not in SUPPORTED_PCM_FORMATS:
            raise ValueError(
                f"ELEVENLABS_OUTPUT_FORMAT must be one of "
                f"{sorted(SUPPORTED_PCM_FORMATS)} so the browser can play the "
                "raw PCM frames; got " + repr(value)
            )
        return value

    @field_validator("voice_id", mode="before")
    @classmethod
    def _empty_voice_id(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @property
    def sample_rate(self) -> int:
        """Sample rate encoded in ``output_format`` (``pcm_24000`` -> 24000)."""
        _, _, rate = self.output_format.partition("_")
        return int(rate) if rate.isdigit() else 24_000


class VoiceSettings(BaseSettings):
    """Voice pipeline behaviour."""

    model_config = SettingsConfigDict(env_prefix="VOICE_", **_BASE_CONFIG)

    # Hard cap so a forgotten WebSocket cannot bill AssemblyAI forever.
    max_session_seconds: int = 900
    # Expected rate of the client's microphone chunks (AudioWorklet PCM16) and
    # of the frames sent to AssemblyAI. The output rate is derived from
    # ``ELEVENLABS_OUTPUT_FORMAT``.
    input_sample_rate: int = 16_000


class SessionSettings(BaseSettings):
    """Conversation store behaviour."""

    model_config = SettingsConfigDict(env_prefix="SESSION_", **_BASE_CONFIG)

    ttl_seconds: int = 3600
    max_turns: int = 100
    # SQLite file for persistent history (relative paths resolve from backend/).
    # Empty keeps history in memory, where it expires after ``ttl_seconds``.
    db_path: str = ""


class AppSettings(BaseSettings):
    """HTTP/app-level settings."""

    model_config = SettingsConfigDict(env_prefix="APP_", **_BASE_CONFIG)

    env: str = "development"
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip() == "*":
                return ["*"]
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


class Settings(BaseSettings):
    """Root settings object composing every section."""

    model_config = _BASE_CONFIG

    llm: LLMSettings = Field(default_factory=LLMSettings)
    # No underscore, like `assemblyai`/`elevenlabs`: a field named `open_router`
    # would make pydantic-settings read the bare `OPEN_ROUTER` env var (the API
    # key) as if it were this nested object.
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    assemblyai: AssemblyAISettings = Field(default_factory=AssemblyAISettings)
    elevenlabs: ElevenLabsSettings = Field(default_factory=ElevenLabsSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    app: AppSettings = Field(default_factory=AppSettings)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
