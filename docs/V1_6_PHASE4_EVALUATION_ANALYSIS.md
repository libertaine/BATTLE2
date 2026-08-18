# v1.6 Phase 4 — Aggregate & Statistical Analysis

This is the durable implementation record for v1.6 Phase 4: a pure,
derived statistical-interpretation layer over already-authoritative
`bytefray.evaluation` data — Wilson-interval win-rate estimates and exact
paired candidate-vs-baseline evidence, surfaced through the existing CLI,
evaluation-history, and Designer read paths.

Written in the same spirit as `docs/V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md`
through `docs/V1_6_PHASE3_EVALUATION_PRESETS.md`: this document cites all
three as the authoritative pre-implementation baseline rather than
re-deriving them, and in particular treats Phase 0-1 §12 ("Statistical
analysis data inventory") as the direct ancestor of the design below.

## 1. Starting state

Branch `v1.6-development`, HEAD `624e292` ("feat(evaluation): add
reusable evaluation presets", Phase 3's own closing commit) — confirmed
via `git rev-parse HEAD`. `main`/`origin/main` both at `c210358` (Phase
0-1's docs commit, predating Phase 2/3 — unchanged by this phase). Working
tree clean at the start (`git status --porcelain` empty). Full suite
reconfirmed green before any edit (see §21).

## 2. Statistical design note (written before implementation, per the
   governing prompt)

### 2.1 What Bytefray's evaluation design can legitimately answer

An evaluation's opponents and seeds are **explicit, author-chosen values**,
not draws from a randomly sampled population (Phase 0-1 §12, restated
here because it is the load-bearing fact behind every choice in this
section). Candidate and baseline cells are aligned **pairwise**, by exact
`(opponent_id, seed, orientation)` plus duplicate-occurrence order
(`agent_evaluation.compare_candidate_baseline`, unchanged this phase) —
this pairing is already the evaluation's real statistical unit, not
something Phase 4 invents.

Given that, Phase 4 can legitimately answer, **for this specific evaluated
sample**:

- How large is the observed candidate-vs-baseline difference (win-rate
  delta, score/territory differential delta)?
- Across the exact paired conditions Bytefray evaluated, in how many does
  the candidate do better / worse / the same?
- Is that pattern consistent across opponents? Across orientations?
- How much would sampling noise alone be expected to move an observed
  proportion, if the *same finite* evaluated cells were the whole
  population of interest (i.e., an interval around the observed rate,
  not a claim about matches never run)?
- Under the null hypothesis that candidate and baseline are equally
  likely to be the better side of a discordant paired condition, how
  surprising is the observed split (exact paired significance)?

### 2.2 What it cannot answer

- The agent's "true" win rate against some *hypothetical* infinite/random
  population of opponents or seeds — no such population was sampled from.
- Generalization to opponents/seeds/tick counts never evaluated.
- A single number that is "better" across opponents, score, territory,
  and ticks simultaneously — the codebase's own `classify()` deliberately
  never invents a lexicographic ranking across those dimensions
  (`docs/specs/agent_evaluation.md`'s "Strongest argument against this
  design"), and Phase 4 does not either.
- Causal claims about *why* an outcome differs (a behavior-profile
  question, explicitly deferred to a future phase, §23 of the governing
  prompt).

### 2.3 Descriptive vs. inferential quantities

**Descriptive** (no distributional assumption beyond "this is what was
observed"): matches played, wins/losses/ties, observed win rate, score/
territory differential averages, per-opponent/per-orientation breakdowns,
improved/regressed/unchanged/inconclusive counts.

**Inferential** (make an explicit, disclosed assumption in order to say
something about uncertainty or evidence):

1. **Wilson score interval on an observed win proportion.** Assumption:
   the `matches_played` scored cells in the given scope are treated as
   independent identical Bernoulli(win) trials *for the purpose of
   quantifying sampling variability around the observed proportion within
   this fixed, already-run sample* — not as a claim that they are a
   random sample from a larger population. This is the same "interval for
   this evaluation design/sample" framing Phase 0-1 §12 already
   recommended.
2. **Exact two-sided binomial test on discordant paired outcomes** (the
   exact sign test / exact McNemar test at p=0.5). Assumption: under the
   null hypothesis that candidate and baseline are equally likely to be
   the better side of any given discordant pair, each discordant pair's
   direction is an independent Bernoulli(0.5) trial. This assumption is
   most defensible when the discordant pairs are more or less
   exchangeable (similar opponents/seeds/orientation mix); it is
   deliberately **not** used as a single pooled verdict without also
   showing the per-opponent/per-orientation breakdown (§2.5), so a reader
   can see whether that exchangeability assumption looks reasonable for
   their own matrix.

### 2.4 Tie treatment (explicit choice, per the governing prompt)

The Wilson interval is computed over **win vs. not-win** (loss or tie
folded together as "not win"), exactly matching the meaning of the
existing `SubjectAggregate.win_rate_display` (`wins/matches_played`) —
never a half-win credit for a tie. `tie_rate` and `loss_rate` are always
reported alongside the win interval so a high tie rate is never hidden
behind a win-rate number that silently treated ties as ordinary losses.
Ties are excluded entirely from `matches_played` only when a cell isn't
`is_scored` at all (subject/opponent init failure, tool failure) — that
exclusion already exists in `SubjectAggregate` and is unchanged by this
phase.

### 2.5 Pairing, opponent blocking, and orientation blocking

Opponent and orientation are both real, disclosed blocking factors, not
interchangeable repetitions (governing prompt §9/§10; Phase 0-1 §12's
explicit warning against pooling across opponents). Phase 4's overall
paired test **pools every discordant pair across every opponent and
orientation** (it is, precisely, "run the exact test over every aligned
`ComparisonEntry`") — but this pooled number is never presented alone:
a per-opponent and a per-orientation `PairedEvidence` breakdown are always
computed alongside it, plus an explicit `consistency` label
(`"consistent: ..."` / `"mixed: ..."` / `"insufficient evidence..."`)
describing whether every group with at least one discordant pair points
the same direction. This mirrors the governing prompt's own preferred
alternative to a "statistically defensible blocked overall test" (§9):
"per-opponent inferential results, overall descriptive delta, explicit
mixed/inconsistent presentation" — rather than a Cochran–Mantel–Haenszel-
style stratified test, which would be exactly the "sophisticated modeling
merely to produce one p-value" the prompt discourages. Orientation is
treated identically (§10 asks for the same three-way choice — pool,
report orientation-specific only, or a blocked method — and this design
picks "pool overall, but always also report orientation-specific
evidence and a consistency label," the same choice made for opponents,
for the same reason).

### 2.6 Small-N and insufficient-sample handling

Every quantity that requires a nonzero denominator is guarded explicitly:
a `RateEstimate` with zero scored matches reports `state =
insufficient_data` and a `None` interval (never a fabricated 0.0%);
a `PairedEvidence` with zero paired conditions reports `state =
no_matched_conditions`; one with paired conditions but zero discordant
pairs (e.g. all ties, or a baseline-free evaluation) reports `state =
no_discordant_pairs` and both the interval and the exact test are `None`
— never presented as "0% / not significant," which would misleadingly
imply evidence was gathered when none was. No new dependency was added
for this (§2.7).

### 2.7 No new runtime dependency

`WilsonInterval`'s normal quantile (`z`) is taken from the standard
library's `statistics.NormalDist().inv_cdf(...)` (available since Python
3.8; this repository's supported floor per `pyproject.toml`/CI matrix is
3.10+). The exact binomial test uses `math.comb` for exact integer
binomial coefficients. Neither requires SciPy or any other new
dependency; `pyproject.toml`'s runtime dependency list is unchanged by
this phase.

## 3. Existing aggregate/comparison architecture (verified from current
   source, not assumed from Phase 0-1 alone)

- `EvaluationCell` (`agent_evaluation.py:635`), `SubjectAggregate`
  (`:681`), `ComparisonEntry` (`:715`) are the three canonical dataclasses.
  `aggregate_cells` (`:885`) and `all_subject_aggregates` (`:931`) are the
  **one** aggregation implementation, reused unchanged by both the live
  run path (`EvaluationService.run`) and the historical read path
  (`evaluation_history/v1_adapter.py`, `v2_adapter.py`, and the Designer's
  `read_evaluation_presentation`... actually the Designer path reads the
  persisted `aggregates`/`comparison` blocks directly rather than
  recomputing — see §11). `compare_candidate_baseline` (`:982`) is the one
  comparison implementation.
- **Pairing is exact, not approximate.** `compare_candidate_baseline`
  groups candidate and baseline cells by `(opponent_id, seed,
  orientation)`, then pairs same-key lists **positionally**
  (`zip_longest`), so a repeated `(opponent, seed, orientation)` tuple
  (an intentionally-preserved duplicate, never silently collapsed) still
  produces one `ComparisonEntry` per duplicate occurrence rather than
  merging duplicates or dropping the extra ones. This positional pairing
  is exactly the "condition_occurrence_index" idea already established
  for cross-evaluation alignment (`docs/specs/evaluation_history.md` §8),
  applied within one evaluation.
- **The statistical unit represented by one `ComparisonEntry`** is:
  candidate and baseline each played the same opponent, at the same seed,
  under the same orientation (both physically ran with the same entrant
  in the always-first-acting slot) — the closest thing to a controlled,
  matched pair Bytefray's design produces. A `classification` of
  `"improved"`/`"regressed"`/`"unchanged"` reuses the existing
  `classify()` outcome-rank comparator (`win > tie > loss`) unchanged;
  `"inconclusive"` covers a missing/unscored cell on either side.
- `all_subject_aggregates` already computes three orientation-scoped
  views per subject (`"all"`, `"candidate_first"`, `"opponent_first"`) —
  the exact per-orientation win/loss/tie counts Phase 4's orientation
  `RateEstimate`s are built from, with zero new aggregation code.
- `SubjectAggregate` has no per-opponent scope (only pooled + orientation)
  — Phase 4 does not add one to that dataclass. Per-opponent evidence is
  instead built directly from `ComparisonEntry` rows grouped by
  `opponent_id` (§4), which already carry per-opponent win/loss/tie
  outcomes for both sides plus per-cell score/territory data, so no new
  per-opponent aggregation primitive was needed in `agent_evaluation.py`
  at all.

## 4. Analysis data model (`engine/src/battle_engine/evaluation_analysis.py`, new)

Pure, dependency-free (stdlib only), Qt-free module. No mutable state; no
I/O. Every function is a pure function of already-computed
`SubjectAggregate`/`ComparisonEntry` values (via the one entry point,
`analyze()`, which itself only calls `all_subject_aggregates`/
`compare_candidate_baseline` — never a second, drifting aggregation).

```
WilsonInterval        -- (lower, upper, confidence_level)
RateEstimate          -- descriptive win/loss/tie + Wilson win_interval,
                          for one subject in one scope (overall or one
                          orientation)
PairedEvidence        -- exact paired evidence (better/equal/worse counts,
                          Wilson interval + exact p-value over discordant
                          pairs, descriptive score/territory deltas) for
                          one scope (overall, one opponent, or one
                          orientation)
EvaluationAnalysis    -- the full top-level result: candidate/baseline
                          RateEstimates (overall + per-orientation),
                          overall/by-opponent/by-orientation
                          PairedEvidence, and two plain-language
                          consistency labels
SampleState           -- RateEstimate's evaluated/insufficient_data enum
EvidenceState          -- PairedEvidence's evaluated/no_matched_conditions/
                          no_discordant_pairs enum
PairedDirection        -- favors_candidate/favors_baseline/even/undetermined
```

`analyze(candidate_id, baseline_id, cells, *, confidence_level=0.95) ->
EvaluationAnalysis` is the one entry point. It accepts `Sequence[
EvaluationCell]` — the single genuinely canonical unit both the live run
path and the historical read path already reconstruct (`evaluation_
history.models.evaluation_cells_from_raw` rebuilds real `EvaluationCell`
objects from parsed JSON specifically so `all_subject_aggregates`/
`compare_candidate_baseline` can run unchanged — Phase 4 slots into that
exact same seam, adding no new reconstruction logic of its own).

A second, narrower helper, `paired_evidence_from_verdicts(scope_label,
verdicts)`, builds one `PairedEvidence` directly from a plain sequence of
`"improved"/"regressed"/"unchanged"/"inconclusive"` strings — used by
`evaluations compare` (§9), whose `ComparisonRow.verdict` uses the
identical vocabulary (`comparison.py`'s `verdict()` is documented as "the
identical mapping to `agent_evaluation.classify`") but has no
`ComparisonEntry` of its own (it compares two *separate* evaluation
artifacts, not candidate vs. baseline within one).

## 5. Confidence-interval method and tie semantics

Wilson score interval (Wilson 1927; standard reference form, e.g. Brown/
Cai/DasGupta 2001), computed via the numerically stable center ± half-
width formula (never the naive normal/Wald approximation, which misbehaves
at small n or p near 0/1 — exactly Bytefray's common evaluation regime).
`z` is `statistics.NormalDist().inv_cdf(1 - (1-confidence_level)/2)` —
exact, not a hardcoded 1.96. Default confidence level 95%, always passed
explicitly and always shown alongside the interval in every presentation
(never an implicit, unlabeled number). Tie treatment: §2.4 above (win vs.
not-win; tie/loss rates always shown alongside, never folded into a
half-win credit).

## 6. Paired-comparison method and exact definition

Exact two-sided binomial test (equivalently, the exact sign test / exact
McNemar test at p=0.5) over discordant `ComparisonEntry` pairs
(`classification in {"improved", "regressed"}`), computed by doubling the
smaller tail of `Binomial(n, 0.5)` using `math.comb` for exact integer
coefficients — see §2.3/§2.7. "Candidate better/equal/worse than
baseline" is defined **exactly** as `agent_evaluation.classify()` already
defines it (`win > tie > loss` outcome rank delta) — no second concept of
improvement was invented. `PairedEvidence.better_interval` is a Wilson
interval over the *proportion of discordant pairs favoring the
candidate*, a distinct quantity from any single subject's win rate — it
answers "of the paired conditions where the two sides actually disagreed,
how lopsided was that disagreement," not "what fraction of all matches
did the candidate win."

## 7. Opponent-blocking treatment

§2.5/§3. Per-opponent `PairedEvidence` for every opponent id present in
the evaluation's comparison rows, computed by filtering `ComparisonEntry`
rows on `opponent_id` and reusing the identical `paired_evidence_from_
entries` function used for the overall/orientation scopes — one
implementation, three call sites (overall, by-opponent, by-orientation),
matching this codebase's own stated "avoid two aggregation
implementations that could independently drift" convention. No
Cochran–Mantel–Haenszel-style stratified overall test was implemented
(deliberately, §2.5); a plain-language `opponent_consistency` label is
computed instead (§9 below).

## 8. Orientation treatment

§2.5/§3, identical mechanism to opponent blocking, filtering
`ComparisonEntry` rows on `orientation` instead of `opponent_id`. An
evaluation run with `--single-orientation` (or a historical artifact
predating both-orientation support) simply produces one non-empty
orientation group and one empty one; the empty group's `PairedEvidence`
reports `state = no_matched_conditions`, never a fabricated zero-evidence
verdict presented as if it were meaningful.

## 9. Insufficient-sample behavior

§2.6. `SampleState`/`EvidenceState` are explicit enums (not ad hoc
strings), following this codebase's own `FieldConfidence`/`HealthCode`
convention (`evaluation_history/models.py`) for exactly this kind of
"don't silently default an absent quantity" requirement. `RateEstimate.
win_interval`/`PairedEvidence.better_interval`/`PairedEvidence.
exact_p_value` are all `None` (never a fabricated number) whenever their
respective denominators are zero.

## 10. Persisted vs. derived decision

**Fully derived, never persisted.** `analyze()` is a pure function of
already-canonical `EvaluationCell` data; nothing about `evaluation.json`'s
schema, `SCHEMA_VERSION`, or `IDENTITY_VERSION` changes in this phase.
This directly satisfies the governing prompt's strong preference (§14) and
lets every existing valid v1/v2 evaluation artifact gain analysis
immediately, with no re-run and no migration.

## 11. Historical artifact compatibility

`evaluation_history.models.evaluation_cells_from_raw` already reconstructs
real `EvaluationCell` objects from parsed JSON for both v1 and v2
artifacts (used by `v1_adapter.py`/`v2_adapter.py` to call `all_subject_
aggregates`/`compare_candidate_baseline` unchanged) — `EvaluationSummary`
gained one new field, `analysis: EvaluationAnalysis`, computed at the
exact point in each adapter where `real_cells` is already in scope, so no
new reconstruction logic was needed. `app/services/designer_workflows.py`'s
`read_evaluation_presentation` (a third, simpler read path used only by
the Designer, over a live evaluation.json it trusts unconditionally) now
also calls `evaluation_cells_from_raw` (imported from `evaluation_history.
models`, not re-implemented) followed by `evaluate_analysis.analyze()`,
reusing the same one reconstruction helper a third time rather than
writing a fourth.

## 12. CLI presentation

`bytefray agents evaluate` (only with `--baseline` set, and only in
non-`--quiet` mode) gains one concise `evidence:` block after the existing
`comparison:` summary line — overall Wilson interval for candidate and
baseline win rate, the overall paired better/equal/worse counts, the
overall Wilson interval + exact p-value over discordant pairs, and the
two consistency labels. Deliberately terse (a handful of lines) per the
governing prompt's "avoid overwhelming normal evaluations with a wall of
statistics" — full by-opponent/by-orientation `PairedEvidence` detail is
available via `evaluations show`, not printed by default here.

## 13. Evaluation-history integration

`bytefray agents evaluations show <id>` gained an `analysis:` section
(overall + by-opponent + by-orientation, using `EvaluationSummary.
analysis`, itself derived — §10/§11). `bytefray agents evaluations
compare <left> <right>` gained one `evidence:` line built from `paired_
evidence_from_verdicts` over `AlignedComparison.rows` — deliberately
narrower than `show`'s full breakdown, since a cross-evaluation compare
already carries its own strict condition-alignment/health machinery this
phase does not extend (per the governing prompt's explicit instruction:
"do not calculate a statistical comparison across unmatched evaluation
conditions unless the tool explicitly reports that limitation" — `compare`
already discloses `unmatched_left`/`unmatched_right`/`changed_condition`/
`ambiguous_duplicate_groups` counts unchanged by this phase, and the new
evidence line is computed only over `result.rows`, i.e. only the aligned,
directly-comparable pairs).

## 14. Designer integration

Modest, per the governing prompt's explicit scope limit. `app/services/
designer_workflows.py`'s `EvaluationPresentation` gained one field,
`analysis: EvaluationAnalysis | None` (`None` only if the artifact has zero
cells), computed by the same shared `evaluation_analysis.analyze()` call —
zero statistical calculation was added to Qt/UI code. `app/views/
evaluation.py`'s results view gained a short summary line (candidate/
baseline win-rate interval, overall paired evidence one-liner) rather than
a new visualization framework or an elaborate drill-down UI.

## 15. Numerical validation

See §21 (focused test results) for the concrete fixtures. Summary of the
independent-oracle strategy (never testing the implementation against
itself, per the governing prompt):

- **Wilson interval**: closed-form edge cases independently derivable by
  hand from the general formula — `x=0` reduces to `upper = z^2/(n+z^2)`,
  `lower = 0` exactly; `x=n` is the mirror image. `z` for 95% is
  cross-checked against the well-known literature constant
  `1.9599639845...`, not merely trusted from `NormalDist` in the same
  test that exercises the interval formula. Monotonicity (interval widens
  as `n` shrinks; contains the point estimate) and boundary containment
  (`0 <= lower <= upper <= 1`) are asserted structurally, not by exact
  digit-matching against a second implementation.
- **Exact binomial p-value**: cross-checked against textbook exact
  sign-test table values (e.g. `n=4, k=4 -> p=0.125`; `n=4, k=3 -> p=0.625`
  — standard, independently-published two-sided exact sign-test results,
  not derived from this module's own code).

## 16. Performance

Measured directly (see §21) rather than assumed: `analyze()` is O(number
of cells) with small constant factors (a handful of list comprehensions
over already-in-memory dataclasses, one `all_subject_aggregates` call
already paid for by existing code, one `compare_candidate_baseline` call
likewise) — no I/O, no new O(n²)/O(n log n) structure.

## 17. Limitations (disclosed, not silently worked around)

- The overall paired exact test pools across opponents and orientations
  (§2.5); it is a legitimate, disclosed pooling, not a stratified test —
  a reader who wants the stratified picture uses the by-opponent/
  by-orientation breakdown shown alongside it, always, not behind an
  extra flag.
- `evaluations compare`'s evidence line is deliberately shallower than
  `show`'s (§13) — it does not break down by opponent/orientation,
  because `compare` operates across two independently-evaluated artifacts
  whose opponent/seed/orientation sets may not even overlap; the existing
  `denominators` block already discloses how much of each side went
  unmatched.
- No ranking system, no behavior-profile analytics, no Elo/Glicko — all
  explicitly out of scope per the governing prompt and untouched by this
  phase.
