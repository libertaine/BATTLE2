# Bytefray Compatibility Reference

This is a concise policy/reference document, not a duplicate of every
schema specification: it names the independent compatibility axes Bytefray
maintains, says what is a stable-candidate contract for the 1.x series
versus explicitly unsupported/experimental, and gives a worked table for
deciding which axis a given change actually requires bumping. For the full
wire-level detail behind each axis, follow the links below rather than
expecting this document to repeat them.

## Stable-candidate contracts for 1.x

The following are candidates for a stable-contract declaration at 1.0 —
see `docs/ROADMAP.md` for the release criterion this feeds into:

- **Ruleset v1** (`bytefray-rules-1`) — the gameplay semantics described in
  [RULES.md](RULES.md).
- **Agent API v1** — the Python loading/lifecycle/`Observation`/
  `AgentAction` contract and its frozen deterministic RNG derivation,
  described in [AGENT_API_V1.md](AGENT_API_V1.md).
- **Result and replay current schemas** — `battle2.result` v1 and
  `battle2.replay` v3, described in [RESULT_SCHEMA.md](RESULT_SCHEMA.md)
  and [REPLAY_SCHEMA.md](REPLAY_SCHEMA.md).
- **Evaluation current schema/history behavior** — `bytefray.evaluation`
  v4/identity v4 and the `evaluations list/show/compare` history behavior
  described in `docs/specs/evaluation_history.md`.
- **Agent revision identity/verification behavior** — the content-
  addressed revision store described in `docs/specs/agent_revision.md`.
- **Agent package format** (new in v1.2.0) —
  `bytefray.agent_package` schema version 1, a transport wrapper around
  one agent revision, described in `docs/specs/agent_package.md`. Newer
  than the other entries in this list, called out explicitly rather than
  silently folded in: package validity/integrity is a stable, versioned
  contract, but it deliberately makes no Ruleset-compatibility claim (an
  Agent API v1 agent isn't bound to one Ruleset the way a match/evaluation
  artifact is) and no code-trust claim (a valid package proves structure/
  integrity/provenance, never that the contained agent code is safe).
- **Canonical CLI surfaces where explicitly supported** — `bytefray run`,
  `bytefray tournament`, `bytefray replay`, `bytefray agents
  create/validate/test/evaluate/inspect/diverge/revisions/evaluations/
  export/import/package`, and their documented flags (README.md,
  `docs/AGENT_LAB.md`, `docs/TOURNAMENTS.md`).

## Separate compatibility axes

These axes are independent and must not be conflated — a change to one
does not imply, and should not silently piggyback on, a change to another:

| Axis | What it identifies | Where it lives |
|---|---|---|
| Project/package version | The installable release (e.g. `0.10.0`). | `pyproject.toml` / `ProjectInfo.version`. |
| Agent API version | The Python agent programming contract, including RNG derivation. | `battle_engine.agent_api.AGENT_API_VERSION`. |
| Ruleset identity | The gameplay rules of the game itself. | `battle_engine.rules.BYTEFRAY_RULESET_ID`. |
| Artifact schema versions | Wire shape of persisted artifacts. | `battle_engine.replay.SCHEMA_VERSION` (`battle2.replay`), `battle_engine.result_model` (`battle2.result`), `battle_engine.agent_evaluation.SCHEMA_VERSION`/`IDENTITY_VERSION` (`bytefray.evaluation`), `battle_engine.agent_trace` (`bytefray.agent_trace`). |
| Evaluation methodology fields | How `agents evaluate` measures agents (orientation coverage, arena-alignment/placement/layout disclosure, seed set, Ruleset selection, roster/seat assignment for multi-entrant), not gameplay itself. | `bytefray.evaluation`'s `orientation_mode`/`arena_alignment_mode`/`rules_compatibility_id`/`group`/`roster_agent_ids` (request-resolved as of v2.0.0-beta2 Phase 1/2) fields, and each cell's `placement_id`/`subject_start`/`opponent_start` (1v1) or `roster_agent_ids`/`seat_agent_ids`/`layout_id`/`seat_starts` (multi-entrant). |
| Agent revision identity | Content-addressed identity of one archived copy of an agent's source. | `battle_engine.agent_revisions`. |
| Source fingerprint versions | Deterministic hash-scope versioning for drift detection. | `battle_engine.agent_api.LOCAL_SOURCE_FINGERPRINT_VERSION`, `battle_engine.agent_revisions`' own fingerprint version. |
| Agent package format | Wire shape/versioning of the portable `.bytefray-agent` transport container itself — independent of the agent revision identity it wraps. | `battle_engine.agent_package.PACKAGE_SCHEMA_VERSION` (`bytefray.agent_package`). |

