"""Source and frozen command construction for Bytefray child applications."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from battle_engine.paths import is_frozen_application, normalize_root


def _packaged_executable_filename(name: str) -> str:
    """Return the platform-appropriate filename PyInstaller gives ``name``.

    A Windows onedir build's launcher is ``<name>.exe``; every other
    platform's PyInstaller launcher (Linux, macOS) has no extension at all.
    """
    return f"{name}.exe" if sys.platform == "win32" else name


def _current_executable() -> str:
    """Return the running interpreter's own path, without resolving symlinks.

    ``sys.executable`` is documented as already absolute, including inside a
    virtualenv. Routing it through :func:`normalize_root` (which calls
    ``Path.resolve()``) is correct for user-supplied paths but wrong here:
    a standard Linux ``venv``'s ``bin/python`` is itself a symlink chain
    down to the base interpreter it was created from, and resolving it
    walks straight past the venv to that base interpreter -- which lacks
    the venv's site-packages entirely. Every child process this module
    launches in source (non-frozen) mode would then fail to import
    ``battle_engine``. ``expanduser`` is kept for parity with
    ``normalize_root`` even though ``sys.executable`` never contains ``~``.
    """
    return str(Path(sys.executable).expanduser())


def _packaged_executable(name: str) -> Path:
    executable_dir = normalize_root(Path(sys.executable).parent)
    filename = _packaged_executable_filename(name)
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
    """Build a non-shell command for the primary Bytefray match interface."""
    options = list(arguments)
    if is_frozen_application():
        return [str(_packaged_executable("bytefray")), "run", *options]
    return [_current_executable(), "-m", "battle_engine", "run", *options]


def build_tournament_command(arguments: Sequence[str]) -> list[str]:
    """Build a non-shell command for the supported tournament interface."""
    options = list(arguments)
    if is_frozen_application():
        return [str(_packaged_executable("bytefray")), "tournament", *options]
    return [
        _current_executable(),
        "-m",
        "battle_engine",
        "tournament",
        *options,
    ]


def build_agents_command(subcommand: str, arguments: Sequence[str]) -> list[str]:
    """Build a non-shell command for a ``bytefray agents <subcommand>`` verb.

    Mirrors :func:`build_match_command`/:func:`build_tournament_command`
    exactly. Only ``validate``/``test`` are routed through this builder --
    ``agents create`` (scaffolding) executes no agent-author code and is
    called directly, in-process, instead (see
    ``docs/specs/agent_designer_workflow.md``).
    """
    options = list(arguments)
    if is_frozen_application():
        return [str(_packaged_executable("bytefray")), "agents", subcommand, *options]
    return [
        _current_executable(),
        "-m",
        "battle_engine",
        "agents",
        subcommand,
        *options,
    ]


def build_designer_match_arguments(
    *,
    ticks: object,
    arena: object,
    a_type: object,
    b_type: object,
    ruleset_id: object,
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
        "--ruleset", str(ruleset_id),
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
            str(_packaged_executable("bytefray-replay-viewer")),
            "--replay",
            replay,
            *options,
        ]
    return [
        _current_executable(),
        "-m",
        "battle_client.cli",
        "--replay",
        replay,
        *options,
    ]
