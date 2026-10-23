"""Tests for the configuration the voice pipeline depends on."""

from __future__ import annotations

import pytest

from app.core.config import AssemblyAISettings, ElevenLabsSettings, VoiceSettings


def test_voice_input_rate_is_the_single_source_of_truth():
    config = VoiceSettings(_env_file=None)

    assert config.input_sample_rate == 16_000
    # The output rate is derived from ELEVENLABS_OUTPUT_FORMAT now.
    assert not hasattr(config, "output_sample_rate")


def test_elevenlabs_output_format_drives_the_sample_rate():
    config = ElevenLabsSettings(
        _env_file=None,
        api_key="key",
        voice_id="voice",
        output_format="pcm_24000",
    )

    assert config.sample_rate == 24_000


def test_non_pcm_output_formats_are_rejected():
    """The browser client cannot decode mp3/ulaw, so fail fast at startup."""
    with pytest.raises(ValueError, match="ELEVENLABS_OUTPUT_FORMAT"):
        ElevenLabsSettings(_env_file=None, output_format="mp3_44100_128")
    with pytest.raises(ValueError, match="ELEVENLABS_OUTPUT_FORMAT"):
        ElevenLabsSettings(_env_file=None, output_format="ulaw_8000")


def test_turn_detection_blanks_are_treated_as_unset():
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


def test_voice_requires_both_assemblyai_and_elevenlabs_credentials(test_settings):
    assert test_settings.assemblyai.is_configured
    assert test_settings.elevenlabs.is_configured