A gameplay-semantic change bumps exactly the Ruleset identity. A Python
programming-contract change (including an incompatible RNG-derivation
change) bumps exactly the Agent API version. A wire-shape change bumps
exactly the relevant schema version. None of these three should ever
require bumping either of the other two on its own — see the table below
for worked examples, including cases where a change legitimately requires
more than one axis at once.

## Ruleset identity

```python
BYTEFRAY_RULESET_ID = "bytefray-rules-1"
```

defined in `battle_engine.rules`. See [RULES.md](RULES.md) for the full
Ruleset v1 contract and its bump policy.

## Ruleset v2 (beta)

`v2.0.0-beta1` introduces a second Ruleset identity:

```python
BYTEFRAY_RULESET_V2_ID = "bytefray-rules-2"
```

defined in `battle_engine.ruleset_policy`, resolved through the same
fail-closed `resolve_ruleset_policy` seam as every other identity. See
[RULES_V2.md](RULES_V2.md) for the full Ruleset v2 gameplay contract and
`docs/V2_0_BETA1_PLAN.md`/`docs/V2_0_RULESET_V2_CANDIDATE.md` for the
evidence behind it.

- **Status: beta candidate semantic identity**, introduced during 2.0 beta
  development from the v2.0 alpha research program's evidence-backed
  result. It is not claimed as permanently immutable forever the way
  Ruleset v1's contract is — a beta or RC qualification pass could still
  find reason to revise it before a final 2.0 release, though no such
  revision is expected without new evidence.
- **Agent API version is unaffected.** Ruleset v2 is a gameplay-semantics
  identity; Agent API v1 (`battle_engine.agent_api.AGENT_API_VERSION == 1`)
  remains the supported Python programming contract for both Ruleset v1 and
  Ruleset v2. Ruleset identity and Agent API version are independent
  compatibility axes (see the table above) — bumping one never implies
  bumping the other.
- **The same Agent API v1 Python agent source may execute under more than
  one compatible Ruleset.** Nothing in the loading/lifecycle contract,
  `Observation`, or `AgentAction` changed; an agent written against
  `docs/AGENT_API_V1.md` runs unmodified whether the match resolves
  `bytefray-rules-1` or `bytefray-rules-2` (the only behavioral difference
  is what the shared arena does around it, not what the agent is allowed to
  do).
- **Runtime support: Python-runtime gameplay only.** Vulnerable Core and
  core observability are implemented only in
  `battle_engine.python_runtime`/`supervised_runtime`. As of `v2.0.0-beta1`
  Phase 2, `battle_engine.match_service.NativeMatchService` enforces this as
  an authoritative execution-compatibility boundary: a match requested under
  the permanent `bytefray-rules-2` identity with **any** VM entrant is
  rejected (`RulesetRuntimeUnsupportedError`) before any entrant executes
  and before any replay/result artifact is written — the Ruleset policy
  itself (`battle_engine.ruleset_policy.RULESET_V2.supported_runtime_kinds
  == frozenset({"python"})`) declares this restriction, and every production
  caller (CLI `run`/`tournament`/`agents test`, and anything built on them)
  inherits it from the one shared seam. **VM parity is not claimed** — this
  is a compatibility boundary, not a promise that VM entrants would see
  Vulnerable Core semantics if only they were allowed to run.
  `bytefray-rules-2-alpha1`/`-alpha11` are deliberately excluded from this
  restriction and keep their original behavior: the policy resolves and the
  match dispatches successfully with the core mechanic simply inert, exactly
  as before Phase 2 — preserving historical alpha-artifact reproducibility
  rather than retroactively rejecting matches those experiments already ran.
