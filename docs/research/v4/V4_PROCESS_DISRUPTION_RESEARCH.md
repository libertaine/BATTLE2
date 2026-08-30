# Bytefray v4 Research — R4b Temporary Disruption Qualification

R4b reopens and corrects the temporary-process-disruption closure recorded in
R4 candidate `3d71fa62dddca2f4f41130c1ae38143bbcf85b7e`. The independent review's
decision, **DOWNGRADE TO QUALIFIED CANDIDATE**, was accepted as the starting
point. This pass replaces incidental quota allocation, pins the research
scheduler, measures optimized suppression, and qualifies the mechanic without
entering Stage 5.

## A. Repository provenance and recovery

- Branch: `v4-research`.
- Initial `HEAD`: `3d71fa62dddca2f4f41130c1ae38143bbcf85b7e`.
- Initial `origin/v4-research`: the same commit; ahead 0, behind 0.
- Initial worktree: the R4 report was emptied, the R4 test had only whitespace
  edits, and `.claude/` was untracked.
- The tracked changes contained no useful research work. The committed R4
  files were restored before R4b changes. `.claude/` was left untouched and is
  excluded from the R4b commit.
- The original R4 commit remains intact as historical evidence; R4b is a
  follow-up rather than rewritten history.

## B. What R4 proved, and what it did not

**Proven:** a valid enemy `WRITE` to a process's current spatial anchor can
selectively suppress that legal action origin. Ordinary contention over the
process's output cells does not suppress its callbacks. Temporary disruption
is therefore materially distinct from ordinary memory contention.

**Not automatically proven by R4:** that its incidental quota fallback, mixed
scheduler assumptions, duration, co-location rule, or perfect-information
economics were suitable production semantics. The original report also
mistook nominal duration sums for actual unavailable match ticks and
overstated the attacker's maintenance cost.

## C. Normative R4b scheduler

The candidate commit was inconsistent: the process research controller
defaulted to K=2 rotating while the registered `bytefray-rules-4-alpha1`
policy was K=1 non-rotating. The latest scheduler research closure in
`V4_SCHEDULER_RESEARCH.md` section 11.9 selected K=2 plus deterministic start
rotation, so R4b makes that registered policy and the controller default the
same object:

```text
scheduler mode:       chunked
K:                    2 callbacks per entrant slot
rotation:             enabled
tick T starting seat: (T - 1) modulo the original entrant count
dead entrants:        skipped without renumbering seats
```

One match tick is one complete scheduler pass in which every live entrant is
eligible for at most entrant quota Q. Entrants execute in K=2 chunks. A hit can
suppress a target's later slots in the same tick; the next tick rotates which
entrant receives the first chunk. All R4b economics below use this policy,
Q=8, two entrants, and ten ticks unless stated otherwise.

## D. Explicit quota-policy comparison

R4b implements and compares exactly two policies. Invalid specifications are
rejected: every entrant must have at least one process, shares must be
non-negative, and declared shares must sum exactly to Q.

**Q1 — lost disrupted quota:** each eligible process retains its declared
share as a hard limit. A disrupted process's share is lost for that tick.

**Q2 — fair explicit redistribution:** declared shares are steady-state
weights, not hard per-process maxima. If eligible processes have weights
`s_i`, total eligible weight `S`, and entrant quota `Q`, each first receives
`floor(Q*s_i/S)`. Remaining callbacks go by descending fractional remainder,
with stable `process_id` as the deterministic tie-break. Allocation sums to Q
whenever any positive-share process is eligible. An all-disrupted entrant gets
zero callbacks. There is no overflow fallback.

Representative one-tick results:

| Shares | Disrupted | Q1 callbacks | Q1 total | Q2 callbacks | Q2 total |
|---|---|---:|---:|---:|---:|
| 8 | p0 | 0 | 0 | 0 | 0 |
| 4/4 | p0 | 0/4 | 4 | 0/8 | 8 |
| 4/4 | all | 0/0 | 0 | 0/0 | 0 |
| 3/3/2 | p0 | 0/3/2 | 5 | 0/5/3 | 8 |
| 3/3/2 | p2 | 3/3/0 | 6 | 4/4/0 | 8 |
| 3/3/2 | p0,p1 | 0/0/2 | 2 | 0/0/8 | 8 |
| 3/3/2 | all | 0/0/0 | 0 | 0/0/0 | 0 |
| 2/2/2/2 | p2 | 2/2/0/2 | 6 | 3/3/0/2 | 8 |
| 2/2/2/2 | p0,p1 | 0/0/2/2 | 4 | 0/0/4/4 | 8 |
| 2/2/2/2 | all | 0/0/0/0 | 0 | 0/0/0/0 | 0 |

Both rules remove the disrupted origin and its remote coverage. Q1 also
removes entrant-wide action volume, compounding positional success with an
immediate capacity penalty and increasing snowball risk. Q2 converts lost
coverage into concentration at surviving origins while preserving Q; attacks
remain useful because reallocated callbacks cannot act from the lost origin.
All 24 list permutations of the equal-share four-process case produce the
same process-ID allocation (`3/3/0/2` when `charlie` is disrupted), proving
that allocation is not list-order biased.

