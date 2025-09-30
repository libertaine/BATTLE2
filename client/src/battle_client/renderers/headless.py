from __future__ import annotations
import sys
from typing import Any, Dict, Optional
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
        self._agents = {}

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

    def on_event(self, event: Dict[str, Any]) -> None:
        et = event.get("type")
        tick = event.get("tick")
        who = event.get("who")
        if et == "spawn":
            pos = event.get("pos")
            self._println(tick, f"SPAWN who={who} pos={pos}")
        elif et == "move":
            frm = event.get("from")
            to = event.get("to")
            self._println(tick, f"MOVE  who={who} {frm}->{to}")
        elif et in ("death", "die"):
            cause = event.get("cause")
            self._println(tick, f"DEATH who={who} cause={cause}")
        elif et in ("territory", "claim"):
            cells = event.get("cells") or event.get("count")
            self._println(tick, f"TERR  who={who} +cells={cells}")
        elif et in ("score", "tick"):
            # Some engines emit periodic score or heartbeat events
            payload = {k: v for k, v in event.items() if k not in ("type", "tick")}
            self._println(tick, f"{et.upper()} {payload}")
        else:
            # Unknown event type: keep visible for debugging
            self._println(tick, f"EVENT {event}")

    def teardown(self) -> None:
        self._println(None, "END")
        self._out.flush()

    def _println(self, tick, msg: str) -> None:
        if tick is None:
            self._out.write(f"[    ] {msg}\n")
        else:
            self._out.write(f"[{tick:04d}] {msg}\n")
        # Do not flush on every line for performance; rely on OS or final flush.
