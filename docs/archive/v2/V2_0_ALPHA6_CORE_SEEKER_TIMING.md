# Bytefray v2.0.0-alpha.6 — Core Seeker Scan-Timing and Geometry Characterization

This is a mechanistic characterization pass, not a mechanic, scoring, or
agent-design change. It answers the question alpha.5 raised but did not
resolve: why does Core Seeker discover and capture vulnerable cores only
around tick 159–168 in the 3-way thirds matrix, and which parts of that
timing are inherent to its own deterministic scan algorithm versus
artifacts of seat geometry, target content, or third-party interference?
`CORE_SIZE`, arena size, tick/instruction budget, scoring, winner
semantics, and every reference/starter agent's source are held byte-for-
byte identical to alpha.1–alpha.5. **No production code was changed
anywhere in this alpha.**

Branched from the verified alpha.5 baseline, commit
`35a2476db4f1cc9e6b59c714e71a9bfc8cc32e20` on `v2.0-development` (`main`
unchanged at `5593d287f95a24996bb3b105befbc625a00795db` throughout).

## 1. Verified starting state (Phase 1)

- Branch: `v2.0-development`. HEAD at start: `35a2476`. Working tree:
  clean. `main`: `5593d287...`, unchanged. Local branch 5 commits ahead of
  `origin/v2.0-development`; nothing pushed.
- `docs/V2_0_ALPHA1_EVALUATION.md`, `docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md`,
  `docs/V2_0_ALPHA4_MULTI_ENTRANT_FEASIBILITY.md`,
  `docs/V2_0_ALPHA5_MULTI_ENTRANT_SCORING_ACTIVATION.md` were read in full.
- Read directly, not inferred: `core_seeker/agent.py`, `core_defender/
  agent.py`, `reactive_core_defender/agent.py`, `claimer/agent.py`,
  `hunter/agent.py`, `agent_api.py` (`Observation`/`MatchContext`/
  `load_python_agent`), `scheduler.py` (`run_sequential_quota`),
  `ruleset_policy.py` (`RulesetPolicy.run_scheduler`/`resolve_termination`),
  `python_runtime.py` (tick loop, `apply_action`, `_execute_action_slot`,
  `seed_core_ownership`, `apply_core_capture`, `_snapshot_core_owners`,
  `CORE_SIZE`, `core_addresses`), `vm.py` (`VM._wr8`, `arena`, `writer`,
  `tick_diffs`), `instructions.py` (`NOP == 0`), `replay.py`
  (`iter_replay`, `TickSnapshot`, `KillDeathEvent`).
- Regression baseline reproduced exactly as documented: pytest **1543
  total / 1537 passed / 6 skipped / 0 failed**; alpha-focused suites
  65/65; `test_ruleset_v1_equivalence.py` 8/8; Ruff clean repo-wide; mypy
  clean for both `engine` (69 files) and `client` (10 files).

## 2. A critical prerequisite fact not previously documented: 8 actions per tick

