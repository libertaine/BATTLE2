from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

from battle_engine.replay import ReplayRecord, iter_replay

def iter_jsonl(path: Path) -> Iterator[ReplayRecord]:
    """
    Stream canonical replay records, adapting supported v0.1 shapes at this
    boundary before renderers see them.
    """
    yield from iter_replay(path)

def maybe_load_summary(replay_path: Path) -> Optional[Dict[str, Any]]:
    """
    Try to locate a sibling summary.json for convenience. Returns None if missing.
    """
    candidate = replay_path.parent / "summary.json"
    if candidate.exists():
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
            # Normalize historical metadata locations once, before presentation.
            return {
                "arena": raw.get("arena") or raw.get("arena_size") or params.get("arena"),
                "ticks": raw.get("ticks") or params.get("ticks") or params.get("ticks_run"),
                "agents": raw.get("agents", {}),
            }
        except Exception:
            return None
    return None

def paced(iterable: Iterable[ReplayRecord], tick_delay: float | None) -> Iterator[ReplayRecord]:
    """
    Optionally pace events by sleeping tick_delay seconds per event.
    """
    if not tick_delay or tick_delay <= 0:
        yield from iterable
        return
    for ev in iterable:
        yield ev
        time.sleep(tick_delay)
