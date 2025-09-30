from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

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

    @abstractmethod
    def on_event(self, event: Dict[str, Any]) -> None:
        """
        Receive a single decoded event dictionary from replay.jsonl.
        Typical fields include 'type', 'tick', 'who', 'pos', etc.
        """
        ...

    def teardown(self) -> None:
        """
        Called once after stream ends (or on error).
        """
        pass
