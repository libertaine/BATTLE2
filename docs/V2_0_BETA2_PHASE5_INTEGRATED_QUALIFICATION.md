# Bytefray v2.0.0-beta2 Phase 5 — Integrated Qualification

Branch: `v2.0-beta2-development`. Starting HEAD:
`22f43be9e7df8541e5bb578dd5c52fc06789ecf8`. Status: qualified for
release, not published. This is the final integrated gate over Beta2
Phases 1–4.1; it introduces no product behavior, schema, or methodology
change.

## 1. Release decision

> **QUALIFIED FOR V2.0.0-BETA2 RELEASE**

The current Beta2 branch is internally coherent across historical v1/v4,
Ruleset-v2 pairwise/v5, and Ruleset-v2 group/v6 evaluation domains. The
former independent-review findings remain closed, real source-tree and
installed-wheel workflows pass, the canonical full and static suites are
green, and no release blocker remains.

This decision authorizes a separate Beta2 release-preparation / merge /
tag / publication task. Phase 5 did not merge, tag, push, publish, or
create a GitHub release.

## 2. Repository and scope evidence

Preflight established:

- branch `v2.0-beta2-development` at the exact expected Phase 4.1 HEAD,
  `22f43be9e7df8541e5bb578dd5c52fc06789ecf8`;
- `origin/v2.0-beta2-development` at the same commit;
- `main` and `origin/main` both at
  `20765765a5b2d3cbafa4d799dbe1f2f9498b6a62`;
- protected historical refs unchanged:
  `v2.0-beta1-development` at `79f61f438b8232936f60d069347b89b030e30439`,
  `v2.0-development` at `ad67a0fe0778fdc40c804618e8ec5ea8ea9cf7d3`,
  and `origin/v2.0-development` at
  `151866c6d862fec4facb78596204861b26889b61`;
- no staged or tracked working-tree change, with only the approved,
  user-owned `.claude/settings.local.json` untracked exception;
- `git diff --check` and `git diff --check 2076576..HEAD` clean.

The complete Beta2 delta from `2076576` comprised 34 files, 10,415
insertions, and 206 deletions. It contains the v2 pairwise evaluation
methodology, generic multi-entrant scheduler/identity model, symmetric
group analysis, strategic characterization records, and Phase 4.1
compatibility remediation. Phase 5 reviewed and exercised their
integration boundaries; it did not reopen settled gameplay, scheduling,
winner, scoring, or strategic-agent design.

## 3. Identity and compatibility qualification

| Domain | Identity | Evidence | Verdict |
|---|---:|---|---|
| Historical v1 methodology | v4 | Literal pre-Beta2 `evaluation_id`, `schedule_id`, and `condition_fingerprint` golden; completed-cell reuse; default and explicit v1 CLI artifacts | Preserved |
| Ruleset-v2 pairwise | v5 | Three placement identities, resume, both-orientation and worker coverage, behavior/capture/history/comparison, source CLI artifact | Sound |
| Ruleset-v2 group | v6 | Roster/seat/layout identity, deterministic resume, group health/verification/comparison/analysis, N=3 and N=4 | Sound |
| Python non-zero start | match identity transition | Non-zero start changes `match_id`; zero-start identity remains stable; old non-zero-start tournament evidence fails closed | Documented and sound |

No Phase 5 or Phase 4.1 schema bump occurred. Stored evaluation identity
generations remain exactly v4/v5/v6. The historical v4 golden values are:

| Identity | Literal value |
|---|---|
| `evaluation_id` | `evaluation-v2_0677e78d27642c3c6f8fa62f` |
| `schedule_id` | `evaluation-cell_08c9393822c99186c03001ef` |
| `condition_fingerprint` | `evaluation-condition_3fba859dabbcf03c7cb6048a` |

The golden test reconstructs the old payload shape independently from
commit `2076576` and compares pinned literals with the current production
path. The resume test then proves that a completed cell carrying that
historical schedule ID is reused rather than executed again.

## 4. Independent-review release gates

| Gate | Integrated evidence | Result |
|---|---|---|
| HIGH-1 group deep verification | Healthy N=3 verifies 18/18; candidate outside seat A verifies; healthy N=4 verifies 72/72; entrant-order, match-id, and replay-digest corruption fail closed; pairwise still verifies | Pass |
| HIGH-2 self-play health | `(candidate, candidate, opponent)` and duplicate-opponent artifacts remain healthy, retain multiplicity/physical-seat evidence, and fabricate no pairwise opponent identity | Pass |
| HIGH-3 capture timing | Single terminal death retains timing; multi-death and non-terminal/tick-limit timing is `None`; capture fact and directed attribution remain independent; pairwise timing unchanged | Pass |
| HIGH-4 Python start identity | Start-sensitive match identity, historical zero-start stability, accurate compatibility prose, and old non-zero-start tournament resume mismatch | Pass |
| HIGH-5 v1 schedule identity | Literal historical hashes and completed-cell reuse | Pass |