- **Artifacts record the exact Ruleset.** Every native result/replay written
  under Ruleset v2 persists the literal `"bytefray-rules-2"` string in its
  `ruleset_id` field (`ResultEnvelope`/`ReplayHeader`), exactly like every
  other registered identity — see "Persisted Ruleset identity on native
  result/replay artifacts" above, which applies unchanged to this identity
  (it required no new plumbing: `ruleset_id` was already generic).
- **Alpha Ruleset artifacts remain distinct historical experiment
  identities.** `bytefray-rules-2-alpha1` and `bytefray-rules-2-alpha11` are
  **not** aliased to `bytefray-rules-2` in either direction —
  `rules._RULESET_ALIASES` gains no entry for any of the three. Even though
  `bytefray-rules-2` shares its exact behavioral implementation with
  `bytefray-rules-2-alpha11` (the evidence being promoted is intentionally
  identical at promotion time — see
  `engine/tests/test_ruleset_v2_promotion_equivalence.py`), the three
  identities dispatch, hash into `canonical_match_id`, and persist
  separately, so no historical alpha artifact can ever be silently
  reinterpreted as a permanent Ruleset-v2 artifact, and evaluation
  comparison/resume both continue to fail closed across any pair of them.

## Ruleset-v2 1v1 evaluation methodology (v2.0.0-beta2 Phase 1)

`agents evaluate` gained an explicit `--ruleset {bytefray-rules-1,
bytefray-rules-2}` selector. This is an **evaluation methodology** change,
never a gameplay change — no Ruleset semantic, Agent API, or artifact
schema (`battle2.result`/`battle2.replay`) was touched. Two independent
compatibility guarantees hold:

- **Omitted, or explicit `bytefray-rules-1`.** Resolves to the exact same
  historical v1 evaluation methodology, byte-for-byte: identical
  `evaluation_id`/`schedule_id` hash payloads, identical
  `SCHEMA_VERSION`/`IDENTITY_VERSION` (4), identical matrix shape/size for
  the same request. No pre-Phase-1 evaluation script, preset, or resumed
  artifact changes behavior.
- **Explicit `bytefray-rules-2`.** A new methodology: a standard,
  mechanically-derived three-placement set, a standard five-seed default,
  and capture/core evidence — see
  [V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md](V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md).
  Uses a second, additive schema/identity version,
  `SCHEMA_VERSION_V2`/`IDENTITY_VERSION_V2` (5) — there is no historical
  `bytefray-rules-2` evaluation artifact to preserve compatibility with,
  since evaluation had no Ruleset selector at all before this phase.

Placement (`EvaluationPlacement`/each cell's `subject_start`/
`opponent_start`) is a new, additive identity axis. `match_service.
canonical_match_id`'s Python-entrant metadata now includes `"start"`
whenever a Python entrant's start address is non-zero. This key's
*absence* at `start=0` keeps every historical **start=0** Python
`match_id`/`result_id`/`replay_id` byte-for-byte unchanged — but it is
**not** an unconditionally no-op addition for every historical Python
match, and it is not true that every historical Python match ever ran at
`start=0`. Non-zero Python starts have always been reachable: explicit
`bytefray run --a-start/--b-start/--c-start`, and — more consequentially —
every tournament entrant past the first, since `bytefray tournament`
(`tournament_cli`) has always placed entrant `index` at
`index * (arena_size // entrant_count)`, nonzero for every index but 0.
For any such non-zero-start Python match, this is a **deliberate,
one-time identity transition** (the same kind of transition
`canonical_match_id`'s own docstring documents for the earlier addition of
`BYTEFRAY_RULESET_ID`), not a silently-safe additive fix:

