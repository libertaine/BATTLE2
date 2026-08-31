# Bytefray v3 Phase 2 — Bounded-Locality Feasibility

Branch: `v3-research-phase2`, cut from `v3-research-phase1` at `0f07425`
immediately after the Phase 1 report. Status: research complete, not merged,
not tagged, not published.

Phase 2 is the first **gameplay-mechanic** research phase of the v3 program.
It implements one experimental mechanic behind one explicitly non-stable
Ruleset identity, measures it against two controls, and scores it against
gates that were committed before any result existed.

No stable `bytefray-rules-3`, no Agent API v2, no multiple loci, no
replication, no fog of war, no ATTACK action, no resource system and no
scoring change were implemented, and none were needed. Ruleset v1 and
Ruleset v2 execute byte-identically to before — see §6.

---

## 1. Initial state

Verified before any change:

| ref | value |
|---|---|
| starting branch | `v3-research-phase1` |
| HEAD | `0f074252dda9fe01a170246ca54a6a652f874fe9` |
| Phase 0 commits present | `2370033`, `253fccb`, `063111c`, `ebe72a1`, `51a39e8` |
| Phase 1 commits present | `3c523bc`, `945d63a`, `0f07425` |
| `v3-research-phase0` | `51a39e8` — unchanged |
| `v3-research-phase1` | `0f07425` — unchanged |
| `main` | `1093393b401aabda243ed89b7c44fa91938477b5` |
| `origin/main` | `1093393` — identical, no unpushed divergence |
| `v2.0.0` tag | annotated `5c525ce`, still targets `965d2f6` |
| working tree | clean |
| frozen Phase-0 benchmark population | 9/9 members verify against their pinned `agent_revision_id` |
| Phase 1 committed grid + report | present (`v3_phase1_arena_action_grid.json`, `docs/V3_PHASE1_ARENA_ACTION_DENSITY.md`) |
| Phase 1 corpus artifacts | present under `runs/research_v3_phase1` (14 GB, 20 conditions) |

Every historical v1/v2 branch and tag is untouched. Work proceeded on a new
branch `v3-research-phase2` cut from `0f07425`. Nothing was merged or
tagged.

---

## 2. Repository reality check

Phase 2B required the current addressing semantics to be established from
code and from execution, not from earlier review claims. All three were
confirmed by running the real runtime (`apply_action` against a live `VM`),
not by reading:

| claim | verified how | result |
|---|---|---|
| `READ`/`WRITE` take arbitrary absolute addresses | `WRITE 5000` in a 256-cell arena | wrote `arena[136]`, i.e. `5000 % 256`; `WRITE -3` wrote `arena[253]` |
| addressing is modulo arena size | `vm._wr8`'s `i = pos % m`, `vm.arena[operand % len(vm.arena)]` in `apply_action` | confirmed in both directions |
| Python `pc` is **not** an execution location | `JUMP 77` moved `pc` 1000 → 77; the next `WRITE 200` still wrote `arena[200]` | address unaffected by `pc`; nothing in `apply_action` reads `pc` for addressing |
| no position/reach invariant exists | enumerated every `PythonEntrantState` field | no field containing `position`, `reach`, or `locus` |
| distance from `pc` to a write is unbounded | `pc = 1000`, wrote address 5000 | 4000 cells, accepted |

Current semantics, stated exactly:

```text
READ  operand          -> value = vm.arena[operand % arena_size]
                          sets last_read, register_a, zero_flag
WRITE operand, value   -> vm._wr8(operand, value, agent_id), i.e. arena[operand % arena_size]
pc                     -> initialized to entrant.start & 0xFFFFFFFF; moved ONLY by
                          JUMP / JUMP_IF_ZERO; read by nothing except Observation.pc
core_start             -> entrant.start % arena_size; fixed at construction, never moved
arena_size             -> Config.arena_size; exposed to agents via MatchContext
action budget          -> Config.instr_per_tick actions per entrant per tick,
                          via ruleset_policy.run_scheduler -> run_sequential_quota
```

The consequence, which is the whole reason the locality hypothesis exists:
a Ruleset-v2 entrant has **no location at all**. `pc` looks like one and is
even used as one by three reference agents — but only to recover their own
*spawn address* on the first `act()`, because that address is also their
core anchor. Nothing constrains where an entrant may read or write. It is
omnipresent by construction.

---

## 3. Locality alternatives considered

Phase 2C required at least two approaches to be compared before
implementing.

### Option A — additive locality actions, absolute actions still available

Add `LOCAL_READ`/`LOCAL_WRITE`/`MOVE`; leave `READ`/`WRITE` in place.

**Rejected as written.** It does not produce an experiment. A locality-aware
agent could ignore its locus entirely and keep addressing globally, so the
corpus would measure an *opt-in handicap* rather than a Ruleset. Every
result would be attributable to how much locality each agent author chose
to accept.

### Option B — Agent API v2 semantics: redefine `READ`/`WRITE` as relative

Under the experimental Ruleset, `READ 100` means "read `locus + 100`".

**Rejected.** It is unbypassable and conceptually clean, and it is the
shape a locality-native API would probably take — which is exactly the
problem. It freezes an Agent API v2 guess into a research prototype before
any gameplay evidence exists, and it makes the *same source file* mean two
different things depending on which Ruleset it runs under. A v2 agent run
under it would not fail; it would quietly do something else, and no reader
of the agent's source could tell which meaning applied.

### Option C — additive vocabulary with the absolute forms *forbidden* (chosen)

Add the three locality actions **and** reject `READ`/`WRITE` under the
locality Ruleset. The two addressing vocabularies are disjoint; every
non-addressing action (`NOP`, `SET_A`, `ADD_A`, `SET_P`, `ADD_P`, `JUMP`,
`JUMP_IF_ZERO`, `HALT`) is identical under both.

This is Option A with the bypass closed, and closing it has direct
repository precedent: `bytefray-rules-2` already restricts what may execute
under it (`supported_runtime_kinds={"python"}`), rejecting a VM entrant
before any entrant runs. Restricting an *action* vocabulary per Ruleset is
the same kind of boundary, scoped entirely to a new experimental identity.

What Option C buys, and why it was worth the extra enum members:

* **`READ 100` still means absolute address 100, forever.** No Agent API v1
  operation changes meaning anywhere, so Phase 2 can answer "what
  incompatibility did locality actually require?" with evidence instead of
  with a decision it made in advance (§21).
* **Failures are loud.** A v2 agent under locality forfeits with
  `agent_action_invalid` on its first `WRITE`; a locality agent under
  Ruleset v2 forfeits identically on its first `LOCAL_WRITE`. Both
  directions are asserted by tests. Neither can be mistaken for a valid
  comparison.
* **Locality is unbypassable.** There is no global addressing to fall back
  on.

The cost is honest and recorded: `ActionKind` gains three members that are
not part of the `docs/AGENT_API_V1.md` contract. `AGENT_API_VERSION` is
**not** bumped — an agent that never emits them observes and behaves
exactly as before — and `docs/AGENT_API_V1.md` is not modified.

---

## 4. Chosen experimental semantics

The entire mechanic lives in `battle_engine.python_runtime`, gated on one
exact `ruleset_id`, in the same style as the vulnerable-core and
core-beacon mechanics it sits alongside.

### Position

Each Python entrant has exactly one **locus**: an engine-owned arena
address, held in `PythonEntrantState.locus`, `None` under every
non-locality Ruleset.

* **Initial value**: `entrant.start % arena_size` — the entrant's own spawn
  address, which is also its `core_start`. An entrant therefore begins
  standing on its own core, so defending it is possible from action one and
  no entrant is undefendable by construction (Phase 2G).
* **Normalization**: `% arena_size`, the same wrap every other arena access
  in this engine has always used.
* **Mutation**: only `MOVE` changes it. `JUMP` does not; `pc` semantics are
  untouched, deliberately, so a locality experiment can never be confused
  with a redefinition of an Agent API v1 observation field.
* **Visibility**: `Observation.locus` (`None` off-Ruleset) and the replay
  tick record's `locus` key (omitted off-Ruleset).

### Reach

One integer `R`, the **bounded reach**. The reachable window is the
`2R + 1` cells at circular distance `<= R` from the locus.

```text
circular_distance(a, b, N) = min((a - b) % N, N - (a - b) % N)
circular_displacement(d, N) = min(d % N, N - d % N)
```