The bounded release-critical suite covering these gates, group comparison,
self-play, N=4, and group analysis produced **217 passed, 2 skipped**. A
second interruption/resume/worker/identity selection produced **13
passed**.

The tests are not tautological: the v4 golden pins independent literal
hashes, group verification tampers real nested artifacts and replay bytes,
comparison mutates candidate and opponent source independently, and the
capture tests construct distinct one-death and multi-death aggregate
evidence.

## 5. Multi-entrant, self-play, and generic N

- N=3: one seed × three standard layouts × six seat permutations produced
  18 real cells in both source and installed-wheel smokes; all completed
  and deep-verified.
- N=4: one seed × three layouts × 24 permutations produced 72 distinct
  cells; seat labels, identity, verification, and analysis passed.
- Duplicate logical IDs execute as distinct physical entrants. Recorded
  roster multiplicity, ordered seats, physical winner evidence, and
  per-instance symmetric rates remain authoritative.
- When the candidate occurs more than once, presentation discloses
  multiplicity and suppresses the ambiguous legacy first-occurrence
  candidate aggregate. The stored `EvaluationCell.outcome`
  first-occurrence behavior remains a documented compatibility limitation,
  not a hidden claim.
- Production paths use generated seat labels, layouts, permutations, and
  per-entrant records; no A/B/C-only production branch was found.

Exhaustive permutations scale factorially, so very large N is a practical
beta limitation. It is not evidence that the architecture is N=3-specific.

## 6. Group comparison

For the representative three-entrant matrix:

| Relationship | Result |
|---|---|
| Identical evaluations | all 18 cells strict-align |
| Candidate implementation changed | all 18 remain comparable; candidate diff disclosed |
| Same opponent ID, opponent content changed | zero strict rows; ambiguity disclosed rather than attributed to candidate |
| Logical roster changed | no alignment |
| Group versus pairwise | no alignment |

Pairwise B4 opponent-content protection remains intact. The source CLI
also compared two independently written but identical group artifacts
with `--verify`: 18 comparable, 18 unchanged, zero unmatched,
changed-condition, ambiguous, or corrupt rows. Discovery correctly marked
the two locations as duplicate locations for the same deterministic
evaluation ID; direct artifact health and deep verification remained
healthy.

## 7. Pairwise, capture, and winner compatibility

Representative default v1, explicit `bytefray-rules-1`, and explicit
pairwise `bytefray-rules-2` workflows passed through the real CLI. The v1
runs emitted schema/identity v4; the v2 run emitted v5 with all three
standard placements. Automated coverage additionally proves both
orientations, behavior/capture analysis, comparison, history, resume, and
worker-count independence.

No winner, scheduler, scoring, VM, or Ruleset implementation changed in
Phase 5. Group outcome derivation remains tied to the engine's physical
winner and survivor eligibility; capture fact, attribution, and timing
remain distinct evidence fields. The deliberate start-identity transition
is the only compatibility exception, and it fails closed.

## 8. Resume and determinism

- v1/v4, pairwise v5, and group v6 no-op resumes reuse completed cells.
- Missing-cell and coordinator-interruption tests rerun only incomplete
  work and reproduce uninterrupted final identities/results.
- Serial and multi-worker executions produce equal evaluation IDs,
  schedule IDs, match IDs, and outcomes for pairwise and group matrices.
- Source drift, roster/methodology drift, corrupted artifacts, and the old
  non-zero-start recipe are refused rather than silently accepted.

## 9. Source-tree CLI and history smoke

The editable source installation was invoked through the public
`bytefray.exe` console entry point with `BYTEFRAY_ROOT` set to the checkout
and outputs isolated under a fresh system-temporary directory. The core
commands were:

```text
bytefray --version
bytefray agents evaluate wanderer --opponents hunter --seeds 1 --ticks 5 --single-orientation ...
bytefray agents evaluate wanderer --ruleset bytefray-rules-1 --opponents hunter --seeds 1 --ticks 5 --single-orientation ...
bytefray agents evaluate wanderer --ruleset bytefray-rules-2 --opponents hunter --seeds 1 --ticks 5 --single-orientation ...
bytefray agents evaluate wanderer --ruleset bytefray-rules-2 --group --opponents hunter,claimer --seeds 1 --ticks 5 ...
bytefray agents evaluations list --root <smoke-root>
bytefray agents evaluations show <v4|v5|v6-artifact> --verify [--json]
bytefray agents evaluations compare <v6-left> <v6-right> --verify
```

Observed artifacts:

| Flow | Schema/identity | Cells | Deep verification |
|---|---:|---:|---|
| default v1 | 4 | 1/1 complete | pass |
| explicit Ruleset v1 | 4 | 1/1 complete | pass |
| Ruleset-v2 pairwise | 5 | 3/3 complete | pass |
| Ruleset-v2 group (each of two runs) | 6 | 18/18 complete | pass |

