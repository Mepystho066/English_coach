from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent

from app.agents.deps import AgentDeps
from app.learning.models import (
    Analysis,
    AnalysisCorrection,
    AnalysisVocabulary,
    LearningState,
)
from app.learning.service import LearningService
from app.learning.store import InMemoryLearningStore, SqliteLearningStore
from app.main import create_app

FIX = AnalysisCorrection(
    original="I go yesterday",
    corrected="I went yesterday",
    explanation="Pasado simple.",
    category="grammar",
)
WORD = AnalysisVocabulary(term="groceries", meaning="compras", example="I bought groceries.")


def _service(analysis: Analysis | None, **kwargs) -> tuple[LearningService, list[str]]:
    seen: list[str] = []

    async def analyze(text: str) -> Analysis | None:
        seen.append(text)
        return analysis

    return LearningService(InMemoryLearningStore(), analyze, **kwargs), seen


async def test_record_turn_stores_corrections_vocabulary_and_progress():
    service, _ = _service(Analysis(corrections=[FIX], vocabulary=[WORD]))

    state = await service.record_turn("t1", "I go yesterday to the market")

    assert state is not None
    assert state.turns == 1
    assert state.corrections[0].corrected == "I went yesterday"
    assert state.corrections[0].source == "I go yesterday to the market"
    assert state.vocabulary[0].term == "groceries"
    assert state.progress.corrections == 1
    assert state.progress.by_category["grammar"] == 1
    assert (await service.get_state("t1")).progress.vocabulary == 1


async def test_repeated_items_are_not_duplicated_but_turns_keep_counting():
    service, _ = _service(Analysis(corrections=[FIX], vocabulary=[WORD]))

    await service.record_turn("t1", "I go yesterday to the market")
    state = await service.record_turn("t1", "I go yesterday again, my friend")

    assert state is not None
    assert state.turns == 2
    assert len(state.corrections) == 1
    assert len(state.vocabulary) == 1


async def test_no_op_corrections_are_dropped():
    same = AnalysisCorrection(
        original="Hello there", corrected="hello there", explanation="x", category="grammar"
    )
    service, _ = _service(Analysis(corrections=[same]))

    state = await service.record_turn("t1", "Hello there my friend")

    assert state is not None and state.corrections == []


async def test_single_word_turns_skip_the_analyzer_but_count():
    service, seen = _service(Analysis(corrections=[FIX]))

    state = await service.record_turn("t1", "Hello")

    assert seen == []
    assert state is not None and state.turns == 1 and state.corrections == []


async def test_failed_analysis_still_counts_the_turn():
    service, _ = _service(None)

    state = await service.record_turn("t1", "I am very tired today")

    assert state is not None and state.turns == 1


async def test_disabled_service_records_nothing():
    service = LearningService(InMemoryLearningStore(), None)

    assert not service.enabled
    assert await service.record_turn("t1", "I go yesterday") is None
    assert (await service.get_state("t1")).turns == 0


async def test_quotes_around_model_output_are_removed():
    quoted = AnalysisVocabulary(
        term='"groceries"', meaning='"compras"', example='"I bought groceries."'
    )
    service, _ = _service(Analysis(vocabulary=[quoted]))

    state = await service.record_turn("t1", "I need to buy some food")

    assert state is not None
    assert state.vocabulary[0].term == "groceries"
    assert state.vocabulary[0].meaning == "compras"
    assert state.vocabulary[0].example == "I bought groceries."


async def test_lists_are_capped():
    service, _ = _service(None, max_corrections=2)
    for index in range(4):
        analysis = Analysis(
            corrections=[
                AnalysisCorrection(
                    original=f"bad {index}",
                    corrected=f"good {index}",
                    explanation="x",
                    category="grammar",
                )
            ]
        )
        service._analyze = (lambda a: (lambda _t: _async(a)))(analysis)  # noqa: SLF001
        await service.record_turn("t1", "some words here")

    state = await service.get_state("t1")
    assert [c.corrected for c in state.corrections] == ["good 2", "good 3"]


async def _async(value):
    return value


async def test_sqlite_learning_store_survives_reopen(tmp_path):
    path = tmp_path / "s.db"
    store = SqliteLearningStore(path)
    state = LearningState(turns=3)
    await store.set("t1", state)
    await store.aclose()

    reopened = SqliteLearningStore(path)
    assert (await reopened.get("t1")).turns == 3
    assert (await reopened.get("other")).turns == 0
    await reopened.clear("t1")
    assert (await reopened.get("t1")).turns == 0
    await reopened.aclose()


def test_state_endpoint_and_delete_clear_learning(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        service, _ = _service(Analysis(corrections=[FIX]))
        app.state.learning = service
        client.portal.call(service.record_turn, "t1", "I go yesterday to school")

        body = client.get("/api/v1/threads/t1/state").json()
        assert body["turns"] == 1
        assert body["corrections"][0]["original"] == "I go yesterday"
        assert body["progress"]["corrections"] == 1

        assert client.delete("/api/v1/threads/t1").status_code == 204
        assert client.get("/api/v1/threads/t1/state").json()["turns"] == 0


def test_chat_stream_carries_a_state_snapshot_before_run_finished(
    test_settings, agent: Agent[AgentDeps, str]
):
    app = create_app(test_settings)
    body = {
        "threadId": "t-snap",
        "runId": "r1",
        "messages": [{"id": "m1", "role": "user", "content": "I go yesterday to school"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    with TestClient(app) as client:
        app.state.agent = agent
        app.state.learning, _ = _service(Analysis(corrections=[FIX], vocabulary=[WORD]))
        text = client.post("/api/v1/chat", json=body).text

    events = [
        json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
    ]
    types = [event["type"] for event in events]
    assert "STATE_SNAPSHOT" in types
    assert types.index("STATE_SNAPSHOT") < types.index("RUN_FINISHED")
    snapshot = events[types.index("STATE_SNAPSHOT")]["snapshot"]
    assert snapshot["corrections"][0]["corrected"] == "I went yesterday"
    assert snapshot["vocabulary"][0]["term"] == "groceries"


def test_chat_without_learning_has_no_snapshot(test_settings, agent: Agent[AgentDeps, str]):
    app = create_app(test_settings)
    body = {
        "threadId": "t-off",
        "runId": "r1",
        "messages": [{"id": "m1", "role": "user", "content": "Hello coach"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    with TestClient(app) as client:
        app.state.agent = agent
        text = client.post("/api/v1/chat", json=body).text

    assert "STATE_SNAPSHOT" not in text
    assert "RUN_FINISHED" in text


@pytest.mark.parametrize("path", ["state"])
def test_state_endpoint_is_empty_for_unknown_threads(test_settings, path):
    with TestClient(create_app(test_settings)) as client:
        body = client.get(f"/api/v1/threads/never/{path}").json()
    assert body["turns"] == 0 and body["corrections"] == []
