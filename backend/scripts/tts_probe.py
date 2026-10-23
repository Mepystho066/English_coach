"""Probe the real audio format ElevenLabs returns for our stream-input call.

Fetches one phrase as ``pcm_24000`` and writes **the same bytes twice**, as two
WAV files that differ only in the declared sample rate:

* ``tts_probe_24000.wav`` - header says 24000 Hz (what we request)
* ``tts_probe_48000.wav`` - header says 48000 Hz (chipmunk, x2)

Play both. Whichever sounds like a normal human voice tells you the true rate
of the data ElevenLabs sends, without trusting any timing metadata.

Usage::

    uv run python scripts/tts_probe.py [output_dir]
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import wave
from pathlib import Path
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from app.core.config import settings

PHRASE = "Hello, this is a short test of the speech rate. I hope it sounds normal."
REQUESTED_FORMAT = "pcm_24000"
ALT_DECLARED_RATES = (24_000, 48_000)


async def fetch(format_name: str) -> bytes:
    """Return the raw PCM bytes ElevenLabs sends for ``format_name``."""
    config = settings.elevenlabs
    if not config.is_configured:
        raise SystemExit("ElevenLabs is not configured in .env (need key + voice_id)")

    query = urlencode(
        {
            "model_id": config.model_id,
            "output_format": format_name,
            "auto_mode": "true",
        }
    )
    url = (
        f"{config.base_url}/v1/text-to-speech/{config.voice_id}"
        f"/stream-input?{query}"
    )

    audio = bytearray()
    async with connect(
        url,
        additional_headers={"xi-api-key": config.api_key.get_secret_value()},
        open_timeout=30,
        max_size=None,
        ping_interval=None,
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "text": " ",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "use_speaker_boost": True,
                    },
                    "generation_config": {
                        "chunk_length_schedule": config.chunk_schedule
                    },
                }
            )
        )
        await ws.send(json.dumps({"text": PHRASE}))
        await ws.send(json.dumps({"text": " ", "flush": True}))
        await ws.send(json.dumps({"text": ""}))

        async for raw in ws:
            payload = json.loads(raw)
            if error := payload.get("error"):
                raise SystemExit(f"ElevenLabs error: {error}")
            if chunk := payload.get("audio"):
                audio.extend(base64.b64decode(chunk))
            if payload.get("isFinal"):
                break

    return bytes(audio)


def write_wav(path: Path, pcm: bytes, rate: int) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)


async def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/opencode")
    out_dir.mkdir(parents=True, exist_ok=True)

    config = settings.elevenlabs
    print(f"voice_id         : {config.voice_id}")
    print(f"model_id         : {config.model_id}")
    print(f"requested format : {REQUESTED_FORMAT}")
    print(f"phrase           : {PHRASE!r}")

    pcm = await fetch(REQUESTED_FORMAT)
    bytes_per_sample = 2
    samples = len(pcm) // bytes_per_sample
    print(f"\nreceived         : {len(pcm)} bytes = {samples} samples (PCM16 mono)")

    for rate in ALT_DECLARED_RATES:
        path = out_dir / f"tts_probe_{rate}.wav"
        write_wav(path, pcm, rate)
        print(f"  {path}   declares {rate} Hz -> {samples / rate:.2f} s")

    print(
        "\nPlay both files. The one that sounds like a normal human voice "
        "reveals the real rate."
    )
    print("  aplay " + str(out_dir / "tts_probe_24000.wav"))
    print("  aplay " + str(out_dir / "tts_probe_48000.wav"))


if __name__ == "__main__":
    asyncio.run(main())