Every range check goes through these, so the experiment cannot silently
measure a linear arena. `+N-1` and `-1` name the same one-cell step and
both normalize to magnitude 1.

### The three operations

```text
MOVE        displacement          legal iff circular_displacement(displacement) <= R
                                  locus <- (locus + displacement) % arena_size
LOCAL_READ  displacement          legal iff circular_displacement(displacement) <= R
                                  value = arena[(locus + displacement) % arena_size]
                                  sets last_read, register_a, zero_flag
LOCAL_WRITE displacement, value   legal iff circular_displacement(displacement) <= R
                                  arena[(locus + displacement) % arena_size] <- value
                                  routed through vm._wr8 like every other write
```

`R` governs both sensing and locomotion, so travel speed is `R` cells per
action and there is exactly one spatial constant, not two. Movement cost is
deliberately not a tunable dimension (Phase 2K).

### Out of reach

An out-of-reach `MOVE`/`LOCAL_READ`/`LOCAL_WRITE` is a **no-op that still
costs its action**, counted as a `reach_miss`. It is neither a forfeit
(which would make the corpus measure agent arithmetic bugs and mortality
rather than strategy) nor silently clamped (which would invent semantics
the agent never asked for). Nothing agent-visible changes, so a reach miss
can never be mistaken for a successful read of an empty cell.

An agent is told `R` at reset via `MatchContext.locality_reach` and sees its
locus on every action, so a reach miss is always avoidable. Across the whole
viable reach range (8…256) every one of the six corpus agents records
**zero** reach misses, which is what lets movement cost be attributed to the
mechanic rather than to agent defects.

### Action accounting

Unchanged. `instr_per_tick` actions per entrant per tick, through the same
`run_sequential_quota` scheduler. Movement spends from that budget; it does
not extend it. Tests assert that a MOVE-only entrant, a reach-miss-only
entrant and a NOP entrant all record the identical `cpu_total`, and that a
locality entrant gets exactly the same total actions as a Ruleset-v2 one.

### Everything else is inherited unchanged

Vulnerable core, `CORE_SIZE = 8`, `CORE_BEACON_BYTE = 0xCE`, the core-beacon
maintenance invariant, capture semantics and attribution, scheduling,
termination, scoring and winner resolution are Ruleset v2's, untouched. A
locality result that differed because the core mechanic also differed would
answer no question Phase 2 asks.

### Not implemented, deliberately

Velocity, acceleration, facing, terrain, movement points, a separate
movement-cost dimension, multiple loci, and any fog-of-war mechanic
distinct from locality itself (Phase 2F). Locality is the only source of
information scarcity in this experiment; §22 records what that produced.

---

## 5. Experimental Ruleset identity

```text
bytefray-rules-3-alpha1
```

Spelled `-alpha1`, following `bytefray-rules-2-alpha1`/`-alpha11` exactly
and for the same reason: the mechanic is a hypothesis under test, not a
matured contract. This is **not** `bytefray-rules-3`; no stable Ruleset 3
exists, and none is proposed by this phase.

* Registered under its own explicit key in `ruleset_policy._RULESET_POLICIES`,
  never aliased to or from any other identity.
* `supported_runtime_kinds = {"python"}` — Python-only (§ Python-only scope).
* Persisted as a first-class `ruleset_id` in every `result.json` and
  `replay.jsonl`, and as `rules_compatibility_id` in every `evaluation.json`.
  All 176 Phase 2 evaluations carry it; zero carry anything else.
* Deliberately **absent from every product CLI's `--ruleset` choices**.
  `bytefray agents evaluate --help` and `bytefray agents test --help` expose
  exactly the two product-facing identities, as they did before Phase 2, and
  a pre-existing test asserts this. The Phase 2 driver constructs its
  `EvaluationRequest` directly instead. An unstable research identity has no
  business appearing in a shipped command's help text.

Reach is per-match configuration under that identity, not a second
identity. It is identity-bearing where it is real: `reproducibility.
locality_reach` enters `canonical_match_id` when — and only when — the
resolved Ruleset has bounded locality, and `effective_conditions.
locality_reach` enters `evaluation_id` and the comparability fingerprint on
the same condition. Two locality evaluations differing only in `R` get
different ids; an explicit default reach and an omitted one share one id.

---

## 6. Compatibility assessment

**Nothing was bumped, and nothing needed to be.**

| axis | changed? | reasoning |
|---|---|---|
| Ruleset v1 (`bytefray-rules-1`) | **No** | Untouched. Not in `LOCALITY_RULESET_IDS`, not in the core-placement guard, not in the spread-start set. |
| Ruleset v2 (`bytefray-rules-2`) | **No** | Untouched. Verified by execution: a Ruleset-v2 match's `result.json` carries no `locality_reach` in `reproducibility`, no `locality` in any entrant's metadata, and its `replay.jsonl` contains no `locus` key. |
| Ruleset identity of anything existing | **No** | One new identity added; no existing one altered or aliased. |
| Agent API version | **No** | `AGENT_API_VERSION` stays 1. Two additive optional fields (`Observation.locus`, `MatchContext.locality_reach`), both `None` under every stable identity, and three additive `ActionKind` members no v1 agent emits. `docs/AGENT_API_V1.md` unmodified. |
| Result schema (`battle2.result`) | **No** | `reproducibility.locality_reach` and `entrants[].metadata.locality` are **omitted**, not written as null, off-Ruleset. `metadata` was already a documented free-form additive dict. |
| Replay schema (`battle2.replay`) | **No** | `AgentState.locus` round-trips but its key is omitted when `None`, so a non-locality replay record is byte-identical to one written before the field existed. Named `locus` rather than `position` specifically because `replay._agent_from_dict` already treats a `position` key as a historical alias for `pc`. |
| Evaluation schema (`bytefray.evaluation`) | **No** | Reach lives in the hashed/persisted *payload*, never on `EffectiveConditions` itself. Adding a dataclass field would have put `"locality_reach": null` into every historical evaluation's conditions and changed every `evaluation_id` ever computed. A test asserts the dataclass gained no field and that a Ruleset-v2 payload is identical to `asdict(conditions)`. |
| Agent trace (`bytefray.agent_trace`) | **No** | Not touched. The action kind and operand the trace already records are sufficient for §17. |
| Evaluation methodology identity | **Extended, scoped** | `is_ruleset_v2_methodology` now also admits the locality identity, so it runs under the identical standard placements, layouts, seed set and capture metrics the Ruleset-v2 control runs under. Without that the comparison would be confounded by methodology rather than by locality. No historical alpha identity was added. |

Empirical confirmation, not argument:

```text
Ruleset-v2 match with locality_reach=999 set on the request
  canonical_match_id  == the same request without it        -> True
  result_id           == the same request without it        -> True
370 pre-Phase-2 evaluation.json artifacts (schema v5 x79, v6 x291)  -> 370/370 load
176 Phase 2 artifacts through the same adapter                      -> 176/176 load
effective_conditions_payload(conditions, None) == asdict(conditions) -> True
```

### Pre-existing tests altered: three, and why

Three tests asserted the *exact field set* of `Observation` and
`MatchContext`. Their substantive guarantee — no field exposes anything
about another entrant — is untouched by two self-referential optional
fields (`locus` is this entrant's own position; `locality_reach` is a
Ruleset constant), and the forbidden-token sweep in
`test_ruleset_v2_alpha11.py` still runs over both unchanged. Each assertion
was rewritten to name the v1 set and the experimental set separately and
was **strengthened** with a check that both new fields default to `None`,
so a Ruleset-v1/v2 agent observes byte-identical values, not merely a
compatible shape. This is disclosed rather than absorbed; no other
pre-existing test was modified.

### Phase 2Q hard requirements

* Ruleset v1 execution unchanged — yes.
* Ruleset v2 execution unchanged — yes.
* Existing v1/v2 agents remain executable under their supported rules — yes;
  the frozen v2 population verifies 9/9 and reproduces its Phase 1 numbers.
* Historical artifacts readable — yes, 370/370.
* Canonical identities stable — yes.
* Phase 2 agents do not replace or modify their v2 ancestors — yes; the two
  populations share no agent id, which a test asserts.

---

## 7. Experimental agents

