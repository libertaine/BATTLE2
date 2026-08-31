# Bytefray v4 Research — Stage 5 Anchor Visibility and Discovery

Stage 5 asks what information cost should precede the exact-anchor `WRITE`
selected by R4b. It compares all requested visibility candidates conceptually
and prototypes only V0 public anchors and V2 local detection. No canonical
Agent API, production ruleset, replay, GUI, process-destruction, or spawning
surface is changed.

## A. Baseline qualification

- Branch: `v4-research`.
- Starting `HEAD` and `origin/v4-research`:
  `2074d4462cd93be355109432443e3b6614a0f6c7`.
- R3 spatial closure:
  `ad442af56d9fe435a06c3a157e4115f1e721422a`.
- Original R4 closure:
  `3d71fa62dddca2f4f41130c1ae38143bbcf85b7e`.
- Qualified R4b closure:
  `2074d4462cd93be355109432443e3b6614a0f6c7`.
- The branch and remote were synchronized at 0/0 divergence. There were no
  tracked changes; the pre-existing untracked `.claude/` directory was left
  untouched and excluded.

Pre-mutation baseline tests:

| Suite | Result |
|---|---:|
| `test_v4_r3_spatial.py` | 1 passed |
| `test_v4_r4_disruption.py` + `test_v4_r4b_disruption.py` | 42 passed |
| Process semantics/R1b + scheduler | 24 passed |
| **Total** | **67 passed** |

The qualified R4b semantics remained unchanged: D=1, fair proportional
largest-remainder redistribution, K=2 rotating scheduling, live enemy-only
C1 disruption, modulo-normalized anchors, automatic recovery, and zero
callbacks when all processes are disrupted.

Post-prototype validation:

| Validation | Result |
|---|---:|
| Stage 5 focused tests | 16 passed |
| All v4 process/scheduler research tests | 83 passed |
| Engine mypy | 88 source files, no issues |
| Client mypy | 12 source files, no issues |
| Ruff on touched Python files | passed |
| `git diff --check` | passed |
| Full headless suite | 1 failed, 2460 passed, 14 skipped, 2 deselected in 279.73 s |

The sole full-suite failure was the unchanged Windows containment test
`test_worker_does_not_survive_a_hard_kill_of_its_own_parent`: its child worker
had exited before the test attempted the deliberate parent kill. This is the
same unrelated failure class recorded during R4b and does not execute the
process research controller. Repository-wide Ruff also reports the four
pre-existing import-order/unused-import findings in untouched
`test_v4_process_semantics_r1b.py` and `v4_r1b_equivalence_challenge.py`.

## B. Current information exposure

Before the Stage 5 prototype, `ProcessObservation` exposed:

| Agent-visible | Engine-internal | Test/debug-only |
|---|---|---|
| Current tick | Every entrant and process object | Direct controller/process references |
| Own entrant/process ID and role | All current process anchors | Process telemetry and position history |
| Own current anchor and reach | Enemy IDs, roles, shares, reach, and disruption state | VM arena/writer arrays inspected by tests |
| Own core base/size and arena size | All core cells, alive states, scores, and territory | Result summaries |
| Own prior action operands/value | Full arena bytes and ownership map | Canonical replay memory diffs |
| Addressed READ byte and owner | Scheduler slot/order state | Development traces of the traced agent's own API boundary |
| Entrant-shared Python dictionary | Enemy MOVE/READ/WRITE sources | Experiment closures that deliberately inspect fixtures |

Only a process's own anchor is directly visible. Friendly peers can publish
their own coordinates through entrant `shared_memory`, but the engine does not
provide a friendly-anchor list. Enemy anchors, process counts, quotas, reach,
roles, disruption states, action sources, and movement events are absent.

`READ` in the research runtime exposes the byte and last-writer owner at the
address explicitly read; it does not expose whether an anchor occupies that
address or the source anchor of a prior write. Arena ownership is not supplied
as a map. The canonical Agent API is stricter still: it exposes own state and
the last-read byte, not read ownership, opponent state, arena state, or cores.

