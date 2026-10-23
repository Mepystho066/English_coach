"""Unit tests for the TTS chunker (pure, no I/O)."""

from __future__ import annotations

from app.services.voice.pipeline import _MAX_TTS_BUFFER, _split_for_tts


def test_splits_on_sentence_boundary():
    ready, remaining = _split_for_tts("Hello there. How are you? I am", force=False)
    assert ready == "Hello there. How are you? "
    assert remaining == "I am"


def test_waits_without_boundary():
    ready, remaining = _split_for_tts("Hello there how are", force=False)
    assert ready == ""
    assert remaining == "Hello there how are"


def test_force_flushes_the_tail():
    ready, remaining = _split_for_tts("Hello there", force=True)
    assert ready == "Hello there"
    assert remaining == ""


def test_force_on_blank_buffer_is_a_noop():
    ready, remaining = _split_for_tts("   ", force=True)
    assert ready == ""
    assert remaining == "   "


def test_splits_on_length_without_punctuation():
    text = ("word " * (_MAX_TTS_BUFFER // 5 + 5)).strip()
    ready, remaining = _split_for_tts(text, force=False)
    assert ready
    assert ready.endswith(" ")
    assert ready + remaining == text
