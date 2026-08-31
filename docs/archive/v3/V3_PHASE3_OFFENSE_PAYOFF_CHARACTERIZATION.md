# Bytefray v3 Phase 3 — Offense Payoff Characterization

Branch: `v3-research-phase3`, cut from `v3-research-phase2` at `753a602`
immediately after the Phase 2 report. Status: research complete, not
merged, not tagged, not published.

Phase 3 tests a **payoff hypothesis**, not a new gameplay mechanic: is
Ruleset v2's residual single-axis ecology caused primarily by decisive
offense being underpaid relative to its cost, rather than by the
vulnerable-core mechanic itself? It varies exactly one existing
`Config`-level scoring weight (`Weights.kill`) and measures the result. No
Ruleset, Agent API, schema, or gameplay-mechanic change was made or is
proposed by this phase.

---

## 1. Initial state

Verified before any change:

| ref | value |
|---|---|
| starting branch | `v3-research-phase2` |
| HEAD | `753a6026b43df5db93d67c849878d2f03602d693` |
| `v3-research-phase0` | `51a39e86e720f2806981bcd35fda4e4ba6234c00` — unchanged |
| `v3-research-phase1` | `0f074252dda9fe01a170246ca54a6a652f874fe9` — unchanged |
| `v3-research-phase2` | `753a6026b43df5db93d67c849878d2f03602d693` — unchanged |
| `main` | `1093393b401aabda243ed89b7c44fa91938477b5` |
| `origin/main` | `1093393` — identical, no unpushed divergence |
| `v2.0.0` tag | annotated `5c525ce`, targets `965d2f6`; `965d2f6` confirmed an ancestor of `main` |
| working tree | clean |
| frozen Phase-0 `v2-baseline` benchmark population | **9/9** members verify against their pinned `agent_revision_id` |
| Phase 1 committed default-condition corpus | present under `runs/research_v3_phase1/main/results/a4096_b8` (11 group rosters × 54 cells, 3 pairwise controls × 18 cells) |
| Phase 2 experimental branch/artifacts | untouched |

Work proceeded on a new branch `v3-research-phase3` cut from `753a602`.
Nothing was merged or tagged.

---

## 2. Research question

> Is Ruleset v2's residual single-axis ecology caused primarily by the
> payoff for decisive offense — a private, throughput-priced cost whose
> principal benefit is shared among all surviving entrants — rather than by
> the vulnerable-core mechanic itself? Specifically: does a principled
> increase in the existing kill-score weight make deliberate offense
> simultaneously viable with expansion and defense in multi-agent play,
> without making offense universal and without altering the underlying
> gameplay mechanism?

This is a causal characterization experiment, not a tuning exercise. A null
result is valid.

---

## 3. Why the core hypothesis was deprioritized

Two independent phases converged on the fixed-size core, not entrant
omnipresence, as the more evidenced explanation for the residual ecology:

* Phase 1 §9.1 found that along constant-density diagonals, absolute action
  budget (not spatial density) governs how affordable a `core_tracker`
  investigation is, because `CORE_SIZE = 8` is a fixed Ruleset constant
  while arena size scales — "the one genuine *scale* effect in the grid".
* Phase 2 independently implicated the same constant from the opposite
  direction: under bounded locality, a fixed-size 8-cell core is captured
  *incidentally* by any contiguous sweep that passes over it, which is what
  made blind expansion become the dominant core-capture mechanism and
  caused Phase 2's `LOCALITY NOT VALIDATED` verdict.

The independent pre-Phase-3 review accepted that the core-model hypothesis
is real but found it **mostly dormant at the shipped Ruleset-v2 default**:
in Phase 1's own default-condition corpus, search agents already cause
90.2% of captures and expansion causes 7.9% (§16 below reproduces and
verifies this from committed replay-level attribution). The review's more
load-bearing finding was that deliberate offense already works
mechanically — `core_tracker` converts captures well in the relevant
pairwise controls — but is poorly rewarded once a third entrant is present
to inherit the benefit. Phase 3 tests that narrower, more load-bearing
claim before revisiting core geometry.

---

## 4. Scoring architecture reality check (Phase 3A)

Verified directly against source, not assumed:

1. **`Weights` is a per-match `Config` field.**
   `engine/src/battle_engine/config.py`:
   ```python
   @dataclass
   class Weights:
       alive: float = 1.0
       kill: float = 5.0
       territory: float = 1.0
       territory_bucket: int = 64

   @dataclass
   class Config:
       ...
       weights: Weights = field(default_factory=Weights)
   ```
2. **Weight semantics are Ruleset-defined; values are Config-level.**
   `docs/RULES.md`'s "Scoring" section documents the same three terms and
   defaults as part of Ruleset v1 (unchanged by v2 per `docs/RULES_V2.md`),
   while `docs/COMPATIBILITY.md`'s compatibility table lists "Default
   territory weight" as requiring no Ruleset/API/schema bump — the
   identical policy this phase relies on for `kill`.
3. **Weights are already persisted in the reproducibility surfaces.**
   `match_service._reproducibility` already builds
   `"weights": asdict(request.config.weights)`, and
   `docs/RESULT_SCHEMA.md`'s identity recipe already lists `"weights"`
   inside `canonical_match_id`'s hashed `reproducibility` block, alongside
   `seed`/`arena_size`/`tick_limit`/`action_budget`/`win_mode`.
4. **Weights are already hashed into canonical match identity.** Direct
   consequence of (3): `canonical_match_id`'s payload includes
   `reproducibility["weights"]`, so a different `weights.kill` was already
   guaranteed to change `match_id`/`result_id`/`replay_id` before this
   phase touched anything.
