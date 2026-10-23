"""Voice WebSocket endpoint.

One connection per conversation thread. Supports two client styles:

* **Duplex voice** - send PCM16 audio as binary frames, receive AG-UI events as
  text frames plus PCM16 audio as binary frames.
* **Text over the voice channel** - send ``{"type": "text", "text": "..."}`` to
  exercise the same pipeline (agent + TTS) without a microphone.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic_ai import Agent

from app.agents.deps import AgentDeps
from app.api.deps import get_agent_ws, get_store_ws
from app.core.config import Settings
from app.schemas.voice import SessionEndPayload, VoiceCustomEvent
from app.services.stt.base import StreamingSTT
from app.services.tts.base import StreamingTTS
from app.services.voice.pipeline import VoiceSession
from app.sessions.store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


async def _reject(websocket: WebSocket, reason: str) -> None:
    await websocket.send_json(
        {
            "type": "CUSTOM",
            "name": VoiceCustomEvent.SESSION_END.value,
            "value": SessionEndPayload(reason=reason).model_dump(by_alias=True),
        }
    )
    await websocket.close(code=1011)


@router.websocket("/{thread_id}")
async def voice(websocket: WebSocket, thread_id: str) -> None:
    await websocket.accept()
    logger.info("Voice session opened (thread=%s)", thread_id)

    config: Settings = websocket.app.state.settings
    if not config.assemblyai.is_configured:
        await _reject(websocket, "assemblyai_not_configured")
        return
    if not config.elevenlabs.is_configured:
        await _reject(websocket, "elevenlabs_not_configured")
        return

    agent: Agent[AgentDeps, str] = get_agent_ws(websocket)
    store: SessionStore = get_store_ws(websocket)
    build_stt: Callable[[Settings], StreamingSTT] = websocket.app.state.stt_factory
    build_tts: Callable[[Settings], StreamingTTS] = websocket.app.state.tts_factory

    session = VoiceSession(
        websocket=websocket,
        agent=agent,
        store=store,
        settings=config,
        thread_id=thread_id,
        stt=build_stt(config),
        tts_factory=lambda: build_tts(config),
    )

    try:
        await session.run()
    except WebSocketDisconnect:
        logger.debug("Voice client disconnected (thread=%s)", thread_id)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Voice session crashed (thread=%s)", thread_id)
    finally:
        logger.info("Voice session closed (thread=%s)", thread_id)
