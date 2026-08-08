# agent_test

**Module:** `engine/src/battle_engine/agent_test.py` (new), with a small,
precisely-scoped export-visibility change inside
`engine/src/battle_engine/agent_scaffold.py` (see §5).
**Purpose:** `bytefray agents test <agent-id>` — a short, deterministic,
*real* Bytefray match for agent development, using the exact production
match machinery (`NativeMatchService`) and canonical result/replay
generation, against either a built-in reference Python opponent or another
discovered Python agent.

## 0. Relationship to v0.4

This is **Phase 3** of v0.4's Agent Authoring & Development Feedback Loop
theme (`ARCHITECTURE.md`'s "v0.4 direction": create → validate → test →
inspect → modify → repeat). Phase 1
(`docs/specs/agent_scaffold.md`, implemented) added
`bytefray agents create <agent-id>`. Phase 2
(`docs/specs/agent_validation.md`, implemented) added
`bytefray agents validate <agent-id>`, a single-tick dry run of the Agent
API v1 contract. Nothing this document describes is implemented yet; this
is a specification only, written before implementation per
`CONTRIBUTING.md`'s spec → issue → prompt → PR flow.

`agents validate` answers "can the agent satisfy one Agent API lifecycle
call?" `agents test` answers a different question: "can the agent execute
through real Bytefray match semantics for a useful short development run,
and what happened?" It is not a second, deeper validator — it is a real
match, run through the same `NativeMatchService` boundary every other
native match uses, producing the same canonical `replay.jsonl`/
`result.json`/`summary.json` artifacts `bytefray run` produces. GUI test
controls, live viewing, tournament execution, and replay-analysis
extraction are explicitly out of scope (§12).

## 1. Purpose and non-goals

**Purpose.** Provide one CLI operation, `bytefray agents test <agent-id>`,
that:

- discovers the agent under test the same way `bytefray run`/`bytefray
  tournament`/`agents validate` do (`battle_engine.agents.resolve_agent`),
  and confirms it is `kind: python` (mixed VM/Python matches remain
  unsupported everywhere in this codebase — `AGENT_AUTHORING.md`);
- resolves an opponent — by default, an internal, non-writable, always-valid
  reference Python opponent built from the Phase 1 scaffold template
  resource; or, with `--opponent <agent-id>`, another discovered Python
  agent (§8);
- runs the two entrants through **the exact production path**,
  `battle_engine.match_service.NativeMatchService`, with a short,
  development-oriented default tick budget (200 ticks, §7) and the
  project's existing default seed (1337, §6), both overridable;
- writes the same three canonical artifacts every other native match
  writes — `replay.jsonl` (schema v3), `result.json` (`battle2.result` v1),
  and `summary.json` — under a dedicated, collision-free location beneath
  the writable data root (§9), never inventing a test-only result or
  replay format;
- reports a concise, `label: value` outcome — including the tested agent's
  own runtime diagnostic if it forfeited, died, or otherwise failed — and
  exits `0` for any outcome that is a fact about a *completed* match,
  reserving a distinct exit code for tool/infrastructure failures that
  prevented a match from running at all (§10);
- never automatically opens a replay viewer: on success, it prints the
  replay path and a suggested `bytefray replay <path>` command, keeping
  **test** and **inspect** distinct development-loop stages (§0's journey).

**Non-goals** (see also §12, "Explicitly out of scope"):

- A second simulation path, a test-only result/replay shape, or a
  test-only diagnostic taxonomy. Every fact this command reports is read
  off the exact `NativeMatchResult`/canonical replay/`RuntimeDiagnostic`
  objects a real `bytefray run` invocation already produces.
- Proving the agent is competitive, or that it will behave identically on
  a longer match, a different seed, or against a different opponent. A
  200-tick development test against one fixed reference opponent is a
  useful, fast feedback signal, not a tournament result.
- Sandboxing, hard timeouts, or process containment for a hung `act()`/
  `reset()` — no such facility exists anywhere in this codebase yet
  (`docs/AGENT_AUTHORING.md`'s "Not yet implemented" list), and Phase 3
  does not add one.
- Multiple built-in opponent strategies, tournament execution, or replay
  analysis/inspection tooling (§12).

## 2. Existing building blocks this spec reuses

Inspected before writing this spec (all under `engine/src/battle_engine/`
unless noted):

- **`match_service.py`** — `NativeMatchService.run(MatchRequest)` is the
  canonical execution/orchestration boundary for every native match
  (`ARCHITECTURE.md`). It:
  1. rejects mixed VM/Python compositions, missing bytecode/Python specs,
     or duplicate entrant IDs (`UnsupportedMatchCompositionError`) before
     anything runs;
  2. routes an all-Python request through `PythonEntrantController.run()`
     (`python_runtime.py`);
  3. calls `_finalize_native_artifacts` to compute the canonical
     `match_id`/`result_id`, rewrite the intermediate replay into typed
     `battle_engine.replay` schema-v3 records, and atomically publish
     `replay.jsonl` + `result.json` at the requested path, with a SHA-256
     replay digest recorded in `result.json`'s `replay` reference.
  Phase 3 builds one `MatchRequest` with two Python `MatchEntrant`s and
  calls this exact method — nothing else. `NativeMatchResult` (`winner`,
  `ticks_run`, `agents: tuple[NativeAgentResult, ...]`,
  `termination_reason`, `replay_path`, `result_path`) already carries
  everything the output contract (§10) needs; `NativeAgentResult.name`
  already carries whatever discovery-facing name the caller assigned each
  slot at `MatchEntrant` construction time — the identity-mapping
  mechanism this spec's output contract depends on (§11) is not new, it
  already exists and is already how `bytefray run` names Python entrants
  in `result.json`/the replay header's `entrants` list (`cli.py`'s
  `MatchEntrant.python("A", nameA, startA, pythonA)`).
- **`cli.py`** — `main()` is the concrete precedent for "resolve two
  Python `AgentSpec`s, build two `MatchEntrant`s, call
  `NativeMatchService().run(...)`, then hand-build `summary.json`
  yourself" — `NativeMatchService`/`_finalize_native_artifacts` publish
  `replay.jsonl`/`result.json` but **never write `summary.json`**;
  `cli.py`'s own `main()` builds and writes that compatibility file itself
  after `NativeMatchService().run(...)` returns. Phase 3 follows the
  identical division of responsibility (§9 shows the exact shape reused).
  `cli.py` also shows the exact exception set a Python match can raise out
  of `NativeMatchService().run(...)`:
  `UnsupportedMatchCompositionError`, `PythonEntrantInitializationError`
  (raised **before** tick zero — no replay/result/summary exist),
  `PythonMatchExecutionError` (an engine/artifact-write failure **during**
  or after execution). Phase 3 catches the identical three, with a
  materially different exit-status decision for
  `PythonEntrantInitializationError` depending on *which slot* failed
  (§8, §10) — every other repository caller (`cli.py`, tournament
  execution) treats any `PythonEntrantInitializationError` as one uniform
  tool failure; Phase 3 is the first caller that needs to distinguish "the
  agent under test failed to initialize" (a completed development test,
  exit `0`) from "the opponent failed to initialize" (a tool problem, exit
  `2`) — see §8.3 for why this distinction is possible without any change
  to `python_runtime.py`.
- **`python_runtime.py`** — `PythonEntrantController` is the exact runtime
  `NativeMatchService` already delegates to for an all-Python match; Phase
  3 never constructs or calls it directly. `PythonEntrantInitializationError.
  diagnostic` and a forfeited `NativeAgentResult.diagnostic` are both
  `RuntimeDiagnostic` instances whose `agent_id`/`slot` fields already
  carry the *runtime slot* (`"A"`/`"B"`, `0`/`1`) that failed or forfeited
  — never a discovery ID. `agent_validation.py`'s `_display_message`
  (uncommitted at the time of this spec — see `git status`) is the direct,
  already-implemented precedent for "rewrite a shared diagnostic's
  synthetic slot identity to the caller's real discovery ID for display,
  without touching the underlying `RuntimeDiagnostic`" — §11's identity
  mapping follows the identical pattern, one level up (mapping a full
  match's two slots, not one fixture's single slot).
- **`agent_api.py`** — `load_python_agent(agent_spec)` only ever reads
  attributes off `agent_spec` via `getattr`/direct access
  (`kind`, `api_version`, `entry_point`, `dir`, `name`, `display`,
  `version`); it has no dependency on the spec having come from
  `discover_agents`/`resolve_agent`. This is what makes §8's manually
  constructed reference-opponent `AgentSpec` (pointing at a package
  resource directory outside `<data_root>/agents/`) work with the
  production loader unmodified — confirmed by direct inspection of
  `load_python_agent`'s body, not assumed. **No existing test in this
  repository constructs an `AgentSpec` by hand** (`grep AgentSpec(` across
  `engine/tests` and `engine/src` finds only the dataclass's own
  definition in `agents.py`) — this is a genuinely new call pattern for
  this codebase, not a copy of an established test idiom, even though it
  is a straightforward, directly-verified consequence of how the loader
  is written.
