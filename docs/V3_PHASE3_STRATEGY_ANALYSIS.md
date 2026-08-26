# Bytefray v3.0 Phase 3 — Strategy Analysis

Branch: `v3.0-development`. Status: complete, not merged, not tagged, not
published.

## Scope

Set by explicit user direction, organized around four questions a user
should be able to answer after running an evaluation, without manually
cross-referencing separate CLI/GUI text blocks:

> Who won, and how convincingly? What did each agent actually do? Why might
> the matchup have favored one agent? Where can the user inspect the
> evidence?

The user's framing was explicit that this is **evidence presentation, not a
new rating/scoring system**, and that the biggest opportunity was that
Bytefray already computes substantial analytics but presents most of it as
plain text — so the phase was directed to *audit what already exists first*
(mirroring how Phase 2 audited the actual workflow before changing it),
then improve how that data is structured and surfaced, with as little new
engine analysis as possible.

**Excluded, by the same direction**: Elo/Glicko or any global ranking; a
composite "agent strength" score; clustering; AI-generated strategic
explanations; new gameplay metrics added merely to fill UI space; and Phase
4's evaluation-execution-controls work (GUI worker-count parity, etc.). None
of these were touched.

No Ruleset, Agent API, scoring, scheduler, capture-semantics, or
reference-agent behavior was changed. No `evaluation_id`/artifact-schema
change — every widget/CLI addition below reads an already-canonical
artifact or recomputes from already-canonical cells, never re-executes a
match.

---

## 0. Audit: what already existed

Before writing any presentation code, the existing analytics pipeline was
read in full (`agent_evaluation.py`'s CLI print functions,
`evaluation_group_analysis.py`, `evaluation_capture.py`,
`app/views/evaluation.py`'s `EvaluationResultsDialog`,
`app/views/evaluation_history.py`'s `EvaluationHistoryDialog`/
`EvaluationComparisonDialog`, `evaluation_history/cli.py`, and the original
`docs/specs/agent_evaluation.md`). Findings that shaped everything below:

* **`evaluations show --json` already serialized everything** — Wilson
  intervals, all 11 behavior dimensions, capture analysis, and the full
  group interaction matrix were already reachable as clean JSON via one
  flag. The live `agents evaluate` command had no `--json` at all.
* **`evaluation_capture.CaptureAnalysis`** (capture rate caused/suffered,
  survival rate, mean/median capture tick) was fully computed by the engine
  but never imported into either GUI dialog — zero GUI exposure anywhere.
* **The group-play captor→victim `InteractionMatrix`** printed in both CLIs
  but was never rendered in either GUI dialog.
* **`EvaluationHistoryDialog` (the "drill deeper" browsing surface) was
  actually the *thinnest* of the four presentation surfaces** — no Wilson
  interval, no behavior, no capture, no elimination rate, no interaction
  matrix — thinner than even the live-run results dialog, despite being
  named for deeper inspection.
* **`BehaviorAnalysis.candidate_vs_baseline_largest`** already ranks the
  biggest behavior deltas by a documented, bounded-unit-only rule — a
  ready-made, no-new-computation basis for a "why" panel: juxtaposing
  already-ranked evidence, not inventing a new ranking.
* **The original v1 spec** (`docs/specs/agent_evaluation.md` §13/§20)
  explicitly said "no in-Designer chart rendering, no new visualization
  framework" — a deliberate, v1-era, modest-GUI decision. It had already
  been superseded once (Phase 4/v1.6 added the Wilson-interval layer §20
  had also called explicitly out of scope). `V3_PRODUCT_SCOPE.md`'s own
  Phase 3 objective calls for "genuinely visual" presentation, so this
  phase knowingly supersedes that provision rather than silently
  contradicting it — recorded here per this project's rule against
  silently changing historical semantics.

Conclusion: almost nothing needed new engine analysis. The work is (a) two
disclosed presentation defects to fix, (b) one CLI gap (`--json` on the
live command) to close by reusing existing serialization, (c) wiring
already-computed `capture`/`behavior`/`group_analysis` into the two GUI
surfaces that never received them, and (d) a genuinely visual rendering of
data every dialog already had in hand.

## 1. Two disclosed v1.6 Phase 6 defects, resolved

Both were precisely located and fixed with no schema/behavior change beyond
the defect itself.

