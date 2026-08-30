# Bytefray v2.0.0-beta2 Phase 4.1 — Pre-Qualification Remediation

Branch: `v2.0-beta2-development`. Phase 4 base: `74a95d2`. Recovery
checkpoint: `6c00c58` (`wip(v2.0-beta2): preserve phase 4.1 review
remediation`). Status: complete; ready to enter Phase 5. Phase 5 itself is
out of scope here.

## 1. Why Phase 4.1 existed

An independent pre-qualification review after Phase 4 recommended fixes
before integrated qualification. It found five high-severity issues:

1. group cells could not pass evaluation-history deep verification;
2. duplicate/self-play group artifacts could be falsely reported
   unhealthy;
3. N>=3 victim capture timing could be fabricated from the final match
   tick;
4. the claim that Python match identity remained historically compatible
   for all starts was false;
5. adding `placement_id="fixed"` changed historical v1 schedule hashes.

The first remediation session was interrupted while working on group
comparison identity. Its mixed but valuable work was preserved and pushed
as `6c00c58`. This continuation treated that commit as a durable recovery
boundary: it inspected and tested the existing changes, retained correct
work, completed the interrupted comparison path, and added only the
remaining bounded fixes.

Recovery began with one known working-tree exception,
`.claude/settings.local.json`, an unrelated user-owned untracked file. It
was not read for task purposes, modified, ignored, staged, or removed.

## 2. Finding disposition

| Finding | State at recovery | Final disposition |
|---|---|---|
| HIGH-1 group deep verification | Production generalization and N=3/N=4 tests present | Retained; healthy N=3 verifies 18/18 cells, non-A candidate seats verify, corrupted evidence fails, N=4 verifies 72/72, pairwise unchanged |
| HIGH-2 self-play group health | Explicit recorded group discriminator and regression tests present | Retained; duplicate-candidate and duplicate-opponent artifacts are healthy and no pairwise opponent identity is fabricated |
| HIGH-3 capture timing | Conservative single-death trust rule and tests present | Retained; unknown multi-death/tick-limit timing remains `None` and is excluded from aggregates/JSON numbers |
| HIGH-4 Python start identity | Start-aware identity and corrected compatibility prose present | Retained as a deliberate transition; old non-zero-start resumes fail closed and require retry/re-execution |
| HIGH-5 v1 schedule identity | Conditional `placement_id` schedule key and historical golden present | Retained; v4 schedule recipe matches pre-Beta2 while v5 placement and v6 seat/layout identity remain significant |
| MEDIUM-1 group comparison content | Model/adapter/signatures partially threaded; caller wiring and tests incomplete | Completed; non-candidate roster content participates in adapted comparison keys, candidate content does not |
| MEDIUM-2 duplicate presentation | Execution/identity healthy, presentation still first-occurrence-shaped | Added multiplicity/per-instance disclosure and suppressed ambiguous legacy candidate aggregate in live/history output |
| MEDIUM-3 duplicated payload construction | Still duplicated between writer and validator | Deferred; extraction crosses three identity generations and was not low-risk enough for this compatibility repair |
| MEDIUM-4 pairwise sentinels | Identity-bearing legacy fields retained | Documented as sentinels; group logic uses roster/seat/layout evidence instead; future schema cleanup only |
| Group orientation switches | Still silently accepted | `--group` now rejects explicit `--single-orientation` and `--both-orientations` |
| Empty group differential | Empty orientation scope could show `0.0` | Empty scopes now emit `None`, matching unknown/no-evidence semantics |
| Phase 4 prose/provenance | Raw ranks, capture-fix claim, and reproduction wording overstated | Corrected without changing the strategic assessment |

## 3. High findings

### HIGH-1 — group deep verification

The old verifier assumed the physical entrant order was always `(A, B)`
and resolved subject/opponent seats through pairwise orientation. Group
cells instead record N physical seats and a seat assignment. The retained
fix derives `(A..seat_label(N-1))`, resolves the subject's recorded
physical seat, and skips only the inapplicable single-opponent identity
check. Nested result/replay identity, digest, seed, winner/outcome, and
candidate identity checks still run.

Regression coverage proves healthy N=3, non-A candidate seats, corrupt
entrant order/match identity/replay digest, unchanged pairwise behavior,
and N=4.

### HIGH-2 — self-play group health

