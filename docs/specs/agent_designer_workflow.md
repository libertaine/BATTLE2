# agent_designer_workflow

**Module(s) affected (future implementation, not this task):** `app/agent_designer.py`,
`app/views/*.py`, a new `app/views/development.py`, `app/services/agent_catalog.py`,
a new `app/services/agent_workflows.py` (or similarly named), `engine/src/battle_engine/launchers.py`
(one new command builder).
**Purpose:** Specify how Bytefray v0.4 Phase 4 brings the Phase 1–3 headless
agent-authoring loop (`create → validate → test → replay → modify → repeat`)
into the existing PySide6 Agent Designer (`app/agent_designer.py`), without
implementing it.

## 0. Status / provenance

This is an **investigation-and-specification task only**. Nothing in this
document is implemented. It was written by tracing the actual current
Designer source (`app/agent_designer.py`, `app/services/*.py`,
`app/views/*.py`), the actual Phase 1–3 backend modules
(`engine/src/battle_engine/agent_scaffold.py`, `agent_validation.py`,
`agent_test.py`), `battle_engine.launchers`, `battle_client.renderers.pygame_canvas`,
and the existing Designer test suite (`tests/test_agent_designer_lifecycle.py`,
`engine/tests/test_designer_workflows.py`) — not by re-deriving intent from
the readiness-audit summary alone. Every claim below that describes current
behavior was checked directly against source; claims about future behavior
are explicitly marked as proposals.

Repository state at the time of writing (branch `v0.4-foundation`):
Phase 0 (docs/packaging hygiene), Phase 1 (`bytefray agents create`), Phase 2
(`bytefray agents validate`), and Phase 3 (`bytefray agents test`) are
implemented and committed. `docs/specs/replay_analysis.md` is an unrelated,
untouched, untracked draft spec — not read for content beyond confirming it
is unrelated, and not modified by this task.

## 1. Product goal

Bring the existing headless authoring loop into the Designer with the
smallest coherent set of controls, without turning the Designer into an IDE,
without changing Agent API v1, and without forking any semantics Phases 1–3
already established (agent ID validity, validation stage/diagnostic
semantics, test exit-code/artifact semantics). The Designer's job is
presentation and process orchestration only.

Non-negotiable constraints carried over from Phases 1–3 and from
`docs/AGENT_AUTHORING.md`:

- Python agents run fully unsandboxed, in-process arbitrary code, with **no
  runtime timeout** anywhere in this codebase. A pathological
  `while True: pass` inside `import`, the factory, `reset()`, or `act()` is
  possible today and Phase 4 does not change that.
- `agents validate` and `agents test` are genuinely different questions (see
  `docs/AGENT_AUTHORING.md`'s comparison table) and must stay visually and
  semantically distinct in the GUI.
- A tested/validated agent's own forfeit, death, loss, or (for `test`)
  pre-tick-zero initialization failure is a **successful evaluation**, not a
  tool failure — the GUI must preserve this distinction exactly as the CLI's
  exit codes and `status:` values already do.

## 2. Existing Designer architecture (as implemented today)

### 2.1 Startup

`AgentDesigner.__init__` (`app/agent_designer.py:39`):

1. Resolves `battle_root = get_data_root()` once (`battle_engine.paths`,
   the same resolver `bytefray`'s CLI, `agent_scaffold`, `agent_validation`,
   and `agent_test` all use — see §4 below for why this matters).
2. Calls `ensure_starter_agents(data_root=battle_root)` eagerly, surfacing
   any `FileNotFoundError`/`OSError`/`ValueError` as a `QMessageBox.critical`
   but continuing startup regardless (non-fatal).
3. Constructs one `AgentCatalog(battle_root)` (`app/services/agent_catalog.py`)
   shared by both tabs.
4. Constructs `SimplePanel` and `AdvancedPanel`, wiring their
   `refreshAgentsRequested`/`runRequested`/`stopRequested`/`openReplayRequested`
   signals to `AgentDesigner` slots. Each panel is wrapped in its own
   `try/except` — a broken `AdvancedPanel` only downgrades to a warning
   dialog, not a fatal startup error (Simple Panel failure is currently
   fatal-by-dialog only, not caught before `self.tabs.addTab`, but the
   `try/except` around it means construction failure does not crash the
   process either — the tab is simply never added).
5. Builds the `Tools`/`Help` menu (`_build_menus`).
6. Calls `self.refresh_agents()` once, populating both panels' combo boxes.

There is no "Simple vs Advanced" mode switch beyond two `QTabWidget` tabs
that are both always constructed; neither view is more "authoritative" than
the other, and both currently launch matches independently (§2.2).

### 2.2 Match launch (`GUI action → ... → GUI state update`)

Traced end to end for both panels (`_on_simple_run`/`_on_advanced_run`,
`app/agent_designer.py:198,294`):

```text
SimplePanel/AdvancedPanel "Run Match" click
  → panel emits runRequested(RunConfig), including canonical ruleset_id
  → AgentDesigner._on_simple_run / _on_advanced_run
      → resolve AgentRow for each side via _resolve_agent_row
        (matches AgentRow.agent_id, with row.name only as a legacy-id fallback;
        a secondary display-name fallback is accepted only when unique)
      → validate_homogeneous((rowA, rowB))   [app/services/designer_workflows.py]
          raises DesignerValidationError for <2 agents or mixed VM/Python kinds
      → new_match_run_directory(battle_root)  -- fresh
        <root>/runs/_designer/<timestamp>-<uuid8>/ every call
      → match_artifact_paths(run_dir / "replay.jsonl")
          -> (result.json, replay.jsonl) siblings, by construction
      → build_designer_match_arguments(..., ruleset_id=...)
          emits --ruleset <canonical-id>          [battle_engine.launchers]
      → build_match_command(arguments)        [battle_engine.launchers]
          - frozen: sibling battle2.exe run ...
          - source/dev: sys.executable -m battle_engine run ...
      → self._start_process(command, env, battle_root, label="RunMatch")
          - env = QProcessEnvironment.systemEnvironment() + PYTHONPATH
            (engine/src, client/src) + BATTLE_AGENTS_DIR=<root>/agents
          - QProcess wired: readyReadStandardOutput/Error -> _pipe_proc_output,
            finished -> _on_proc_finished, errorOccurred -> _on_proc_error
      → proc.start()
```

Completion (`_on_proc_finished`, `app/agent_designer.py:363`): re-enables
controls, and on exit `0` calls
`read_match_presentation(self._result_path)` (`app/services/designer_workflows.py`),
which reads the canonical `result.json` via
`battle_engine.result_model.read_result` and resolves the sibling replay
path from `result.replay.filename` — **the Designer already reads the exact
canonical `result.json` a real match writes; it does not parse `bytefray
run`'s stdout for winner/termination.** `AdvancedPanel.show_result(...)`
renders a 4-row `(field, value)` table from that same
`MatchPresentation` dataclass.

`BATTLE_AGENTS_DIR` deserves a precise note: it is set on the *child
process's* environment for two independent reasons that happen to share one
name — `AgentCatalog.agents_dir()` (`app/services/agent_catalog.py:27`)
consults it as a test-only override for the Designer's *own* in-process
catalog scan, and `battle_engine.cli.py`'s `_load_agents_spec_from_env`
(`engine/src/battle_engine/cli.py:133`) consults it only for the legacy
`BATTLE_AGENTS_JSON` back-compat path. **Neither `--a-type`/`--b-type`
resolution in `cli.py` nor `battle_engine.agents.resolve_agent` (used by
`agents create`/`validate`/`test`) ever reads `BATTLE_AGENTS_DIR`** — both
resolve strictly through `get_data_root()/agents`. Setting it on the child
environment today is therefore inert for every code path Phase 4 cares
about; it is not a second data-root mechanism to preserve or replicate.

### 2.3 Tournament launch

`_on_tournament` (`app/agent_designer.py:420`) follows an identical shape:
`TournamentDialog` selection → `build_designer_tournament_command`
(`designer_workflows.py`, itself calling `battle_engine.launchers.build_tournament_command`)
→ `self._start_process(...)` → on finish, `_present_tournament_result` reads
`<output>/tournament.json` via `read_tournament_presentation`, again a
**canonical structured file**, not tournament stdout.

### 2.4 Replay opening

Three paths, all converging on the same primitive:

- **"Open Last Replay"** (`_on_open_replay`, `app/agent_designer.py:401`):
  uses `self._last_replay` (set only from a completed match's
  `MatchPresentation.replay_path`, i.e. only ever a genuinely-finished run's
  replay — the stale-process guards in `_on_proc_finished`/`_dispose_process`
  make this safe) if it exists, else falls back to a `QFileDialog`.
- **Replay Browser** (`AdvancedPanel`, "Replay Browser" tab): a label +
  "Choose .jsonl…" (`QFileDialog.getOpenFileName`) + "Open in Pygame" button,
  independent of `_last_replay`.
- Both call **`open_pygame_client_direct(root, path)`**
  (`app/services/engine_commands.py:73`), which builds a non-shell command
  via `battle_engine.launchers.build_replay_command` (frozen:
  sibling `battle-replay-viewer.exe`; source: `python -m battle_client.cli`)
  and starts it with a bare `subprocess.Popen` — **not** `QProcess`, and
  **not** tracked by `self._proc`. This is a deliberate, already-correct
  fire-and-forget launch: the Designer has no reason to own the replay
  viewer's lifecycle (it is a separate interactive window the user closes
  independently), and it does not compete with `self._proc`'s single-slot
  invariant (§2.5).