- A Python `match_id`/`result_id`/`replay_id` computed by a pre-`v2.0.0-
  beta2` build for a non-zero-start entrant differs from what this build
  now computes for the identical inputs.
- Resuming a pre-Beta2 tournament artifact that used non-zero starts under
  Beta2 can therefore report `resumed_result_mismatch` — the artifact's
  own recorded `match_id` no longer matches the id `tournament_service`
  re-derives for the same scheduled match. This is the intended, fail-
  closed outcome (`tournament_service._resumed_result_mismatch` refuses to
  silently trust a result it cannot recompute the identity of), never a
  silent misattribution — see `TournamentService.run`'s `--retry-failed`
  handling for how such a match is re-executed rather than left
  `corrupted` indefinitely.
- `bytefray run` (single ad hoc matches, not resumed against prior state)
  is unaffected in practice: a non-zero `--a-start`/`--b-start` match
  simply gets a new, correctly start-sensitive identity going forward.

## Multi-entrant ("group") evaluation methodology (v2.0.0-beta2 Phase 2)

`agents evaluate --group` fields the candidate together with every
`--opponents` entry as one N-entrant roster per cell, instead of Phase 1's
pairwise "one cell per opponent." Requires `--ruleset bytefray-rules-2`;
every non-`--group` evaluation (v1 or Phase 1's pairwise v2) is completely
unaffected — see
[V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md](V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md).
Uses a third, additive schema/identity version,
`SCHEMA_VERSION_V2_GROUP`/`IDENTITY_VERSION_V2_GROUP` (6) — as with Phase
1's version 5, there is no historical group-evaluation artifact to
preserve compatibility with. `EvaluationLayout`/`EvaluationSeatAssignment`
(roster/seat/layout) are new, additive identity axes for group cells only;
Phase 1's `EvaluationPlacement`/`orientation` (1v1) path is untouched.

This phase also fixed a defect discovered in its own manual
characterization: `evaluation_history`'s artifact-health self-consistency
check (an independent rehash of `evaluation_id`/`condition_fingerprint`
used to verify an artifact was computed honestly) had not been updated
when Phase 1 added `"placements"` to that hash payload, so it falsely
reported `planned_identity_inconsistent`/`condition_fingerprint_
inconsistent` on every Phase-1-produced artifact. This was a
*verification* bug only — no persisted `evaluation_id`/`schedule_id`/
`match_id` was ever actually wrong, and none was rewritten by the fix.

## Historical alias: evaluation-rules-1 ↔ bytefray-rules-1

`bytefray.evaluation`'s `EVALUATION_RULES_COMPATIBILITY_ID` (wire field
`rules_compatibility_id`, introduced in v0.7.0 as the literal string
`"evaluation-rules-1"`) is, as of v0.10 Phase 2, a derived alias of
`BYTEFRAY_RULESET_ID`:

```python
EVALUATION_RULES_COMPATIBILITY_ID = BYTEFRAY_RULESET_ID
```

This is justified by direct inspection of the gameplay-semantic source
history — see [RULES.md](RULES.md)'s "Historical relationship to
evaluation-rules-1" section for the git-history evidence — which shows the
gameplay semantics `"evaluation-rules-1"` was always narrowly scoped to
(scoring, winner resolution, Python scheduling order, derived-seed policy)
have been unchanged for the value's entire existence.

This alias does **not** rewrite history. An `evaluation.json` artifact
persisted before this alias existed still literally contains the string
`"evaluation-rules-1"` in its `rules_compatibility_id` field; it never
contained, and readers must never pretend it contained, the string
`"bytefray-rules-1"`. Historical wire field names (`rules_compatibility_id`)
are unchanged — only how the *current* value is computed changed, from an
independently maintained literal to a derived one. The practical effect
going forward: a gameplay-semantic change requires exactly one Ruleset
bump, not a Ruleset bump plus a separate hand-maintained evaluation-rules
bump.