5. **Weights are already represented in evaluation effective conditions.**
   `agent_evaluation.EffectiveConditions` already declares a
   `weights: dict[str, float | int]` field, and pre-Phase-3
   `effective_conditions_for` already computed
   `weights=asdict(defaults.weights)` — hardcoded to `Config()`'s default,
   never parameterized. This is exactly the gap `arena_size`/
   `instr_per_tick` had before Phase 0's plumbing (`docs/
   V3_PHASE0_RESEARCH_BASELINE.md` §4), reproduced here for `weights.kill`.
6. **Evaluation did not expose arbitrary weight values through the request
   path.** Confirmed: no `--kill-weight`-shaped CLI flag,
   `EvaluationRequest` field, or `agent_test`/`agent_evaluation` parameter
   existed before this phase.
7. **No Agent API field exposes scoring weights to agents.**
   `docs/AGENT_API_V1.md`'s `Observation`/`MatchContext` field lists
   (`tick`, `agent_id`, `pc`, `register_a`, `register_p`, `zero_flag`,
   `last_read`, `alive`; `agent_id`, `seed`, `arena_size`, `tick_limit`,
   `action_budget`, `rng`) contain no scoring field. Verified by reading
   both dataclasses directly.
8. **No current agent changes behavior based on scoring weight.** All nine
   frozen `v2-baseline` agents were already read during Phase 0/1; none
   references `weights`/score in its own source (confirmed again here by
   grep across the frozen population).
9. **Score weights do not affect gameplay before final resolution.**
   `scoring.ScoringPolicy.score_alive`/`score_territory`/`score_kill` only
   ever *write into* a `score: ScoreMap` dict; nothing in
   `python_runtime.py`'s `apply_action`/`validate_action`/capture-detection/
   scheduler code ever *reads* `weights` or `score`. `score_kill` is called
   exactly once per capture, from a call site already fixed by capture
   attribution logic that does not depend on weight values. This was
   verified by direct code reading and then proven empirically (§6).

All nine assumptions in the governing task held exactly as stated; no
difference from expectation needed to be documented.

---

## 5. Weight-plumbing implementation (Phase 3B)

The implementation mirrors Phase 0's `arena_size`/`instr_per_tick` pattern
exactly, adding one parallel `kill_weight: float | None = None` at every
site that pattern already established:

```text
EvaluationRequest.kill_weight (None == shipped default, byte-identical to omission)
  -> .resolved_kill_weight
  -> EvaluationService.preflight / ._validate (rejects a negative weight)
  -> ._effective_conditions -> effective_conditions_for(..., kill_weight=...)
       -> EffectiveConditions.weights["kill"]  (already-existing field, now variable)
       -> _evaluation_id / effective_conditions_fingerprint (already hashed this key)
  -> serial execution / _run_pending_parallel -> _evaluation_dispatcher_loop
       -> EvaluationCellWorkerHandle.submit_cell (additive wire key, `.get(...)`-tolerant)
       -> EvaluationService._execute_cell /._execute_group_cell
  -> agent_test.test_agent / test_agents
       -> Config(weights=replace(Config().weights, kill=kill_weight))
  -> MatchRequest -> NativeMatchService.run
       -> canonical_match_id ("reproducibility": ... "weights": {...})
       -> result.json / replay.jsonl "reproducibility"/"config"
  -> resume: _expected_cell_match_id / _expected_group_cell_match_id
       (rebuild the identical non-default Config the original run used)
  -> CLI: --kill-weight (mirrors --arena-size/--instr-per-tick exactly)
  -> disclosure: agent_evaluation._print_experimental_conditions,
       evaluation_history.cli._print_experimental_conditions
