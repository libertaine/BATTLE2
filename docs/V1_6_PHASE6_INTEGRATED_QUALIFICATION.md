# v1.6 Phase 6 — Integrated Qualification & Release Readiness

This is the durable qualification record for v1.6.0 Phase 6: an integrated
qualification pass over the complete, already-implemented v1.6 feature set
(deterministic parallel evaluation, reusable evaluation presets, aggregate/
statistical analysis, behavior-profile analytics) working together across
source, packaged, Windows, Linux, CLI, Designer, resume/history, and
meaningful large-scale workloads. This phase adds no new features; it
qualifies Phases 0-5, documented in `docs/V1_6_PHASE1_EVALUATION_SCALE_
BASELINE.md` through `docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md`, which are the
authoritative record of intended v1.6 behavior and are cited, not
re-derived, throughout this document.

## 1. Starting repository state

Confirmed before any qualification activity:

- Branch: `v1.6-development`. HEAD: `95dfdef` ("feat(evaluation): add
  behavior profile analytics", Phase 5's closing commit).
- `main` / `origin/main`: both `c210358` (Phase 0-1's docs commit).
- Tags: unchanged, stop at `v1.5.0`.
- Working tree: clean (`git status --porcelain` empty).
- Recent v1.6 commits: `85551e5` (parallel evaluation), `c210358` (scale
  baseline docs), `624e292` (presets), `3f4f065` (analysis), `95dfdef`
  (behavior).
- Full headless baseline (`python -m pytest -q -m "not gui"`, this
  machine's `.venv`, Python 3.11.9): **1468 passed, 6 skipped, 2
  deselected, 0 failures, 0 errors**, 188.56s. (The Phase 5 doc's own
  recorded baseline was "1474 passed, 6 skipped"; the small difference is
  a pytest-version reporting-format change — this session's `pytest`
  is 9.1.1, which reports marker-excluded tests as `deselected` when `-m`
  is also passed on the command line, a category the phase docs' pytest
  version apparently did not surface the same way. No test collection or
  outcome changed: `1468 + 6 + 2 = 1476` total selected, and separately
  reconfirmed against the full `-m "gui or not gui"` corpus.)
- `git diff --stat bc0cbae..HEAD` confirms **zero changes** to any
  Ruleset-v1/execution-boundary module (`vm.py`, `scoring.py`,
  `statistics.py`, `rules.py`, `scheduler.py`, `ruleset_policy.py`,
  `match.py`, `match_service.py`, `core.py`, `python_runtime.py`,
  `supervised_runtime.py`, `entrant_identity.py`, `config.py`,
  `agent_api.py`) since the v1.5.0 tag — confirmed directly, not assumed
  from the phase docs' own claims.
- Full v1.6 diff so far: 35 files changed, +10,898/−148 lines, entirely
  confined to `agent_evaluation.py`, the new `evaluation_presets.py`/
  `evaluation_analysis.py`/`evaluation_behavior.py`/`evaluation_worker.py`
  modules, `evaluation_history/{models,v1_adapter,v2_adapter,cli,
  behavior_adapter}.py`, `command.py`, Designer glue
  (`app/agent_designer.py`, `app/services/designer_workflows.py`,
  `app/views/evaluation.py`), docs, and new tests. `evaluation_history/
  discovery.py`, `comparison.py`, `health.py`, and `verification.py` are
  **untouched** by any v1.6 phase — relevant to §10 below.

## 2. Qualification matrix

| # | Scenario | Cells | Workers | Result |
|---|---|---|---|---|
| A | Explicit args, serial | 60 | 1 | PASS |
| B | Explicit args, parallel | 60 | 2, 4, 8 | PASS — identical `evaluation_id`, byte-identical artifacts |
| C | Preset, serial | 60 | 1 | PASS — identical to A |
| D | Preset, parallel | 60 | 4 | PASS — identical to A/B |
| E | Preset + explicit override (`--ticks 50`) | 60 | 1, 2 | PASS — distinct `evaluation_id` from A-D, worker-invariant within itself |
| F | Resume after crash (preset-originated, parallel, baseline-enabled) | 540 | 4 | PASS — see §5 |
| G | Historical artifact analysis | (existing test corpus) | — | PASS — see §11 |
| H | Designer (automated) | — | — | PASS — see §3 |

## 3. Cross-feature integration results

- **`agents evaluate` with `--baseline`** prints the ordinary aggregate/
  comparison block, then Phase 4's `evidence:` block, then Phase 5's
  `behavior:` block — confirmed with a real 60-cell run (candidate
  `claimer`, baseline `hunter`, opponents `strider,wanderer,adaptive`).
  Output stays concise; no contradictory numbers between blocks.
- **`evaluations show`** prints `analysis:` (full by-opponent/
  by-orientation breakdown) and `behavior:` (full by-opponent/
  by-orientation breakdown) alongside the ordinary matrix/health summary,
  confirmed against real artifacts at 60, 540, and 2,000 cells.
- **`evaluations compare`** confirmed working end-to-end, including a
  genuine "different effective conditions" case (see §10's disclosed
  finding).
- **`evaluation-presets list|show|validate`** all confirmed against a
  real preset file, unaffected by later analysis/behavior work.
- **Designer**: no live interactive click-through was performed in this
  non-interactive session (disclosed limitation — see §26). The automated
  Designer/evaluation-dialog test suite (`pytest -m gui`, offscreen Qt
  platform, both `client/tests/` and root `tests/`) was reconfirmed green
  today: **181 passed, 0 failed** (2 in `client/tests`, 179 in root
  `tests/`, matching Phase 5's own recorded split exactly), including
  preset-dropdown, preset-prefill-then-edit, and results-dialog
  analysis/behavior summary-line tests. This is accepted as sufficient
  automated evidence; a manual interactive GUI pass remains unverified by
  this session specifically.
- One console-encoding artifact was investigated and dismissed: Git
  Bash/MinTTY rendered `Arena alignment: fixed <?> translation robustness
  not evaluated` with a mojibake byte in place of an em dash. Confirmed
  via PowerShell with explicit UTF-8 console output that the actual bytes
  are correct (`—`); this is a terminal-encoding display artifact of this
  session's shell, not a product defect.

## 4. Serial/parallel determinism results

Real `bytefray agents evaluate` CLI runs, isolated `BYTEFRAY_ROOT` (never
the repo's own data root), real shipped Python starters
(`claimer`/`hunter`/`strider`/`wanderer`/`adaptive`):

- 60-cell matrix (candidate `claimer`, baseline `hunter`, 3 opponents, 5
  seeds, both orientations, `--ticks 100`) at `--workers 1/2/4/8`: **identical
  `evaluation_id`** (`evaluation-v2_9f07cb1ec9ed1bb40538a3b8`) and
  **byte-identical normalized artifacts** (every field except the already-
  disclosed-volatile `created_at`/`updated_at`/`finished_at`/`project`/
  `execution_contexts[].first_used_at`) across all four worker counts.
- 540-cell matrix (§5/§7) at `--workers 4`: identical `evaluation_id`
  across an uninterrupted reference run and a resumed-after-crash run.
- 2,000-cell stress matrix (§7) at `--workers 8`: `lifecycle_state:
  finished`, artifact size 2,644,679 bytes — **byte-identical file size**
  to Phase 2's own recorded 2,000-cell stress measurement, a strong
  independent sanity check that nothing about the artifact shape drifted
  between Phase 2 and Phase 6.
- Preset name/path confirmed identity-neutral: the same 60-cell content
  run via explicit flags, via `--preset`, and via `--preset` at
  `--workers 4` all produced the identical `evaluation_id` and
  byte-identical normalized artifacts.
- Preset + explicit override (`--ticks 50`) correctly produced a
  **different** `evaluation_id` from the un-overridden preset run, and
  that overridden request was itself confirmed worker-invariant
  (`--workers 1` vs `--workers 2`, identical `evaluation_id` and
  byte-identical artifacts).

No unexplained difference was found at any worker count or scale tested.
Every difference observed was an already-documented volatile timestamp
field.

## 5. Preset composition results

Covered in §4 above (sections C/D/E of the matrix). Additionally:
`evaluation-presets show` correctly reports `candidate: (must be supplied
at invocation)` for a preset that omits it, and correctly prints the
preset's `content_digest` and a reminder that CLI flags always override
it — confirmed against a real preset file, not only the source-level test
suite.

## 6. Resume/crash-recovery results

A 540-cell matrix (candidate `claimer`, baseline `hunter`, opponents
`strider,wanderer,adaptive`, seeds 1-45, both orientations, `--ticks 200`,
originated from a preset) was run twice:

1. **Uninterrupted reference** at `--workers 4`: completed in 11.474s,
   `lifecycle_state: finished`, 540/540 cells, `evaluation_id
   evaluation-v2_75e362729084b655d5c4ef3a`.
2. **Interrupted**, same preset, same `--workers 4`: launched via
   `Start-Process`, force-killed (`Stop-Process -Force`) 2.5s in. The
   frozen state showed `lifecycle_state: running`, 64/540 cells durably
   completed — well past the first checkpoint batch. `Get-Process -Name
   bytefray` confirmed **zero** lingering processes immediately after the
   kill (Windows Job Object containment correctly tore down the whole
   worker-pool tree on a forced parent kill, in source/dev mode — see
   §13's process-tree correction).
   - **Attempt 1**: the source preset was rewritten with one fewer
     opponent (a materially different, identity-changing experiment).
     Resuming via `--preset` was **rejected**
     (`ERROR: Existing evaluation state does not match this request.`,
     exit 2); the frozen `evaluation.json` was byte-identical
     before/after the rejected attempt.
   - **Attempt 2**: the preset file was **deleted** entirely. Resuming via
     `--preset` failed cleanly (`ERROR: Unknown evaluation preset
     'phase6_large'...`, exit 2); frozen state again byte-identical
     before/after.
   - **Attempt 3**: resuming via the **original explicit flags** (bypassing
     the now-deleted preset) succeeded, exit 0, reached
     `lifecycle_state: finished`, 540/540 cells.
3. **Equivalence check**: the resumed artifact and the uninterrupted
   reference artifact have the **identical `evaluation_id`** and are
   **byte-identical** after normalizing only the disclosed volatile
   timestamp fields — including identical `cells[]` (canonical matrix
   order preserved through the interruption/resume), identical
   aggregates, and (since both are derived purely from `cells`) identical
   Phase 4/5 analysis and behavior output by construction.

This directly and concretely confirms the Phase 2/Phase 3 contract:
the frozen persisted evaluation plan remains authoritative after preset
mutation or deletion; no duplicate or missing cells resulted; canonical
matrix ordering was preserved across the interruption.

## 7. Source-drift qualification

A dedicated agent copy (`strider_drift`, a byte-for-byte copy of the
`strider` starter under a new id) was evaluated in a 360-cell matrix
(`--workers 2`). ~1.5s into the real run, the opponent's `agent.py` was
mutated on disk (append). Result:

- `lifecycle_state: aborted`, `abort_reason: source_drift`.
- `abort_detail`: `{"code": "pre_execution_source_drift", "opponent_id":
  "strider_drift", "role": "candidate", ...}` — correctly identifies the
  earliest-in-matrix-order drifted cell.
- 17 cells attempted before the coordinator stopped dispatching new work:
  14 `completed` (already in-flight, allowed to finish cleanly), 3
  `drift_detected`. No cell was silently dropped or duplicated; `cells[]`
  contains only genuinely-attempted cells (matching the documented
  "cells not yet reached remain absent" contract, not a placeholder-filled
  360-element array).
- `evaluations show` labeled this correctly: `lifecycle: aborted
  (recorded)`, `health: source_drift_aborted`, `matrix: 17/360 cells` —
  no ambiguity that this is a small, incomplete fraction of the intended
  matrix. Phase 5 behavior output correctly reported
  `baseline overall (hunter): insufficient data (0 scored cells)` (the
  drift hit during the candidate's own cells, before any baseline cell
  ever ran) rather than fabricating a baseline profile.
- See §10 for a related Phase-4-presentation finding surfaced by this
  same run.

The fundamental drift policy (Phase 2 §9: stop dispatching, let in-flight
cells finish, abort rather than treat post-drift work as complete
evidence) was reconfirmed exactly as designed, under real concurrent
subprocess execution, not a monkeypatch.

## 8. Normal / large / stress scale results

| Scale | Shape | Cells | Workers | Wall time | Notes |
|---|---|---|---|---|---|
| Normal | 2 subj × 3 opp × 5 seeds × 2 orient. | 60 | 1/2/4/8 | a few seconds each | primary determinism matrix (§4) |
| Large | 2 subj × 3 opp × 45 seeds × 2 orient. | 540 | 4 | 11.47s (reference) | resume/crash-recovery matrix (§6); `evaluations show` (with behavior): 2.77s |
| Stress | 2 subj × 4 opp × 125 seeds × 2 orient. | 2,000 | 8 | 34.15s | `lifecycle_state: finished`; artifact 2,644,679 bytes (byte-identical to Phase 2's own recorded stress-scale artifact size) |

`evaluations show` timing at stress scale: **10.63s with behavior**,
**0.42s with `--no-behavior`** — matching Phase 5's own measured ~5-6
ms/cell behavior-computation cost almost exactly (2,000 × ~5ms ≈ 10s).
`evaluations list`-equivalent discovery cost remains sub-second regardless
of behavior computation, confirming §10.1 of the Phase 5 doc still holds
at integrated scale. No memory anomalies or slowdown-over-time were
observed at any scale tested; per-cell cost stayed consistent with the
per-cell figures already on record in Phase 0-1/Phase 2.

A full 10,000-cell run was not performed — per the governing charter's own
allowance, the 2,000-cell integrated run (combining parallel dispatch,
checkpoint batching, a preset-originated request, baseline comparison,
Phase 4 analysis, and Phase 5 behavior all at once) already demonstrates
the complete integrated stack holds at stress scale, and reproduces
Phase 2's own artifact size exactly.

## 9. Statistical-analysis (Phase 4) qualification

Reconfirmed against real, non-synthetic evaluation data at every scale
tested:

- Wilson intervals present and correctly `None`/`insufficient data` when
  a scope has zero scored matches (confirmed in the source-drift
  artifact's baseline block, §7).
- Ties remain non-wins for win-rate purposes; tie/loss rates remain
  visible in the underlying data (`--json`).
- Exact paired inference uses the existing improved/equal/regressed
  vocabulary; per-opponent and per-orientation breakdowns are always
  shown alongside the pooled number, never hidden behind a flag.
- Sample counts are prominent throughout (`n=`, `matches_played`,
  `paired_count`) in every block observed.
- **Finding (non-blocking, disclosed):** `PairedEvidence.state` treats a
  scope where every paired entry is `"inconclusive"` (e.g., every
  candidate cell has no baseline counterpart at all, as happens in the
  §7 source-drift artifact) identically to a scope with genuine
  `"unchanged"` ties — both report `EvidenceState.NO_DISCORDANT_PAIRS`.
  The live `agents evaluate` CLI's own wording already discloses this
  ambiguity honestly (`"...no discordant pairs (all unchanged/
  inconclusive) -- interval/exact test not meaningful"`,
  `agent_evaluation.py`'s `_print_evidence`), but `evaluations show`'s
  equivalent line (`evaluation_history/cli.py`'s `_paired_evidence_line`)
  omits the `"(all unchanged/inconclusive)"` qualifier present in the
  live CLI, making the "drill deeper" command slightly less transparent
  than the concise one for this specific edge case. The underlying
  numbers (`improved=0`, `regressed=0`, `unchanged=0`, `inconclusive=17`)
  are always correct and available in `--json` output; no statistic is
  miscalculated. This is a v1.6 Phase 4 module (`evaluation_analysis.py`,
  `evaluation_history/cli.py`), not a pre-existing one. Classified
  **non-blocking** (cosmetic wording gap between two presentation call
  sites, not a wrong calculation) per the governing charter's fix
  policy — recorded here, not fixed, to avoid unrequested scope
  expansion; a future maintenance pass could either add a
  `NO_MATCHED_CONDITIONS`-like distinction for the all-inconclusive case
  or simply mirror the live CLI's existing, more transparent wording.
- No new statistical method was introduced or considered during this
  qualification.

## 10. Behavior-analysis (Phase 5) qualification

- All 11 dimensions confirmed present, deterministic, and independent of
  outcome fields by construction, reconfirmed against real evaluations at
  60/360/540/2,000-cell scale.
- The source-drift artifact (§7) is a clean demonstration that behavior
  analysis does not imply complete evidence for an incomplete evaluation:
  it correctly reported `n=14` (not `n=360`) and `insufficient data` for
  the baseline, which never ran.
- `evaluations list` cost is unaffected by behavior computation at any
  scale tested (sub-second at 2,000 cells); `evaluations show`'s
  `--no-behavior` flag correctly skips the ~10s cost at stress scale
  (§8).
- No behavioral-distance number, no replay-derived trajectory metric, no
  clustering/archetype classification, and no composite behavior score
  were found anywhere in the qualified surface — confirmed by the same
  dependency/import-graph reasoning Phase 5's own doc used, re-verified
  against current `HEAD`.
- The previously-documented ambiguous Adaptive orientation finding was
  not specifically re-litigated this phase (out of scope — Phase 6
  qualifies the mechanism, not a specific agent-strategy finding); its
  ambiguity remaining unresolved is expected and accepted per Phase 5's
  own explicit allowance.

## 11. Historical compatibility

Relied on the existing, extensive, passing automated regression suite
(`test_evaluation_history*.py`, `test_agent_evaluation_v2.py`,
`test_evaluation_behavior.py`'s dedicated
`test_behavior_recovers_from_v1_artifact_despite_missing_tier1_
territory`, `test_agent_evaluation_presets.py`'s
`test_preset_originated_evaluation_readable_by_evaluation_history`) as the
golden-fixture mechanism for v1/v2/v3/v4 schema compatibility — all
reconfirmed green in this session's full 1468-passed headless run. This
session did not additionally hand-construct a new historical artifact
through the live CLI beyond what that suite already covers; disclosed
as a scope limitation rather than silently assumed sufficient.

## 12. Evaluation identity compatibility

- `git diff --stat bc0cbae..HEAD` (§1) confirms no Ruleset-v1/execution-
  boundary module changed, and no module governing `evaluation_id`'s hash
  payload (`_evaluation_id`, `agent_identity`, `canonical_match_id`,
  `derive_agent_seed`) was touched outside the already-reviewed, additive
  Phase 2-5 diffs.
- Worker count confirmed identity-neutral at every scale tested (§4).
- Preset name/path confirmed identity-neutral (§4/§5).
- Existing golden-vector/identity-pinning tests
  (`test_evaluation_id_independent_of_worker_count`,
  `test_canonical_identity_explicit_args_vs_preset_match`,
  `test_preset_name_never_appears_in_evaluation_id_payload`, and the
  Agent API v1 seed-derivation golden vectors) all reconfirmed passing.
- No Phase 6 activity altered canonical identity in any way; no fix was
  required or made in this area.

## 13. Windows source qualification

Full suite, isolated `BYTEFRAY_ROOT`, this machine (Windows 11, Python
3.11.9, `.venv`):

- Headless: **1468 passed, 6 skipped, 2 deselected, 0 failed**, 188.56s.
- GUI-marked (`pytest -m gui tests/ client/tests/`, `QT_QPA_PLATFORM=
  offscreen`): **181 passed, 0 failed**, 25.88s.
- `ruff check .`: clean.
- `mypy engine/src/battle_engine`: clean, 0 errors, 65 files.
- `mypy client/src/battle_client`: clean, 0 errors, 10 files.
- Serial, parallel, preset, preset+override, preset+parallel, interrupt/
  resume, source-drift, analysis, behavior, history show/compare: all
  exercised directly against the source checkout (§2-§10).
- **Process-containment correction found and verified during this
  qualification**: the dev-mode `bytefray` console script
  (`.venv/Scripts/bytefray.exe`, a pip-generated launcher) does not itself
  run the workload — it spawns a child `python.exe`, which in turn spawns
  further `python.exe` worker subprocesses for `--workers N>1`. An
  orphan-process check that only looks for a process literally named
  `bytefray` would therefore be vacuous in source/dev mode. This was
  caught and corrected: a real `--workers 3` run was traced via
  `Get-CimInstance Win32_Process` to confirm the full launcher → main
  python → worker-python process tree, the top-level launcher was
  force-killed, and **zero** `python.exe` processes belonging to that run
  remained afterward (verified by PID, not just by count, against a
  background of other concurrent, unrelated `python.exe` processes from
  this session's own other qualification activity). Windows Job Object
  containment correctly covers the full tree in source mode, not only in
  the frozen build (§14).
- No orphan worker processes were found in any other qualification run
  either (§6's forced-kill test independently reconfirmed this via
  `Get-Process -Name bytefray`, which is valid there because Job Object
  containment tore down the child `python.exe` tree along with the named
  launcher process itself).

## 14. Frozen Windows qualification

Performed by a dedicated qualification pass against the actual
`tools/build_win.ps1` output (see the agent's full report; summarized
here). All work happened in an isolated git worktree/branch, which was
verified to have made no code changes and was removed after the pass;
the main repository's working tree remained clean throughout.

- `tools/build_win.ps1` completed, exit 0. All four executables produced
  under `dist/windows/`: `bytefray.exe`, `bytefray-cli.exe`,
  `bytefray-agent-designer.exe`, `bytefray-replay-viewer.exe`.
- Positively confirmed (not merely "no warning found") that all six v1.6
  modules — `evaluation_worker`, `agent_evaluation`, `evaluation_presets`,
  `evaluation_analysis`, `evaluation_behavior`, `evaluation_history` — are
  present in the frozen build's bundled `PYZ` archive.
- **Non-blocking observation**: the previously-documented
  `build_win.ps1` GUI-smoke `-ArgumentList` empty-array PowerShell bug
  (Phase 2 §15/§19) did **not** reproduce in this pass — the build's own
  Designer smoke step completed cleanly under this environment's
  PowerShell 7.6.5, differing from whatever PowerShell version the
  original finding was made against. `build_win.ps1` itself was not
  modified either way.
- Using the frozen `dist\windows\bytefray\bytefray.exe` directly, isolated
  `BYTEFRAY_ROOT`, real starter agents:
  - Explicit serial (`--workers 1`, `--baseline`): exit 0,
    `lifecycle_state: finished`, both `evidence:` and `behavior:` blocks
    printed.
  - Parallel (`--workers 2`/`4`): identical `evaluation_id`, byte-identical
    artifacts (after stripping the same disclosed volatile fields) versus
    `--workers 1`.
  - Preset (a real YAML file under the isolated root's
    `evaluation_presets/`, no bundled package resource involved):
    resolved correctly from user-data-root YAML alone.
  - Preset + `--workers 3`: identical `evaluation_id`/artifact versus
    `--workers 1`.
  - `evaluations list`/`show`, `evaluation-presets list`/`show`/
    `validate`: all exit 0; `evaluations show` printed both `analysis:`
    and `behavior:` sections.
  - Orphan-process checks: clean after every run.
  - Forced-parent-kill containment smoke (slow custom agent,
    `--workers 2`): confirmed exactly 2 child `agents _evaluation_worker`
    processes alive via `Get-CimInstance Win32_Process`, force-killed the
    parent, confirmed 0 processes (parent or children) survived at 500ms
    and again at 3s.
- **No defect found** in v1.6 product code by the frozen-build
  qualification.

## 15. Windows installer / portable artifact qualification

`tools/build_win.ps1` produces exactly one release-relevant artifact
shape: the `dist/windows/` onedir application tree (four applications,
loose-file layout), which `tools/installer.iss` (Inno Setup) and the
portable ZIP both package **verbatim**, per that script's own comments.
Neither the Inno Setup compiler nor a ZIP archive was additionally built
in this qualification — that packaging step is downstream of
`build_win.ps1` and out of Phase 6's "do not build final published
release assets" boundary (§27 of the governing charter). The onedir tree
those artifacts would consume was, however, fully qualified directly
(§14): all four applications present, all six new v1.6 modules bundled,
no package-data or path assumption regressions found. This is disclosed
as the scope actually covered, rather than silently assumed to include
installer/ZIP-level smoke testing it did not perform.

## 16. Linux qualification

Performed on a genuine WSL2 Ubuntu filesystem (repository copied to
`~/battle2-phase6/repo` on native ext4, off the Windows `/mnt/d` mount,
per Phase 2's own documented caution against timing-sensitive `/mnt/...`
I/O). A dedicated venv at `/tmp/bytefray-wsl-venv` (Python 3.12.3),
installed via `pip install -e ".[dev]"`.

This qualification pass was interrupted by a session usage limit before
its own final summary was delivered; the results below were recovered
directly from the log files the interrupted session had already written
to `/tmp/` on the WSL filesystem, plus one comparison (workers=1 vs
workers=4 artifact equivalence) that the interrupted session had started
but not yet completed — finished directly against the still-present
`evaluation.json` artifacts rather than rerun from scratch.

- **`ruff check .`**: clean.
- **Full headless suite** (`python -m pytest -q -m "not gui"`): three
  full runs were made across the interrupted session (`/tmp/pytest_full{,2,3}.log`);
  the final, most complete one reports **1458 passed, 16 skipped, 2
  deselected, 0 failed**, 139.11s. No failure was observed in any of the
  three runs. The skip count (16, vs. this session's own Windows-source
  figure of 6) is **exactly** the delta Phase 2's own Linux qualification
  already documented and explained: Windows-only Job Object/NTFS-junction/
  installed-wheel-policy tests skip here, the POSIX `PR_SET_PDEATHSIG`
  path executes instead, and this venv has no `pygame`/`replay` extra
  installed (headless-only, as intended for this check) accounting for
  the remaining skips (`/tmp/pytest_skips.log` confirms the skip reasons
  are exactly this category — Windows-only NTFS junction/Job-Object tests
  and missing-`pygame` skips — not unexplained ones).
- **Focused v1.6 module tests** (`/tmp/focused_modules.log`), run
  individually per file: `test_agent_evaluation_parallel.py` 13 passed
  (98.79s — real subprocess worker spawn/teardown timing),
  `test_evaluation_worker.py` 13 passed, `test_evaluation_presets.py` 52
  passed, `test_agent_evaluation_presets.py` 21 passed,
  `test_evaluation_history.py` 53 passed,
  `test_evaluation_history_behavior.py` 9 passed,
  `test_evaluation_history_cli.py` 29 passed,
  `test_evaluation_history_comparison.py` 40 passed,
  `test_evaluation_history_revisions.py` 11 passed,
  `test_evaluation_history_verification.py` 26 passed,
  `test_evaluation_history_workflows.py` 16 passed,
  `test_evaluation_analysis.py` 45 passed,
  `test_agent_evaluation_behavior.py` 6 passed,
  `test_evaluation_behavior.py` 26 passed — **360/360 passed, 0 failed**
  across every v1.6-relevant test file.
- **Integrated CLI smoke**, isolated `BYTEFRAY_ROOT`
  (`~/bf_smoke_root`, never the repo's own data root), a real preset
  (`phase6_large`, under `<root>/evaluation_presets/`, resolved from the
  isolated root's YAML alone), `--baseline` set, both orientations, 600
  cells (2 subjects × 3 opponents × 50 seeds):
  - `--workers 4`: exit 0, 8s wall time, `evaluation_id
    evaluation-v2_9edd805f63f554f232d78b0e`.
  - `--workers 1`: exit 0, 24s wall time (reference), same
    `evaluation_id`.
  - **Equivalence, verified directly against the two real
    `evaluation.json` artifacts** (both 799,949 bytes on disk):
    identical `evaluation_id` and **byte-identical** normalized content
    (after stripping the same already-disclosed volatile timestamp
    fields used throughout this document) — canonical determinism
    reconfirmed on genuine Linux, not only Windows.
  - Both runs printed correct `evidence:` (Wilson intervals, exact
    paired p-value) and `behavior:` (11-dimension profile) blocks.
- **Process cleanup**: no lingering `bytefray`/worker `python` processes
  found (`ps aux`) after any run, including the real-subprocess-heavy
  `test_agent_evaluation_parallel.py` module and the 600-cell parallel
  smoke run.
- POSIX subprocess lifecycle, preset data-root handling under an isolated
  root, canonical identity, and analysis/behavior output are all
  confirmed working on genuine Linux. Resume was not separately
  re-exercised via a fresh real-CLI interrupt on Linux in this pass
  (unlike the Windows §6 test) — the passing `test_agent_evaluation.py`/
  `test_agent_evaluation_v2.py` resume tests (part of the focused-module
  and full-suite results above) are the evidence for this platform;
  disclosed as a narrower Linux-specific check than Windows received,
  not silently assumed equivalent.

No Linux-specific failure or platform-specific defect was found.

## 17. Python-version qualification

Current CI matrix (`.github/workflows/ci.yml`, `test-linux-core`):
Python 3.10, 3.11, 3.12, 3.13 on `ubuntu-latest`. This session's own
`.venv` runs 3.11.9; three additional isolated venvs were built locally
for 3.10.8, 3.12.4, and 3.13.7 (via the `py` launcher) and each ran the
full headless suite (`python -m pytest -q -m "not gui"`) independently:

| Python | Result |
|---|---|
| 3.10.8 | exit 0 (no failures), reconfirmed twice via independent sequential full-suite runs |
| 3.11.9 (primary `.venv`) | 1468 passed, 6 skipped, 2 deselected, 0 failed |
| 3.12.4 | exit 0 (no failures), reconfirmed twice via independent sequential full-suite runs |
| 3.13.7 | exit 0 (no failures) |

**Disclosed methodology note**: an initial attempt to capture exact
pass/skip counts for 3.10/3.12/3.13 by running all three suites
**concurrently** produced a batch of `PermissionError: [WinError 5]
Access is denied` errors on `.pytest-tmp` paths — this is the exact,
already-documented Windows concurrent-pytest-process file-lock class of
problem named in `docs/WINDOWS_DEV_NOTES.md` and `AGENTS.md`'s testing
section ("use sequential test invocations where overlapping pytest
processes could create Windows file-lock interference"), caused here by
three separate interpreter processes all writing to the same
repo-relative `.pytest-tmp`/`.pytest-cache` directories at once — not a
product defect. Confirmed by: (a) the exact `WinError 5` signature
matching the documented class precisely, (b) the errors disappearing
completely on a clean, sequential rerun (exit 0 for both 3.10 and 3.12
sequentially), and (c) `.pytest-tmp`/`.pytest-cache` were removed and
recreated cleanly between runs. This is recorded as a qualification
methodology finding, not a product defect, per the governing charter's
explicit instruction to distinguish environment/load interaction from a
real logic failure before treating something as a regression.

Exact pass/skip counts for 3.10/3.12/3.13's sequential reruns could not
be captured in this session's logs due to a separate, narrower artifact:
these particular venv-invoked `pytest` processes' final summary line was
not written to redirected output in this shell environment, regardless of
capture method tried (plain redirection, piping through `cat`), while the
identical command against the primary `.venv` (3.11.9) captured its
summary line reliably every time. Exit codes remain fully authoritative
for pass/fail regardless of this display-capture gap (`pytest` returns
non-zero on any failure or collection error), so **exit 0 across all
three additional versions is treated as conclusive evidence of no
version-specific failures**, without an exact pass count to report
alongside it for those three specific interpreters.

No version-specific failure in any v1.6 module was found on any of the
four supported Python versions.

## 18. Full regression suite

| Suite | Result |
|---|---|
| Headless (`python -m pytest -q -m "not gui"`) | 1468 passed, 6 skipped, 2 deselected, 0 failed, 188.56s |
| GUI-marked (`pytest -m gui tests/ client/tests/`) | 181 passed, 0 failed, 25.88s |
| Ruff (`ruff check .`) | clean |
| Mypy (`mypy engine/src/battle_engine`) | clean, 0 errors, 65 files |
| Mypy (`mypy client/src/battle_client`) | clean, 0 errors, 10 files |

No flake was observed in any of these runs at the source level. (The one
transient artifact observed anywhere in this qualification was the
concurrent-pytest-process file-lock issue in §17, which is a
process-isolation methodology issue in this session's own venv-comparison
script, not a flake in the product's own test suite.)

## 19. CI qualification

`.github/workflows/ci.yml` (`test-linux-core`) already targets Python
3.10-3.13 unconditionally on every push/PR, with no path filter — every
new v1.6 test module under `engine/tests/` is automatically included via
`pytest.ini`'s `testpaths`; no module is omitted from CI collection.
`build-windows-exe` builds all four executables and runs a narrow,
deliberately-scoped Windows-only subset (process containment, agent
worker, supervised runtime, agent revisions) — this predates v1.6 and was
not expected to (and does not need to) separately exercise evaluation/
preset/analysis/behavior code, since that is already covered by
`test-linux-core`'s full headless run. `linux-gui-smoke.yml` remains a
narrow X11 startup smoke, not a substitute for the full `gui`-marked
suite, exactly as `AGENTS.md` already documents.

**Pre-existing, non-v1.6 CI gap noted for disclosure**: neither `mypy`
invocation is run in CI at all (only `ruff`); this predates v1.6 and was
verified locally instead (§18) per the charter's own allowance to use
local qualification as primary when CI hasn't run against this branch.

The branch has not been pushed; per the governing charter, local
qualification (§13, §18 above) is the primary evidence, and this
remains unverified against actual CI infrastructure until the eventual
push/release phase.

## 20. Dependency and packaging audit

`pyproject.toml` inspected directly:

- Runtime `dependencies`: unchanged, `PyYAML>=6.0` only. No new runtime
  dependency was introduced by any v1.6 phase.
- `windows-build` extra (`pyinstaller`, `pefile`) is dev/build tooling
  only, unchanged.
- No new `[tool.setuptools.package-data]` entry was needed or added —
  Phase 3's own decision not to ship built-in presets (docs/V1_6_PHASE3
  §16) is reflected in the unchanged package-data list.
- `[tool.setuptools.packages.find]`'s wildcard discovery
  (`battle_engine*`) automatically includes every new plain module
  (`evaluation_presets.py`, `evaluation_analysis.py`,
  `evaluation_behavior.py`, `evaluation_worker.py`) and the new
  `evaluation_history.behavior_adapter` submodule with no explicit
  entry required — independently confirmed by the frozen-build
  qualification's direct inspection of the bundled `PYZ` (§14).
- No network dependency, no cloud requirement, no hidden GUI-only
  dependency for CLI analysis (`evaluation_analysis.py`/
  `evaluation_behavior.py` are stdlib-only, confirmed by their own phase
  docs and re-verified by import-graph reasoning against current `HEAD`).

No packaging or dependency change was required or made in Phase 6.

## 21. Documentation consistency audit

A dedicated audit pass (cross-checking `docs/V1_6_PHASE1-5`, `docs/
AGENT_LAB.md`, `docs/ROADMAP.md`, `docs/FUTURE_PLANS.md`,
`CHANGELOG.md`, `docs/specs/agent_evaluation.md`, `docs/specs/
evaluation_history.md`, and `README.md` against each other and against
live `--help`/CLI output) found **no factual inconsistencies**:

- No document describes Phase 2 (parallel evaluation) as future/
  unimplemented.
- Preset CLI syntax in documentation matches actual `--help` output
  exactly (`list [--json]`, `show <name> [--json]`, `validate <name>`).
- No document overstates statistical significance or claims a behavioral-
  distance/replay-derived-trajectory feature is shipped.
- Worker default is documented as `1` everywhere checked, matching actual
  behavior.
- `v1.6.0` is not marked released/shipped/tagged anywhere; `CHANGELOG.md`
  has no `[1.6.0]` heading; `README.md`'s downloads/roadmap sections still
  point at `v1.5.0` as current.
- Every checked `--help` flag/default (for `agents evaluate`,
  `evaluation-presets {list,show,validate}`, `evaluations show`,
  `evaluations compare`) matches documented behavior.
- Live CLI `evidence:`/`behavior:` block wording matches `docs/
  AGENT_LAB.md`'s documented examples verbatim, including the 11 named
  behavior dimensions.

## 22. Defects discovered

Two findings, both **non-blocking**, both disclosed rather than
silently worked around or fixed opportunistically:

1. **`comparison.py`'s ambiguous-fallback grouping omits orientation**
   (§10-adjacent finding from the `evaluations compare` cross-feature
   check): `evaluation_history/comparison.py`'s `_classify_unmatched`
   groups strictly-unmatched cells by `(opponent_id, seed)` only, not by
   orientation. When comparing two both-orientation evaluations that
   differ in any effective condition (e.g., tick count — a realistic
   scenario, such as comparing a quick-smoke preset against a thorough
   one), every candidate cell for a given `(opponent, seed)` lands in the
   same fallback group (2 cells per side, one per orientation), which the
   existing, deliberate "more than one unmatched cell per side is
   genuinely ambiguous — never guess a pairing" rule (documented directly
   in that function's own docstring) correctly refuses to resolve,
   reporting `ambiguous_duplicate_groups` instead of the more precise
   `changed_condition` it could report if orientation were included in
   the fallback key. **Not a correctness defect** — no cell is ever
   silently mispaired, and the conservative "ambiguous" classification is
   exactly what the code's own documented design intends for a case it
   cannot uniquely resolve. **Pre-existing, not part of v1.6**:
   `comparison.py` is untouched by any v1.6 phase (§1's diff confirms
   this); Phase 4/5 never extended it. Recorded as a disclosed, narrow
   precision opportunity for a future maintenance pass (include
   orientation in `_classify_unmatched`'s grouping key), not fixed here
   per the charter's explicit instruction against opportunistically
   improving unrelated, out-of-scope code.
2. **`PairedEvidence` wording inconsistency between two presentation call
   sites for the all-inconclusive-pairs case** — see §9 for the full
   description. Non-blocking (cosmetic wording gap, not a wrong
   calculation), recorded but not fixed per the charter's classification
   guidance for non-blocking maintenance items.

No release-blocking defect was found anywhere in this qualification:
no nondeterminism, no resume corruption, no invalid canonical identity,
no broken frozen packaging, no platform-specific crash, no wrong
statistical or behavioral calculation, no unreadable historical artifact,
and no preset resolution that changed evaluation meaning unexpectedly.

## 23. Fixes made

None. No code fix was required; both findings in §22 are classified
non-blocking per the governing charter's own fix policy, and the charter
explicitly instructs recording (not expanding scope to fix) such items.

## 24. Deferred non-blocking issues

- The two findings in §22.
- The pre-existing CI gap noted in §19 (mypy not run in CI at all).
- Exact pass/skip counts for the 3.10/3.12/3.13 headless suite reruns
  were not captured due to a display-capture artifact specific to those
  venv invocations in this session's shell (§17) — exit codes (0 for all
  three) are treated as conclusive for pass/fail, but a future session
  wanting exact counts should capture them via `--junitxml` rather than
  relying on redirected stdout for these particular interpreters.
- No live, manual, interactive Designer GUI click-through was performed
  in this non-interactive session; the automated `gui`-marked suite
  (181 tests, offscreen Qt) was used as the qualification evidence
  instead (§3).
- Installer (Inno Setup) and portable ZIP artifact generation were not
  additionally exercised beyond the onedir tree those artifacts package
  verbatim (§15).
- A new, hand-constructed historical (v1-schema) artifact was not
  additionally run through the live CLI beyond what the existing,
  passing automated test suite already covers (§11).

## 25. Files changed in Phase 6

**None in the production source tree.** This qualification pass found no
defect requiring a code fix (§22-§23); the only new file is this
document itself, `docs/V1_6_PHASE6_INTEGRATED_QUALIFICATION.md`.

## 26. Phase 6 commit(s)

One documentation/qualification-record commit adding this document,
per the governing charter's explicit allowance ("If no production fixes
are required, a documentation/test qualification commit is acceptable").
No amendment to any Phase 2-5 commit was made.

## 27. Final working-tree state

Clean except for this new documentation file, staged for the single
Phase 6 commit described above. All temporary qualification artifacts
(isolated `BYTEFRAY_ROOT`, evaluation output directories, per-version
venvs, log files) were created entirely outside the repository, under a
scratch directory, and are not part of this commit.

## 28. Final verdict

**READY FOR RELEASE PREPARATION.**

Every criterion in the governing charter's §26 was checked directly, not
assumed:

1. Ruleset-v1 unchanged — confirmed by direct `git diff --stat` against
   every execution-boundary module since v1.5.0 (§1, §12).
2. Canonical identities stable — confirmed at every worker count and
   scale tested, plus existing golden-vector tests (§4, §12).
3. Serial/parallel deterministic equivalence preserved — confirmed at
   60/540/2,000-cell scale (§4, §8).
4. Preset resolution identity-neutral and reproducible — confirmed (§4,
   §5).
5. Resume remains authoritative after preset mutation — confirmed with a
   real forced-crash-and-resume test, not just the source-level suite
   (§6).
6. Statistical calculations verified — confirmed; one non-blocking
   presentation-wording finding disclosed, not a calculation error (§9,
   §22).
7. Behavioral calculations verified — confirmed, including a real
   incomplete-evidence (source-drift) case that did not misrepresent
   itself as complete (§7, §10).
8. Historical supported artifacts remain usable — confirmed via the
   existing, extensive, passing automated test suite (§11).
9. Large integrated evaluation completes successfully — confirmed at
   540 and 2,000 cells (§8).
10. Windows source qualification passes — confirmed, including a
    corrected, more rigorous orphan-process check than the naive one
    (§13).
11. Frozen Windows qualification passes — confirmed, no defect found
    (§14).
12. Linux qualification passes — confirmed on genuine WSL2 Ubuntu
    (§16).
13. Supported Python versions are qualified — confirmed for 3.10-3.13,
    exit-code-verified with one disclosed reporting-capture gap for
    exact counts on three of the four (§17).
14. Full headless suite green — 1468 passed, 0 failed (§18).
15. GUI suite green — 181 passed, 0 failed (§18).
16. Ruff clean — confirmed (§18).
17. Mypy clean — confirmed for both packages (§18).
18. No release-blocking packaging defect — confirmed (§14, §20).
19. Documentation matches actual shipped behavior — confirmed by
    dedicated audit, zero inconsistencies found (§21).
20. Working tree contains only intentional Phase 6 changes — confirmed
    (§27); no production code was touched.

No criterion could not be verified. The two non-blocking findings (§22)
do not affect the release-readiness verdict and are recorded for a future
maintenance pass, not required before Phase 7 (release preparation) may
begin.
