# app/agent_designer.py
from __future__ import annotations

import os
import sys
from pathlib import Path

from battle_engine.launchers import (
    build_agents_command,
    build_designer_match_arguments,
    build_match_command,
)
from battle_engine.paths import get_data_root
from battle_engine.project_info import get_project_info
from battle_engine.starters import ensure_starter_agents
from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QTabWidget

from app.services.agent_catalog import AgentCatalog
from app.services.agent_workflows import (
    build_development_test_presentation,
    build_validation_presentation,
)
from app.services.designer_workflows import (
    DesignerValidationError,
    build_designer_tournament_command,
    match_artifact_paths,
    new_match_run_directory,
    read_match_presentation,
    read_tournament_presentation,
    validate_homogeneous,
)
from app.services.engine import open_pygame_client_direct
from app.views.advanced import AdvancedPanel
from app.views.development import AgentDevelopmentPanel, NewAgentDialog
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
        self._validate_agent_id = None
        self._validate_stdout = ""
        self._validate_stderr = ""
        self._test_agent_id = None
        self._test_stdout = ""
        self._test_stderr = ""
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

        try:
            self.development = AgentDevelopmentPanel(catalog=self.catalog)
            self.development.refreshAgentsRequested.connect(self.refresh_agents)
            self.development.newAgentRequested.connect(self._on_new_agent)
            self.development.openFolderRequested.connect(self._on_open_agent_folder)
            self.development.validateRequested.connect(self._on_validate_agent)
            self.development.testRequested.connect(self._on_test_agent)
            self.development.openTestReplayRequested.connect(self._on_open_test_replay)
            self.development.inspectTraceRequested.connect(self._on_inspect_trace)
            self.tabs.addTab(self.development, "Agent Development")
        except Exception as e:
            QMessageBox.warning(
                self,
                "Agent Development Panel Unavailable",
                f"Failed to initialize Agent Development panel with battle_root={battle_root}\n\n{e}",
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
    def refresh_agents(self, *, select: str | None = None) -> None:
        """Repopulate agent dropdowns in every panel from the shared catalog.

        This is the single centralized catalog-refresh entry point: every
        panel's combo is repopulated from one fresh ``list_agents()`` call,
        preserving each combo's own current selection where still present.
        ``select`` additionally selects a specific agent in the Agent
        Development tab afterward (used after a successful "New Agent").
        """
        try:
            rows = self.catalog.list_agents()  # returns list of AgentRow
            names = [r.name for r in rows] or ["(none found)"]
            if hasattr(self, "simple"):
                self.simple.setAgents(names)
            if hasattr(self, "advanced"):
                self.advanced.setAgents(names)
            if hasattr(self, "development"):
                self.development.setAgents(rows)
                if select:
                    self.development.selectAgent(select)
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
        if hasattr(self, "development"):
            self.development.setBusy(True)
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
        if self._active_workflow == "validate":
            # Validation's stdout/stderr is the structured `label: value`
            # payload itself (docs/specs/agent_validation.md Sec 3.4), not
            # human log narration -- buffer it for parsing at process exit
            # instead of piping it into a Simple/Advanced log panel.
            self._validate_stdout += out
            self._validate_stderr += err
            return
        if self._active_workflow == "test":
            # Same reasoning as validation: a development test's
            # stdout/stderr is the structured `label: value` payload
            # docs/specs/agent_test.md Sec 11 documents, not human log
            # narration -- buffer it for parsing at process exit.
            self._test_stdout += out
            self._test_stderr += err
            return
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
        if hasattr(self, "development"):
            self.development.setBusy(True)
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
        was_validating = self._active_workflow == "validate"
        was_testing = self._active_workflow == "test"
        validate_agent_id = self._validate_agent_id
        test_agent_id = self._test_agent_id
        self._dispose_process()
        self.simple.setBusy(False)
        self.advanced.setBusy(False)
        if hasattr(self, "development"):
            self.development.setBusy(False)
            if was_validating and validate_agent_id:
                self.development.show_stopped(validate_agent_id)
            elif was_testing and test_agent_id:
                self.development.show_test_stopped(test_agent_id)
        if was_validating or was_testing:
            return  # Validate/Test have no Simple/Advanced log target to narrate the stop.
        if self._log_target:
            self._log_target.appendLog("[RunMatch] stopped.\n")

    def _on_proc_finished(self, proc, code, status):
        if proc is not self._proc:
            return  # Stale signal from a process this window has already moved past.
        self.simple.setBusy(False)
        self.advanced.setBusy(False)
        if hasattr(self, "development"):
            self.development.setBusy(False)
        if self._active_workflow == "validate":
            self._present_validation_result(code)
            return
        if self._active_workflow == "test":
            self._present_test_result(code)
            return
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
        if hasattr(self, "development"):
            self.development.setBusy(False)
            if self._active_workflow == "validate":
                self.development.show_tool_failure(self._validate_agent_id or "", message)
            elif self._active_workflow == "test":
                self.development.show_test_tool_failure(self._test_agent_id or "", message)
        if self._active_workflow not in ("validate", "test"):
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
        if hasattr(self, "development"):
            self.development.setBusy(True)
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

    def _on_new_agent(self) -> None:
        dialog = NewAgentDialog(self.battle_root, parent=self)
        if not dialog.exec() or dialog.result is None:
            return
        result = dialog.result
        self.refresh_agents(select=result.agent_id)
        if hasattr(self, "development"):
            self.development.setStatus(
                f"Created agent '{result.agent_id}'.\n"
                f"manifest: {result.manifest_path}\n"
                f"source: {result.source_path}"
            )

    def _on_validate_agent(self) -> None:
        """Validate the selected Python agent out-of-process (QProcess).

        Validation executes arbitrary, unsandboxed, un-timed-out user
        Python during import/factory construction/``reset()``/``act()``
        (docs/specs/agent_designer_workflow.md Sec 5) -- it must never run
        synchronously on this (the GUI) thread. Shares the existing single
        ``self._proc`` slot/lifecycle machinery with match/tournament
        launch (Sec 14.1), so a Validate click while any process is already
        active is a no-op rather than replacing the in-flight run.
        """
        if not hasattr(self, "development"):
            return
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            return  # A process (match/tournament/validate/test) is already active.
        row = self.development.selectedAgentRow()
        if row is None:
            return
        agent_id = row.name

        try:
            command = build_agents_command("validate", [agent_id])
        except FileNotFoundError as exc:
            self.development.show_tool_failure(agent_id, str(exc))
            return

        self._active_workflow = "validate"
        self._validate_agent_id = agent_id
        self._validate_stdout = ""
        self._validate_stderr = ""
        self.development.showValidating(agent_id)
        self.simple.setBusy(True)
        self.advanced.setBusy(True)
        self.development.setBusy(True)

        # Same child environment construction already used for match
        # launch: the child inherits this process's environment (so a
        # custom BYTEFRAY_ROOT/BATTLE2_ROOT/BATTLE_ROOT is honored
        # identically), plus a PYTHONPATH extension for a source checkout.
        env = QProcessEnvironment.systemEnvironment()
        root = self.battle_root
        eng = str(root / "engine" / "src")
        cli = str(root / "client" / "src")
        sep = ";" if sys.platform == "win32" else ":"
        existing = env.value("PYTHONPATH") or ""
        env.insert("PYTHONPATH", eng + sep + cli + (sep + existing if existing else ""))
        env.insert("BATTLE_AGENTS_DIR", str(root / "agents"))

        proc = self._start_process(command, env, root, label="Validate")
        proc.start()

    def _present_validation_result(self, code: int) -> None:
        if not hasattr(self, "development"):
            return
        presentation = build_validation_presentation(
            code, self._validate_stdout, self._validate_stderr, agent_id=self._validate_agent_id or ""
        )
        self.development.show_validation_result(presentation)

    def _on_test_agent(self) -> None:
        """Development-test the selected Python agent out-of-process (QProcess).

        Same process-boundary reasoning as ``_on_validate_agent`` --
        ``agents test`` executes up to 200 (default) ticks of fully
        arbitrary, un-timed-out user Python (docs/specs/agent_designer_workflow.md
        Sec 5/Sec 11) -- and shares the identical single ``self._proc``
        slot/lifecycle machinery, so a Test click while any process is
        already active is a no-op rather than replacing the in-flight run.
        """
        if not hasattr(self, "development"):
            return
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            return  # A process (match/tournament/validate/test) is already active.
        row = self.development.selectedAgentRow()
        if row is None:
            return
        agent_id = row.name
        opponent_id = self.development.selected_opponent_id()
        seed = self.development.selected_seed()
        ticks = self.development.selected_ticks()
        timeout = self.development.selected_timeout()

        arguments = [agent_id]
        if opponent_id is not None:
            arguments.extend(("--opponent", opponent_id))
        arguments.extend(("--seed", str(seed)))
        arguments.extend(("--ticks", str(ticks)))
        arguments.extend(("--timeout", str(timeout)))

        try:
            command = build_agents_command("test", arguments)
        except FileNotFoundError as exc:
            self.development.show_test_tool_failure(agent_id, str(exc))
            return

        self._active_workflow = "test"
        self._test_agent_id = agent_id
        self._test_stdout = ""
        self._test_stderr = ""
        self.development.showTesting(agent_id, opponent_id or "reference")
        self.simple.setBusy(True)
        self.advanced.setBusy(True)
        self.development.setBusy(True)

        # Same child environment construction already used for match
        # launch/validate: the child inherits this process's environment
        # (so a custom BYTEFRAY_ROOT/BATTLE2_ROOT/BATTLE_ROOT is honored
        # identically), plus a PYTHONPATH extension for a source checkout.
        env = QProcessEnvironment.systemEnvironment()
        root = self.battle_root
        eng = str(root / "engine" / "src")
        cli = str(root / "client" / "src")
        sep = ";" if sys.platform == "win32" else ":"
        existing = env.value("PYTHONPATH") or ""
        env.insert("PYTHONPATH", eng + sep + cli + (sep + existing if existing else ""))
        env.insert("BATTLE_AGENTS_DIR", str(root / "agents"))

        proc = self._start_process(command, env, root, label="AgentTest")
        proc.start()

    def _present_test_result(self, code: int) -> None:
        if not hasattr(self, "development"):
            return
        presentation = build_development_test_presentation(
            code, self._test_stdout, self._test_stderr, agent_id=self._test_agent_id or ""
        )
        self.development.show_test_result(presentation)

    def _on_open_test_replay(self) -> None:
        """Open a development test's own replay -- independent of "Open Last Replay".

        Deliberately does not touch ``self._last_replay`` (Sec 13 of the
        Phase 4 spec): a development test's replay must never silently
        become the Simple/Advanced "Open Last Replay" target, since a user
        bouncing between tabs should never be surprised by which replay
        that button opens.
        """
        if not hasattr(self, "development"):
            return
        path = self.development.last_test_replay_path()
        if not path:
            return
        try:
            open_pygame_client_direct(self.battle_root, Path(path))
        except (FileNotFoundError, OSError) as exc:
            QMessageBox.critical(self, "Replay Launch Failed", str(exc))

    def _on_inspect_trace(self) -> None:
        """Open the Trace Inspector over the last development test's trace.

        Unlike Validate/Test/Open Replay, this executes no agent code and
        reads no live process -- it only parses an already-written
        ``trace.jsonl`` (docs/specs/agent_lab.md §11) -- so it runs
        directly on the GUI thread with no QProcess/busy-state involved.
        """
        if not hasattr(self, "development"):
            return
        path = self.development.last_test_trace_path()
        if not path:
            return
        from app.views.trace_inspector import TraceInspectorDialog

        dialog = TraceInspectorDialog(Path(path), parent=self)
        dialog.exec()

    def _on_open_agent_folder(self) -> None:
        if not hasattr(self, "development"):
            return
        row = self.development.selectedAgentRow()
        if row is None:
            QMessageBox.information(self, "Open Agent Folder", "Select an agent first.")
            return
        path = Path(row.path)
        if not path.is_dir():
            QMessageBox.warning(self, "Open Agent Folder", f"Agent folder not found:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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
