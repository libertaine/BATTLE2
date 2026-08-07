# app/agent_designer.py
from __future__ import annotations

import os
import sys
from pathlib import Path

from battle_engine.launchers import build_designer_match_arguments, build_match_command
from battle_engine.paths import get_data_root
from battle_engine.project_info import get_project_info
from battle_engine.starters import ensure_starter_agents
from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QTabWidget

from app.services.agent_catalog import AgentCatalog
from app.services.engine import open_pygame_client_direct
from app.services.designer_workflows import (
    DesignerValidationError,
    build_designer_tournament_command,
    match_artifact_paths,
    new_match_run_directory,
    read_match_presentation,
    read_tournament_presentation,
    validate_homogeneous,
)
from app.views.advanced import AdvancedPanel
from app.views.simple import SimplePanel
from app.views.tournament import TournamentDialog


def _resolve_battle_root() -> Path:
    """Compatibility wrapper for the shared writable data-root resolver."""
    return get_data_root()


class AgentDesigner(QMainWindow):
    """Main window combining Simple and Advanced tabs."""
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bytefray – Agent Designer")

        # Build battle_root and shared catalog
        battle_root = _resolve_battle_root()
        try:
            ensure_starter_agents(data_root=battle_root)
        except (FileNotFoundError, OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Starter Agents Unavailable",
                f"Bytefray could not initialize its starter agents.\n\n{exc}",
            )
        self.battle_root = battle_root            # <-- keep for later
        self._proc = None                         # <-- init process handle
        self._last_replay = None                  # <-- init replay capture
        self._result_path = None
        self._tournament_output = None
        self._active_workflow = "match"
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
        self._build_menus()
        self.resize(1000, 720)

        # Initial population of agent lists
        self.refresh_agents()

    def _build_menus(self) -> None:
        tools = self.menuBar().addMenu("Tools")
        tools.addAction("Run Tournament…", self._on_tournament)
        tools.addAction("Open Last Output Folder", self._on_open_output_folder)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About Bytefray", self._on_about)

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

    # ------------------------------------------------------------------
    # QProcess lifecycle
    # ------------------------------------------------------------------
    def _dispose_process(self) -> None:
        """Detach and schedule cleanup of the current process, if any.

        Disconnecting a process's signals before killing/replacing it means
        a 'finished'/'errorOccurred' notification that the OS delivers
        *after* this call (the child's actual exit is always asynchronous
        relative to a kill() request) can no longer reach any slot -- this
        removes the stale-signal race at its source, rather than only
        detecting it after the fact. The per-signal handlers below also
        verify the emitting process is still the active one, as a second,
        independent safety net in case a future connection is ever added
        without going through this method.
        """
        proc = self._proc
        if proc is None:
            return
        for signal in (
            proc.finished,
            proc.errorOccurred,
            proc.readyReadStandardOutput,
            proc.readyReadStandardError,
        ):
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass  # Nothing was connected, or the object is already gone.
        if proc.state() != QProcess.NotRunning:
            proc.kill()
        proc.deleteLater()
        self._proc = None

    def _start_process(
        self, command: list[str], env: QProcessEnvironment, working_directory: Path, *, label: str
    ) -> QProcess:
        """Build, wire, and start a fresh QProcess, replacing any prior one.

        Every signal connection closes over ``proc`` explicitly (rather than
        reading ``self._proc`` from inside the handler) so a handler can
        reliably tell whether it is still hearing from the currently active
        process, independent of Qt's ``sender()`` tracking.
        """
        self._dispose_process()
        proc = QProcess(self)
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(str(working_directory))
        proc.setProgram(command[0])
        proc.setArguments(command[1:])
        proc.readyReadStandardOutput.connect(lambda p=proc: self._pipe_proc_output(p))
        proc.readyReadStandardError.connect(lambda p=proc: self._pipe_proc_output(p))
        proc.finished.connect(lambda code, status, p=proc: self._on_proc_finished(p, code, status))
        proc.errorOccurred.connect(
            lambda error, p=proc: self._on_proc_error(p, label, command[0], error)
        )
        self._proc = proc
        return proc

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
        try:
            validate_homogeneous((rowA, rowB))
        except DesignerValidationError as exc:
            self.advanced.appendLog(f"[RunMatch] {exc}\n")
            QMessageBox.warning(self, "Unsupported Match", str(exc))
            return

        a_type = (rowA.meta.get("name") if isinstance(getattr(rowA, "meta", None), dict) else None) or Path(rowA.path).name or a_name
        b_type = (rowB.meta.get("name") if isinstance(getattr(rowB, "meta", None), dict) else None) or Path(rowB.path).name or b_name

        run_directory = new_match_run_directory(self.battle_root)
        result_path, replay_path = match_artifact_paths(run_directory / "replay.jsonl")
        match_arguments = build_designer_match_arguments(
            ticks=ticks,
            arena=arena,
            a_type=a_type,
            b_type=b_type,
            a_blob=getattr(rowA, "blob_path", None),
            b_blob=getattr(rowB, "blob_path", None),
            alive_w=alive_w,
            kill_w=kill_w,
            territory_w=terr_w,
            territory_bucket=bucket,
            seed=seed,
        )
        match_arguments.extend(("--replay", str(replay_path)))
        try:
            command = build_match_command(match_arguments)
        except FileNotFoundError as exc:
            self.advanced.appendLog(f"[RunMatch] {exc}\n")
            return

        # disable controls; set log target (again, just to be explicit)
        self.simple.setBusy(True)
        self.advanced.setBusy(True)
        self._log_target = self.advanced
        self._result_path = result_path
        self._active_workflow = "match"

        # child env
        env = QProcessEnvironment.systemEnvironment()
        root = self.battle_root
        eng = str(root / "engine" / "src")
        cli = str(root / "client" / "src")
        sep = ";" if sys.platform == "win32" else ":"
        existing = env.value("PYTHONPATH") or ""
        env.insert("PYTHONPATH", eng + sep + cli + (sep + existing if existing else ""))
        env.insert("BATTLE_AGENTS_DIR", str(root / "agents"))

        proc = self._start_process(command, env, root, label="RunMatch")

        self.advanced.appendLog(
            f"[RunMatch] A={a_name} -> type='{a_type}' blob='{getattr(rowA,'blob_path',None)}'  "
            f"B={b_name} -> type='{b_type}' blob='{getattr(rowB,'blob_path',None)}'  "
            f"ticks={ticks} arena={arena} seed={seed} "
            f"alive_w={alive_w} kill_w={kill_w} territory_w={terr_w} bucket={bucket}\n"
            f"[RunMatch] output: {run_directory}\n"
        )
        proc.start()

    def _pipe_proc_output(self, proc=None):
        if proc is None or proc is not self._proc:
            return  # Stale signal from a process this window has already moved past.
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "ignore")
        err = bytes(proc.readAllStandardError()).decode("utf-8", "ignore")
        text = (out or "") + (err or "")
        if text:
            # send to active tab’s log
            if getattr(self, "_log_target", None):
                self._log_target.appendLog(text)
            else:
                self.simple.appendLog(text)  # fallback

    def _on_simple_run(self, cfg):
        rowA = self._resolve_agent_row_by_name(cfg.a_type)
        rowB = self._resolve_agent_row_by_name(cfg.b_type)
        if not rowA or not rowB:
            self.simple.appendLog(f"[RunMatch] could not resolve agents: A='{cfg.a_type}' B='{cfg.b_type}'\n")
            self.simple.setBusy(False)
            return
        try:
            validate_homogeneous((rowA, rowB))
        except DesignerValidationError as exc:
            self.simple.appendLog(f"[RunMatch] {exc}\n")
            QMessageBox.warning(self, "Unsupported Match", str(exc))
            return

        # Prefer explicit name from YAML, else folder, else UI text
        a_type = (rowA.meta.get("name") if hasattr(rowA, "meta") and isinstance(rowA.meta, dict) else None) or Path(rowA.path).name or cfg.a_type
        b_type = (rowB.meta.get("name") if hasattr(rowB, "meta") and isinstance(rowB.meta, dict) else None) or Path(rowB.path).name or cfg.b_type

        # Build CLI args with the correct flags
        run_directory = new_match_run_directory(self.battle_root)
        result_path, replay_path = match_artifact_paths(run_directory / "replay.jsonl")
        match_arguments = build_designer_match_arguments(
            ticks=cfg.ticks,
            arena=cfg.arena,
            a_type=a_type,
            b_type=b_type,
            a_blob=getattr(rowA, "blob_path", None),
            b_blob=getattr(rowB, "blob_path", None),
        )
        match_arguments.extend(("--replay", str(replay_path)))
        try:
            command = build_match_command(match_arguments)
        except FileNotFoundError as exc:
            self.simple.appendLog(f"[RunMatch] {exc}\n")
            return

        # disable controls while running
        self.simple.setBusy(True)
        self._result_path = result_path
        self._active_workflow = "match"

        # child env (so imports/agents work)
        env = QProcessEnvironment.systemEnvironment()
        root = self.battle_root
        eng = str(root / "engine" / "src")
        cli = str(root / "client" / "src")
        sep = ";" if sys.platform == "win32" else ":"
        existing = env.value("PYTHONPATH") or ""
        env.insert("PYTHONPATH", eng + sep + cli + (sep + existing if existing else ""))
        env.insert("BATTLE_AGENTS_DIR", str(root / "agents"))

        proc = self._start_process(command, env, root, label="RunMatch")

        # start
        self.simple.appendLog(
            f"[RunMatch] A={cfg.a_type} -> type='{a_type}' blob='{getattr(rowA,'blob_path',None)}'  "
            f"B={cfg.b_type} -> type='{b_type}' blob='{getattr(rowB,'blob_path',None)}'  "
            f"ticks={cfg.ticks} arena={cfg.arena}\n"
            f"[RunMatch] output: {run_directory}\n"
        )
        proc.start()

    def _on_stop_run(self):
        self._dispose_process()
        self.simple.setBusy(False)
        self.advanced.setBusy(False)
        if self._log_target:
            self._log_target.appendLog("[RunMatch] stopped.\n")

    def _on_proc_finished(self, proc, code, status):
        if proc is not self._proc:
            return  # Stale signal from a process this window has already moved past.
        self.simple.setBusy(False)
        self.advanced.setBusy(False)
        label = "Tournament" if self._active_workflow == "tournament" else "RunMatch"
        if self._log_target:
            self._log_target.appendLog(f"[{label}] finished with exit code {code}\n")
        if self._active_workflow == "tournament":
            self._present_tournament_result(code)
            return
        if code == 0 and self._result_path:
            try:
                result = read_match_presentation(self._result_path)
                self._last_replay = result.replay_path
                self._log_target.appendLog(
                    f"[Result] winner={result.winner}; termination={result.termination_reason}\n"
                    f"[Result] canonical result: {result.result_path}\n"
                    f"[Result] replay: {result.replay_path or 'not available'}\n"
                )
                if hasattr(self, "advanced"):
                    self.advanced.show_result(result)
            except (OSError, ValueError, KeyError) as exc:
                self._log_target.appendLog(f"[Result] Could not read canonical result: {exc}\n")
        if self._last_replay and Path(self._last_replay).is_file():
            # enable in both; Advanced tab definitely has the button
            self.simple.enableOpenReplay(True)
            self.advanced.enableOpenReplay(True)

    def _on_proc_error(self, proc, label: str, program: str, error) -> None:
        if proc is not self._proc:
            return  # Stale signal from a process this window has already moved past.
        self.simple.setBusy(False)
        self.advanced.setBusy(False)
        message = f"[{label}] failed to start '{program}': {error}"
        self._log_target.appendLog(message + "\n")
        QMessageBox.critical(self, f"{label} Failed", message)

    def _on_open_replay(self):
        # "Open Last Replay" intentionally stays enabled while a new run is
        # busy (Option A): each run now writes to its own directory
        # (new_match_run_directory), and the stale-process guards above
        # ensure self._last_replay only ever names a genuinely completed
        # run's replay -- never the file a currently-running match is still
        # writing. If either guarantee is ever relaxed, this button should
        # move back into setBusy()'s disabled set.
        path = None
        if self._last_replay and Path(self._last_replay).exists():
            path = self._last_replay
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open Replay", str(self.battle_root), "All Files (*.*)")
        if path:
            try:
                open_pygame_client_direct(self.battle_root, Path(path))
            except (FileNotFoundError, OSError) as exc:
                QMessageBox.critical(self, "Replay Launch Failed", str(exc))

    def _on_tournament(self) -> None:
        rows = self.catalog.list_agents()
        default = self.battle_root / "runs" / "tournaments" / "designer-tournament"
        dialog = TournamentDialog(rows, default, self)
        if not dialog.exec():
            return
        try:
            command = build_designer_tournament_command(
                dialog.selected_rows(),
                rounds=dialog.rounds.value(),
                seed=dialog.seed.value(),
                output_dir=dialog.output_path(),
            )
        except (DesignerValidationError, OSError) as exc:
            QMessageBox.warning(self, "Invalid Tournament", str(exc))
            return
        self._tournament_output = dialog.output_path().expanduser().resolve()
        self._active_workflow = "tournament"
        self._log_target = self.advanced if hasattr(self, "advanced") else self.simple
        self.simple.setBusy(True)
        self.advanced.setBusy(True)
        env = QProcessEnvironment.systemEnvironment()
        sep = ";" if sys.platform == "win32" else ":"
        existing = env.value("PYTHONPATH") or ""
        source = [str(self.battle_root), str(self.battle_root / "engine" / "src")]
        env.insert("PYTHONPATH", sep.join(source + ([existing] if existing else [])))
        env.insert("BATTLE_AGENTS_DIR", str(self.battle_root / "agents"))

        proc = self._start_process(command, env, self.battle_root, label="Tournament")

        self._log_target.appendLog(f"[Tournament] output: {self._tournament_output}\n")
        proc.start()

    def _present_tournament_result(self, code: int) -> None:
        if not self._tournament_output:
            return
        state_path = self._tournament_output / "tournament.json"
        try:
            result = read_tournament_presentation(state_path)
        except (OSError, ValueError, KeyError) as exc:
            self._log_target.appendLog(f"[Tournament] Could not read state: {exc}\n")
            return
        self._log_target.appendLog(
            f"[Tournament] {result.tournament_id} ({result.division})\n"
            f"[Tournament] completed={result.completed} failed={result.failed} "
            f"rejected={result.rejected} corrupted={result.corrupted}\n"
            "[Tournament] standings:\n"
        )
        for row in result.standings:
            self._log_target.appendLog(
                f"  {row.get('agent_id')}: W={row.get('wins')} L={row.get('losses')} "
                f"T={row.get('ties')} score={row.get('score_total')}\n"
            )

    def _on_open_output_folder(self) -> None:
        path = self._tournament_output or (
            self._result_path.parent if self._result_path else self.battle_root / "runs"
        )
        if not path.exists():
            QMessageBox.information(self, "Output Folder", f"Output does not exist yet:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_about(self) -> None:
        info = get_project_info()
        QMessageBox.about(
            self,
            "About Bytefray",
            f"{info.project_name} {info.version} (formerly {info.former_project_name})\n"
            f"Agent API v{info.agent_api_version}\n"
            f"Result schema v{info.result_schema_version}; replay schema v{info.replay_schema_version}\n"
            f"Python {info.python_version}\n"
            f"License: {info.license_name}\n{info.project_url}",
        )

    def closeEvent(self, event) -> None:
        # Detach and kill any active match/tournament subprocess before the
        # window (and this object's slots) go away, so a delayed signal
        # from it can never run against a partially/fully destroyed window,
        # and so the child is not left running detached from the app.
        self._dispose_process()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    win = AgentDesigner()
    win.show()
    smoke_exit_ms = os.environ.get("BATTLE2_GUI_SMOKE_EXIT_MS", "").strip()
    if smoke_exit_ms:
        QTimer.singleShot(max(0, int(smoke_exit_ms)), app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
