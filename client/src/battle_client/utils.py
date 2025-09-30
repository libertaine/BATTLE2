from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    """
    Stream JSONL events from file. If battle_engine provides a helper,
    we try to use it for compatibility; otherwise fall back to plain JSONL.
    """
    # Optional fast-path if engine exposes a JSONL reader
    try:
        # Example: engine might export JSONLSink / JSONLSource style APIs.
        # We only import lazily and fail open to plain JSONL.
        from battle_engine import jsonl  # type: ignore[attr-defined]
        # Expect an API like jsonl.iter_events(path) -> Iterator[dict]
        if hasattr(jsonl, "iter_events"):
            for ev in jsonl.iter_events(str(path)):
                yield ev
            return
    except Exception:
        pass

    # Portable fallback
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)

def maybe_load_summary(replay_path: Path) -> Optional[Dict[str, Any]]:
    """
    Try to locate a sibling summary.json for convenience. Returns None if missing.
    """
    candidate = replay_path.parent / "summary.json"
    if candidate.exists():
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def paced(iterable: Iterable[Dict[str, Any]], tick_delay: float | None) -> Iterator[Dict[str, Any]]:
    """
    Optionally pace events by sleeping tick_delay seconds per event.
    """
    if not tick_delay or tick_delay <= 0:
        yield from iterable
        return
    for ev in iterable:
        yield ev
        time.sleep(tick_delay)