Six agents, pinned as the frozen `v3-phase2-locality` benchmark population
through the same content-addressed revision machinery Phase 0 used, in
`engine/src/battle_engine/data/benchmarks/v3_phase2_locality.json`. All six
verify 6/6. They live in their own resource directory and share no agent id
with the v2 population.

| agent | v2 lineage | role | locality-forced change | unavoidable redesign |
|---|---|---|---|---|
| `local_claimer` | `claimer` | blind expansion | absolute stride 101 → contiguous fill of `R` cells then `MOVE R`; one action in `R+1` now buys movement | none |
| `local_core_defender` | `core_defender` | blind defense + expansion | the ancestor interleaved defense and expansion action-by-action, which absolute addressing made free; here refreshing the core requires *standing near it*, so the interleave becomes a cycle: travel out, claim four windows, travel back, refresh eight core cells | **one, disclosed**: the ancestor's defense duty cycle was uniform in *time* (1 action in 4, forever); this one's is periodic in *space*. No locality-respecting agent can reproduce uniformity in time without also being immobile — which is the other defender's strategy, not this one's |
| `local_reactive_defender` | `reactive_core_defender` | reactive defense | binds itself to a guard band of `R - CORE_SIZE` cells from its core, so every core cell is readable on every action and detection latency is exactly the ancestor's; expansion is confined to ~`4R` cells | none — this is the one v2 defense archetype that ports without compromise, because its ancestor's behaviour was already spatially local and simply had no way to say so |
| `local_core_seeker` | `core_seeker` | sweeping search offense | golden-ratio stride scan → contiguous sweep of the reachable window, because remote cells cannot be inspected at all; an assault must now be preceded by an **approach**, since a hit up to `R` away cannot be struck from where it was noticed. `SCAN_EVERY`, `LOCK_RADIUS`, `ASSAULT_WINDOW` unchanged | none |
| `local_core_tracker` | `core_tracker` | probe-confirming search offense | same sweep change; probes are issued from *on top of* the candidate, since a candidate `R` away has probe points `R + 8` away. The RNG-drawn scan **anchor** becomes an RNG-drawn sweep **direction** — an anchor is an absolute address a locality entrant cannot choose | **one, disclosed**: the anchor→direction substitution above |
| `local_camper` | *none* | stationary control | n/a | n/a — deliberately has no ancestor. It exists to detect two predeclared ABANDON signals (turtling dominance, trivial universal policy) |

Two clamps are recorded rather than hidden. `ASSAULT_WINDOW` (16) and
`PROBE_OFFSETS` (`±4, ±8`) are clamped to the reachable window. At every
reach the experiment treats as viable (`R >= CORE_SIZE`) both clamps are
no-ops; below that they are the minimal locality-forced adaptation, so a
too-small-`R` condition is rejected for the mechanic's reason rather than
for an agent's arithmetic.

Every agent guards its own off-Ruleset case by emitting a locality action
anyway, so it forfeits visibly rather than behaving like some other agent.
Tests assert all six forfeit with `agent_action_invalid` under Ruleset v2.

---

## 8. Pilot design

Twelve conditions, two rosters, one seed, 400 ticks: **504 cells, 40.9 s,
0.19 GB.** Ten sweep `R` from 4 to 2048 at the density anchor (arena 4096,
budget 8); two check density and scale at `R = 64`.

Seven rejection rules were declared with the pilot, before it ran:
`attack_infeasible` (`R < CORE_SIZE`), `reach_collapse`
(`R >= arena_size/4`), `no_contact`, `movement_dominated` (mean MOVE share
`>= 0.50`), `crawl`, `turtle_dominant`, `runtime_pathology`.

| condition | arena | budget | R | captures | move share | mean ticks | sat% | rejected by |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `r4` | 4096 | 8 | 4 | 32 | 24.7% | 390 | 57.5 | `attack_infeasible`, `runtime_pathology` |
| `r8` | 4096 | 8 | 8 | 55 | 16.5% | 372 | 59.2 | — |
| `r16` | 4096 | 8 | 16 | 65 | 10.3% | 358 | 60.9 | — |
| `r32` | 4096 | 8 | 32 | 64 | 5.4% | 344 | 61.8 | — |
| `r64` | 4096 | 8 | 64 | 65 | 2.9% | 347 | 63.2 | — |
| `r128` | 4096 | 8 | 128 | 60 | 1.8% | 340 | 64.2 | — |
| `r256` | 4096 | 8 | 256 | 57 | 1.5% | 343 | 63.1 | — |
| `r512` | 4096 | 8 | 512 | 55 | 1.5% | 316 | 61.8 | — |
| `r1024` | 4096 | 8 | 1024 | 55 | 1.5% | 306 | 65.1 | `reach_collapse`, `turtle_dominant` |
| `r2048` | 4096 | 8 | 2048 | 63 | 1.2% | 258 | 65.4 | `reach_collapse` |
| `r64_a16384_b8` | 16384 | 8 | 64 | 9 | 2.7% | 400 | 34.1 | — |
| `r64_a1024_b2` | 1024 | 2 | 64 | 55 | 2.3% | 350 | 64.0 | — |

Two rejections, each for the reason its rule was written for.

**`r4` — `attack_infeasible` and `runtime_pathology` together.** The
pathology is attributable and instructive: `local_core_defender` recorded
84.2 reach misses per match, because refreshing its own core requires
writing offsets `0…7` and `R = 4` cannot reach `5, 6, 7`. At
`R < CORE_SIZE` even *blind* core defense is partially impossible by
construction. Every other agent recorded zero misses at `r4`.

**`r1024` and `r2048` — `reach_collapse`.** A quarter or more of the arena
reachable from one locus is not bounded locality in any strategically
meaningful sense. `r2048` (`R = arena/2`, every cell reachable from
anywhere) was retained as the explicitly labelled global-reach control the
definition allows, never as an experimental condition. `r1024` additionally
tripped `turtle_dominant`.

**Promotion.** The predeclared rule selects the smallest surviving reach
with captures occurring and MOVE share below 0.50, preferring a power of
two no larger than `arena_size/32`. Eligible: `r8, r16, r32, r64, r128`.

```text
R* = 8
```

This is the tightest locality the pilot admits, which is the right
scientific choice — a mechanic that cannot help at its strongest setting is
unlikely to help at weaker ones — and it is also the choice that most needs
a generalization check. §11 provides one.

---

## 9. Predeclared GO / MODIFY / ABANDON criteria

Committed in `v3_phase2_locality_corpus.json` with
`declared_before_interpretation: true` at `3be0bae`, **before** the pilot or
the main stage ran. The main-stage results were produced at `141e161`.
The git history shows the ordering; the gates were not weakened,
reinterpreted or supplemented afterwards.

The number the locality arm had to beat was recorded in the definition
itself: **on the six-condition ladder, the Ruleset-v2 control holds
criterion 2 at exactly one density value (S = 0.781).**

**GO** (G1 primary): G1 criterion 2 at ≥ 2 distinct densities; G2 ≥ 4 of 6
conditions at 5/5; G3 expansion loses its edge without becoming useless;
G4 search wins ≥ 25% and owns capture at ≥ 2 densities; G5 no archetype
≥ 90% in ≥ 2 dissimilar rosters; G6 context sensitivity survives; G7
pairwise-vs-group divergence ≥ 10 pp everywhere; G8 an observable
movement/reconnaissance tradeoff; G9 ≥ 4 rates disjoint from the
global-reach control; G10 encounters in ≥ 80% of search rosters.

**ABANDON**: A1 MOVE share ≥ 0.50; A2 criterion 2 at ≤ 1 density and no
other GO met; A3 ≥ 50% of search-roster cells tick-limited without capture;
A4 expansion top at ≥ 5 of 6 with search < 15% throughout; A5 search
strictly worse than the v2 control everywhere; A6 the trivial control leads
≥ 4 rosters; A7 no reach survives the pilot; A8 indistinguishable from the
global-reach control; A9 context sensitivity reduced on all three axes.

**Decision rule**: evaluate ABANDON first; if any holds → NOT VALIDATED.
Otherwise if G1 holds and ≥ 6 of G1–G10 hold → VALIDATED. Otherwise
PROMISING. INCONCLUSIVE only for a genuine inability to decide, never to
avoid an ABANDON result.

---

## 10. Final experimental conditions

Three arms at matched conditions.