Direct reading of `scheduler.run_sequential_quota` and `ruleset_policy.
RulesetPolicy.run_scheduler` established a fact this alpha's entire
analysis depends on and no prior alpha document stated explicitly: **each
live entrant receives `instr_per_tick` (= 8) full `act()` calls per tick**,
not one. The scheduler's structure is `for state in states: for slot in
range(quota): execute_slot(state, slot)` — outer loop over entrants, inner
loop over the full quota — so one entrant's entire 8-action quota for a
tick executes as a contiguous block before the next entrant's quota begins
(no per-slot interleaving across entrants). Over a 200-tick match this
gives each surviving entrant **up to 1,600 total actions**, matching
alpha.1 §7's own passing remark ("`instr_per_tick=8` and `max_ticks=200`
give each entrant at most 1,600 actions") but never previously connected
to Core Seeker's own internal `actions_taken` counter, which is what this
alpha's entire timing model is built on. `CoreSeekerAgent.actions_taken`
increments once per non-assault `act()` call; it is therefore an *action*
clock, not a *tick* clock, and converting between the two (`tick =
((action_index - 1) // 8) + 1`) is required for every prediction below.

## 3. Core Seeker's exact state machine (Phase 2)

Read directly from `core_seeker/agent.py`. Two states (`self.mode`):

**`scan`** (default): `self.actions_taken += 1`; if `actions_taken %
SCAN_EVERY(=3) == 0`, issue a `READ` at `self.scan_cursor`, then advance
`scan_cursor += scan_stride` (mod arena). Otherwise, check
`observation.last_read` (the value from whichever `READ` most recently
completed — see §4 for why this is the crux of the whole mechanism): if it
looks "foreign" (`!= 0` and `!= self.signature`), compute `hit_address =
(scan_cursor - scan_stride) % arena_size` (recovers the address that
produced this `last_read`), and:
  - if `self.last_foreign_address` is set and `hit_address` is within
    `LOCK_RADIUS(=12)` of it (wrap-aware `min(forward, backward)` distance,
    §5): transition to `assault` — `assault_cursor = (min(hit_address,
    last_foreign_address) - ASSAULT_WINDOW//4) % arena_size`,
    `assault_remaining = ASSAULT_WINDOW(=16)`, `last_foreign_address =
    None`.
  - else: `self.last_foreign_address = hit_address` (no lock yet).
  Whether or not this check fired, the action **falls through** to an
  ordinary outward `WRITE` at `expand_cursor` (stride 149, starting at 0,
  independent of Core Seeker's own spawn address) — so even the exact tick
  a lock transition is decided still returns an expand write that tick,
  not the first assault write (§4).

**`assault`**: every call is a `WRITE` of `self.signature` at
`assault_cursor`, then `assault_cursor += 1` (mod arena),
`assault_remaining -= 1`; when `assault_remaining` reaches 0, return to
`scan` with `last_foreign_address` already cleared. **Critically,
`actions_taken` is never incremented while `mode == "assault"`** (the
early-return branch is above the increment line) — the scan-index clock
*pauses* for the full 16-action burst every time a lock fires, real or
false-positive (§8).

No randomness anywhere (`self.rng` stored, never called — confirmed by
direct reading, not inference). Neither `scan_cursor`'s start
(`arena_size // 3`) nor `expand_cursor`'s start (`0`) depends on Core
Seeker's own spawn address (`observation.pc` is never read by this agent
at all, unlike `core_defender`/`reactive_core_defender`) — its entire
schedule is **absolute**, identical regardless of which seat it occupies.

## 4. The mechanism the design docstring does not fully describe: an echo-lock, not a two-independent-hit requirement (Phase 5)

The governing task explicitly asked this to be verified from source rather
than trusted from alpha.5's shorthand ("two scan hits within roughly
radius 12"). Direct trace instrumentation (§6) found the real mechanism is
narrower, and fires far more readily, than that phrasing suggests:

`observation.last_read` reflects the value from the **most recently
completed `READ`**, and — critically — it is **never cleared** after being
checked. Because the foreign-check runs on *every* non-scan action, not
just the action immediately after a `READ`, the exact same `last_read`
value gets re-evaluated on **every subsequent action** until the next
`READ` overwrites it (one scan in every three actions). Since
`hit_address` is recomputed the same way each time (`scan_cursor -
scan_stride`, unchanged since the last scan), it resolves to the **same
address** on every one of those re-checks. Concretely, after a scan at
address X returns a foreign byte:

- Action *n+1* (first re-check): `last_foreign_address` is usually `None`
  (or some unrelated older address) → records `hit_address = X` as
  `last_foreign_address`. No lock yet.
- Action *n+2* (second re-check, same stale `last_read`): `hit_address` is
  computed identically → still `X`. `last_foreign_address` is now `X`
  (just set). `within_lock_radius(X, X)` → distance 0 → **lock fires
  immediately.**

So in practice, Core Seeker locks on within **one or two actions** of
*any single* foreign scan hit — not upon finding two genuinely
independent, spatially-nearby hits as the module docstring's "two
foreign-looking hits… within `LOCK_RADIUS`… a plausible cluster" language
implies. `LOCK_RADIUS` is real code and does gate the transition, but the
self-echo means it is met almost automatically once *any* one scan finds
foreign content — the genuine "two independent hits close together"
scenario the docstring describes is not what actually drives lock-on in
observed play.

## 5. Consequence: continuous lock/assault cycling, not one-time commit (Phase 2/8)

Traced directly (§6's harness) over a full 200-tick match: Core Seeker
enters `assault` mode **55–58 separate times** in a typical 3-entrant
match — roughly once every 3 ticks for the entire match after its first
lock (observed as early as tick 1, §11), not the single "search, then
commit" episode its own docstring narrative implies. This follows directly
from §4: once enough of the arena is non-zero (which happens quickly, see
§13), nearly every subsequent scan finds something foreign and re-triggers
the echo lock. **Only one of these 55–58 episodes per match ever actually
threatens a real core** — every other one is a false positive, its
16-action burst landing on ordinary claimed territory that happens to lie
near wherever that particular scan landed.

## 6. Cross-validated research harness (Phases 2, 6, 7)

`runs/v2_0_alpha6_core_seeker_timing/trace_match.py` re-derives the tick
loop's *shape* using the real, unmodified production pieces directly —
`battle_engine.python_runtime.VM`/`apply_action`/`seed_core_ownership`/
`apply_core_capture`/`PythonEntrantState`, `battle_engine.agent_api.
Observation`/`MatchContext`/`load_python_agent`,
`battle_engine.ruleset_policy.resolve_ruleset_policy`,
`battle_engine.scoring.ScoringPolicy`,
`battle_engine.statistics.StatisticsCollector` — plus one line of
instrumentation reading Core Seeker's own already-public instance
attributes (`mode`, `scan_cursor`, `expand_cursor`, `assault_cursor`,
`assault_remaining`, `last_foreign_address`, `actions_taken`) after every
one of its `act()` calls. **`CoreSeekerAgent` itself is never modified**
(Phase 14) — this is ordinary attribute access on a real, unmodified
instance.

`validate_against_alpha5()` runs this harness on the exact trio/seat/seed
used by alpha.5's real `NativeMatchService`-executed matches and compares
capture tick/victim/killer:

| Check | Result |
|---|---|
| All 4 real alpha.5 captures | tick, victim, and killer reproduced **exactly** |
| 2 alpha.5 non-capture controls | no capture in either, matching exactly |
| Legacy alpha.1 1v1 case (`core_defender@0` vs `core_seeker@2048`) | capture at **tick 140** — exactly alpha.1 §4's own documented value |
| Legacy alpha.2 orientation control (`core_seeker@0` vs `core_defender@2048`) | **0 captures**, matching alpha.2 §9/§10's documented 0/10 |

**6/6 exact reproductions**, across two different alpha generations' own
independently-documented results, using a harness built from real
production code, not a reimplementation. This is the evidentiary basis for
trusting the harness's internal-state trace as ground truth for the rest
of this document.

## 7. Pure analytical scan-sequence derivation (Phase 3)

`runs/v2_0_alpha6_core_seeker_timing/predict_timing.py` computes, purely
from the constants in §3 — **no match execution required for this part**:

```
scan_stride  = (int(4096 * 0.381_966_011) | 1) or 1 = 1565
scan_cursor0 = 4096 // 3                             = 1365
```

- `gcd(1565, 4096) = 1` — the stride is coprime to the arena size, so the
  scan sequence is a full-period permutation: all 4,096 addresses are
  visited exactly once every 4,096 scans, never repeating early.
- Within the full 200-tick / 1,600-action budget, at most `1600 // 3 =
  533` scans occur (fewer once any false-positive delay is subtracted,
  §8) — **13.0% of the arena** is ever scanned in a match that runs the
  full tick limit, at most.
- Because the sequence never revisits an address inside one match, an
  opportunity to scan any *specific* address (e.g. exactly `1365`) occurs
  **at most once** per match — the mechanism instead depends on the
  sequence passing *near* a fixed target address (within a window a
  16-action assault burst can fully cover), which — per the three-gap/
  low-discrepancy structure of an additive sequence with this kind of
  stride — happens far sooner than a full-period return.

## 8. Two prediction pathways, and why one is far more robust than the other (Phase 5)

For a fixed core start address, two distinct geometric events can trigger
a covering assault:

1. **Within-core**: the scan address itself lands inside the victim's own
   8 core cells. Robust: it only requires that the *core's owner* (or
   some other agent) has, by that point, written something non-zero to at
   least one of its own core cells — true early for any defending agent
   and eventually true for any expander whose sweep happens to cross its
   own spawn region.
2. **Window-containment**: the scan address lands just *outside* the core
   (often via wraparound) but close enough that the resulting 16-cell
   assault window (`[addr - 4, addr + 12)`) still fully covers the core.
   Can fire earlier, but requires that this *other*, non-core address
   happen to already be foreign — dependent on which other entrants are
   present and what they've incidentally written, not on the victim's own
   behavior.

## 9. Predicted timing by fixed seat (Phases 6, 9)

Computed offline (§7/§8), before any execution, for the established
alpha.4/alpha.5 thirds convention (`0`, `1365`, `2730`):

| Seat | Core start | Within-core (k, addr, no-delay tick) | Window-containment (k, addr, no-delay tick) |
|---|---:|---|---|
| A | 0 | k=466, addr=2, **tick 175** | k=254, addr=4094 (via wrap), **tick 96** |
| B | 1365 | k=1 (degenerate, tick 1 — content never ready this early); **next: k=213, addr=1369, tick 80** | same k=213/1369 event also gives full containment |
| C | 2730 | k=719, addr=2731, **tick 270** (already exceeds the 200-tick budget with *zero* delay) | k=507, addr=2727, **tick 191** |

Legacy alpha.1/alpha.2 1v1 convention (`0`/`2048`):

| Position | Within-core | Window-containment |
|---|---|---|
| `0` | k=466, tick 175 | k=254, addr=4094, **tick 96** |
| `2048` | k=360, addr=2048, tick 135 | k=148, addr=2044, **tick 56** |

**Seat B's `k=213`/address-`1369` event is, by a wide margin, the earliest
*realistic* opportunity of any fixed thirds address** (excluding the
degenerate, content-impossible `k=1`). This single fact is the core of
why seat B is the only thirds seat that ever produces a real capture.

## 10. Predicted vs. observed: the exact causal chain (Phase 6, 7, 8)

Traced for all 4 of alpha.5's real captures (§6):

| Match | Real capture tick | Winning episode # (of total) | Window start | Global action index |
|---|---:|---|---:|---:|
| `(reactive_core_defender, claimer, core_seeker)` | 166 | 43 / 56 | 1365 | 1313 |
| `(core_defender, claimer, core_seeker)` | 168 | 44 / 56 | 1365 | 1329 |
| `(reactive_core_defender, hunter, core_seeker)` | 160 | 40 / 55 | 1365 | 1265 |
| `(core_defender, hunter, core_seeker)` | 160 | 40 / 55 | 1365 | 1265 |

**In all 4 real captures, the winning episode's window start is exactly
`1365`** — the victim's own core start — confirming this is the identical
`k=213` scan (address `1369`, §9) predicted analytically before any
execution. The causal chain, with real numbers from one representative
match (`reactive_core_defender@A, hunter@B, core_seeker@C`, capture tick
160):

```
scan sequence (fixed, content-independent)
  → k=213: scan address 1369 (Core Seeker's own action #639, no-delay tick 80)
  → by real elapsed time, this specific scan actually executes at
    action #1263 (tick 159) — 624 actions / 39 false-positive assault
    episodes' worth of delay later (§11)
  → observation.last_read = 227 (non-zero, non-Seeker-signature: foreign)
  → echo re-check one action later locks on (§4)
  → assault_cursor = 1365, 16-action burst covers [1365, 1381),
    fully containing the core [1365, 1373)
  → apply_core_capture finds victim owns zero core cells at end of tick 160
  → core-captured, kill credited to core_seeker
```

The only thing this alpha's prediction could not fix in advance —
*exactly* which real tick the critical scan lands on — is explained fully
in §11, and cross-validated exactly (§6).

## 11. Why captures cluster at ticks 159–168, not tick 80 (Phase 8)

§9 predicts `k=213`'s scan happens at Core Seeker's own action #639
(no-delay tick 80) if nothing else ever intervened. Real captures occur
40–90 ticks later. The gap is fully accounted for by §5's false-positive
episodes: **`actions_taken` does not advance during `assault` mode**
(§3), so every completed 16-action false-positive burst *before* the
critical `k=213` scan delays it by exactly 16 real actions (2 ticks) in
elapsed match time, without changing which `k` is critical. Across the 4
real captures, the critical scan actually lands at real action index
1263–1329 (tick 159–168) instead of its no-delay index 639 (tick 80) — a
delay of 624–690 actions, i.e. **39–43 completed false-positive assault
episodes** happened first, matching the observed 40th–44th episode being
the winning one out of 55–56 total (§10). This delay is not a fixed
constant — it is the cumulative count of *how many prior scans happened to
land on already-foreign content*, which depends on how much of the arena
the specific matchup's other entrants have claimed by each point in the
match, which is why the exact real tick varies by 8 ticks (160 vs. 168)
across otherwise-similar matchups even though the *critical scan index*
(`k=213`) is identical in every case.

## 12. Why seat A and seat C are never real victims (Phase 8, 9)

- **Seat C** (`2730`): its earliest opportunity of *either* kind — even
  the more permissive window-containment pathway (`k=507`, no-delay tick
  **191**) — already leaves at most 9 ticks of budget before any
  false-positive delay is even added; the within-core pathway
  (`k=719`, no-delay tick **270**) exceeds the 200-tick budget with *zero*
  delay. Given real captures accumulate 40+ ticks of delay before
  reaching *any* candidate `k` in this population (§11), a seat-C victim
  is not merely rare — **it is not achievable within the current 200-tick
  budget under this scan schedule**, a closed-form conclusion, not a
  sampling artifact. This matches 0/44 seat-C-victim captures across the
  entire alpha.4+alpha.5 corpus.
- **Seat A** (`0`): its within-core pathway (`k=466`, no-delay tick 175)
  is already too late once any realistic delay is added (175 + 40–90 ≈
  215–265, past the budget). Its window-containment pathway (`k=254`,
  addr `4094` via wraparound, no-delay tick 96) is numerically comparable
  to seat B's `k=213` (no-delay tick 80) — but, unlike seat B's pathway,
  it depends on some *other* entrant's incidental write reaching address
  `4094` (2 cells before wraparound to seat A's own core), not on the
  victim's own behavior. **Directly tested**: in one of alpha.5's real
  seat-A-attacker trios (`core_seeker@A, claimer@B, hunter@C`), address
  `1369` never becomes non-zero at all during the whole match, and no
  episode ever achieves any overlap with either potential victim's core —
  the opportunistic pathway simply did not fire for this specific
  population. **Separately confirmed as real and reachable**: the same
  `k=254`/address-`4094` pathway *did* fire in the legacy alpha.1/alpha.2
  1v1 configuration (`core_defender@0` vs. `core_seeker@2048`), producing
  the exact tick-140 capture §6 cross-validated. This is reported as a
  content-dependent, matchup-specific pathway whose exact availability in
  the 3-entrant thirds population was not exhaustively traced across every
  trio (Phase 18's scope boundary — not a general spawn-geometry sweep);
  what is established with certainty is that it did not fire in the
  tested 3-way corpus, while the far more robust seat-B `k=213` pathway
  reliably did whenever a fast-enough content source was present (§13).

## 13. The defender-stride discovery: why a defender bystander enables capture (Phase 10, 18)

This refines, with an exact mechanism, alpha.4 §16 / alpha.5 §22's
"claimer blocks captures, defenders don't" finding. Both `core_defender`
and `reactive_core_defender` use the **identical** `expand_stride = 131`,
starting at `core_start + DEFENDED_RADIUS(=8)` — a coincidence of their
shared design lineage (`reactive_core_defender/agent.py` was built as a
direct evolution of `core_defender/agent.py`, §2 of
`V2_0_ALPHA2_REACTIVE_DEFENSE.md`), not a shared engine default. Traced
directly: with `reactive_core_defender` at seat A, address `1369` (§9's
critical trigger address) first becomes non-zero at **tick 118**, written
by `reactive_core_defender` itself via this ordinary expand sweep — well
before the critical scan's real arrival (~tick 159–168). Traced again with
`core_seeker@A, claimer@B, hunter@C` (no defender present): address `1369`
**never** becomes non-zero in the whole match — neither `claimer`'s
stride-101 sweep (starting at literal address `0`, independent of its own
spawn) nor `hunter`'s two-phase sweep happens to land exactly on `1369`
within this seed's budget.

**Refined interpretation**: alpha.4/alpha.5's "third-party interference"
finding is less about `claimer` actively *disrupting* detection and more
about `core_defender`/`reactive_core_defender`'s specific `stride=131`
sweep being the one that reliably *supplies* the critical trigger content
early enough, purely incidentally — an artifact of which bystander happens
to be present, not a deliberate or adversarial interaction. **This is a
genuinely new, more precise characterization**, not previously available
because alpha.4/5 never traced individual scan/write addresses.

## 14. Core Defender's own survival mechanism as a victim (Phase 10, 11)

Directly traced (`reactive_core_defender@A, core_defender@B,
core_seeker@C` — the one alpha.5 rotation with a defender *at* the
vulnerable seat, never captured in that corpus): lock-on happens
**almost immediately, at tick 1**. `core_defender`'s own `REFRESH_EVERY=4`
schedule writes its own signature (`0xD3` = 211) to its own core cell 0
(address `1365`) on its 4th action — within tick 1's own 8-action quota,
*before* `core_seeker` (seat C, scheduled after seat B every tick) has
even taken its first action that tick. Core Seeker's very first scan
(`k=1`, address `1365`) therefore reads a genuinely foreign byte
immediately, and the echo mechanism (§4) locks on and begins a full-window
assault burst starting at tick 1.

**This directly answers Phase 11's question**: detection is not avoided —
it happens essentially instantly. Survival comes from a **reclaim race**:
because seat B acts *before* seat C every tick, `core_defender` continues
its own uncorrelated periodic refresh (2 refreshes per tick, cycling
through all 8 cells) *during* the ~2-tick assault burst, interleaved by
the scheduler so that its refresh actions for a given tick complete before
Core Seeker's assault actions for that same tick. This reclaims enough
cells fast enough that ownership never reaches zero simultaneously across
all 8 — `core_defender` wins the race in this specific timing
configuration, unlike the alpha.1 1v1 case (tick 140, a *later*,
differently-timed attack that it lost outright, §6). This is a materially
different, more precise characterization than "defense prevents
detection" — detection is not prevented at all here; the outcome hinges on
turn-order-sensitive reclaim timing.

## 15. Reactive Core Defender's mechanism, contrasted (Phase 11)

`reactive_core_defender`'s `SIGN` phase writes its own signature to all 8
core cells within its **first 8 actions** (tick 1, even faster coverage
than `core_defender`'s spread-out `REFRESH_EVERY=4` cycle) — so by the
time any scan could find it, all 8 cells already carry a consistent,
recognizable signature. Its `PATROL`/`ALERT` phases (alpha.2 §4) add
*reactive* repair on top of this — a `READ`-verified mismatch triggers an
immediate, targeted `WRITE` — a qualitatively different, evidence-driven
response than `core_defender`'s blind timer, but operating on the same
underlying "was I scanned/attacked early, and can I reclaim fast enough"
race this alpha's tracing reveals is the actual mechanism at stake,
confirming alpha.2's own tick-139–140 burst-vs-refresh-latency analysis
(§2 of that document) was the right diagnosis, now generalized: it is a
race against Core Seeker's *actual* attack timing in a given match, not
a fixed property of "reactive vs. blind" defense in the abstract.

## 16. Claimer's and Hunter's role (Phase 10)

Neither defends its own spawn region at all. Both were the only real
victims observed in the alpha.4/alpha.5 corpus, and this alpha's tracing
now explains *why they, specifically, are captured while the defenders at
the same seat are not*: their core cells only become foreign incidentally,
whenever their own blind sweep (or, per §13, a defending bystander's
sweep) happens to pass through address `1369` specifically — a slower,
less-guaranteed process than a defender's own deliberate, fast, core-
targeted writes, but one that (per §10/§13) reliably completes by the time
Core Seeker's delayed critical scan arrives, given a defender bystander is
present to supply the trigger content early.

## 17. Third-party effects, restated precisely (Phase 10, 18)

Alpha.4/alpha.5's finding ("third-party ordinary writes can change whether
an otherwise identical capture succeeds") is confirmed and now precisely
mechanized: the third party's effect operates through exactly one
address, `1369`, and exactly one question — does *some* entrant's own
ordinary sweep write there before Core Seeker's delayed critical scan
arrives? `core_defender`/`reactive_core_defender` reliably do (shared
`stride=131`, §13); `claimer`/`hunter` did not in the tested seed. This is
a content-supply effect, not a detection-suppression or scheduler-order
effect — no evidence was found of a bystander's writes actively
*overwriting away* foreign content Core Seeker would otherwise have found
(the alternative hypothesis alpha.4 §16 raised but did not resolve).

## 18. Scheduler/tick effects (Phase 10)

Established directly (§2): each entrant's full 8-action quota executes as
one contiguous block per tick, in entrant order. This produces exactly one
seat-order effect this alpha found evidence for: a seat-B victim's own
per-tick actions (including any defensive refresh) always complete before
a seat-C attacker's same-tick actions, which is the exact mechanism behind
§14's reclaim-race survival. No other scheduler-order pathology (kill-
stealing, simultaneous-attacker ambiguity) arises in this population,
since at most one entrant (`core_seeker`) is ever offense-capable in any
alpha.5 trio (already noted, alpha.5 §22).

## 19. Seat sensitivity, fully explained (Phase 9)

| Question | Answer |
|---|---|
| Does each seat's core intersect the scan path differently? | Yes — §9's table; seat B's `k=213` opportunity (no-delay tick 80) is far earlier than seat A's marginal options and seat C's already-out-of-budget one. |
| Earliest qualifying pair by seat? | §9's table, both pathways. |
| Is one seat intrinsically impossible within 200 ticks? | Yes, seat C — proven, not merely observed (§12). |
| Does Core Seeker's own seat affect the scan sequence? | No — confirmed directly from source (§3): `scan_cursor`/`scan_stride`/`expand_cursor` never read `observation.pc`, unlike `core_defender`/`reactive_core_defender`. |
| Are scan addresses absolute or relative to spawn? | Absolute (§3). |
| Does seat asymmetry come from Core Seeker, target agents, scheduler order, or all? | Primarily Core Seeker's own fixed absolute schedule (§9/§12) plus, secondarily, which bystander agent happens to be present (§13) and per-tick scheduler ordering for the reclaim race specifically (§14/§18) — not a single cause, a composition of three. |

## 20. Alpha.2 orientation finding — now explained (Phase 26 item 26)

Yes, fully. Alpha.2 §10's "every capture occurred with Core Seeker at
`2048`, victim at `0`, never the reverse" is the same mechanism as §9's
seat-A analysis, using the legacy 1v1 convention's own two fixed addresses
(`0`, `2048`) instead of the thirds convention's three. §9's table shows
address `0`'s only realistic opportunity (`k=254`, addr `4094` via wrap,
no-delay tick 96) and address `2048`'s (`k=148`, addr `2044`, no-delay
tick 56) both exist geometrically — **the orientation asymmetry is not
about whether a geometric opportunity exists for each address, but about
which one Core Seeker is actually *looking for*, since the scan schedule
is fixed and identical regardless of which role Core Seeker plays.**
§6 confirms directly: with `core_defender@0`/`core_seeker@2048` (Core
Seeker "looking for" address `0` via its fixed schedule), the exact
`k=254`/address-`4094` opportunity fires and captures at tick 140 — the
documented alpha.1 result, reproduced exactly. With roles reversed
(`core_seeker@0`/`core_defender@2048`), Core Seeker's fixed schedule still
looks for the same absolute addresses (§3's spawn-independence), but the
2048-side opportunity (`k=148`, tick 56) did not fire within budget in
that specific matchup's content — 39 false-positive episodes occurred with
no successful hit. Both orientations were tested directly with the same
harness (§6); the underlying mechanism (§4–§9) is identical in both, only
the specific realized content timing differs, exactly as §17 predicts for
the thirds case.

## 21. Alpha.5 capture behavior — now explained (Phase 26 item 27)

Yes, completely: §10's exact causal chain, cross-validated exactly against
all 4 real captures, with the specific triggering scan (`k=213`, address
`1369`) identified, the exact delay mechanism quantified (§11), and the
defender-stride content source identified (§13).

## 22. Seat C's broader win-rate advantage — not explained by this analysis (Phase 18, 26 item 28)

Alpha.5 §24 separately found seat C shows a win-rate advantage
*independent* of Core Seeker's presence (e.g. `hunter` won 6/6 from seat C
including in `core_seeker`-free trios). This alpha's analysis is entirely
about Core Seeker's *own* scan/attack timing and does not bear on ordinary
territorial accumulation by non-`core_seeker` agents at any seat. Per
Phase 18's explicit scope boundary, this is **not explained here** and is
carried forward as an open question for a future, separately-scoped
spatial/territorial-geometry characterization — it was not investigated
further in this alpha.

## 23. Controlled synthetic fixtures (Phase 12)

Not needed. Every question this alpha set out to answer was resolvable
directly from real reference-agent behavior traced through the harness
(§6) — no scripted fixture agents were created. This differs from
alpha.1/alpha.4's own precedent of using small scripted agents for
isolated scenarios; here, the real bundled agents' own deterministic,
fully-traceable behavior was sufficient at every step.

## 24. Focused tests (Phase 13)

**None added.** Every property this alpha characterizes (scan-sequence
determinism, the echo-lock mechanism, per-seat timing) is a property of
existing, unmodified reference-agent source and engine mechanics already
covered by alpha.1–alpha.5's existing test suites (which continue to pass
unchanged, §27) — this alpha found no undertested behavior worth locking
in with a new focused test, and no correctness defect to add a regression
test for. Adding tests that encode `CoreSeekerAgent`'s specific numeric
constants (`scan_stride=1565`, etc.) as contractual would risk exactly the
kind of "locking in an arbitrary research-agent strategy choice" the
governing task's Phase 13 explicitly warns against, since Core Seeker
remains an experimental reference agent, not a stable contract.