- **`agent_scaffold.py`** — `_template_resource_dir(resource_root)` locates
  the bundled `battle_engine/data/agent_template/` resource directory
  (holding the exact static `agent.yaml`/`agent.py` pair `bytefray agents
  create` copies), trying a source-checkout-relative path and an
  installed-package-relative path, exactly mirroring `starters.py`'s
  `_starter_resource_dir`. Phase 3 reuses this exact function (promoted
  from private to a small public re-export, §5) rather than re-deriving
  the same two-candidate-path lookup a third time.
- **`paths.py`** — `get_data_root()` (writable root: agents, runs, replays)
  and `get_resource_root()` (read-only application resource root: source
  checkout, installed wheel, or PyInstaller `_MEIPASS`) are the same two
  resolvers every other subcommand already uses; Phase 3 introduces no new
  root-resolution logic.
- **`config.py`** — `Config()`'s dataclass defaults: `arena_size=4096`,
  `instr_per_tick=8`, `seed=1337`, `win_mode="score_fallback"`. Confirms
  the task's assumption that 1337 is the current canonical default seed
  (§6).
- **`agents.py`** — `resolve_agent(root, name)` is reused unchanged for
  both the agent under test and a `--opponent`-supplied opponent; it
  already raises `SystemExit` for an unknown or path-escaping name, the
  exact pattern `agent_validation.py`'s discovery stage already catches
  (§8.4 reuses the identical catch).
- **`result_model.py`** — `ResultEnvelope`/`write_json_atomic`/`stable_id`
  are used internally by `_finalize_native_artifacts`; Phase 3 does not
  call them directly (it calls `NativeMatchService().run(...)`, which
  calls them), but reading them confirms `result.json`'s schema is fixed
  and versioned (`battle2.result` v1) and is not altered by this spec.
- **`replay.py`** — `ReplayHeader.entrants`/`MatchResult.entrants` are
  `tuple[Mapping[str, Any], ...]`, each entry built by
  `_finalize_native_artifacts` from `NativeAgentResult` and already
  including `agent_id` (slot), `name` (discovery-facing identity), `alive`,
  `score`, `termination_reason`, `diagnostic`, `statistics`, `metadata`.
  Confirms §11's identity mapping needs no replay/result schema change:
  the `name` field already exists and is already populated from
  `MatchEntrant.name` for every native match, VM or Python.
- **`tournament_service.py`** — `_safe_name(value)`
  (`re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "entrant"`) is
  the existing precedent for sanitizing an arbitrary agent ID into a
  filesystem-safe path segment, reused by §9's artifact-directory naming
  for the `--opponent` value. No existing code in this repository
  constructs a *timestamped* run directory anywhere (`grep
  datetime|strftime|utcnow` across `engine/src/battle_engine` finds
  nothing) — §9's collision-avoidance scheme is new, not a reused pattern,
  and is flagged for review in §14.
- **`tools/battle2.spec`** (PyInstaller) — **discovered packaging gap,
  not merely inspected for confirmation.** `datas` explicitly lists
  `battle_engine/data/starter_agents` but has no equivalent entry for
  `battle_engine/data/agent_template`. This means **Phase 1's own
  `bytefray agents create` is already broken in the shipped frozen Windows
  build** (`battle2.exe`, the only executable that exposes `bytefray
  agents ...` — `battle-cli`/`tools/battle_cli.spec` dispatch straight to
  `cli.py`'s `run` argparse entry point and never reach `command.py`'s
  `_agents`; `tools/agent_designer.spec`/`tools/replay_viewer.spec` are
  unrelated GUI entry points). Phase 3's reference opponent depends on the
  identical resource directory being present in a frozen build, so this
  is not a new problem Phase 3 introduces, but Phase 3 cannot silently
  assume it is already solved — see §8.5 and §14 item 5.
- **Tests inspected:** `engine/tests/test_native_match_service.py` (the
  `NativeMatchService`-usage-proof idiom this spec's own architectural
  test follows — mocking/monkeypatching a controller method and asserting
  it was actually invoked, e.g.
  `test_service_is_identical_to_former_direct_kernel_orchestration`),
  `engine/tests/test_battle2_command.py` (`test_cli_python_act_failure_is_
  structured_without_traceback` — the load-bearing existing proof that a
  real match's entrant forfeit already returns CLI exit `0`, not `2`, in
  this codebase today; `test_cli_rejects_mixed_vm_python_without_traceback`
  for the tool-failure/exit-`2`/no-traceback convention;
  `test_agents_command_initializes_starters_idempotently` for the
  subprocess CLI test idiom), `engine/tests/test_output_paths.py` (the
  "explicit vs. default replay path, relative-to-cwd vs.
  relative-to-data-root, stale-artifact cleanup" test idiom §9/§13 follow),
  `engine/tests/test_agent_scaffold.py`/`test_agent_validation.py` (CLI
  test conventions, custom-data-root idiom), `engine/tests/
  test_python_runtime.py` (`validate_action`/forfeit-diagnostic coverage
  reused unchanged by the real match this spec runs).

## 3. Command/API surface

### 3.1 Exact CLI syntax

```text
bytefray agents test <agent-id> [--opponent <agent-id>] [--seed <int>] [--ticks <n>]
```

`battle2 agents test <agent-id> ...` behaves identically (the existing
`battle2_main` deprecation-notice wrapper already applies uniformly to
every subcommand).

### 3.2 Dispatch — extends `_agents`, mirroring `create`/`validate`

```python
def _agents(argv: list[str]) -> int:
    if argv and argv[0] == "create":
        from battle_engine.agent_scaffold import main as scaffold_main
        return scaffold_main(argv[1:])
    if argv and argv[0] == "validate":
        from battle_engine.agent_validation import main as validate_main
        return validate_main(argv[1:])
    if argv and argv[0] == "test":
        from battle_engine.agent_test import main as test_main
        return test_main(argv[1:])
    if argv == ["--help"] or argv == ["-h"]:
        return _simple_help("agents", ...)  # mentions list, create, validate, test
    if argv:
        parser = argparse.ArgumentParser(prog="bytefray agents", add_help=False)
        parser.error(f"unrecognized arguments: {' '.join(argv)}")
    from battle_engine.cli import main as engine_main
    return engine_main(["--list-agents"])
```

Bare `bytefray agents` and `bytefray agents --help`/`-h` are unchanged in
behavior (existing tests keep passing unmodified); only the help text
gains a one-line mention of `test`. `battle_engine.agent_test.main(argv)`
owns its own small `argparse` parser (`prog="bytefray agents test"`, one
required positional `agent_id`, three optional flags), mirroring
`agent_scaffold._parser()`/`agent_validation._parser()` exactly.

`test` is a verb on the agent catalog, the same conceptual level as
`create`/`validate`/the bare-`agents` list — not a new top-level command,
for the identical reasoning `agent_scaffold.md` §3.2 already gives (not
repeated here).

### 3.3 Flags

| Flag | Type | Default | Semantics |
|---|---|---|---|
| `agent_id` (positional) | `str` | required | Discovery ID of the agent under test, resolved exactly as `bytefray run --a-type`/`agents validate` resolve one. |
| `--opponent <agent-id>` | `str` | internal reference opponent | Discovery ID of another discovered Python agent to use instead of the built-in reference. Resolved via `resolve_agent`, identical to the agent under test. |
| `--seed <int>` | `int` | `Config().seed` (currently `1337`) | Same parsing as `bytefray run --seed` (`type=int`, no extra range constraint) — this is a genuine reuse of the *value*, not a re-derivation; `agent_test.py` imports nothing from `cli.py`, it constructs its own `Config(seed=...)` the same way `cli.py`'s own `cfg_kwargs["seed"]` branch does. |
| `--ticks <n>` | positive `int` | `200` | Same validator as `bytefray run --quota`/the CLI's own `_positive_int` (`ArgumentTypeError` for `<= 0`), applied here to a genuinely new default rather than reusing `run`'s `--ticks` default of `3000`. |

No `--data-root` flag (env-var override only:
`BYTEFRAY_ROOT`/`BATTLE2_ROOT`/`BATTLE_ROOT`), matching
`agent_scaffold.py`/`agent_validation.py`'s existing precedent
(`agent_validation.md` §12/§14 item 5).

No `--arena`, `--quota`, `--win-mode`, `--a-start`/`--b-start`, or any of
`bytefray run`'s agent-parameter flags (`--byte`, `--offset`, etc.) — a
development test is deliberately narrower than a full `run` invocation;
every entrant uses `Config()`'s own defaults for everything except `seed`,
and both entrants start at `0`, matching `cli.py`'s own
`--a-start`/`--b-start` defaults for a Python-vs-Python match with no
override. Widening this flag surface later is a natural, additive
extension, not something this phase needs to anticipate.

### 3.4 Exit codes

See the full matrix in §10.4; summarized here for the CLI-surface section:

**Approved correction (post-implementation review):** an explicitly
selected `--opponent`'s own initialization failure is exit `0`, not `2` —
see the resolution of design decision 3 in §14 and the corrected §8.5/
§10.3/§10.4/§11 below. Only the *internal bundled* `reference` opponent's
initialization failure remains exit `2`, since it alone is Bytefray-owned
infrastructure rather than user-provided agent code under evaluation.

| Condition | Exit code |
|---|---|
| Completed real match (any tested-agent outcome, including forfeit/loss/death) | `0` |
| Tested agent's own initialization failure (before tick zero) | `0` |
| Explicit `--opponent`'s own initialization failure (before tick zero) | `0` |
| `--help`/`-h` | `0` |
| Missing/extra positional arguments, invalid `--ticks`/`--seed` (argparse usage error) | `2` |
| Unknown/non-Python test agent or opponent | `2` |
| Internal bundled `reference` opponent's initialization failure | `2` |
| Any other tool/infrastructure failure (§10.4) | `2` |

### 3.5 stdout/stderr behavior

Split purely on exit code, matching `agent_validation.py`'s convention
exactly: **exit `0` → stdout only; exit `2` → stderr only, no raw
traceback.** This holds even though a tested-agent initialization failure
is "failure-shaped" diagnostic text — it is exit `0`, so per this
convention it goes to stdout, not stderr, consistent with "an agent
failure inside a successfully executed development test is a test result,
not a tool failure" applying to the *stream* choice too, not only the exit
code (scripts can rely on stdout containing test-result content whenever
the exit code is `0`, exactly as `agent_validation.py`'s docstring already
promises for its own stdout).

No progress/spinner output beyond the match's own optional per-tick print
(§8.2 sets `verbose=False` unconditionally — a 200-tick development test
does not need `bytefray run`'s periodic `[T00050] alive=...` lines; this
command defines its own, more concise post-match summary instead).

## 4. Product framing (restated precisely)

`agents validate` and `agents test` ask genuinely different questions and
must not be confused with each other in documentation or error messages:

| | `agents validate` | `agents test` |
|---|---|---|
| Question | Can the agent satisfy one Agent API lifecycle call? | Can the agent execute through real match semantics for a short development run, and what happened? |
| Execution | One `reset()`, one `act()`, no VM, no arena, no opponent. | A real `NativeMatchService`/`PythonEntrantController` match, up to 200 ticks, against a real opponent. |
| Artifacts | None — a dry run produces no replay/result. | Canonical `replay.jsonl`/`result.json`/`summary.json`, identical in shape to `bytefray run`'s. |
| A forfeit/exception in the checked callback | The one validation failure reported — validation itself failed. | One entrant's outcome within an otherwise successfully executed match — the *test* still succeeded. |

## 5. The one required change outside `agent_test.py`

`agent_scaffold.py`'s `_template_resource_dir` is renamed to
`template_resource_dir` (leading underscore dropped) and added to a new
`agent_scaffold.__all__` (the module currently has no `__all__`; one is
added: `__all__ = ["AgentScaffoldError", "ScaffoldResult", "create_agent",
"template_resource_dir", "validate_agent_id", "main"]`). No behavior
changes — this is a pure visibility/reuse change, the same class of
"smallest safe extraction" `agent_validation.md` §5 already used for
`python_runtime.py`'s four `diagnose_*` functions, and for the identical
reason: so `agent_test.py` calls the *exact* function
`agent_scaffold.py` uses to locate the bundled template directory, rather
than a second, independently-maintained copy of the same two-candidate-path
lookup. `create_agent`'s own call site (`_template_resource_dir(resources)`
inside `create_agent`) is updated to call it by its new public name;
existing tests referencing the old private name (if any —
`test_agent_scaffold.py` should be checked at implementation time) are
updated to match.