```

**Files changed** (commit `e5f6dfc`):

| file | change |
|---|---|
| `engine/src/battle_engine/agent_evaluation.py` | `effective_conditions_for(kill_weight=...)`; `EvaluationRequest.kill_weight` + `resolved_kill_weight`; `_validate` non-negative check; `preflight`/`_effective_conditions`/`_evaluation_dispatcher_loop`/`_execute_cell`/`_execute_group_cell`/`_expected_cell_match_id`/`_expected_group_cell_match_id` threading; `--kill-weight` CLI flag; `_print_experimental_conditions` disclosure |
| `engine/src/battle_engine/agent_test.py` | `test_agent`/`_test_agent`, `test_agents`/`_test_agents` gain `kill_weight`; `Config(weights=...)` construction |
| `engine/src/battle_engine/evaluation_worker.py` | additive `kill_weight` wire key, `.get(...)`-tolerant on the worker side |
| `engine/src/battle_engine/evaluation_history/cli.py` | `kill weight: … (non-default)` disclosure in `show`, mirroring the arena/budget precedent |
| `engine/tests/test_v3_phase3_offense_payoff_evaluation.py` | **new** — 21 tests |

**Deliberately not touched:** no `EvaluationPreset` field (a reweighting
experiment has no business being a reusable product-facing preset shape,
the identical reasoning Phase 2 gave for keeping the locality Ruleset out
of presets); no new dataclass field on `EffectiveConditions` (the `weights`
field already existed); no Ruleset identity, Agent API version, or schema
version bump anywhere.

### Compatibility properties, proven not assumed

```text
effective_conditions_for(400, 1) == effective_conditions_for(400, 1, kill_weight=Config().weights.kill)   -> True
stable_id("evaluation-conditions", asdict(one)) == stable_id(..., asdict(other))                           -> True
preflight(...) omitted kill_weight  == preflight(..., kill_weight=Config().weights.kill)  (evaluation_id)  -> True
distinct kill weights {5, 400, 1600, 3200} -> 4 distinct evaluation_ids                                    -> True
explicit kill_weight reaches executed result.json's reproducibility.weights.kill (pairwise and group)      -> True
non-default kill-weight evaluation reproduces deterministically across two independent runs                -> True
non-default kill-weight evaluation resumes without resumed_result_mismatch                                 -> True
--workers 1 identical to --workers 3 at a non-default kill weight                                           -> True
`show`/live matrix print stay silent at the default weight, disclose a non-default one                      -> True
negative --kill-weight rejected; zero accepted (a meaningful boundary, unlike a negative weight)             -> True
```

---

## 6. Execution-invariance result (Phase 3C)

**Gameplay trajectory does not change with `w_kill`. Only final scoring and
winner resolution do.**

A dedicated tool, `tools/v3_phase3_execution_invariance.py`, re-executed a
curated, representative sample of 23 cells drawn from the committed Phase 1
default-condition corpus — one capture cell and one non-capture cell per
group roster where both exist (`claimer_coredefender_reactive` never
captures by construction; `hunter_coretracker_coreseeker` captures in
every sampled cell), plus all three pairwise controls — at all four
predeclared kill weights (5, 400, 1600, 3200), for identical agents, source
revisions, seed, arena, action budget, tick limit, entrant order, and
placements/layout.

Comparison excluded only fields that are *supposed* to differ: `score`
(the term under test), `weights`/`match_id`/`result_id`/`replay_id`
(deliberately identity-bearing per §4-§5), the replay's `sha256` (a digest
over bytes that legitimately differ because of the two items above), and
`winner`/`outcome` (explicitly downstream of score per the governing task).
Everything else — every tick's per-agent `pc`/`alive`/`cpu_used`/
`mem_writes`/`region`/`register_a`/`register_p`/`zero_flag`/`last_read`/
`termination_reason`, every memory diff's `address`/`length`/`owner`/
`values`, every engine event, tick count, and final per-entrant
`statistics` (`kills`, `deaths`, `territory_*`, `cpu_total`, `mem_writes`)
— was required to match exactly.

```text
cells tested: 23
trajectory-invariant cells: 23/23
cells whose score changed with kill weight: 10/23
cells whose winner changed with kill weight: 5/23 (all group capture cells; zero pairwise)
```

This matches the structural prediction from §4 item 9: `weights.kill` is
read exactly once, in `scoring.ScoringPolicy.score_kill`, which only
writes into a `score` dict that nothing else in the tick loop reads.
**No further per-weight re-execution was required for the broad corpus.**

---

## 7. Offline-rescoring validation (Phase 3D)

Because only `weights.kill` varies and Phase 6 proved gameplay invariant to
it, the exact rescored score is the closed form

```text
new_score = old_score + kills * (new_kill_weight - old_kill_weight)
```

using each entrant's already-exact, already-persisted `statistics.kills`.
The new winner is resolved by calling the real, unmodified
`battle_engine.results.resolve_winner` — the identical production
function, not a reimplementation — against the rescored score map and each
entrant's already-recorded `alive` state (which §6 proved invariant).

`tools/v3_phase3_rescore.py`'s `validate_against_real_executions` compares
this offline rescoring against the §6 sample's own real production
executions at every non-default weight:

```text
cells checked: 69   (23 cells x 3 non-default weights)
mismatches:     0
exact_agreement: true
```

Score map and winner agree exactly in all 69 cases, including all 5 cells
whose winner actually flips. **The full corpus was therefore built by exact
rescoring of the committed Phase 1 artifacts, validated against real
execution, rather than by 4x-6x re-execution.**

---

## 8. Predeclared kill-weight values (Phase 3E)

| Condition | `w_kill` | Purpose |
|---|---:|---|
| K0 | 5 | shipped control |
| K1 | 400 | ~¼ opportunity cost / expected dead-zone boundary |
| K2 | 1600 | ~1x opportunity cost / expected interior region |
| K3 | 3200 | ~2x opportunity cost / approaching saturation |

Not altered after seeing results. Two additional values were added under
the predeclared Phase 3L MODIFY-interpolation rule **after** K0-K3 were
scored and found not to jointly satisfy every GO gate at one weight (§13):
`M1 = 800`, `M2 = 1200`, both strictly inside the `(K1, K2)` bracket the
primary sweep identified as ambiguous. No value outside `[5, 3200]` was
ever added.

---

## 9. Corpus methodology (Phase 3F–3H)

**Environment**: `bytefray-rules-2`, `arena_size = 4096`, `instr_per_tick =
8`, `ticks = 400` — the shipped default, unchanged, matching Phase 0/1's
own standard placements/layouts.

**Population**: the frozen Phase-0 `v2-baseline` population, verified 9/9
before and after this phase's work. No production agent changes, ports, or
replacements.

**Corpus**: the same 11 three-entrant group rosters (54 cells each: 3
seeds x 3 layouts x 6 seat permutations) and 3 pairwise controls (18 cells
each) Phase 0/1 already defined and executed — `11 x 54 + 3 x 18 = 648`
cells per condition, `648 x 6 = 3,888` cells across all six tested weights.

**True executions vs rescored cells**, distinguished explicitly:

| source | cells | how |
|---|---:|---|
| K0 (`w_kill=5`) | 648 | **reused directly** — the committed Phase 1 default-condition corpus itself, not re-executed |
| K1/K2/K3/M1/M2 group (11 rosters x 54) | 2,970 | **offline-rescored** `result.json` copies (§7); no replay copied or regenerated |
| K1/K2/K3/M1/M2 pairwise (3 pairs x 18, `outcome` only) | 270 | **offline-recomputed** `outcome` field in an `evaluation.json` copy, `result.json` read from the original committed match directory unmodified |
| Execution-invariance validation sample | 92 (23 cells x 4 weights) | **real production executions**, `tools/v3_phase3_execution_invariance.py` |

Group and pairwise analysis reused `tools/v3_phase1_arena_action_grid.py`'s
own `analyze_roster`/`analyze_pair` functions **unmodified** (imported, not
reimplemented), pointed at the rescored artifact trees; §17 rubric scoring
reused `tools/v3_phase1_ecology_rubric.py`'s own criterion functions
**unmodified**.

---

## 10. Control reproduction (K0)

K0's group and pairwise analysis entries were diffed field-by-field against
`runs/research_v3_phase1/main/results/phase1_main_analysis.json`'s own
`a4096_b8` entries:

```text
rosters compared: 11/11, mismatches: 0   (win_rate and capture_caused, every agent)
pairwise pairs compared: 3/3, mismatches: 0   (candidate_win_rate)
```

**K0 reproduces the committed Phase 1 default-condition control exactly**,
which is the expected consequence of reusing the identical artifacts
rather than re-executing them — not a coincidence to be explained.

---

## 11. Pairwise negative controls (Phase 3I)

Alpha.3 §8 proved algebraically that in a 1-on-1, fixed-tick-limit match,
`alive_ticks` and `kills` are always exactly tied between two entrants in
every *non-forced* match (both entrants alive at the end), so `w_alive` and
`w_kill` cancel identically from the score comparison at any value; a
successful core capture instead makes the match *survival-forced*, so the
sole survivor wins regardless of any weight. Either way, a pairwise outcome
should never move with `w_kill`.

Checked directly, across all three pairwise controls at every non-default
weight (K1, M1, M2, K2, K3 against the K0 reference):

```text
pairwise comparisons checked: 15
changes: 0
PASS: True
```

**No pairwise outcome moved at any tested weight.** The control holds
exactly as predicted; interpretation proceeded without needing to invoke
the "stop and investigate" branch.

---

## 12. Group ecology results

Per-agent aggregate win rate (mean across every roster appearance),
K0 -> K3:

| agent | K0 (5) | K1 (400) | M1 (800) | M2 (1200) | K2 (1600) | K3 (3200) |
|---|---:|---:|---:|---:|---:|---:|
| claimer | 53.2% | 53.2% | 53.2% | 53.2% | 51.6% | 45.5% |
| hunter | 41.0% | 41.0% | 41.0% | 40.2% | 39.4% | 32.5% |
| core_seeker | 30.1% | 30.1% | 28.7% | 29.6% | 33.8% | 46.8% |
| core_tracker | 19.3% | 19.3% | 26.3% | 45.6% | 45.9% | 53.7% |
| core_defender | 28.1% | 29.3% | 24.8% | 10.7% | 10.4% | 10.4% |
| reactive_core_defender | 16.7% | 15.6% | 14.1% | 9.3% | 9.3% | 9.3% |

Search/expansion/defense aggregate win and capture-caused shares (from
`tools/v3_phase1_ecology_rubric.py`'s own `search_profile`, unmodified):

| condition | search win | expand win | defend win | search caused | expand caused | defend caused |
|---|---:|---:|---:|---:|---:|---:|
| K0 (5) | 24.1% | 47.1% | 22.4% | 38.9% | 2.9% | 1.1% |
| K1 (400) | 24.1% | 47.1% | 22.4% | 38.9% | 2.9% | 1.1% |
| M1 (800) | 27.4% | 47.1% | 19.4% | 38.9% | 2.9% | 1.1% |
| M2 (1200) | 38.5% | 46.7% | 10.0% | 38.9% | 2.9% | 1.1% |
| K2 (1600) | 40.5% | 45.5% | 9.8% | 38.9% | 2.9% | 1.1% |
| K3 (3200) | 50.6% | 39.0% | 9.8% | 38.9% | 2.9% | 1.1% |

Capture-caused shares are **exactly invariant** across every weight
(§6/§7's proof, empirically confirmed again here): the mechanism does not
change, only who benefits from it. `core_tracker` is the largest single
riser (19.3% -> 53.7%), consistent with it being the placement-agnostic,
probe-confirming search specialist the payoff hypothesis targets most
directly.

---

## 13. Original §17 rubric (verbatim)

The five Beta2 Phase 4 §17 criteria, scored by
`tools/v3_phase1_ecology_rubric.py`'s own unmodified functions:

| condition | C1 (leaders) | C2 | C3 | C4 | C5 | score |
|---|---|---|---|---|---|---:|
| K0 (5) | PASS (4) | PASS | PASS | PASS | PASS | 5/5 |
| K1 (400) | PASS (4) | PASS | PASS | PASS | PASS | 5/5 |
| M1 (800) | PASS (5) | PASS | PASS | PASS | PASS | 5/5 |
| M2 (1200) | PASS (5) | PASS | PASS | PASS | PASS | 5/5 |
| K2 (1600) | PASS (5) | PASS | PASS | PASS | PASS | 5/5 |
| K3 (3200) | PASS (5) | PASS | PASS | PASS | PASS | 5/5 |

**Every tested weight scores 5/5.** This is a real result, not a
tautology, but it needs one caveat stated plainly: criterion 2 (§14) and
criterion 5 (no roster ever reaches 90% even at K3, highest non-control
rate 83.3%) hold at *every* weight including K0, because — as §14/§16
detail — the specific things criterion 2 measures (the 1v1 matchup and
which archetype owns the capture mechanism) are exactly the two things
§6/§11 proved invariant to this lever. The rubric was never at risk of
*failing* under a kill-weight sweep; the informative question, and the
reason G1-G8 (§15) exist as an additional, stricter layer, is whether
offense becomes *more* rewarded without breaking coexistence — which the
verbatim rubric alone cannot see, by construction of what it measures.
Criterion 1's leader count rising from 4 to 5 (K2 onward) is a genuine,
if secondary, signal that the ecology diversified rather than collapsed.

---

## 14. Diagnostic criterion 2A / 2B split

**2A — pairwise counter-strategy effectiveness** (does dedicated search
beat blind expansion in the 1v1 controls?): `claimer` loses to
`core_tracker` 33.3% of the time (i.e. `core_tracker` wins 66.7%) and
`hunter` loses 22.2% of the time (`core_tracker` wins 77.8%) — **identical
at every tested weight**, confirmed by §11's pairwise negative control.
2A passes at all six weights, for the structural reason given in §11: it
is not a function of `w_kill` at all.

**2B — group offensive-mechanism effectiveness** (does search actually own
capture attribution in group play?): search's maximum capture-caused rate
(61.1%) exceeds every non-search agent's maximum (11.1%) at every tested
weight — again identical throughout, per §12's invariance table. 2B passes
at all six weights for the same structural reason.

Both halves were already true at the shipped default. Phase 3's kill-weight
lever cannot move either half, by construction (§6): it operates purely on
the score map that gets built *after* the matchup and the capture mechanism
have already been decided by gameplay. This is the direct, mechanistic
reason G1 (§15) is easy to satisfy and was never the discriminating gate.

---

## 15. Killer-versus-bystander payoff

The primary new causal metric, measured from exact per-cell replay-level
attribution (`battle_engine.evaluation_group_analysis.load_group_cell_records`,
Tier-2, single-death-restricted — never guessed on multi-death cells):

| condition | killer wins | attempts | killer-win rate | bystander wins | attempts | bystander-win rate |
|---|---:|---:|---:|---:|---:|---:|
| K0 (5) | 48 | 217 | **22.1%** | 169 | 217 | **77.9%** |
| K1 (400) | 51 | 217 | 23.5% | 166 | 217 | 76.5% |
| M1 (800) | 73 | 217 | 33.6% | 144 | 217 | 66.4% |
| M2 (1200) | 128 | 217 | 59.0% | 89 | 217 | 41.0% |
| K2 (1600) | 138 | 217 | **63.6%** | 79 | 217 | **36.4%** |
| K3 (3200) | 187 | 217 | 86.2% | 30 | 217 | 13.8% |

The pre-Phase-3 review quoted an approximate baseline of killer ≈ 36.3%,
bystander ≈ 63.7%. **Verified from committed data, the actual K0 baseline
is killer 22.1%, bystander 77.9%** — directionally identical (a clear
minority of killers ultimately win their own kill) but numerically
different, most likely because the review's figure came from a different
measurement scope than the 11-roster, 54-cell-per-roster default-condition
corpus this phase re-derives from first principles. The correction is
recorded here rather than silently adopting the quoted figure.

The response is a clean, monotonic dose-response curve spanning the exact
dead-zone / interior / saturation structure the pre-check predicted: flat
through K1, a sharp rise from M1 through K2, and clear saturation by K3.
**G4's predeclared 45–65% band (§15 of the governing prompt) is satisfied
only at K2 (63.6%) and closely approached from below at M2 (59.0%); K1 and
M1 fall short, K3 overshoots.**

---

## 16. Capture attribution

By strategic role, exact replay attribution, **identical at every tested
weight** (§6/§12's invariance, confirmed again at the individual-capture
level):

```text
attributed captures:    217 (single-death, unambiguous)
unattributed captures:  100 (multi-death cells; Tier-2 honestly declines to guess)
  search:      189 / 217  (87.1%)
  expansion:    22 / 217  (10.1%)
  defense:       6 / 217  ( 2.8%)