**Selected quota policy: Q2 — fair explicit redistribution.** It gives
distributed entrants resilience without making a hit counterproductive: the
attacker still removes spatial coverage, while the victim retains a response
from surviving locations. The single-process all-disrupted case necessarily
receives zero callbacks under either policy.

## E. Selected disruption duration

The controller default remains `D=0` so existing research controls are
opt-in and unchanged. The selected R4b mechanic explicitly uses **D=1**:

```text
on a hit during tick N: disrupted_until_tick = N + D
at tick t:             disrupted when t < disrupted_until_tick
```

For D=1, a hit during tick N suppresses later eligible execution in tick N and
the process recovers at tick N+1. A single tick-1 hit observed after the victim
had used its first K=2 chunk produced victim callbacks `{1: 2, 2: 8}`.

For D=2, the same hit suppresses later tick-N execution and all tick N+1
execution, with recovery at N+2. This doubles steady-state refresh efficiency
in the measured distributed-target case, so D=2 is rejected for R4b.

## F. Optimized suppression economics

The attacker writes the known target anchor only when a refresh is required;
all other callbacks remain available for other play.

| Case | Hits / writes | Denied callbacks | Distinct unavailable ticks | Remote services | Other attacker actions | Denied/write | Q spent/tick |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4/4 scout, D=1 | 10 | 40 | 10 | 0 of control 40 | 70 | 4 | 12.5% |
| 4/4 scout, D=2 | 5 | 40 | 10 | 0 of control 40 | 75 | 8 | 6.25% |
| static 8 monolith, D=1 | 10 | 70 | 10 | 10 callbacks remain | 70 | 7 | 12.5% |

The original full-Q maintenance claim was false. With perfect target
information and a stationary anchor, D=1 costs one targeted write per tick,
not the attacker's full Q. D=2 achieves the same complete scout suppression
with writes only on ticks 1, 3, 5, 7, and 9; that 6.25% maintenance cost is too
efficient for the smallest meaningful duration rule.

The static monolith result is deliberately not softened: K=2 rotation lets it
act twice on victim-first odd ticks, but one perfect-information write per tick
still denies 70 of 80 control callbacks. A movable monolith can spend its
surviving windows on escape. Against a perfect-information chaser over ten
ticks it received 20 callbacks, spending 10 on movement and 10 on service;
the attacker spent 10 disruption writes, 10 pursuit moves, and retained 60
other actions. D=1 is therefore severe but does not provide a free stationary
lock against a target that moves.

## G. Co-location semantics

**Selected: C1 — shared-location blast.** One valid enemy write disrupts every
live enemy process whose current anchor equals that cell. Tests with two and
four co-located enemies give every enemy one hit and zero later callbacks in
the attacker-first tick. Co-located friendly processes are immune; in the
mixed test the friendly process receives its full four callbacks while both
enemy processes are suppressed.

C1 treats the arena cell as the vulnerable physical location and makes
stacking an explicit risk. C2 would require process-identity targeting and an
additional deterministic selection surface without evidence that C1 is
pathological.

## H. Anchor normalization and dead state

- Explicit initial positions are normalized modulo arena size before the
  match. In a 1024-cell arena, anchor 1024 becomes 0, is recorded as 0 rather
  than the raw value, and is targetable by a write to 0.
- Disruption targeting skips entrants already marked dead. In the stale-anchor
  control, the target receives its one live tick-1 hit; later writes after
  death do not increase hit, nominal-duration, or distinct-tick metrics.

## I. Recovery and metrics

R4b adds `disruption_hits_received` and the set of distinct match ticks on
which each process was unavailable. The report derives denied callbacks from
an undisrupted control and separately counts total callbacks, remote service
actions, attacker refresh writes, recovery tick, and maintenance efficiency.
The legacy `total_disrupted_ticks` / summary `disrupted_ticks` nominal-duration
sum remains for compatibility, but it is not interpreted as distinct disabled
ticks, denied callbacks, or lost actions.

Disruption does not reset a process. In the D=2 recovery test, the victim acts
twice in tick 1, zero times in tick 2, and exactly eight times in tick 3. Its
local counter remains 2 at recovery; the first recovered callback still sees
the pre-disruption READ kind and result; a MOVE advances the anchor from 100
to 101; and no duplicate quota appears. Expiry is exactly tick 3.

Old feedback can therefore be several ticks stale. `ProcessObservation.tick`
exposes current match time, and local state can track the last callback, but
the feedback itself has no production timestamp. That is a future Agent API
design concern; R4b does not redesign the public API.

## J. No-disruption controls

**N1 — ordinary memory contention.** With disruption disabled, a 4-share
remote scout receives all four callbacks and performs all four service writes
each tick even while an attacker makes one late overwrite per tick. Final
ownership of the output cell is attacker after tick 1 and victim after tick 2
because rotated execution changes the final writer. Contention can contest
the result, but it does not remove the remote action origin.