## 6. Seed

Default: `Config().seed` — currently `1337`, confirmed by direct read of
`config.py` (§2). `--seed <int>` overrides it with `bytefray run
--seed`'s exact parsing semantics (plain `type=int`, no extra validation).
The effective seed is always echoed in the output contract (`seed:
<value>`, §11) so a development run's exact reproduction command is always
visible without needing to open `result.json`.

## 7. Tick duration

Default: **200 ticks** — a development-loop default distinct from
`bytefray run --ticks`'s own default of `3000`. `--ticks <n>` overrides it
with the identical positive-integer validator `bytefray run`'s own
`--quota` flag already uses (`_positive_int`; `agent_test.py` defines its
own copy of this three-line validator rather than importing a private
name from `cli.py` — importing a leading-underscore name across modules is
the kind of coupling this repository avoids elsewhere, and the validator
is three lines with no state).

200 is explicitly a **development-loop** default, not a proposed new
general Bytefray match default — `bytefray run`'s own `--ticks 3000`
default is unaffected and unrelated. The rationale for 200 specifically:
short enough to run in well under a second for any realistic Python agent
(no hard timeout exists — §1 non-goals — so a short default tick budget is
also the practical mitigation against a slow-but-not-hung `act()` making
the create → validate → test loop feel slow), long enough that a
non-trivial fraction of realistic strategies reach a meaningful outcome
(elimination, or several dozen territory-scoring ticks) rather than always
hitting the tick limit. This number is not derived from a measurement in
this codebase — it is a judgment call, flagged explicitly in §14 item 1
for review.

## 8. Reference opponent design

### 8.1 Resource path and construction

The reference opponent reuses the **exact same bundled resource**
`bytefray agents create` copies from — `battle_engine/data/agent_template/`
(`agent.yaml` + `agent.py`, §2's `agent_scaffold.py` citation) — located
via `template_resource_dir(get_resource_root())` (§5). It is loaded
**directly from that package-resource directory**, never copied into the
user's writable `agents/` catalog, by constructing an `AgentSpec` by hand:

```python
def _reference_opponent_spec(resource_root: Path | None = None) -> AgentSpec:
    template_dir = template_resource_dir((resource_root or get_resource_root()))
    return AgentSpec(
        name="reference",
        display="Bytefray reference agent",
        dir=template_dir,
        blob=None,
        defaults={},
        kind="python",
        api_version=1,
        version="0.1.0",
        source_path=(template_dir / "agent.py").resolve(),
        entry_point="agent.py:create_agent",
        manifest={
            "kind": "python",
            "api_version": 1,
            "entrypoint": "agent.py:create_agent",
            "version": "0.1.0",
        },
    )
```

This is loaded through `battle_engine.agent_api.load_python_agent`
**unmodified** — the same production loader every other Python agent goes
through (§2 confirms by direct inspection that `load_python_agent` never
requires its `agent_spec` argument to have come from
`discover_agents`/`resolve_agent`; it only reads attributes off it).

### 8.2 Runtime identity and match construction

The agent under test is always `MatchEntrant.python("A", <agent-id>, 0,
tested_spec)`; the opponent (reference or `--opponent`) is always
`MatchEntrant.python("B", <opponent-name>, 0, opponent_spec)` — a fixed
slot assignment (tested agent always slot A), chosen for the same reason
`cli.py` always resolves `--a-type` before `--b-type`: a single, predictable
convention that §11's identity mapping and §8.3/§8.4's failure-attribution
logic can rely on without re-deriving "which slot is which" per call.
`<opponent-name>` is the literal string `"reference"` when using the
built-in default, or the resolved `--opponent` agent's own discovery ID
otherwise — this is the *only* mechanism that distinguishes the reference
opponent from the tested agent in output and in the canonical
result/replay (§11); no new replay/result field is introduced.

```python
request = MatchRequest(
    config=Config(seed=effective_seed),
    entrants=(
        MatchEntrant.python("A", agent_id, 0, tested_spec),
        MatchEntrant.python("B", opponent_name, 0, opponent_spec),
    ),
    max_ticks=effective_ticks,
    replay_path=artifact_replay_path,   # see §9
    verbose=False,
)
match_result = NativeMatchService().run(request)
```

### 8.3 Distinguishing a tested-agent failure from an opponent failure

`PythonEntrantController.__init__` (§2) constructs and resets entrants **in
request order** and raises `PythonEntrantInitializationError` on the
*first* one that fails — its `.diagnostic.agent_id`/`.diagnostic.slot`
identify exactly which slot failed (`"A"`/`0` or `"B"`/`1`), because
`diagnose_load_failure`/`diagnose_reset_failure` are always called with
the failing entrant's own `agent_id`/`slot` (§2's citation of
`python_runtime.py`). Because §8.2 fixes the tested agent to slot `"A"`
and the opponent to slot `"B"` unconditionally, `agent_test.py` can
attribute any `PythonEntrantInitializationError` to the correct side by a
simple equality check on `exc.diagnostic.agent_id`, with **no change to
`python_runtime.py`** and no new diagnostic code:

- `exc.diagnostic.agent_id == "A"` → the agent **under test** failed to
  initialize → §10.2 (exit `0`, `status: initialization_failed`).
- `exc.diagnostic.agent_id == "B"` → the **opponent** failed to initialize.
  §8.5 (corrected) distinguishes which opponent: the internal bundled
  `reference` opponent → §10.3 (exit `2`, tool/infrastructure failure);
  an explicitly selected `--opponent` → §10.2 (exit `0`,
  `status: initialization_failed`, identified by its own discovery id) —
  the same disposition as a tested-agent initialization failure, since
  both are user-provided agent code under evaluation. `agent_test.py`
  distinguishes the two cases with the already-available `opponent is
  None` check (whether `--opponent` was passed), not a new diagnostic
  field.

A mid-match forfeit is not this ambiguity at all: `NativeAgentResult.
diagnostic` is populated per-agent on the already-successful
`NativeMatchResult` (§2), so both the tested agent's and (if the runtime
ever produces one) the opponent's forfeit diagnostics are available
side-by-side on one completed result — no attribution problem, no special
casing; §10.1/§11 read both directly off `match_result.agents_by_id`.

### 8.4 `--opponent` validation, before attempting the match

`--opponent <agent-id>` is resolved with the identical two-stage check
`agent_validation.py`'s discovery/kind stages already use (§2), reusing
the same diagnostic codes for message consistency even though this
command's own uniform exit code is `2` either way (not `agent_validation`'s
per-stage taxonomy — see §10.4):

1. `resolve_agent(root, opponent_id)` — `SystemExit` → unknown opponent,
   exit `2`.
2. `spec.kind != "python"` → non-Python opponent rejected **before
   attempting the match**, exit `2`, matching the product goal's explicit
   "Reject non-Python opponents before attempting the match" requirement
   literally (this is a pre-check, not something `NativeMatchService`
   itself would reject with a comparably clear message — an all-VM-vs-
   all-Python composition check exists in `NativeMatchService`, but this
   spec's own pre-check gives a message specifically about `--opponent`,
   not a generic "mixed composition" message a `run`-level caller would
   see).

The identical two checks apply to the **agent under test** itself
(`agent_id`, not `--opponent`) — an unknown or non-Python test agent is
also a pre-match, exit-`2` tool failure, never a "test result." This
mirrors `agent_validation.py` §4.1/§4.2 exactly, reapplied to both
positions in this command's two-entrant match rather than
`agent_validation.py`'s single position.

### 8.5 Opponent initialization failure — corrected: distinguish reference from explicit `--opponent`

**This section supersedes the original "uniform tool failure" draft below
the line** (kept as superseded context — see the resolution of design
decision 3 in §14). Post-implementation review corrected the rule to the
principle §0/§1 state throughout this spec: Bytefray exits `0` whenever it
successfully evaluated *user-provided* agent code, even when that code
prevented a match from starting. An explicit `--opponent` is user-provided
agent code being evaluated by this development test exactly like the
tested agent itself — there is no principled reason to treat its
initialization failure differently from the tested agent's own. The
internal bundled `reference` opponent is different in kind: it is
Bytefray-owned infrastructure, never something the person running
`agents test` authored or selected, so its failure to initialize can only
mean a real bug in this command's own opponent-construction logic, a
corrupted/missing packaged resource, or a packaging gap (§8.6) — never a
fact about the user's own agent code.

- **Internal bundled `reference` opponent fails to initialize:** exit `2`.
  Reported as a distinct `agent_test_internal_error`-class message (§10.3)
  naming the underlying `RuntimeDiagnostic`'s own `code`/`stage`/`message`,
  with wording that makes clear this is a tool problem, not a fact about
  `<agent-id>`.
- **`--opponent`-supplied agent fails to initialize:** exit `0`,
  `status: initialization_failed` (§10.2/§11.2, corrected), identified by
  the opponent's own discovery id (an added `opponent: <opponent-id>`
  line distinguishes this from a tested-agent initialization failure,
  which has no such line) — the same disposition, and the same
  `RuntimeDiagnostic` fields, a tested-agent initialization failure
  already gets. No result/replay/summary artifacts are produced, for the
  identical reason: the canonical match never began.

`agent_test.py` implements this distinction with the already-available
`opponent is None` check (whether `--opponent` was passed) at the point
where `exc.diagnostic.agent_id == "B"` is observed (§8.3) — no new
diagnostic field, no change to `python_runtime.py`.

---

**Superseded original text (uniform tool failure), kept for context only:**

The task's own framing singles out the *default* reference opponent
("since the bundled reference opponent should always be valid, that may
represent an internal/tool failure"). This spec generalizes that
reasoning to **any** opponent, default or `--opponent`-supplied, for a
reason that is not specific to the reference opponent's guaranteed
validity: from the "author is testing their own agent" framing, an
opponent (whichever one) that cannot even initialize means **no
meaningful development test of the agent under test ran at all** — unlike
a mid-match forfeit (which is entirely a fact about the tested agent's own
behavior, §10.1), an opponent's failure to initialize is not a fact about
the tested agent's behavior in any sense, so classifying it as a
successful "test result" would be misleading. Concretely:

- **Default reference opponent fails to initialize:** this can only mean
  a real bug in this command's own opponent-construction logic, a
  corrupted/missing packaged resource, or a packaging gap (§8.6) — never
  something the person running `agents test` did wrong. Reported as a
  distinct `agent_test_internal_error`-class message (§10.3) naming the
  underlying `RuntimeDiagnostic`'s own `code`/`stage`/`message`, with
  wording that makes clear this is a tool problem, not a fact about
  `<agent-id>`.
- **`--opponent`-supplied agent fails to initialize:** classified exit `2`
  for the reason above, but this is explicitly flagged as the weaker half
  of this generalization and listed in §14 item 3 for review — a reviewer
  may reasonably prefer an exit-`0` "the chosen opponent could not be
  used" test-shaped result instead, since (unlike the guaranteed-valid
  reference) a `--opponent` failing is at least conceivably informative to
  the author (e.g. "I pointed `--opponent` at an agent I broke last week").
  This spec's recommendation is uniform tool-failure treatment for
  implementation simplicity and for consistency with §8.4's "reject before
  attempting the match" framing (an opponent that resolves and claims to
  be a valid Python agent but cannot actually initialize is, from this
  command's perspective, indistinguishable in kind from one that was never
  valid to begin with) — but this is a judgment call, not a forced
  conclusion from existing architecture.

### 8.6 Packaging verification (source checkout, wheel, frozen build)

- **Source checkout:** `get_resource_root()` returns the repository root
  (`paths._source_checkout_root()`); `template_resource_dir` finds
  `engine/src/battle_engine/data/agent_template/` directly. Works today,
  unmodified — this is exactly how `bytefray agents create` already works
  in a source checkout.
- **Installed wheel:** `pyproject.toml`'s `[tool.setuptools.package-data]`
  includes `include-package-data = true` and the `battle_engine` package's
  data glob already covers `data/agent_template/**` (confirmed by
  `agent_scaffold.md` §8's own inspection, which this spec did not need to
  repeat) — `get_resource_root()` resolves to the installed package's
  parent directory, and `template_resource_dir`'s first candidate
  (`resource_root / "battle_engine" / "data" / "agent_template"`) is a real
  on-disk directory in any standard (non-zipped) wheel install. Works
  today, unmodified.
