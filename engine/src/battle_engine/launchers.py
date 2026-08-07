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


def build_tournament_command(arguments: Sequence[str]) -> list[str]:
    """Build a non-shell command for the supported tournament interface."""
    options = list(arguments)
    if is_frozen_application():
        return [str(_packaged_executable("battle2")), "tournament", *options]
    return [
        str(normalize_root(sys.executable)),
        "-m",
        "battle_engine",
        "tournament",
        *options,
    ]


def build_designer_match_arguments(
    *,
    ticks: object,
    arena: object,
    a_type: object,
    b_type: object,
    a_blob: object | None = None,
    b_blob: object | None = None,
    alive_w: object | None = None,
    kill_w: object | None = None,
    territory_w: object | None = None,
    territory_bucket: object | None = None,
    seed: object | None = None,
) -> list[str]:
    """Build Designer match options without importing a GUI toolkit."""
    arguments = [
        "--ticks", str(ticks),
        "--arena", str(arena),
        "--a-type", str(a_type),
        "--b-type", str(b_type),
    ]
    for flag, value in (("--a-blob", a_blob), ("--b-blob", b_blob)):
        if value:
            arguments.extend((flag, str(value)))
    optional = (
        ("--alive-w", alive_w),
        ("--kill-w", kill_w),
        ("--territory-w", territory_w),
        ("--territory-bucket", territory_bucket),
        ("--seed", seed),
    )
    for flag, value in optional:
        if value is not None:
            arguments.extend((flag, str(value)))
    return arguments


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
