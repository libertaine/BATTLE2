# evaluation_history

**Modules:** `engine/src/battle_engine/agent_evaluation.py` (v2 writer,
additive), `engine/src/battle_engine/evaluation_history/` (new package: v1/v2
adapters, discovery, comparison, health, CLI), with narrow, discovery-ID-only
fixes to `app/services/agent_catalog.py`, `app/views/development.py`,
`app/views/evaluation.py`, `app/agent_designer.py`.
**Purpose:** harden `bytefray.evaluation` capture (v2) and add read-only,
Qt-free history/comparison across evaluation runs: `bytefray agents
evaluations list|show|compare`.

Status: design spec, written before implementation, per `CONTRIBUTING.md`'s
spec → issue → prompt → PR flow. Built incrementally alongside
implementation; kept authoritative and synchronized as each slice lands.

## 1. Established v0.6.1 facts (verified in source, not assumed)

- `agent_evaluation.py` already implements `run_dir` on `agent_test.test_agent`
  (not a pending TODO — confirmed at `agent_test.py` and its use at
  `agent_evaluation._execute_cell`).
- `evaluation_id = stable_id("evaluation", {candidate identity, baseline
  identity or None, opponent identities (ordered), seeds (ordered), ticks,
  agent_api_version})`. It does **not** include `Config`'s other fields
  (`arena_size`, `instr_per_tick`, `win_mode`, `weights`) because
  `agent_test.py` never lets a caller vary them — they are always `Config()`
  defaults today. v2 must still record them explicitly (see §3) rather than
  relying on that being true forever.
- `canonical_match_id` (`match_service.py`) hashes the **full** effective
  `Config` (`seed`, `arena_size`, `instr_per_tick`, `win_mode`,
  `asdict(weights)`) plus per-entrant identity (`derived_seed`,
  `source_sha256`, `api_version`, `agent_version`) and entrant order. This is
  the existing canonical precedent for "effective execution conditions" — v2
  reuses its shape rather than inventing a second one.
- `tournament.json` (`battle2.tournament` v1) has **no timestamp fields at
  all** — there is no existing lifecycle-timestamp precedent in this
  codebase to reuse verbatim; v2 introduces the first one, scoped narrowly to
  evaluation.
- The Designer bug is real and precisely located: `app/views/development.py`
  `python_agent_names()` returns `AgentRow.name`, which
  `app/services/agent_catalog.py` populates with `spec.display` (display
  name), not `spec.name` (discovery id). `app/agent_designer.py` passes that
  list into `EvaluationDialog`; `app/views/evaluation.py`'s
  `candidate_id()`/`baseline_id()`/`opponent_ids()` return those display
  strings directly; `app/services/designer_workflows.
  build_designer_evaluate_command` forwards them verbatim as CLI arguments.
  When display name != discovery id, `bytefray agents evaluate` receives a
  string `resolve_agent` cannot find.
- The fixed-output bug is real and precisely located:
  `app/agent_designer.py` hardcodes
  `self.battle_root / "runs" / "evaluations" / "designer-evaluation"`
  regardless of the selected plan.
- `AgentSpec` (`agents.py`) already carries both `name` (discovery id) and
  `display` (display name) — the catalog layer just doesn't expose `name` to
  the evaluation dialog today. No new discovery concept is needed, only
  wiring the field that already exists.

## 2. v2 identity payload

```python
def planned_identity_payload(
    candidate: AgentSpec,
    baseline: AgentSpec | None,
    opponents: Sequence[AgentSpec],   # ordered, request order, duplicates preserved
    seeds: Sequence[int],             # ordered, request order, duplicates preserved
    ticks: int,
    effective_conditions: EffectiveConditions,
    rules_compatibility_id: str,
    agent_api_version: int,
) -> dict[str, Any]: ...

evaluation_id = stable_id("evaluation-v2", planned_identity_payload)
```

This reuses `agent_identity()`/`stable_id()`/`canonical_json()` unchanged
(§8 of `agent_evaluation.md`), extended with three fields v1 never hashed:

- `effective_conditions` (§3) — so an `arena_size`/`win_mode`/weights
  override (once one ever exists) changes identity, not just seed/ticks.
- `rules_compatibility_id` (§4) — so a scoring/winner-resolution semantics
  bump changes identity even when nothing else did.
- an explicit `"identity_version": 2` marker, so a v1 and v2
  `evaluation_id` computed from *otherwise identical* inputs are
  byte-for-byte guaranteed to differ (they already would in practice because
  the payload shape differs, but the marker makes this a documented
  invariant, not an accident of hashing).

Excluded, exactly as v1 already excludes: timestamps, `output_dir`,
filesystem paths, outcomes, `complete`/lifecycle state, `project.version`
(package version — only `agent_api_version` and `rules_compatibility_id`
enter the hash; see §4 for why package version alone is insufficient but is
still recorded for humans).