`PygameCanvas` (`client/src/battle_client/renderers/pygame_canvas.py`)
participates in **none** of these paths — see §16.

### 2.5 Result display

- Native matches: `result.json` via `read_match_presentation`
  (§2.2) — canonical, typed, four fields (`winner`, `termination_reason`,
  `result_path`, `replay_path`).
- Tournaments: `tournament.json` via `read_tournament_presentation` —
  canonical, typed, counts + standings.
- Raw subprocess stdout/stderr is piped to the active tab's log
  (`_pipe_proc_output`) purely for human visibility; it is never parsed for
  structured fields today. **This is the one place Phase 4 cannot simply
  extend the existing pattern**, because `agents validate`/`agents test`
  have no equivalent always-present canonical file for every outcome (a
  validation dry run never writes one; a test's initialization-failure
  outcome deliberately writes none) — see §13.
- Errors: `QMessageBox` dialogs (`.critical`/`.warning`/`.information`) for
  startup failures, unresolved agent selections, unsupported match
  compositions, and process-start failures; the active tab's log panel for
  ongoing/streamed output. There is no existing distinction in the UI
  between "your input was invalid" and "Bytefray itself failed" beyond the
  dialog vs. log placement and the message text itself — Phase 4 needs a new,
  narrowly-scoped presentation-level distinction for this (§13).

### 2.6 Process management

`_dispose_process`/`_start_process` (`app/agent_designer.py:142,173`) already
implement exactly the invariants Phase 4 needs to reuse, not reinvent:

- **Single active process.** `self._proc` is one slot; `_start_process`
  calls `_dispose_process()` first, so starting any new process
  (match, tournament — and, per this spec's recommendation, validate/test)
  always tears down whatever was running before.
- **Stale-signal immunity.** Every signal connection closes over the actual
  `proc` object explicitly; every handler (`_on_proc_finished`,
  `_on_proc_error`, `_pipe_proc_output`) checks `proc is self._proc` before
  acting, and `_dispose_process` additionally `disconnect()`s every signal
  before killing/replacing a process, so a signal delivered after
  replacement cannot mutate state belonging to a different run. This exact
  pattern is directly regression-tested (`tests/test_agent_designer_lifecycle.py`).
- **Kill, not terminate-then-escalate.** `_dispose_process` calls
  `proc.kill()` unconditionally (no `terminate()` grace period, no timeout
  escalation) whenever a process is still running at disposal time. Phase 4
  should reuse this exact, already-shipped behavior for a new "Stop"
  affordance on validate/test rather than inventing a softer
  terminate-then-kill sequence that does not exist anywhere else in this
  codebase today (§23).
- **`closeEvent` disposes the active process** before the window closes, so
  no child is ever left running detached from a closed Designer.
- Nothing here assumes match/tournament output is the *only* kind of
  process the Designer will ever run — `_start_process`'s signature
  (`command`, `env`, `working_directory`, `label`) is already fully generic.

### 2.7 Agent catalog

`AgentCatalog` (`app/services/agent_catalog.py`) is a thin, stateless adapter:
`list_agents()` calls `battle_engine.agents.discover_agents_in(self.agents_dir())`
fresh on every call (no caching) and maps each `AgentSpec` to an `AgentRow`
(`name` = display, `path`, `blob_path`, `meta`). There is **no
`refresh()`/staleness state on `AgentCatalog` itself** — "refresh" is purely
"call `list_agents()` again," already idempotent and side-effect-free.

`AgentDesigner.refresh_agents()` (`app/agent_designer.py:106`) is the
existing, single call site that repopulates *both* panels'
combos (`self.simple.setAgents(names)`, `self.advanced.setAgents(names)`),
where `setAgents` preserves the current selection by text if still present
(`app/views/simple.py:94`, `app/views/advanced.py:156`). **This already is
a de facto centralized refresh** — it just needs one more caller
(`self.development.setAgents(names)`) once a third combo exists, and,
per §20, one added parameter to also *select* a specific agent afterward
(needed for "New Agent" — see §9).

Two other, unrelated `AgentCatalog`-named classes exist and are **dead
code**, not part of the wired Designer:

- `app/services/agents.py`'s `AgentCatalog` (a hand-rolled JSON-only
  directory scanner) — no import of it exists anywhere outside its own
  module.
- `app/services/agent_meta.py`'s `read_agent_meta` — likewise unreferenced.

These are pre-existing orphans, unrelated to Phase 4's own work; see §28
("Later roadmap item").

### 2.8 Agent Params tab — confirmed semantics, and a confirmed dead-wiring bug

`AdvancedPanel`'s "Agent Params" tab (`app/views/advanced.py:107`) is two
`JsonEditor` widgets (`app/widgets/json_editor.py`) whose `get_data_or_none()`
is read into `RunConfig.a_params`/`b_params` inside `AdvancedPanel._emit_run`
(`app/views/advanced.py:230`). Tracing what happens to that `RunConfig` next:

- `AgentDesigner._on_advanced_run` (`app/agent_designer.py:198`) receives
  this `cfg` and extracts fields via `self._cfgget(cfg, "a_type", "aType", ...)`
  — a small multi-alias getter that **never queries `a_params`/`b_params`
  under any alias**.
- `build_designer_match_arguments` (`battle_engine.launchers`) has **no
  parameter for per-agent JSON params at all** — its signature is `ticks`,
  `arena`, `a_type`, `b_type`, `a_blob`/`b_blob`, the three score weights,
  `territory_bucket`, `seed`.

**Confirmed: the "Agent Params" tab's JSON is validated locally by
`JsonEditor` and then silently discarded — it never reaches
`build_designer_match_arguments`, the constructed CLI command, or the child
process's environment, for either the Simple or Advanced launch path.**
(A separate, unused code path — `app/services/engine_commands.py`'s
`build_engine_command`, called only by the dead `EngineRunner` class in
`app/services/engine.py`, §2.9 — *would* have serialized `a_params`/`b_params`
into `BATTLE_AGENT_A_PARAMS_JSON`/`BATTLE_AGENT_B_PARAMS_JSON` environment
variables, but that function and class are never instantiated by
`AgentDesigner` today.) This means the tab's existing behavior is strictly
worse than "edits transient run-time JSON rather than the source" — it
edits JSON that currently has **no effect on any match at all**. This is a
genuine, pre-existing bug, but it is orthogonal to Phase 4's own scope (it
concerns a VM-agent parameter-override feature, not agent *authoring*), and
fixing it would touch `_on_advanced_run`/`build_designer_match_arguments`,
neither of which Phase 4 otherwise needs to change. See §28 — classified as
a **later roadmap item**, explicitly called out so it is not confused with
Phase 4's new "Agent Development" tab.

**Resolved** (post-1.0 maintenance pass): `_on_advanced_run` now reads
`cfg.a_params`/`cfg.b_params` and exports them as
`BATTLE_AGENT_A_PARAMS_JSON`/`BATTLE_AGENT_B_PARAMS_JSON` on the child
process's environment, matching the export `build_engine_command` already
performed in the dead `EngineRunner` path (§2.9). `_resolve_agent`
(`cli.py`) also had its own half of the bug: it parsed
`BATTLE_AGENT_{letter}_PARAMS_JSON` for a *discovered* agent but discarded
the merged result (`_merged` was computed and never read), and never parsed
it at all for the *built-in* fallback branch — the common case for the
starter VM agents. Both are now fixed: the built-in branch merges the
per-agent JSON over the shared `--byte`/`--offset`/etc. CLI defaults before
calling `build_agent`, so per-agent overrides actually take effect.
Covered by `tests/test_agent_designer_lifecycle.py::test_advanced_run_exports_agent_params_json_to_child_env`
and `engine/tests/test_cli_characterization.py::test_resolve_agent_applies_per_agent_env_json_to_builtin_construction`.

The task's premise — that this tab's existing purpose is materially
different from authoring/editing an agent's own source or catalog
definition — is correct regardless of the dead-wiring bug: even if the
wiring worked as originally intended, this tab edits **per-run VM parameter
overrides**, not `agent.yaml`/`agent.py`. Phase 4 must not repurpose it.

### 2.9 Other services confirmed unused by the live Designer