**N2 — defended core.** A 4-share defender continually cycles writes across
its eight core cells while a 4-share scout services the remote region. A
remote attacker requires 2 movement actions and 22 core writes to remove the
defended core by the end of tick 3. Before irreversible global elimination,
the victim executes 24 callbacks and the scout completes 12 remote service
actions. Core attack is practical counterplay, so disruption is not
structurally required. It is instead a cheaper, selective, localized, and
automatically reversible alternative to global lethal counterplay.

## K. Single-process fragility

Under Q2, an unavailable sole process has no eligible recipient, so its quota
cannot be redistributed. With D=1, a stationary one-process entrant facing a
perfect-information attacker loses 70/80 callbacks for 10 writes; rotation
preserves two callbacks on each of five victim-first ticks. This is
near-continuous suppression at 12.5% of attacker Q and is the mechanic's
sharpest risk.

The compensating properties are a single anchor's smaller attack surface,
automatic next-tick recovery, rotating first action windows, and the ability
to spend those windows moving. The movement experiment raises the monolith to
20/80 callbacks and 10 successful services while forcing pursuit costs. This
supports D=1 only as a deliberately severe positional punishment; D=2 is not
acceptable.

## L. Multi-process resilience

For 4/4, suppressing one origin gives the survivor 8 local callbacks. For
3/3/2, one suppressed origin yields `0/5/3`, `5/0/3`, or `4/4/0`; suppressing
the two 3-share origins concentrates all 8 callbacks at the 2-share origin.
For 2/2/2/2, one suppressed origin yields deterministic `3/3/0/2`, while two
suppressed origins yield 4/4 at the survivors. In every case, suppressed
origins lose their regional reach, total volume remains 8 while an eligible
positive-share process survives, and response capacity becomes more locally
concentrated. List permutations do not change the process-ID result.

## M. Qualified strategic trade

The measured axis is coherent but intentionally not described as perfect:

```text
Concentrated entrant                 Distributed entrant
- fewer vulnerable anchors          - broader spatial coverage
- stronger normal local share       - lower normal per-anchor share
- smaller attack surface            - larger attack surface
- severe single-point suppression   - redundant surviving origins
- can spend recovery windows moving - Q2 concentrates response after a hit
```

Disruption trades attacker actions for removal of a specific action origin.
It does not erase the victim's total capacity when another process survives,
and it does not replace ordinary output contention or lethal core attack.

## N. Validation

The final validation record is filled from the R4b follow-up worktree:

- Required process/spatial/R4/R4b group: 48 passed.
- All non-scheduler v4 process research tests: 53 passed.
- Scheduler tests: 14 passed.
- Full headless suite: 1 failed, 2444 passed, 14 skipped, 2 deselected in
  354.50 seconds. The failure was
  `test_worker_does_not_survive_a_hard_kill_of_its_own_parent`; both isolated
  reruns reproduced the same unrelated Windows containment-test failure
  because the child worker exited before the test's deliberate parent kill.
- Engine mypy: success, 88 source files.
- Client mypy: success, 12 source files.
- Ruff on all touched Python files: passed.
- Repository-wide Ruff: four pre-existing import-order/unused-import errors in
  untouched `test_v4_process_semantics_r1b.py` and
  `v4_r1b_equivalence_challenge.py`; R4b does not alter those files.

The containment-test failure does not execute the research controller or
disruption code. It is reported rather than hidden or treated as a pass.

## O. Corrected R4 conclusion

Temporary localized disruption is a valid, distinct candidate because it can
selectively suppress a spatial action origin. The acceptable R4b form is not
the incidental original prototype: it requires explicit Q2 redistribution,
the registered K=2 rotating scheduler, D=1, C1 shared-location blast,
normalized anchors, live-target filtering, and behavior-derived metrics.
Optimized stationary suppression is cheap and single-process fragility is
high, so these constraints and the perfect-information assumption are
material qualifications.

## P. Final R4b decision

**Decision B2 — Temporary disruption with fair redistribution.**

The rule is explicit and order-neutral, D=1 is the smallest meaningful and
less efficient tested duration, stacking and recovery are defined, and the
controls show a selective role not duplicated by ordinary contention or core
attack. The choice remains a v4 research result, not an assertion that all
production balance questions are closed.

## Q. Git policy

R4b is recorded as a new follow-up to `3d71fa62`; the original candidate is
not amended or rebased. `.claude/` is excluded. Final commit and remote state
are reported at handoff.

## R. Stage 5 boundary

Every R4b attacker is given the exact current target anchor. No public anchor
metadata, detection radius, scanning, hidden coordinates, or inference is
researched here. The 12.5% D=1 maintenance figure excludes discovery cost and
therefore depends on perfect information. Whether and how an attacker learns
an anchor remains solely the Stage 5 question; Stage 5 has not begun.
