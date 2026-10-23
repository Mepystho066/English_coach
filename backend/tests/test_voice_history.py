"""Tests for translating between the chat store and Pipecat's context."""

from __future__ import annotations

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart

from app.services.voice.history import to_llm_messages, to_model_messages


def test_to_llm_messages_extracts_text_turns():
    history = [
        ModelRequest.user_text_prompt("Hello"),
        ModelResponse(parts=[TextPart("Hi there")]),
    ]

    assert to_llm_messages(history) == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]


def test_to_llm_messages_skips_tools_and_blank_turns():
    history = [
        ModelRequest.user_text_prompt("   "),
        ModelResponse(parts=[ToolCallPart("get_current_datetime", {})]),
        ModelResponse(parts=[TextPart("  ")]),
    ]

    assert to_llm_messages(history) == []


def test_round_trip_preserves_the_conversation():
    messages = [
        {"role": "user", "content": "I went to the beach"},
        {"role": "assistant", "content": "Nice! What did you do there?"},
    ]

    history = to_model_messages(messages)

    assert [type(message) for message in history] == [ModelRequest, ModelResponse]
    assert to_llm_messages(history) == messages


def test_to_model_messages_ignores_system_and_unknown_roles():
    history = to_model_messages(
        [
            {"role": "system", "content": "instructions"},
            {"role": "tool", "content": "result"},
            {"role": "user", "content": "hello"},
        ]
    )

    assert len(history) == 1
    assert isinstance(history[0], ModelRequest)
