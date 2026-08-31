# Bytefray v3.0 — Phase 4: Evaluation Infrastructure

This document records Phase 4 of the v3.0 product cycle (see
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) §6). Phase 4's objective is to
improve how users start, inspect, reproduce, and manage evaluations —
while preserving all existing evaluation semantics, canonical identity,
Ruleset behavior, and artifact compatibility. It follows Phase 3 (Strategy
analysis, complete), and does not begin Phase 5 (Distribution) work.

## 1. Initial state

Phase 3 (`V3_PHASE3_STRATEGY_ANALYSIS.md`) was already committed on
`v3.0-development` at session start (`b5cd7fa "initial commit phase 4"`,
which — despite its message — is the Phase 3 Strategy Analysis commit;
`26484d0` and `3290c61` are subsequent, unrelated Replay Viewer
presentation commits). `git status` was clean, two commits ahead of
`origin/v3.0-development`. No uncommitted Phase 3 work existed to protect,
so Phase 4 implementation proceeded directly, per this repository's commit
discipline (CLAUDE.md §11).

## 2. Audit findings accepted

This session continued a prior, already-complete audit rather than
re-running it. The accepted findings, verified against current source
before implementation:

* `evaluations list` discovery is intentionally cheap — one-level scan,
  one `evaluation.json` parse per run, no per-cell or `result.json`/
  `replay.jsonl` reads, no directory-size computation. A size column was
  explicitly excluded as out of scope.
* `evaluations show` already has `_print_experimental_conditions()`
  (`engine/src/battle_engine/evaluation_history/cli.py`), disclosing
  non-default arena size, action budget, kill weight, and (unconditionally)
  experimental locality reach — silent at defaults, silent when
  `effective_conditions` confidence is `UNKNOWN`. The GUI history/detail
  surface (`EvaluationHistoryDialog`) had no equivalent — a real parity gap.
