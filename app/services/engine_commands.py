"""GUI-independent process construction for the Agent Designer."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from subprocess import Popen
from typing import Any

from battle_engine.launchers import build_match_command, build_replay_command

from app.services.osutil import DefaultPaths, pythonpath_separator


@dataclass
class RunConfig:
    a_type: str
    b_type: str
    arena: int = 512
    ticks: int = 600
    alive_w: float | None = None
    kill_w: float | None = None
    territory_w: float | None = None
    territory_bucket: int | None = None
    seed: int | None = None
    a_params: dict[str, Any] | None = None
    b_params: dict[str, Any] | None = None


def _source_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    sep = pythonpath_separator()
    env["PYTHONPATH"] = sep.join(
        [str(root), str(root / "engine" / "src"), str(root / "client" / "src")]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    return env


def build_engine_command(
    cfg: RunConfig, paths: DefaultPaths
) -> tuple[list[str], dict[str, str]]:
    """Build the source or frozen match command and child environment."""
    arguments = [
        "--arena", str(cfg.arena),
        "--ticks", str(cfg.ticks),
        "--win-mode", "score_fallback",
        "--replay", str(paths.replay_path),
        "--a-type", cfg.a_type,
        "--b-type", cfg.b_type,
    ]
    for flag, value in (
        ("--alive-w", cfg.alive_w),
        ("--kill-w", cfg.kill_w),
        ("--territory-w", cfg.territory_w),
        ("--territory-bucket", cfg.territory_bucket),
    ):
        if value is not None:
            arguments.extend((flag, str(value)))
    if cfg.seed is not None and cfg.seed > 0:
        arguments.extend(("--seed", str(cfg.seed)))

    env = _source_environment(paths.root)
    if cfg.a_params is not None:
        env["BYTEFRAY_AGENT_A_PARAMS_JSON"] = json.dumps(cfg.a_params)
    if cfg.b_params is not None:
        env["BYTEFRAY_AGENT_B_PARAMS_JSON"] = json.dumps(cfg.b_params)
    return build_match_command(arguments), env


def open_pygame_client_direct(battle_root: Path, replay_path: Path) -> None:
    """Launch the source or packaged replay application without a shell."""
    if not replay_path.exists():
        raise FileNotFoundError(f"Replay not found: {replay_path}")
    command = build_replay_command(
        replay_path, ("--renderer", "pygame", "--tick-delay", "0.02")
    )
    try:
        Popen(command, cwd=str(battle_root), env=_source_environment(battle_root))
    except OSError as exc:
        raise OSError(f"Failed to start replay command '{command[0]}': {exc}") from exc