**Arm L — bounded locality**, `bytefray-rules-3-alpha1` at `R* = 8`, six
conditions spanning `S ∈ {0.195, 0.781, 3.125}` and arenas 1024–16384.
Arena is held to `{1024, 4096, 16384}` on purpose: Phase 1 §10.1 measured
`territory_bucket = 64` collapsing the territory term to identically zero
at arena 256 and below, so Phase 2H's *preferred* approach was taken —
keep the range narrow enough that the existing bucket resolution stays
meaningful and change locality only. The coupled alternative (normalizing
buckets per arena) was not needed and was not used.

**Arm G — global-reach control** (Phase 2L Control 2), identical runtime,
identical population, identical conditions, `R = 2048 = arena/2` so every
cell is reachable from anywhere. This is what separates the effect of
bounded reach from the effect of having written new agents.

**Arm V — Ruleset-v2 historical control** (Phase 2L Control 1), read from
Phase 1's committed artifacts without re-execution. Phase 1 already
measured exactly these six conditions with the frozen v2 population.

**Equal action budget** (Phase 2L Control 3) holds throughout: no locality
condition gives any entrant extra actions, and an out-of-reach attempt
still costs its action.

---

## 11. Main corpus

Eleven three-entrant rosters structurally mirroring the eleven the Phase 0
control and Phase 1 grid both used (with `local_camper` in the seat hunter
held), plus three pairwise controls, at 3 seeds × 3 layouts × 6 seat
permutations.

| stage | evaluations | cells | wall clock | artifacts | non-zero exits |
|---|---:|---:|---:|---:|---:|
| pilot | 36 | 504 | 40.9 s | 0.19 GB | 0 |
| main | 112 | 5,184 | 337.6 s | 2.15 GB | 0 |
| reach diagnostic | 28 | 1,296 | 75.3 s | 0.51 GB | 0 |
| **total** | **176** | **6,984** | **453.8 s** | **2.85 GB** | **0** |

### The reach diagnostic, and why it exists

The pilot's promotion rule selects the *smallest* surviving reach, so the
main stage measured bounded locality at `R = 8 = CORE_SIZE` — one point on
the reach axis, and the most extreme one. Reporting a finding from a single
point without checking whether it generalizes would be dishonest.

The identical eleven-roster corpus was therefore re-run at `R = 64` and
`R = 256`, **after** the main stage was scored, declared as a separate
`reach_diagnostic` stage and **excluded from the gates by construction**
(the gate evaluator reads only the declared `main` stage). The ordering is
visible in git history: the diagnostic stage was added in `141e161`, after
the main stage's results existed. It could have overturned the reading; it
did not. §13 reports it in full either way.

---

## 12. Beta2 §17 rubric

The five criteria are used **verbatim**. Every number for both arms is
produced by `v3_phase1_ecology_rubric`'s own functions, imported rather
than reimplemented, with only their role/roster constants rebound. The
Ruleset-v2 arm is not merely comparable to the locality arm — it is scored
by literally the same lines.

One scoring note, disclosed: criterion 2 names its 1v1 pair ids as literals
inside the Phase 1 function. Rather than modify a committed Phase 1 tool,
the Phase 2 buckets alias their single expansion matchup into Phase 1's
first slot and leave the second **empty**. Phase 1 scored criterion 2's
first half as a disjunction over two expansion agents; Phase 2's population
has exactly one expansion archetype, so scoring it on one matchup is
strictly *stricter* than Phase 1's own reading, never looser.

| condition | arm | S | C1 | C2 | C3 | C4 | C5 | score | v2 C2 | v2 score |
|---|---|---:|:-:|:-:|:-:|:-:|:-:|---:|:-:|---:|
| `L_a4096_b2` | locality | 0.195 | PASS | **FAIL** | PASS | PASS | **FAIL** | **3/5** | FAIL | 4/5 |
| `L_a4096_b8` | locality | 0.781 | PASS | **FAIL** | PASS | PASS | **FAIL** | **3/5** | PASS | 5/5 |
| `L_a4096_b32` | locality | 3.125 | PASS | **FAIL** | PASS | PASS | **FAIL** | **3/5** | FAIL | 4/5 |
| `L_a1024_b2` | locality | 0.781 | PASS | **FAIL** | PASS | PASS | **FAIL** | **3/5** | PASS | 5/5 |
| `L_a16384_b8` | locality | 0.195 | PASS | **FAIL** | PASS | PASS | **FAIL** | **3/5** | FAIL | 4/5 |
| `L_a16384_b32` | locality | 0.781 | PASS | **FAIL** | PASS | PASS | **FAIL** | **3/5** | PASS | 5/5 |
| `G_a4096_b2` | global-reach control | 0.195 | PASS | **FAIL** | PASS | PASS | PASS | **4/5** | — | — |
| `G_a4096_b8` | global-reach control | 0.781 | PASS | **FAIL** | PASS | PASS | PASS | **4/5** | — | — |

**The primary gate fails in the worst available direction.** Phase 2 asked
whether locality could hold criterion 2 across a *wider* density band than
Ruleset v2's. Ruleset v2 holds it at one density on this ladder. Bounded
locality holds it at **zero**. The band did not widen; it vanished.

**Every locality condition scores 3/5**, against 4/5 or 5/5 for the matched
Ruleset-v2 conditions and 4/5 for the global-reach control on the identical
runtime and population. No locality condition scores as well as any
control.

### Criterion 2 detail

| condition | expansion vs search 1v1 | search caused max | non-search caused max | search owns capture |
|---|---:|---:|---:|:-:|
| `L_a4096_b2` | 100.0% | 11.1% | 22.2% | **no** |
| `L_a4096_b8` | 100.0% | 66.7% | 88.9% | **no** |
| `L_a4096_b32` | 100.0% | 57.4% | 44.4% | yes |
| `L_a1024_b2` | 100.0% | 72.2% | 77.8% | **no** |
| `L_a16384_b8` | 100.0% | 22.2% | 22.2% | **no** |
| `L_a16384_b32` | 100.0% | 66.7% | 61.1% | yes |
| `G_a4096_b2` | 100.0% | 13.0% | 70.4% | **no** |
| `G_a4096_b8` | 100.0% | 5.6% | 40.7% | **no** |

Both halves fail, and they fail differently.

*The matchup half* fails at **100.0%** everywhere — including under global
reach. `local_claimer` never loses a single 1v1 to `local_core_tracker` at
any condition in either arm. Under Ruleset v2 the same matchup goes the
other way (`claimer` at 23.3–33.3%). Because this holds under global reach
too, it is **not attributable to bounded locality**: it is a property of the
ported population, and §22 treats it as the phase's principal confound.

*The mechanism half* fails under bounded locality specifically, and that
failure is the interesting one — see §13.

### Criteria 1, 3 and 4

All three pass at every condition in both arms, exactly as Phase 1 found
for Ruleset v2. They remain non-discriminating.

Criterion 4 passes on pairwise-vs-group divergence, but the *kingmaking*
half of it is gone under bounded locality: at the reference condition the
passive third wins **0.0%** whether or not a search agent is present, so
there is no door for an elimination event to open (§15). Under Ruleset v2
the mechanism reproduced at every one of Phase 1's twenty conditions.

### Criterion 5

Fails at every locality condition and passes at both global-reach controls.
`local_claimer` reaches ≥ 90% in **five** dissimilar rosters at the
reference condition (100.0% in three of them) and `local_core_seeker` in
two. Bounded locality manufactures precisely the universal solution the
criterion exists to detect.

---

## 13. Search / offense versus expansion

| condition | search win | expansion win | defense win | search caused | expansion caused | defense caused |
|---|---:|---:|---:|---:|---:|---:|
| `L_a4096_b2` | 44.4% | 97.6% | 0.0% | 3.7% | 15.9% | 0.0% |
| `L_a4096_b8` | 53.1% | 88.9% | 0.0% | 30.0% | 55.0% | 0.0% |
| `L_a4096_b32` | 50.6% | 88.9% | 0.4% | 21.6% | 30.7% | 0.2% |
| `L_a1024_b2` | 50.2% | 84.1% | 5.9% | 33.1% | 42.1% | 2.0% |
| `L_a16384_b8` | 44.7% | 97.6% | 0.0% | 6.6% | 11.1% | 0.0% |
| `L_a16384_b32` | 50.8% | 88.9% | 0.0% | 29.0% | 40.2% | 0.0% |
| `G_a4096_b2` | 2.7% | 65.6% | 18.5% | 7.0% | 12.7% | 5.6% |
| `G_a4096_b8` | 17.9% | 38.9% | 47.4% | 2.5% | 3.2% | 12.4% |

