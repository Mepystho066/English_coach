"""Voice WebSocket endpoint backed by Pipecat.

The browser connects with ``@pipecat-ai/client-js`` over Pipecat's protobuf
WebSocket transport. One connection maps to one conversation thread; the thread
is also used by the AG-UI chat endpoint, so history moves between both channels.
"""

from __future__ import annotations

import logging
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import Settings
from app.services.voice.pipecat_pipeline import run_voice_session
from app.sessions.store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.websocket("/{thread_id}")
async def voice(websocket: WebSocket, thread_id: str) -> None:
    config: Settings = websocket.app.state.settings

    await websocket.accept()
    logger.info("Voice session opened (thread=%s)", thread_id)

    if not config.assemblyai.is_configured:
        logger.error("Rejecting voice session: ASSEMBLYAI_API_KEY is not set")
        await websocket.close(code=1011, reason="assemblyai_not_configured")
        return
    if not config.elevenlabs.is_configured:
        logger.error("Rejecting voice session: ElevenLabs is not configured")
        await websocket.close(code=1011, reason="elevenlabs_not_configured")
        return

    store: SessionStore = websocket.app.state.store
    lock = store.lock(thread_id)
    await lock.acquire()
    try:
        await run_voice_session(
            websocket=websocket,
            config=config,
            store=store,
            thread_id=thread_id,
            learning=websocket.app.state.learning,
        )
    except WebSocketDisconnect:
        logger.debug("Voice client disconnected (thread=%s)", thread_id)
    except Exception:
        logger.exception("Voice session crashed (thread=%s)", thread_id)
        with suppress(Exception):
            await websocket.close(code=1011, reason="voice_session_failed")
    finally:
        if lock.locked():
            lock.release()
        logger.info("Voice session closed (thread=%s)", thread_id)
