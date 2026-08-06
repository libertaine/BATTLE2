"""Source and frozen command construction for BATTLE2 child applications."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from battle_engine.paths import is_frozen_application, normalize_root


def _packaged_executable(name: str) -> Path:
    executable_dir = normalize_root(Path(sys.executable).parent)
    filename = f"{name}.exe"
    candidates = (
        executable_dir / filename,
        executable_dir.parent / name / filename,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Packaged executable not found: {filename}. Checked: {checked}")


def build_match_command(arguments: Sequence[str]) -> list[str]:
    """Build a non-shell command for the primary BATTLE2 match interface."""
    options = list(arguments)
    if is_frozen_application():
        return [str(_packaged_executable("battle2")), "run", *options]
    return [str(normalize_root(sys.executable)), "-m", "battle_engine", "run", *options]


def build_replay_command(
    replay_path: Path, arguments: Sequence[str] = ()
) -> list[str]:
    """Build a non-shell command for the shared replay application."""
    replay = str(normalize_root(replay_path))
    options = list(arguments)
    if is_frozen_application():
        return [
            str(_packaged_executable("battle-replay-viewer")),
            "--replay",
            replay,
            *options,
        ]
    return [
        str(normalize_root(sys.executable)),
        "-m",
        "battle_client.cli",
        "--replay",
        replay,
        *options,
    ]