### 13.1 The mechanism: bounded reach forces contiguous claiming

This is the phase's central structural finding, and it is the direct
inversion of the hypothesis.

Under Ruleset v2 a claiming agent writes wherever it likes, one cell per
action. `claimer`'s stride of 101 spreads its claims sparsely across the
whole arena, so it passes *through* an 8-cell core only rarely and never
writes eight consecutive cells anywhere.

Under bounded locality it cannot do that. Cheap claiming is necessarily
**contiguous**: filling the `R` cells ahead of the locus and stepping costs
`1` action per cell plus `1/(R+1)` overhead, while sparse claiming would
cost a MOVE per cell — halving throughput. So every rational locality
expander sweeps a solid band.

A solid band of writes over a fixed-size 8-cell core captures it. Blind
expansion therefore becomes an **incidental core-killer**, and the capture
attribution shows exactly that: at the reference condition `local_claimer`
causes **88.9%** of captures in `lclaimer_ldefender_lreactive` while
holding 68.2% of the arena, and non-search capture-caused exceeds search
capture-caused at four of six locality conditions.

Criterion 2's second half — "search must be the reason cores fall" — is not
merely lost to tuning here. It is structurally unavailable, because
bounding reach is what forces the expander to sweep through cores in the
first place.

### 13.2 Search collapses into expansion rather than coexisting with it

The corollary is worse. Under bounded locality a searcher must also sweep
contiguously — remote cells cannot be inspected at all — so its behaviour
becomes the expander's behaviour with one action in three spent reading
instead of claiming. It is **expansion minus a third of its throughput,
plus better aim**.

The two strategic axes Phase 2 hoped to make simultaneously viable did not
become simultaneously viable. They *merged*.

### 13.3 The reach ladder

The main stage measured `R = 8`. The post-hoc diagnostic (§11) measured the
identical corpus at `R = 64` and `R = 256`. Together with the global-reach
control this gives four points spanning a 256× reach range at one density.

| R | R/arena | stage | expansion win | defense win | search win | expansion caused | search caused | defense move share | expansion move share | C5 | score |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|:-:|---:|
| 8 | 1/512 | main | 88.9% | 0.0% | 53.1% | 55.0% | 30.0% | 41.5% | 11.1% | **FAIL** | 3/5 |
| 64 | 1/64 | diagnostic | 84.1% | 15.2% | 39.9% | 39.2% | 25.1% | 4.6% | 1.5% | **FAIL** | 3/5 |
| 256 | 1/16 | diagnostic | 84.1% | 26.3% | 27.6% | 28.3% | 31.5% | 0.5% | 0.4% | **FAIL** | 3/5 |
| 2048 | 1/2 | main | 38.9% | 47.4% | 17.9% | 3.2% | 2.5% | 0.0% | 0.0% | PASS | 4/5 |

Every column is monotone in reach, and the finding generalizes: across a
32× range of *bounded* reaches the rubric score is 3/5 and criterion 5
fails at all of them. The ecology only recovers when reach stops being
bounded at all.

---

## 14. Defense

Defense is where bounded locality does its clearest damage, and the
mechanism is precise.

| R | defense win rate | defense MOVE share |
|---:|---:|---:|
| 8 | **0.0%** | 41.5% |
| 64 | 15.2% | 4.6% |
| 256 | 26.3% | 0.5% |
| 2048 (global) | 47.4% | 0.0% |

At the reference condition the two defense archetypes fail in opposite,
equally instructive ways.

* **`local_reactive_defender` is invulnerable and worthless.** It suffers
  **0.0%** capture in almost every roster — it never leaves reach of its
  core, so it detects and repairs every attack with the ancestor's exact
  latency. It also holds **0.3%** of the arena and wins **0.0%**. At
  `R = CORE_SIZE` the guard band is one cell wide: zero-latency defense
  requires zero mobility, and zero mobility means zero territory.
* **`local_core_defender` is mobile and dead.** It suffers **88.9%**
  capture, because it is away commuting when the expander arrives. It
  spends **41.5%** of its entire budget on movement — and that share grows
  with its frontier, since each excursion must travel further out and
  further back.

The general statement is the important one. **Bounded locality taxes
exactly the strategies that must be somewhere, and barely taxes the one
that never needs to be anywhere in particular.** Blind expansion has no
home to defend, so bounding presence costs it 11.1% of its actions at
`R = 8` and 0.4% at `R = 256`. Every strategy with a spatial commitment —
guard your core, return to it, keep it in view — pays the full tax.

This is the exact opposite of the governing hypothesis, which predicted
that making presence scarce would erode expansion's advantage. Scarcity of
presence penalizes commitment, and expansion is the archetype with none.

---

## 15. Pairwise and group behaviour

Pairwise-vs-group divergence survives everywhere: **≥ 10 pp at every
locality condition** (gate G7 holds). Group outcomes are not repeated 1v1,
which would have been the clearest sign of lost depth, and it is not lost.

Kingmaking, the other half of criterion 4, does not survive — see §12.
Under Ruleset v2 the passive third *wins* when a search agent is present
and drops to 0.0% when it is removed: at the matched control condition
`a4096_b8`, `core_defender` wins 44.4% with `core_tracker` in the roster
and 0.0% without, and `reactive_core_defender` 38.9% and 0.0%. Phase 1
reproduced that drop at 39 of 40 roster/condition pairs. Under bounded locality the passive third wins
**0.0% in both cases**, so the mechanism check is not merely weakened but
vacuous — there is no door for an elimination event to open, because
`local_claimer` wins essentially every roster it joins whether anything
gets eliminated or not.

---

## 16. Ranking perturbation and context effects

Measured with Phase 1's own `ranking_perturbation`, against the locality
reference condition.

| condition | leader changes | pairwise reversals | strict | rates moved | mean abs move |
|---|---:|---:|---:|---:|---:|
| `L_a4096_b2` | 1/11 | 1/33 | 0 | 4/33 | 6.8 pp |
| `L_a4096_b8` | 0/11 | 0/33 | 0 | 0/33 | 0.0 pp (reference) |
| `L_a4096_b32` | 0/11 | 0/33 | 0 | 1/33 | 1.3 pp |
| `L_a1024_b2` | 1/11 | 2/33 | 0 | 0/33 | 4.5 pp |
| `L_a16384_b8` | 1/11 | 1/33 | 0 | 4/33 | 6.4 pp |
| `L_a16384_b32` | 0/11 | 1/33 | 0 | 2/33 | 1.7 pp |
| `G_a4096_b2` | **8/11** | **16/33** | **7** | **19/33** | **37.8 pp** |
| `G_a4096_b8` | **9/11** | **15/33** | **4** | **25/33** | **41.4 pp** |

Two readings, both unfavourable.

**Bounded locality flattens the ecology's response to its own parameters.**
Across a 16× arena range and a 16× density range the locality arm moves
0–1 leaders, 0–2 pairwise relationships, **zero** statistically robust
reversals, and 1.3–6.8 pp of mean rate movement. Phase 1's Ruleset-v2 grid
moved 3–9 leaders per condition with 8.9–26.3 pp mean movement. Under
locality the outcome barely depends on the conditions at all — because one
archetype wins almost everything almost everywhere.

**Removing the bound changes everything.** The global-reach control differs
from the locality reference by 8–9 leader changes, 15–16 reversals (4–7 of
them beyond both Wilson intervals), and ~40 pp of mean rate movement. Gate
G9 holds decisively at 25 disjoint rates: bounded reach is unambiguously
doing the work. That rules out the "it was just the new agents"
explanation — and makes the negative result attributable to the mechanic.

### Context sensitivity

| condition | seat | layout | seed |
|---|---:|---:|---:|
| `L_a4096_b2` | 33.3 | 33.3 | 33.3 |
| `L_a4096_b8` (reference) | 38.9 | 16.7 | 16.7 |
| `L_a4096_b32` | 50.0 | 33.3 | 16.7 |
| `L_a1024_b2` | 61.1 | 38.9 | 22.2 |
| `L_a16384_b8` | 38.9 | 33.3 | 22.2 |
| `L_a16384_b32` | 33.3 | 11.1 | 16.7 |
| `G_a4096_b8` | 33.3 | 50.0 | 16.7 |
| **Ruleset v2 `a4096_b8`** (Phase 1 §11) | **100.0** | **33.3** | **27.8** |

