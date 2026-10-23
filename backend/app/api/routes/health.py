"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_settings
from app.core.config import Settings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(config: Settings = Depends(get_settings)) -> dict[str, object]:
    """Liveness plus a note of which optional providers are configured."""
    return {
        "status": "ok",
        "env": config.app.env,
        "providers": {
            "llm": {
                "base_url": config.llm.base_url,
                "model": config.llm.base_model,
            },
            "stt": {
                "provider": "assemblyai",
                "configured": config.assemblyai.is_configured,
            },
            "tts": {
                "provider": "elevenlabs",
                "configured": config.elevenlabs.is_configured,
            },
        },
    }
