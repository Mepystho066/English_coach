from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart

from app.main import create_app
from app.sessions.store import SqliteSessionStore

HISTORY = [
    ModelRequest.user_text_prompt("Hello"),
    ModelResponse(parts=[TextPart("Hi there")]),
]


async def test_sqlite_store_round_trips_and_survives_reopen(tmp_path):
    path = tmp_path / "nested" / "sessions.db"
    store = SqliteSessionStore(path)
    await store.set_history("t1", HISTORY)
    await store.aclose()

    reopened = SqliteSessionStore(path)
    history = await reopened.get_history("t1")

    assert [type(m) for m in history] == [ModelRequest, ModelResponse]
    assert await reopened.get_history("unknown") == []
    await reopened.aclose()


async def test_sqlite_store_append_clear_and_trim(tmp_path):
    store = SqliteSessionStore(tmp_path / "s.db", max_messages=2)
    for text in ("a", "b", "c"):
        await store.append("t1", ModelRequest.user_text_prompt(text))

    assert len(await store.get_history("t1")) == 2

    await store.clear("t1")
    assert await store.get_history("t1") == []
    await store.aclose()


def test_threads_endpoints_list_and_delete(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        client.portal.call(app.state.store.set_history, "t1", HISTORY)

        listed = client.get("/api/v1/threads/t1/messages")
        assert listed.status_code == 200
        assert listed.json()["messages"] == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        assert client.delete("/api/v1/threads/t1").status_code == 204
        assert client.get("/api/v1/threads/t1/messages").json()["messages"] == []