All three axes stay non-zero everywhere, so criterion 3 passes. But at the
reference condition every axis is below the Ruleset-v2 control's, which is
what ABANDON criterion A9 tests, and A9 holds. Against the *population-
controlled* comparison the picture is mixed rather than uniform (seat
38.9 vs 33.3 higher, layout 16.7 vs 50.0 much lower, seed equal) — §22
records that A9 as predeclared is a cross-population comparison, and §23
records that the verdict does not rest on it.

---

## 17. Conditional action behaviour

Phase 2N item 3 asks whether a locality-aware strategy conditions its
behaviour on observations rather than performing a fixed action mix.
`local_core_tracker`, traced against three opponents at identical
conditions (arena 4096, budget 8, `R = 64`, seed 5):

| opponent | MOVE | LOCAL_READ | LOCAL_WRITE | reads/action | moves/action | assault bursts |
|---|---:|---:|---:|---:|---:|---:|
| `local_camper` | 44 | 706 | 1466 | 0.319 | 0.020 | 7 |
| `local_claimer` | 33 | 687 | 1368 | 0.329 | 0.016 | 0 |
| `local_core_defender` | 121 | 836 | 2067 | 0.276 | 0.040 | **50** |

The behaviour is genuinely conditional. The same agent produces zero
assault bursts against one opponent and fifty against another, and its
movement share varies by 2.5× purely from what it read. The
`move → inspect → detect → approach → attack` sequence the phase hoped to
see does occur, and the engine's own trace records it.

That this is true and the mechanic still fails is the point worth keeping:
**activity is not depth.** Phase 1 drew that distinction and Phase 2
reproduces it from the other side — richly conditional individual behaviour
inside a collapsed ecology.

---

## 18. Spatial behaviour

At the reference condition, per strategic role:

| role | move share | read share | write share | moves | distinct loci | max distance from own core | encounter ticks |
|---|---:|---:|---:|---:|---:|---:|---:|
| expansion | 11.1% | 0.0% | 88.9% | 327 | 328 | 1939 | 2.3 |
| search | 9.8% | 26.6% | 63.6% | 259 | 259 | 1706 | 6.8 |
| defense | **41.5%** | 12.5% | 45.9% | 1070 | **51** | **198** | 2.0 |
| control | 0.0% | 0.0% | 100.0% | 0 | 1 | 0 | 6.3 |

The instrumentation is deterministic, engine-side, and additive: movement
count, cells travelled, distinct loci occupied, reach misses, local reads
and writes, distance from own core (sum and max), encounter ticks, and
ticks with an opponent core in reach. All of it is recorded per entrant in
`result.json`'s existing free-form `metadata` block and read from there by
research tooling, exactly as Phase 1 read `cpu_total` — no production
analysis record was widened for one experiment's benefit.

The table is the §14 finding in one line: the defenders move four times as
much as the expander while covering a fifteenth of the ground.

**Encounters are rare in absolute terms** — 2–7 ticks of 400 with an
opponent inside reach, against 200–390 under global reach — but they are
not *absent*: gate G10 holds at **100%**, with encounters occurring in
every search-containing roster at every locality condition, and captures
occur at 4.2–50.2% of entrant slots. So the negative result is not "the
agents never met".

The `interaction_starved` flag fires at the two lowest-density conditions,
`L_a4096_b2` and `L_a16384_b8`. One of those is a fair comparison and one
is not, and the difference is worth recording: Phase 1's Ruleset-v2 control
was *also* starved at `a16384_b8`, but it carried **no flag at all** at
`a4096_b2` (§6 of the Phase 1 report). At that density, bounded locality
starves interaction where Ruleset v2 did not.

---

## 19. Translation and placement sensitivity

Phase 2J: *measure* it, do not claim it. `spread` and `spread-shifted`
have identical seat gaps and differ only by a half-gap phase shift, so the
win-rate difference between them is translation sensitivity with relative
geometry held fixed. `close` changes the geometry and is reported
separately, never folded in.

| arm | condition | translation mean | translation max |
|---|---|---:|---:|
| locality | `L_a4096_b8` | **0.7 pp** | 11.1 pp |
| locality | every other L condition | **0.0 pp** | 0.0 pp |
| global-reach control | `G_a4096_b2`, `G_a4096_b8` | **0.0 pp** | 0.0 pp |
| reach diagnostic | `D_r64`, `D_r256` | **0.0 pp** | 0.0 pp |
| **Ruleset v2** | `a4096_b2` | 5.4 pp | 16.7 pp |
| **Ruleset v2** | `a4096_b8` | 7.7 pp | 33.3 pp |
| **Ruleset v2** | `a4096_b32` | **15.2 pp** | **66.7 pp** |
| **Ruleset v2** | `a1024_b2` | 9.1 pp | 50.0 pp |
| **Ruleset v2** | `a16384_b8` | 5.4 pp | 33.3 pp |
| **Ruleset v2** | `a16384_b32` | 6.7 pp | 33.3 pp |

(The Ruleset-v2 figures were computed by the same helper over Phase 1's
committed artifacts, read-only; nothing was re-executed.)

**This is the phase's one clearly positive secondary result.** Absolute-
addressing Ruleset-v2 agents move 5.4–15.2 pp on average, up to 66.7 pp,
under a pure translation of the layout. Relative-addressing agents move
0.0–0.7 pp. Placement sensitivity essentially vanishes.

The attribution matters, and it is not what the hypothesis predicted: the
global-reach control shows **0.0 pp too**. The invariance comes from
writing agents in *relative* terms, not from *bounding* their reach.
Relative addressing buys translation invariance; the bound buys nothing
extra. That distinction survives the verdict and is carried forward in §24.

Geometry sensitivity (`spread` vs `close`) remains real in both arms
(1.3–22.6 pp), so the measure is not simply saturated at zero.

---

## 20. Performance and artifact cost

| measure | value |
|---|---|
| cells executed | **6,984** (504 pilot + 5,184 main + 1,296 diagnostic) |
| evaluations | 176 |
| workers | 4 |
| total wall clock | **453.8 s (7.6 min)** |
| total artifacts | **2.85 GB** |
| failed / drifted / corrupted cells | **0** |
| non-zero evaluation exits | **0** |
| cheapest / costliest condition | pilot `r64_a1024_b2` 1.1 s per evaluation / main `L_a16384_b32` ~7.5 s per group evaluation |

Against Phase 1's reference (12,960 cells, 1,090.5 s, 12.73 GB): per-cell
cost is comparable and artifact volume is again dominated by replay size,
exactly as Phase 0 predicted. Locality instrumentation cost is negligible:
the per-tick telemetry is `O(entrants²)` integer arithmetic on three
entrants, and the per-entrant `locality` metadata block adds ~300 bytes to
a ~4 KB `result.json`. Nothing was optimized; no region presented a
blocker. Phase 2 was cheap to run and would have been cheap to abandon at
any point, which was the intent.

---

## 21. Agent API implications

Phase 2P asks, separately from the verdict: **what actual incompatibility
with Agent API v1 did locality require?**

The answer, from evidence rather than from a decision made in advance:

**Additive capability only.** Two optional observation/context fields
(`Observation.locus`, `MatchContext.locality_reach`), both `None` under
every stable Ruleset, and three new action kinds no v1 agent emits. No v1
operation changed meaning. `READ 100` still reads absolute address 100
under every Ruleset that admits it.

**One genuinely incompatible thing, and it is not an API change.** The
locality Ruleset *forbids* `READ`/`WRITE`. That is a Ruleset-level
execution restriction, not a redefinition — the same category as
`bytefray-rules-2` rejecting VM entrants — and it is what makes a v2 agent
fail loudly rather than silently mean something else.

**Semantic redefinition was not required.** The Option B shape (`READ`
meaning "read at `locus + operand`") is the one that would have been strong
evidence for Agent API v2, and Phase 2 deliberately avoided it and still
conducted the experiment honestly.

Since the mechanic is not validated, **no Agent API v2 is recommended and
none is declared.** If a future spatial thesis is pursued, the recorded
finding is that a locality-style mechanic is reachable additively; the
question of whether a locality-*native* API would be nicer is a design
question with no evidence behind it yet.

