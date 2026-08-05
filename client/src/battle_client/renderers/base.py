from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from battle_engine.replay import ReplayRecord


class RendererDependencyError(RuntimeError):
    """A selected renderer's optional dependency is not installed."""

class AbstractRenderer(ABC):
    """
    Renderer interface for BATTLE Client.
    Implementations should be *presentation only*; no game logic.
    """

    def __init__(self) -> None:
        self._initialized = False

    def setup(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Called once before events stream. `metadata` may include:
          - 'arena' (int), 'ticks' (int), 'params' (dict), 'agents' (dict), etc.
          - any fields found in summary.json or first replay events.
        """
        self._initialized = True

    def wait_for_start(self) -> None:
        """Optional interactive gate before replay delivery begins."""

    def wait_until_ready(self) -> None:
        """Block or pump frames until one logical replay record may be delivered."""

    @abstractmethod
    def on_event(self, event: ReplayRecord) -> None:
        """
        Receive one canonical replay model. Compatibility conversion has already
        happened at the replay-reader boundary.
        """
        ...

    def update(self) -> None:
        """Process one presentation frame for embedded/live integrations."""

    def on_complete(self) -> None:
        """Notify the renderer that replay iteration completed normally."""

    def hold_open(self) -> None:
        """Optionally keep an interactive presentation open after completion."""

    def teardown(self) -> None:
        """
        Called once after stream ends (or on error).
        """
        pass