As of v0.10 Phase 4, comparison behavior between two artifacts' recorded
values is explicitly **normalized**, not merely unchanged:
`battle_engine.rules.normalize_ruleset_id` maps the one established
historical alias (`"evaluation-rules-1"` → `BYTEFRAY_RULESET_ID`) so that
`bytefray agents evaluations compare` can align a historical baseline
against a fresh run's cells directly, rather than reporting every pair as a
`changed_condition` merely because Phase 2 renamed the canonical spelling.
This is a small, explicit, finite lookup table (`battle_engine.rules.
_RULESET_ALIASES`) — **never** prefix/pattern matching — so an unrelated
or future Ruleset identity (a hypothetical `"bytefray-rules-2"`) never
opportunistically normalizes to today's value. The artifact's own recorded
value (`rules_compatibility_id`/`EvaluationSummary.rules_compatibility_id
.value`) is exposed unchanged; only the *comparison alignment key* is
normalized.

## Persisted Ruleset identity on native result/replay artifacts

v0.10 Phase 4 makes `battle2.result`/`battle2.replay` independently
answer, from the artifact itself or an evidence-backed adapter, which
gameplay Ruleset produced one native match:

- Every current native (VM or Python) match writes `ruleset_id:
  "bytefray-rules-1"` into both `result.json`'s envelope
  (`battle_engine.result_model.ResultEnvelope.ruleset_id`) and the
  canonical replay's header record
  (`battle_engine.replay.ReplayHeader.ruleset_id`) — one discriminator
  per match, on the header only, exactly like `runtime_kind` already
  works (see [REPLAY_SCHEMA.md](REPLAY_SCHEMA.md)'s "Runtime-kind
  semantics"). Both are additive fields; neither schema was bumped (see
  [RESULT_SCHEMA.md](RESULT_SCHEMA.md)/[REPLAY_SCHEMA.md](REPLAY_SCHEMA.md)
  for the reader-tolerance evidence).
- A `redcode94`/pMARS result never *claims* Bytefray Ruleset v1 — but
  "absent" and "explicit `null`" are two different, precisely distinguished
  facts here, not interchangeable phrasing (see
  [RESULT_SCHEMA.md](RESULT_SCHEMA.md)'s "Ruleset identity" for the full
  detail): the current writer (`ResultEnvelope.as_dict()`, used by both the
  native and pMARS paths) always emits the `ruleset_id` key, so a current
  `redcode94` result has `"ruleset_id": null` — key **present**, value
  `null` — never `"bytefray-rules-1"`. Only a `result.json` written
  *before this field existed at all* (any pre-Phase-4 artifact, native or
  pMARS) has the key genuinely, structurally **absent**. Both decode to
  `ResultEnvelope.ruleset_id is None` at the Python level, and
  `resolve_result_ruleset` treats them identically via `mode`, which is
  what actually carries the "not applicable" fact — not whether the JSON
  key itself was present. pMARS produces no canonical replay at all, so
  this absent-vs-null question does not arise for `battle2.replay`.
- `battle_engine.result_model.resolve_result_ruleset`/`battle_engine.
  replay.resolve_replay_ruleset` attribute a confidence-qualified answer
  for an artifact that predates this field: `"recorded"` (field present
  and non-null), `"recovered"` (field `None`, but the artifact's own
  shape/mode is evidence-backed as Ruleset v1 — every native
  `battle2.result` v1 result, and every `battle2.replay` header whose
  `schema_version` is **exactly** `3`, since neither shape ever existed
  before the v0.3.0 "Bytefray Rename & Native Core" rewrite that
  established the currently-frozen gameplay semantics), `"unknown"` (no
  evidence — a genuine `battle2.replay` schema-version-2 header, which the
  pre-rename `v0.2.0` release's own canonical writer also produced, plus
  any future schema version greater than 3 until deliberately proven to
  fall in the same window — the check is exact equality, never `>=`, so an
  unrelated future wire-shape bump is never silently also treated as a
  Ruleset-provenance fact), or `"not_applicable"` (any `redcode94` result,
  whether its `None` came from an explicit current-writer `null` or a
  genuinely absent historical key). See the compatibility matrix below for
  the full artifact/version/runtime table.