---

## 22. Known limitations and confounds

Stated plainly, because two of them are load-bearing.

### 22.1 The ported population does not reproduce the v2 counter-strategy result

This is the phase's principal confound. `local_claimer` beats
`local_core_tracker` **100.0%** of the time in 1v1 — at every condition, in
**both** arms, including at global reach. Under Ruleset v2 that matchup
goes the other way (`claimer` 23.3–33.3%).

Consequence: criterion 2's *matchup* half cannot be meaningfully compared
against the Ruleset-v2 control, because the ported population fails it even
when reach is effectively unbounded. Any claim of the form "locality broke
criterion 2's first half" would be false.

What survives the confound, and why:

* The **L-versus-G** comparison is population-controlled by construction —
  identical agents, identical rosters, identical conditions, only the bound
  differs. It shows 4/5 → 3/5, criterion 5 passing → failing, defense
  47.4% → 0.0%, and 25 win rates moving beyond both Wilson intervals. Every
  headline finding in §13 and §14 rests on this comparison, not on the
  cross-population one.
* The **mechanism** identified in §13.1 is structural rather than
  agent-specific: bounding reach makes cheap claiming contiguous, and
  contiguous claiming over a fixed-size core captures it. No agent design
  removes that; a sparse-claiming expander exists but pays double for every
  cell, and the corpus shows the dense one winning.
* The §14 defense finding is likewise structural: at `R` near `CORE_SIZE`,
  zero-latency core defense requires near-zero mobility, and mobility is
  what territory costs.

A stronger locality searcher — one that samples by `MOVE R`, `LOCAL_READ 0`
rather than sweeping every cell — could plausibly fix criterion 2's first
half. It could not fix the second half or the defense collapse, because
those are consequences of what bounded reach does to the *expander* and the
*defender*, not to the searcher.

### 22.2 A9 is a cross-population comparison

ABANDON criterion A9 compares the locality arm's context sensitivity
against the Ruleset-v2 control's, i.e. across populations. As predeclared
it holds (all three axes lower). The population-controlled comparison
against the global-reach control is mixed rather than uniform. §23 records
that the verdict does not depend on A9.

### 22.3 R* = 8 is the tightest surviving reach

The pilot's predeclared promotion rule selects the smallest viable reach,
so the main stage measured the mechanic at its most extreme setting. The
post-hoc reach diagnostic (§11, §13.3) checks whether the finding
generalizes across a 32× reach range; it does. Without that diagnostic the
result would have been a single point and should not have been trusted.

### 22.4 Scoring resolution

Phase 1 §10.1's `territory_bucket = 64` confound was bounded rather than
eliminated: arena is held to 1024–16384 (16/64/256 buckets), so survival's
share of score varies from 19.1% to 4.6% across the corpus. Phase 2H's
preferred approach, and the coupled alternative was not needed. The
confound is fully recoverable from every artifact's persisted
`effective_conditions.weights`.

### 22.5 What was not measured

