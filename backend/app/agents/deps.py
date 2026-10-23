"""Dependencies injected into agent runs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDeps:
    """Per-run dependencies available to tools and dynamic instructions.

    Kept intentionally small for the first block; add request-scoped services
    (repositories, per-user clients, ...) here as the app grows.
    """

    thread_id: str = "default"
    # Channel the run is happening on, so tools/instructions can adapt
    # (e.g. shorter answers for voice).
    channel: str = "chat"
    metadata: dict[str, str] = field(default_factory=dict)
