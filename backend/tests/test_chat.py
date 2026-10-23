from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic_ai import Agent

from app.agents.deps import AgentDeps
from app.main import create_app

RUN_BODY = {
    "threadId": "thread-1",
    "runId": "run-1",
    "messages": [
        {"id": "msg-1", "role": "user", "content": "Hello coach, I am learning English."}
    ],
    "tools": [],
    "context": [],
    "forwardedProps": {},
}


def _post_chat(client: TestClient, body: dict) -> object:
    return client.post("/api/v1/chat", json=body)


def test_chat_streams_ag_ui_sse(test_settings, agent: Agent[AgentDeps, str]):
    app = create_app(test_settings)
    with TestClient(app) as client:
        app.state.agent = agent
        response = _post_chat(client, RUN_BODY)
        history = app.state.store._sessions["thread-1"].messages

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "RUN_STARTED" in body
    assert "TEXT_MESSAGE_START" in body
    assert "TEXT_MESSAGE_CONTENT" in body
    assert "How was your day?" in body
    assert "RUN_FINISHED" in body
    assert history, "conversation history should be persisted after the run"


def test_chat_history_is_reused_across_turns(
    test_settings, agent: Agent[AgentDeps, str]
):
    app = create_app(test_settings)
    with TestClient(app) as client:
        app.state.agent = agent
        _post_chat(client, RUN_BODY)
        first_len = len(app.state.store._sessions["thread-1"].messages)

        second = dict(RUN_BODY, runId="run-2")
        second["messages"] = [
            {"id": "msg-2", "role": "user", "content": "And what about tomorrow?"}
        ]
        response = _post_chat(client, second)
        second_len = len(app.state.store._sessions["thread-1"].messages)

    assert response.status_code == 200
    assert second_len > first_len