- `app/services/engine.py`'s `EngineRunner` (a `Popen`+`threading`-based
  runner) and its `_read_loop`/`_waiter` threads are never instantiated by
  `AgentDesigner`. The live match-launch path is entirely the `QProcess`
  path in `app/agent_designer.py` itself (§2.2). `EngineRunner` is dead
  code kept for historical reasons; not touched by this spec (see §28).
- `app/services/osutil.py`'s `get_default_paths`/`ensure_dirs`/
  `read_summary_json` are used by `AdvancedPanel`'s Replay Browser label
  default and by `EngineRunner`, not by the live match-result path.

## 3. Existing Phase 1–3 backend as a GUI integration surface

All three modules already expose a small, precisely-typed **service API**
distinct from their CLI adapter — confirmed by reading the actual source,
not inferred from the specs:

| Phase | Service function | Success type | Failure type (raises) |
|---|---|---|---|
| 1 (`agent_scaffold.py`) | `create_agent(agent_id, *, data_root=None, resource_root=None)` | `ScaffoldResult(agent_id, manifest_path, source_path)` | `AgentScaffoldError` (message only; no `RuntimeDiagnostic`) or a bare `OSError` |
| 2 (`agent_validation.py`) | `validate_agent(agent_id, *, data_root=None)` | `ValidationResult(agent_id, api_version, dry_run_action)` | `AgentValidationFailedError(diagnostic: RuntimeDiagnostic)` |
| 3 (`agent_test.py`) | `test_agent(agent_id, *, opponent=None, seed=None, ticks=None, data_root=None, resource_root=None)` | `DevelopmentTestOutcome(agent_id, opponent_name, seed, ticks_requested, match_result: NativeMatchResult, summary_path)` **or** `InitializationFailureOutcome(agent_id, diagnostic: RuntimeDiagnostic, opponent_name=None)` | `AgentTestError(diagnostic: RuntimeDiagnostic)` |