The tick-by-tick approach to saturation (Phase 1 §10's own gap) is still
unmeasured. Per-tick loci *are* now recorded in every locality replay, so a
future phase could reconstruct trajectories without new instrumentation —
but nothing here did, and no Replay Viewer work was done.

### 22.6 One archetype has no locality port

Ruleset v2's `hunter` (dispersed expansion) has no counterpart in the
Phase 2 population; `local_camper` occupies its roster seat as a control.
The Phase 2 population therefore has one expansion archetype where the v2
population had two. This is disclosed in the corpus definition and is why
criterion 2's first half is scored on one matchup (§12).

---

## 23. Phase 2 verdict

### **LOCALITY NOT VALIDATED — ABANDON CURRENT V3 THESIS**

Gate evaluation, mechanically applied by
`tools/v3_phase2_locality_rubric.py` from the predeclared definition:

```text
GO held:      4/10   (G7, G8, G9, G10)
GO failed:    G1 (primary), G2, G3, G4, G5, G6
ABANDON held: A9
Decision rule step 1: an ABANDON criterion holds -> NOT VALIDATED
```

The verdict is over-determined; it does not rest on A9. Even setting A9
aside entirely, **the primary gate G1 fails in the worst available
direction**. Phase 2 asked whether bounded locality could hold §17
criterion 2 across a *wider* density band than Ruleset v2's narrow one.
Ruleset v2 holds it at one density on this ladder. Bounded locality holds
it at **zero**, at every reach from 1/512 to 1/16 of the arena.

The evidence, in the order it forces the conclusion:

1. **The two strategic axes merged rather than coexisting.** Bounded reach
   forces every claiming agent to sweep contiguously, and a searcher under
   bounded reach is the same contiguous sweep with a third of its
   throughput spent reading. Search became a worse expander with better
   aim, not a second viable axis (§13.2).

2. **Blind expansion became the dominant core-capture mechanism, by
   construction.** Contiguous claiming over a fixed-size 8-cell core
   captures it incidentally. `local_claimer` causes 88.9% of captures at
   the reference condition while holding 68.2% of the arena. Criterion 2's
   mechanism half is not lost to tuning here — bounding reach is what
   creates the bulldozer (§13.1).

3. **Locality penalizes commitment, which is the opposite of the
   hypothesis.** The thesis predicted that making presence scarce would
   erode expansion's advantage. It did the reverse: expansion has no home
   to defend and pays 0.4–11.1% of its budget for movement, while the
   defenders pay up to 41.5% and are either invulnerable-and-worthless
   (0.0% capture suffered, 0.3% territory, 0.0% wins) or mobile-and-dead
   (88.9% capture suffered). Defense win rate is monotone in reach:
   0.0% → 15.2% → 26.3% → 47.4% as R goes 8 → 64 → 256 → global (§14).

4. **It is bounded reach doing this, not the new agents.** The
   population-controlled global-reach control — identical runtime,
   population, rosters and conditions, only the bound removed — scores 4/5,
   passes criterion 5, and gives defense 47.4%. Twenty-five of thirty-three
   roster/agent win rates move beyond both Wilson intervals between the two
   arms (§16).

5. **The mechanic manufactured a universal solution.** Criterion 5 fails at
   every locality condition and at no control condition. `local_claimer`
   reaches ≥ 90% in five dissimilar rosters, three of them at 100.0%.

6. **It flattened the ecology's response to its own parameters.** Across a
   16× arena range and a 16× density range the locality arm produces zero
   statistically robust reversals and 1.3–6.8 pp of mean rate movement.
   Ruleset v2 across comparable ranges produced 8.9–26.3 pp (§16).

**What would have changed this verdict.** A region where criterion 2 held
at two or more densities with search both winning matchups and owning
capture attribution, and no archetype running away with dissimilar rosters.
The corpus contains no such region at any tested reach. The closest
approach is `L_a4096_b32` and `L_a16384_b32`, where search *does* own the
capture mechanism (57.4% vs 44.4%, 66.7% vs 61.1%) — but the matchup half
fails at 100.0% there too, and criterion 5 fails at both. That is recorded
as the near-miss it is, not rounded away.

**Why not PROMISING.** Every MODIFY criterion was checked. The failure is
not a narrow-`R` problem (M2): the reach ladder shows it across a 32× range
and the trend is monotone toward *global* reach, which is the absence of
the mechanic. It is not an addressing-semantics problem (M3): zero reach
misses were recorded anywhere in the viable range. It is not one small
correction away (M5): the two decisive failures are consequences of what
bounding reach does to claiming and to spatial commitment, and no small
mechanic correction addresses either without adding compensating machinery
— which Phase 2's own scope rule says would itself be evidence about
locality's complexity cost.

**Why not INCONCLUSIVE.** The confound in §22.1 is real and it does
invalidate the cross-population criterion-2 comparison. But it does not
prevent a decision: the population-controlled L-versus-G comparison is
clean, the mechanism is identified and structural, and the finding
generalizes across reach. Phase 2 could decide, and did.

---

## 24. What happens next

Per the governing instruction for a NOT VALIDATED verdict: **the
locality/multiplicity program stops here.** Multi-locus research is not
recommended and is not begun. Nothing in this phase is promoted; the
experimental Ruleset stays experimental.

### Evidence that should be reconsidered before choosing another v3 thesis

1. **The real Ruleset-v2 problem may be the fixed-size core, not
   omnipresence.** Phase 1 §9.1 already found that `CORE_SIZE = 8` in an
   arena of arbitrary size is the source of the only genuine scale effect
   in its grid. Phase 2 now adds that the same fixed-size core is what lets
   a contiguous sweeper capture cores incidentally. Two phases have now
   independently implicated the core model. A thesis about what a core *is*
   — scaled, distributed, or defined by something other than a fixed window
   of addresses — has more evidence behind it than locality ever did.

2. **Territory scoring rewards throughput, and every mechanic that costs
   throughput loses to it.** Both the locality defenders lost on territory
   while succeeding at defense. Whatever mechanic is tried next, if it
   taxes actions it will be measured against an opponent that spends all of
   them claiming. That is a scoring-model observation, and Phase 1 §10.1
   already flagged the bucket resolution from a different direction.

3. **Relative addressing is worth keeping without locality.** §19's
   translation-invariance result is real, cleanly measured, and attributable
   to relative addressing rather than to bounded reach. If placement
   sensitivity is ever considered a defect worth fixing, this phase already
   measured the fix and it does not require locality.

4. **Activity is still not depth.** §17 shows genuinely conditional,
   observation-driven agent behaviour inside an ecology that scores 3/5.
   Any future phase should keep the Phase 1/Phase 2 discipline of scoring
   the ecology rather than admiring the traces.

### The next research question this phase justifies

Stated, **not** implemented:

> Is Ruleset v2's residual single-axis structure a consequence of the
> *core model* — a fixed 8-cell window at a fixed address, capturable by
> any writer that passes over it — rather than of entrant omnipresence?
> Specifically: does a core whose size, location, or definition is not a
> fixed contiguous window make dedicated offense mechanically distinct from
> incidental territorial sweeping?

Phase 1 implicated the fixed-size core through a scale effect. Phase 2
implicated it again through a capture-attribution effect, under a mechanic
that was supposed to be about something else entirely. That is two
independent lines of evidence pointing at the same constant, and neither
phase set out to find it.

---

## 25. Files changed

| file | change |
|---|---|
| `engine/src/battle_engine/ruleset_policy.py` | `bytefray-rules-3-alpha1` identity + policy, registered |
| `engine/src/battle_engine/agent_api.py` | `Observation.locus`, `MatchContext.locality_reach`, three experimental `ActionKind` members |
| `engine/src/battle_engine/python_runtime.py` | the whole locality mechanic: constants, circular geometry, `PythonEntrantState.locus` + telemetry, ruleset-gated `validate_action`, `apply_action` locality branch, per-tick telemetry, controller wiring |
| `engine/src/battle_engine/supervised_runtime.py` | identical locality resolution and wiring for the supervised path |
| `engine/src/battle_engine/agent_worker.py` | additive `locality_reach`/`locus` wire keys, backward-tolerant |
| `engine/src/battle_engine/match_service.py` | `MatchRequest.locality_reach`, shared `_reproducibility` payload, resolved-reach helper, core-placement guard extension, per-entrant locality metadata |
| `engine/src/battle_engine/placement.py` | spread-start default extended to the locality identity |
| `engine/src/battle_engine/replay.py` | `AgentState.locus`, omitted when `None` |
| `engine/src/battle_engine/telemetry.py` | per-tick `locus` in the agent snapshot, omitted when `None` |
| `engine/src/battle_engine/agent_evaluation.py` | `EvaluationRequest.locality_reach` + resolution, `effective_conditions_payload`, methodology gate, validation, execution/worker/resume threading, disclosure |
| `engine/src/battle_engine/agent_test.py` | `locality_reach` threaded through `test_agent`/`test_agents` |
| `engine/src/battle_engine/evaluation_worker.py` | additive `locality_reach` wire key |
| `engine/src/battle_engine/evaluation_history/cli.py` | experimental-condition disclosure in `show` |
| `engine/src/battle_engine/data/v3_locality_agents/*` | **new** — six experimental agents |
| `engine/src/battle_engine/data/benchmarks/v3_phase2_locality.json` | **new** — the frozen six-member population |
| `engine/src/battle_engine/data/benchmarks/v3_phase2_locality_corpus.json` | **new** — the predeclared corpus and gates |
| `tools/v3_phase2_locality_corpus.py` | **new** — corpus `run`/`analyze` driver |
| `tools/v3_phase2_locality_rubric.py` | **new** — §17 scoring and gate evaluation |
| `engine/tests/test_v3_phase2_locality_runtime.py` | **new** — 64 tests |
| `engine/tests/test_v3_phase2_locality_evaluation.py` | **new** — 22 tests |
| `engine/tests/test_v3_phase2_locality_agents.py` | **new** — 70 tests |
| `engine/tests/test_ruleset_v2_alpha11.py` | pre-existing test updated — see §6 |
| `engine/tests/test_v2_alpha2_reactive_defender.py` | pre-existing test updated — see §6 |
| `engine/tests/test_v2_alpha8_core_tracker.py` | pre-existing test updated — see §6 |
| `docs/V3_PHASE2_LOCALITY_FEASIBILITY.md` | **new** — this report |

## 26. Validation

| check | result |
|---|---|
| Full test suite (`python -m pytest`) | **2151 passed, 14 skipped, 2 deselected** in 271 s. Phase 1's measured baseline was 1995 passed with the same 14/2 — the delta is exactly the 156 new tests, with no pre-existing test removed |
| Focused Phase 2 tests | 156 passed (64 runtime + 22 evaluation + 70 agents) |
| Focused Phase 0 + Phase 1 tests | 59 passed, unchanged |
| Pre-existing tests altered | 3, disclosed in §6, each strengthened rather than weakened |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success, 81 source files |
| `mypy client/src/battle_client` | Success, 12 source files |
| Historical artifacts still load | **370/370** pre-Phase-2 `evaluation.json` (schema v5 ×79, v6 ×291) through `adapt_any`, 0 failures |
| Phase 2 artifacts load | 176/176 through the same adapter |
| Frozen v2 population | **9/9** verify — untouched |
| Frozen locality population | **6/6** verify |
| Ruleset-v2 identity unchanged | `effective_conditions_payload(conditions, None) == asdict(conditions)`; identical conditions fingerprint; a stray `locality_reach` on a v2 request produces an identical `match_id` and `result_id` |
| Deterministic locality reproduction | Two independent runs → identical `evaluation_id`, `match_id`, `result_id`, replay bytes; three runs → one replay digest |
| Corpus reproduces | A re-executed `L_a4096_b8` roster evaluation matches the committed one on `evaluation_id` and **54/54** cells (`match_id` + outcome), 0 failed/corrupted/drifted |
| Serial ≡ parallel | `--workers 1` identical to `--workers 3` at a locality condition |
| Resume safe | Resuming a completed locality evaluation changes nothing, no `resumed_result_mismatch` |
| Experimental identity persists | 176/176 Phase 2 evaluations record `rules_compatibility_id = bytefray-rules-3-alpha1` and their exact `locality_reach` |
| Reach is identity-bearing | Changing `R` changes `canonical_match_id` and `evaluation_id`; explicit default ≡ omitted |
| Pilot and main separated | Distinct stages, distinct directories, distinct declared conditions; the reach diagnostic is a third stage excluded from the gates |
| Gates predate results | Declared at `3be0bae` with `declared_before_interpretation: true`; main results produced at `141e161` |
| Non-zero evaluation exits | 0 across all 176 evaluations |
| Out-of-scope mechanics | none present — no multiple loci, locus identity, replication, SPAWN, specialization, shared state, messaging, fog of war, ATTACK, energy, territory decay, Elo, clustering, BFScript, VM/Redcode locality, Designer or Replay Viewer change, or distributed evaluation |

## 27. Commits

| SHA | message |
|---|---|
| `ac1102b` | feat(rules): add the experimental bytefray-rules-3-alpha1 locality runtime |
| `044ef20` | feat(research): add the v3 Phase 2 locality-aware experimental agents |
| `3be0bae` | feat(research): declare the v3 Phase 2 locality corpus and its gates |
| `141e161` | feat(research): score the Phase 2 locality corpus and its predeclared gates |
| *(this report)* | docs(v3): record the Phase 2 locality feasibility findings |

Nothing merged to `main`, nothing tagged, nothing published. Ruleset v1,
Ruleset v2, the `v2.0.0` tag, `main`, `origin/main`, and the Phase 0 and
Phase 1 branches and reports are all unchanged.