- **PyInstaller frozen build (`battle2.exe`): does NOT work today, and
  this is a real, pre-existing gap, not something Phase 3 introduces.**
  `tools/battle2.spec`'s `datas` list explicitly enumerates
  `battle_engine/data/starter_agents` but has **no equivalent entry for
  `battle_engine/data/agent_template`** (§2's direct inspection of the
  spec file). Since PyInstaller's `Analysis` only bundles data files
  explicitly listed in `datas` (it does not follow `pyproject.toml`'s
  package-data globs), `agent_template/` is silently **absent** from
  `battle2.exe`'s `_MEIPASS` extraction directory today. This means:
  - **Phase 1's `bytefray agents create` is already broken in the shipped
    Windows executable** — a preexisting bug this task's inspection
    surfaced as a side effect, not a regression Phase 3 causes.
  - Phase 3's reference opponent has the identical dependency and would be
    equally broken in `battle2.exe` without a fix.
  - **Required implementation-time fix (in scope for whichever PR lands
    Phase 3, since Phase 3 cannot ship correctly without it — but see
    §14 item 5 for why this is flagged rather than silently assumed):**
    add one `datas` entry to `tools/battle2.spec`, mirroring the existing
    `starter_agents_dir` pattern exactly:
    ```python
    agent_template_dir = os.path.join(engine_src, "battle_engine", "data", "agent_template")
    ...
    if os.path.isdir(agent_template_dir):
        datas.append((agent_template_dir, "battle_engine/data/agent_template"))
    ```
    This single change fixes both Phase 1's existing gap and Phase 3's
    requirement, since both features depend on the identical resource
    directory being present in the frozen build. No other `.spec` file
    needs this: `battle-cli`/`agent_designer`/`replay_viewer` never reach
    `command.py`'s `_agents` dispatch (§2's console-script/architecture
    citation), so they have no dependency on `agent_template/` either
    (their existing `starter_agents_dir` inclusion is for an unrelated
    reason — the Designer's own agent catalog).

### 8.7 Discoverability and safety of the reference opponent

- **Not copied into the user's `agents/` directory** — it is loaded
  directly from the package resource path every time `agents test` runs
  without an `--opponent`; there is no "install the reference opponent"
  step and no persistent writable copy of it anywhere.
- **Not discoverable as a normal user agent** — `discover_agents`/
  `resolve_agent` only ever scan `<data_root>/agents/`; the reference
  opponent's `AgentSpec.dir` is never under that tree, so it never appears
  in `bytefray agents` (bare list), can never be selected via
  `--a-type`/`--b-type`/`agents validate`, and is architecturally
  incapable of colliding with a real user agent directory, including one a
  user might separately choose to name `reference` themselves (§8.2's
  `--opponent reference` would resolve *that* real, discovered agent
  through the ordinary `resolve_agent` path — a legitimate, if
  coincidental, naming overlap with the internal default's display label,
  no different in kind from a user naming their own agent `runner` and
  shadowing the built-in VM agent of the same name, already accepted
  behavior per `agent_scaffold.md` §4).
- **Write-safety for a real 200-tick match:** the template's `act()`
  performs exactly one `WRITE` per tick to `self.rng.randrange(256)` — a
  bounded, always-in-range address (Agent API v1's `WRITE` wraps any
  operand against the arena size in `apply_action`/`vm._wr8` regardless,
  so even an out-of-`range(256)` address would still be safe, but the
  template never produces one) — with a fixed byte value `0xA5`. This is
  ordinary, unattributed battlefield state (§7 of `agent_scaffold.md`);
  running it for up to 200 ticks is exactly as safe as any real match
  against it already is (`bytefray agents create my_agent && bytefray run
  --a-type my_agent --b-type my_agent` already runs the identical code
  path today, just via a copy under `agents/`, not the resource directory
  directly). No new safety property needs to be established — the
  template's action pattern is already exercised by every existing Phase 1
  test that runs a scaffolded agent in a real match
  (`agent_scaffold.md` §11's "immediate discovery" subprocess test).

## 9. Artifact location

### 9.1 Directory scheme

```text
<data_root>/runs/agents_test/<agent-id>/<run-label>/replay.jsonl
<data_root>/runs/agents_test/<agent-id>/<run-label>/result.json
<data_root>/runs/agents_test/<agent-id>/<run-label>/summary.json
```

Modeled directly on `cli.py`'s own `DEFAULT_REPLAY_RELATIVE_PATH = Path
("runs") / "_loose" / "replay.jsonl"` (`<data_root>/runs/...` is already
the canonical loose-match artifact root) and on
`tournament_service.TournamentRequest.output_dir`'s own `matches/<label>/`
per-match subdirectory convention (§2) — `agents_test/<agent-id>/` groups
every development test for one agent together (so an author can `ls` their
own agent's test history), and `<run-label>` (below) gives each individual
invocation its own directory, matching how `_finalize_native_artifacts`
already expects a `replay_path` whose *parent* directory it owns
(`replay_path.parent.mkdir(parents=True, exist_ok=True)`; sibling
`result.json`/`summary.json` share that same parent) — this spec's
`<run-label>` directory is exactly that owned parent, never reused across
invocations.

### 9.2 `<run-label>` — collision avoidance and non-overwrite

No existing code in this repository builds a timestamped directory name
(§2) — this is new. Proposed format, combining a sortable, human-readable
timestamp with a short random tiebreaker and the opponent's identity:

```text
<UTC timestamp, microsecond precision>-<8 hex chars>-vs-<safe opponent id>
```

e.g. `20260808T211055123456-a1b2c3d4-vs-reference`. Concretely:

- **Timestamp:** `datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")`
  — sortable lexicographically, filesystem-safe on both NTFS and POSIX (no
  `:` characters), and matches this codebase's existing preference for
  explicit UTC over local time where timing matters (replay/result content
  itself carries no wall-clock timestamps today, so there is no existing
  in-repo convention to match beyond "use UTC, not local time," a general
  good practice rather than a reused pattern).
- **Random tiebreaker:** 8 hex characters from `uuid.uuid4().hex[:8]` —
  the identical primitive `agent_scaffold.py`'s temp-directory naming
  already uses (§2), repurposed here for uniqueness rather than
  atomicity-during-construction. Guards against two `agents test`
  invocations landing in the same microsecond (e.g. a test harness
  spawning several in a tight loop, or a coarser OS clock resolution than
  assumed) without relying on the timestamp's precision alone.
- **Opponent suffix:** `tournament_service._safe_name(opponent_name)`
  reused verbatim (promoted alongside `template_resource_dir` in §5's
  visibility change, or reimplemented as an equally trivial three-line
  regex — a one-function judgment call left to implementation, since
  `_safe_name` lives in a module (`tournament_service.py`) with no
  existing precedent of being imported by a CLI-facing "verb" module the
  way `agent_scaffold.py` is by `agent_test.py`) — makes the directory
  name legible (`...-vs-reference` vs. `...-vs-hunter_v2`) without
  affecting collision-avoidance, which the timestamp+random prefix alone
  already guarantees.

This directory is created fresh by `agent_test.py` itself before
constructing the `MatchRequest` (never reused, never pre-existing), so
`_run_python_match`'s own stale-artifact-removal step (§2,
`_remove_python_artifacts` called before `PythonEntrantController`
construction) is always a no-op removal of files that were never there —
consistent with, not a workaround for, the production match path's own
idempotent-cleanup behavior.

### 9.3 Visibly distinct from normal loose matches

`runs/agents_test/<agent-id>/<run-label>/` is already visibly distinct
from `runs/_loose/` (`bytefray run`'s own default location) and from
`runs/agents_test/`'s sibling `tournament` output directories (which live
wherever a tournament's own `--output-dir` points, not under
`runs/agents_test/`) purely by path — no change to the normal artifact
writer (`NativeMatchService`/`_finalize_native_artifacts`) is needed or
made; `agents test` achieves this distinction entirely by choosing where
it points `MatchRequest.replay_path`, exactly the mechanism `bytefray run
--replay <path>` already uses to redirect output anywhere the caller
wants (`test_output_paths.py`'s existing coverage of explicit-vs-default
replay paths, §2).

## 10. Exit-status semantics

### 10.1 Completed real match

If `NativeMatchService().run(...)` returns a `NativeMatchResult` (no
exception), the command exits **`0`** unconditionally, regardless of the
tested agent's own outcome within that match:

- won, lost, tied, or was eliminated by tick limit;
- died via a normal `HALT` (`entrant_termination == "normal_halt"` on its
  `NativeAgentResult` — Python entrants have no arena-corruption mortality
  per `AGENT_AUTHORING.md`, so a Python agent's only "death" is a
  self-inflicted `HALT`, never an opponent "kill" — confirmed by direct
  inspection of `PythonEntrantController.run()`, which never emits a
  `"kill"`-typed event, only `"death"`/`"forfeit"`, §2);
- forfeited from an invalid action (`agent_action_invalid`) or an `act()`
  exception (`agent_action_failed`) — both already produce a populated
  `NativeAgentResult.diagnostic`, surfaced verbatim in §11's forfeit line.

This is a direct, deliberate generalization of behavior this codebase
**already has today** for `bytefray run` itself
(`test_cli_python_act_failure_is_structured_without_traceback`, §2 —
a real match's entrant forfeit already returns CLI exit `0`, not `2`).
Phase 3 does not invent this convention; it reuses it.

### 10.2 Tested agent's or an explicit opponent's own initialization failure

Per §8.3, `exc.diagnostic.agent_id == "A"` on a caught
`PythonEntrantInitializationError` means the agent under test itself
failed before tick zero (import/factory/contract/`reset()` failure — the
identical failure classes `agent_validation.py`'s load/reset stages
already check, but now observed inside a real match construction instead
of a dry run). Per the task's explicit instruction, this is treated as a
**successfully completed development test result**:

- exit `0`;
- `status: initialization_failed` (§11.2);
- the full structured diagnostic (`stage`, `code`, `error`, and
  `detail: <ExceptionType>` when present) printed verbatim, using the
  exact `RuntimeDiagnostic` `PythonEntrantController` already produced —
  no re-derivation, no second diagnostic construction;
- **no result/replay artifacts are created**, and the output says so
  explicitly (`result: none`, `replay: none`) rather than fabricating
  empty files to make the output shape uniform with §10.1's — this
  matches the task's explicit instruction and is additionally already
  true by construction: `_run_python_match` (§2) never writes anything at
  the requested path before `PythonEntrantController.__init__` succeeds,
  and re-runs its own stale-artifact cleanup on the way out of the
  exception handler, so nothing exists at `<run-label>/` when this path
  is taken. (The empty `<run-label>` directory itself — created by
  `agent_test.py` before the match, per §9.2 — is harmless, empty, and
  not itself claimed to be an artifact; whether to also remove that empty
  directory or leave it is an implementation-level tidiness choice with no
  behavioral consequence, not addressed further by this spec.)

**Corrected (§8.5, §14 item 3 resolved): `exc.diagnostic.agent_id == "B"`
gets the identical exit-`0` treatment whenever `--opponent` was explicitly
supplied** — the opponent is user-provided agent code being evaluated by
this development test exactly like the tested agent itself, so there is
no principled reason to disposition its initialization failure
differently. The only difference from a tested-agent initialization
failure is presentational: an added `opponent: <opponent-id>` line
identifies which side failed (§11.2), using the opponent's own discovery
id rather than the tested agent's. This does **not** apply to the
internal bundled `reference` opponent used when `--opponent` is omitted —
see §10.3.

### 10.3 Internal reference opponent initialization failure, and other tool/infrastructure failures

Exit **`2`** for every condition in this category — none of these are
facts about evaluated user agent code, so none are reported as `status:
initialization_failed` or any other test-result shape:

- the **internal bundled `reference` opponent** (used only when
  `--opponent` is omitted) failed to initialize (§8.3/§8.5) —
  `exc.diagnostic.agent_id == "B"` with no `--opponent` supplied. This is
  Bytefray-owned infrastructure, not user code, so its failure means the
  tool or its bundled fixture is broken. (An explicitly selected
  `--opponent`'s own initialization failure is exit `0` instead — §10.2.)
- unknown test-agent ID, or test agent not `kind: python`;
- unknown `--opponent`, or opponent not `kind: python`;
- invalid `--ticks`/`--seed` (argparse-level usage error, handled by
  argparse itself before any of the above);
- `UnsupportedMatchCompositionError` from `NativeMatchService` itself —
  should never trigger given §8.4's pre-checks (both entrants are always
  Python by construction), but still caught defensively rather than
  allowed to propagate as an unhandled exception, exactly as `cli.py`
  already does for the same exception type;
- `PythonMatchExecutionError` — an engine or artifact-write failure during
  or after execution (`artifact_write_failed`, `engine_failed`) — never a
  per-entrant forfeit (those are recorded as replay events / a populated
  `NativeAgentResult.diagnostic` on an otherwise-successful result, §10.1,
  not raised as this exception type at all, per `python_runtime.py`'s own
  design, §2);
- inability to create the `<run-label>` output directory, or any other
  `OSError` while preparing to run the match;
- any other exception `agent_test.py`'s own orchestration raises that is
  not one of the above typed cases (a bug in this module, not the agent
  under test) — caught once at the top of `main`/the library entry point
  and reported as an `agent_test_internal_error`-class message, mirroring
  `agent_validation.py`'s own `validation_internal_error` catch-all
  (§6.1 of `agent_validation.md`) rather than inventing a differently-named
  equivalent.

No raw traceback in any of the above — every message is either an
existing `RuntimeDiagnostic`'s already-normalized `message` field, or a
short, hand-written sentence, matching every other subcommand's
no-traceback convention.

### 10.4 Exit-code matrix

| Condition | Exit code | Stream |
|---|---|---|
| Match completes (any tested-agent outcome: win/loss/tie/forfeit/death/tick-limit) | `0` | stdout |
| Tested agent's own initialization failure (pre-tick-0) | `0` | stdout |
| Explicit `--opponent`'s own initialization failure (pre-tick-0) | `0` | stdout |
| `--help`/`-h` | `0` | stdout |
| Missing/extra positional args, invalid `--ticks`/`--seed` | `2` | stderr |
| Unknown test-agent ID | `2` | stderr |
| Test agent not `kind: python` | `2` | stderr |
| Unknown `--opponent` | `2` | stderr |
| Opponent not `kind: python` | `2` | stderr |
| Internal bundled `reference` opponent's initialization failure | `2` | stderr |
| `UnsupportedMatchCompositionError` (defensive) | `2` | stderr |
| `PythonMatchExecutionError` (engine/artifact-write failure) | `2` | stderr |
| Output-directory creation/write failure | `2` | stderr |
| Unexpected internal `agent_test.py` failure | `2` | stderr |

## 11. Output contract

### 11.1 Completed match

```text
agent: my_agent
opponent: reference
seed: 1337
ticks: 117/200
winner: my_agent
termination: last_agent_standing
result: <data_root>/runs/agents_test/my_agent/20260808T211055123456-a1b2c3d4-vs-reference/result.json
replay: <data_root>/runs/agents_test/my_agent/20260808T211055123456-a1b2c3d4-vs-reference/replay.jsonl
summary: <data_root>/runs/agents_test/my_agent/20260808T211055123456-a1b2c3d4-vs-reference/summary.json

Run 'bytefray replay <replay-path>' to inspect it.
```

If either entrant forfeited, one additional line per forfeited entrant,
inserted before the trailing `replay:` hint, in match order (tested agent
first):

```text
forfeit: my_agent stage=action code=agent_action_invalid
```

Built from `NativeAgentResult.diagnostic.stage`/`.code` for whichever
`NativeAgentResult` in `match_result.agents` has a non-`None` diagnostic —
no new diagnostic shape (matches the task's explicit "Do not invent
another diagnostic shape" instruction). A normal `HALT` death produces no
forfeit line (it is not a forfeit — §10.1) and needs no separate line
either, since `winner`/`termination` already convey the match's outcome;
this spec does not add a distinct "death:" line, to keep the output
contract exactly as small as the task's own example shows.

`winner` is `match_result.agents_by_id[match_result.winner].name` when
`match_result.winner` is a real slot (`"A"`/`"B"`), or the literal string
`match_result.winner` itself (`"tie"`, `results.WINNER_TIE_SENTINEL`) when
there is no single winner — `bytefray run`'s own summary output already
prints this exact sentinel value verbatim today, so `agents test` reuses
it rather than inventing different tie-wording.

`ticks` is `f"{match_result.ticks_run}/{effective_ticks}"` — visibly shows
whether the match ran to completion early (elimination) or used its full
budget (tick limit).

`termination` is `match_result.termination_reason.value`
(`last_agent_standing`/`all_agents_dead`/`tick_limit`).

### 11.2 Initialization failure (tested agent, or an explicit opponent)

```text
agent: my_agent
status: initialization_failed
stage: reset
code: agent_reset_failed
error: Python agent my_agent reset failed: RuntimeError: boom
detail: RuntimeError
result: none
replay: none
```

`stage`/`code`/`error`/`detail` are read directly off
`exc.diagnostic` (`RuntimeDiagnostic.stage`/`.code`/`.message`/
`.exception_type`) — `detail` is omitted when `exception_type` is `None`,
matching `agent_validation.py`'s identical convention (§3.4 of
`agent_validation.md`). `error`'s message text still names the fixture's
runtime slot (`"Python agent A reset failed: ..."`, since
`diagnose_reset_failure`/`diagnose_action_exception` always format the
message using the `agent_id` they were called with, and §8.2 always calls
them with the real slot value, `"A"`) — **this spec reuses
`agent_validation.py`'s exact already-implemented `_display_message`
rewrite** (§2) to substitute the caller-facing display id for the
literal slot letter in the printed text only, leaving the underlying
`RuntimeDiagnostic.message` untouched, for the identical reason
`agent_validation.py` already does this: a person running `bytefray
agents test my_agent` should never see the string `"Python agent A"` in
their own terminal when they typed `my_agent`.

There is no `seed:`/`ticks:` line in this shape — the match never
started, so there is nothing to report about it (no seed was "used" in
any observable sense, no ticks ran); only what actually happened is
reported. This is a deliberate difference from §11.1's shape, not an
oversight — the task's own example output for this case likewise omits
them.

**Corrected: when an explicitly selected `--opponent` is the entrant that
failed to initialize (§10.2), rather than the tested agent, an
`opponent:` line is added** (right after `agent:`) naming the opponent's
own discovery id, and the display-id substitution in `error:` uses that
opponent id instead of the tested agent's:

```text
agent: my_agent
opponent: other_python_agent
status: initialization_failed
stage: reset
code: agent_reset_failed
error: Python agent other_python_agent reset failed: RuntimeError: boom
detail: RuntimeError
result: none
replay: none
```

There is still no `seed:`/`ticks:` line — the match never started. The
internal bundled `reference` opponent never produces this shape at all:
its own initialization failure is §11.3's tool-failure shape instead,
since it is not user-provided agent code.

### 11.3 Tool/infrastructure failure

```text
agent: my_agent
status: error
stage: <stage>
code: <code>
error: <message>
```

Printed to **stderr**, exit `2`. Used uniformly for every §10.3/§10.4
tool-failure condition, with `stage`/`code` populated from the relevant
`RuntimeDiagnostic` when one exists (internal `reference` opponent init
failure, `UnsupportedMatchCompositionError.diagnostic`,
`PythonMatchExecutionError.diagnostic`) or a small fixed
stage/code pair for conditions with no underlying `RuntimeDiagnostic`
(e.g. `stage: discovery`, `code: agent_unknown` for an unknown test agent
or opponent — reusing `agent_validation.py`'s exact code for the identical
underlying condition, §8.4). `status: error` (not `status: invalid`,
which `agents validate` already uses for a *validation* failure, and not
`status: initialization_failed`, which §11.2 reserves for a tested agent's
or an explicit opponent's own pre-match failure) is a new, deliberately
distinct value so a script distinguishing `agents validate`'s and `agents
test`'s stderr shapes by `status:` never confuses the two commands'
failure kinds.

## 12. Explicitly out of scope for Phase 3

Restated from the task's own scope boundary, for this spec's completeness:

- GUI test controls, automatically opening the replay viewer, or live
  match viewing (§0/§1 — `bytefray replay <path>` remains a separate,
  explicit next step).
- Mixed VM/Python matches, Redcode/pMARS development testing — unsupported
  everywhere in this codebase today, not something this phase changes.
- Sandboxing or a new timeout system for `reset()`/`act()`.
- Static linting or performance benchmarking of the agent's code.
- Multiple built-in opponent strategies — exactly one internal reference
  opponent (§8), plus `--opponent` for any other discovered Python agent.
- Tournament execution (`bytefray tournament` already exists and is
  unrelated/unaffected).
- Replay-analysis extraction (tracked separately —
  `docs/specs/replay_analysis.md`, an unrelated, already-drafted spec this
  task's own instructions required preserving untouched, not built on by
  Phase 3).
- A run-history browser, or any tooling that lists/summarizes prior
  `agents test` runs under `runs/agents_test/<agent-id>/` — this spec
  only defines where they land, not a viewer for them.
- `--data-root`, `--arena`, `--quota`, `--win-mode`, or any
  `bytefray run`-style agent-parameter flag beyond `--opponent`/`--seed`/
  `--ticks` (§3.3).

## 13. Required tests

Location: `engine/tests/test_agent_test.py` (co-located with the other
`battle_engine` CLI/catalog test modules; no `gui` marker), following
`test_agent_scaffold.py`/`test_agent_validation.py`'s existing structure
and CLI-subprocess idiom (`test_battle2_command.py`'s `_run` helper
pattern, §2).

### Successful flow

- A Phase 1 `bytefray agents create`-scaffolded agent (built via
  `agent_scaffold.create_agent`, not hand-written), tested against the
  default reference opponent, completes with exit `0` and the §11.1
  output shape.
- The same agent, `bytefray agents validate` then `bytefray agents test`
  in sequence (mirroring the documented create → validate → test loop),
  both succeed.
- Two calls to `agent_test.test_agent(...)`/the CLI with identical
  `agent_id`/`--seed`/`--ticks`/`--opponent` produce byte-identical
  `winner`/`termination`/`ticks_run` and byte-identical replay content
  (modulo the artifact *path* itself, which always differs per §9.2) —
  confirms determinism given a fixed seed.
- `--seed` override changes the recorded seed in `result.json`'s
  `reproducibility.seed` and (for an RNG-sensitive template agent) can
  change the outcome versus the default seed.
- `--ticks` override changes `effective_ticks` used both for the match's
  `max_ticks` and for the `ticks: <run>/<requested>` output line.
- `--opponent <other-python-agent>` (a second scaffolded or hand-written
  Python agent) substitutes correctly for the reference opponent —
  `opponent:` in the output and `entrants[1].name` in the canonical
  result/replay both show the substituted agent's discovery ID, not
  `"reference"`.
- Canonical `replay.jsonl` (schema v3), `result.json` (`battle2.result`
  v1, with a valid replay SHA-256 digest verified via
  `result_model.verify_result_replay`), and `summary.json` are all
  written at the expected `<run-label>` directory.
- The emitted replay loads via `battle_engine.replay.iter_replay` and via
  `battle_client.session.ReplaySession`/`battle_client.cli.main` (normal
  replay tooling reads it with no special-casing) — a direct architectural
  proof that no test-only replay format was introduced.
- Two separate `agents test` invocations against the same `agent_id`
  (same or different `--opponent`/`--seed`) both succeed and leave *both*
  prior runs' artifacts intact under distinct `<run-label>` directories —
  confirms §9.2's non-overwrite/non-collision claim directly, not just by
  construction.

### Author-agent failures

- `act()` raises during the real match → `NativeAgentResult.diagnostic.
  code == "agent_action_failed"`, exit `0`, a `forfeit:` line present,
  `winner`/`termination` reflect the surviving/tied outcome.
- `act()` returns an invalid action → `agent_action_invalid`, exit `0`,
  same shape as above.
- Agent dies via `HALT` or otherwise loses (opponent wins by score/
  survival) → exit `0`, no `forfeit:` line, `winner` names the opponent
  (or `"reference"`).
- Agent's `reset()`/factory/import fails before tick zero →
  `PythonEntrantInitializationError` with `diagnostic.agent_id == "A"` →
  exit `0`, `status: initialization_failed`, §11.2 shape, and **no**
  `<run-label>`-directory `replay.jsonl`/`result.json`/`summary.json` are
  created (assert their absence directly, not just exit code/output text).
- **Corrected:** an explicitly selected `--opponent`'s own `reset()`/
  factory/import fails before tick zero → `PythonEntrantInitializationError`
  with `diagnostic.agent_id == "B"` and `--opponent` supplied → exit `0`,
  `status: initialization_failed`, §11.2's corrected `opponent:`-line
  shape identifying the failing opponent by its own discovery id, and
  **no** `<run-label>`-directory artifacts created — the identical
  disposition and artifact-absence guarantee as a tested-agent
  initialization failure, since both are user-provided agent code.

### Opponent/tool failures

- Unknown test-agent ID → exit `2`, `agent_unknown`-class message,
  stderr, no traceback.
- Non-Python test agent (`kind: builtin`, e.g. a starter-populated
  `runner`) → exit `2`, `agent_kind_unsupported`-class message.
- Unknown `--opponent` → exit `2`.
- Non-Python `--opponent` → exit `2`, and confirm the match was never
  attempted (no `PythonEntrantController` construction — e.g. via a
  monkeypatched sentinel, or simply by asserting no `<run-label>`
  directory was created for that invocation).
- Invalid `--ticks` (`0`, negative, non-integer) → argparse-level exit `2`.
- Malformed `--seed` (non-integer) → argparse-level exit `2`.
- Output-directory creation failure (e.g. monkeypatch `Path.mkdir` to
  raise, or — POSIX-only, matching `agent_scaffold.md` §11's existing
  skip convention — an actually-read-only parent directory) → exit `2`,
  no traceback, no partial artifacts.
- **Internal bundled `reference` opponent** initialization failure only
  (no `--opponent` supplied), simulated (e.g. monkeypatch
  `_reference_opponent_spec`/`template_resource_dir` to point at a
  deliberately broken template fixture) → exit `2`,
  `agent_test_internal_error`-class message naming the underlying
  diagnostic, and confirm the message text does **not** claim anything
  about `<agent-id>`'s own status. (Contrast with the explicit-opponent
  case moved to "Author-agent failures" above, which is exit `0`.)

### CLI

- stdout-only on exit `0` (both §11.1 and §11.2 shapes); stderr-only on
  exit `2`; never both non-empty in the same invocation.
- No `Traceback`/`File "`/multi-line stack text in stdout or stderr for
  any of the above cases.
- `--help`/`-h`: exit `0`, usage text mentions `agent_id`,
  `--opponent`, `--seed`, `--ticks`, and states the §4 boundary (a
  forfeit/loss/death is still a successful test).
- `battle2 agents test <agent-id>` behaves identically to `bytefray agents
  test <agent-id>` apart from the existing deprecation notice, mirroring
  `test_battle2_command_console_script_prints_deprecation_notice_and_
  matches_bytefray`'s existing idiom.
- Existing `agents` (bare list), `agents create`, and `agents validate`
  behavior and tests are unmodified by this addition (a regression check,
  not new coverage — run the existing `test_agent_scaffold.py`/
  `test_agent_validation.py`/relevant `test_battle2_command.py` tests
  unchanged and confirm they still pass).

### Architectural proof

- At least one test that monkeypatches
  `battle_engine.match_service.NativeMatchService.run` (or
  `PythonEntrantController.run`, one layer lower, mirroring
  `test_native_match_service.py`'s own proof idiom, §2) to record that it
  was called exactly once with a `MatchRequest` containing the expected
  two Python `MatchEntrant`s, and asserts `agent_test.py` contains **no**
  private per-tick loop, no direct `PythonEntrantController` construction,
  and no direct arena/VM manipulation of its own — Phase 3 invokes the
  canonical `NativeMatchService`, it does not reproduce match execution
  privately, proven by test rather than only by code review.

### Custom data root

- `BYTEFRAY_ROOT` (and, separately, the `BATTLE2_ROOT` fallback with
  `BYTEFRAY_ROOT` unset) set to a `tmp_path` directory: artifacts land
  under `<that root>/runs/agents_test/...`, not the default/source-checkout
  root, mirroring `test_paths.py`'s precedence-testing idiom and
  `agent_scaffold.md`/`agent_validation.md`'s equivalent existing coverage.

## 14. Design decisions needing human approval

1. **The 200-tick development default (§7).** Chosen as a judgment call
   (fast enough not to slow the create → validate → test loop with no
   timeout safety net; long enough for a non-trivial fraction of
   strategies to reach a real outcome), not derived from any measurement
   in this codebase. A reviewer may prefer a different number, or a
   different rationale (e.g. tying it to `Config.instr_per_tick` or arena
   size instead of a flat constant).
2. **The exact `<run-label>` directory-naming scheme (§9.2)** — UTC
   microsecond timestamp + 8 hex random chars + sanitized opponent suffix.
   This is new (no existing in-repo precedent for a timestamped directory
   name, §2), and a reviewer may prefer a simpler scheme (e.g. a
   monotonically increasing per-agent counter directory, closer to
   `tournament_service`'s `{ordinal:06d}-...` labels, avoiding wall-clock
   dependence entirely) or a different level of nesting (e.g. omitting the
   opponent suffix, or flattening `agent_id` and `run-label` into one
   directory segment).
3. **Resolved (post-implementation correction): a `--opponent`-supplied
   opponent's initialization failure is exit `0`, using the existing
   `status: initialization_failed` shape with an added `opponent:` line
   naming it by discovery id (§8.5, §10.2, §11.2), not exit `2`.** This
   spec originally recommended uniform exit-`2` treatment for both the
   internal reference opponent and any `--opponent`, and flagged that
   generalization as its weaker, more debatable half. Human review
   corrected it: the approved Phase 3 exit-code principle is "exit `0`
   whenever Bytefray successfully evaluated user-agent behavior, even when
   that behavior prevented a match from starting," and an explicit
   `--opponent` is user-provided agent code being evaluated by this
   development test exactly like the tested agent itself — there is no
   principled basis for disposition-ing its initialization failure
   differently. The internal bundled `reference` opponent remains exit `2`
   because it is Bytefray-owned infrastructure, never user code: its
   failure means the tool or its bundled fixture is broken, not a fact
   about the agent under test. No new `status` value was introduced;
   `status: initialization_failed` (§11.2) already generalizes cleanly to
   "the entrant identified by the `agent:`/`opponent:` line(s) failed to
   initialize" for either the tested agent or an explicit opponent.
4. **Whether the tested agent's own initialization failure returning exit
   `0` is the correct long-term CLI contract** (task's own open question).
   This spec implements the task's explicit instruction as given, but the
   task itself asks this be flagged for reconsideration — e.g. whether a
   future scripting/CI use of `agents test` would actually want a
   distinguishable exit code for "no match ran" versus "a match ran and
   the agent lost/forfeited," even though both are legitimately "test
   results" from a human-development-loop perspective.
5. **The `tools/battle2.spec` packaging fix (§8.6).** This spec treats
   adding the missing `agent_template_dir` `datas` entry as a required
   part of implementing Phase 3 (since Phase 3's default opponent cannot
   work in the frozen build otherwise), which incidentally also fixes a
   preexisting Phase 1 defect. A reviewer may instead prefer that the
   Phase 1 packaging fix be landed as its own, separate, immediately-
   mergeable bugfix PR (since it is a real defect in already-shipped
   functionality, independent of whether/when Phase 3 lands), with Phase
   3's implementation only asserting the fix already exists rather than
   introducing it.
6. **Whether `agents test`'s own `--seed`/`--ticks` validators should be
   literally shared with `cli.py`'s (currently private, module-level)
   `_positive_int`/`--seed`'s plain `type=int`, versus this spec's
   proposal of a small independent copy (§7).** Proposed independent to
   avoid importing a leading-underscore name across modules; a reviewer
   valuing single-source-of-truth over that particular boundary might
   prefer promoting `cli._positive_int` to a small shared, public
   argument-parsing helper instead.

## 15. Documentation impact

`docs/AGENT_AUTHORING.md` implementation changes (not made by this spec
itself, per the task's "do not modify production code/tests" instruction):

- The recommended workflow section changes from **create → validate →
  run** to:

  ```bash
  bytefray agents create my_agent
  bytefray agents validate my_agent
  bytefray agents test my_agent
  bytefray replay <reported-replay-path>
  ```

- A new short section, "Development-test your agent" (or similar), placed
  after "Validate before running," showing the §11.1 output shape and
  stating precisely, in prose, the §4 boundary between `validate` and
  `test` — reusing that table's wording rather than inventing new
  phrasing.
- Explicit callout, matching the task's own instruction verbatim in
  spirit: "a test-agent forfeit, death, or loss is still a *successfully
  executed* development test and returns exit `0` — only a problem
  running the test itself (an unknown agent/opponent, a non-Python
  opponent, or an opponent that fails to initialize) returns exit `2`."
- A one-sentence pointer to `docs/TOURNAMENTS.md` for "if you want to
  compare more than one opponent or run more than a short development
  match, use `bytefray tournament` or `bytefray run` directly" — so
  `agents test` is not mistaken for a general-purpose match runner.
- `docs/AGENT_API_V1.md` is not changed: Phase 3 adds no new Agent API v1
  contract surface, only a new consumer (a real match) of the existing
  one, identical in spirit to `agent_validation.md` §13's equivalent
  statement for Phase 2.
- `ARCHITECTURE.md`'s "v0.4 direction" section should be updated once
  Phase 3 lands (not by this spec) to note `agents test` now exists,
  mirroring how that section already tracks Phase 1/Phase 2 completion
  implicitly through this repository's spec-then-implement convention.

## 16. Runtime/result identity mapping (summary)

Consolidating §8.2/§8.3/§11's mapping into one explicit table, per the
task's explicit request for this documented separately:

| Layer | Tested agent | Opponent (reference) | Opponent (`--opponent`) |
|---|---|---|---|
| User-facing discovery ID | `<agent-id>` (CLI positional) | *(none — internal)* | `<opponent-id>` (`--opponent` value) |
| `MatchEntrant.agent_id` (runtime slot) | `"A"` | `"B"` | `"B"` |
| `MatchEntrant.name` | `<agent-id>` | `"reference"` | `<opponent-id>` |
| `RuntimeDiagnostic.agent_id`/`.slot` (init failure or forfeit) | `"A"` / `0` | `"B"` / `1` | `"B"` / `1` |
| `NativeAgentResult.agent_id` | `"A"` | `"B"` | `"B"` |
| `NativeAgentResult.name` | `<agent-id>` | `"reference"` | `<opponent-id>` |
| `result.json`/replay `entrants[].agent_id` | `"A"` | `"B"` | `"B"` |
| `result.json`/replay `entrants[].name` | `<agent-id>` | `"reference"` | `<opponent-id>` |
| `NativeMatchResult.winner` (raw) | `"A"` or `"tie"` | `"B"` or `"tie"` | `"B"` or `"tie"` |
| CLI `winner:` line (§11.1) | `<agent-id>` (mapped via `.name`) | `"reference"` (mapped via `.name`) | `<opponent-id>` (mapped via `.name`) |
| CLI `forfeit:`/`error:` line (§11.1/§11.2) | `<agent-id>` (`_display_message`-style rewrite of the shared slot-based text, §2) | `"reference"` (same rewrite) | `<opponent-id>` (same rewrite) |

No canonical `result.json`/`replay.jsonl` field is renamed, added, or
reinterpreted to make this mapping work — every row above already exists
in the schema (`agent_id` is the stable runtime-slot key every existing
consumer already keys off; `name` is the existing free-text display field
every existing native match already populates from `MatchEntrant.name`,
§2). Only the CLI's own *printed text* (`winner:`, `forfeit:`, `error:`
lines) performs the slot → name substitution, using the same
already-implemented, already-tested pattern `agent_validation.py`'s
`_display_message` established for its own single-slot fixture.