The adapter previously inferred pairwise structure from `opponent_id`.
That field is only a display label in group cells and can equal a real
opponent id in a roster such as `(candidate, candidate, opponent)`. The
retained fix keys from the explicit recorded `group` methodology instead.
Group cells therefore receive no fabricated pairwise opponent identity and
are not passed through pairwise condition-fingerprint reconstruction.

Both `(candidate, candidate, opponent)` and `(candidate, opponent,
opponent)` are covered. Ordinary distinct-roster v5/v6 health stays clean.

### HIGH-3 — victim-side capture timing

Aggregate `result.json` evidence proves a victim died at the terminal
match tick only when alive-count termination occurred and exactly one
entrant died. With multiple deaths it cannot identify which victim died
last, so all victim-side capture ticks are withheld. Tick-limit endings are
also unknown. Known single-death timing remains available, while `None`
values are excluded from means/medians and serialize as JSON `null`.

No replay parsing was added and pairwise capture timing was not changed.

### HIGH-4 — start-aware Python match identity

Python `MatchEntrant.start` changes core placement/capture geometry and is
therefore match-significant. The start key remains omitted only for zero,
preserving historical zero-start IDs. Historical non-zero starts were
reachable through single-run start flags and tournament spacing, so a
pre-Beta2 non-zero-start match may receive a different `match_id`,
`result_id`, and `replay_id` under Beta2.

Tournament resume recomputes the new ID and reports
`resumed_result_mismatch` rather than trusting incompatible evidence.
Retry/re-execution is the supported transition. No broad migration alias
was added.

### HIGH-5 — historical v1 schedule identity

Unlike HIGH-4, v1 evaluation schedule identity has a real compatibility
contract. The v4 schedule payload again omits `placement_id` entirely;
v5 adds it because placement varies, and v6 continues using its separate
roster/seat/layout payload.

The literal historical fixture is:

| Identity | Pre-Beta2 / observed value |
|---|---|
| `evaluation_id` | `evaluation-v2_0677e78d27642c3c6f8fa62f` |
| `schedule_id` | `evaluation-cell_08c9393822c99186c03001ef` |
| `condition_fingerprint` | `evaluation-condition_3fba859dabbcf03c7cb6048a` |

The values were reconstructed against commit `2076576`, pinned as
literals, and then compared with the current production path. A completed
cell carrying the historical schedule ID resumes without re-execution.

## 4. Group comparison content identity

Pairwise comparison already prevents strict alignment when a logical
opponent id stays the same but its source/revision content changes. The
interrupted remediation added `EvaluationSummary.roster_identities` and a
group key branch, but failed to pass the recorded maps from `align()`
through `_align_cell_sets()` into `_condition_key()`. Every group cell
therefore failed closed into one ambiguous duplicate group, including two
identical evaluations.

The completed design uses the existing planned identity fields
(`source_sha256`, `entry_point`, `api_version`, and
`local_source_fingerprint`) for each non-focal logical roster member.
Candidate identity is deliberately excluded, preserving the purpose of a
candidate comparison. Results:

- identical 1-seed / 3-layout / 6-permutation evaluations align all 18
  cells;
- different logical rosters do not align;
- the same logical roster with changed opponent content does not
  strict-align;
- changed candidate content with unchanged opponents remains comparable;
- pairwise local-source B4 protection remains unchanged.

Duplicate ids are represented by the canonical roster tuple, including
multiplicity. Content identity is keyed by logical id because duplicate
instances necessarily resolve the same source. In candidate self-play,
focal candidate content cannot meaningfully be separated from a second
candidate instance's content; all instances share one source identity, so
the candidate logical id is excluded as a whole rather than inventing a
distinction the artifact cannot support.

This is adapted comparison metadata only. No stored v6 identity changed.

## 5. Self-play semantics

- **Execution:** duplicate logical ids execute as distinct physical seats;
  physical `MatchEntrant.agent_id` remains unique.
- **Persisted identity:** roster multiplicity, ordered seat assignment,
  layout, and raw result entrants remain authoritative and unchanged.
- **Symmetric analysis:** one raw record is retained per physical seat;
  summaries over duplicate ids therefore use physical entrant instances as
  their denominator.
- **Candidate presentation:** derived JSON exposes `roster_multiplicity`,
  duplicate logical ids, and `rate_denominator_unit`;
  candidate-focused JSON exposes multiplicity and ambiguity. Plain live
  and history output labels per-instance rates and suppresses the legacy
  first-occurrence candidate outcome aggregate when multiplicity exceeds
  one.

The stored legacy `EvaluationCell.outcome` still follows the first
candidate occurrence because changing it would require schema/identity
churn. Raw physical-seat evidence and derived group analysis are the
truthful self-play surfaces.

