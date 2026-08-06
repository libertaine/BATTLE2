from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from battle_engine.paths import get_data_root, get_resource_root


@dataclass
class DefaultPaths:
    root: Path
    replay_path: Path
    summary_path: Path


def get_battle_root() -> Path:
    """Return the writable data root (legacy public name)."""
    return get_data_root()

def pythonpath_separator() -> str:
    return ";" if os.name == "nt" else ":"

def get_client_assets_dir() -> str:
    """
    Return the first existing client assets directory, or empty string if none.
    Supports both classic and src-based layouts.
    """
    root = get_resource_root()
    candidates = [
        root / "client" / "assets",          # classic
        root / "client" / "src" / "assets",  # src-layout
        root / "client" / "resources",       # alt
        root / "app" / "assets",             # installed app package
        root / "assets",                     # fallback
    ]
    for p in candidates:
        if p.is_dir():
            return str(p)
    return ""

def get_default_paths(root: Path) -> DefaultPaths:
    root = root.expanduser().resolve()
    replay = root / "runs" / "_loose" / "replay.jsonl"
    summary = root / "runs" / "_loose" / "summary.json"
    return DefaultPaths(root=root, replay_path=replay, summary_path=summary)


def ensure_dirs(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_summary_json(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
