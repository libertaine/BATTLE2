from __future__ import annotations
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class DefaultPaths:
    root: Path
    replay_path: Path
    summary_path: Path

def get_battle_root() -> Optional[Path]:
    """Resolve <BATTLE_ROOT>.

    Order:
      1) PyInstaller bundle root (when frozen)
      2) env BATTLE_ROOT
      3) parent of this file's parent (assumes app/* layout)
      4) CWD
    """
    # 1) Frozen bundle (PyInstaller)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]

    # 2) Explicit override
    env = os.environ.get("BATTLE_ROOT")
    if env:
        return Path(env).resolve()

    # 3) Repo root: app/services/osutil.py -> app/ -> <root>
    here = Path(__file__).resolve()
    root = here.parents[2]
    if (root / "engine").exists() and (root / "client").exists():
        return root

    # 4) Fallback
    return Path.cwd()

def pythonpath_separator() -> str:
    return ";" if os.name == "nt" else ":"

def get_client_assets_dir() -> str:
    """
    Return the first existing client assets directory, or empty string if none.
    Supports both classic and src-based layouts.
    """
    root = get_battle_root()
    if root is None:
        return ""
    candidates = [
        root / "client" / "assets",          # classic
        root / "client" / "src" / "assets",  # src-layout
        root / "client" / "resources",       # alt
        root / "assets",                     # fallback
    ]
    for p in candidates:
        if p.is_dir():
            return str(p)
    return ""

def get_default_paths(root: Path) -> DefaultPaths:
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