```

This reproduces, from this phase's own committed default-condition corpus,
the review's claim that search causes the large majority of captures at
the shipped default (the review's figure was 90.2% search / 7.9%
expansion measured against captures generally, not restricted to the
single-death-attributable subset this Tier-2 method can name a captor for
— the two are close and directionally identical, with the residual gap
attributable to denominator scope, disclosed rather than reconciled
further since it does not affect any Phase 3 conclusion).

**Deliberateness signature**: unaffected by construction. Since §6 proved
every tick, memory diff, and engine event is byte-identical across kill
weights, the capture *mechanism* — cells acquired by the killer, whether a
capture is a sole-ownership assault or a last-hit on a core damaged by
others, acquisition span — cannot have changed either. The payoff
intervention is provably score-only, not a disguised mechanism change.

---

## 17. Expansion/offense/defense coexistence

This is the phase's central finding, and it does not fit either extreme
cleanly.

**No single tested weight satisfies G3, G4, and G5 together** (§13's full
gate table). Reading the three relevant curves side by side:

| condition | search win share (G3 >= 25%) | killer-win rate (G4 in [45%, 65%]) | defense win share (G5 >= 15%) |
|---|---:|---:|---:|
| K0 (5) | 24.1% FAIL | 22.1% FAIL | 22.4% PASS |
| K1 (400) | 24.1% FAIL | 23.5% FAIL | 22.4% PASS |
| M1 (800) | 27.4% PASS | 33.6% FAIL | **19.4% PASS** |
| M2 (1200) | 38.5% PASS | 59.0% PASS | **10.0% FAIL** |
| K2 (1600) | 40.5% PASS | 63.6% PASS | 9.8% FAIL |
| K3 (3200) | 50.6% PASS | 86.2% FAIL | 9.8% FAIL |

The crossing point where G4 starts passing (between M1=800 and M2=1200)
and the crossing point where G5 stops passing (the identical interval) are
**the same bracket**. By the time decisive offense's own payoff has been
raised enough to move killer conversion into the predeclared healthy band,
defense's win share has already fallen below the predeclared 15% floor.
This is not a boundary artifact of one interpolation step: it holds at
every one of the three weights (M2, K2, K3) where G4 is closest to or
inside its band.

**What this is not**: it is not offense straightforwardly replacing
expansion as the new universal strategy. Expansion (`claimer`/`hunter`)
declines only gradually (47.1% -> 39.0% win share from K0 to K3, `claimer`
itself still on top at 45.5% even at K2) and criterion 5 never fails —
no archetype ever reaches 90% in even two rosters, and criterion 1's
distinct-leader count *rises* (4 -> 5) as weight increases. Search's rise
comes measurably more at defense's expense than at expansion's: defense's
aggregate win share roughly halves from K0 to M1 alone (22.4% -> 19.4%)
before collapsing further, while expansion barely moves in the same
interval.

**What it is**: raising the kill weight demonstrably converts the
"bystander inherits an uncompensated kill" pattern into "the killer is
compensated for its own kill" — precisely the mechanism the payoff
hypothesis predicted, and precisely why `kingmaking_observed` (Beta2 §17
criterion 4's own kingmaking check) flips from `True` at K0/K1 to `False`
from M2 onward: the passive third stops disproportionately inheriting
search's kills once search itself is paid fairly for them. But the same
correction that fixes the killer's payoff simultaneously erodes exactly
the mechanism (bystander survival value) that gave the two defender
archetypes most of their win share, since neither `core_defender` nor
`reactive_core_defender` is a search agent and neither benefits from
`weights.kill` directly.

---

## 18. Ranking and context sensitivity

Ranking perturbation against K0 (`tools/v3_phase1_ecology_rubric.py`'s own
`ranking_perturbation`, unmodified):

| condition | leader changes | pairwise reversals | strict | rates moved | mean abs move |
|---|---:|---:|---:|---:|---:|
| K0 (5) | 0/11 | 0/33 | 0 | 0/33 | 0.0pp |
| K1 (400) | 0/11 | 0/33 | 0 | 0/33 | 0.3pp |
| M1 (800) | 2/11 | 2/33 | 0 | 0/33 | 2.1pp |
| M2 (1200) | 3/11 | 7/33 | 3 | 6/33 | 8.3pp |
| K2 (1600) | 4/11 | 9/33 | 3 | 6/33 | 9.4pp |
| K3 (3200) | 5/11 | 12/33 | 3 | 9/33 | 14.5pp |

Ranking perturbation grows smoothly and monotonically with weight —
another clean dose-response signal, not a discontinuous jump, and further
evidence the intervention is behaving as a graded scoring lever rather
than a threshold effect.

Context sensitivity (criterion 3's three axes) stays materially
non-zero and roughly stable throughout:

| condition | seat | layout | seed |
|---|---:|---:|---:|
| K0 (5) | 100.0pp | 33.3pp | 27.8pp |
| K1 (400) | 100.0pp | 33.3pp | 27.8pp |
| M1 (800) | 100.0pp | 33.3pp | 33.3pp |
| M2 (1200) | 100.0pp | 33.3pp | 27.8pp |
| K2 (1600) | 100.0pp | 33.3pp | 27.8pp |
| K3 (3200) | 100.0pp | 33.3pp | 22.2pp |

No axis collapses toward zero at any tested weight — context sensitivity
does not trade away against the payoff correction, which rules out A7's
concern ("strategic ranking/context sensitivity collapses, leaving another
single-axis ecology") as literally stated, even though G5 fails.

Pairwise-versus-group divergence (criterion 4's other half) stays large
throughout: 29.6pp at K0/K1, rising to 50.0pp by K3 — comfortably above
the 10pp G7 floor at every weight.

---

## 19. Optional beacon probe

**Not run.** Ruling 4/Phase 3N make this strictly optional and non-gating,
intended to bound how much of search's density sensitivity is an artifact
of the reference agents' own discriminator rather than the Ruleset. That
question is orthogonal to the payoff hypothesis this phase tests — the
existing `core_tracker`/`core_seeker` reference agents' capture mechanism
was already shown invariant to kill weight (§6/§16), so a beacon-keyed
probe would not change any conclusion in this report. Skipped per the
prompt's own "if it is not necessary to answer the main payoff question,
skip it" instruction.

---

## 20. Phase 1 §9.1 correction

**Confirmed.** The pre-Phase-3 review's claim — that Phase 1 §9.1's
attribution of a scale effect to fixed `CORE_SIZE` is contradicted by
Phase 1's own capture-caused data — holds up under direct inspection of
Phase 1's own published constant-density diagonals
(`docs/V3_PHASE1_ARENA_ACTION_DENSITY.md` §9's table).

§9.1 predicted that a fixed 8-cell core against a scaling absolute action
budget should let search *afford more investigations* as the diagonal's
arena size (and therefore absolute budget) grows, and used **search win
rate** at `S = 0.195` (9.1% -> 8.2% -> 24.9% at arenas 4096/16384/65536,
budgets 800/3200/12800) as its evidence. That win-rate trend is real. But
the mechanism's own more direct signal — **search's capture-caused rate**,
the actual measure of whether search is causing more of the captures it is
supposed to be affording more of — moves the *other* way on four of the
five multi-point diagonals in the same table:

| diagonal (`S`) | conditions (absolute budget) | search-caused rate | trend vs. rising budget |
|---|---|---|---|
| 0.195 | a4096_b2 (800) -> a16384_b8 (3,200) -> a65536_b32 (12,800) | 41.8% -> 34.8% -> 37.0% | net **fall** |
| **0.781 (default)** | a1024_b2 (800) -> a4096_b8 (3,200) -> a16384_b32 (12,800) -> a65536_b128 (51,200) | 39.9% -> 38.9% -> 36.6% -> 28.2% | monotonic **fall**, 64x budget |
| 3.125 | a256_b2 (800) -> a1024_b8 (3,200) -> a4096_b32 (12,800) | 10.1% -> 5.1% -> 5.6% | net **fall** |
| 12.5 | a256_b8 (3,200) -> a1024_b32 (12,800) -> a4096_b128 (51,200) | 2.5% -> 1.9% -> 0.0% | monotonic **fall** |
| 0.049 (2 points only) | a16384_b2 (800) -> a65536_b8 (3,200) | 19.5% -> 28.0% | rise |

Four of five diagonals — including the one containing the shipped
default — show search-caused rate **falling**, in one case monotonically
across a 64x absolute-budget range, exactly where §9.1's own mechanism
predicts it should rise. Only the shortest diagonal (two points) shows a
rise, too thin a sample to anchor the mechanism against the other four.
This is evidence against attributing the scale effect specifically to
*affordable investigations causing more captures*; the win-rate rise
§9.1 documented is real but appears to be carried by something other than
increased capture-causing effectiveness — plausibly survival/territory
dynamics at those low-density, large-arena conditions, which this phase
did not further investigate since it is secondary to the payoff question.

Recorded here as a prospective correction, with its evidence, per Ruling 5.
`docs/V3_PHASE1_ARENA_ACTION_DENSITY.md` is not edited.

---

## 21. Compatibility and identity

**Nothing was bumped, and nothing needed to be.**

| axis | changed? | reasoning |
|---|---|---|
| Ruleset identity (`bytefray-rules-2`) | **No** | `weights.kill` is per-match configuration, exactly like `arena_size`/`instr_per_tick` before it (`docs/RULES.md`'s "Configuration values are not Ruleset identity"). No gameplay semantic was touched — proven, not assumed, by §6. |
| Agent API version | **No** | No `Observation`/`MatchContext`/`AgentAction` field changed; agents still receive nothing about scoring. |
| Result schema (`battle2.result`) | **No** | `reproducibility.weights.kill` already existed; only its range of values widened. |
| Replay schema (`battle2.replay`) | **No** | Same: the header's `config`/`reproducibility` already carried `weights`. |
| Evaluation schema (`bytefray.evaluation`) | **No** | `EffectiveConditions.weights` already existed and was already hashed into `_evaluation_id`/`effective_conditions_fingerprint`; no key was added, removed, or retyped. |
| Evaluation methodology identity | **Extended, not bumped** | `resolved_kill_weight`/`EvaluationRequest.kill_weight` are new *fields*, not a new methodology version; every pre-Phase-3 request that omits them is byte-identical to before. |

Empirical confirmation (also exercised by the 21 tests in
`test_v3_phase3_offense_payoff_evaluation.py`):

```text
omitted kill_weight  == explicit Config().weights.kill   (effective conditions, evaluation_id, canonical identity, executed reproducibility.weights.kill)
{5, 400, 1600, 3200} -> 4 distinct evaluation_ids
serial (--workers 1) == parallel (--workers 3) at a non-default kill weight
resume over a non-default-weight evaluation: no resumed_result_mismatch
```

No Ruleset bump (`bytefray-rules-3`/`-alpha*` was never created — this
experiment stays entirely under `bytefray-rules-2`, per the governing
task's explicit instruction).

---

## 22. Performance and artifact cost

| measure | value |
|---|---:|
| true production executions | 92 (23 sampled cells x 4 predeclared weights, execution-invariance validation) |
| offline-rescored group `result.json` cells | 2,970 (11 rosters x 54 cells x 5 non-K0 weights) |
| offline-recomputed pairwise `outcome` cells | 270 (3 pairs x 18 cells x 5 non-K0 weights) |
| K0 cells | 648 — reused directly, zero new artifacts |
| total logical corpus | 3,888 cells (648 x 6 weights) |
| disk used by all Phase 3 artifacts | 85 MB (55 MB validation-sample replays, 29 MB rescored `result.json` copies) |
| avoided duplication | ~4x-6x full replay corpora (each ~2-13 GB per Phase 1's own per-condition figures) that a naive full-re-execution sweep would have produced |
| Ruff / mypy | clean on every new/changed production and tooling file (`tools/v3_phase1_ecology_rubric.py`'s one pre-existing, unrelated `var-annotated` note is untouched, pre-dates this phase, and is outside the `engine/`/`client/` trees this project's own validation gate checks) |

---

## 23. Phase 3 verdict

### **PAYOFF HYPOTHESIS PROMISING — NARROW FOLLOW-UP REQUIRED**

Evidence for this verdict, weighed against the predeclared gates in the
order they force the conclusion:

1. **G1, G2, G6, G7, G8 hold robustly, in fact at every tested weight**
   (§13, §14, §18, §11) — the verbatim rubric always scores 5/5, criterion
   2's both halves always pass (they are structurally invariant to this
   lever, §14), pairwise/group divergence stays far above its floor, and
   the pairwise negative control never once moves.
2. **G3 and G4 can each be satisfied**, and can be satisfied *together* in
   the same narrow region (M2=1200 through K2=1600, §15/§17).
3. **G5 cannot be satisfied at the same time as G3+G4 anywhere in the
   tested range [5, 3200]**, including after the one predeclared round of
   MODIFY-rule interpolation (M1=800, M2=1200). The crossing point where
   offense's payoff becomes adequately compensated is the same crossing
   point where defense's win share falls below its predeclared 15% floor
   (§17's table makes this exact).
4. **None of the predeclared ABANDON criteria A1-A7 hold** (checked
   explicitly): outcomes move substantially (¬A1); defense degrades but
   never falls below 5% even at K3 (9.8%, ¬A3); the pairwise negative
   control never moves (¬A4); rescoring was validated exactly against real
   execution (¬A6); and while G5 fails, criterion 5 and context
   sensitivity never collapse (¬A7 as literally stated) — offense gains
   real ground without becoming a second universal solution.
5. This is squarely the second predeclared MODIFY trigger (Phase 3L): *"a
   MODIFY result may also be appropriate if payoff clearly affects
   ecology; offense becomes viable; but defense or criterion 5 fails only
   near one boundary."* The boundary here is sharp and well-characterized
   (between roughly `w_kill=800` and `w_kill=1200`), not vague, and the
   one permitted round of interpolation was used to characterize it rather
   than to search further.

**Why not a full GO**: Phase 3K's G3-G5 are phrased as properties of "a
successful weight" (singular) — a single weight where offense is
adequately compensated *and* defense remains meaningful *and* the
band-limited killer-conversion target is met. No such single weight exists
in the tested range; the region that satisfies G3+G4 is the same region
that fails G5.

**Why not ABANDON**: unlike Phase 2's locality verdict, no evidence here
points at a structural incompatibility. The mechanism is proven unchanged
(§6, §16); the divergence is a *quantitative* payoff-allocation tension
between two beneficiaries of the same correction (search gains what
defense's bystander-inheritance used to supply), not a sign that the
scoring lever is inert, that the corpus was compromised, or that the
result is a rescoring artifact.

**What a narrow follow-up would need to answer**, stated but not
implemented here, per the governing task's own scoping: whether a modest,
independently-justified compensating adjustment for defense specifically
(not a further kill-weight increase, which only sharpens the same
tension) could hold G5 at the same weight that already satisfies G3/G4 —
or whether that turns out to require a mechanic change after all, in which
case the finding would collapse back toward the core-model hypothesis §3
deprioritized.

---

## Files changed

| file | change |
|---|---|
| `engine/src/battle_engine/agent_evaluation.py` | `kill_weight` plumbing throughout the evaluation stack (§5) |
| `engine/src/battle_engine/agent_test.py` | `kill_weight` threaded into `Config.weights` construction |
| `engine/src/battle_engine/evaluation_worker.py` | additive `kill_weight` wire key |
| `engine/src/battle_engine/evaluation_history/cli.py` | non-default kill-weight disclosure in `show` |
| `engine/tests/test_v3_phase3_offense_payoff_evaluation.py` | **new** — 21 plumbing/identity/compatibility tests |
| `engine/tests/test_v3_phase3_rescore.py` | **new** — 7 offline-rescoring unit tests |
| `tools/v3_phase3_execution_invariance.py` | **new** — Phase 3C trajectory-invariance tool |
| `tools/v3_phase3_rescore.py` | **new** — Phase 3D offline rescoring + validation |
| `tools/v3_phase3_corpus.py` | **new** — Phase 3H/3F corpus builder + Phase 1 tooling reuse |
| `tools/v3_phase3_killer_bystander.py` | **new** — Phase 3J killer/bystander + attribution analysis |
| `tools/v3_phase3_rubric.py` | **new** — Phase 3J §17/2A-2B/pairwise-negative-control scoring |
| `docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md` | **new** — this report |

## Validation

| check | result |
|---|---|
| Full test suite (`python -m pytest`) | **2,179 passed, 14 skipped, 0 failed** in 264s. Phase 2's own measured baseline was 2,151 passed with the same 14 skipped — the delta is exactly the 28 new tests (21 + 7), with no pre-existing test removed or altered |
| Focused Phase 3 tests | 28/28 passed |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success, 81 source files |
| `mypy client/src/battle_client` | Success, 12 source files |
| Frozen `v2-baseline` population | **9/9** verify, before and after |
| K0 reproduces Phase 1 default-condition control | **exact**, 11/11 rosters and 3/3 pairwise pairs, 0 mismatches |
| Omitted-default / explicit-default equivalence | proven for effective conditions, evaluation_id, canonical match identity, and executed `result.json` |
| Non-default kill weights are identity-bearing | proven — 4 distinct weights, 4 distinct `evaluation_id`s |
| Execution-invariance (Phase 3C) | **23/23 sampled cells trajectory-invariant** across all 4 predeclared weights |
| Offline-rescoring equivalence (Phase 3D) | **69/69 exact agreement** (score and winner) against real production execution |
| Serial / parallel equivalence | proven at a non-default kill weight |
| Resume | proven safe at a non-default kill weight |
| Pairwise negative controls (Phase 3I) | **0/15 changed** across every tested non-default weight |
| No Ruleset / Agent API / schema semantic change | confirmed (§21) |

## Commits

| SHA | message |
|---|---|
| `e5f6dfc` | feat(evaluation): thread weights.kill through the evaluation stack |
| `5fa1070` | feat(research): add Phase 3 execution-invariance and offline-rescoring tools |
| `1ba6f5e` | feat(research): add Phase 3 corpus, killer/bystander, and rubric tooling |
| *(this report)* | docs(v3): record the Phase 3 offense payoff characterization findings |

Nothing merged to `main`, nothing tagged, nothing published. Ruleset v1,
Ruleset v2, the `v2.0.0` tag, `main`, `origin/main`, and the Phase 0/1/2
branches and reports are all unchanged.
