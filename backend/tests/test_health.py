from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_configured_providers(test_settings):
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["providers"]["stt"] == {"provider": "assemblyai", "configured": True}
    assert body["providers"]["tts"] == {"provider": "elevenlabs", "configured": True}


def test_health_reports_unconfigured_providers():
    from app.core.config import (
        AppSettings,
        AssemblyAISettings,
        ElevenLabsSettings,
        Settings,
    )

    config = Settings(
        assemblyai=AssemblyAISettings(_env_file=None),
        elevenlabs=ElevenLabsSettings(_env_file=None),
        app=AppSettings(_env_file=None),
    )
    with TestClient(create_app(config)) as client:
        body = client.get("/health").json()

    assert body["providers"]["stt"]["configured"] is False
    assert body["providers"]["tts"]["configured"] is False