**Defect 1 — `evaluations compare`'s ambiguous-fallback grouping omitted
orientation.** `evaluation_history/comparison.py`'s `_classify_unmatched`
grouped strictly-unmatched cells by `(opponent_id, seed)` only. Comparing
two both-orientation evaluations that also differed in another condition
(e.g. tick count) pooled a `candidate_first` cell and an `opponent_first`
cell for the same `(opponent, seed)` into one spurious 2-vs-2
`ambiguous_duplicate_group`, when each orientation was independently an
unambiguous 1:1 `changed_condition` relation. Fixed by adding orientation
to the fallback key. Two pre-existing tests
(`test_evaluation_comparison_dialog_ambiguous_group_never_enables_actions`,
`test_compare_evaluations_ambiguous_groups_are_disclosed_not_silently_zero`)
had (unknowingly) relied on this exact bug to construct their "ambiguous"
test scenario via a single duplicated-by-orientation seed; both were
rewritten to use a genuinely ambiguous scenario (a literally duplicated
seed) so their original intent — ambiguous groups disable drill-down
actions and are disclosed, not silently zeroed — is still covered.

**Defect 2 — `evaluations show`'s paired-evidence wording omitted a
qualifier the live CLI already had.** `evaluation_history/cli.py`'s
`_paired_evidence_line` printed `"N matched, no discordant pairs --
interval/exact test not meaningful"` for the all-inconclusive-pairs case;
the live `agents evaluate` CLI's equivalent line already said `"...(all
unchanged/inconclusive) -- interval/exact test not meaningful"`. Both read
the identical `PairedEvidence.state`; only the English differed. Fixed by
matching the live CLI's wording exactly.

## 2. Structured (`--json`) output on `agents evaluate`

`bytefray agents evaluate` gained a `--json` flag producing the same
top-level `analysis`/`behavior`/`capture`/`group_analysis` keys
`evaluations show --json` already has, computed the identical way
`_print_result` already computes them for text, layered onto the artifact
the run just wrote (read back from its own `state_path`, so it can never
drift from what was persisted). `--dry-run --json` emits a minimal
structured matrix preview instead of the human text. `--quiet` still
suppresses output entirely in either mode. No second command is needed to
get structured output for a run just executed.

## 3. Visual evidence widgets

New module `app/widgets/evaluation_visuals.py` — hand-rolled,
`QPainter`-based Qt widgets, no new third-party charting dependency (kept
deliberately modest, consistent with this codebase's existing GUI
precedent and zero added compatibility/dependency risk):

* **`ProportionBar`** — a stacked horizontal proportion bar with an
  optional Wilson-interval whisker. Renders a `RateEstimate` (win/tie/loss
  share plus its own CI — pairwise win rate), a `RateStat` (a single rate
  plus its own CI — group winner/survival/elimination rate), or a bare
  float rate with no CI (capture rates, which were never given a Wilson
  interval).
* **`DimensionDeltaRow`** — one behavior dimension, candidate vs. baseline,
  scaled only against that dimension's own range (never across dimensions
  — the same "don't invent a shared scale" rule
  `evaluation_behavior.largest_bounded_differences` already applies to
  ranking, extended to rendering). A ★ marks a dimension already ranked
  among the largest candidate-vs-baseline differences.
* **`InteractionMatrixGrid`** — a captor→victim heatmap for the group
  interaction matrix; shading encodes the pair's already-computed rate,
  cell text is the raw count.

Every value these widgets draw comes from an already-computed engine
dataclass; the module computes no statistic, ranking, or derived score.

## 4. Wired into the live-run results dialog

`app/views/evaluation.py`'s `EvaluationResultsDialog` gained a
`_build_visual_evidence_panel` (bounded-height, scrollable, added below the
existing one-line text summaries — kept, not removed, for quick-scan
accessibility):

* Pairwise: a win-rate bar per subject (candidate, and baseline if
  present); core-capture rate bars (**previously absent from this dialog
  entirely**) when the artifact is Ruleset-v2; every behavior dimension as
  a row, highlighted where already ranked "largest difference" — this is
  the "why might X have favored one agent" surface: it juxtaposes the
  already-ranked behavior deltas next to the win-rate outcome shown
  directly above, inventing no causal claim.
