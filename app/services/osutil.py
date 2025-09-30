from __future__ import annotations
import json
import os
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

    Order: env BATTLE_ROOT -> parent of this file's parent (assumes app/* layout) -> CWD
    """
    env = os.environ.get("BATTLE_ROOT")
    if env:
        p = Path(env).resolve()
        return p
    # Assuming app/services/osutil.py -> app/ -> <root>
    here = Path(__file__).resolve()
    root = here.parents[2]  # <root>
    if (root / "engine").exists() and (root / "client").exists():
        return root
    return Path.cwd()


def pythonpath_separator() -> str:
    return ";" if os.name == "nt" else ":"


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
