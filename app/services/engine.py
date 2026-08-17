from __future__ import annotations

import threading
from pathlib import Path
from subprocess import PIPE, STDOUT, Popen

from PySide6.QtCore import QObject, Signal

from app.services.engine_commands import (
    RunConfig,
    build_engine_command,
    open_pygame_client_direct,
)
from app.services.osutil import (
    ensure_dirs,
    get_default_paths,
)


class EngineRunner(QObject):
    """Runs the battle engine CLI as a subprocess and streams output."""

    output_line = Signal(str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, data_root: Path) -> None:
        super().__init__()
        self.paths = get_default_paths(data_root)
        ensure_dirs(self.paths.replay_path.parent)
        self._proc: Popen[str] | None = None
        self._reader: threading.Thread | None = None

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
        except Exception as e:
            self.error.emit(f"Failed to build engine command: {e}")
            return

        try:
            self._proc = Popen(
                cmd,
                stdout=PIPE,
                stderr=STDOUT,
                env=env,
                text=True,
                cwd=str(self.paths.root),  # ensure runs/ paths resolve under repo root
            )
        except FileNotFoundError:
            self.error.emit(f"Match executable not found when starting: {cmd[0]}")
            return
        except Exception as e:
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
        """Build the source or frozen match command and its child environment."""
        return build_engine_command(cfg, self.paths)

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
