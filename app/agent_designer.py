# app/agent_designer.py
from __future__ import annotations
import os
import sys
from pathlib import Path
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QMessageBox
from app.views.simple import SimplePanel
from app.views.advanced import AdvancedPanel
from app.services.agent_catalog import AgentCatalog
from PySide6.QtCore import Slot, QProcess, QProcessEnvironment
from PySide6.QtWidgets import QFileDialog



def _resolve_battle_root() -> Path:
    # 1) allow override via env
    env = os.getenv("BATTLE2_ROOT")
    if env:
        return Path(env).resolve()
    # 2) default to project root (parent of app/)
    return Path(__file__).resolve().parent.parent


class AgentDesigner(QMainWindow):
    """Main window combining Simple and Advanced tabs."""
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BATTLE2 – Agent Designer")

        # Build battle_root and shared catalog
        battle_root = _resolve_battle_root()
        self.battle_root = battle_root            # <-- keep for later
        self._proc = None                         # <-- init process handle
        self._last_replay = None                  # <-- init replay capture
        self.catalog = AgentCatalog(battle_root)

        # Tabs + panels
        self.tabs = QTabWidget(self)

        try:
            self.simple = SimplePanel(catalog=self.catalog)
            # reacts to 'Refresh Agents' in Simple tab
            self.simple.refreshAgentsRequested.connect(self.refresh_agents)
            self.simple.runRequested.connect(self._on_simple_run)
            self.simple.stopRequested.connect(self._on_stop_run)
            self.simple.openReplayRequested.connect(self._on_open_replay)
            self.tabs.addTab(self.simple, "Simple")
            # default log target so finish/stop never hit AttributeError
            self._log_target = self.simple
        except Exception as e:
            QMessageBox.critical(self, "Simple Panel Error", str(e))

        try:
            self.advanced = AdvancedPanel(catalog=self.catalog, battle_root=battle_root)
            # reacts to 'Refresh Agents' in Advanced tab
            self.advanced.refreshAgentsRequested.connect(self.refresh_agents)
            self.advanced.runRequested.connect(self._on_advanced_run)
            self.advanced.stopRequested.connect(self._on_stop_run)
            self.advanced.openReplayRequested.connect(self._on_open_replay)
            self.tabs.addTab(self.advanced, "Advanced")
        except Exception as e:
            QMessageBox.warning(
                self,
                "Advanced Panel Unavailable",
                f"Failed to initialize Advanced panel with battle_root={battle_root}\n\n{e}",
            )

        self.setCentralWidget(self.tabs)
        self.resize(1000, 720)

        # Initial population of agent lists
        self.refresh_agents()

    @Slot()
    def refresh_agents(self) -> None:
        """Repopulate agent dropdowns in both panels from the shared catalog."""
        try:
            rows = self.catalog.list_agents()  # returns list of AgentRow
            names = [r.name for r in rows] or ["(none found)"]
            if hasattr(self, "simple"):
                self.simple.setAgents(names)
            if hasattr(self, "advanced"):
                self.advanced.setAgents(names)
        except Exception as e:
            QMessageBox.warning(self, "Agent Load Failed", str(e))

    def _cfgget(self, obj, *names, default=None):
        for n in names:
            if hasattr(obj, n):
                return getattr(obj, n)
            if isinstance(obj, dict) and n in obj:
                return obj[n]
        return default

    def _resolve_agent_path_by_name(self, display_name: str) -> str | None:
        for row in self.catalog.list_agents():
            if row.name == display_name:
                return row.path
        return None

    def _resolve_agent_row_by_name(self, display_name):
        for row in self.catalog.list_agents():   # AgentCatalog rows have .name, .path, .blob_path, .meta
            if row.name == display_name:
                return row
        return None

    def _on_advanced_run(self, cfg):
        # make sure Advanced tab gets log output immediately
        self._log_target = self.advanced

        # Accept multiple possible field names from the Advanced panel
        a_name = self._cfgget(cfg, "a_type", "aType", "a", "agentA", "a_kind", "aName")
        b_name = self._cfgget(cfg, "b_type", "bType", "b", "agentB", "b_kind", "bName")
        arena  = self._cfgget(cfg, "arena", "map_size", "board", default=256)
        ticks  = self._cfgget(cfg, "ticks", "steps", "frames", default=200)

        # optional weights / seed
        alive_w = self._cfgget(cfg, "alive_w", "aliveW", "aliveWeight")
        kill_w  = self._cfgget(cfg, "kill_w",  "killW",  "killWeight")
        terr_w  = self._cfgget(cfg, "territory_w", "territoryW", "territoryWeight")
        bucket  = self._cfgget(cfg, "territory_bucket", "territoryBucket")
        seed    = self._cfgget(cfg, "seed", "rng_seed")

        # resolve catalog rows
        rowA = self._resolve_agent_row_by_name(a_name)
        rowB = self._resolve_agent_row_by_name(b_name)
        if not rowA or not rowB:
            self.advanced.appendLog(f"[RunMatch] could not resolve agents: A='{a_name}' B='{b_name}'\n")
            return

        from pathlib import Path
        a_type = (rowA.meta.get("name") if isinstance(getattr(rowA, "meta", None), dict) else None) or Path(rowA.path).name or a_name
        b_type = (rowB.meta.get("name") if isinstance(getattr(rowB, "meta", None), dict) else None) or Path(rowB.path).name or b_name

        args = [
            "-m", "battle_engine.cli",
            "--ticks", str(ticks),
            "--arena", str(arena),
            "--a-type", a_type,
            "--b-type", b_type,
        ]
        if getattr(rowA, "blob_path", None):
            args += ["--a-blob", str(rowA.blob_path)]
        if getattr(rowB, "blob_path", None):
            args += ["--b-blob", str(rowB.blob_path)]
        if alive_w is not None: args += ["--alive-w", str(alive_w)]
        if kill_w  is not None: args += ["--kill-w",  str(kill_w)]
        if terr_w  is not None: args += ["--territory-w", str(terr_w)]
        if bucket  is not None: args += ["--territory-bucket", str(bucket)]
        if seed    is not None: args += ["--seed", str(seed)]

        # disable controls; set log target (again, just to be explicit)
        self.simple.setBusy(True)
        self.advanced.setBusy(True)
        self._log_target = self.advanced
        self._last_replay = None

        # child env
        env = QProcessEnvironment.systemEnvironment()
        root = self.battle_root
        eng = str(root / "engine" / "src")
        cli = str(root / "client" / "src")
        sep = ";" if os.name == "nt" else ":"
        existing = env.value("PYTHONPATH") or ""
        env.insert("PYTHONPATH", eng + sep + cli + (sep + existing if existing else ""))
        env.insert("BATTLE_AGENTS_DIR", str(root / "agents"))

        # build process
        self._proc = QProcess(self)
        self._proc.setProcessEnvironment(env)
        self._proc.setWorkingDirectory(str(root))
        self._proc.setProgram(sys.executable)
        self._proc.setArguments(args)

        self._proc.readyReadStandardOutput.connect(self._pipe_proc_output)
        self._proc.readyReadStandardError.connect(self._pipe_proc_output)
        self._proc.finished.connect(self._on_proc_finished)
        self._proc.errorOccurred.connect(lambda e: self.advanced.appendLog(f"[RunMatch] process error: {e}\n"))

        self.advanced.appendLog(
            f"[RunMatch] A={a_name} -> type='{a_type}' blob='{getattr(rowA,'blob_path',None)}'  "
            f"B={b_name} -> type='{b_type}' blob='{getattr(rowB,'blob_path',None)}'  "
            f"ticks={ticks} arena={arena} seed={seed} "
            f"alive_w={alive_w} kill_w={kill_w} territory_w={terr_w} bucket={bucket}\n"
        )
        self._proc.start()

    def _pipe_proc_output(self):
        if not self._proc:
            return
        out = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "ignore")
        err = bytes(self._proc.readAllStandardError()).decode("utf-8", "ignore")
        text = (out or "") + (err or "")
        if text:
            # send to active tab’s log
            if getattr(self, "_log_target", None):
                self._log_target.appendLog(text)
            else:
                self.simple.appendLog(text)  # fallback
        # optional: capture replay-ish hint
        for line in text.splitlines():
            if "replay" in line.lower() and (".rep" in line or ".json" in line or ".mp4" in line):
                self._last_replay = line.strip()
                
    def _on_simple_run(self, cfg):
        rowA = self._resolve_agent_row_by_name(cfg.a_type)
        rowB = self._resolve_agent_row_by_name(cfg.b_type)
        if not rowA or not rowB:
            self.simple.appendLog(f"[RunMatch] could not resolve agents: A='{cfg.a_type}' B='{cfg.b_type}'\n")
            self.simple.setBusy(False)
            return

        # Prefer explicit name from YAML, else folder, else UI text
        from pathlib import Path
        a_type = (rowA.meta.get("name") if hasattr(rowA, "meta") and isinstance(rowA.meta, dict) else None) or Path(rowA.path).name or cfg.a_type
        b_type = (rowB.meta.get("name") if hasattr(rowB, "meta") and isinstance(rowB.meta, dict) else None) or Path(rowB.path).name or cfg.b_type

        # Build CLI args with the correct flags
        args = [
            "-m", "battle_engine.cli",
            "--ticks", str(cfg.ticks),
            "--arena", str(cfg.arena),
            "--a-type", a_type,
            "--b-type", b_type,
        ]
        # If blobs exist, pass them (optional)
        if getattr(rowA, "blob_path", None):
            args += ["--a-blob", str(rowA.blob_path)]
        if getattr(rowB, "blob_path", None):
            args += ["--b-blob", str(rowB.blob_path)]

        # disable controls while running
        self.simple.setBusy(True)
        self._last_replay = None

        # child env (so imports/agents work)
        env = QProcessEnvironment.systemEnvironment()
        root = self.battle_root
        eng = str(root / "engine" / "src")
        cli = str(root / "client" / "src")
        sep = ";" if os.name == "nt" else ":"
        existing = env.value("PYTHONPATH") or ""
        env.insert("PYTHONPATH", eng + sep + cli + (sep + existing if existing else ""))
        env.insert("BATTLE_AGENTS_DIR", str(root / "agents"))

        # build process
        self._proc = QProcess(self)
        self._proc.setProcessEnvironment(env)
        self._proc.setWorkingDirectory(str(root))
        self._proc.setProgram(sys.executable)
        self._proc.setArguments(args)

        # wire logs & finish
        self._proc.readyReadStandardOutput.connect(self._pipe_proc_output)
        self._proc.readyReadStandardError.connect(self._pipe_proc_output)
        self._proc.finished.connect(self._on_proc_finished)

        # start
        self.simple.appendLog(
            f"[RunMatch] A={cfg.a_type} -> type='{a_type}' blob='{getattr(rowA,'blob_path',None)}'  "
            f"B={cfg.b_type} -> type='{b_type}' blob='{getattr(rowB,'blob_path',None)}'  "
            f"ticks={cfg.ticks} arena={cfg.arena}\n"
        )
        self._proc.start()

    def _on_stop_run(self):
        if self._proc and self._proc.state() != QProcess.NotRunning:
            self._proc.kill()
        self.simple.setBusy(False)
        self.advanced.setBusy(False)
        if self._log_target:
            self._log_target.appendLog("[RunMatch] stopped.\n")

    def _on_proc_finished(self, code, status):
        self.simple.setBusy(False)
        self.advanced.setBusy(False)
        if self._log_target:
            self._log_target.appendLog(f"[RunMatch] finished with exit code {code}\n")
        if self._last_replay:
            # enable in both; Advanced tab definitely has the button
            self.simple.enableOpenReplay(True)
            self.advanced.enableOpenReplay(True)


    def _on_open_replay(self):
        # try the captured path; else let the user pick
        path = None
        if self._last_replay and os.path.exists(self._last_replay):
            path = self._last_replay
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open Replay", str(self.battle_root), "All Files (*.*)")
        if path:
            if os.name == "nt":
                os.startfile(path)  # nosec
            else:
                QProcess.startDetached("xdg-open", [path])                

def main() -> int:
    app = QApplication(sys.argv)
    win = AgentDesigner()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