Each process receives its own core base and size. Enemy cores are internal,
although their seeded arena cells can be investigated through ordinary local
interaction. Thus exact globally public enemy anchors would reveal more direct
opponent state than the existing core/arena observation philosophy.

The research prototype adds only:

```python
visible_enemy_anchors: tuple[int, ...]
```

to research-only `ProcessObservation`. Its default model is hidden, preserving
all earlier experiments. It is not added to canonical `Observation`.

## C. Candidate visibility models

| Model | Information event | Assessment |
|---|---|---|
| V0 public | All live enemy occupied anchor addresses before every callback | Executable zero-discovery-cost control; simplest, but perfect tracking makes movement only a geometric defense. |
| V1 friendly-public/enemy-hidden | No enemy reveal event | Current arena interaction cannot reliably discover an anchor; blind guesses receive no disruption confirmation. Reject as incomplete. |
| V2 local detection | Exact occupied address when an eligible friendly anchor is within deterministic radius | Executable candidate; turns MOVE and retained spatial presence into reconnaissance without READ spam. |
| V3 READ discovery | Exact-cell occupancy metadata on READ | At 1024 cells, uniform exact-cell search averages 512.5 reads and has a 1024-read worst case: 64.06 and 128 ticks respectively at Q=8 before bounded-reach movement cost. Reject as blind search. |
| V4 activity reveal | An enemy action emits its source anchor | Low search burden, but ordinary useful activity becomes free exposure while passivity hides perfectly; requires a new opponent-action event/lifetime rule. Not prototyped. |
| V5 engine last-known | Engine retains prior detections | Redundant: agents can store coordinate and tick themselves. Not selected as engine state. |

Approximate regions were also considered. They require sector/band definitions
and refinement mechanics before a disruption can be attempted. Exact location
after a meaningful local detection condition is more explainable and directly
actionable, so approximation adds complexity without a demonstrated benefit.

No V2+V4 hybrid is needed: local detection already supplies discovery,
movement-driven staleness, and reconnaissance specialization. Activity reveal
would mainly restore free information for active targets.

## D. Information-equivalence criteria

Agent memory cannot synthesize an unknown engine-owned coordinate. The
meaningful Stage 5 event is therefore the engine revealing a spatial fact at a
defined time and cost. Once received, a monolithic controller or any process
can remember the same `(address, tick)` pair; that memory is not a separate
engine capability.

The selected candidate defines the event as:

```text
Immediately before a process callback:
  if any currently eligible friendly process anchor is within its detection
  radius of a live enemy anchor, expose that enemy occupied address to the
  entrant for this observation.
```

The field is recomputed from current engine state before every callback.
Movement earlier in the schedule can therefore affect a later observation,
just as an earlier write affects a later read. There is no post-action
retroactivity and no random component.

## E. Discovery-cost analysis

V0 costs zero search actions and zero search time. The attacker still pays
geometric MOVE actions to enter WRITE reach and one WRITE for each D=1 refresh.

V2 uses movement as both search and approach. The tested attacker has arbitrary
internal memory, stores legitimate detections, takes shortest circular pursuit
after detection, refreshes at most once per tick, and never performs artificial
forgetting. Before detection it performs a deterministic clockwise ring sweep.
This sweep is a reproducible strong control, not a claim that one direction is
optimal for every unknown placement; the mirror placements deliberately show
the cost of directional uncertainty.

V3's exact-cell burden is unacceptable without prior information:

```text
uniform one-anchor search without replacement
expected READs = (1024 + 1) / 2 = 512.5
worst READs    = 1024
Q=8 lower bound, ignoring movement = 64.06 / 128 ticks
```

This is precisely the blind-search trap Stage 5 is intended to avoid.

## F. Static-target experiments

Exact parameters:

```text
arena=1024, Q=8, K=2 rotating, D=1
action reach=50, detection radius=50, max MOVE=64
attacker anchor=0, static target anchor=256 or 768
duration=2 ticks, attacker listed first
```

Addresses 256 and 768 are equally distant from 0 geometrically but lie in
opposite directions. V0 directs shortest pursuit. V2 has no target coordinate
and uses its declared clockwise sweep.