## 25. Core Seeker redesign — not performed (Phase 14)

Confirmed: `git diff -- engine/src/battle_engine` is empty. Every finding
in this document was obtained by tracing the existing, unmodified
`CoreSeekerAgent` through a research harness built from real, unmodified
production pieces.

## 26. Benchmark-quality classification (Phase 16)

**B — useful only as a narrow characterization fixture, not yet a general
offense benchmark.** Evidence:

- Its "search-then-commit" design intent (per its own docstring) is not
  what actually happens: it is a near-continuous echo-lock cycle (§4/§5),
  not a deliberate two-hit correlation. The docstring's stated mechanism
  and the actual mechanism diverge.
- Its capture timing and seat-dependence are dominated by a fixed,
  content-independent absolute schedule (§7–§9) that has no relationship
  to "searching" in any adaptive sense — the same three addresses (near
  `0`, `1365`, `2730`) are always the only ones with any realistic chance
  within budget, regardless of what any opponent actually does.
- Its one demonstrated success mode (§10–§13) depends on a coincidental
  shared implementation detail (`expand_stride=131`) between two other
  reference agents supplying trigger content — not on any property of
  Core Seeker's own search intelligence.
- It is nonetheless a **legitimate, useful, fully deterministic
  characterization fixture** for testing whether a defender can survive a
  known, reproducible, non-adaptive attack pattern (exactly how alpha.2
  used it, and how this alpha's §14 reclaim-race finding was obtained) —
  its determinism and traceability are real assets for that narrower
  purpose.
- It is **not** classified C (needs redesign before further combat
  research) because nothing found here invalidates alpha.1/alpha.2's own
  conclusions about those specific, already-published results (§27) — the
  mechanism explains *why* those results occurred, it does not overturn
  them.

## 27. Implications for Vulnerable Core (Phase 17)

**Partly — proves feasibility, does not yet demonstrate realistic
strategic pressure**, and this alpha sharpens rather than weakens that
existing (alpha.1 §10, alpha.4 §21) qualified verdict. Deliberate core
offense genuinely works (a directed search-then-commit strategy captures
cores no blind sweep ever does, still true) — but this alpha shows that
"working" is substantially narrower and more mechanical than "searching"
suggests: it is really "reaching one of at most 2–3 fixed, config-
dependent addresses via a fixed absolute schedule, then depending on
existing content (frequently supplied by unrelated bystanders, §13) being
already present there." A hypothetical opponent that never placed anything
near those specific fixed addresses would face **zero** capture risk from
this specific implementation, regardless of how much territory it claimed
elsewhere — this is a real, now-quantified brittleness, not merely a
"seat-sensitivity" caveat. Mechanic viability (a fixed vulnerable region
that can, in principle, be found and captured through ordinary API calls)
remains established; this specific attacker's *generality* as evidence for
that viability is weaker than alpha.1's original framing suggested.

## 28. Do prior offense/defense conclusions remain valid? (Phase 26 items 31–32)

- **Offense (alpha.1)**: valid, with the refinement above. The tick-140
  capture in the exact original alpha.1 orientation is reproduced exactly
  by this alpha's independent harness (§6) — not merely re-asserted, newly
  and independently confirmed via a from-scratch mechanistic re-derivation.
- **Defense (alpha.2)**: valid, with a materially more precise mechanism
  (§14/§15). Reactive Core Defender's real advantage over blind Core
  Defender is not "detection vs. no detection" as alpha.2 §11 characterized
  it (both, this alpha finds, are typically detected essentially
  immediately when directly threatened, §14) — it is repair *speed and
  correlation with the actual attack's timing*, which alpha.2's own
  narrower analysis (§2 of that document, the 32-action-cycle-vs-16-action-
  burst latency argument) already correctly anticipated in spirit, now
  confirmed with an exact, traced, cross-matchup mechanism.

## 29. Success/negative-result assessment (Phase 19/20)

**Success**, against the governing task's own bar: this alpha explains,
mechanistically and reproducibly, the exact scan progression (§3/§7), the
exact detection/confirmation rule including the previously-undocumented
echo behavior (§4), the exact attack transition (§3), why captures cluster
at ticks 159–168 with an exact causal chain (§10/§11), why some fixed
seats are vulnerable and others provably are not (§9/§12), a concrete,
address-level bystander-interference trace (§13/§17), and both defenders'
actual survival mechanisms (§14/§15) — the strongest outcome the governing
task named ("offline analysis predicts the timing and engine replays
confirm it exactly") was achieved for the primary (seat B / k=213) pathway
and partially achieved (geometric opportunity confirmed, exact real-world
firing not exhaustively traced across every trio) for the seat-A
opportunistic pathway (§12), which is reported honestly as a bounded, not
a complete, result rather than overclaimed.

## 30. Recommended next direction (Phase 21)

**B — spatial/start-position characterization**, not A, C, or D.

- Not **A** (Core Seeker redesign): §26 classifies it as a legitimate
  narrow fixture, not a broken benchmark requiring replacement; its
  documented behavior is now well-understood enough to use deliberately
  (e.g., knowing its only realistic within-budget targets are addresses
  near `0`/`1365`/`2730`/`2048` is itself useful information for designing
  future placement-aware experiments), which argues for *using* it more
  precisely rather than replacing it yet.
- Not **C** (return to broader rules research) or **D** (stop Vulnerable
  Core research): §27/§28 show the mechanic's core viability claim still
  stands, just narrower than originally framed — there is a concrete,
  well-scoped next question (does the mechanism generalize away from these
  three specific fixed addresses?) that a stop/pivot would leave
  unanswered for no evidentiary reason.
- **B** follows directly from §9/§12's central finding: capture
  reachability is governed almost entirely by fixed absolute address
  geometry relative to Core Seeker's unchanging schedule, not by anything
  behavioral. The single most direct next step this alpha's own evidence
  implies is a **controlled placement/position characterization** (not a
  broad randomized sweep, consistent with every prior alpha's placement
  discipline) that varies *where* cores sit relative to the fixed scan
  schedule's few realistic windows, to determine whether the "vulnerable
  core" mechanic's demonstrated offense/defense dynamic is a general
  property or an artifact of one specific, oft-reused placement
  convention (`0`/`arena_size//3`/`arena_size//2`/`2*arena_size//3`) that
  alpha.1 through alpha.6 have, so far, never varied.

## 31. Unresolved questions (Phase 26 item 46)

- Whether the `k=254`/address-`4094` opportunistic pathway for seat A
  (§12) can ever fire within the 3-entrant thirds population under some
  other trio/seed not tested here — confirmed absent in one tested trio,
  confirmed present in the 2-entrant legacy configuration, not
  exhaustively checked across all trios.
- No trio in alpha.5's own corpus placed `hunter` as the seat-A bystander
  while `core_seeker` occupied seat C (alpha.5 §22's own gap) — this
  alpha's `stride=131` finding (§13) predicts `hunter` would *not* supply
  early trigger content (its own two-phase sweep does not share the
  defenders' stride), but this was not directly tested.
- Seat C's win-rate advantage independent of Core Seeker's presence
  (alpha.5 §24) remains fully open (§22) — out of this alpha's scope by
  design.
- Whether the echo-lock mechanism (§4) — arguably the single most
  significant, previously-undocumented finding in this alpha — was an
  intentional simplification or an oversight relative to the agent's own
  docstring's stated design intent is a question about original design
  intent this alpha cannot answer from source alone; it is reported
  purely as an accurate characterization of actual behavior, not
  adjudicated as correct or incorrect design.

## 32. Recommendation for alpha.7 (Phase 26 item 47)

**alpha.7**, scoped to: hold every mechanic, scoring weight, and agent
implementation exactly fixed (per this alpha's own Phase 14/15/26
findings, redesigning Core Seeker or any defender now would discard the
now-precise mechanistic understanding this alpha built without first
using it); introduce a **controlled, still-narrow set of alternative fixed
placements** (not a random sweep) chosen specifically to test whether
Core Seeker's realistic capture window generalizes away from the
`0`/`1365`/`2730`/`2048` addresses this alpha found are the *only* ones
with any realistic within-budget opportunity under the current scan
formula — e.g., one placement convention deliberately chosen so that no
core start falls within this alpha's identified realistic-opportunity
addresses at all, to test the (implied but untested) prediction that zero
captures would occur regardless of which agents are matched, and one
chosen so that *all three* seats fall within a realistic window, to test
whether the seat-B-only pattern this alpha and every prior alpha observed
is genuinely a property of the specific thirds convention rather than an
inherent limit of the mechanic. This closes the open placement-generality
question §30/§31 raise, using the exact predictive model (§7–§9) this
alpha built and validated, before any future alpha considers redesigning
Core Seeker itself.

## 33. Regression qualification (Phase 24)

No production code was changed anywhere in this alpha (§25) — confirmed
by an empty `git diff -- engine/src client/src`. No new focused tests were
required (§24).

| Check | Result |
|---|---|
| Alpha-focused suites (alpha.1/1.1/2/4/4.1) | 65 / 65 passed |
| `test_ruleset_v1_equivalence.py` | 8 / 8 passed |
| Full `pytest` | **1543 total / 1537 passed / 6 skipped / 0 failed** — unchanged, exactly reconciled |
| Ruff (repo-wide) | clean, 0 errors |
| mypy (`engine/src/battle_engine`) | clean, 69 files |
| mypy (`client/src/battle_client`) | clean, 10 files |
| `git diff --check` | clean |
| `git diff -- engine/src client/src` | empty |

## 34. Research artifacts (Phase 22)

`runs/v2_0_alpha6_core_seeker_timing/`: `trace_match.py` (the
production-code-reusing harness, §6), `predict_timing.py` (the pure
analytical derivation, §7–§9), `validation_summary.json` and
`prediction_summary.json` (their outputs — gitignored local scratch, per
the existing `runs/` `.gitignore` precedent; this document is the durable,
committed record). No large replay collections were persisted.