v1 and v2 `evaluation_id`s occupy different identity spaces by construction:
a v1-produced default output directory (`runs/evaluations/<v1-id>`) is never
implicitly resumed by a v0.7 invocation of the same candidate/opponents/seeds
run under v2, because the v2 payload always differs from the v1 payload it
supersedes (different hashed fields, plus the `identity_version` marker).
This is intentional (§1's "v1 and v2 IDs cannot be mistaken for equivalent
contracts") and is a visible, documented behavior change from pure byte
compatibility, not a silent one: a user upgrading from v0.6.1 who reruns an
existing evaluation gets a **new** v2 artifact at a new path, and the old v1
artifact remains on disk, readable, untouched. `bytefray agents evaluate`'s
CLI contract (flags, output shape when `--output` is explicit) is otherwise
unchanged.

## 3. Effective conditions

```python
@dataclass(frozen=True)
class EffectiveConditions:
    tick_limit: int
    arena_size: int
    action_budget: int          # Config.instr_per_tick
    win_mode: str
    weights: dict[str, float | int]   # asdict(Config().weights)
    subject_slot: str = "A"     # TESTED_AGENT_SLOT
    opponent_slot: str = "B"    # OPPONENT_SLOT
    entrant_order: tuple[str, str] = ("A", "B")
    runtime_kind: str = "python"
    agent_api_version: int
    supervision: str = "unsupervised"   # evaluation always runs timeout=None
    tracing: str = "untraced"           # evaluation always runs trace=False
```

Recorded once per evaluation (constant across every cell, since
`agent_test.py` gives no per-cell override surface — §2 finding 4 of
`agent_evaluation.md` still holds). `seed` is deliberately excluded from
`EffectiveConditions` itself: it varies per cell and is already captured by
each cell's `seed`/`seed_index` (§6), not duplicated here. A stable,
opaque `effective_conditions_fingerprint = stable_id("evaluation-conditions",
asdict(effective_conditions))` is stored alongside the readable fields (per
Part I's "a stable fingerprint may be stored alongside the readable payload,
but must be reproducible from those fields").

`supervision`/`tracing` are recorded as fixed string labels, not booleans,
because they are read straight off `agent_evaluation.py`'s hardcoded
`timeout=None, trace=False` call (§10 of `agent_evaluation.md`) — future
evaluation code that makes these configurable would widen the enum, not
change its meaning.

## 4. Rules/runtime compatibility identifier

```python
# battle_engine/evaluation_history/models.py
EVALUATION_RULES_COMPATIBILITY_ID = "evaluation-rules-1"
```

A hand-maintained string, independent of `ProjectInfo.version`, bumped only
when one of these evaluation-relevant behaviors changes: `ScoringPolicy`'s
scoring semantics, `results.resolve_winner`'s winner-resolution rule,
Python-vs-Python scheduling order (`PythonEntrantController.run`'s fixed
A-before-B slot order), derived-seed policy (currently N/A — evaluation
seeds are always literal, never derived; if that ever changes, this ID must
bump), or match-runtime behavior that changes whether/how a cell completes.
Persisted verbatim in every v2 artifact's `effective_conditions` and hashed
into `evaluation_id` (§2). Documented here, not auto-derived from package
version, because a documentation-only release and a scoring-changing release
must not silently share an identifier, and because package-version equality
is not proof of complete environmental equality (interpreter version, OS,
dependency versions can still differ) — this ID intentionally covers *only*
evaluation/match comparability semantics, nothing broader.

v1 artifacts have no such field. Comparison (§9) treats its absence as
`unknown`, never as an implied match.

## 5. Lifecycle and provenance

Timestamp format: `datetime.now(timezone.utc).isoformat(timespec="microseconds")`
with the `+00:00` suffix normalized to `Z` (helper: `_utc_now_iso()`).
Example: `2026-08-09T14:03:07.123456Z`. All three fields use this format.

```json
{
  "created_at": "2026-08-09T14:03:07.123456Z",
  "updated_at": "2026-08-09T14:03:09.881002Z",
  "finished_at": null,
  "lifecycle_state": "running",
  "abort_reason": null,
  "abort_detail": null
}
```

- `created_at` is written once, in the very first atomic checkpoint, before
  any cell executes (so a crash during cell 1 still leaves discoverable
  lifecycle state — Part I's explicit requirement).
- `updated_at` is rewritten at every atomic checkpoint (unchanged per-cell
  cadence from v1's `_write_state` calls).
- `finished_at` is written only in the same atomic write that also writes
  final `aggregates`/`comparison` and flips `lifecycle_state` to
  `"finished"` — the same call, not two calls, so a crash between them is
  impossible by construction (Python single-process atomic-rename write).
- `lifecycle_state`: `"running"` (checkpointed, incomplete),
  `"finished"` (scheduler reached its terminal point — §5.1), or
  `"aborted"` (stopped early; `abort_reason` is currently only
  `"source_drift"`, `abort_detail` holds the typed diagnostic, §7).
- No-op resume (every scheduled cell already `completed`/trusted, nothing
  re-executed) still performs its final aggregate/comparison recomputation
  and writes `updated_at`, but MUST NOT change `created_at`, MUST NOT append
  a new execution context (§6), and MUST NOT change any cell's
  `execution_context_id`. This is asserted directly by test (§10).

### 5.1 `finished` vs. healthy

`lifecycle_state == "finished"` means the scheduler reached its terminal
point: every cell in the matrix reached `completed`/`failed`/`corrupted` and
final aggregation/comparison were written. It does **not** mean every cell
is scorable — `subject_init_failed`/`opponent_init_failed`/`failed`/
`corrupted` cells may coexist with `finished`. Health (§8) is a materially
separate axis; `complete: true` is retained only as a legacy/presentation
field with v1's original meaning (`len(cells) >= matrix_size`) documented as
such, not treated as v2's authoritative truth.

## 6. Execution provenance / execution contexts

```python
@dataclass(frozen=True)
class ExecutionContext:
    context_id: str          # stable_id("evaluation-context", {...})
    bytefray_version: str
    agent_api_version: int
    python_version: str
    result_schema_version: int
    replay_schema_version: int
    rules_compatibility_id: str
    first_used_at: str       # UTC iso, first cell executed under this context
```

`evaluation.json["execution_contexts"]` is a list of these, keyed by
`context_id` (`stable_id` over every field except `first_used_at`, so two
runs under byte-identical environments share one context even across
separate invocations that both append to the same evaluation). Each newly
*executed* v2 cell records `execution_context_id` pointing at one of these.
Cells trusted from prior state on resume keep their originally recorded
`execution_context_id` unchanged. If the current process's context is not
yet present when a cell is about to be freshly executed, it is appended
before that cell runs (so the list only grows to contain contexts that
actually produced at least one cell). A no-op resume therefore never
appends anything (§5). An evaluation whose cells reference more than one
`execution_context_id` is not an error — it is a truthful record of a retry
performed under a different environment — and `show`/`list` must report
`"execution: mixed"` rather than picking one arbitrarily.

## 7. Source drift protection

**Revised after an independent adversarial review (v0.7 correction pass,
"B1") found that the original design below was not actually TOCTOU-safe as
written.** The original post-check recomputed its "expected" `match_id` by
calling `canonical_match_id`, which reads `spec.source_path` from disk
*at call time* — so a post-check running *after* a cell had already
executed would simply re-read whatever the file currently contained,
which could be the same (already-drifted) content the executor itself had
just read. Comparing two fresh reads of the same live file to each other
is vacuous; it does not detect that the file changed since the plan was
frozen. The strategy actually implemented by `EvaluationService` closes
that gap:

1. **Freeze once.** `EvaluationService.run` builds `planned_identities`
   (one `agent_identity()` call per candidate/baseline/opponent) exactly
   once, immediately after `_validate`, before any cell executes.
   `evaluation_id` is derived from that *same* dict (never a second,
   independent `agent_identity()` call) so the persisted
   `planned_identities` payload is structurally guaranteed to reproduce the
   recorded `evaluation_id` — the frozen snapshot and the id it produced
   can never independently drift apart.
2. **Pre-check** (`_detect_pre_execution_drift`, immediately before each
   cell's `test_agent` call). Re-resolve the cell's subject and opponent
   and compute `agent_identity(spec)`; compare against the *frozen*
   snapshot from step 1 (never re-derived from a live `AgentSpec.source_path`
   later). A mismatch on any field is drift.
3. **Post-check** (`_post_execution_identity_drift`, after a real match
   runs). Compares the frozen snapshot against the *executor's own
   recorded* per-entrant metadata (`NativeAgentResult.metadata`'s
   `source_sha256`/`api_version`/`agent_version`, embedded in the match
   result `test_agent` already returned) — not a second independent disk
   read. This is what actually catches a source edit landing between the
   pre-check and `test_agent`'s own internal resolution/execution.
4. **Initialization failures** get a *live re-resolve* against the frozen
   plan instead (no `NativeAgentResult.metadata` exists when an agent
   fails to initialize — `RuntimeDiagnostic` carries no identity fields).
   This still has its own read-after-the-fact race, but it is strictly
   narrower than not checking at all, and prevents a source edit that
   causes an init failure from being silently attributed to the original,
   frozen agent.
5. On first detected drift (any check, either role): **stop scheduling
   further cells immediately.** The drifted cell itself is recorded with
   `status="drift_detected"` and a typed diagnostic. Every cell that
   already completed validly before the drifted one is preserved
   unchanged. The final checkpoint sets `lifecycle_state="aborted"`,
   `abort_reason="source_drift"`, `abort_detail={role, agent_id, cell
   schedule_id, mismatched fields}`. No `finished_at` is written.
   `--retry-failed` never retries a `drift_detected` cell, even after the
   source is restored to its original content — the only correct recovery
   is a fresh evaluation.
6. A fresh evaluation (new plan/output, since the changed source now
   produces a different `evaluation_id` anyway) is required to continue
   evaluating the changed agent — the aborted artifact is never silently
   resumed or "fixed up" by rerunning inside the same output directory.

**Documented residual TOCTOU window (not claimed to be closed).** Inside
`python_runtime.PythonEntrantController.__init__`, an agent's module is
loaded/executed first, and its `source_sha256` is computed by a *separate*,
subsequent `read_bytes()` call. An edit that lands and then reverts to the
originally-planned bytes before that digest read — or before this module's
own inputs are otherwise captured — is not detectable from outside that
call, and no check in this module can close it without changing
`python_runtime` itself. In practice this means: any edit that lands and
*stays* is caught (proven by TOCTOU tests using real file/manifest
mutation, not just a monkeypatched drift detector); a transient edit that
fully reverts before anything reads it is not, and must not be, falsely
reported as drift either.

Helper/imported-source changes (an agent's entry point importing a sibling
module or nested local package) are a related but distinct concern from
this section's *timing* race — see §H3 (`agent_identity.
local_source_fingerprint`) for how those are covered; that mechanism is
scoped to an agent's own `agents/<id>/` directory only, and is checked at
planning time (evaluation_id/pre-execution drift), not against
`NativeAgentResult.metadata` (which has no concept of "every local file
loaded").

No source is embedded or snapshotted anywhere — drift detection is entirely
comparison of small identity fingerprints already computed for other reasons
(§2), never a copy of agent source.

## 8. Duplicate occurrence coordinates

Every v2 cell gains four fields beyond v1's:

```python
opponent_index: int              # 0-based position in request.opponent_ids
seed_index: int                  # 0-based position in request.seeds
matrix_ordinal: int              # 1-based global position (was implicit in
                                  # schedule_id's hash input in v1; now explicit)
condition_occurrence_index: int  # 0-based count of prior cells for this
                                  # subject sharing the same (opponent_id, seed)
                                  # pair, in request order
```

`condition_occurrence_index` is the field cross-evaluation alignment (Part
IV) actually uses: two evaluations that both evaluate `opponent_ids=[
"seeker", "seeker"]` at `seeds=[7]` each produce two cells per subject with
`opponent_id="seeker", seed=7`; occurrence index `0`/`1` lets a comparison
align "first seeker@7 attempt" with "first seeker@7 attempt" deterministically
without relying on `schedule_id` (evaluation-local only, §9) or directory
names. `schedule_id` keeps its existing v1 role (within-evaluation identity
for resume + Designer drill-down) unchanged; it is never read by the history/
comparison layer as a join key.

## 9. v2 artifact shape (full)

```json
{
  "schema": "bytefray.evaluation",
  "schema_version": 2,
  "identity_version": 2,
  "evaluation_id": "evaluation-v2_<hex24>",
  "candidate_id": "...", "baseline_id": "...|null",
  "opponent_ids": ["..."], "seeds": [0],
  "ticks": 200, "matrix_size": 40,
  "planned_identities": {
    "candidate": { "...": "agent_identity() dict" },
    "baseline": null,
    "opponents": [ "...one agent_identity() dict per ordered occurrence..." ]
  },
  "effective_conditions": { "...§3 fields...": null },
  "effective_conditions_fingerprint": "evaluation-conditions_<hex24>",
  "rules_compatibility_id": "evaluation-rules-1",
  "created_at": "...", "updated_at": "...", "finished_at": "...|null",
  "lifecycle_state": "running|finished|aborted",
  "abort_reason": null, "abort_detail": null,
  "execution_contexts": [ "...§6..." ],
  "project": { "...ProjectInfo, unchanged shape..." },
  "cells": [ "...v1 fields + §8 coordinates + execution_context_id + condition_fingerprint..." ],
  "aggregates": [ "...unchanged shape, always recomputable from cells..." ],
  "comparison": [ "...unchanged shape..." ],
  "complete": true
}
```

Every additive field beyond v1 is optional-safe to add without touching
`battle2.result`/`battle2.replay`/Agent API v1 — none of them are read.

## 10. v1/v2 domain model and adapters (`evaluation_history/`)

New Qt-free package, one focused module per concern (chosen over one
monolith because schema adaptation, discovery, and comparison are
independently testable and independently likely to grow):

```
battle_engine/evaluation_history/
    __init__.py        # re-exports the stable public surface
    models.py           # common typed domain model (Sec 11)
    v1_adapter.py        # read-only v1 -> common model
    v2_adapter.py        # read-only v2 -> common model
    discovery.py         # filesystem scan -> ArtifactListing
    health.py            # typed diagnostics (Sec 12)
    comparison.py         # alignment + verdicts (Sec 13)
    cli.py                # list/show/compare (Sec 14)
```

Depends only on `battle_engine.{agents,agent_evaluation,config,paths,
project_info,result_model,replay}` (identity/result/replay facilities it is
explicitly permitted to depend on) — never on `app.*`/Qt/pygame. A headless
import test (`test_evaluation_history_headless_imports`) asserts this.

### 11. Common domain model (`models.py`)

```python
class FieldConfidence(Enum):
    RECORDED = "recorded"        # read directly from the artifact
    RECOVERED = "recovered"      # derived from nested result.json (v1 only)
    UNKNOWN = "unknown"          # no evidence either way
    CONFLICTING = "conflicting"  # two evidence sources disagree
    VERIFIED = "verified"        # recorded value cross-checked against a
                                  # canonical artifact (replay digest, etc.)

@dataclass(frozen=True)
class ConfidenceValue(Generic[T]):
    value: T | None
    confidence: FieldConfidence

@dataclass(frozen=True)
class ArtifactLocation:
    evaluation_json_path: Path        # absolute, resolved
    directory: Path                   # containing directory
    file_modified_at: str             # ISO UTC, explicitly labeled fallback

@dataclass(frozen=True)
class SchemaSupport:
    schema: str
    schema_version: int
    supported: bool
    reason: str | None                # set when supported=False

@dataclass(frozen=True)
class AdaptedCell:
    # subset of Sec 9's cell fields common to v1/v2, each wrapped where the
    # source artifact might not provide it (v1 lacks coordinates/context)
    schedule_id: str
    subject_role: str
    subject_id: str
    opponent_id: str
    seed: int
    status: str
    outcome: str | None
    opponent_index: ConfidenceValue[int]
    seed_index: ConfidenceValue[int]
    condition_occurrence_index: ConfidenceValue[int]
    score_subject: float | None
    score_opponent: float | None
    territory_subject: float | None
    territory_opponent: float | None
    condition_fingerprint: ConfidenceValue[str]

@dataclass(frozen=True)
class EvaluationSummary:
    location: ArtifactLocation
    schema: SchemaSupport
    evaluation_id: str
    candidate_id: str
    baseline_id: str | None
    opponent_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    matrix_size: int
    lifecycle_state: ConfidenceValue[str]
    created_at: ConfidenceValue[str]
    health: "HealthReport"            # Sec 12
    cells: tuple[AdaptedCell, ...]
    rules_compatibility_id: ConfidenceValue[str]
    aggregates_recomputed: tuple[SubjectAggregate, ...]   # never trusted-as-is
```

`aggregates_recomputed` is **always** computed from `cells` by the adapter
(reusing `agent_evaluation.aggregate_cells` unchanged), never read verbatim
from the artifact's stored `aggregates` — this single rule satisfies both
"recompute when absent" (v1) and "derived fields must never override
contradictory canonical cell state" (Part I) with one code path instead of
two.

Unknown legacy v1 fields are represented as `FieldConfidence.UNKNOWN`, never
silently defaulted to a current-schema value (e.g. a v1 artifact with no
`rules_compatibility_id` produces `ConfidenceValue(None, UNKNOWN)`, not
`ConfidenceValue("evaluation-rules-1", RECORDED)`).

### 12. Health model (`health.py`)

```python
class HealthCode(Enum):
    HEALTHY = "healthy"
    FINISHED_WITH_INIT_FAILURES = "finished_with_init_failures"
    FINISHED_WITH_FAILED_CELLS = "finished_with_failed_cells"
    FINISHED_WITH_CORRUPTED_CELLS = "finished_with_corrupted_cells"
    UNFINISHED = "unfinished"
    SOURCE_DRIFT_ABORTED = "source_drift_aborted"
    MALFORMED_JSON = "malformed_json"
    WRONG_SCHEMA = "wrong_schema"
    UNSUPPORTED_VERSION = "unsupported_version"
    INVALID_REQUIRED_FIELDS = "invalid_required_fields"
    MISSING_NESTED_RESULT = "missing_nested_result"
    MISSING_REPLAY = "missing_replay"
    REPLAY_DIGEST_MISMATCH = "replay_digest_mismatch"
    RESULT_MATRIX_MISMATCH = "result_matrix_mismatch"
    UNKNOWN_LEGACY_CONDITION = "unknown_legacy_condition"
    NON_PORTABLE_ABSOLUTE_PATH = "non_portable_absolute_path"
    DUPLICATE_IDENTITY_LOCATION = "duplicate_identity_location"

@dataclass(frozen=True)
class HealthReport:
    codes: tuple[HealthCode, ...]     # every applicable code, never just one
    detail: tuple[str, ...]           # human-readable, index-aligned with codes
    verified: bool                    # True only after --verify's deep pass ran
```

`codes` is a tuple, not a single enum, because multiple states can coexist
(e.g. `FINISHED_WITH_FAILED_CELLS` and `NON_PORTABLE_ABSOLUTE_PATH`
simultaneously) — this is the "don't let a single boolean flatten these
states" requirement (Part V) satisfied directly by the type.

### 13. Discovery (`discovery.py`)

```python
def default_roots() -> tuple[Path, ...]:
    return (get_data_root() / "runs" / "evaluations",)

def discover(
    *,
    roots: Sequence[Path] = (),
    artifacts: Sequence[Path] = (),   # explicit evaluation.json or directory paths
) -> ArtifactListing: ...
```

`roots` defaults to `default_roots()` when both `roots` and `artifacts` are
empty. Each root is scanned non-recursively one level deep
(`root/*/evaluation.json`), never recursing into arbitrary subdirectories or
following the pattern outside the given roots/explicit paths — matching
Part III's "do not recursively scan arbitrary disks or user home
directories."

```python
@dataclass(frozen=True)
class ArtifactListing:
    entries: tuple["DiscoveredEvaluation", ...]
    duplicate_identity_groups: tuple[tuple[str, tuple[Path, ...]], ...]

@dataclass(frozen=True)
class DiscoveredEvaluation:
    location: ArtifactLocation
    schema: SchemaSupport
    evaluation_id: str | None   # None only when schema/parse failed entirely
    summary: EvaluationSummary | None    # None on hard failure
    health: HealthReport
```

One malformed sibling never raises out of `discover()` — every failure mode
becomes a `DiscoveredEvaluation` with `summary=None` and an explanatory
`HealthReport`, never an exception propagating past that one entry (proven
by `test_discovery_malformed_sibling_does_not_abort_listing`). Two
locations sharing the same `evaluation_id` are both listed individually
*and* cross-referenced in `duplicate_identity_groups`; a selector (§14)
naming an evaluation ID that matches more than one location raises a typed
`AmbiguousSelectorError` requiring a path-qualified selector instead.

`file_modified_at` (filesystem mtime) is populated on every
`ArtifactLocation` and is the *only* place mtime is exposed; it is never
substituted for `created_at`/`updated_at`.

Default listing performs shallow health only (JSON parse + schema/field
validation + cell-count/coordinate consistency — no replay digest
verification, no nested result re-read beyond what v1's recovery already
needs). `--verify` (§14) performs the deeper canonical
`verify_replay_digest`/`verify_result_replay` pass, only for the specific
selected artifact(s), not on every discovered sibling — this is the "shallow
discovery health vs. selected-artifact/deep verification" split Part III
requires, and keeps default `list` fast regardless of how many artifacts
exist (§16 performance).

### 14. Comparison (`comparison.py`)

```python
def align(
    left: EvaluationSummary, right: EvaluationSummary, *, deep_verified: bool = False
) -> AlignedComparison: ...
```

**`deep_verified`** (added in the v0.7 correction pass, "B3") must be
`True` only when the caller has already run
`evaluation_history.verification.verify_summary` on *both* `left` and
`right` (i.e. `bytefray agents evaluations compare --verify`). It gates
reproducibility-anomaly and baseline-control-anomaly detection below —
see the corrected §14.1. An ordinary (non-`--verify`) comparison leaves
this `False`, and CLI/JSON output for that comparison must say plainly
that its evidence was not deep-verified rather than implying it was.

Orientation is always `right` (new) relative to `left` (old) — this is
explicit in every returned/printed structure, never implicit positional
convention alone.

**Strict shared-condition fingerprint** (excludes candidate identity by
construction — candidate identity is compared and reported *separately* as
the experimental variable, never folded into the shared-condition key):

```python
def condition_key(cell: AdaptedCell, opponent_identity: dict, conditions_fp: str,
                   rules_id: str | None) -> tuple[Any, ...]:
    return (
        opponent_identity["agent_id"], opponent_identity["source_sha256"],
        opponent_identity["entry_point"], opponent_identity["api_version"],
        cell.seed, conditions_fp, rules_id, cell.condition_occurrence_index.value,
    )
```

Two cells align only when every element of `condition_key` matches exactly,
**and** both sides' `condition_occurrence_index` confidence is not
`UNKNOWN` (an unknown coordinate never compares equal to anything, including
another unknown — Part IV's "unknown required dimensions do not compare
equal"). `rules_id=None` (v1 without a compatibility field) never equals any
value, including another `None` from a different v1 artifact — two v1
artifacts with no rules ID are never silently treated as rules-compatible;
they can still be shown side-by-side descriptively (§14.3), just never given
a direct verdict.

For v1, `condition_occurrence_index` is recovered only when the artifact's
cell list, in file order, gives unambiguous, consistent per-(subject,
opponent,seed) counting evidence (i.e., no malformed/duplicate schedule IDs
disrupting the count); otherwise it is `UNKNOWN` for every cell in that
duplicate group, and that entire group becomes an explicit
`ambiguous_duplicate_group` in the result rather than a guessed pairing.

**Verdict** (only for aligned pairs where both cells are `is_scored`):

```python
def verdict(left_outcome: str, right_outcome: str) -> str:
    # identical mapping to agent_evaluation.classify, oriented right-vs-left
    ...   # "improved" | "regressed" | "unchanged"
```

`"inconclusive"` covers: either side not scored (init failure/failed/
corrupted/missing), or a differing pair whose two cells ran under
materially different or unknown execution contexts (added in the v0.7
correction pass, "H2" — equivalence cannot be established across
incompatible runtimes, so an otherwise-differing verdict is downgraded to
inconclusive with a `reason` rather than reported as an ordinary
improvement/regression; an `unchanged` verdict is left alone since it
makes no cross-runtime equivalence claim). A **reproducibility anomaly**
(§14.1) is a related but separate, narrower classification layered on top
of an `improved`/`regressed` row (via `ComparisonRow.reproducibility_anomaly`,
never by itself producing `"inconclusive"`): it requires `deep_verified`
*and* both individual cells having actually verified (`AdaptedCell.verified
is True`), not merely a matching candidate identity fingerprint — a
fingerprint match alone was found to be an insufficient basis for this
claim during the v0.7 correction pass ("B3") and no longer triggers it.

```python
@dataclass(frozen=True)
class AlignedComparison:
    orientation: str                    # "right_relative_to_left"
    candidate_changed: bool
    candidate_diff: dict[str, tuple[Any, Any]] | None
    baseline_context: "BaselineContext"
    rows: tuple["ComparisonRow", ...]
    unmatched_left: tuple[AdaptedCell, ...]
    unmatched_right: tuple[AdaptedCell, ...]
    changed_condition: tuple[tuple[AdaptedCell, AdaptedCell], ...]
    ambiguous_duplicate_groups: tuple[tuple[Any, ...], ...]
    reproducibility_anomalies: tuple["ComparisonRow", ...]
    denominators: "ComparisonDenominators"
```

```python
@dataclass(frozen=True)
class ComparisonDenominators:
    left_total: int
    right_total: int
    condition_intersection: int
    directly_comparable: int
    improved: int
    regressed: int
    unchanged: int
    inconclusive: int
    unmatched_left: int
    unmatched_right: int
    changed_condition: int
    ambiguous_duplicate_groups: int
    corrupt_or_missing: int
```

Every denominator is always populated, even when zero — no field is omitted
because a bucket is empty (Part IV's "always expose denominators").

#### 14.1 Candidate semantics

`candidate_diff` is populated (non-`None`) whenever any planned candidate
identity field differs between left and right, regardless of whether
`candidate_id` (the logical ID) itself changed — a same-ID source edit and a
different-ID candidate both populate it, but `candidate_changed` is `True`
only for the logical-ID case, and the CLI/JSON explicitly labels that case
"different candidates" rather than presenting it as a revision (Part IV).

If `candidate_diff is None` (fingerprints identical) and strict conditions
match and the comparison ran with `deep_verified=True` *and* both cells on
that row actually verified individually (not merely "the `--verify` flag
was passed" — a specific cell can still fail to verify even under
`--verify`), but `outcomes differ` on an aligned row, that row is added to
both `rows` (with its plain verdict) and `reproducibility_anomalies`
(flagged) — never silently relabeled as `improved`/`regressed` without the
anomaly flag, and never flagged at all from evidence that was only read
and recomputed from each artifact's own recorded fields.

#### 14.2 Opponent semantics

An aligned row additionally carries `opponent_identity_changed: bool` and
`opponent_diff`. `condition_key` (above) already prevents source/entry-point/
API changes from aligning as the *same* row — an opponent identity change
therefore shows up as `changed_condition`, not as a row with a diff flag, by
construction. A rename-equivalent relaxation (same executable identity,
different logical ID) is **not** implemented in v0.7 — out of scope per Part
IV's "may be offered... only if the specification and CLI make that
relaxation visible," and no product requirement in this task asks for it;
documented here as a deliberate deferral, not an oversight.

#### 14.3 Baseline semantics

```python
@dataclass(frozen=True)
class BaselineContext:
    left_baseline_id: str | None
    right_baseline_id: str | None
    identity_status: str   # "absent_both" | "absent_one" | "same" | "changed" | "unknown_legacy"
    control_rows: tuple["ComparisonRow", ...]   # only when identity_status == "same"
    control_anomaly: bool   # requires deep_verified=True and both cells verified on the
                             # anomalous row (same gate as reproducibility_anomalies, §14.1) --
                             # never derived from a bare verdict != "unchanged" check
```

Baseline identity differences never block candidate-cell comparison rows
(candidate cells are independent matches — Part IV). When
`identity_status == "same"` and both baseline cell sets verify, baseline
cells are compared the same way candidate cells are (§14 verdict function)
purely as a control signal; if that control shows anything other than
`unchanged`, `control_anomaly=True` is set and surfaced prominently, since
an identical baseline producing different outcomes under identical
conditions indicates an environment/determinism problem, not a candidate
result.

### 15. CLI (`evaluation_history/cli.py`)

```
bytefray agents evaluations list   [--root PATH ...] [--artifact PATH ...] [--json]
bytefray agents evaluations show   <evaluation-id-or-path> [--root PATH ...] [--verify] [--json]
bytefray agents evaluations compare <left> <right> [--root PATH ...] [--verify] [--json]
```

Wired into `command.py._agents` as one more `if argv[0] == "evaluations":`
branch (mirroring the existing `evaluate`/`inspect`/`diverge` branches
exactly), lazily importing `battle_engine.evaluation_history.cli.main`. The
deprecated `battle2` alias reaches it through the existing shared dispatch —
no second implementation.

A bare `<evaluation-id-or-path>`/`<left>`/`<right>` selector is resolved:
if it parses as an existing filesystem path (file or directory containing
`evaluation.json`), it is used directly; otherwise it is looked up as an
`evaluation_id` against the discovered roots, raising `AmbiguousSelectorError`
(exit `2`) if more than one location matches.

**Exit codes** (documented here, pinned by test):

- `0`: the command executed and produced its requested result — for
  `compare`, this includes a result containing regressions or degraded
  sibling entries; for `list`/`show`, this includes results containing
  unhealthy/legacy entries, as long as the requested artifact(s) themselves
  were readable enough to report on.
- `1`: the specifically selected artifact/comparison could not produce a
  trustworthy requested result — `show`/`compare` on an artifact that fails
  to parse at all, `compare` with zero directly comparable cells and zero
  other explicit outcome buckets to report, or a `--verify` deep-integrity
  failure on the selected artifact.
- `2`: invalid arguments, an ambiguous/missing selector, or an incompatible
  request shape (e.g. comparing two paths that don't exist).

`list` itself never exits non-zero solely because a *sibling* (not the
selected artifact — `list` has no single "selected" artifact) is malformed;
malformed siblings are reported as rows with their health code, and `list`
exits `0` as long as it could enumerate the roots at all.

JSON output serializes the typed dataclasses above via a stable, explicit
`to_json_dict` on each (sorted keys where order is not semantically
significant; list order is always semantically significant and preserved).
No CLI human-text parsing anywhere in this package — JSON is produced from
the same typed objects the human renderer reads, never derived from the
human string.

### 16. Performance

Discovery/adaptation stays on-demand scanning (Part III's pinned decision;
no index). Measured methodology: synthetic v2 artifacts matching the
40-cell reference shape (1 candidate, 4 opponents, 5 seeds), written
directly (not executed) to avoid multi-minute real-match generation time,
over 10/100/1000-artifact populated roots, three untimed warm-up scans
discarded, five timed repetitions averaged, wall-clock, on this development
machine (Windows, this checkout's `.venv`):

| n artifacts | avg scan+adapt time | sample artifact size |
|---|---|---|
| 10 | ~18 ms | 20,763 B |
| 100 | ~182 ms | 20,763 B |
| 1000 | ~1,862 ms | 20,763 B |

This is roughly 5x slower per artifact than the v0.6.1 raw-JSON-scan
baseline already on record (10: ~3.7ms, 100: ~36ms, 1000: ~358ms) — expected,
since `list`'s default path now performs full typed adaptation (aggregate
recomputation via `aggregate_cells`, per-field `ConfidenceValue` wrapping,
health-code derivation) rather than a raw parse. Absolute time remains
well under two seconds even at 1000 artifacts, a population size well
beyond what a typical data root accumulates; this does not, on its own,
meet the "measurements demonstrate a real requirement" bar Part III sets
for introducing an index, so none was added.

### 17. Designer fixes (no history UI in this slice)

**Discovery ID vs. display name.** `AgentRow` (`agent_catalog.py`) already
carries the discovery id in `meta["name"]`; `python_agent_names()`
(`development.py`) is changed to return `(display, agent_id)` pairs (or an
equivalent typed row) instead of bare display strings, and
`EvaluationDialog` (`evaluation.py`) is changed so its combo/list widgets
display `display` but their `.currentData()`/associated `Qt.UserRole` carry
`agent_id`; `candidate_id()`/`baseline_id()`/`opponent_ids()` return the
discovery ids. `build_designer_evaluate_command` itself needs no change — it
already just forwards whatever strings it is given; the fix is entirely at
the selection-collection boundary. A regression test uses a fixture agent
whose manifest `display` differs from its directory name and asserts the
built CLI argument list contains the directory name.

**Fixed-output collision.** Before launching the `QProcess`, the Designer
now calls `EvaluationService.preflight(...)` in-process (Qt-free; it only
resolves agent manifests via `resolve_agent`, no agent code execution — the
same safety boundary the CLI's own `--dry-run` preflight call already
relies on) to compute this plan's actual default output directory
(`<data-root>/runs/evaluations/<evaluation_id>`), and passes it explicitly
via `--output` unless the user overrides the field. This preserves same-plan
resume (`preflight` is deterministic and side-effect-free, so calling it
twice for the same plan yields the same directory both times) while
eliminating the collision, using only the existing preflight/evaluation-id
architecture — no new parsing of arbitrary stdout, matching the prompt's
explicit "don't reintroduce fragile stdout parsing if a typed/preflight
solution exists" guidance. If `preflight` raises
`EvaluationConfigurationError` (unknown/invalid agent selection), the
Designer surfaces that error before ever spawning the process, rather than
launching a doomed `QProcess`.

Designer history UI (list/open/compare inside the Designer) is **deferred**
out of this slice: the domain/CLI layer above is substantial on its own, and
Part VII explicitly permits deferral when adding history UI would threaten
domain/CLI quality within the same slice. The deferred slice's shape (a
read-only "Evaluation History…" action reusing `EvaluationResultsDialog`/
`TraceInspectorDialog`/replay-open plumbing already built for `evaluate`) is
recorded here so a follow-up has a concrete starting point, not just a
placeholder.

## 18. Compatibility

- No `battle2.result`/`battle2.replay`/Agent API v1 change.
- `tournament_service.py`/`match_service.py` are not modified.
- v1 `evaluation.json` artifacts remain fully readable and are never
  mutated by any history/discovery/comparison operation (enforced by tests
  that snapshot a v1 fixture's bytes before and after every operation this
  spec adds).
- `bytefray agents evaluate`'s existing flags/exit-code contract (§12 of
  `agent_evaluation.md`) is unchanged; only the artifact it writes gains
  `schema_version: 2` and the additive fields above.

## 19. Correction to `docs/specs/agent_evaluation.md`

§7's `schedule_id` prose describes hashing `(evaluation_id, role,
subject_id, opponent_id, seed)` without mentioning `ordinal`; the shipped
v0.6.1 code (`build_matrix`, verified directly) includes `ordinal` in that
hash specifically to keep duplicate cells' `schedule_id`s distinct (see the
inline comment at `agent_evaluation.py`'s `build_matrix`). This spec is
corrected as part of this task (§7's code block there gains the `ordinal`
key) rather than left stale.

## 20. Deferred / explicitly out of scope

Matches Part X's "explicitly out of scope" list verbatim: no revision
store, no embedded source snapshots, no generic provenance system, no
run-instance ledger, no database/index, no ranking/Elo/statistics, no
Designer charts/dashboards/tags, no Agent API v2, no scoring/rules redesign.
Also deferred within this slice specifically: Designer history UI (§17),
opponent rename-equivalence relaxation (§14.2), and exhaustive-permutation
test coverage for every bullet enumerated in the parent task's Part VIII
(the test suite covers every acceptance-criterion-bearing behavior with
focused tests per §21 below, not a combinatorial expansion of every listed
scenario).

## 21. Testing and validation criteria

Each behavior in §2–§17 above gets at least one focused test; the full list
is tracked in the implementation PR/commit series rather than duplicated
here verbatim. Minimum bar before this spec is considered satisfied:
`evaluation_id` determinism and its sensitivity to every §2 input;
lifecycle atomicity (pre-cell checkpoint exists, finished+aggregates+
timestamp are one atomic write); no-op resume provenance stability (§5);
source drift stopping the matrix and preserving prior cells (§7); duplicate
coordinate correctness including asymmetric multiplicity; v1 artifacts never
mutated; one malformed sibling never aborting discovery; strict condition
fingerprint excluding candidate identity; duplicate alignment never using
`schedule_id`; denominators always populated; CLI exit codes for all three
classes in human and JSON mode; Designer discovery-id and output-path fixes;
headless import check (no Qt/pygame pulled in by `evaluation_history`).
Full headless `python -m pytest`, both `mypy` invocations, and the
repository's configured Ruff checks must pass before this feature is
reported complete.