| Model / target | First detection | Search MOVE | Pursuit MOVE | Attempts/hits | Victim callbacks | Denied vs 16 | Other actions |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 / 256 | tick 1, action 1 | 0 | 4 | 2/2 | 6 | 10 | 10 |
| V0 / 768 | tick 1, action 1 | 0 | 4 | 2/2 | 6 | 10 | 10 |
| V2 / 256 | tick 1, action 5 | 4 | 0 | 2/2 | 6 | 10 | 10 |
| V2 / 768 | tick 2, action 13 | 12 | 0 | 1/1 | 14 | 2 | 3 |

The V2 detection itself costs no special action. Its cost is the MOVE/time
opportunity cost of putting a sensor within radius and the uncertainty of
choosing a search direction. A favorable sweep can equal V0's total geometric
movement; an unfavorable placement delays first suppression and consumes most
of the two-tick action budget.

## G. Moving-target experiments

Exact parameters:

```text
arena=1024, Q=8, K=2 rotating, D=1
reach=detection radius=50, max MOVE=64, duration=2 ticks
friendly Scout: position 50, share 2
friendly Attacker: position 100, share 6
target: position 100, share 8, MOVE +64 on its first callback each tick
friendly entrant listed first
```

The Scout publishes visible coordinates and observation tick to entrant-shared
memory. The Attacker retains the last known coordinate and uses it even when
current visibility disappears.

| Model | Scout search MOVE | Pursuit MOVE | Attempts/hits/misses | Victim callbacks | Denied vs 16 | Non-search/pursuit/write actions |
|---|---:|---:|---:|---:|---:|---:|
| V0 | 0 | 2 | 2/2/0 | 6 | 10 | 12 entrant-wide |
| V2 | 2 | 2 | 2/1/1 | 14 | 2 | 10 entrant-wide |

Deterministic V2 trace:

```text
tick 1: Scout at 50 detects target at 100; stores (100, 1)
tick 1: target moves 100 -> 164 and leaves radius
tick 1: Attacker at 100 sees no current target, writes last-known 100, misses
tick 2: target moves 164 -> 228
tick 2: Scout moves 50 -> 114 -> 178 (2 reacquisition actions)
tick 2: Attacker observation sees current occupied address 228 via Scout
tick 2: Attacker moves 100 -> 164 -> 228, writes 228, and disrupts target
```

Public visibility removes the stale-coordinate failure: after each target move,
the Attacker receives the new exact location and converts movement into only a
pursuit cost. Local current-only detection gives MOVE an information-defense
role as well as a geometric role. Reacquisition in this case costs two Scout
MOVEs and one tick, followed by two pursuit MOVEs and the targeted WRITE.

## H. Reconnaissance specialization

V2 creates a useful but optional Scout role:

```text
Scout retains or moves a local sensor origin
  -> exact occupied address becomes currently visible entrant-wide
  -> shared memory stores address and detection tick
  -> Attacker pursues or attempts disruption
```

Any process can detect, so the rules do not force a dedicated Scout. A
monolith can perform the same search but spends its own MOVE/action capacity
and cannot retain another persistent sensor origin elsewhere. This is
consistent with R3: the value comes from independently persistent spatial
origins, not from process-local Python memory.

The Defender+Scout scenario places an observer at 750, an enemy Defender at
100, and an enemy Scout at 800. At radius 50 the observation contains only
`(800,)`. The entrant can prioritize the discovered spatial target, but the
engine does not label it as a Scout or expose the undiscovered Defender.

## I. Information-sharing semantics

**Selected: shared entrant intelligence.** A current detection made possible
by any eligible friendly anchor appears in every friendly process observation
while the condition holds. The detector identity is not exposed. A process at
500 receives `(40,)` because its friendly Scout at 0 is within radius of the
enemy at 40.

Process-local detection would require forwarding the same spatial fact through
mailboxes before another process could act, recreating R1b organizational
complexity without a distinct spatial benefit. Shared visibility also lets a
single monolithic controller and a multi-process entrant consume the same
engine revelation once obtained.