The **CLI adapter** in each module (`_parser()`/`main(argv)`) is purely
argparse + `print(...)`/exit-code translation around these functions — there
is no CLI-only behavior a GUI caller would need to reproduce, and no
argument-order/environment dependency beyond `data_root`/`resource_root`
(both already explicit, optional keyword parameters mirroring
`get_data_root()`/`get_resource_root()`'s own defaults).

**Environment/data-root parity, verified directly (task §4's central
question):** `get_data_root()` (`battle_engine.paths`) is a pure function of
`os.environ` (or an explicit mapping) with no process-identity dependency —
`configured_data_root` checks `BYTEFRAY_ROOT`/`BATTLE2_ROOT`/`BATTLE_ROOT`;
absent those, source-checkout/frozen/installed-platform fallback applies
identically regardless of caller. `battle_engine.cli.py`'s own
`_battle_root()` (used by every subcommand's `--a-type`/`--b-type`
resolution) is `return get_data_root()` — the literal same function, not a
CLI-specific variant. **A Designer process calling `validate_agent(id,
data_root=self.battle_root)` in-process therefore sees exactly the same
agent catalog a concurrently-launched `bytefray agents validate id`
subprocess would see**, because `self.battle_root` was itself computed by
the identical `get_data_root()` call at Designer startup, against the same
OS environment the Designer process (and therefore any QProcess child it
spawns, which inherits/extends that environment) shares. There is no second,
divergent root-resolution path anywhere in this call graph. Passing
`data_root=self.battle_root` explicitly (rather than relying on each
function's own internal `get_data_root()` default) is still recommended
practice — not because the two would ever disagree today, but because it
makes the dependency visible at the call site and immune to a future
Designer feature that mutates `os.environ` mid-session for some unrelated
reason.

`get_resource_root()` parity is **not** unconditionally true across every
packaging target — see the concrete packaging gap in §17.3/§28 (item 1):
`tools/agent_designer.spec` does not bundle `battle_engine/data/agent_template/`,
so a frozen `battle-agent-designer.exe`'s own `get_resource_root()` would
not find the scaffold template even though the identically-shaped
`tools/battle2.spec` was already fixed to bundle it (visible directly in
the two spec files; `agent_test.md` §8.6 documents the `battle2.spec` half
of this same class of bug, discovered independently for Phase 3).

## 4. Integration alternatives considered

### Approach A — QProcess/CLI for all authoring operations

Consistent with current match/tournament launch, but forces every operation
through argv/exit-code/stdout, including scaffold — a pure filesystem
operation with no arbitrary user code and an existing, fully-typed
`ScaffoldResult`. Subprocess startup cost (tens of milliseconds at minimum,
more on Windows) for an operation that already completes in microseconds
in-process is real, avoidable overhead for the single most frequently
repeated action in the loop (an author will create far more agents than
they will run tournaments). Uniform-Process is simple to reason about but
not the cheapest correct answer for every operation.

### Approach B — direct Python service calls for everything

Cleanest structured-data story, but wrong for `validate`/`test` specifically
because both execute **arbitrary, unsandboxed, un-timed-out user Python**
(§1). See §5 (thread-vs-process analysis) for why a `QThread`/`QThreadPool`
worker does not solve this: Python's GIL means a CPU-bound infinite loop in
a worker thread still starves the Qt event loop of interpreter time, and a
thread that never returns from `act()`/`reset()` cannot be safely killed at
all (no supported thread-kill primitive in CPython) — a hung worker thread
would hold the *entire process*, GUI included, hostage indefinitely, which
is strictly worse than today's un-sandboxed-but-CLI-isolated status quo.
A `QProcess` a user can kill is not a substitute for a real sandbox, but it
is a substantially better failure mode than an unkillable in-process hang.

### Approach C — hybrid (recommended; see §5 for the exact split)

Different operations have different risk profiles that this repository has
already characterized precisely (§1, §3): scaffold executes zero
agent-author code; validate and test both execute arbitrary user Python
with no existing timeout/sandbox. The hybrid is not "some things QProcess,
some things direct, for variety" — it is "process boundary exists exactly
where arbitrary user code executes, and nowhere else," which is a coherent,
narrow rule, not an arbitrary inconsistency.

## 5. Chosen architecture

| Operation | Mechanism | Why |
|---|---|---|
| **Scaffold** (`agents create`) | **Direct in-process call**, on the GUI thread, synchronous | Executes zero agent-author code (§3's table: `create_agent` only copies two static template files and does a directory rename). Already fast (microseconds) and already returns a fully-typed `ScaffoldResult`/`AgentScaffoldError`. A subprocess round-trip here would be pure overhead for the loop's most-repeated action. |
| **Validate** (`agents validate`) | **QProcess**, one call per click | Executes `import`, factory, `reset()`, and one `act()` of fully arbitrary, un-timed-out user Python (§1, `docs/AGENT_AUTHORING.md`'s "Not yet implemented"). A `QThread`/`QThreadPool` worker cannot be safely killed if any of those hangs (§4/Approach B) and would freeze the entire Designer process, not just a panel. `QProcess` gives exactly what the existing match/tournament launch already gives: a hard, killable OS-process boundary the Designer already knows how to manage (§2.6). |
| **Development test** (`agents test`) | **QProcess**, one call per click | Same reasoning as validate, amplified: up to 200 ticks (default) of the identical unsandboxed `act()`/`reset()` calls. Already fits the existing QProcess match-launch shape almost exactly (it *is* a real match through `NativeMatchService`, §3), and already writes the same canonical `replay.jsonl`/`result.json`/`summary.json` artifacts the Designer already knows how to read (§2.2, §13). |
| **Replay** | **Unchanged**: `open_pygame_client_direct` (`subprocess.Popen`, fire-and-forget, outside `self._proc`) | Already correct — an independent, user-owned interactive window; nothing about authoring changes this (§2.4, §15). |

This is exactly the hypothesis floated in the task's §32, confirmed against
the actual repository rather than assumed: scaffold direct, validate and
test out-of-process, replay unchanged.

### 5.1 Thread vs. process, explicitly

- **`QThread`/`QThreadPool`**: rejected for validate/test. The GIL means a
  CPU-bound hang in a worker thread still starves the GUI thread of
  interpreter time (Qt's own event loop is Python-driven here via PySide6
  signal dispatch, not purely native), and there is no safe way to
  terminate a CPython thread stuck in a non-returning call — the process
  would have to be killed entirely to recover, which a user cannot do from
  inside a frozen GUI. This is a strictly worse failure mode than today's
  status quo (a hung *subprocess* the user can kill from Task Manager or,
  with §23's Stop button, from inside the Designer itself).
- **`QProcess`**: accepted for validate/test, for the same reason it is
  already used for match/tournament launch — a hard OS-process boundary
  that (a) the Designer already has complete, tested lifecycle machinery
  for (§2.6), (b) can be killed unconditionally regardless of what the
  child's Python interpreter is doing, and (c) isolates a crash/hang from
  ever touching the Designer's own GUI thread or memory space.
- **Direct call, no thread, no process**: accepted only for scaffold, which
  runs no agent-author code at all and completes in well under the time a
  single Qt paint event takes — there is nothing to protect the GUI thread
  from.

None of this introduces a runtime sandbox or timeout to the Python Agent
API itself. A `QProcess` a human can terminate remains categorically
different from interrupting a non-returning `act()` call inside that
process — killing the process is the only thing Phase 4 can do, exactly as
`bytefray agents validate`/`test` already can only be killed at the OS
level today (Ctrl+C / process kill), never gracefully interrupted mid-call.

## 6. User workflow

```text
select/create agent
        │
        ▼
   [New Agent]  ──(dialog: agent id)──► scaffold direct-call ──► catalog
        │                                                        refresh +
        ▼                                                        select
   [Validate]  ──► QProcess: bytefray agents validate <id> ──► parsed
        │                                                       status
        ▼
   [Development Test]  ──► QProcess: bytefray agents test <id> [opts] ──►
        │                   parsed status + (if completed) canonical
        │                   result.json read the same way match results
        │                   already are
        ▼
   [Open Replay]  ──► existing open_pygame_client_direct, unchanged
        │
        ▼
  (edit agent.py externally — Open Agent Folder)
        │
        └──► back to [Validate]
```

This matches `docs/AGENT_AUTHORING.md`'s documented author workflow
(create → validate → test → replay → modify → repeat) with no reordering.

The Agent Development tab also displays the selected Python agent's current
`agent.py` and `agent.yaml` in a read-only source viewer. It reads those two
files from the exact catalog-discovered `AgentRow.path` on selection and
catalog refresh; it does not parse, import, execute, or write agent source.
Editing remains external through **Open Folder**.

## 7. Proposed UI structure

### 7.1 Placement: a new top-level tab, not a repurposed "Agent Params"

Per §2.8, "Agent Params" edits a materially different concept (per-run VM
parameter overrides, currently non-functional) and must not be repurposed —
doing so would either destroy an existing (if currently broken) feature
surface or confuse two unrelated concepts under one tab. `AgentDesigner`'s
tab structure is a single flat `QTabWidget` (`self.tabs`) with `Simple` and
`Advanced` as siblings — adding a third top-level sibling tab,
**`Agent Development`**, is the least disruptive placement and requires no
change to either existing tab's internal structure:

```python
self.tabs.addTab(self.development, "Agent Development")
```

`AgentDevelopmentPanel` (new, `app/views/development.py`) is constructed and
wired exactly like `SimplePanel`/`AdvancedPanel` are today — its own
`try/except` around construction, its own signal set connected in
`AgentDesigner.__init__`.

### 7.2 Illustrative layout (not final visual spec — see §35)

```text
Agent Development
────────────────────────────────────────
Agent: [ my_agent          ▼ ]  [Refresh]  [New Agent…]  [Open Agent Folder]

Validation                                    Last validation: (none yet)
[Validate]  [Stop]
  Status: Valid
  API version: 1
  Dry-run action: WRITE operand=173 value=165

Development Test                              Last test: (none yet)
▸ Test Options (seed: 1337, ticks: 200, opponent: reference)
[Test]  [Stop]
  Agent: my_agent   Opponent: reference   Seed: 1337
  Ticks: 117/200   Winner: my_agent   Termination: last_agent_standing
  [Open Replay]
```

An initialization-failure test result and a tool/internal-error result
replace the "Development Test" result block with their own shapes (§12).

## 8. Create behavior ("New Agent")

1. **`New Agent…`** opens a minimal `QDialog` with exactly one input: a
   `QLineEdit` for `agent_id`, plus a static hint label built from the
   scaffold module's own constants —
   `battle_engine.agent_scaffold.AGENT_ID_PATTERN.pattern` and
   `MAX_AGENT_ID_LENGTH` — never a hand-duplicated copy of the regex text,
   so the hint cannot drift from the actual allow-list. No template
   picker, no description field, no version field: Phase 1's "one minimal
   canonical template" philosophy (`docs/specs/agent_scaffold.md` §1) is
   still current — nothing in Phases 2–3 or in the Designer's own
   architecture gives a reason to widen it.
2. On **OK**, call `battle_engine.agent_scaffold.create_agent(agent_id,
   data_root=self.battle_root)` directly, synchronously, on the GUI thread
   (§5).
3. **Success:** call the centralized `refresh_agents(select=agent_id)`
   (§20) so every combo (Simple, Advanced, Agent Development) repopulates
   and the Agent Development tab's own agent combo selects the new agent —
   matching by `AgentRow.name == agent_id`, which is exact for a freshly
   scaffolded agent because `agent_scaffold.py` never writes a `display`/
   `name` manifest field (§6 of `docs/specs/agent_scaffold.md`), so
   `AgentSpec.display` is always the directory basename for a scaffolded
   agent. Show a brief, non-modal success indication (e.g. a status-bar
   message or an inline label — not another blocking dialog) naming the
   two paths written.
4. **`AgentScaffoldError`** (invalid ID, duplicate ID) or **`OSError`**
   (unwritable data root): show inline in the dialog (a label, not a
   second modal `QMessageBox`) so the user can correct the ID and retry
   without re-opening the dialog; the dialog stays open until cancelled or
   successful.
5. No progress indicator is needed — `create_agent` is a handful of
   filesystem writes, already documented as completing "essentially
   instantly" (`docs/specs/agent_scaffold.md` §3.4).

## 9. External editing behavior

**Recommendation: Option A, `Open Agent Folder` only — not `Open Source`.**

`QDesktopServices.openUrl(QUrl.fromLocalFile(str(agent_dir)))` is already
the exact, proven, portable primitive this codebase uses for the identical
class of problem (`AgentDesigner._on_open_output_folder`,
`app/agent_designer.py:474`) — Qt already owns the Windows/Linux difference,
so no OS-specific subprocess logic is needed, satisfying the task's stated
preference directly.

**Why not also `Open Source` (opening `agent.py` directly):**
`QDesktopServices.openUrl` on a `.py` file delegates to the OS's file-type
association for `.py`. On a typical Windows machine with Python installed,
that association frequently **executes the script** (or launches whatever
IDE/interpreter is currently registered) rather than opening it in a text
editor — an unpredictable, per-machine outcome that is not "open a folder"
levels of safe. For a tool whose entire premise elsewhere in this document
is "unsandboxed user Python is dangerous to run casually," an action whose
Windows-default behavior can be "silently execute the file" is a
categorically worse risk than the filesystem-only "open folder" action.
`Open Agent Folder` gets the author to `agent.py` in one extra click with
zero execution risk; the marginal convenience of `Open Source` does not
justify that risk for Phase 4. This applies only to agents reachable
through the Agent Development tab's picker, which — per §3's discovery
model — are always real, on-disk, user-writable `<data_root>/agents/<id>/`
directories; there is no bundled/internal agent selectable through this
picker to special-case (the internal reference opponent used by `agents
test`, §3, is never discoverable via `resolve_agent`/`discover_agents` at
all, so it can never appear in this combo in the first place).

## 10. Validation behavior

### 10.1 Process construction

A new `battle_engine.launchers.build_agents_command(subcommand, arguments)`
function (small, Qt-free addition, mirroring `build_match_command`/
`build_tournament_command`/`build_replay_command` exactly) is the one piece
of new shared infrastructure this spec requires outside `app/`:

```python
def build_agents_command(subcommand: str, arguments: Sequence[str]) -> list[str]:
    """Build a non-shell command for a `bytefray agents <subcommand>` verb."""
    options = list(arguments)
    if is_frozen_application():
        return [str(_packaged_executable("battle2")), "agents", subcommand, *options]
    return [str(normalize_root(sys.executable)), "-m", "battle_engine",
            "agents", subcommand, *options]
```

(`agents create` is deliberately *not* routed through this — scaffold is a
direct call, §5/§8 — this builder exists only for `validate`/`test`.)

The Agent Development tab's `Validate` click builds
`build_agents_command("validate", [agent_id])`, starts it via the
**existing** `self._start_process(command, env, self.battle_root,
label="Validate")` (§2.6 — same method, same single-`self._proc` slot, same
stale-signal immunity, reused verbatim), with the identical child
environment construction already used for match launch (`PYTHONPATH`
extension for a source checkout; irrelevant for a frozen build where
`battle2.exe` is self-contained).

### 10.2 Output parsing — Option 1, not a new worker protocol

`agents validate`'s entire structured output surface is the small, fully
enumerable, already-versioned-by-convention `label: value` line contract
`docs/specs/agent_validation.md` §3.4 defines (four lines on success, four
or five on failure) — not organically-grown human prose. A small, private
parser (`app/services/agent_workflows.py`, new) reads this exact shape into
a typed presentation dataclass:

```python
@dataclass(frozen=True)
class ValidationPresentation:
    agent_id: str
    valid: bool
    api_version: int | None = None
    dry_run_action: str | None = None
    stage: str | None = None
    code: str | None = None
    error: str | None = None
    detail: str | None = None
```

**Why Option 1 (parse the documented CLI output) over Option 3 (a new
internal JSON worker protocol) for validation specifically:** a dry run
produces **no artifact file at all** by design (`docs/specs/agent_validation.md`
§1) — there is no canonical structured file to read instead, so *some*
parsing of process output is unavoidable regardless of architecture. Given
that, inventing a second, JSON-shaped, internally-versioned protocol to
carry the same five fields the CLI's stdout/stderr contract already commits
to keeping stable would be strictly more surface to build, test, and keep
in sync, for a payload too small to benefit from a general serialization
format. The existing contract already reads as machine-oriented, not
human-prose (`docs/specs/agent_validation.md`'s own text: "scripts can rely
on stdout being validation-result content only when the exit code is
`0`") — Phase 4 becomes the first "script," and the smallest robust
mechanism is a five-field line parser, not a new protocol.

### 10.3 Presentation

- **Valid:** status "Valid", `api_version`, `dry_run_action` verbatim (the
  task's own example: `WRITE operand=232 value=165`).
- **Agent authoring failure** (`AgentValidationFailedError`, exit `2`,
  parsed from stderr): render `stage`/`code`/`error`/optional `detail` as
  labeled fields, never a raw traceback (the CLI itself never emits one —
  nothing to strip). Visually: a plain "Invalid" status block, not an error
  dialog — this is a *result*, matching `agents validate`'s own exit-`2`
  convention meaning "the agent under test has a problem," not "the tool
  crashed."
- **Tool/internal failure:** distinguished from the above by exactly one
  existing signal — `code == "validation_internal_error"` — which the
  parser surfaces as a boolean `is_tool_failure` field on
  `ValidationPresentation` (or a `QProcess` start failure /
  `errorOccurred`, handled identically to today's `_on_proc_error`, §2.6).
  Rendered with a visually distinct (e.g. differently colored/iconed)
  status block from an ordinary "Invalid" result, but still inline — no new
  notification framework, matching the task's explicit "do not invent an
  elaborate notification framework" instruction. A `QMessageBox.critical`
  remains appropriate only for a process that failed to *start* at all
  (mirrors `_on_proc_error`'s existing behavior).

## 11. Development-test behavior

### 11.1 Options surface

Per §12's product framing, default behavior (`select agent → Test`) must be
useful with zero configuration. A small collapsible "Test Options" group
(matching the task's own suggestion) holds:

- **Opponent:** a combo, default "Reference" (maps to omitting `--opponent`
  entirely), else any other Python agent from the shared catalog (excluding
  the agent currently under test — the CLI does not forbid testing an agent
  against itself, but the Designer's picker can reasonably default the list
  to exclude it without forbidding the CLI's own permissive behavior if a
  reviewer prefers otherwise; not a hard requirement).
- **Seed:** integer field, default blank/placeholder showing `1337`
  (`Config().seed`) — blank means "omit `--seed`," not "send 0."
- **Ticks:** integer field, default blank/placeholder showing `200`.

`Test` builds `build_agents_command("test", [agent_id, *optional flags])`
and starts it identically to Validate (§10.1), with `label="AgentTest"`.

### 11.2 Output parsing and structured-artifact reuse

Unlike validation, a **completed** development test writes the exact same
canonical `result.json` a real match writes (§3). The parser therefore only
needs to extract the small set of `label: value` lines that identify
*which shape* occurred and, for the completed-match shape, the artifact
paths — then hands off to the **already-existing** `read_match_presentation`
(`app/services/designer_workflows.py`) for the authoritative
winner/termination/replay fields, exactly as ordinary match completion
already does. This is a direct, minimal reuse, not a parallel result model:

```python
@dataclass(frozen=True)
class DevelopmentTestPresentation:
    agent_id: str
    opponent: str | None = None
    outcome: Literal["completed", "initialization_failed", "tool_error"] = "completed"
    seed: int | None = None
    ticks_run: int | None = None
    ticks_requested: int | None = None
    match: MatchPresentation | None = None          # completed only, via read_match_presentation
    forfeits: tuple[str, ...] = ()                    # raw "forfeit: ..." lines, completed only
    stage: str | None = None                          # initialization_failed / tool_error
    code: str | None = None
    error: str | None = None
    detail: str | None = None
```

Three shapes to parse, all already fully specified in
`docs/specs/agent_test.md` §11 and stable by the same "scripts can rely on
stdout" convention as validation:

1. **Completed match** (stdout, exit `0`): parse `agent:`/`opponent:`/
   `seed:`/`ticks:`/`winner:`/`termination:`/zero-or-more `forfeit:`/
   `result:`/`replay:`/`summary:` lines. Then call
   `read_match_presentation(Path(parsed["result"]))` for the authoritative
   `winner`/`termination_reason`/`replay_path` — the parsed `winner:`/
   `termination:` text lines are used only as a fallback/cross-check, not
   the primary source, keeping the "read canonical files, not CLI text,
   wherever a canonical file exists" principle intact even though a small
   amount of text parsing remains unavoidable to *locate* that file (there
   is no `--output-dir` flag on `agents test`, and its `<run-label>`
   directory name is timestamp+random — see §14 for why this spec does not
   propose adding one).
2. **Initialization failure** (stdout, exit `0`): parse `agent:`/optional
   `opponent:`/`status: initialization_failed`/`stage:`/`code:`/`error:`/
   optional `detail:`/`result: none`/`replay: none`. No file to read —
   the CLI's own contract guarantees none exists (§3).
3. **Tool/internal failure** (stderr, exit `2`): parse `agent:`/
   `status: error`/`stage:`/`code:`/`error:`.

## 12. Diagnostic presentation

One shared convention across §10/§11, so a user cannot confuse the three
outcome kinds:

| Outcome | Visual treatment | Analogous existing Designer element |
|---|---|---|
| Valid / completed test (any tested-agent result, including forfeit/loss/death) | Neutral/positive result block, inline | `AdvancedPanel.show_result`'s existing result table |
| Invalid / initialization failed | Neutral-but-attention result block (this is a fact about the agent, not an error) | Same table styling, different heading text ("Invalid" / "Initialization failed") |
| Tool/internal failure | Visually distinct (e.g. warning-colored) inline block **and**, only if the process itself failed to start, a `QMessageBox.critical` exactly like `_on_proc_error` today | New, narrow addition — not a new framework |

No raw traceback is ever displayed in any of the three cases, because
`docs/specs/agent_validation.md`/`agent_test.md` already guarantee neither
CLI ever emits one for an expected failure category.

## 13. Replay behavior

**Reuse "Open Last Replay" unchanged; add a contextual "Open Replay" inside
the Agent Development tab's own test-result block, both ultimately calling
`open_pygame_client_direct`.** Do not make a development test's replay
silently become the global `self._last_replay` — a user who just ran a
match in the Advanced tab and then a development test in the Agent
Development tab should not have "Open Last Replay" in the Advanced tab
silently start pointing at the test's replay instead (surprising
cross-tab side effect). Concretely:

- `AgentDevelopmentPanel` owns its own `_last_test_replay: Path | None`,
  set only from a completed `DevelopmentTestPresentation.match.replay_path`,
  independent of `AgentDesigner._last_replay`.
- Its own "Open Replay" button calls the same
  `open_pygame_client_direct(self.battle_root, path)` primitive
  (§2.4) — no new replay-launch mechanism, no second implementation.
- `AgentDesigner._last_replay` (the Simple/Advanced "Open Last Replay"
  target) is **not** updated by a development test's completion — this is
  a deliberate scope boundary, not an oversight: a development test is
  authoring-loop feedback, conceptually separate from "the last match I
  ran to see results," and conflating them would surprise a user
  bouncing between tabs.

## 14. State model

| State | Controls disabled | Notes |
|---|---|---|
| **Idle** | none | Default. |
| **Creating** | `New Agent…`'s own OK button only, briefly | Synchronous; no global busy state needed (§8) — fast enough that a disabled-button flash is the only necessary affordance. |
| **Validating** | `Validate`, `Test`, `New Agent…`, agent combo (selection-change during a run would desync the in-flight process from the displayed agent) | `Stop` enabled. Match/Tournament launch in Simple/Advanced is **also** disabled during this state, and vice versa — see §14.1. |
| **Testing** | Same as Validating | Same shared-slot reasoning. |
| **Validation result (valid/invalid)** | none | Persists until agent selection changes or a new Validate/Test starts. |
| **Test result (completed, with or without replay)** | none | `Open Replay` enabled only when `match.replay_path` is set and exists. |
| **Test result (initialization failed)** | none | `Open Replay` never enabled (§3: no artifacts exist by construction). |
| **Tool/internal failure** | none | Distinct visual treatment (§12); does not clear a prior valid/completed result silently — see §14.2. |
| **Stopped (user-cancelled)** | none | Distinct "Stopped" status, never presented as any of the above outcome shapes (§23). |

### 14.1 Single shared process slot — no independent Agent Development process

Per §2.6, `self._proc` is one slot with strong existing stale-signal
guarantees. **Recommendation: Validate/Test share this exact slot with
Match/Tournament launch, rather than introducing a second, independent
`QProcess` owned only by `AgentDevelopmentPanel`.** A second slot would
either (a) allow a match and a development test to run concurrently,
reintroducing exactly the class of concurrent-run ambiguity
`_dispose_process`'s own docstring was written to eliminate, or (b) need
its own duplicate stale-signal-immunity machinery, a second thing to keep
in sync with `_dispose_process`'s carefully-reasoned pattern. Sharing the
slot means: `Match`/`Tournament`/`Validate`/`Test` are the four things that
can ever be "the current operation," exactly one at a time, and the
existing `setBusy(bool)` convention (`SimplePanel`/`AdvancedPanel`) extends
naturally to a new `AgentDevelopmentPanel.setBusy(bool)` that
`AgentDesigner` calls alongside the other two panels' `setBusy` calls on
every process start/finish.

### 14.2 Agent-selection change and stale results

Per §19, changing the selected agent in the Agent Development combo clears
both the validation and test result panels immediately (no filesystem
mtime check, no watcher) — a simple, sufficient rule matching the task's
own "a simple 'Last validation' label may be sufficient" guidance. A
**tool/internal failure** (§12's third row) is the one outcome that should
*not* be silently replaced by a subsequent successful run without at least
a brief transition — in practice this falls out naturally, since any new
Validate/Test click already fully replaces the previous result block
regardless of its kind; no special-casing is needed beyond "a new run's
result always replaces the previous one for that same operation kind"
(Validate results and Test results are tracked and cleared independently
of each other, since they answer different questions, §1).

## 15. Stale-result semantics

Adopting the task's minimal recommendation directly: every result block is
labeled **"Last validation"**/**"Last development test"**, not merely
"Validation"/"Test result" — making it visually explicit that the displayed
status describes a specific prior run, not necessarily the current state of
`agent.py` on disk. Combined with §14.2's "selection change clears results"
rule, this covers the task's worked example (validate → edit externally →
return) adequately: returning to the *same* agent still shows its last
result, correctly labeled as such, until the user clicks Validate/Test
again. No file-modification-time detection and no filesystem watcher are
introduced — both are explicitly out of scope per the task's own guidance
and are not justified by anything found in this investigation.

## 16. PygameCanvas decision

**Recommendation: continue deferring `PygameCanvas`; do not adopt it in
Phase 4, and do not treat it as "not yet wired" — it is not currently
functional against the renderer contract it depends on.**

Direct inspection of `client/src/battle_client/renderers/pygame_canvas.py`
finds it calls exactly four methods on a `PygameRenderer` instance:
`setup()` (once, in `showEvent`), `update()` (every 16 ms via a `QTimer`),
`on_complete()` and `teardown()` (both in `closeEvent`). Per
`ARCHITECTURE.md`'s own description of the actual current renderer
lifecycle, a renderer must be driven through
`setup → wait_for_start → [wait_until_ready → on_event → update]* →
on_complete → hold_open → teardown`, with `battle_client.player.ReplayPlayer`
as the only component in this codebase that drives that full lifecycle —
critically including `on_event`, the call that actually delivers each
replay record to the renderer. **`PygameCanvas` never calls
`wait_for_start`, `wait_until_ready`, or `on_event` at all** — it only ever
calls a bare `update()` in a timer loop with no replay data delivery
mechanism. Concretely, even if something in the Designer instantiated and
displayed a `PygameCanvas` today, no replay content would ever reach it —
it would show whatever `PygameRenderer.update()` renders with an empty/
initial internal state, indefinitely, regardless of which replay file the
Designer thinks it "opened." This is a stronger, more concrete answer than
"unused, so undecided":

1. **Does it currently work well enough to be considered for Phase 4?** No
   — it does not merely lack callers, it lacks the calls to
   `ReplayPlayer`'s own delivery lifecycle that would make it show a replay
   at all.
2. **Lifecycle/teardown risk of embedding Pygame in Qt?** Real and
   additional to the above: `pygame.display.init()` bound to a native Qt
   window ID (`SDL_WINDOWID`) via an OS-specific env var
   (`windib`/`x11` — no macOS branch at all) is exactly the kind of
   fragile, platform-coupled resource-lifecycle interaction Bytefray's own
   `AGENTS.md`/`ARCHITECTURE.md` elsewhere prefer to avoid where an
   already-working external-process alternative exists.
3. **Would it materially improve the create/validate/test loop?** No
   concrete gain was found: the loop's actual bottleneck today is
   iteration speed on validate/test feedback (§5/§10/§11), not the replay
   viewer's launch mechanism, which already works via the existing
   external Pygame subprocess (§2.4).
4. **Does it solve a Phase 4 requirement external launch does not?** No —
   nothing in §11/§13's development-test replay handoff needs an embedded
   view; "Open Replay" opening a separate, already-interactive external
   window is sufficient and consistent with the existing, working pattern.

Per the task's own instruction ("unless the answer to #4 is clearly yes,
recommend deferring it"), and given #1/#2 add concrete new reasons beyond
mere non-adoption, this spec recommends deferral, not merely "leave as is."

## 17. Platform/packaging considerations

### 17.1 Command construction

`build_agents_command` (§10.1) reuses `_packaged_executable`/
`normalize_root`'s existing frozen/source branching verbatim — no new
Windows/Linux conditional logic, no shell strings, argument lists only,
identical to every other `battle_engine.launchers` builder.

### 17.2 Folder opening

`QDesktopServices.openUrl(QUrl.fromLocalFile(...))` is already
cross-platform via Qt and already proven in this exact codebase
(`_on_open_output_folder`) — no OS-specific branch needed for §9.

### 17.3 Confirmed packaging blocker: `tools/agent_designer.spec`

Direct inspection of both `.spec` files finds `tools/battle2.spec` already
includes a `datas` entry for `battle_engine/data/agent_template/`
(landed, per `docs/specs/agent_test.md` §8.6, as part of Phase 3's own
implementation), but **`tools/agent_designer.spec` has no equivalent
entry** — only `assets/` and `battle_engine/data/starter_agents/` are
listed. Because §5/§8 recommends calling `agent_scaffold.create_agent`
**in-process, inside the Designer's own executable**, a frozen
`battle-agent-designer.exe` (built from this exact spec file) would fail
"New Agent" with a `FileNotFoundError` from `template_resource_dir` — the
identical class of bug `agent_test.md` §8.6 already found and fixed for
`battle2.exe`, now found a second time for the Designer's own frozen build.
**This is a required implementation-time fix, not an optional cleanup**:
whichever slice implements §8 ("New Agent") must add the identical `datas`
entry `tools/battle2.spec` already has:

```python
agent_template_dir = os.path.join(engine_src, "battle_engine", "data", "agent_template")
...
if os.path.isdir(agent_template_dir):
    datas.append((agent_template_dir, "battle_engine/data/agent_template"))
```

This does not affect a source checkout or a regular wheel install (both
already work, per §3's `get_resource_root()` tracing) — only the
standalone frozen Designer executable.

### 17.4 Validate/Test packaging

Both run through `build_agents_command`, which resolves a **sibling**
`battle2.exe` in a frozen build (`_packaged_executable`, identical to
existing match/tournament launch). This already works today for
match/tournament launch from the standalone Designer executable (same
mechanism, same sibling-executable assumption, already shipped and
smoke-tested per `ARCHITECTURE.md`'s packaging section) — Phase 4
introduces no new packaging risk for these two operations beyond what
already exists and is already validated by the Windows build's
deterministic frozen-GUI-import smoke test.

## 18. Error/exit semantics

Phase 4 introduces no new exit codes, diagnostic codes, or stages — it only
translates the existing ones (§3's table; `RuntimeDiagnostic.stage`/`.code`)
into GUI presentation (§12). The one new GUI-only concept is
`is_tool_failure`/`outcome` discriminators on the presentation dataclasses
(§10.2/§11.2), which exist purely to pick a rendering branch and are never
serialized, stored, or treated as a new canonical taxonomy.

## 19. Testing strategy

Following this repository's existing, already-established split exactly
(`engine/tests` for Qt-free logic; `tests/`, `gui`-marked, for real
`AgentDesigner` instantiation under `QT_QPA_PLATFORM=offscreen`; see
`tests/test_agent_designer_lifecycle.py`/`engine/tests/test_designer_workflows.py`
for the precise idioms reused below).

### 19.1 Pure helper/model tests (`engine/tests` or `app`-local, no `gui` marker, no Qt import required)

- `build_agents_command("validate"/"test", [...])` — frozen vs. source
  branching, argument order, no shell strings (mirrors existing
  `test_designer_workflows.py::test_tournament_command_validates_runtime_and_uses_supported_cli`).
- Validation-output parser: all documented success/failure line shapes from
  `docs/specs/agent_validation.md` §3.4, including the optional trailing
  `detail:` line present/absent.
- Development-test-output parser: all three documented shapes from
  `docs/specs/agent_test.md` §11 (completed with/without forfeits,
  initialization failure with/without an `opponent:` line, tool failure),
  fed literal example text from the spec itself.
- `DevelopmentTestPresentation` construction from a parsed "completed"
  shape plus a real `result.json` fixture, via the *actual*
  `read_match_presentation` (not a mock) — proves the reuse claim in §11.2
  directly.
- Centralized `refresh_agents(select=...)` selection logic against a fake
  multi-combo container (no real Qt widgets needed if this logic is
  extracted into a small pure helper — see §20).

### 19.2 PySide GUI tests (`tests/`, `@pytest.mark.gui`, `QT_QPA_PLATFORM=offscreen`, mirroring `test_agent_designer_lifecycle.py`'s direct-slot-call idiom — no real subprocess execution, no timing dependency)

- New Agent dialog: OK with a valid id calls `create_agent` and triggers a
  catalog refresh + selection (assert via monkeypatching `create_agent` to
  a stub returning a `ScaffoldResult`, exactly as existing tests
  monkeypatch/stub around `QProcess` rather than running a real one).
- New Agent duplicate/invalid id: inline error shown, dialog stays open,
  no catalog refresh triggered.
- Validate/Test button enable/disable transitions across Idle → Validating/
  Testing → result, and the cross-panel disable during those states
  (§14.1) — directly analogous to
  `test_current_process_finished_clears_busy_state`.
- Stale-process guards for Validate/Test `QProcess` signals, reusing
  `test_stale_process_signals_do_not_mutate_current_run_state`'s exact
  pattern with a `label="Validate"`/`"AgentTest"` process instead of
  `"RunMatch"`.
- Selection-change clears prior validation/test result panels (§14.2).
- Each of the presentation shapes from §12 renders the expected labeled
  fields (feed a canned `ValidationPresentation`/`DevelopmentTestPresentation`
  directly into the panel's own render method — no real process needed for
  this half of the test).
- `Open Replay` enablement exactly tracks `match.replay_path` existing vs.
  an initialization-failure/tool-failure result.

### 19.3 Process-construction tests

- `QProcess` command/environment construction for Validate/Test mirrors
  existing match-launch tests' coverage of spaces-in-data-root paths
  (`test_starter_agents.py`'s established convention, reused).
- A real, short-lived user Python agent (a Phase-1-scaffolded fixture,
  `agent_scaffold.create_agent` under `tmp_path`) run through an actual
  `bytefray agents validate`/`agents test` subprocess from a test, asserting
  the parser correctly reconstructs the same fields the engine-level
  `test_agent_validation.py`/`test_agent_test.py` suites already assert
  about the underlying service calls — an end-to-end proof the GUI's
  parser and the CLI's actual output never drift apart.
- If §23's Stop button is implemented: killing an in-flight Validate/Test
  `QProcess` reuses the exact `_dispose_process` mechanism already
  regression-tested in `test_dispose_process_disconnect_prevents_stale_finished_from_firing`.

### 19.4 Regression

- Existing Simple/Advanced match launch, Tournament launch, Replay Browser,
  and "Open Last Replay" behavior and their existing tests are unmodified
  by this addition — run unchanged as a regression check.
- Existing headless engine tests (`test_agent_scaffold.py`,
  `test_agent_validation.py`, `test_agent_test.py`) remain entirely
  GUI-independent; Phase 4 adds no dependency in the reverse direction
  (`battle_engine` must never import from `app`).

### 19.5 Manual smoke (Windows, packaged application)

1. Launch `battle-agent-designer.exe`; open the new **Agent Development**
   tab.
2. **New Agent** with a fresh id; confirm it appears, selected, in all
   three tabs' agent combos.
3. **Validate** the new agent (its unmodified template): confirm "Valid" /
   `WRITE operand=... value=165`.
4. **Development Test** with defaults: confirm a completed-match result,
   `Open Replay` enabled, and that clicking it opens the existing external
   Pygame viewer showing the same replay.
5. **Open Agent Folder**: confirm Windows Explorer opens the correct
   directory.
6. Edit `agent.py` externally to raise inside `reset()`; return to the
   Designer without restarting it; **Validate** again: confirm the
   `reset`-stage failure renders correctly and does not confuse the prior
   "Valid" result with the new "Invalid" one.
7. Repeat step 6 with a `--opponent` initialization failure and with an
   unknown `--opponent`, confirming the exit-`0`/exit-`2` distinction is
   visible in the UI (not just the process exit code).
8. Confirm a Simple-tab match launch is disabled while a development test
   is running, and vice versa.

## 20. Refresh/catalog semantics

`AgentDesigner.refresh_agents()` already centrally repopulates every
existing combo (§2.7); Phase 4 extends it with one optional parameter
rather than introducing a second refresh mechanism:

```python
def refresh_agents(self, *, select: str | None = None) -> None:
    rows = self.catalog.list_agents()
    names = [r.name for r in rows] or ["(none found)"]
    for panel in (self.simple, self.advanced, self.development):
        if hasattr(self, panel_attr_name):   # existing hasattr guard pattern preserved
            panel.setAgents(names)
    if select and hasattr(self, "development"):
        self.development.selectAgent(select)
```

This is the "one centralized catalog-refresh method" the task invites
consideration of — already 90% present in the existing code, extended
narrowly rather than rebuilt. No independent per-panel refresh timers or
watchers are introduced.

## 21. Explicitly deferred work (not part of Phase 4)

Restated from the task's own exclusion list, confirmed against this
investigation as still correctly excluded: an embedded source-code editor
or syntax highlighting, LLM-assisted generation, multiple scaffold
templates, Agent API v2, Python sandboxing or a runtime CPU timeout system,
live match spectating, mixed VM/Python matches, Redcode authoring or a
Redcode development-test GUI, tournament redesign, ratings/brackets, a
run-history browser for `runs/agents_test/<agent-id>/...`, replay-analysis
extraction (tracked separately, `docs/specs/replay_analysis.md`, untouched
by this task), `PygameCanvas` integration (§16), and any general
application redesign or web UI.

Additionally, **not adding a `--json`/machine-readable output mode or an
internal structured worker protocol to the public CLI** (§10.2/§11.2) — the
existing `label: value` contracts are sufficient and already
committed-stable; inventing a second protocol to carry the same five-to-ten
fields would be avoidable surface area, consistent with the task's own
caution against adding CLI surface "just to serve the GUI."

## 22. Risks

1. **Stdout/stderr contract drift.** The GUI's parser depends on the exact
   line shapes `docs/specs/agent_validation.md`/`agent_test.md` document.
   If a future change to `agent_validation.py`/`agent_test.py` alters that
   text without updating the parser, the GUI would silently mis-render
   (or fail to parse) a result. Mitigated by §19.3's end-to-end
   subprocess-based tests, which fail loudly on drift rather than only unit
   testing the parser against frozen example strings.
2. **Frozen-build packaging gap (§17.3)** is a concrete, verified blocker
   that must be fixed in the same slice that implements "New Agent," or
   "New Agent" ships broken in the standalone Designer executable exactly
   as `agents create` was found broken in `battle2.exe` for Phase 3.
3. **Shared single-process-slot contention (§14.1)** means a long-running
   development test blocks a user from launching an ordinary match in
   Simple/Advanced until it finishes or is stopped. This is a deliberate
   simplicity/safety tradeoff (§14.1's reasoning), not an oversight, but is
   worth confirming with a reviewer since it is a real, user-visible
   behavior change in the "can I run two things at once" sense (today,
   Match and Tournament already share this same constraint, so Phase 4
   does not introduce a new *kind* of restriction, only two new operations
   subject to the existing one).
4. **Un-sandboxed validate/test remains true after Phase 4.** Nothing in
   this spec makes a hung agent's `QProcess` any easier to detect
   automatically (no timeout is added, per explicit non-goal, §21) — a user
   who does not notice a stuck "Testing…" state and does not click Stop
   (§23) is in the identical position as a CLI user who does not Ctrl+C.

## 23. Design decisions needing human approval

1. **Stop/Cancel button for Validate/Test (recommended: yes, low-risk to
   add).** Because Validate/Test share the existing `self._proc` slot and
   `_dispose_process` already implements an unconditional `kill()` with
   full stale-signal immunity (§2.6), adding a `Stop` button to the Agent
   Development tab requires **no new process-management code** — it can
   call the exact same method the existing Simple/Advanced `Stop` buttons
   already call. The one new user-facing state is "Stopped," which must
   render distinctly from "Valid"/"Invalid"/"Tool failure"/"Initialization
   failed" (§14) and must never be presented as if a match completed
   (a killed `agents test` process cannot leave a success-shaped
   `result.json` behind, per `NativeMatchService`'s atomic-publish
   discipline — `ARCHITECTURE.md` — so there is nothing to accidentally
   mis-present as a completed result). This spec recommends including it
   in Phase 4c (§26) since the marginal implementation cost is genuinely
   small, but flags it as approval-worthy because it is new *UI*, not
   because it is architecturally risky.
2. **Exact wording/placement of the "Test Options" disclosure (§11.1)** —
   a collapsible group vs. always-visible three-field row. Either is
   consistent with this spec; left as an implementation-time visual choice
   for whichever slice builds it, per the task's own "avoid overspecifying
   cosmetic details" guidance.
3. **Whether to exclude the agent-under-test from its own `--opponent`
   picker (§11.1).** The CLI permits self-play; the Designer's picker could
   either allow or hide it. Recommended: allow it (do not narrow CLI-
   permitted behavior in the GUI without a concrete reason), but flagged
   since a reviewer may reasonably prefer hiding it to reduce confusion.
4. **Whether the pre-existing "Agent Params" dead-wiring bug (§2.8) should
   be fixed opportunistically alongside Phase 4, or left as a separate,
   later fix.** This spec recommends treating it as a **later roadmap
   item** (§28) — it is a real, independent defect, but fixing it touches
   `_on_advanced_run`/`build_designer_match_arguments`, neither of which
   Phase 4 otherwise needs to change, and conflating the fix with the new
   Agent Development tab's PR would make that PR's diff harder to review
   for its actual purpose.

## 24. Completion criteria

Phase 4 (across the slices in §26) is complete when:

- An author can create, validate, development-test, and open the replay
  for a new Python agent entirely from the Designer, matching
  `docs/AGENT_AUTHORING.md`'s documented CLI workflow step for step, with
  no functionality gap versus the CLI for any of the four operations'
  success/failure shapes documented in Phases 1–3's specs.
- No Phase 1–3 semantic (agent ID rules, validation stage/diagnostic
  codes, test exit-code/artifact rules) has been reimplemented,
  reinterpreted, or forked by the GUI layer — every fact the GUI displays
  is read from the exact same typed service results or canonical artifact
  files the CLI itself produces and consumes (§3, §34 of the parent task).
- The frozen `battle-agent-designer.exe` packaging gap (§17.3) is fixed as
  part of whichever slice ships "New Agent."
- Existing Simple/Advanced/Tournament/Replay Browser/"Open Last Replay"
  behavior is provably unregressed (§19.4).
- The test plan in §19 is implemented at the layer appropriate to each
  claim (pure logic headless, GUI behavior `gui`-marked, process
  construction and real-subprocess behavior each independently covered).

---

## 25. Implementation slices

Sliced along the same operation/risk boundaries §5 already established,
each independently reviewable and each leaving the Designer in a fully
working state if no further slice lands immediately after.

### Phase 4a — UI foundation, catalog refresh, New Agent, Open Folder

**Files touched:** `app/views/development.py` (new),
`app/agent_designer.py` (add tab, centralize `refresh_agents`, wire New
Agent/Open Folder), `tools/agent_designer.spec` (packaging fix, §17.3).

**Responsibilities:** `AgentDevelopmentPanel` shell with agent combo +
Refresh/New Agent/Open Folder controls only (no Validate/Test yet); New
Agent dialog calling `agent_scaffold.create_agent` directly; centralized
`refresh_agents(select=...)`.

**Tests:** §19.1's refresh/selection helper tests; §19.2's New Agent dialog
tests (success, duplicate, invalid id, selection-after-create); a
Designer-startup regression test confirming the third tab is present and
does not break existing tab construction's `try/except` isolation.

**Explicit non-goals:** no Validate/Test UI yet (buttons may exist but
disabled, or simply absent until 4b/4c land) — this slice is purely
catalog/creation/navigation.

**Completion criteria:** an author can create an agent from the GUI and see
it selected everywhere, and open its folder — nothing else changes.

### Phase 4b — validation workflow

**Files touched:** `engine/src/battle_engine/launchers.py`
(`build_agents_command`), `app/services/agent_workflows.py` (new — output
parser + `ValidationPresentation`), `app/views/development.py` (Validate
button, result rendering), `app/agent_designer.py` (wire Validate through
`_start_process`, extend `setBusy` cross-panel disabling, §14.1).

**Responsibilities:** subprocess-based validate execution; parsing;
presentation; stale-result clearing on selection change (§14.2/§15 for
validation only).

**Tests:** §19.1's validation-parser tests; §19.2's Validate button-state
and presentation-rendering tests; §19.3's real-subprocess validate test.

**Explicit non-goals:** no development-test UI yet; no Stop button yet
(§23 item 1 can land here or in 4c — either is coherent, since both share
identical mechanics).

**Completion criteria:** an author can validate an agent from the GUI and
see the exact CLI-equivalent Valid/Invalid/tool-failure presentation.

### Phase 4c — development-test workflow

**Files touched:** `app/services/agent_workflows.py` (extend with
`DevelopmentTestPresentation` + its three-shape parser, reusing
`read_match_presentation`), `app/views/development.py` (Test Options,
Test/Stop buttons, result rendering including forfeit lines), possibly
`app/agent_designer.py` (Stop wiring if not already generalized in 4b).

**Responsibilities:** subprocess-based test execution with options;
parsing all three outcome shapes; canonical-`result.json` reuse for the
completed-match shape; Stop button (§23 item 1) if not already added.

**Tests:** §19.1's test-output-parser tests (all three shapes) and the
`DevelopmentTestPresentation`-from-real-`result.json` reuse test; §19.2's
Test button-state, options, and all-three-outcome-shape rendering tests;
§19.3's real-subprocess test and (if Stop lands here) the kill/stale-signal
test.

**Explicit non-goals:** no run-history browsing of prior
`runs/agents_test/<agent-id>/...` directories (§21).

**Completion criteria:** an author can development-test an agent from the
GUI and see the exact CLI-equivalent completed/initialization-failed/
tool-failure presentation, matching `docs/AGENT_AUTHORING.md`'s documented
output shapes field-for-field.

### Phase 4d — replay handoff, stale-result polish, documentation

**Files touched:** `app/views/development.py` (contextual Open Replay
wiring, §13), `docs/AGENT_AUTHORING.md` (document the GUI workflow
alongside the existing CLI one), `docs/MANUAL_SMOKE_TESTS.md` (add §19.5's
sequence), `CHANGELOG.md`.

**Responsibilities:** contextual "Open Replay" tied to
`AgentDevelopmentPanel`'s own last-test-replay state (§13); "Last
validation"/"Last development test" labeling polish (§15); manual smoke
documentation; user-facing documentation of the now-complete GUI loop.

**Tests:** §19.2's Open Replay enablement tests; §19.4's full regression
pass across all four tabs.

**Explicit non-goals:** no new functionality — this slice is integration
polish and documentation only.

**Completion criteria:** the full create → validate → test → replay →
modify → repeat loop is usable end to end from the Designer, documented,
and manually smoke-tested on Windows per §19.5.

---

## Appendix: findings classification (task §28)

**Phase 4 blockers:**
- `tools/agent_designer.spec` missing the `agent_template` `datas` entry
  (§17.3) — must be fixed in the slice that implements "New Agent" (4a).

**Phase 4 opportunistic cleanups:**
- None identified that are both small and directly useful to this specific
  implementation beyond the centralized `refresh_agents` extension already
  folded into §20/4a (which is sized as part of the feature, not a
  separate cleanup).

**Later roadmap items:**
- ~~`AdvancedPanel`'s "Agent Params" tab is completely disconnected from the
  actual match-launch path (§2.8) — a genuine, pre-existing bug, unrelated
  to agent authoring, left for a separate fix.~~ **Resolved** in a later
  post-1.0 maintenance pass — see the "Resolved" note under §2.8.
- `app/services/agents.py`'s unused `AgentCatalog` and
  `app/services/agent_meta.py`'s unused `read_agent_meta` (§2.7) — dead
  code, harmless, candidates for removal in an unrelated cleanup pass.
- `app/services/engine.py`'s `EngineRunner` (Popen+threading match runner)
  is entirely dead code superseded by the QProcess path in
  `app/agent_designer.py` (§2.9) — candidate for removal in an unrelated
  cleanup pass, not touched here since Phase 4 does not depend on it either
  way.

**Ignore:**
- `app/main.py`/`app/match_runner.py` — already correctly documented as
  stale/dead in `ARCHITECTURE.md`; out of scope for this investigation and
  not re-litigated here.