- **`ruleset_id` is a first-class input to `match_id`'s hash payload**
  (`match_service.canonical_match_id`), sibling to `reproducibility`/
  `entrants`, never folded into `reproducibility` (see
  [RULES.md](RULES.md)'s "Configuration values are not Ruleset identity").
  `result_id`/`replay_id` inherit this transitively, since both already
  embed `match_id`. This is a **deliberate, one-time native-ID
  transition**: because exactly one Ruleset has ever existed, hashing its
  literal value in changes the `match_id`/`result_id`/`replay_id` a v0.10
  Phase 4+ build computes relative to a pre-Phase-4 build, for
  byte-identical execution inputs. Historical stored IDs are never
  rewritten; only fresh computation changes. The direct consequence: a
  `tournament.json`/`evaluation.json` left mid-run by a pre-Phase-4 build
  will show its already-completed matches/cells as
  `resumed_result_mismatch`/`corrupted` on the first Phase-4+ resume — the
  existing, safe, fail-closed behavior any other `match_id` mismatch
  already produces (never silently trusted, never a crash), requiring
  `--retry-failed` or a fresh run. This mirrors the precedent already set
  when `bytefray.evaluation` moved v1 → v2's strictly richer identity
  payload. See [RESULT_SCHEMA.md](RESULT_SCHEMA.md#identity-recipe) for
  the full rationale and pinned tests.
- These four states deliberately reuse a self-contained
  `battle_engine.rules.RulesetProvenance`/`RulesetConfidence` vocabulary
  rather than importing `evaluation_history`'s richer `FieldConfidence`/
  `ConfidenceValue` machinery, which depends on `battle_engine.
  agent_evaluation` and sits well above `battle_engine.rules` in the
  dependency direction. Do not collapse the two vocabularies into one.
- Cross-artifact consistency: a resumed tournament match or evaluation
  cell whose recorded `result.json` `ruleset_id` disagrees with its own
  replay header's `ruleset_id` is treated exactly like an existing
  `match_id`/`result_id` disagreement — demoted to `corrupted`, never
  silently trusted
  (`tournament_service._resumed_result_mismatch`/`agent_evaluation.
  _resumed_cell_mismatch`). The same check is part of `evaluations
  show/compare --verify`'s deep verification
  (`evaluation_history.verification.verify_cell`).
- `battle2.tournament` intentionally does **not** gain a `ruleset_id`
  field: every tournament match already references its own canonical
  `result.json`/`replay.jsonl`, tournament divisions are already
  homogeneous (all-VM or all-Python), and an echoed field would be purely
  redundant informational data with a compatibility-documentation cost and
  no concrete benefit. Tournament-level Ruleset compatibility is derived
  from constituent match artifacts, not stored separately.
- `bytefray.agent_trace` and agent revision manifests
  (`battle_engine.agent_revisions`) are unchanged. A trace records the
  Agent API boundary, not gameplay outcome, and revision identity answers
  "what exact source tree" independently of "under what game rules it
  ran" — see [RULES.md](RULES.md) and `docs/specs/agent_revision.md`.

## Legacy compatibility matrix

| Artifact | Version/era | Rules identity behavior |
| --- | --- | --- |
| `result.json` | current native (VM or Python) | `recorded` `bytefray-rules-1` |
| `result.json` | legacy native, `battle2.result` v1, missing field | `recovered` `bytefray-rules-1` (proven stable since v0.3.0) |
| `result.json` | `redcode94`/pMARS | `not_applicable` |
| `replay.jsonl` header | current native, schema v3 | `recorded` `bytefray-rules-1` |
| `replay.jsonl` header | legacy schema v3, missing field | `recovered` `bytefray-rules-1` (v3 never existed before v0.3.0) |
| `replay.jsonl` header | genuine schema v2 (v0.2.0-era canonical, or adapted v0.1) | `unknown` (predates the proven-stable window) |
| `evaluation.json` | current, `rules_compatibility_id: "bytefray-rules-1"` | recorded; treated as canonical |
| `evaluation.json` | historical v2-v4, `rules_compatibility_id: "evaluation-rules-1"` | recorded verbatim; **normalized** to `bytefray-rules-1` for comparison alignment only |
| `evaluation.json` | v1 (no `rules_compatibility_id` field at all) | `unknown` (never recoverable — v1 never persisted this identifier) |
| `tournament.json` | any | no field; derive from each constituent match's own `result.json`/`replay.jsonl` |

## Experimental/unsupported boundaries

The following are explicitly **not** part of the 1.x stability promise,
regardless of how mature adjacent functionality is:

- **Mixed VM/Python matches** — rejected outright; not implemented.
- **Security sandboxing of Python agent code** — the Agent Lab
  worker-subprocess timeout (`docs/AGENT_LAB.md`) is development-time hang
  **containment**, not a security sandbox; agent code runs with the same
  OS privileges as its host process.
- **Hard callback containment on every execution path** — only
  `bytefray agents test`/`agents validate` run supervised by default;
  `bytefray run`/`tournament` still run Python entrants in-process with no
  hard timeout.
- **Replication / corruptible Python-core designs** — research-stage
  ideas tracked in [FUTURE_PLANS.md](FUTURE_PLANS.md), not implemented.
- **Redcode/pMARS authoring, evaluation, and gameplay parity with the
  native engine** — pMARS interoperability continues, but does not use
  Bytefray Ruleset v1, Agent API v1, or the canonical replay schema; see
  [RULES.md](RULES.md)'s "Redcode/pMARS — not Ruleset v1".
- **Arena translation/placement robustness in evaluation** — decided in
  v0.10 Phase 3: the standard 1.0 `agents evaluate` methodology uses a
  single, fixed arena alignment for every cell (`arena_alignment_mode:
  "fixed"`) and explicitly discloses that translation robustness is not
  evaluated. This is a deliberate, evidence-informed deferral, not an
  oversight — Python arena translation cannot be implemented without
  either an incompatible Agent API v1 change (out of bounds) or
  substantial new shared Python-runtime engineering that is its own,
  separately scoped future effort; VM/native placement is directly usable
  today via `MatchEntrant.start` but `agents evaluate` is Python-only and
  has no VM path to attach it to. See `docs/ROADMAP.md` and
  `docs/RULES.md`.
- **Future rulesets** (advanced offensive mechanics, arena-size research,
  multipronged agents, replication) — anything in that category would
  require a Ruleset identity beyond `bytefray-rules-1`, tracked in
  [FUTURE_PLANS.md](FUTURE_PLANS.md), and is explicitly not part of
  Ruleset v1.

## Compatibility-change impact table

| Change | Ruleset bump | Agent API bump | Schema bump | Methodology change |
| --- | ---: | ---: | ---: | ---: |
| Territory scoring formula | yes | no | no | no |
| Default territory weight | no | no | no | no |
| Arena-size default | no | no | no | no |
| Ownership semantics | yes | maybe, only if API exposure changes | no | no |
| Kill attribution | yes | no | no | no |
| Python RNG derivation | no | yes | no | no |
| Existing `ActionKind` redefined | possibly yes | yes | maybe | no |
| Candidate-first → both orientations | no | no | no | yes |
| Fixed alignment → translation suite | normally no | only if API semantics change | maybe, only if wire shape changes | yes |
| Replay optional telemetry field | no | no | normally no (additive) | no |
| Revision-store sharding | no | no | no | no |
| Agent package (`bytefray.agent_package`) wire-shape change | no | no | no (bumps `PACKAGE_SCHEMA_VERSION`, its own independent axis) | no |

Use this table as a starting heuristic, not a substitute for judgment —
verify a specific change's actual effect against [RULES.md](RULES.md),
[AGENT_API_V1.md](AGENT_API_V1.md), and the relevant schema document
before deciding which axis to bump.
