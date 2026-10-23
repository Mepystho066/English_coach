"""Translation between the chat store and Pipecat's LLM context.

The chat channel stores prompt-ai ``ModelMessage`` objects; Pipecat works with
plain OpenAI-style dictionaries (``{"role": ..., "content": ...}``). Both
channels share the same ``SessionStore`` so a conversation can move from text
to voice and back.

Only user and assistant *text* turns are translated. System prompts are rebuilt
on every session and tool traffic is skipped: the voice tool
(``get_current_datetime``) is stateless, so replaying its calls adds tokens
without adding context.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

LLMMessage = dict[str, Any]


def to_llm_messages(history: list[ModelMessage]) -> list[LLMMessage]:
    """Convert stored prompt-ai history into Pipecat/OpenAI messages."""
    messages: list[LLMMessage] = []
    for message in history:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    text = part.content.strip()
                    if text:
                        messages.append({"role": "user", "content": text})
        elif isinstance(message, ModelResponse):
            text = "".join(
                part.content for part in message.parts if isinstance(part, TextPart)
            ).strip()
            if text:
                messages.append({"role": "assistant", "content": text})
    return messages


def to_model_messages(messages: list[LLMMessage]) -> list[ModelMessage]:
    """Convert Pipecat messages back into prompt-ai history."""
    history: list[ModelMessage] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        if role == "user":
            history.append(ModelRequest.user_text_prompt(text))
        elif role == "assistant":
            history.append(ModelResponse(parts=[TextPart(text)]))
    return history


__all__ = ["LLMMessage", "to_llm_messages", "to_model_messages"]
