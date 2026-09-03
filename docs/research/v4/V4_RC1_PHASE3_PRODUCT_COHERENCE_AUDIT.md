# Bytefray v4 RC Path — Phase 3: Product Coherence, Default Audit and Pre-RC Defect Sweep

Branch: `v4-rc1-development`

Starting SHA: `b2000c4d84ae4452c83b59fb5bb5549f55374a8d` (Phase 2's ending commit)
Ending SHA: `7c9780c5f2c01d43040e160b8b7a94dbd65b2056`

Authority for this phase's implementation decisions: the governing "Bytefray v4 RC Path —
Phase 3" task itself, plus [docs/research/v4/V4_RC1_PHASE1_EVALUATION_METHODOLOGY.md](V4_RC1_PHASE1_EVALUATION_METHODOLOGY.md),
[docs/research/v4/V4_RC1_PHASE2_STABLE_CONTRACT_PROMOTION.md](V4_RC1_PHASE2_STABLE_CONTRACT_PROMOTION.md),
and [docs/research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md](V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md),
all treated as ratified and frozen. Nothing found in this phase contradicts any of the three.

This is an **adversarial product-coherence audit**, not a feature-development, gameplay-research,
or compatibility-architecture phase. Its question is whether every real Bytefray product surface
tells the same, correct story about stable Bytefray 4 — not whether the underlying engine
contracts are correct (Phases 1/2 already proved that).

---

## A. Executive decision

| Gate | Result |
|---|---|
| Stable v4 defaults coherent across product? | **PASS** |
| Known evaluation-summary defect fixed? | **PASS** |
| Designer current/historical presentation coherent? | **PASS** |
| CLI current/historical behavior coherent? | **PASS** |
| Replay/trace handling safe? | **PASS** |
| Perspective knowledge boundary intact? | **PASS** |
| Evaluation/history/comparison coherent? | **PASS** |
| Historical Rulesets preserved? | **PASS** |
| Current docs match actual product? | **PASS** (after fixes; see §J) |
| Ready for Phase 4 RC artifact qualification? | **YES** |

```text
PHASE 3 QUALIFIED — READY FOR RC PATH PHASE 4
```

---

## B. Starting state

```text
git status --short          (empty)
git branch --show-current   v4-rc1-development
git rev-parse HEAD           b2000c4d84ae4452c83b59fb5bb5549f55374a8d
git rev-parse origin/main    010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99
git rev-parse v4.0.0-alpha4  07a1bae30706c0110d16f5a879c24601bf66acb5
```

Matched the governing task's stated baseline exactly (`b2000c4d` is Phase 2's reported final
SHA). No unexpected repository state was found; no unrelated work was discarded.

---

## C. Known-defect reproduction and fix

Reproduced fresh, as instructed, before any other Phase 3 work:

```text
$ bytefray agents evaluate v4_claimer --opponents v4_scout --ruleset bytefray-rules-4 --seeds 1 --ticks 20
...
Entrant orientation: both
Arena alignment: fixed -- translation robustness not evaluated
...
```

against a persisted `evaluation.json` correctly recording
`"arena_alignment_mode": "ruleset_v4_seeded_placements"`, `"schema_version": 7`. Root cause
(confirmed by reading, not guessed): three call sites in `agent_evaluation.py` —
`_print_matrix` (and its `--dry-run --json` counterpart, `_matrix_to_json`) and `_print_result`
— called `resolved_arena_alignment_mode(request.is_v2_methodology, request.group)`, omitting the
function's existing third parameter, `is_v4_methodology` (default `False`), unlike the real
matrix-building call site in `EvaluationService.run()`, which already passed all three arguments
correctly. Only the rendered text disagreed with the artifact; the artifact itself was never
wrong.

**Fix** (commit `30f4218`): all three call sites now pass the request's own already-existing
`is_v4_methodology` property, mirroring the one call site that was already correct. Verified with
real, non-`--quiet` runs against both `bytefray-rules-4` and `bytefray-rules-4-alpha2`:

```text
Arena alignment: ruleset_v4_seeded_placements -- translation robustness not evaluated
```

and confirmed unaffected for historical Rulesets: `bytefray-rules-1` still reports its own
`"fixed"` label; `bytefray-rules-2` still reports its own, distinct
`"ruleset_v2_standard_placements"` label (v2.0.0-beta2 Phase 1's own methodology, never `"fixed"`
even before this bug existed).

**Regression coverage** (same commit): three new tests in `test_agent_evaluation_v4.py`, all
exercising the real CLI entry point (`evaluate_main`) against a real, non-`--quiet` run —
capturing actual console output via `capsys` and cross-checking it against the persisted artifact
— never only a unit test of `resolved_arena_alignment_mode` itself:

- `test_rendered_summary_reports_v4_seeded_placements_for_stable_v4`
- `test_rendered_summary_reports_v4_seeded_placements_for_alpha2`
- `test_rendered_summary_for_historical_v1_and_v2_is_unaffected`

---

## D. First-user workflow audit

A literal GUI session could not be driven in this environment, so the Simple→Designer portion of
the workflow was exercised at the same service-layer seams the Qt widgets themselves call
(`app.services.ruleset_options`, `app.services.designer_workflows`) — the same boundary the
existing Designer GUI test suite already drives — plus real CLI execution for every step that has
one. Every step below is real, executed evidence, not inspection alone:

| Step | How exercised | Result |
|---|---|---|
| Inspect available agents / Ruleset preference | `best_designer_ruleset_for_agents` against real API v1/v2/VM metadata, all four option tuples | Correct: API v2 → `bytefray-rules-4` in Simple/Advanced/Evaluation; API v1 → `bytefray-rules-2`; VM → `None` in Simple (not offered), `bytefray-rules-1` in Advanced |
| Validate / Test | `bytefray agents test`, omitted and explicit `--ruleset` | Correct resolution and preservation (§F) |
| Run Simple match | `bytefray run`, omitted `--ruleset`, API v2 roster | Resolved to `bytefray-rules-4`, recorded correctly in `result.json`/replay header |
| Open Replay | `spectator_derivation.analyze_pair` against the real produced replay+trace pair | Succeeded, correct `ruleset_id` |
| Perspective Cam / Director / Fight Night | `PerspectiveManager` against the real pair; existing 35-test spectator/perspective/director/fight-night suite | All pass; no leakage found (§G) |
| Evaluate | `bytefray agents evaluate`, omitted `--ruleset`, API v2 roster | Resolved to `bytefray-rules-4`, schema 7, correct console summary (§C) |
| Evaluation History | `bytefray agents evaluations show` against the real produced artifact | Correct |
| Compare | Existing comparison test suite (unchanged, all passing) | Coherent |
| Replay an evaluation cell | Cell's own recorded replay path opened via the same `analyze_pair` seam | Succeeded |

**No step required knowing that "API v2 means Ruleset v4"** — every surface either resolves it
automatically (CLI, Designer preference order) or names it explicitly in its own output (`bytefray
run`'s `Winner: ...; ruleset: bytefray-rules-4` line, the evaluation console summary, the Designer
option labels). No confusing or contradictory behavior was found in this pass beyond the defects
listed in §K, all of which were documentation/comment staleness, not behavior.

---

## E. Designer audit

Audited via direct execution against `app.services.ruleset_options`'s real option tables and
resolution functions (§D), plus reading `app/services/designer_workflows.py` and
`app/widgets/agent_combo.py` in full.

- **Simple**: `SIMPLE_RULESET_OPTIONS = (bytefray-rules-2, bytefray-rules-4)` — current gameplay
  only, exactly as the governing task expects. A VM/blob selection correctly yields no compatible
  option (`best_designer_ruleset_for_agents` returns `None`) rather than silently falling back to
  a Ruleset that would reject the match. Duplicate display names, starter-ID-vs-display-name, and
  post-refresh/post-API-switch defaults are all governed by the same
  `agent_row_supported_by_ruleset`/`best_designer_ruleset_for_agents` seam `NativeMatchService`
  itself enforces — there is no second, Designer-only compatibility decision to drift from it.