A disrupted friendly process is not an eligible sensor. A test with a Scout at
0 disrupted for tick 1, an active peer at 500, and an enemy at 40 exposes no
coordinate; disruption cannot leave behind a free passive detector.

## J. Detection lifetime

**Selected: current-only engine visibility.** The engine does not retain
last-known coordinates. It recomputes a sorted tuple before each callback.
Agents may store exact coordinates and `obs.tick` in local or entrant-shared
memory. Match reset clears those agent-owned structures through the existing
runtime lifecycle.

The moving-target trace proves this is sufficient: `(100, 1)` remains in
shared memory after current visibility disappears, produces one stale miss,
and is replaced by `(228, 2)` on reacquisition. An engine-managed V5 cache
would duplicate this logic and require additional invalidation semantics.

## K. R4 disruption interaction

The Stage 5 quantity is:

```text
total disruption cost
= search/detection movement
+ pursuit or reacquisition movement
+ attempted targeted WRITEs
+ D=1 refresh WRITEs
```

V0 preserves R4b's strongest case. If already in reach, an exact anchor is
free information and maintenance remains one WRITE per tick (12.5% of Q=8).
For the static remote controls, V0 adds four directed pursuit MOVEs but still
lands two refreshes and denies 10/16 callbacks.

V2 makes cost spatial and target-dependent. It can equal V0 after a favorable
search, but the opposite placement costs twelve search MOVEs and permits only
one late hit. Against movement, current visibility can invalidate between
detection and attack, producing a paid miss plus explicit reacquisition and
pursuit costs. Hiding therefore does not make disruption impossible, while
public visibility demonstrably removes the information-defense component of
MOVE.

A successful disruption does not add explicit confirmation in this prototype.
When a coordinate is currently visible and the actor is in reach, WRITE is
applied immediately after that observation, so an additional success field is
not needed to establish the selected visibility rule. A guessed stale write
has no confirmation. Likewise, a recovering victim receives no attacker ID or
hit-source telemetry. Those are future combat-feedback/API questions, not
Stage 5 visibility requirements.

## L. Core-information consistency

Neither canonical agents nor research processes receive an opponent-core list
or arena ownership map. Research processes know only their own core and can
investigate addressed cells through bounded READs; canonical observations are
even more restrictive. Although core placement is deterministic engine state,
an agent is not directly given opponent count/slots through the observation.

V2 is consistent with that philosophy: opponent spatial state is revealed by
local arena relationship rather than globally injected. V0 would be a simple
rule, but it would make anchors more public than cores and ordinary ownership
without evidence that this exception improves play.

## M. Metadata exposure

The minimum selected fact is:

```text
"one or more live enemy processes occupy address A now"
```

The field is a sorted tuple of unique normalized addresses. It does not expose:

- process ID or role;
- process count at an address;
- quota share or reach;
- disruption state;
- detector identity;
- movement or action history.

With enemies at 40, 45, 45, and 60 and an observer at 0 with radius 50, the
result is `(40, 45)`: exact nearby addresses, co-location collapsed, and the
out-of-range address omitted. This fits R4b C1 because one WRITE affects all
enemies at an occupied address; knowing the hidden count is unnecessary.

Modulo normalization and circular distance are used. An initial target anchor
1044 normalizes to 20 and is visible from 1000 at circular distance 44. Dead
enemy anchors are omitted. Enemy WRITE activity under the hidden control does
not leak an anchor through the new field.

## N. Complexity and gameplay assessment

### Radius comparison

With action reach 50, observer 0, and enemies at 40 and 75:

| Detection radius | Visible | Interpretation |
|---:|---|---|
| 25 (< reach) | none | Address 40 is legally attackable but invisible; creates an awkward blind-attack band. |
| 50 (= reach) | 40 | Simple rule: if a friendly origin can interact with the anchor, the entrant can see it. |
| 75 (> reach) | 40, 75 | Provides reconnaissance before engagement, but adds a second range parameter without demonstrated need. |