* Group: winner/survival/**eliminated** rate bars per roster entrant
  (elimination was computed by `EntrantSummary.elimination` but never
  rendered anywhere in the GUI before this phase — only the CLI's
  `_print_entrant_summary_row` showed it); the captor→victim interaction
  matrix grid when any capture occurred (**previously absent from this
  dialog entirely**).

`app/services/designer_workflows.py`'s `EvaluationPresentation` gained a
`capture: CaptureAnalysis | None` field, computed the same way
`_print_result`/`--json` compute it, to supply this data.

## 5. Wired into the evaluation-history dialog

Per the audit's §0 finding, `EvaluationHistoryDialog` was the thinnest
surface despite being the "drill deeper" workflow. `app/services/
evaluation_history_workflows.py` gained `behavior_analysis_for_summary`/
`capture_analysis_for_summary` (mirroring the already-existing
`group_analysis_for_summary`, and the CLI's own `_cmd_show` computation),
and `app/views/evaluation_history.py` gained `_build_history_visual_panel`
— the same shared widget panel as §4, wired into a new `QScrollArea` that
refreshes on each row selection. `EvaluationComparisonDialog` (a
structurally different, verdict-focused surface) was left unchanged —
scoped out rather than opportunistically touched; noted here as a
deferred candidate, not silently skipped.

## 6. Before/after evidence

Captured against the real running Designer (native `windows` Qt platform,
not `offscreen` — Phase 1/2 already found `offscreen` renders unreadable
tofu-box text on this environment), driving a real backend evaluation run
(not a mock) through the actual `EvaluationResultsDialog`/
`EvaluationHistoryDialog` classes, under
`docs/screenshots/v3-phase3-baseline/`:

| file | shows |
|---|---|
| `results-dialog-pairwise-visuals.png` | Live-run results dialog: candidate/baseline win-rate bars with CI whiskers (one all-tie, gray; one all-win, green), core-capture bars, and the behavior-dimension panel with its ★-highlighted largest-difference row |
| `results-dialog-group-visuals.png` | Live-run results dialog, group mode: per-entrant winner/survival/eliminated bars — including a 100% elimination rate rendered in red, the first time this project has shown elimination anywhere in a GUI |
| `history-dialog-visuals.png` | `EvaluationHistoryDialog` showing the same visual panel for a historically-browsed (not just-run) group evaluation |

## Files changed

| file | change |
|---|---|
| `app/widgets/evaluation_visuals.py` | **new** — `ProportionBar`, `DimensionDeltaRow`, `InteractionMatrixGrid`, and their data-factory functions |
| `app/views/evaluation.py` | `_build_visual_evidence_panel`; wired into `EvaluationResultsDialog` |
| `app/views/evaluation_history.py` | `_build_history_visual_panel`; wired into `EvaluationHistoryDialog` via a new `QScrollArea` |
| `app/services/designer_workflows.py` | `EvaluationPresentation.capture` field + computation |
| `app/services/evaluation_history_workflows.py` | `behavior_analysis_for_summary`, `capture_analysis_for_summary` |
| `engine/src/battle_engine/agent_evaluation.py` | `--json` flag; `_matrix_to_json`, `_result_to_json` |
| `engine/src/battle_engine/evaluation_history/comparison.py` | Defect 1 fix — orientation in `_classify_unmatched`'s fallback key |
| `engine/src/battle_engine/evaluation_history/cli.py` | Defect 2 fix — `_paired_evidence_line` wording |
| `tests/test_evaluation_visuals.py` | **new** — 7 widget-construction/render tests |
| `tests/test_agent_evaluation_dialog.py` | +2 visual-panel integration tests |
| `tests/test_beta3_group_designer_dialogs.py` | +1 group visual-panel integration test |
| `tests/test_agent_evaluation_history_dialog.py` | ambiguous-group test rewritten for the Defect 1 fix |
| `engine/tests/test_agent_evaluation.py` | +6 `--json` CLI tests |
| `engine/tests/test_evaluation_history_comparison.py` | +1 Defect 1 regression test |
| `engine/tests/test_evaluation_history_cli.py` | +1 Defect 2 regression test |
| `engine/tests/test_evaluation_history_workflows.py` | ambiguous-group test rewritten for the Defect 1 fix |
| `docs/screenshots/v3-phase3-baseline/*.png` | **new** — the three images in §6 |
| `docs/V3_PHASE3_STRATEGY_ANALYSIS.md` | **new** — this report |

## Validation

| check | result |
|---|---|
| Default suite (`python -m pytest`, `testpaths` scope) | exit 0, clean |
| Root `tests/` directory, `-m gui` (display-backed, run explicitly on this Windows session's real display) | 216/216 passed |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success, 84 source files |
| `mypy client/src/battle_client` | Success, 12 source files (unaffected; re-run for completeness) |
| `app/` (Designer/Qt) mypy | not part of this project's mypy gate (see Phase 2's identical note) |
| Real driven GUI walkthrough | pairwise, group, and history dialogs all screenshotted against real backend evaluation runs — confirmed legible, correctly colored/proportioned, correctly scoped (0%-rate bars show an empty track, not a misleading full bar) |
| No `evaluation_id`/schema change | confirmed — every addition reads an existing artifact or recomputes from already-canonical cells |
| Scope guards held | confirmed by inspection of this diff — no Elo/Glicko, no composite score, no clustering, no AI-generated text, no new gameplay metric, no Phase 4 GUI worker-count work |

## Phase 3 verdict

### **STRATEGY ANALYSIS MADE VISUAL — EVIDENCE PRESENTATION ONLY, NO NEW SCORING SYSTEM**