- **Advanced**: `DESIGNER_RULESET_OPTIONS` offers all five identities in product-preference
  order (`rules-2`, `rules-4`, `rules-4-alpha2`, `rules-4-alpha1`, `rules-1`); stable v4 is
  preferred first for an API v2 selection, both alphas remain one explicit choice away, and their
  Designer labels (`"Historical"`) never present them as equally current (§J.1's compatibility
  matrix; `docs/COMPATIBILITY.md`'s own "Ruleset v4 alpha1" section already documents this
  labeling policy, confirmed unchanged by reading `ruleset_options.py` directly).
- **Development**: uses the same `DESIGNER_RULESET_OPTIONS` full catalog; a newly created API v2
  agent naturally resolves to stable v4 through the identical preference order, confirmed live.
- **Evaluation**: `EVALUATION_RULESET_OPTIONS` mirrors Advanced's order; confirmed live that an
  API v2 roster's evaluation runs schema 7 under `bytefray-rules-4` by default and that explicit
  alpha1/alpha2 selection keeps their own distinct, correct methodologies (§H).

No Designer-specific defect found.

---

## F. CLI audit

Every Ruleset-aware entry point (`run`, `agents test`, `agents evaluate`, `tournament`) was
exercised live, not only read:

| Case | `run` | `agents test` | `agents evaluate` | `tournament` |
|---|---|---|---|---|
| Omitted + API v1 roster | `bytefray-rules-2` | `bytefray-rules-2` | `bytefray-rules-2` | (not separately re-tested; same `OMITTED_RULESET_CANDIDATES` seam) |
| Omitted + API v2 roster | `bytefray-rules-4` | `bytefray-rules-4` | `bytefray-rules-4` | `bytefray-rules-4` |
| Explicit alpha1 | preserved | preserved | preserved (own methodology) | n/a |
| Explicit alpha2 | n/a (covered by Phase 2's equivalence corpus) | n/a | preserved (own methodology) | preserved, recorded correctly |
| Explicit stable v4 | used | used | used | used |
| API v1 + `bytefray-rules-4` | **rejected before execution**, clear message naming entrant/kind/API version | — | — | — |
| API v2 + `bytefray-rules-2` | **rejected before execution**, same clear message shape | — | — | — |
| `--arena-size` disagreeing with the v4 methodology's pinned 512 | — | — | **rejected before execution**, names the pin and the fix | — |

Sample real rejection text (`bytefray run`, API v1 roster against explicit `bytefray-rules-4`):

```text
ERROR: Ruleset 'bytefray-rules-4' does not support entrant metadata: A (python, Agent API 1), B (python, Agent API 1).
```

No silent upgrade, downgrade, or fallback was observed in any case. `--ruleset` help text across
all four commands lists all five identities in the same order and correctly describes automatic
resolution to the stable identity (already updated in Phase 2; reconfirmed unchanged and accurate
here). VM/blob rejection under `bytefray-rules-4` was not re-driven through the CLI directly in
this phase (a CLI-level blob invocation requires a binary fixture this audit did not need to
construct); it was instead reconfirmed through the existing, already-passing
`test_ruleset_agent_compatibility.py` suite, which proves the identical rejection at the real
`NativeMatchService.run()` boundary the CLI itself calls.

---

## G. Replay/spectator audit

This turned out to be the strongest area of the product: `battle_engine.spectator_derivation
.verify_pair` already implements a cryptographic (SHA-256) binding between a canonical replay and
its trace, established before this RC path began (the "record spectator traces for v4 matches"
work). Every scenario the governing task named was reproduced live against real match output, not
merely inferred from reading the code:

| Scenario | Real test performed | Result |
|---|---|---|
| Correct replay + correct trace | `analyze_pair` on a genuine paired run | Succeeds; correct `ruleset_id` |
| No trace supplied | `PerspectiveManager(replay, None)` | `available=False`, `"no trace supplied"`, falls back to Broadcast |
| Trace from a different match | `analyze_pair(replay_A, trace_B)` | `PairBindingError`: reports both SHA-256 digests, names the mismatch |
| Truncated trace | First 100 bytes of a real trace | `PairBindingError`: `"unusable API-v2 trace ... invalid JSON"` |
| Corrupt trace (garbage appended) | Real trace + trailing garbage bytes | `PairBindingError`: `"unusable API-v2 trace ... invalid JSON"` |
| Stale sibling `trace.jsonl` | Same mechanism as "different match" (content-hash bound, not path-bound) | Rejected |
| Historical schema-3 replay + a v4 trace | Real `bytefray-rules-1` replay + a real v4 trace | `PairBindingError`: binding-hash mismatch (schema-3 replay hashes differently) |
| Stable-v4 replay identity | `analyze_pair` on a real `bytefray-rules-4` pair | Correctly reports `ruleset_id: bytefray-rules-4` |
| `PerspectiveManager`-level mismatch (not just the derivation layer) | Real mismatched replay/trace pair | `available=False`, honest status message, `mode` stays `broadcast` — never crashes, never fabricates data |

No scenario produced believable false Perspective data, a crash, or a silent fallback that hid
the mismatch. **No fix was needed here** — existing dedicated test coverage
(`test_verify_pair_rejects_a_trace_bound_to_a_different_match`,
`test_verify_pair_rejects_a_trace_with_no_binding_record`,
`test_verify_pair_distinguishes_a_malformed_trace_from_a_mismatch`,
`test_cli_rejects_a_mismatched_pair_and_accepts_a_matching_one`, plus the full spectator/
perspective/director/fight-night suite, 35 tests) was reconfirmed green and matches the live
reproductions above exactly.

### G.1 Perspective knowledge-boundary audit

Focused re-verification of Alpha3's own knowledge-boundary implementation, per the governing
task's explicit request. Existing dedicated coverage already targets every leakage vector named:
`test_negative_target_entrant_id_leakage_prohibited`, `test_read_owner_never_becomes_contact
_identity` (process-ID/role leakage), `test_three_entrant_colocation_remains_one_anonymous
_contact`/`test_four_entrant_projection_preserves_multiple_contacts_without_attribution`
(synthetic continuity between anonymous contacts), `test_elimination_and_result_remain_outside
_continuing_entrant_perspective` (hidden lifecycle/result knowledge),
`test_stale_contact_transition_and_age`/`test_end_of_tick_replay_geometry_does_not_override_last
_observation` (stale contacts never silently "corrected" with omniscient knowledge), and the
capture-attribution suite (`test_live_perspective_suppresses_an_opponent_vs_opponent_capture`,
etc., for killer attribution the entrant could not know). All 35 tests across
`test_v4_spectator_perspective.py`, `test_v4_spectator_derivation.py`,
`test_v4_spectator_director.py`, `client/tests/test_perspective.py`,
`client/tests/test_perspective_card_knowledge.py`, `client/tests/test_director.py`, and
`client/tests/test_fight_night.py` pass. No new leakage vector was found; no fix was needed; no
new Perspective feature was added.

---

## H. Evaluation audit

Walked live, via the real CLI, not the library API alone:

- **Identity/schema**: a real stable-v4 evaluation persists `rules_compatibility_id:
  "bytefray-rules-4"`, `schema_version: 7`, `identity_version: 7`,
  `arena_alignment_mode: "ruleset_v4_seeded_placements"` — all confirmed by reading back the
  written `evaluation.json`, not merely asserted.
- **Arena/samples/orientation/schedule**: `--dry-run --json` against one opponent reports
  `matrix_size: 16` (8 seeds × 2 orientations); the pinned-512 guard rejects a disagreeing
  `--arena-size` before any match executes (§F).
- **Lifecycle state / console summary**: both now agree (§C's fix) — a completed all-success run
  reports `lifecycle_state: "finished"`; a run with a genuine `ruleset_agent_unsupported` failure
  reports `"finished_with_failures"`, `complete: false`, and an honest `"failed cells:"` console
  section naming the exact incompatibility per cell.
- **History / comparison / deep verify**: `bytefray agents evaluations show` against a real
  produced artifact reads back correctly; the existing comparison suite (unchanged) still passes,
  and its `_condition_key` (already including `arena_alignment_id`/`rules_id`/`placement.value`)
  continues to keep every methodology non-comparable with every other one — a stable-v4 cell can
  never silently align with a v2 or alpha-methodology cell.
- **Constructed mismatches**: a genuine failed-cell evaluation (real API v1 opponent under stable
  v4) was produced live and correctly reported `finished_with_failures`/`complete: false` with
  per-cell `ruleset_agent_unsupported` disclosure, in both the console summary and the persisted
  artifact — the exact case F.6 exists to prevent recurring, reconfirmed still prevented.

No `comparison.py` change was made; none was needed.

### H.1 Evaluation resume audit

- A no-op resume (identical request re-run against the same completed output directory) produces
  a byte-identical `finished_at` timestamp and byte-identical placement geometry for every cell —
  proof no cell was silently re-executed.
- A genuine failed-cell evaluation, resumed without `--retry-failed`, keeps its failed cells
  failed and its `lifecycle_state`/`complete` truthful, rather than reprocessing or "healing" them
  merely because the checkpoint was re-written.
- Arena 512 and seed-derived placement geometry were confirmed to reproduce identically across
  the initial run and the resume in every case above.

No resume defect was found.

---

## I. Historical compatibility audit

One representative match executed live under each of the five registered identities, arena 512
where applicable, seed 5, 10 ticks, output artifacts read back directly:

| Ruleset | Recorded `ruleset_id` | Recorded replay `schema_version` |
|---|---|---|
| `bytefray-rules-1` | `bytefray-rules-1` | 3 |
| `bytefray-rules-2` | `bytefray-rules-2` | 3 |
| `bytefray-rules-4-alpha1` | `bytefray-rules-4-alpha1` | 4 |
| `bytefray-rules-4-alpha2` | `bytefray-rules-4-alpha2` | 4 |
| `bytefray-rules-4` | `bytefray-rules-4` | 4 |

All five values are distinct, correct, and self-consistent between the replay header and
`result.json`. No alias, no cross-identity contamination, no silent migration. Combined with
Phase 2's own `test_v4_historical_immutability.py` (pinned canonical `match_id`/`result_id`
values for alpha1/alpha2, reconfirmed unchanged by this phase's full-suite run) and this phase's
own tournament-level check (`bytefray-rules-4-alpha2` explicit tournament match, correctly
recorded), historical reproducibility across all three v4 identities plus v1/v2 is proven, not
merely declared. No historical golden value was re-blessed; none needed to be.

---

## J. Documentation and code consistency sweep

`git grep` for `bytefray-rules-4-alpha1`/`bytefray-rules-4-alpha2` across `engine/`, `client/`,
`app/`, `agents/` (excluding `docs/research/**`/`docs/archive/**`) returned every hit in the
repository; each was individually read and classified:

| Disposition | Count (approx.) | Examples |
|---|---|---|
| Historical support — retain | most hits | `rules.py`/`ruleset_policy.py` identity definitions and rationale comments, `placement.py`'s fixed domain-separation-string docstrings, test fixtures exercising specific alpha behavior |
| Illustrative example — retain | a few | `cli.py`/`agent_combo.py` comments using alpha1 as one example of "Python-only, told apart by API version" — still literally true regardless of which identity is current, not a default-behavior claim |
| **Current-default bug — fix** | 3 | `agent_evaluation.py`'s F.6 comment, `ruleset_policy.py`'s docstring, `agent_test.py`'s comment — all described the pre-Phase-2 default (§K) |
| **Stale user-facing presentation — fix** | 2 | `AGENTS.md` (this repo's own authoritative agent guidance), `agents/viper/agent.py`'s docstring (§K) |

No hit was mechanically replaced — each was read in context and judged individually, exactly per
the governing task's own instruction not to destroy historical compatibility by blind substitution.

### J.1 Current-documentation review

`README.md`, `docs/COMPATIBILITY.md`, `docs/AGENT_API_V2.md`, `docs/AGENT_AUTHORING.md`,
`docs/REPLAY_SCHEMA.md`, `docs/RULES_V4.md` — all already correctly describe stable v4 as current
(Phase 2's own documentation pass); reconfirmed by direct reading, no further edit needed.
`CHANGELOG.md` and `docs/ROADMAP.md` entries referencing alpha1/alpha2 are dated, historical
release narrative (each under its own `**Published <date>**`/version heading) — correctly left
unedited, per the governing task's own instruction to distinguish historically-accurate old
statement from currently-stale documentation. `docs/MANUAL_SMOKE_TESTS.md` contains no
Ruleset-identity-specific content requiring an update (it covers UI/packaging mechanics, not
gameplay semantics). `INSTALL.md`'s literal `...alpha1...` example filenames are a pre-existing,
explicitly self-disclosing pattern (the surrounding sentence already tells the reader "see
README.md for the current release; the exact filenames below track that latest tag as later
versions ship") — unrelated to the v4 Ruleset/API promotion this audit covers, and correctly left
to whatever installer-documentation pass eventually retargets it. `docs/FUTURE_PLANS.md`'s only
hit is an unrelated hypothetical `bytefray-rules-3-alpha1`.

### J.2 Compatibility matrix (current state, for reference)

| Ruleset ID | Agent API | Runtime | Replay schema | Product status |
|---|---|---|---|---|
| `bytefray-rules-1` | v1 | Python and VM/blob | 3 | Stable |
| `bytefray-rules-2` | v1 | Python only | 3 | Stable, current for API v1 |
| `bytefray-rules-4-alpha1` | v2 | Python only | 4 | Historical, frozen |
| `bytefray-rules-4-alpha2` | v2 | Python only | 4 | Historical, frozen |
| `bytefray-rules-4` | v2 | Python only | 4 | Stable, current for API v2 |

Unchanged from Phase 2's own matrix — this phase found no compatibility-axis defect, only
presentation/comment staleness.

---

## K. Defects found

### K.1 Known evaluation-summary defect (fixed)

```text
severity/class:   Phase 3 correctness fix
root cause:       resolved_arena_alignment_mode's third parameter (is_v4_methodology) omitted
                   at three call sites in agent_evaluation.py (_print_matrix, _matrix_to_json,
                   _print_result)
fix:              pass request.is_v4_methodology at all three sites, mirroring the one
                   already-correct call site in EvaluationService.run()
regression test:  test_rendered_summary_reports_v4_seeded_placements_for_stable_v4,
                   test_rendered_summary_reports_v4_seeded_placements_for_alpha2,
                   test_rendered_summary_for_historical_v1_and_v2_is_unaffected
outcome:          fixed
```

### K.2 Stale "resolves to alpha2/alpha1" internal comments (fixed)

```text
severity/class:   Phase 3 correctness fix (documentation/comment only, no behavior)
root cause:       three comments/docstrings written before Phase 2's promotion still described
                   the pre-Phase-2 default-resolution target (alpha2 or alpha1)
fix:              engine/src/battle_engine/agent_evaluation.py:5217-5225 (F.6 comment),
                   engine/src/battle_engine/ruleset_policy.py's
                   resolve_omitted_ruleset_for_agents docstring, engine/src/battle_engine/
                   agent_test.py's default-Ruleset comment above _resolve_agent_metadata --
                   all corrected to name the current bytefray-rules-4 default while preserving
                   the historical narrative
regression test:  none added -- no behavior changed; the actual resolution logic
                   (resolve_omitted_ruleset_for_agents / OMITTED_RULESET_CANDIDATES) was already
                   correct and already covered by Phase 2's own tests
outcome:          fixed
```

### K.3 AGENTS.md's stale default-resolution claim (fixed)

```text
severity/class:   Phase 3 correctness fix (this repository's own authoritative agent guidance)
root cause:       AGENTS.md's "Two v4 Rulesets now exist" bullet still stated that alpha2 is
                   what an omitted --ruleset resolves to for an Agent API v2 roster -- a claim
                   any future coding-agent session reading this file would reasonably, and
                   now incorrectly, rely on
fix:              updated to name bytefray-rules-4 as the current default, describe it as a
                   third, non-aliased identity, and link docs/RULES_V4.md
regression test:  n/a (documentation)
outcome:          fixed
```

### K.4 viper's docstring misstated its own default-Ruleset behavior (fixed)

```text
severity/class:   Phase 3 correctness fix (starter-agent documentation)
root cause:       agents/viper/agent.py's module docstring claimed an omitted --ruleset for
                   its own all-Agent-API-v2 test command resolves to bytefray-rules-2 (the
                   pre-metadata-aware, kind-only resolution behavior the RC1 default-Ruleset
                   defect fix already replaced) -- and did not explain that --ruleset is
                   explicit there only to reach alpha1 specifically, not out of necessity
fix:              corrected to state the real current default (bytefray-rules-4) and note that
                   viper's own target-acquisition logic makes no placement assumption, so it
                   would function unchanged under stable v4/alpha2 -- the alpha1 selection is a
                   documented historical showcase choice, not a functional requirement
regression test:  n/a (documentation)
outcome:          fixed
```

### K.5 hydra/Nemesis catalog descriptions did not disclose their placement-fallback assumption (fixed)

```text
severity/class:   Post-4.0-adjacent, but a narrow enough disclosure fix to make now
root cause:       hydra and Nemesis (both API v2, both offered under stable v4/alpha2 by the
                   metadata-driven compatibility predicate) use a hardcoded
                   own_core_base + arena_size // 2 opposite-core fallback tuned for alpha1's
                   fixed evenly-spaced placement -- already disclosed in general terms by
                   docs/COMPATIBILITY.md's alpha2 boundary section, but not in the catalog
                   description a Designer/CLI user actually sees
fix:              added one sentence to each manifest's description pointing to
                   hydra_alpha2/nemesis_alpha2 as the seeded-placement-compatible derivative;
                   no behavior change to either agent
regression test:  n/a (description text only)
outcome:          fixed
```

No RC blocker was found. No defect required touching gameplay semantics, Agent API v2, replay
schema 4, or the evaluation methodology.

---

## L. Qualification

All commands run on Windows 11 Pro 10.0.26120, Python 3.13.14, `.venv/` at the repository root,
against the final commit `7c9780c`.

### L.1 Qualification integrity protocol

```text
HEAD before:  7c9780c5f2c01d43040e160b8b7a94dbd65b2056
HEAD after:   7c9780c5f2c01d43040e160b8b7a94dbd65b2056   (unchanged)
git status:   clean, both times
SHA-256 digests of the 8 phase-modified files: identical, all 8, before and after the full
  suite/GUI suite/static-check run below
```

### L.2 Static checks

| Check | Command | Result |
|---|---|---|
| Ruff | `ruff check .` | **All checks passed** |
| Engine mypy | `mypy engine/src/battle_engine` | **Success, 101 source files** |
| Client mypy | `mypy client/src/battle_client` | **Success, 15 source files** |
| Whitespace | `git diff --check` | clean |

### L.3 Full repository suite

```text
pytest --junitxml=...
```

**2936 collected, 0 errors, 0 failures, 14 skipped**, in 312.4s.

Reconciles exactly against Phase 2's own final count (2933) plus this phase's 3 new regression
tests (§C): +3.

One transient failure occurred on the first full-suite attempt
(`test_resume_after_coordinator_interruption_matches_uninterrupted_reference`, a Windows
`os.replace` `PermissionError` under temp-directory file-lock contention) and passed cleanly on
immediate isolated re-run and on the full clean re-run recorded above — the same documented,
pre-existing transient-flake pattern already recorded in Phase 1's own qualification report
(§H.4), not a Phase 3 regression.

### L.4 Designer GUI suite

```text
pytest -m gui --junitxml=...
```

**2 collected, 0 errors, 0 failures, 0 skipped**, in 7.0s. Unchanged from Phase 2.

### L.5 Not performed, and not claimed

No Linux qualification was performed. No packaged/installer qualification was performed or is
claimed — both remain Phase 4 work.

---

## M. Manual/source smoke tests actually performed

All of the following were executed as real, live commands against real bundled starter agents in
this session — not claimed from reading code alone. None constitutes packaged-build
qualification (Phase 4's scope).

| Smoke test | Performed |
|---|---|
| CLI stable-v4 match, API-v2 entrants, omitted Ruleset | Yes — `bytefray run`, resolved `bytefray-rules-4`, recorded correctly |
| CLI stable-v4 match, then Open Replay (`analyze_pair`) | Yes |
| Perspective / Director / Fight Night suites | Yes — full existing suite (35 tests) re-run and passing; `PerspectiveManager` live-tested against real matched, mismatched, and missing-trace pairs |
| Stable-v4 evaluation, API-v2 roster, omitted Ruleset | Yes — schema 7, `ruleset_v4_seeded_placements`, correct console summary |
| Evaluation resume (no-op and genuine-failed-cell cases) | Yes |
| Evaluation history (`agents evaluations show`) | Yes |
| Historical Alpha1 match, explicit identity | Yes |
| Historical Alpha2 match, explicit identity (direct match and tournament) | Yes |
| API-v1 Ruleset-v2 match, omitted Ruleset | Yes |
| Invalid API/Ruleset combination rejection (both directions) | Yes |
| Evaluation `--arena-size` guard rejection | Yes |
| Tournament resume | Yes |

No packaged-build (installer/portable ZIP/wheel) smoke test was performed or is claimed.

---

## N. Phase 4 requirements

Belongs to actual RC artifact qualification, not further source changes:

- Version bump to `v4.0.0-rc1` (deliberately not done in this phase).
- Windows installer build and qualification.
- Portable ZIP qualification.
- Wheel/sdist build and qualification.
- Installer lifecycle (install/upgrade/uninstall) verification.
- Real Linux GUI qualification (this phase's Linux-related work was limited to reading
  `docs/LINUX_INSTALL.md`; no Linux execution was performed).
- Cross-platform (Linux) reproduction of Phase 2's placement/identity/equivalence evidence,
  carried forward unresolved from Phase 2's own §L.1.
- Checksums for release artifacts.
- The actual tag/release/publish decision for `v4.0.0-rc1`.

---

## O. Deferred post-4.0 items

Recorded for future consideration; **not** Phase 4 blockers:

- A `docs/ROADMAP.md` entry for the RC path itself (Phase 1/2/3) — the path is already
  thoroughly documented by its own three phase reports; ROADMAP.md's own per-release-date
  narrative convention is best extended when the RC actually ships, alongside whatever else
  Phase 4 adds, rather than churned mid-path.
- Broader starter-catalog disclosure/curation (beyond the narrow hydra/Nemesis description fix in
  §K.5) — the repository-root `agents/` directory also contains several agents that read as
  ad hoc development/test fixtures (`tester`, `tester2`, `rc_ubuntu_gui_agent`,
  `rc_ubuntu_smoke_*`) unrelated to the v4 promotion; out of this phase's scope
  ("not to rewrite the starter roster in Phase 3") and not a coherence defect.
- `INSTALL.md`'s hardcoded example release filenames (currently `...alpha1...`, self-disclosed as
  tracking whatever the actual latest tag is) — a natural candidate for Phase 4's own installer
  documentation pass, not a Phase 3 finding.

---

## P. Final decision

```text
PHASE 3 QUALIFIED — READY FOR RC PATH PHASE 4
```
