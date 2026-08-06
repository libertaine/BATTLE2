from __future__ import annotations
import sys
from typing import Any, Dict, Optional
from battle_engine.replay import (
    AgentEvent,
    KillDeathEvent,
    MatchResult,
    ReplayHeader,
    ReplayRecord,
    TickSnapshot,
)
from .base import AbstractRenderer


class HeadlessRenderer(AbstractRenderer):
    """
    Minimal text renderer for debugging/logging.
    Prints one line per event with stable, grep-friendly formatting.
    """

    def __init__(self, stream=None) -> None:
        super().__init__()
        self._out = stream or sys.stdout
        self._arena = None
        self._agents: Dict[str, Any] = {}

    def setup(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        super().setup(metadata)
        if not metadata:
            return
        self._arena = metadata.get("arena")
        self._agents = metadata.get("agents", {})
        # Header
        self._out.write("[BATTLE:HEADLESS] start")
        if self._arena:
            self._out.write(f" arena={self._arena}")
        if self._agents:
            self._out.write(f" agents={self._agents}")
        self._out.write("\n")
        self._out.flush()

    def on_event(self, record: ReplayRecord) -> None:
        if isinstance(record, ReplayHeader):
            self._println(0, f"HEADER arena={record.config.arena_size}")
            return
        if isinstance(record, MatchResult):
            self._println(record.ticks, f"RESULT winner={record.winner or 'tie'} score={dict(record.score)}")
            return

        self._println(record.tick, f"TICK score={dict(record.score)} agents={len(record.agents)}")
        for event in record.events:
            if isinstance(event, KillDeathEvent):
                self._println(record.tick, f"{event.event_type.upper()} victim={event.victim} killer={event.killer}")
            elif isinstance(event, AgentEvent):
                cells = list(event.cells) if event.cells else event.cell_count
                self._println(record.tick, f"{event.event_type.upper()} who={event.agent_id} pos={event.position} cells={cells}")

    def teardown(self) -> None:
        self._println(None, "END")
        self._out.flush()

    def _println(self, tick, msg: str) -> None:
        if tick is None:
            self._out.write(f"[    ] {msg}\n")
        else:
            self._out.write(f"[{tick:04d}] {msg}\n")
        # Do not flush on every line for performance; rely on OS or final flush.