Human and JSON history views exposed rules/methodology, health, roster,
group analysis, and verification. Group artifacts stayed out of pairwise
behavior/capture adaptation. Automated tamper cases prove unhealthy
artifacts fail visibly.

Invalid group combinations all exited 2 with specific diagnostics:
Ruleset v1/default, fewer than three entrants, `--baseline`, pairwise-only
orientation flags, and an unknown Ruleset. Pairwise defaults remain v1.

## 10. Packaging and installed-wheel qualification

The Beta2 delta changes no `pyproject.toml`, console entry point, package
data, `app/`, `client/`, build script, or PyInstaller specification. New
engine/history modules are covered by automatic `battle_engine*` package
discovery; the frozen specifications likewise use
`collect_submodules("battle_engine")`. A full Windows frozen rebuild would
therefore repeat unchanged packaging machinery and was not required at
this gate.

The canonical isolated build command (`python -m build --wheel`) produced:

```text
bytefray-2.0.0b1-py3-none-any.whl
SHA-256 5da68b54652112fe863049a3606e0b4550dbd8cba98b08cb3943f0d5c32a6b70
```

The `2.0.0b1` metadata is expected: Phase 5 does not perform the separate
Beta2 release-version bump. `tools/check_wheel.py` passed. The wheel was
installed with its declared PyYAML dependency into a fresh venv and run
from a directory outside the checkout. `battle_engine`,
`agent_evaluation`, `evaluation_group_analysis`, and `evaluation_history`
all resolved from that venv's `site-packages`, not the source tree.

The installed CLI passed version/help/history availability checks, created
three new agents from packaged templates, completed an 18-cell Ruleset-v2
group evaluation, and reported schema v6, a three-agent roster, complete
cells, group analysis, and `verified=True`.

The build emitted current-setuptools deprecation warnings for the existing
TOML license table/classifier. They do not affect this wheel and are future
packaging cleanup before setuptools' stated 2027 enforcement date, not a
Beta2 blocker.

## 11. Client and GUI scope

Beta2 changes no client or GUI production file and adds no GUI dependency
or import edge. The canonical full suite includes client coverage; a
dedicated client run produced **272 passed, 2 deselected**, and a
lightweight import smoke for `battle_client`, `battle_client.session`, and
`app.services.evaluation_history_workflows` passed. Client mypy is clean
for 12 files.

Because the changed release surface is headless engine/evaluation code,
automatic frozen collection already covers it, and the installed wheel
proved it is present, a display-backed GUI feature pass or full Windows
executable rebuild would add ritual rather than relevant Beta2 evidence.

## 12. Complete automated and static qualification

```text
python -m pytest
1893 collected
1877 passed
14 skipped
2 deselected
0 failed
0 errors

ruff check .
All checks passed!

mypy engine/src/battle_engine
Success: no issues found in 73 source files

mypy client/src/battle_client
Success: no issues found in 12 source files

git diff --check
clean
```

The full test run took 241.39 seconds. The known `.pytest-cache-v141/`
warning did not prevent qualification. No failure was dismissed as flaky.

## 13. Strategic-characterization validity

Phase 5 changed no production code, test semantics, scheduler, scoring,
agent, Ruleset, match outcome, or strategic metric formula. Phase 4.1 also
changed no simulation outcome or statistic used by the Phase 4 corpus.
Therefore:

> Phase 4 strategic characterization remains valid; no corpus rerun is
> required.

Its decision remains `PROCEED WITH DOCUMENTED CONCERNS`: Claimer is
conditionally strong; exhaustive permutations balance a real global seat
bias at the entrant-exposure level; kingmaking/non-transitive effects are
real; and group win rate is not a complete strategic descriptor.

## 14. Limitations and blockers

Release blockers: **None**.

Documented Beta2 limitations carried forward:

- stored self-play `EvaluationCell.outcome` retains first-occurrence
  candidate semantics; raw seats and symmetric analysis are authoritative;
- group evaluation ID depends on opponent CLI ordering;
- exhaustive seat permutations scale factorially;
- group effective conditions retain identity-bearing pairwise sentinels;
- capture attribution/timing remains conservative without replay-level
  Tier-3 evidence;
- writer/validator identity-payload centralization and the existing
  packaging-license metadata deprecation are future cleanup.

These are disclosed behavior, scaling, or maintenance boundaries. None is
an integrity failure or false compatibility claim.

## 15. Publication handoff

The next step is a separate **Beta2 release-preparation / merge / tag /
publication** task. It should:

1. update package/version and release metadata from `2.0.0b1` to the
   intended `2.0.0b2` / `v2.0.0-beta2` form;
2. preserve the v4/v5/v6 identity and non-zero-start compatibility notes;
3. carry the documented self-play, opponent-order, factorial-scaling,
   pairwise-sentinel, and conservative-capture limitations into release
   notes;
4. rebuild and qualify the final release artifacts from the exact release
   commit before tagging and publication.

No publication mutation occurred during Phase 5.

**Beta2 Phase 5: COMPLETE**
