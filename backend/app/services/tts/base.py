"""Streaming text-to-speech abstraction."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class StreamingTTS(Protocol):
    """A single text-to-speech generation context.

    One instance produces the audio for one assistant turn: create it, call
    :meth:`start`, stream text in, :meth:`flush` when the text ends, consume
    :meth:`audio_chunks` until it is exhausted, then :meth:`aclose`.
    """

    async def start(self) -> None:
        """Open the synthesis context."""
        ...

    async def send_text(self, text: str) -> None:
        """Append text to the synthesis buffer."""
        ...

    async def flush(self) -> None:
        """Force generation of whatever text is still buffered."""
        ...

    async def finish(self) -> None:
        """Signal that no more text is coming.

        Must be called before draining :meth:`audio_chunks`, otherwise the
        generator never terminates (or truncates the tail of the audio).
        """
        ...

    def audio_chunks(self) -> AsyncIterator[bytes]:
        """Yield raw audio bytes in :attr:`output_format`."""
        ...

    async def aclose(self) -> None:
        """Terminate the context, releasing the provider connection."""
        ...

    @property
    def output_format(self) -> str:
        """Encoding of the yielded bytes, e.g. ``pcm_24000``."""
        ...

    @property
    def sample_rate(self) -> int:
        ...
