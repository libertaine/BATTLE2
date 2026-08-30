# v1.5 Phase 5 — Entrant identity and execution-state separation

This is the durable record of v1.5 Phase 5: introducing an explicit
`EntrantIdentity` type and making `match_service.MatchEntrant`, VM
`agent_state.Agent`, and `python_runtime.PythonEntrantState` each reference
one authoritative identity object instead of independently storing
`agent_id`/`name` as flat fields, with no change to Ruleset-v1 behavior,
persisted schemas, deterministic identity, or gameplay.

Phase 1 characterized this exact conflation and classified every relevant
field ([the Phase 1 baseline](V1_5_PHASE1_RULESET_V1_BASELINE.md)'s "Entrant
identity versus execution state"); Phases 2-4 centralized scheduling and
termination behind `RulesetPolicy` without touching it
([Phase 2](V1_5_PHASE2_SCHEDULER_ABSTRACTION.md),
[Phase 3](V1_5_PHASE3_RULESET_POLICY_DISPATCH.md),
[Phase 4](V1_5_PHASE4_TERMINATION_POLICY.md)), each recommending it as the
one item on Phase 1's original list still untouched. Phase 5 does exactly
that, and nothing else.

## Pre-refactor model

Three classes each independently stored `agent_id` (two also stored `name`)
as a flat field alongside data that is not competitor identity:

- **`match_service.MatchEntrant`** (frozen dataclass): `agent_id`, `name`
  (identity) flat alongside `start`, `code`, `kind`, `python_spec`
  (resolved match participation data) -- six fields, two conceptual
  categories, no structural boundary between them.
- **VM `agent_state.Agent`** (mutable dataclass): `agent_id` (identity) flat
  alongside `pc`, `alive`, `regs`, `cpu_used`, `mem_writes` (mutable
  execution state) and `region` (resolved match input, per Phase 1's
  finding #5). No `name` field exists here at all -- the VM path has never
  tracked a display name on its execution state; `match_service._build_result`
  resolves it separately from `MatchEntrant.name` via a local dict.
- **`python_runtime.PythonEntrantState`** (mutable dataclass): `agent_id`,
  `name` (identity) flat alongside `slot`, `derived_seed`,
  `source_digest`/fingerprints, `agent_dir`, `region` (resolved match
  input/provenance) and `pc`, `register_a`, `register_p`, `zero_flag`,
  `last_read`, `alive`, `cpu_used`, `total_actions`, `mem_writes`,
  `diagnostic`, `entrant_termination` (mutable execution state/output) --
  twenty-two fields, four conceptual categories, no structural boundary.

Nothing was duplicated *across* these three classes in a way that could
drift (each entrant's `agent_id` string is copy-constructed once, from the
same source, into each class that needs it) -- the problem Phase 1 named
was conflation *within* each class, not divergence between them.

## Field classification (revalidated against current source)

| Field | Class | Category | Notes |
|---|---|---|---|
| `agent_id` | `MatchEntrant`, `Agent`, `PythonEntrantState` | Entrant identity | Match-slot identity (`"A"`/`"B"`/…) |
| `name` | `MatchEntrant`, `PythonEntrantState` | Entrant identity | Display name; VM `Agent` never had this field |
| `kind` | `MatchEntrant` | Resolved match input (execution configuration) | See "What `kind` is, and is not" below -- not moved into identity |
| `start` | `MatchEntrant` | Resolved match input | Feeds `Agent.pc`/`PythonEntrantState.pc` and `region` at construction; never itself identity |
| `code` | `MatchEntrant` | Resolved match input | `None` for Python |
| `python_spec` | `MatchEntrant` | Resolved match input | `None` for VM |
| `slot` | `PythonEntrantState` | Resolved match input | Feeds `derive_agent_seed`; unchanged, unmoved (see "Slot" below) |
| `region` | `Agent`, `PythonEntrantState` | Resolved match input | Fixed at construction, descriptive only (Phase 1 finding #5, reconfirmed) |
| `pc`, `alive`, `regs`, `cpu_used`, `mem_writes` | `Agent` | Mutable execution state | Unchanged |
| `pc`, `register_a`, `register_p`, `zero_flag`, `last_read`, `alive`, `cpu_used`, `total_actions`, `mem_writes` | `PythonEntrantState` | Mutable execution state | Unchanged |
| `derived_seed`, `source_digest`, `local_source_fingerprint(_final)`, `agent_dir`, `loaded` | `PythonEntrantState` | Provenance/reproducibility | Unchanged |
| `diagnostic`, `entrant_termination` | `PythonEntrantState` | Output | Populated only on forfeit/halt |

This matches Phase 1's own classification exactly; Phase 5 changed no
field's category, only how identity-category fields are stored.

## What `kind` is, and is not

`kind` (`"vm"`/`"python"`) determines *how this entrant participates in this
match* -- which runtime executes it, which execution-state class it
resolves onto -- not *who the competitor is*. Asking Phase 3's own test
("could the same logical entrant identity theoretically be executed by
another runtime representation while remaining the same entrant?") the
answer is no in the sense that matters here: a Bytefray agent's kind is
fixed by what it *is* (compiled VM bytecode vs. a Python module), but that
fixedness is a property of the *resolved artifact*, not an abstract
competitor-identity fact the way `agent_id` is. `kind` therefore stays on
`MatchEntrant` (resolved match input), not on `EntrantIdentity` -- consistent
with Phase 1's own classification, which this phase does not revise.

`kind` continues to participate in `canonical_match_id`'s per-entrant
metadata dict exactly as before (`match_service.py`'s `canonical_match_id`
was not touched) -- Phase 5 only changes *where in the internal type system*
`kind` lives, never whether it affects deterministic identity.

## Slot

`PythonEntrantState.slot` and `MatchEntrant`'s implicit schedule-order slot
(the `enumerate(entrants)` index used in `canonical_match_id`,
`PythonEntrantController.__init__`, and `SupervisedPythonEntrantController.
_initialize_entrant`) are unchanged -- still resolved match participation
data, still the second positional argument to `derive_agent_seed`, still
never renumbered, made mutable, or removed. No code in this phase touches
`derive_agent_seed`, its call sites, or the `enumerate` loops that produce
`slot`.

## Start

`start` (`MatchEntrant.start`) is unchanged -- still resolved match
placement data, feeding `Agent.pc`/`region` (via `Kernel.spawn`, untouched)
and `PythonEntrantState.pc`/`region` (via each Python controller's
`__init__`, untouched) exactly as before. Wrap/modulo placement behavior
(`entrant.start % config.arena_size`) is byte-for-byte unchanged.

## `EntrantIdentity` design

**Module:** `engine/src/battle_engine/entrant_identity.py` (new).

```python
@dataclass(frozen=True)
class EntrantIdentity:
    agent_id: str
    name: str
```

**Why this module and not `agent_state.py`:** both the VM and Python paths
need to reference the same identity concept without either importing the
other's module. Like `rules.py` and `scheduler.py` before it, this module
is dependency-free (standard library only) and sits at the bottom of the
runtime import graph; `agent_state.py`, `python_runtime.py`, and
`match_service.py` all import it "upward," and it imports nothing from
`battle_engine`.

**Fields, and why each belongs:** `agent_id` is the canonical, match-slot-
scoped identity string every existing ownership/scoring/statistics/kill-
attribution/replay/result code path already keys by -- unchanged in type,
meaning, or value. `name` is the display label already present on
`MatchEntrant`/`PythonEntrantState`, never authoritative for anything the
engine keys by (canonical IDs remain authoritative over display names --
see "Display-name safety" below).

**`kind` is deliberately excluded** -- see above.

**Immutability:** frozen, matching the fact that neither field changes once
a match starts in any of the three classes that reference it.

**Not a dict key anywhere new:** `EntrantIdentity` is not used as a mapping
key by any production code this phase touched. `kernel.score`,
`kernel.stats`, `vm.ownership_counts`, `vm.writer`, and every other
existing `agent_id`-string-keyed structure remain string-keyed, confirmed
directly by `test_vm_agent_identity_does_not_leak_into_ownership_key_
namespace` (new, see "Tests added").

## Resolved-match model (`MatchEntrant`)

**Composition, not a rename (Option A).** `MatchEntrant` keeps its name and
its exact six-argument positional constructor shape
(`agent_id, name, start, code, kind="vm", python_spec=None`) and the
`MatchEntrant.python(...)` classmethod, unchanged for the ~30 call sites
across the engine, CLI, tournament service, client, and tests that
construct it. Internally, the dataclass's stored fields are now
`identity: EntrantIdentity, start, code, kind, python_spec` -- a custom
`__init__` (the class sets `init=False` and defines its own) builds
`EntrantIdentity(agent_id, name)` once and stores only that, plus the four
resolved-match fields, via `object.__setattr__` (the standard frozen-
dataclass constructor pattern). `agent_id`/`name` are now read-only
properties delegating to `self.identity`.

`start`, `code`, and `python_spec` are completely unchanged -- still plain
fields, still resolved once per match, still read the same way by every
existing caller (`entrant.start`, `entrant.code`, `entrant.python_spec`, all
still plain attribute access, transparently satisfied by a dataclass field
exactly as before).

## VM execution-state design

**What it references:** `agent_state.Agent` now stores `identity:
EntrantIdentity` instead of a flat `agent_id: str` field. Every other field
(`pc`, `alive`, `regs`, `cpu_used`, `mem_writes`, `region`) is unchanged in
name, type, default, and meaning.

**Compatibility accessor:** `agent_id` is a read-only property reading
`self.identity.agent_id`. The constructor keeps its exact original
signature and parameter order (`agent_id, pc, alive=True, regs=None,
cpu_used=0, mem_writes=0, region=(0,0)`) -- every existing `Agent(agent_id=
..., pc=..., ...)` call site across `core.Kernel.spawn`,
`test_replay_reconstruction.py`, and other tests is unaffected.

**No display name was fabricated.** The VM has never tracked a separate
entrant display name on its execution state -- `_build_result` has always
resolved the real name from `MatchEntrant.name` via a local dict, never
from `Agent`. Rather than thread a `name` parameter through `Kernel.spawn`
(which would touch its one production call site plus roughly twenty direct
`kernel.spawn(...)` test call sites for no behavioral gain, since nothing
reads a name off `Agent` today), `Agent.identity.name` synthesizes to
`agent_id` -- an honest statement that no separate display name is known at
this layer, not a fabrication. `_build_result`'s existing name resolution
was deliberately left untouched, and a new regression test
(`test_vm_native_result_name_comes_from_match_entrant_not_synthetic_agent_
identity`) pins that persisted VM results keep sourcing the real display
name from `MatchEntrant`, not from `Agent.identity.name` -- protecting
against a future "simplification" that would silently regress every VM
match's persisted display name to its bare `agent_id`.

**Attribution behavior:** `vm.VM.step`'s `self._wr8(addr, ..., owner=agent.
agent_id)` (ownership/writer tracking), `match.MatchRunner._attribute_
deaths`'s killer comparison, `scoring.ScoringPolicy`/`statistics.
StatisticsCollector`'s `agent.agent_id`-keyed score/statistics updates, and
`telemetry._agent_snapshot`'s replay serialization are **all unchanged
source** -- every one of them reads `agent.agent_id` via plain attribute
access, which the property satisfies transparently. `match.py`, `core.py`,
`vm.py`, `scoring.py`, `statistics.py`, `telemetry.py`, and `results.py`'s
`build_summary`/`resolve_winner` call bodies have **zero source diff** this
phase (`results.py`'s only change is the `HasAgentIdentity` Protocol
declaration -- see "Static validation" below).

## Python execution-state design

**What it references:** `python_runtime.PythonEntrantState` now stores
`identity: EntrantIdentity` instead of flat `agent_id: str`/`name: str`
fields. All eighteen remaining fields (`loaded`, `rng`, `slot`,
`derived_seed`, `source_digest`, `local_source_fingerprint(_final)`,
`agent_dir`, `pc`, `register_a`, `register_p`, `zero_flag`, `last_read`,
`alive`, `cpu_used`, `total_actions`, `mem_writes`, `region`, `diagnostic`,
`entrant_termination`) are unchanged in name, type, default, and meaning.

**Slot handling:** unchanged -- `slot` remains a plain field on
`PythonEntrantState`, populated the same way (`enumerate(entrants)` in each
controller's `__init__`), read the same way by `derive_agent_seed` and
`canonical_match_id`.

**Seed/provenance handling:** unchanged -- `derived_seed`, `source_digest`,
`local_source_fingerprint(_final)`, and `agent_dir` remain plain fields,
computed and stored exactly as before construction completes. Neither
`derive_agent_seed` itself nor either call site that invokes it
(`PythonEntrantController.__init__`, `SupervisedPythonEntrantController.
_initialize_entrant`, `match_service.canonical_match_id`) was touched.

**Mutable runtime fields:** unchanged -- `pc`, registers, `zero_flag`,
`last_read`, `alive`, and the accounting counters continue to be assigned
directly (`state.alive = False`, `state.cpu_used += 1`, …) throughout
`apply_action`, `forfeit_entrant`, and both controllers' tick loops, none of
which reference `identity`, `agent_id`, or `name` in a way that changed.

**Compatibility accessors:** `agent_id`/`name` are read-only properties
reading `self.identity.agent_id`/`self.identity.name`. The constructor
keeps its exact original parameter order and defaults (`agent_id, name,
loaded, rng, slot=0, derived_seed=0, ...`), so both production construction
sites (`PythonEntrantController.__init__`,
`SupervisedPythonEntrantController._initialize_entrant`) and the two direct
test constructions (`test_python_runtime.py`, `test_ownership_accounting.
py`) needed **zero changes**.

## Supervised runtime

`supervised_runtime.py` required **no source changes at all** this phase.
`SupervisedPythonEntrantController._initialize_entrant` already constructs
`PythonEntrantState` with the exact keyword arguments (`agent_id=...,
name=..., loaded=..., rng=..., slot=..., ...`) the refactored constructor
still accepts, and every other read (`state.agent_id`, `handle =
self.handles[state.agent_id]`, `forfeit_entrant(state, diagnostic)`) is
plain attribute access, transparently satisfied by the new property.
`AgentWorkerHandle`/`_NullAgentInstance` remain pure execution-mechanism
infrastructure -- the worker subprocess is not, and was never treated as, a
second gameplay entity; this phase did not need to touch that boundary to
confirm it, since nothing about worker-handle identity changed.

## One-state-per-entrant invariant

Ruleset v1 continues to map exactly one resolved entrant to exactly one
runtime execution state, unconditionally:

- `Kernel.spawn` appends exactly one `Agent` to `self.agents` per call, and
  is called exactly once per `MatchRequest.entrants` element
  (`match_service._run_vm_match`'s `for entrant in request.entrants:`
  loop) -- unchanged.
- `PythonEntrantController.__init__`/`SupervisedPythonEntrantController.
  _initialize_entrant` append exactly one `PythonEntrantState` to
  `self.states` per entrant in `enumerate(entrants)` -- unchanged.
- No new collection type (`dict[EntrantIdentity, list[...]]` or similar)
  was introduced anywhere. `kernel.agents`/`controller.states` remain plain
  `list[Agent]`/`list[PythonEntrantState]`, iterated in construction order.
- `EntrantIdentity` itself carries no notion of "which execution state(s)
  own me" -- it is a value object referenced *by* exactly one `Agent` or
  `PythonEntrantState` per match, never a registry or collection root. There
  is structurally no way to attach two execution states to one identity
  without also constructing two separate `Agent`/`PythonEntrantState`
  objects and appending both to the (still ordinary, still singly-iterated)
  agents/states list -- something no code in this phase does or enables.

`test_vm_match_preserves_entrant_order_and_one_identity_per_execution_state`
and `test_python_match_preserves_entrant_order_and_one_identity_per_
execution_state` (new) directly confirm, for a live three-entrant match,
that the number of distinct `EntrantIdentity` objects equals the number of
execution states equals the number of entrants requested.

## Ordering preservation

Confirmed unchanged, both by inspection and by the two new tests above:

- `MatchRequest.entrants` is still a plain tuple, iterated in order by
  `_run_vm_match`'s spawn loop and both Python controllers'
  `enumerate(entrants)` construction loops -- neither loop changed.
- `Kernel.agents`/`PythonEntrantController.states`/
  `SupervisedPythonEntrantController.states` remain plain lists, appended to
  in construction order, iterated in that same order by the Phase 2
  scheduler, statistics, scoring, and replay publication -- none of that
  code changed.
- Replay/result construction (`_build_result`, `_build_python_result`,
  `_finalize_native_artifacts`) iterates `kernel.agents`/`runtime.states`/
  `result.agents` in the same order as before; no source line in any of
  these three functions changed.

## Seed preservation

`derive_agent_seed(match_seed, slot, agent_id, api_version)` itself was not
touched, and neither were its three call sites. `test_derive_agent_seed_
golden_vectors` (pre-existing, unmodified) continues to pass, pinning the
exact same literal seed values for the same inputs. Constructing an
`EntrantIdentity` never participates in seed material -- `agent_id` is
still passed to `derive_agent_seed` as the same plain `str` it always was
(`entrant.agent_id`, transparently satisfied by the new property before the
string ever reaches the hash).

## Identity preservation

- **Ruleset ID:** `rules.py` has no diff this phase; `BYTEFRAY_RULESET_ID`
  unchanged.
- **`canonical_match_id`:** not touched. Still builds its per-entrant
  metadata dict from `entrant.agent_id`, `entrant.name`, `entrant.kind`,
  `entrant.start`, `entrant.code`, `entrant.python_spec` -- all still plain
  attribute reads, now transparently satisfied by properties for
  `agent_id`/`name` instead of stored fields, producing byte-identical
  values.
- **`result_id`/`replay_id`/`replay_sha256`:** unchanged -- all are pure
  functions of `match_id` and final result/replay content, neither of which
  changed. No `EntrantIdentity` instance, repr, or hash is ever serialized
  into any identity computation -- `canonical_match_id` and `result_id`
  hash plain strings/ints/dicts exactly as before.
- **Golden corpus:** see below.

## Persisted-schema preservation

Zero. Every persisted-artifact code path (`telemetry._agent_snapshot`,
`replay.py`'s `AgentState`/`ReplayHeader`/`MatchResult` construction,
`match_service._build_result`/`_build_python_result`/
`_finalize_native_artifacts`, `result_model.ResultEnvelope`) already builds
its output via explicit field-by-field access (`agent.agent_id`,
`agent.pc`, `state.derived_seed`, …), never via `dataclasses.asdict()`,
`__dict__`, or any other whole-object introspection of `Agent`,
`PythonEntrantState`, or `MatchEntrant` (confirmed by direct repository
search before implementation -- see "Persisted-schema audit" below).
Consequently, changing what those three classes store internally has no
observable effect on any persisted schema. No `battle2.replay`/
`battle2.result`/`bytefray.evaluation`/`bytefray.agent_package` schema
version changed.

**Persisted-schema audit (performed before implementation):** searched for
`asdict(`, `vars(agent`, `vars(state`, `vars(entrant`, `.__dict__`, and
`dataclasses.replace(` against `Agent`/`PythonEntrantState`/`MatchEntrant`
across `engine/src/battle_engine`. Every `asdict()` call site in the
repository operates on an unrelated dataclass (`RuntimeDiagnostic`,
`Config`, evaluation/comparison rows, trace records); none targets any of
the three refactored classes. No `dataclasses.replace()` call targets them
either -- had one existed, it would have needed updating, since `replace()`
calls the dataclass's `__init__` with each declared field's current value
as a keyword argument (`identity=...`, not `agent_id=...`/`name=...`),
which the custom constructors introduced this phase do not accept. This is
a known, narrow limitation of the compatibility-accessor design, recorded
here rather than worked around, since nothing in the repository currently
needs it (see "Architectural debt intentionally left").

## Ruleset semantic preservation

Confirmed unchanged by the full validation run below and by inspection:

- **Scheduling:** `scheduler.run_sequential_quota`/`RulesetPolicy.
  run_scheduler` were not touched; both still operate on `list[Agent]`/
  `list[PythonEntrantState]` via the `alive: bool` structural attribute,
  unaffected by the identity refactor.
- **Termination:** `RulesetPolicy.resolve_termination` was not touched;
  still receives plain `alive_count: int`/`tick: int`/`max_ticks: int`, no
  entrant-identity-shaped argument.
- **Scoring:** `ScoringPolicy.score_alive`/`score_territory`/`score_kill`
  source unchanged; still keyed by `agent.agent_id`, transparently
  satisfied by the property.
- **Winner resolution:** `results.resolve_winner`'s body unchanged; only
  its `HasAgentIdentity` Protocol declaration changed (see "Static
  validation").
- **Kill attribution:** `match.MatchRunner._attribute_deaths` source
  unchanged; VM-only, as before -- neither Python controller calls
  `score_kill`/`record_death(..., killer=...)`.
- **HALT/forfeit:** `apply_action`/`forfeit_entrant` source unchanged;
  both still only ever mutate `state.alive` (plus, for HALT,
  `entrant_termination`), never touch `identity`.

## Tests added

`engine/tests/test_entrant_identity.py` (10 new tests):

1. `test_entrant_identity_is_frozen_hashable_and_value_comparable` --
   `EntrantIdentity` rejects mutation and compares/hashes by value.
2. `test_match_entrant_agent_id_and_name_derive_from_identity_not_
   duplicated_storage` -- `MatchEntrant.agent_id`/`.name` equal
   `.identity.agent_id`/`.identity.name`, and neither is a separately
   stored instance attribute (`vars(entrant)` contains only `identity` and
   the resolved-match fields) -- the central structural claim of this
   phase, verified directly rather than only by value equality.
3. `test_match_entrant_python_classmethod_builds_the_same_identity_shape`
   -- `MatchEntrant.python(...)` produces the same `identity` shape as the
   main constructor.
4. `test_vm_agent_agent_id_derives_from_identity_not_duplicated_storage` --
   same structural proof as #2, for VM `Agent`.
5. `test_python_entrant_state_agent_id_and_name_derive_from_identity_not_
   duplicated_storage` -- same structural proof as #2, for
   `PythonEntrantState`.
6. `test_duplicate_display_names_remain_distinct_entrant_identities` --
   two `EntrantIdentity` instances with the same `name` but different
   `agent_id` compare unequal -- protects the v1.4.1 Designer-fix invariant
   ("canonical IDs remain authoritative over display names") at the new
   identity layer specifically.
7. `test_vm_match_preserves_entrant_order_and_one_identity_per_execution_
   state` -- a live three-entrant VM match: entrant order is preserved
   end-to-end, and exactly three distinct `EntrantIdentity` objects exist,
   one per `Agent` (protects "one-state-per-entrant" and "ordering"
   simultaneously).
8. `test_vm_native_result_name_comes_from_match_entrant_not_synthetic_
   agent_identity` -- a live VM match with a real (non-`agent_id`-shaped)
   display name: `NativeAgentResult.name` is the real name, not `Agent.
   identity.name`'s `agent_id`-mirroring placeholder. Protects specifically
   against the risk this phase's own design choice (VM `Agent` synthesizes
   `identity.name = agent_id`) introduces if a future change naively
   "simplified" `_build_result` to read `agent.identity.name`.
9. `test_python_match_preserves_entrant_order_and_one_identity_per_
   execution_state` -- Python counterpart of #7, additionally asserting
   the exact three `EntrantIdentity` values (including real, distinct
   `name`s, unlike the VM case).
10. `test_vm_agent_identity_does_not_leak_into_ownership_key_namespace` --
    after a live match, `kernel.score`/`kernel.stats`/`vm.ownership_counts`
    remain `str`-keyed, not `EntrantIdentity`-keyed -- protects Step 20's
    "do not turn `EntrantIdentity` into a dictionary key casually."

No existing test was modified.

## Golden corpus

`engine/tests/test_ruleset_v1_equivalence.py`: **8 passed, zero Ruleset-v1
golden differences** -- all six pinned scenarios' `snapshot_sha256`/
`match_id`/`result_id` values are unchanged from the Phase 4 baseline.

## Validation

**Focused** (golden corpus + native-match-service + match-services +
scheduler/Python-scheduler characterization + Python runtime + supervised
runtime + ruleset-policy + scheduler + ownership accounting + ruleset
persistence + replay reconstruction + tournament service + extracted
components + reference agents + v0.1 characterization + agent validation +
agent-lab integration + client analysis/pygame-renderer/playback-
controller/replay-session + the new `test_entrant_identity.py`): **all
passed**, run both immediately after the three-class refactor (before
adding new tests) and again after adding the ten new tests.

**Full suite** (`python -m pytest`, via `--junitxml` since this
environment's `-q` summary line is not reliably captured -- see Phase 3's
validation note for the same observation): **1283 passed, 6 skipped, 0
failures, 0 errors** (`--junitxml` reports `tests="1289"`, `skipped="6"` →
`1289 - 6 = 1283` passed), plus the pre-existing 2 `gui`-marked
deselections `pytest.ini`'s `-m "not gui"` always excludes. This is exactly
10 more than Phase 4's baseline (`1273 passed, 6 skipped, 2 deselected`),
matching the 10 tests added this phase. No pre-existing test's outcome
changed.

**Static validation:**

- `ruff check .`: all checks passed.
- `mypy engine/src/battle_engine`: no issues found (60 source files, one
  more than Phase 4's 59 -- the new `entrant_identity.py`).
- `mypy client/src/battle_client`: no issues found (10 source files,
  unchanged).
- `results.py`'s `HasAgentIdentity` Protocol required one type-only change:
  `agent_id: str` (a plain-attribute declaration) became `@property def
  agent_id(self) -> str: ...` (a read-only declaration), because mypy's
  structural typing rejects a read-only property satisfying a protocol that
  declares a settable attribute (`note: Protocol member HasAgentIdentity.
  agent_id expected settable variable, got read-only attribute`) --
  confirmed with a minimal reproduction before making the change. This is a
  type-checking-only change; `Protocol` classes are never instantiated, so
  it has zero runtime effect. `alive: bool` is unchanged, since both
  `Agent.alive` and `PythonEntrantState.alive` remain genuine mutable
  attributes.

## Files changed

- `engine/src/battle_engine/entrant_identity.py` (new) -- `EntrantIdentity`.
- `engine/src/battle_engine/agent_state.py` -- `Agent` stores `identity:
  EntrantIdentity` instead of `agent_id: str`; adds a compatibility
  `agent_id` property and a custom `__init__` preserving the original
  constructor signature.
- `engine/src/battle_engine/match_service.py` -- `MatchEntrant` stores
  `identity: EntrantIdentity` instead of `agent_id: str`/`name: str`; adds
  compatibility `agent_id`/`name` properties and a custom `__init__`
  preserving the original six-argument constructor signature and the
  `python(...)` classmethod. No other function in this module changed.
- `engine/src/battle_engine/python_runtime.py` -- `PythonEntrantState`
  stores `identity: EntrantIdentity` instead of `agent_id: str`/`name:
  str`; adds compatibility `agent_id`/`name` properties and a custom
  `__init__` preserving the original constructor signature. No other
  function in this module changed.
- `engine/src/battle_engine/results.py` -- `HasAgentIdentity.agent_id`
  redeclared as a read-only property (type-only change, see "Static
  validation").
- `engine/tests/test_entrant_identity.py` (new) -- see "Tests added".
- `docs/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md` (new, this
  document).
- `docs/ROADMAP.md` -- v1.5 section updated with Phase 5 status.

`supervised_runtime.py`, `match.py`, `core.py`, `vm.py`, `scoring.py`,
`statistics.py`, `telemetry.py`, and `rules.py` have **zero source diff**
this phase.

## Architectural debt intentionally left

- **Scoring** (`ScoringPolicy`) and **winner resolution** (`results.
  resolve_winner`) remain outside the Ruleset policy seam, unchanged since
  Phase 4 -- this phase did not touch that boundary, per its own scope.
- **VM/Python execution states remain intentionally distinct** -- no shared
  `ExecutionState` base or protocol beyond the pre-existing, minimal
  `MatchState`/`HasAgentIdentity` structural protocols was introduced.
  `Agent` and `PythonEntrantState` still have almost entirely disjoint
  field sets; only `identity`/`alive`/`pc`/`cpu_used`/`mem_writes`/`region`
  are shared in name, and even `pc`'s meaning differs (a real VM
  instruction pointer vs. controller-side Python bookkeeping, per
  `docs/RULES.md`'s "Source is not arena content").
- **Only one execution state per entrant is supported** -- see "One-state-
  per-entrant invariant" above; no one-to-many collection was introduced.
- **Mixed VM/Python execution remains unsupported** --
  `NativeMatchService.run`'s homogeneous-composition validation is
  unchanged.
- **No Ruleset v2, no Agent API v2.**
- **VM `Agent.identity.name` is a synthetic placeholder (`== agent_id`),
  not a real display name** -- a deliberate, documented asymmetry with
  `PythonEntrantState.identity.name` (always real), left in place rather
  than threading a `name` parameter through `Kernel.spawn` for zero
  behavioral gain (nothing reads `Agent.name`/`Agent.identity.name` in
  production; `_build_result` already resolves the real display name from
  `MatchEntrant` directly). Documented in `agent_state.Agent`'s own
  docstring and protected by
  `test_vm_native_result_name_comes_from_match_entrant_not_synthetic_
  agent_identity` so it cannot silently regress if a future change reaches
  for `Agent.identity.name` expecting it to be a real display name.
- **`dataclasses.replace()` is not supported on `MatchEntrant`, `Agent`, or
  `PythonEntrantState`** -- their custom constructors accept `agent_id`/
  `name` positionally, not the now-internal `identity` field `replace()`
  would try to pass as a keyword argument. Nothing in the repository calls
  `replace()` on any of the three today (confirmed by search before
  implementation); recorded here as a known limitation rather than worked
  around, since adding `identity=` acceptance to each custom `__init__`
  purely for a hypothetical future caller would be exactly the kind of
  unrequested, speculative flexibility this repository's own conventions
  discourage.
- **`_build_result`'s VM display-name resolution (a local `names` dict
  built from `entrants`) was deliberately left as its own, separate
  mechanism** rather than reading `agent.identity.name`, since the latter
  is `Agent`'s synthetic `agent_id`-mirroring placeholder, not the real
  name -- see the point directly above. This is not duplication left in
  place for expediency; the two mechanisms answer genuinely different
  questions (`_build_result`: "what is this entrant's real display name,"
  which only `MatchEntrant` currently knows; `Agent.identity.name`: "what
  identity does this execution state's owner have," which for VM has
  always been `agent_id`-only).

## Phase 5 verdict

**PHASE 5 COMPLETE — ENTRANT IDENTITY AND EXECUTION STATE SEPARATED**

Bytefray now has an explicit `EntrantIdentity` type, and `MatchEntrant`
(resolved match entrant), VM `Agent`, and `PythonEntrantState` (execution
states) each reference one authoritative identity object instead of
independently storing `agent_id`/`name` as flat, duplicable fields. VM and
Python execution states remain intentionally distinct rather than unified
behind a shared abstraction. Ruleset v1 continues to create exactly one
execution state per resolved entrant, with no new one-to-many collection
anywhere. Zero golden differences, zero persisted-schema changes, zero
full-suite regressions, an unchanged static-analysis baseline (one
type-only Protocol change, zero runtime effect), and exactly the ten tests
this phase added.

## Recommended Phase 6 boundary

With scheduling (Phase 2), the dispatch seam (Phase 3), termination
(Phase 4), and entrant identity/execution-state separation (Phase 5) all
now behind clean structural boundaries, the strongest remaining candidate
named by every prior phase's own "architectural debt" section is **an
architecture-equivalence qualification pass across all four completed
v1.5 refactors together** -- not a new refactor, but a dedicated
verification milestone: re-running the full golden corpus plus every
characterization suite added across Phases 1-5 against one qualified
commit, and auditing for any transitional compatibility accessor
(`Agent.agent_id`, `PythonEntrantState.agent_id`/`.name`, `MatchEntrant.
agent_id`/`.name`, the `RulesetPolicy` default-parameter pattern on
`Kernel`/both Python controllers) that could now be tightened without
churn, before v1.5.0 itself is prepared for release. Moving scoring/winner
resolution into the `RulesetPolicy` seam remains available but was already
named by Phase 4 as "a structural relocation with no duplication to
eliminate, not a genuine Phase-4-shaped win" -- that judgment is unchanged
by Phase 5 and still applies. Release preparation itself (version bump,
changelog, tagging) is out of scope for any phase named here, per this
prompt's own hard scope boundary.
