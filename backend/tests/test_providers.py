"""Tests for the wire contract and provider wiring (no network access)."""

from __future__ import annotations

import pytest

from app.core.config import AssemblyAISettings, ElevenLabsSettings, VoiceSettings
from app.schemas.voice import (
    AudioStartPayload,
    ChatText,
    Interrupt,
    SessionStart,
    SessionStop,
    TranscriptPayload,
    parse_client_message,
)
from app.services.stt.assemblyai import AssemblyAIStreamingSTT
from app.services.tts.elevenlabs import ElevenLabsStreamingTTS


def test_client_messages_are_discriminated_by_type():
    assert isinstance(parse_client_message('{"type": "session.start"}'), SessionStart)
    assert isinstance(
        parse_client_message('{"type": "text", "text": "hi"}'), ChatText
    )
    assert isinstance(
        parse_client_message('{"type": "response.interrupt"}'), Interrupt
    )
    assert isinstance(parse_client_message('{"type": "session.stop"}'), SessionStop)


def test_unknown_and_invalid_client_messages_are_rejected():
    with pytest.raises(Exception):
        parse_client_message('{"type": "nope"}')
    with pytest.raises(Exception):
        parse_client_message("not json")
    with pytest.raises(Exception):
        parse_client_message('{"type": "text", "text": "   "}')


def test_session_start_defaults_sample_rate_to_none():
    assert parse_client_message('{"type": "session.start"}').sample_rate is None


def test_client_messages_accept_camel_case_aliases():
    """AG-UI clients send camelCase; the field must not be silently dropped."""
    message = parse_client_message('{"type": "session.start", "sampleRate": 16000}')
    assert message.sample_rate == 16_000


def test_audio_start_payload_serialises_as_camel_case():
    """Regression: snake_case here made the browser read `undefined` and play
    24 kHz PCM at the device rate, i.e. chipmunk audio."""
    dumped = AudioStartPayload(sample_rate=24_000).model_dump(by_alias=True)

    assert dumped["sampleRate"] == 24_000
    assert "sample_rate" not in dumped


def test_transcript_payload_serialises_as_camel_case():
    dumped = TranscriptPayload(text="hi", final=True, turn_order=3).model_dump(
        by_alias=True
    )

    assert dumped["turnOrder"] == 3
    assert "turn_order" not in dumped


def test_stt_requires_an_api_key():
    with pytest.raises(ValueError):
        AssemblyAIStreamingSTT(AssemblyAISettings(_env_file=None))


def test_tts_requires_credentials():
    with pytest.raises(ValueError):
        ElevenLabsStreamingTTS(ElevenLabsSettings(_env_file=None))


def test_elevenlabs_stream_input_url():
    tts = ElevenLabsStreamingTTS(
        ElevenLabsSettings(
            _env_file=None,
            api_key="key",
            voice_id="voice-1",
            model_id="eleven_flash_v2_5",
            output_format="pcm_24000",
        )
    )
    url = tts._url()

    assert url.startswith("wss://api.elevenlabs.io/v1/text-to-speech/voice-1/stream-input?")
    assert "model_id=eleven_flash_v2_5" in url
    assert "output_format=pcm_24000" in url
    assert tts.sample_rate == 24_000
    assert tts.output_format == "pcm_24000"


def test_elevenlabs_output_format_drives_sample_rate():
    config = ElevenLabsSettings(
        _env_file=None, api_key="key", voice_id="v", output_format="pcm_16000"
    )
    assert ElevenLabsStreamingTTS(config).sample_rate == 16_000


def test_non_pcm_output_formats_are_rejected():
    """The browser client cannot decode mp3/ulaw, so fail fast at startup."""
    with pytest.raises(ValueError, match="ELEVENLABS_OUTPUT_FORMAT"):
        ElevenLabsSettings(_env_file=None, output_format="mp3_44100_128")
    with pytest.raises(ValueError, match="ELEVENLABS_OUTPUT_FORMAT"):
        ElevenLabsSettings(_env_file=None, output_format="ulaw_8000")


def test_chunk_schedule_accepts_csv_and_lists():
    assert ElevenLabsSettings(
        _env_file=None, chunk_schedule="50,120,200,300"
    ).chunk_schedule == [50, 120, 200, 300]
    assert ElevenLabsSettings(
        _env_file=None, chunk_schedule=[10, 20]
    ).chunk_schedule == [10, 20]


def test_chunk_schedule_rejects_the_api_limit():
    """ElevenLabs closes the socket with a 1008 above 500."""
    with pytest.raises(ValueError, match="between 1 and 500"):
        ElevenLabsSettings(_env_file=None, chunk_schedule="50,9999")
    with pytest.raises(ValueError, match="between 1 and 500"):
        ElevenLabsSettings(_env_file=None, chunk_schedule=[0])
    with pytest.raises(ValueError, match="must not be empty"):
        ElevenLabsSettings(_env_file=None, chunk_schedule="")


def test_turn_detection_blanks_are_treated_as_unset():
    """`VAR=` in a .env must mean "let AssemblyAI decide", not an empty string."""
    config = AssemblyAISettings(
        _env_file=None,
        api_key="key",
        min_turn_silence="",
        max_turn_silence="",
        end_of_turn_confidence_threshold="",
    )

    assert config.min_turn_silence is None
    assert config.max_turn_silence is None
    assert config.end_of_turn_confidence_threshold is None


def test_turn_detection_values_are_parsed():
    config = AssemblyAISettings(
        _env_file=None,
        api_key="key",
        min_turn_silence="350",
        max_turn_silence="2000",
    )

    assert config.min_turn_silence == 350
    assert config.max_turn_silence == 2000


def test_turn_grace_defaults_to_enough_time_for_a_natural_pause():
    """Below this, a thinking pause splits one utterance into two replies."""
    assert VoiceSettings(_env_file=None).turn_grace_ms == 500


def test_turn_grace_must_stay_in_a_sane_range():
    with pytest.raises(ValueError):
        VoiceSettings(_env_file=None, turn_grace_ms=-1)
    with pytest.raises(ValueError):
        VoiceSettings(_env_file=None, turn_grace_ms=99_999)


def test_transcript_utterance_defaults_to_empty_for_older_clients():
    payload = TranscriptPayload(text="hi", final=True)

    assert payload.utterance == ""
    assert payload.model_dump(by_alias=True)["utterance"] == ""