* `evaluations compare` already has rich orientation/identity/denominator/
  gap/ambiguity/statistical disclosure. One GUI comparison state
  (`EvaluationComparisonDialog`'s ambiguous-duplicate-group detail) told the
  user to leave the GUI and run
  `bytefray agents evaluations show <id> --json` to locate a concrete
  `schedule_id`/`artifact_dir` — the only such escape hatch found.
* No supported evaluation-artifact delete/prune/archive/size-accounting
  capability exists anywhere in this layer, and none was added — see §11.
* `EvaluationHistoryDialog`'s existing actions were Refresh, Verify, Test in
  Agent Lab, Open Replay, Show Revision, Restore Revision Files, Compare
  With, Close — no folder-open action existed.
* `EvaluationSummary.effective_conditions` already exists on the model; the
  CLI already computes meaningful non-default disclosure from it; the GUI
  did not reuse that computation.

## 3. Discovery/performance findings

Preserved unchanged. None of Phase 4's additions touch the discovery/list
path (`evaluation_history/discovery.py`, `discover_evaluation_listing`):

* The effective-conditions disclosure (`effective_condition_lines`) reads
  only the already-in-memory `summary.effective_conditions` field of an
  `EvaluationSummary` that discovery/selection has already loaded — no new
  file read, and it only runs when a user selects one entry in the detail
  pane, never during list refresh.
* The "Open Evaluation Folder" action reads `entry.location.directory`
  (already known from discovery — the same field every existing per-cell
  replay/result lookup in this dialog already uses) and performs exactly
  one `Path.is_dir()` stat call, only when the button is shown/clicked —
  never during list refresh, never recursive.
* No directory-size column, no pagination, no new filtering, no recursive
  stat walk were added anywhere.

## 4. Effective-condition parity (P1)

**Implementation.** The CLI's interpretation of "non-default" was extracted
from `evaluation_history/cli.py::_print_experimental_conditions` into a new
pure function, `evaluation_history/models.py::effective_condition_lines(summary) -> list[str]`,
exported from `battle_engine.evaluation_history`. `_print_experimental_conditions`
now just prints each returned line (behavior byte-for-byte unchanged — the
existing `test_show_stays_silent_at_default_conditions`/
`test_show_discloses_non_default_conditions` regression tests in
`engine/tests/test_v3_phase0_evaluation_conditions.py` pass unmodified).
`app/services/evaluation_history_workflows.py::format_evaluation_summary_text`
(the function `EvaluationHistoryDialog`'s detail pane already calls) now
calls the same shared function and splices its lines in at the identical
position the CLI uses — immediately after the seeds/ticks line, before
lifecycle — so CLI and GUI can no longer drift into two definitions of
"non-default."

This directly satisfies the audit's explicit instruction to "reuse or
factor the existing CLI semantics so CLI and GUI cannot drift," rather than
re-implementing the interpretation a second time (the pattern this same
module's docstring already uses for `evaluations show`/`compare` in
general, but which risks silent divergence specifically for interpretive
logic like a default-value comparison).

**Behavior.** At default conditions, nothing is printed (verified: existing
history rendering is unchanged). At non-default conditions, the GUI now
shows the identical lines the CLI shows, e.g.:

```
arena size: 1024 (non-default) (recorded)
action budget/tick: 4 (non-default) (recorded)
kill weight: 9.0 (non-default) (recorded)
```

Locality reach (experimental bounded locality) uses the same shared
function and is therefore preserved without a second implementation.

## 5. Worker-count parity (P2)

**Audit confirmation.** `EvaluationRequest.workers: int = 1` is explicitly
documented as "[n]ever part of `_evaluation_id`'s hash payload: worker
count must never affect what an evaluation *means*, only how fast it
runs" (`engine/src/battle_engine/agent_evaluation.py`). The CLI's
`--workers` flag (default 1, `_positive_int`) dispatches a bounded pool of
long-lived worker subprocesses across independent `EvaluationCell`s and is
already documented as shipped, stable functionality (`docs/ROADMAP.md`,
v1.6 Phase 2). It is confirmed execution-only — safe to expose in the GUI
without any identity/reproducibility concern.

**Implementation.**

* `app/views/evaluation.py::EvaluationDialog` gained a `workersSpin`
  (`QSpinBox`, range 1–64, default 1) next to the existing Ticks field, and
  a `workers()` accessor. Not wired into the group-mode matrix preview
  refresh, since worker count cannot change the matrix.
* `app/services/designer_workflows.py::build_designer_evaluate_command`
  (pairwise path) and `build_designer_evaluation_plan`/
  `build_designer_evaluate_command_from_plan` (group path) gained a
  `workers` parameter, appending `--workers N` to the built argv only when
  `workers != 1` — an ordinary (serial) evaluation's command line is
  unchanged.
* `app/agent_designer.py::_on_evaluate`/`_build_evaluation_plan` thread
  `dialog.workers()` through to both paths, using the same defensive
  `getattr(dialog, "workers", None)` fallback the existing `mode` plumbing
  already uses — so a test double or any other caller predating this
  control still evaluates serially, not with an `AttributeError`.

**Identity verified unaffected.** A new engine-level test
(`test_group_plan_workers_default_omits_flag_and_never_affects_identity`)
confirms the same plan's `evaluation_id` and cell `schedule_id`s are
identical whether `workers=1` or `workers=4`.

## 6. Evaluation-folder access (P3)

**Audit.** The only cross-platform "open folder" mechanism used anywhere
in this codebase is the inline idiom
`QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))` — used in
`AgentDesigner._on_open_agent_folder`/`_on_open_output_folder`, and already
once inside `EvaluationHistoryDialog` itself (the Restore Files success
dialog's "Open Folder" button). There is no separate reusable helper
function anywhere to call into instead; every call site repeats the same
two-line idiom, so the new action follows that same convention rather than
introducing a new abstraction.

**Implementation.** `EvaluationHistoryDialog` gained an "Open Evaluation
Folder" button in the existing role-actions row (alongside "Show
Revision…"/"Compare With…"), enabled whenever a real evaluation entry is
selected and its directory (`entry.location.directory`) exists on disk —
deliberately independent of whether the evaluation's JSON parsed
successfully, since an unreadable `evaluation.json` is exactly when a user
most wants to inspect the raw directory. The handler
(`_on_open_evaluation_folder`) guards for a missing directory (a
`QMessageBox` warning, no exception) and otherwise calls
`QDesktopServices.openUrl(QUrl.fromLocalFile(...))` — no shell string
construction, no subprocess, no new mutation.

Tests mock `QDesktopServices.openUrl` rather than actually launching
Explorer, per the task's explicit requirement, and separately verify the
enabled/disabled state transitions.

## 7. Comparison-ambiguity disposition (P4)

**Investigation.** The one GUI path directing a user to
`bytefray agents evaluations show <id> --json` is
`EvaluationComparisonDialog._on_gap_selected`'s ambiguous-duplicate-group
branch. Investigation found the concrete `schedule_id`s were already
computed and present in `entry.label` (visible, truncated, in the gaps
list row) but were **not** reused in the detail-pane message — the message
only pointed the user at the CLI, discarding data already in hand.

**Smallest GUI-native fix applied.** The detail-pane message now leads with
`entry.label` (the full, untruncated, copyable `opponent=… seed=…
left_schedule_ids=[…] right_schedule_ids=[…]` text) before the explanatory
paragraph, and the CLI-escape-hatch sentence was replaced with guidance
that names the now-visible identifiers and the existing Cells-list
alternative. No pairing is ever guessed either way — this is a disclosure
improvement, not a resolution of the ambiguity. No comparison wizard, no
new architecture; `EvaluationComparisonDialog`'s existing structure is
otherwise unchanged. The pre-existing regression test asserting this
dialog's ambiguous-group behavior
(`test_evaluation_comparison_dialog_ambiguous_group_never_enables_actions`)
was updated to assert on the new, more useful message content.

## 8. Resume/interruption findings

**Null finding — resume already works, including from the GUI.** No
`--resume` CLI flag exists because none is needed: `EvaluationRequest.resume`
defaults to `True`, and `EvaluationService.run()` always loads prior
checkpointed state (`evaluation.json`) from the resolved output directory
when present, reconciling already-completed cells and only re-executing
the rest. Checkpointing happens every 16 newly-completed cells or every 1.0s
(whichever first), bounding the non-durable work lost to an ungraceful
crash. `--retry-failed` is a distinct, resume-adjacent flag controlling
whether previously *failed* cells are retried, not whether resume happens.

Critically, this already works identically from the GUI: when the
Designer's evaluate dialog is left at its default output placeholder,
`AgentDesigner._plan_default_evaluation_output` computes the exact same
content-addressed (evaluation-id-hashed) default directory a bare
`bytefray agents evaluate` invocation would use (confirmed by reading its
own docstring and call site). Re-invoking the identical evaluation from the
GUI after an interruption therefore lands in the same directory and resumes
exactly like the CLI does, with no user action beyond re-submitting the
same request.

**No infrastructure defect found**, so no resume-specific change was made,
per the task's explicit "if resume already works ... document the null
finding" instruction. One minor, non-blocking observation: neither the CLI
nor the GUI currently prints an explicit "N of M cells already completed"
message when a resume actually reuses prior work — a transparency nicety,
not a correctness or infrastructure gap, and out of scope for this phase's
priorities (P1–P5 do not include it).

## 9. Research-control disposition (P5)

**Evidence gathered.** `--arena-size`, `--instr-per-tick`, and
`--kill-weight` are `agents evaluate` CLI flags whose `--help` text already
cites the relevant v3 research reports
(`docs/V3_PHASE0_RESEARCH_BASELINE.md`,
`docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md`) and already states
they are "controlled experimental variable[s], not a Ruleset change."
`docs/V3_PHASE0_RESEARCH_BASELINE.md` §5's compatibility table confirms all
three are fully identity-bearing (hashed into `effective_conditions` /
`evaluation_id`) but not a Ruleset, Agent API, or schema change. No doc in
the repository (`COMPATIBILITY.md`, `ROADMAP.md`, or elsewhere) promises
these flags will be hidden, relocated, or removed from the product CLI —
the only place that stated such an objective was this phase's own,
not-yet-implemented entry in `V3_PRODUCT_SCOPE.md` §6, written before the
audit.

**Disposition: retained as advanced/experimental evaluation controls in the
CLI, unchanged, and intentionally not added to the ordinary GUI evaluation
workflow.** Rationale:

* Their `--help` text already correctly discloses research provenance and
  identity-bearing status — no misleading omission exists to fix.
* Moving or restructuring them (e.g. into a separate subcommand) risks the
  exact bit-for-bit reproducibility guarantee this phase's own governing
  scope explicitly protects, for no evidenced product benefit.
* Most GUI users do not need to *set* these before a run; P1's
  effective-conditions disclosure already ensures that if an evaluation
  *was* run with them non-default (however it was launched — GUI or CLI),
  the GUI now discloses that fact after the run, which is the concrete gap
  that mattered.
* `docs/V3_PRODUCT_SCOPE.md` §6 Phase 4 has been updated (this session) to
  record this disposition explicitly, superseding its original,
  audit-unsupported wording.

No `--help` text, default value, or CLI behavior for these three flags was
changed.

## 10. Reproducibility disclosure

Reviewed what a user currently sees in `EvaluationHistoryDialog`'s detail
pane (`format_evaluation_summary_text`): ruleset (`rules_compatibility_id`),
now-parity effective conditions (§4), methodology (orientation/arena
alignment mode via the shared `methodology_lines`), health, lifecycle,
runtime (created_at/finished_at), execution contexts, and agent-revision
provenance for candidate/baseline/opponents. This was already substantial
before Phase 4 (Phase 3 brought it to visual parity for evidence/behavior/
capture); Phase 4's addition is exactly the one concrete gap the audit
found — non-default conditions — not a new provenance dump.

**Exact-rerun command reconstruction was evaluated and rejected as a
candidate.** While `evaluation_id`, seeds, ticks, and (now) non-default
effective conditions are all individually visible, reliably reconstructing
a byte-identical `bytefray agents evaluate` invocation from a persisted
artifact alone is not always possible — e.g. candidate/baseline/opponent
*identity* (source, not just id) can differ from current local agent
source without the artifact recording enough to resolve which
historical source produced it (that is precisely what agent-revision
archival/verification exists to check, not reverse). Inventing a
"suggested rerun command" from partial information risked presenting a
plausible-looking but silently wrong command — exactly the "invent a
partial or misleading command" the task explicitly forbids. No rerun-command
feature was added; this is recorded as a deliberate non-finding rather than
an unstated gap.

## 11. Explicitly rejected/deferred infrastructure

Per the audit's explicit findings and this phase's non-goals, the following
were **not** built, and remain deferred rather than rejected outright
should real evidence later justify them:

* Evaluation artifact delete/prune/archive of any kind.
* Any filesystem-size accounting for an evaluation directory (would require
  a new recursive stat walk, changing discovery's cost profile — the audit
  explicitly excludes this).
* A directory-size column in `evaluations list` or its GUI equivalent.
* Listing pagination, and date/agent/status filtering (no scale evidence
  presented).
* An evaluation database/index, or migration away from filesystem
  artifacts.
* A general comparison-ambiguity "wizard" (P4 stayed a minimal disclosure
  fix).
* A "suggested rerun command" feature (§10).
* Any change to `V3_PRODUCT_SCOPE.md` §6 Phase 4's original list/prune/
  archive wording beyond recording that it was not pursued and why.

## 12. GUI evidence

Captured under
[docs/screenshots/v3-phase4-evaluation-infrastructure/](../../screenshots/v3-phase4-evaluation-infrastructure/)
against real evaluation artifacts (not mocked), via a script that launches
the actual `EvaluationHistoryDialog`, `EvaluationDialog`, and
`EvaluationComparisonDialog` classes with the native Qt/Windows platform
(not the offscreen platform, which rendered illegible placeholder glyphs on
this machine) and grabs each to a PNG:

* `history-default-conditions.png` — an ordinary evaluation's detail pane;
  no arena/action-budget/kill-weight lines present, confirming unchanged
  rendering at defaults.
* `history-nondefault-conditions-open-folder.png` — the same view for a
  `arena_size=1024, instr_per_tick=4, kill_weight=9.0` evaluation, showing
  all three non-default disclosure lines and the new, enabled "Open
  Evaluation Folder" button.
* `evaluate-dialog-workers-control.png` — the evaluate-launch dialog with
  the new "Workers" spin box set to 4, directly under Ticks.
* `comparison-ambiguous-detail.png` — a real ambiguous-duplicate-group
  comparison (duplicated seed under a changed condition), showing the
  improved detail-pane text with concrete `left_schedule_ids`/
  `right_schedule_ids` and the revised guidance.

## 13. Tests/validation

* `engine/tests/test_evaluation_history_workflows.py`: three new tests —
  default conditions hidden, non-default conditions disclosed (ordering
  verified against `ticks:`/`lifecycle:`), and confidence-`UNKNOWN`/
  `RECOVERED` v1-legacy silence.
* `engine/tests/test_beta3_group_designer_workflows.py`: one new test —
  `--workers` omitted at default, present and correctly valued when
  non-default, and `evaluation_id`/`schedule_id`s unchanged either way.
* `tests/test_agent_evaluation_dialog.py`: two new `gui`-marked tests —
  the `workersSpin` default/accessor, and the Designer's pairwise-path
  `--workers` argv emission (only when non-default), mirroring the existing
  `--single-orientation` precedent test.
* `tests/test_agent_evaluation_history_dialog.py`: three new `gui`-marked
  tests — non-default disclosure end-to-end through the real dialog, the
  Open-Folder button's enabled/disabled transitions with a mocked
  `QDesktopServices.openUrl`, and the disabled-with-no-selection case; one
  existing test's assertions updated for the new ambiguous-comparison
  message (§7).
* Ran and passing: the focused suites above; the full default suite
  (`python -m pytest`, `_legacy/tests` + `engine/tests` + `client/tests`,
  `-m "not gui"`); the full GUI suite explicitly
  (`pytest tests/... -m gui`, 63 tests, all passing); `ruff check .`;
  `mypy engine/src/battle_engine` and `mypy client/src/battle_client`
  (both clean).
* One unrelated transient failure was observed on a shared, non-isolated
  `.pytest-tmp` run (`test_bare_agents_create_and_validate_are_unaffected`,
  a bare-agent CLI subprocess test touching nothing this phase changed) —
  confirmed to be a collision from a concurrent session sharing this
  machine's repo-local temp directory (multiple other Claude Code sessions
  were active against this same working tree during this run), not a
  regression: it passes cleanly in isolation with a dedicated `--basetemp`,
  and a full-suite rerun with an isolated `--basetemp` was clean.

## 14. Compatibility impact

None. No evaluation identity, schema, Ruleset, or Agent API change. No
default value changed for any existing flag. `effective_condition_lines`
is a pure extraction of already-shipped CLI logic (verified byte-identical
CLI output via untouched existing regression tests); the GUI-only additions
(`workers` spin box, Open Folder button, comparison message wording) are
additive UI, not persisted-artifact or wire-format changes.

## 15. Verdict

**EVALUATION WORKFLOW IMPROVED — PHASE 4 COMPLETE**
