"""Standalone AssemblyAI streaming demo (the former ``app/api/routes/voice.py``).

Transcribes a live AAC internet radio stream so it can be run without a
microphone. Handy for verifying the API key and the SDK in isolation::

    uv run python scripts/transcribe_demo.py
"""

from __future__ import annotations

import os
import time

import requests
from assemblyai.streaming.v3 import (
    BeginEvent,
    Encoding,
    RealTimeError,
    RealTimeEvents,
    RealTimeParameters,
    RealTimeTranscriber,
    RealTimeTranscriberOptions,
    TerminationEvent,
    TurnEvent,
)

STREAM_URL = "https://14123.live.streamtheworld.com/WBBRAMAAC.aac"
RUN_SECONDS = 25


def on_begin(_client: RealTimeTranscriber, event: BeginEvent) -> None:
    print(f"Session started: {event.id}")


def on_turn(_client: RealTimeTranscriber, event: TurnEvent) -> None:
    if event.transcript:
        print(event.transcript)


def on_terminated(_client: RealTimeTranscriber, event: TerminationEvent) -> None:
    print(f"Terminated after {event.audio_duration_seconds}s of audio")


def on_error(_client: RealTimeTranscriber, error: RealTimeError) -> None:
    print(f"Error: {error}")


def main() -> None:
    client = RealTimeTranscriber(
        RealTimeTranscriberOptions(terminate_timeout=30.0),
        api_key=os.environ["ASSEMBLYAI_API_KEY"],
    )
    client.on(RealTimeEvents.Begin, on_begin)
    client.on(RealTimeEvents.Turn, on_turn)
    client.on(RealTimeEvents.Termination, on_terminated)
    client.on(RealTimeEvents.Error, on_error)

    client.connect(
        RealTimeParameters(speech_model="universal-3-6-pro", encoding=Encoding.aac)
    )

    response = requests.get(STREAM_URL, stream=True, timeout=30)
    deadline = time.time() + RUN_SECONDS
    try:
        for chunk in response.iter_content(chunk_size=4096):
            client.stream(chunk)
            if time.time() > deadline:
                break
    finally:
        response.close()
        client.disconnect(terminate=True)


if __name__ == "__main__":
    main()