## 6. Compatibility matrix

| Surface | Expected | Observed | Verdict |
|---|---|---|---|
| v4 evaluation ID | pre-Beta2 value | literal golden matches `2076576` | preserved |
| v4 condition fingerprint | pre-Beta2 value | literal golden matches `2076576` | preserved |
| v4 schedule ID | pre-Beta2 value and resume reuse | literal golden matches; completed cell reused | restored |
| v5 placement identity | distinct placements remain distinct | three schedule IDs; health/comparison green | preserved |
| v5 pairwise comparison | opponent content guarded | B4 comparison tests green | preserved |
| v6 evaluation/schedule/fingerprint | no stored drift | writer payloads unchanged; schedule reconstruction and health tests green | preserved |
| v6 self-play health | healthy | duplicate-candidate/opponent tests green | fixed |
| v6 deep verification | generic N | N=3 18/18; N=4 72/72 | fixed |
| v6 resume | deterministic | completed/missing-cell tests green | preserved |
| v6 comparison | changed opponents fail strict match | content-guard tests green | fixed |

Stored generations remain v4 (v1), v5 (Ruleset-v2 pairwise), and v6
(Ruleset-v2 group). No schema or identity version was bumped.

## 7. Deferred findings

- Centralizing writer/validator identity payload construction remains a
  post-Beta2 cleanup. A safe extraction must preserve historical branching
  across v4/v5/v6 and group/pairwise condition payloads; doing it here
  would create more identity risk than the bounded correctness benefit.
  HIGH-2/HIGH-5 regressions protect the repaired boundaries meanwhile.
- Group `EffectiveConditions.subject_slot`, `opponent_slot`, and
  `entrant_order` remain identity-bearing pairwise compatibility
  sentinels. N-aware cleanup requires a future identity/schema version.
- Group evaluation ID dependence on opponent CLI order, huge-N exhaustive
  layout degeneration, and O(n²) unattributed-interaction calculation are
  unchanged and deferred as originally scoped.

None is a Phase 5 blocker. The first two are future identity/schema
cleanup; huge-N is a documented Beta2 practical limit; the O(n²) item is
future performance work.

## 8. Phase 4 corrections and rerun decision

The Phase 4 record now distinguishes raw point-estimate rank from
statistical overlap, no longer calls raw-leading Claimer a clear third,
does not claim Claimer/Core Tracker rankings contradicted by its own
tables, and corrects the claim that Phase 3's capture-tick repair was
already complete. It also states that the `runs/` research inputs were
retained local/untracked artifacts rather than claiming a clean checkout
alone contains a complete reproduction bundle.

Phase 4 used match outcomes, capture occurrence/rates, and attribution;
it did not base strategic conclusions on victim-side capture ticks. No
simulation result, scoring result, or statistic used by the strategic
assessment changed. Therefore:

> Phase 4 corpus rerun not required.

The strategic decision remains `PROCEED WITH DOCUMENTED CONCERNS`.

## 9. Qualification

Focused recovery wave:

- multi-entrant, group analysis, history verification, and comparison:
  green;
- broad evaluation/history/ruleset/tournament wave: **463 passed, 2
  skipped**;
- historical v1 literal golden/resume, v5 placement, v6 schedule, N=3,
  N=4, self-play, changed-opponent, changed-candidate, and CLI cleanup are
  included in those suites.

Full local qualification:

```text
python -m pytest
1877 passed, 14 skipped, 2 deselected, 0 failed, 0 errors

python -m ruff check .
All checks passed!

python -m mypy engine/src/battle_engine
Success: no issues found in 73 source files

python -m mypy client/src/battle_client
Success: no issues found in 12 source files
```

The first sandboxed full-suite attempt reported one false failure in the
Windows orphan-process test because sandboxed `tasklist` returned access
denied. The exact test passed outside the sandbox, and the complete
authoritative outside-sandbox run produced the totals above.

`git diff --check` is clean. `.claude/settings.local.json` remains the
approved, untouched untracked exception.

## 10. Readiness decision

All five high findings are closed. MEDIUM-1 and MEDIUM-2 are complete;
MEDIUM-3/MEDIUM-4 have explicit safe deferrals. The CLI and empty-
aggregate cleanup items are complete. Identity generations and schema
versions are stable, focused and full qualification are green, and no
strategic rerun is required.

**READY FOR BETA2 PHASE 5**

**Beta2 Phase 4.1: COMPLETE**
