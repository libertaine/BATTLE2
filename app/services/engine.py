from __future__ import annotations
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from subprocess import Popen, PIPE, STDOUT

from PySide6.QtCore import QObject, Signal

from app.services.osutil import (
    get_default_paths,
    pythonpath_separator,
    ensure_dirs,
)


@dataclass
class RunConfig:
    a_type: str
    b_type: str
    arena: int = 512
    ticks: int = 600
    alive_w: Optional[float] = None
    kill_w: Optional[float] = None
    territory_w: Optional[float] = None
    territory_bucket: Optional[int] = None
    seed: Optional[int] = None
    a_params: Optional[Dict[str, Any]] = None
    b_params: Optional[Dict[str, Any]] = None


class EngineRunner(QObject):
    """Runs the battle engine CLI as a subprocess and streams output."""

    output_line = Signal(str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, battle_root: Path) -> None:
        super().__init__()
        self.paths = get_default_paths(battle_root)
        ensure_dirs(self.paths.replay_path.parent)
        self._proc: Optional[Popen[str]] = None
        self._reader: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ---- Public API ----
    def run(self, cfg: RunConfig) -> None:
        if self.is_running:
            self.error.emit("Engine already running.")
            return
        try:
            cmd, env = self._build_engine_cmd(cfg)
        except FileNotFoundError as e:
            self.error.emit(str(e))
            return
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Failed to build engine command: {e}")
            return

        try:
            self._proc = Popen(
                cmd,
                stdout=PIPE,
                stderr=STDOUT,
                env=env,
                text=True,
                cwd=str(self.paths.root),
            )
        except FileNotFoundError:
            self.error.emit("Python interpreter not found when launching engine.")
            return
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Failed to start engine: {e}")
            return

        # Start reader thread
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        # Start watcher thread to emit finished code
        threading.Thread(target=self._waiter, daemon=True).start()

    def stop(self) -> None:
        if not self.is_running:
            return
        assert self._proc is not None
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
        finally:
            self._proc = None

    def open_pygame_client(self, replay_path: Path) -> None:
        open_pygame_client_direct(self.paths.root, replay_path)

    # ---- Internal helpers ----
    def _build_engine_cmd(self, cfg: RunConfig) -> tuple[list[str], dict[str, str]]:
        py = sys.executable
        engine_cli = self.paths.root / "engine" / "src" / "battle_engine" / "cli.py"
        if not engine_cli.exists():
            raise FileNotFoundError(f"Missing engine CLI at {engine_cli}")

        # Common arguments
        args: list[str] = [
            py,
            str(engine_cli),
            "--arena",
            str(cfg.arena),
            "--ticks",
            str(cfg.ticks),
            "--win-mode",
            "score_fallback",
            "--replay",
            str(self.paths.replay_path),
            "--a-type",
            cfg.a_type,
            "--b-type",
            cfg.b_type,
        ]
        if cfg.alive_w is not None:
            args += ["--alive-w", str(cfg.alive_w)]
        if cfg.kill_w is not None:
            args += ["--kill-w", str(cfg.kill_w)]
        if cfg.territory_w is not None:
            args += ["--territory-w", str(cfg.territory_w)]
        if cfg.territory_bucket is not None:
            args += ["--territory-bucket", str(cfg.territory_bucket)]
        if cfg.seed is not None and cfg.seed > 0:
            args += ["--seed", str(cfg.seed)]

        # Agent params via environment variables (engine can read if supported)
        env = os.environ.copy()
        sep = pythonpath_separator()
        env["PYTHONPATH"] = sep.join(
            [
                str(self.paths.root / "engine" / "src"),
                str(self.paths.root / "client" / "src"),
            ]
        )

        # If engine supports agent params via JSON envs, pass them.
        if cfg.a_params is not None:
            env["BATTLE_AGENT_A_PARAMS_JSON"] = json.dumps(cfg.a_params)
        if cfg.b_params is not None:
            env["BATTLE_AGENT_B_PARAMS_JSON"] = json.dumps(cfg.b_params)

        return args, env

    def _read_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self.output_line.emit(line.rstrip("\n"))
        # Drain done.

    def _waiter(self) -> None:
        assert self._proc is not None
        code = self._proc.wait()
        self.finished.emit(int(code))
        self._proc = None


def open_pygame_client_direct(battle_root: Path, replay_path: Path) -> None:
    if not replay_path.exists():
        raise FileNotFoundError(f"Replay not found: {replay_path}")
    py = sys.executable
    module_cmd = [
        py,
        "-m",
        "battle_client.cli",
        "--replay",
        str(replay_path),
        "--renderer",
        "pygame",
        "--tick-delay",
        "0.02",
    ]

    env = os.environ.copy()
    sep = pythonpath_separator()
    env["PYTHONPATH"] = sep.join(
        [
            str(battle_root / "engine" / "src"),
            str(battle_root / "client" / "src"),
        ]
    )

    Popen(module_cmd, cwd=str(battle_root), env=env)