**Selected radius: each sensor process's action reach.** An explicit override
exists only for research comparison. One radius is easier to explain, avoids
blind legal targets, and does not grant an unpriced early-warning halo.

### Implementation and exploit review

- Strategy: search direction, sensor placement, pursuit, and when to trust a
  stale coordinate are real deterministic choices.
- Explainability: “if a friendly process could locally interact with that
  anchor, your entrant sees the occupied address” uses the existing reach rule.
- Agent burden: one tuple plus optional agent-owned `(address, tick)` memory.
- Engine state: a pure pre-callback query; no retained detection cache.
- Scheduler: deterministic current state is sampled before the callback.
  Movement in one callback can affect the next, with no after-the-fact reveal.
- Compatibility: research-only field, hidden default, no canonical API or
  production ruleset mutation; Model A and current agents remain unaffected.
- Future replay/UI: the exact current detection event is representable without
  exposing process metadata, but no replay/UI work is performed here.
- Debug leakage: tests access internals for assertions, but agent logic receives
  only the explicit tuple.
- Staleness: current visibility disappears when geometry changes; only agent
  memory persists.
- Wrap/normalization: circular distance and normalized addresses are tested.
- Lifecycle: dead enemies and disrupted friendly sensors do not contribute.
- Co-location: unique occupancy avoids count/identity leakage.

### Required Stage 5 answers

1. Enemy anchors should not be public by default.
2. A live anchor is revealed immediately before a callback when any eligible
   friendly anchor is within its action reach.
3. Discovery costs the MOVE actions and time required to bring a sensor into
   range: 4 or 12 moves and tick-1/tick-2 detection in the static controls.
4. Local detection is preferable to READ scanning; exact-cell READ search has
   a 512.5-read expectation and 1024-read worst case before movement.
5. Process activity does not itself reveal position.
6. Detection supplies exact, not approximate, occupied addresses.
7. Current detection is shared across the entrant.
8. Engine-provided visibility persists only while the current geometric
   condition holds.
9. Agents may store their own last-known coordinate and observation tick.
10. Movement meaningfully invalidates coordinates and caused a measured stale
    miss under V2.
11. The moving control required two Scout reacquisition MOVEs, two pursuit
    MOVEs, and one successful WRITE after the stale miss.
12. Local hiding does not make disruption impossible; both static placements
    and the moving target were eventually hit.
13. Public visibility is too cheap informationally: it produced immediate
    detection, perfect tracking, no misses, and 10/16 denied callbacks.
14. The minimum exposed information is a sorted set-like tuple of current
    occupied enemy addresses.
15. Identity, role, quota, reach, count, and disruption state remain hidden.
16. Co-located enemies appear as one occupied address.
17. Visibility creates a useful Scout role without requiring one because every
    eligible process is a sensor and intelligence is shared.
18. V2 exact local detection at action reach best balances reconnaissance,
    disruption, movement, determinism, and implementation simplicity.

## O. Stage 5 decision

**Decision B — Local detection.**

Enemy process anchors are not globally public. Immediately before each
research-process callback, the entrant receives the sorted unique addresses of
live enemy anchors within the action reach of any currently eligible friendly
process. This is exact current occupancy only, entrant-wide, and contains no
identity or structural metadata. Agents own any last-known memory.

V0 proves that public anchors keep disruption operational but remove discovery
and informational evasion. V2 keeps disruption achievable while pricing it
through the same spatial movement economy established by R3. No hybrid,
probabilistic fog, explicit scan action, or engine tracking cache is justified.

## P. Recommended next research

The smallest next boundary is a **process-observation contract and combat-
feedback qualification pass**: specify how the selected research-only
occupancy tuple would be versioned in a future process API and whether guessed
WRITE attempts or recovered processes require minimal disruption feedback.
That pass must preserve current-only detection and must decide compatibility
before any canonical API, replay, or UI implementation.

This report does not begin that work or any broader Stage 6 research.

---

Executable provenance: `engine/tests/test_v4_r5_visibility.py`, using the
research-only prototype in `battle_engine.process_runtime`. Final validation
counts and the containing follow-up commit are recorded at handoff.
