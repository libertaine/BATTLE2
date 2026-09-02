# Bytefray v4 Spectator Research Phase 8 — Multi-Entrant Director Qualification and Fight Night Presentation

## Verdict

**PASS.**

Phase 8 asked two questions. First, whether the Phase 7 Director survives
contact with 3- and 4-entrant matches — the gap Phase 7 disclosed as its own
limitation (§23.3) rather than assumed safe. Second, whether a "Fight Night"
broadcast presentation can make matches easier to follow without becoming a
second semantic interpretation engine or leaking hidden facts through
presentation emphasis.

Both answered yes, with evidence. The multi-entrant prerequisite passed on all
six gate criteria and required **no Director remediation**: worst-case
multi-entrant Broadcast inflation measured **1.84x**, *below* Phase 7's
disclosed two-entrant worst case of 2.10x. The research gate (§47) passed on
all ten criteria, so minimal integration was completed and visually qualified
on real Windows pygame.

The most important finding is structural rather than numerical: the
sustained-activity fatigue rule is *strengthened* by multi-entrant load, not
defeated by it, because it triggers on a continuous elevated streak and extra
concurrent engagements make that streak more continuous.

| Area | Classification |
|---|---|
| Multi-entrant Director corpus (3 + 4 entrants, real matches) | **BUILT AND MEASURED** |
| Multi-entrant Broadcast pacing | **PASS — no remediation needed** |
| Sustained-activity fatigue under multi-entrant load | **PASS — strengthened, not defeated** |
| Multi-entrant timing disclosure | **PASS — blind entrants provably unaffected** |
| Fight Night information architecture (data-source matrix) | **ESTABLISHED** |
| Perspective disclosure policy | **EXPLICIT (Policy A, entrant-safe)** |
| Event ribbon (deterministic, indexed, flood-bounded) | **IMPLEMENTED AND QUALIFIED** |
| Opening / result cards | **IMPLEMENTED AND QUALIFIED** |
| Entrant cards / phase indicator | **REJECTED — already exist, not duplicated** |
| 2 / 3 / 4-entrant layout, long names, 640×480 | **QUALIFIED (closes Phase 6's open item)** |
| Identity-leak negative regressions | **IMPLEMENTED AND QUALIFIED** |
| Simulation / replay isolation | **CONFIRMED (artifact hashes unchanged)** |
| Full repository suite | **PASS (2806 passed, 14 skipped, 2 deselected)** |
| **Phase 8 overall** | **PASS** |

---

## 1. Baseline

| Fact | Value |
|---|---|
| Repository | `D:\Projects\BATTLE2` |
| Starting branch | `v4-spectator-phase7-development` |
| Starting `HEAD` | `08005605f036a738c7437731439eb1f4350c9385` (matched the phase brief's expected `0800560` exactly) |
| Phase 7 implementation checkpoint | `b309749dd681de92826196268f35ef9f69f8b77e` (confirmed present as an ancestor) |
| `origin/main` | `4aa8ac3a4cc0deccfdd6c5b94136933b315335be` |
| Initial `git status` | clean (aside from the pre-existing unreadable `.pytest-cache-v141`) |
| `git diff` / `git diff --cached` | empty |
| Development branch | `v4-spectator-phase8-development` (created from `0800560`) |
| Worktrees | two, on different repositories (`D:/Projects/BATTLE2`, `D:/Projects/Bytefray-v1-rc1`) — no second writable agent on this tree |

Repository stability was confirmed by re-reading `HEAD` and `git status` after
an interval before any mutation; both were unchanged. The working tree was
hashed immediately before the qualification run and re-verified afterwards
(§24). No unexplained external write occurred at any point.

`docs/research/v4/V4_SPECTATOR_PHASE_{3,4,5,6,7}_RESEARCH.md` and
`docs/specs/v4_spectator_perspective.md` were read in full before any design
decision, along with the existing renderer/HUD architecture
(`pygame_renderer.py`, `hud_layout.py`, `replay_status.py`) — the last of
which materially changed the phase's scope (§8).

---

# PART A — MULTI-ENTRANT DIRECTOR QUALIFICATION

## 2. Multi-entrant corpus

Sixteen real matches were run through the real `NativeMatchService`, producing
genuine replay/trace pairs. Every measurement below is derived from
`analyze_pair` → `build_director_plan` on those artifacts. **No hand-built
Director event list was used anywhere in this phase.**

One constraint shaped the corpus: the v4 ruleset rejects overlapping entrant
cores, so entrant starts must be ≥ 8 cells apart. Genuine co-location is
therefore produced by agents that *converge* on a shared address mid-match
(`meeter`), not by adjacent spawns.

| Scenario | Entrants | Shape | Purpose |
|---|---:|---|---|
| `p2_quiet` | 2 | two hermits, no interaction | CRUISE baseline |
| `p2_pin` | 2 | hunter pins a hermit | Phase 7 carry-forward |
| `p2_wander` | 2 | detection opens/closes repeatedly | Phase 7's worst case, re-measured |
| `p3_pair_plus_quiet` | 3 | A vs B fight, C blind 260 cells away | **the §7 question** |
| `p3_staggered` | 3 | staggered A/B then B/C contacts | overlapping engagements |
| `p3_three_way` | 3 | all three in mutual reach | **heaviest 3-entrant load** |
| `p3_early_elim` | 3 | forfeit at tick 1, capture later | early elimination |
| `p3_colocated` | 3 | B and C converge on one address | co-location anonymity |
| `p3_blind` | 3 | C has reach 1 all match | little/no visibility |
| `p4_two_fights` | 4 | A vs B and C vs D simultaneously | **two independent engagements** |
| `p4_three_way_plus_quiet` | 4 | three-way fight, D blind | **heaviest 4-entrant load** |
| `p4_rapid_elim` | 4 | two forfeits plus a capture | rapid elimination sequence |
| `p4_long_quiet` | 4 | one pair fights, three quiet | long quiet entrants |
| `p4_heavy` | 4 | max self-write rate, zero aggression | write volume ≠ escalation |
| `p4_stacked_holds` | 4 | two forfeits plus movement | MAJOR-hold stacking |
| `p4_mixed_visibility` | 4 | watcher/wanderer/hunter/hermit | mixed contact visibility |

Every category the brief names (§6) is covered. Two scenarios initially came
back degenerate and were fixed rather than reported as passes: `p3_three_way`'s
hunters started 40 cells apart with reach 20 and never detected each other
(fixed by moving them into mutual reach — the match then derived 713 events),
and `p3_colocated`'s reader was sampling an unowned cell (fixed by having the
converging agents claim their destination).

## 3. Three-entrant Director results

Broadcast, default config. `x` is Director duration ÷ flat-18-TPS duration.

| Scenario | Ticks | Flat | Director | `x` | CRUISE | CONTACT | ENGAGE | HOLD | RECOV | longest slow | holds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `p3_pair_plus_quiet` | 81 | 4.50 s | 8.14 s | **1.81** | 79.0% | 4.9% | 7.4% | 2.5% | 6.2% | 16 | 2 |
| `p3_staggered` | 101 | 5.61 s | 10.25 s | **1.83** | 3.0% | 1.0% | 95.0% | 1.0% | 0% | 98 | 1 |
| `p3_three_way` | 91 | 5.06 s | 9.31 s | **1.84** | 1.1% | 0% | 97.8% | 1.1% | 0% | 90 | 1 |
| `p3_early_elim` | 15 | 0.83 s | 3.33 s | 4.00 | 40.0% | 6.7% | 6.7% | 13.3% | 33.3% | 6 | 2 |
| `p3_colocated` | 71 | 3.94 s | 7.94 s | 2.01 | 74.6% | 16.9% | 0% | 1.4% | 7.0% | 17 | 1 |
| `p3_blind` | 91 | 5.06 s | 8.61 s | 1.70 | 78.0% | 4.4% | 9.9% | 2.2% | 5.5% | 19 | 2 |

## 4. Four-entrant Director results

| Scenario | Ticks | Flat | Director | `x` | CRUISE | CONTACT | ENGAGE | HOLD | RECOV | longest slow | holds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `p4_two_fights` | 91 | 5.06 s | 8.53 s | **1.69** | 81.3% | 3.3% | 7.7% | 2.2% | 5.5% | 16 | 2 |
| `p4_three_way_plus_quiet` | 91 | 5.06 s | 9.19 s | **1.82** | 12.1% | 1.1% | 85.7% | 1.1% | 0% | 80 | 1 |
| `p4_rapid_elim` | 11 | 0.61 s | 3.11 s | 5.09 | 18.2% | 9.1% | 9.1% | 18.2% | 45.5% | 6 | 2 |
| `p4_long_quiet` | 121 | 6.72 s | 10.19 s | **1.52** | 86.0% | 2.5% | 5.8% | 1.7% | 4.1% | 16 | 2 |
| `p4_heavy` | 91 | 5.06 s | 6.00 s | 1.19 | 98.9% | 0% | 0% | 1.1% | 0% | 1 | 1 |
| `p4_stacked_holds` | 121 | 6.72 s | 8.83 s | 1.31 | 94.2% | 0% | 0% | 1.7% | 4.1% | 6 | 2 |
| `p4_mixed_visibility` | 101 | 5.61 s | 9.08 s | 1.62 | 83.2% | 3.0% | 6.9% | 2.0% | 5.0% | 16 | 2 |

## 5. The §7 question, answered

> *If only two entrants are actively fighting, should Broadcast slow the entire
> match?*

**Yes, and the measured consequence is acceptable.** Broadcast has one global
timeline, so a fight anywhere slows everywhere — but the fear the brief raises
("the Director becoming permanently slow because *someone* is always
fighting") does not materialize:

- Worst multi-entrant Broadcast inflation is **1.84x** (`p3_three_way`), which
  is *lower* than Phase 7's disclosed two-entrant worst case of **2.10x**
  (`p2_wander`, re-measured unchanged this phase).
- `p4_long_quiet` — one pair fighting while three entrants sit quiet for 121
  ticks — is the brief's exact scenario, and measures **1.52x** with 86%
  CRUISE. The three quiet entrants do not drag the match down.
- `p4_heavy` (four entrants writing at maximum rate, zero aggression) stays at
  98.9% CRUISE / 1.19x, re-confirming Phase 3's "volume ≠ meaning" finding at
  four entrants.

Adding entrants did **not** monotonically increase inflation. The two heaviest
matches in the corpus (`p3_three_way` at 713 events, `p4_three_way_plus_quiet`
at 531) land at 1.84x and 1.82x, essentially tied with the two-entrant worst
case, because fatigue caps them (§6).

### 5.1 The short-match exception, disclosed

`p3_early_elim` (4.00x) and `p4_rapid_elim` (5.09x) exceed 2x. Both are
**10–15 tick matches** where two 900 ms MAJOR holds dominate a sub-second flat
baseline. Absolute Director duration is 3.1–3.3 s. This is the same
short/decisive-match behavior Phase 7 measured and accepted (`elimination`
6.6x, `forfeit` 4.9x) — a blink-and-miss-it match becoming long enough to
actually read — not a multi-entrant regression. Restricting to matches of ≥ 60
ticks, **every** multi-entrant Broadcast plan measures ≤ 2.01x.

### 5.2 Hold stacking is not a practical concern

A four-entrant match can in principle stack up to three eliminations plus a
victory plus a match-end. Measured across all sixteen scenarios, the maximum
hold count in any plan was **2**: eliminations cluster onto the same tick (and
same-tick MAJOR events collapse into one hold by construction). `p4_two_fights`
kills two entrants simultaneously at tick 3 and produces a single hold there.
No remediation required; recorded as a measured bound rather than a hope.

## 6. Sustained-activity fatigue under multi-entrant load

The brief (§8) asks whether multiple unrelated engagements defeat the fatigue
rule by continuously refreshing important activity. **They do not, and the
reason is structural rather than lucky.**

Fatigue triggers on a *continuous elevated streak*. Additional concurrent
engagements make that streak **more** continuous, so fatigue engages **sooner**
under multi-entrant load, not later. The mechanism the brief worried might be
overwhelmed is the one multi-entrant load reinforces.

Proven as a counterfactual on the same real derivations, differing only in
whether `sustain_ticks_before_fatigue` is reachable:

| Scenario | Entrants | Flat | Fatigue **off** | Fatigue **on** | Saved |
|---|---:|---:|---:|---:|---:|
| `p2_wander` | 2 | 5.61 s | 34.06 s (6.07x) | 11.81 s (2.10x) | 22.25 s |
| `p3_staggered` | 3 | 5.61 s | 17.50 s (3.12x) | 10.25 s (**1.83x**) | 7.25 s |
| `p3_three_way` | 3 | 5.06 s | 15.89 s (3.14x) | 9.31 s (**1.84x**) | 6.58 s |
| `p4_three_way_plus_quiet` | 4 | 5.06 s | 14.94 s (2.96x) | 9.19 s (**1.82x**) | 5.75 s |
| `p4_two_fights` | 4 | 5.06 s | 8.78 s (1.74x) | 8.53 s (1.69x) | 0.25 s |

`p3_three_way` is the strongest case: 504 `HOSTILE_WRITE` and 178
`PROCESS_DISRUPTED` events, the Director elevated for 90 of 91 ticks, and the
rule still holds total duration to 1.84x.

Per the brief's instruction, this was **not** tuned toward an arbitrary 1x.
The residual ~1.8x is disclosed as a deliberate judgment: a continuously
active match genuinely reads better somewhat slowed.

### 6.1 A watchability caveat that is *not* a duration problem

`p3_three_way` sits in `ENGAGEMENT` for 97.8% of the match and `p3_staggered`
for 95%. Duration is fine, but the Director's *state label* is nearly constant
in these matches. This is a real input to Fight Night design and is why §17
rejects a Director-state-driven "match phase" graphic: such an element would
read `ENGAGEMENT` for the entire match and convey nothing.

## 7. Multi-entrant timing disclosure

The brief's §9 requirements, each measured on real multi-entrant matches:

**Hidden fighting does not slow an uninvolved entrant's plan.** In every case
the precondition was proven from the artifacts first — the entrant is
delivered *zero* events for the whole match — and only then was pacing
asserted.

| Match | Broadcast | Blind entrant | Blind entrant's visible events |
|---|---:|---|---:|
| `p3_pair_plus_quiet` | 1.81x, 79.0% CRUISE | **C: 1.21x, 98.8% CRUISE** | 0 |
| `p4_two_fights` | 1.69x, 81.3% CRUISE | **B: 1.19x, 98.9% CRUISE** | 0 |
| | | **D: 1.19x, 98.9% CRUISE** | 0 |
| `p4_three_way_plus_quiet` | 1.82x, 12.1% CRUISE | **D: 1.19x, 98.9% CRUISE** | 0 |
| `p4_long_quiet` | 1.52x, 86.0% CRUISE | **B/C/D: 1.14x, 99.2% CRUISE** | 0 |

`p4_three_way_plus_quiet` is the decisive one: 531 events, 297 hostile writes
and 153 disruptions happen between A, B and C, and D's plan stays flat CRUISE
at every tick before the terminal hold. D cannot learn that three enemies are
fighting by timing the playback.

**Entrant-visible contact does slow.** In the same match A/B/C measure
1.78–1.81x with 11.0–16.5% CONTACT — so the flat CRUISE above is a real
information boundary, not an inert match.

**Changing selected entrant changes pacing only by allowed information.** In
`p4_two_fights` the two blind hermits B and D produce *pacing-identical* plans
(same states, rates, holds, reasons, source events) while the two engaged
hunters A and C differ from them. The plans are not wholly identical — each
carries its own `visibility_basis` (`perspective:B` vs `perspective:D`) so any
decision remains traceable to the domain that produced it. An initial test
asserted whole-decision equality and failed on exactly this; the assertion was
corrected to compare pacing, and the reason documented in the test.

**Terminal policy remains consistent.** Every mode's plan holds at
`result_ticks` via the mode-independent `TERMINAL_HOLD` override, unchanged
from Phase 7.

## 8. Multi-entrant Director PASS gate (§10)

| # | Criterion | Result |
|---|---|---|
| 1 | Broadcast pacing remains reasonable | **PASS** — worst 1.84x, below Phase 7's 2.10x (§3–5) |
| 2 | Sustained activity does not trap the match in slow states | **PASS** — counterfactual measured, 3.14x → 1.84x (§6) |
| 3 | Perspective timing remains disclosure-safe | **PASS** — blind entrants flat CRUISE against 531-event matches (§7) |
| 4 | Multi-entrant mode switching is deterministic | **PASS** — repeated builds fingerprint-identical for 4 entrants |
| 5 | Seek/restart remain path-independent | **PASS** — forward, backward and shuffled traversals identical |
| 6 | No new semantic inference is required | **PASS** — no change to `spectator_director.py` or any derivation module |

**Gate passed. No Director remediation was required, so no
`fix(v4): harden director for multi-entrant matches` commit exists.** Phase 7's
§23.3 limitation is now closed by measurement rather than by inspection.

---

# PART B — FIGHT NIGHT INFORMATION ARCHITECTURE

## 9. The finding that shaped the phase: entrant cards already exist

Reading the renderer before designing anything changed the phase's scope. The
existing HUD **already ships per-entrant status cards** in its top band
(`hud_layout.calculate_layout`'s `entrant_card_rects`,
`format_entrant_card_lines`, driven by `replay_status.EntrantReplayStatus`),
carrying display name, ordinal badge, palette color, alive/dead/**CAPTURED**
with attribution, **core intact/total**, score, territory and kills — already
generic over 2/3/4+ entrants with detailed and compact modes.

The existing footer likewise already carries a Director state indicator
(`DIRECTOR <STATE> <rate>tps`), and the header already carries a terminal
result line.

Building "Fight Night entrant cards" and a "Fight Night match-phase indicator"
would therefore have been building a **second** copy of surfaces that already
exist and are already qualified. Per the brief's own instruction not to assume
all five candidate surfaces should ship, they were rejected (§17).

## 10. Data-source matrix

Every Fight Night element, with its source stated explicitly.

| Element | Source | Allowed in | Not derived from |
|---|---|---|---|
| Ribbon entry label | Fixed constant in `RIBBON_LABELS`, keyed by qualified `SpectatorEventKind` | Broadcast + Perspective (domain-filtered) | any renderer inference; no entrant id can be interpolated into a label |
| Ribbon entry subject | The source event's own `actors[0]` or `targets[0]`, per an explicit per-kind role table | as above | never both; never a joined pair |
| Ribbon entry identity | The source event's `(tick, sequence)` | audit/debug | never re-derived |
| Ribbon membership (Perspective) | Phase 3 `visible_to`, filtered **before** assembly | Perspective | never a post-hoc label filter |
| Ribbon ordering / recency | Dense per-tick prefix index into the entry list | both | never runtime accumulation |
| Opening card entrant roster | `PairBinding.entrant_identities` | both | never replay parsing |
| Opening card display names | `EntrantReplayStatus.name` (replay header `entrants[].name`) | both | never `agent.yaml` |
| Opening card ruleset label | `replay_status.resolve_match_ruleset_label` | both | never re-resolved by the renderer |
| Result card winner / termination | Canonical replay result record, via `SpectatorDerivation` | both (terminal exception, §12) | never inferred |
| Result card survivors | `EntrantReplayStatus.alive` for the current tick | both | never derived by Fight Night |
| Result card tick | `SpectatorDerivation.result_ticks` | both | never counted by the renderer |
| Phase (OPENING/LIVE/RESULT) | Pure function of the current tick vs `first_tick`/`result_ticks` | both | never a timer or animation clock |

**Fight Night derives nothing.** Each ribbon entry restates one already-derived
event and adds only a fixed label plus a single subject. A regression test
walks every entry of a 4-entrant heavy match and resolves it back to the exact
source event by `(tick, sequence)`, asserting kind and label agreement.

## 11. Perspective disclosure policy — Policy A, explicit

**Adopted: Policy A. Fight Night presents the selected entrant's own
information domain in Perspective mode, and canonical facts in Broadcast.**

The mechanism is the Director's, reused verbatim: the event stream is filtered
by `visible_to` **before** the ribbon is assembled, so a hidden fact is never
in the list the plan is built from rather than being in it and skipped.

Policy B (always-Broadcast chrome) was rejected on a specific distinction
between two kinds of disclosure:

- The existing top-band cards are **ambient** — always-present fields whose
  values drift.
- A ribbon entry is **reactive** — it appears at the exact moment something
  happens.

A reactive element is a far stronger channel, and is precisely the analogy the
brief draws to Phase 7's timing disclosure (§18). Two phases were spent making
Perspective mode structurally incapable of reacting to hidden facts; adopting
Policy B would have deliberately built a new reactive leak back into it.
Policy A also costs nothing extra — it is the same filter, reusing the same
Phase 3 computation.

**There is no ambiguous middle state, and the resolution is on screen, not
just in this document.** The ribbon's title line always names its own domain:

```text
FIGHT NIGHT · BROADCAST
FIGHT NIGHT · A KNOWS
```

A viewer never has to remember which view mode they selected to know what they
are reading.

### 11.1 A pre-existing leak Fight Night deliberately does not extend

The existing top-band cards show canonical core/territory/score/kills for
*every* entrant, unchanged, in Perspective mode. This is pre-existing Phase
5/6 behavior, separately qualified there as broadcast chrome, and is outside
Phase 8's scope to change — but it is a genuine information asymmetry with the
knowledge-limited arena beside it, and it is recorded plainly here (§25) with
a Phase 9 recommendation rather than left unmentioned. Fight Night neither
relies on it nor widens it.

## 12. Terminal exception

`MATCH_ENDED`/`VICTORY` are omniscient-only and can never reach a Perspective
stream. The result card is therefore built from **plan-level metadata**
(`winner`, `termination_reason`, `result_ticks`), never from a filtered event —
exactly the mechanism Phase 7 used for the Director's terminal hold, and for
the same reason: once the whole match is over there is no hidden gameplay left
to protect, and the already-qualified renderer shows the same terminal banner
in every mode (Phase 6 §11 item 09, re-confirmed unmodified this phase).

`AGENT_ELIMINATED` — a *specific* entrant's death, which may occur while a
larger match continues — remains fully excluded from Perspective ribbons.

## 13. Never names a second party

Every ribbon entry names **at most one** entrant, its `subject`. This is a hard
structural rule: `FightNightEvent.subject` is a single optional id, so there is
nowhere to put a counterparty.

| Source kind | Label | Subject |
|---|---|---|
| `DETECTION_GAINED` | `CONTACT` | actor (the observer) |
| `FIRST_HOSTILE_READ` | `FIRST HOSTILE READ` | actor (the reader) |
| `FIRST_HOSTILE_WRITE` | `FIRST HOSTILE WRITE` | actor (the attacker) |
| `CORE_CELL_LOST` | `CORE CELL LOST` | target (the victim) |
| `PROCESS_DISRUPTED` | `PROCESS DISRUPTED` | target (the victim) |
| `AGENT_ELIMINATED` | `ELIMINATED` | target (the victim) |
| `AGENT_FORFEITED` | `FORFEITED` | target (the victim) |
| `VICTORY` | `VICTORY` | actor (the winner) |
| `MATCH_ENDED` | `MATCH ENDED` | none |

The actor/target role is stated **explicitly per kind** rather than inferred by
a generic "targets else actors" rule, because the two families genuinely
differ — a detection is about the entrant that gained it, a core-cell loss is
about the entrant that lost the cell — and a generic rule would silently
mislabel every entry of an entire kind.

This makes `A ATTACKS B` structurally unconstructible, and answers §38's
READ-owner separation directly: a `FIRST_HOSTILE_READ` factually records both
the reader and the sampled cell's owner, and the ribbon presents **only the
reader**. The cell's owner is a fact about a memory address, never about the
anonymous spatial contact the reader can also see.

Every kind absent from the table is never presented at all.

## 14. First contact (§20)

The three candidate sources are **kept distinct, not collapsed**, because they
describe genuinely different events:

- `DETECTION_GAINED` → **`CONTACT`** — the engine told an entrant that an
  enemy anchor address is occupied. It never says whose. The label is
  therefore deliberately unattributed; naming a counterparty would invent
  knowledge (`docs/specs/v4_spectator_perspective.md` §6).
- `FIRST_HOSTILE_READ` → **`FIRST HOSTILE READ`** — someone sampled a
  foreign-owned cell.
- `FIRST_HOSTILE_WRITE` → **`FIRST HOSTILE WRITE`** — someone overwrote one.

Collapsing these into a single "FIRST CONTACT" would assert an equivalence the
artifacts do not support.

## 15. Event ribbon design and flood control

Two bounded, purely structural rules; neither weighs, ranks, or interprets an
event.

1. **Vocabulary restriction.** Only kinds in `RIBBON_LABELS` are eligible.
   Ordinary `HOSTILE_WRITE`, `HOSTILE_READ`, `DETECTION_LOST` and
   `EFFECTIVE_MOVE` are excluded by omission from one reviewable table.
2. **Repeat cooldown.** A repeat of the same `(label, subject)` within
   `repeat_cooldown_ticks` (12, set above the Director's
   `contact_lookback_ticks` of 8) is suppressed. Lifecycle events
   (elimination, forfeit, victory, match end) always bypass it — they are
   one-shot facts, so a cooldown could only ever suppress a genuinely distinct
   entrant's entry.

Measured across the corpus:

| Scenario | Total events | Ribbon-eligible | Ribbon entries | Reduction |
|---|---:|---:|---:|---:|
| `p3_staggered` | 550 | 280 | 29 | **9.7x** |
| `p3_three_way` | 713 | 200 | 32 | **6.2x** |
| `p4_three_way_plus_quiet` | 531 | 181 | 29 | **6.2x** |
| `p4_two_fights` | 47 | 25 | 11 | 2.3x |
| `p4_stacked_holds` | 243 | 3 | 3 | 1.0x |
| `p4_heavy` | 1 | 1 | 1 | 1.0x |

The important property is not the ratio but its **shape**: entries emerge in
bursts of at most one per entrant per cooldown window. In `p3_three_way` the
entry ticks are `1,1,1,1, 2,2,2,2,2, 3, 14,14,15, 26,26,27, 38,38,39, …` — a
legible ~12-tick rhythm of three subjects, not churn. Ribbon volume therefore
scales with **entrant count, not event volume**, which is asserted directly as
a bound in the test suite.

The cooldown is also verified monotone (a larger cooldown never produces more
entries), so tuning it cannot surprise a reviewer.

## 16. Path independence (§43)

The ribbon is **not** implemented as mutable runtime accumulation. A plan
stores the whole match's ordered entry list plus a dense per-tick prefix
count, and `ribbon_at_tick(N)` is a pure slice:

```python
end = cursor[N - first_tick]
return entries[max(0, end - ribbon_size) : end]
```

The ribbon at tick N depends on N alone. Verified along four traversals
(sequential, backward, backward-then-forward scrub, restart-then-seek) at
every tick of a four-entrant match, plus a no-look-ahead assertion that no
entry with `tick > N` can ever appear at tick N.

The same property makes **mode switching** and **restart** trivially clean:
because presentation is a pure function of `(plan, tick)`, there is no residue
to clear. The renderer's restart handler deliberately does nothing for Fight
Night, and says so in a comment.

## 17. Rejected designs

Recorded as rejections, with reasons, rather than silently omitted:

| Candidate | Decision | Reason |
|---|---|---|
| Fight Night entrant cards | **Rejected** | The HUD already ships them (§9). A second card system would duplicate a qualified surface and compete for the same band. |
| Fight Night match-phase / intensity indicator | **Rejected** | The footer already shows Director state, and §6.1 measured that state as ~constant (`ENGAGEMENT` 95–98%) in exactly the busy matches such a graphic would target. It would convey nothing. |
| Core/protected-cell bar or condition icon | **Rejected** | The cards already show `Core N/8`, which is an **ownership count, not HP**. A segmented bar or health-style meter would imply linear HP semantics the game does not have (brief §21's explicit warning). Nothing was added. |
| Card pulse / flash on disruption | **Rejected** | `PROCESS_DISRUPTED` means disruption, not death (§22), and a reactive flash is exactly the emphasis channel §18 forbids in Perspective mode. Disruption is a ribbon line only. |
| Per-entrant coloring of ribbon entries | **Rejected** | Coloring an entry in its subject's palette would let a viewer join an anonymous on-arena contact to a named entrant by matching hues — §27/§37's explicit negative regression. Entries use one fixed accent, never varying by entrant. |
| Extra elimination animation | **Rejected** | The Director's existing `IMPACT_HOLD` already provides readability (§23). No second timeline pause was invented. |
| Dedicated Fight Night HUD band | **Rejected** | Would shrink the arena. At 640×480 a four-entrant detailed card grid already sits within **4px** of the top band cap, so a reserved band would silently re-flow that layout. Fight Night reserves no layout space at all. |
| v2-era process-count / spawn-wave graphics | **Rejected** | Phases 3/4 established v4 has no comparable dynamic process birth/death semantics (brief §13). Not designed around. |

## 18. Data model and architecture

Following the Director's already-qualified seam exactly — deterministic plan in
the engine, thin manager in the client, renderer decides only *how to draw*:

```text
canonical replay + API-v2 trace
              ↓  analyze_pair  (paid once, shared)
      SpectatorDerivation
         ↓            ↓             ↓
 PerspectiveMgr   DirectorMgr   FightNightMgr
                                     ↓
                              FightNightPlan   (pure, immutable, indexed)
                                     ↓
                              FightNightState  (per tick)
                                     ↓
                                 renderer
```

| Module | Contents |
|---|---|
| `engine/src/battle_engine/spectator_fight_night.py` | `FightNightMode`, `SubjectRole`, `RIBBON_LABELS`, `FightNightConfig`, `FightNightEvent`, `FightNightPlan`, `build_fight_night_plan` |
| `client/src/battle_client/fight_night.py` | `FightNightPhase`, `FightNightAvailability`, `FightNightState`, `FightNightManager` |
| `client/src/battle_client/hud_layout.py` | pure geometry + text formatting (no pygame import) |
| `client/src/battle_client/renderers/pygame_renderer.py` | drawing only |

**There is no runtime class.** The Director needs a clock to decide whether a
hold has finished waiting; Fight Night needs only the current tick. That
absence is the architectural reason seek/restart/mode-switch are clean.

`FightNightManager` is constructed from the already-computed
`SpectatorDerivation` (`PerspectiveManager.derivation`) and does no work beyond
storing it — no second `analyze_pair`, confirmed by inspection of `cli.py`'s
single construction site.

## 19. Opening and result presentation

**Opening card** shows at `tick == first_tick` and nowhere else — derived from
the tick alone, with no timer and no animation. Consequences, matching §44
exactly: a restart returns to tick 0 and shows it again; a seek into mid-match
never shows it; any step or play leaves it immediately, so it can never trap
the viewer (§39).

It lists one entrant per line rather than a single `A vs B vs C vs D` string:
at 640×480 a four-entrant single line with realistic display names does not
fit, and wrapping would break it at arbitrary points. One line each also lets
each name truncate independently instead of the last entrant losing its name.

**Result card** shows at `tick >= result_ticks`, carrying winner (or
`DRAW / TIE`, worded consistently with the existing
`format_terminal_state_line`), termination reason, result tick, and survivors.
It uses the Director's existing terminal hold; no additional delay was stacked.

## 20. Layout: no reserved space, and the letterbox finding

Fight Night reserves **no layout space**. `calculate_layout` takes no Fight
Night argument, so identical window/entrant inputs produce identical geometry
whether the feature is on or off — the arena is never shrunk and the cards
never re-flow.

Visual qualification then produced a genuine mid-phase improvement. The first
implementation anchored the ribbon to the arena band's lower-left, and the
screenshots showed it overlaying battlefield cells. Measuring the real geometry
across supported window sizes and entrant counts explained why that was
avoidable:

| Window | Entrants | Arena left gutter | Gutter below arena |
|---|---:|---:|---:|
| 640×480 | 2 | 170 px | 6 px |
| 640×480 | 4 | **190 px** | 0 px |
| 500×420 | 4 | 140 px | 6 px |
| 1280×820 | 2 / 4 | **320 px** | 6 px |
| 640×820 | 2 | 0 px | 6 px |

Because the arena is drawn at an integer cell scale centered in its band, a
*horizontal* letterbox column is the normal case (130–320 px), while the gutter
below is only ever 0–6 px. The ribbon now takes that column whenever it is
≥ 150 px wide, falling back to overlaying only when the arena already spans the
full width. At the documented 640×480 minimum with four entrants this moves the
ribbon **entirely clear of the arena — no battlefield cell is covered at all**,
which is what the standing "the arena shows the battle, the HUD explains the
battle" rule actually asks for.

The narrower column is why `format_fight_night_ribbon_line` drops its tick
prefix before touching the label: at 150 px the longest entry renders as
`A · PROCESS DISRUPTED` with the label intact. Directly visible in
`W_01_min_640x480` (§22), where two entries show the tick and two have shed it.

Below the minimum the ribbon degrades line by line and then disappears
(capacity 4 at 400 px viewport height, <4 at 130 px, 0 at 80 px or below
200 px width) rather than forcing a larger window.

## 21. Long entrant names — closing Phase 6's open item

Phase 6 §12/§20 item 4 disclosed that its long-name stress test **did not
actually exercise long names**: the custom `agent.yaml` `name:` field never
reached the HUD. The cause is now identified: the replay header's
`entrants[].name` comes from the `MatchEntrant` the *caller* constructs, not
from `agent.yaml`. Phase 8's fixtures set it there, so long names genuinely
reach the presentation path.

Verified with four realistic 41–43 character names at 640×480:

- **Entrant cards** truncate with ellipsis inside their own cards
  (`RECURSIVE PERIMETER DENIAL CONSTRUCT…`) — no overlap, no unbounded
  expansion, no arena displacement, no footer collision.
- **Opening card** displays all four names **in full without truncation**
  (screenshot `LN_04_opening_640`), because the card is 420 px wide and
  centered.
- **Result card** and **ribbon** fit their budgets; asserted for 2, 3 and 4
  entrants in `client/tests/test_fight_night.py`, including that the entrant id
  survives truncation so the card still identifies who is fighting.

## 22. Visual qualification (real Windows pygame)

37 screenshots captured driving the real `PygameRenderer` — real SDL 2.28.4,
real Windows video driver, real fonts, not the dummy driver — using `run()`'s
own production setup path with only the blocking event loop replaced by a
scripted sequence, matching Phase 7's methodology.

### 22.1 Mandatory disclosure cases

| # | Case | Result |
|---|---|---|
| `P_03_blind_D_heavy` | **Perspective D, tick 30 of `p4_three_way_plus_quiet`** (531 events, 297 hostile writes, 153 disruptions in progress between A/B/C) | **No ribbon at all.** Arena shows only D's own process. Footer: `Contacts: 0 current`. No card flash, no ribbon item, no identity color. **The §36 negative regression, visually confirmed.** |
| `P_04_active_A_heavy` | Perspective A, same match and tick | Ribbon reads `FIGHT NIGHT · A KNOWS` with a single entry `T14 A · CONTACT`. Broadcast at this tick has dozens of writes/disruptions involving A; none appear, because `HOSTILE_WRITE` is omniscient-only — the engine never tells the writer whose cell it took. |
| `P_05_colocation_A` | Perspective A, `p3_colocated`, tick 40 | `Contacts: 1 current, 13 stale`, all anonymous neutral rings with no entrant color. Ribbon: `T1 A · CONTACT` only. **Nothing connects the single contact to B or C** by color, order, label or emphasis. |
| `P_01/P_02` | Blind C vs Broadcast, same tick | Broadcast escalates; C's view stays quiet with an empty ribbon. |

### 22.2 Entrant-count and layout checklist

| # | Case | Result |
|---|---|---|
| `2p_01…06` | 2 entrants: opening, quiet, contact, engagement, elimination, result | All correct; ribbon quiet during quiet play. |
| `3p_01…05` | 3 entrants: active pair + quiet third, elimination, three-way | `3p_04` shows the §15 rhythm: `T3 B / T14 A / T14 C / T15 B · PROCESS DISRUPTED` — readable, not flooded, from a 178-disruption match. |
| `4p_01…05` | 4 entrants: opening, simultaneous events, result, heavy, rapid elimination | `4p_02` shows two simultaneous kills at tick 3 as four coherent lines. All four cards visible throughout. |
| `W_01_min_640x480` | 640×480, 4 entrants | Ribbon entirely in the left gutter; **arena completely unobstructed**; all four cards fit. |
| `W_02_narrow_500x420` | below minimum | Compact cards; ribbon still fits, overlays the band's lower-left (gutter 140 px < 150 px threshold). Degrades, does not break. |
| `W_03_wide_1280x820` | wide desktop | Ribbon in the 320 px gutter; arena untouched. |
| `LN_01…05` | long names at default and 640×480 | §21. |
| `G_01_diagnostics` | Perspective A + Director + Fight Night + `F3` | All coexist. Fight Night overlaps neither debug panel. |

### 22.3 Fight Night OFF vs ON (§32)

Same replay, same tick 3, same Broadcast mode (`X_01_fn_off` / `X_02_fn_on`):

- **Is the match easier to understand?** Yes. OFF, the cards show two entrants
  `CAPTURED` but give no sense of sequence. ON, the ribbon states
  `B · PROCESS DISRUPTED / D · PROCESS DISRUPTED / B · ELIMINATED /
  D · ELIMINATED` at T3 — the viewer immediately grasps that two independent
  fights resolved simultaneously on one tick.
- **Is the arena still primary?** Yes — at 640×480 the ribbon occupies the
  letterbox column and covers no cell.
- **Does the extra UI distract?** No; it is static between events.
- **Does it reveal facts it should not?** No (§22.1).
- **Does it fit at minimum resolution?** Yes.
- **Is ordinary replay unchanged when OFF?** Yes — `X_01_fn_off` is
  pixel-equivalent to the pre-Phase-8 viewer.

### 22.4 Feature-combination matrix (§41, §42)

All four Fight Night × Director combinations were rendered
(`X_01`, `X_02`, `D_01`, `D_02`). Neither feature requires the other: Fight
Night draws from its own plan and never consults Director state. Perspective ×
Fight Night verified for Broadcast, A, C and D, plus same-tick mode switching.

Screenshots are retained in the session's scratch directory as qualification
evidence, not committed — matching Phase 6/7 convention.

## 23. Performance and memory

Measured on a purpose-built **4-entrant, 3,001-tick, 1,024-cell, 18,341-event**
fixture (the largest used in any spectator phase to date).

| Operation | Cost |
|---|---:|
| `analyze_pair` (shared prerequisite, paid once, reused) | 3187.82 ms |
| `build_fight_night_plan` (broadcast) | **3.51 ms** |
| `build_fight_night_plan` (perspective:A / B / C / D) | 2.52 / 2.17 / 0.83 / 0.83 ms |
| `build_director_plan` (broadcast, same fixture, for comparison) | 15.80 ms |
| Cold build of **all five** modes | **10.02 ms** |
| `FightNightManager` warm `plan_for` | 0.000118 ms |
| `FightNightPlan.ribbon_at_tick` | **0.000268 ms** |
| `FightNightManager.state_at_tick` (the per-frame call) | **0.001337 ms** |

The per-frame cost is **0.008% of a 16.7 ms 60 fps frame budget**, four orders
of magnitude under it, and Fight Night plan construction is *cheaper* than the
Director's on the same fixture. There is no O(history) per-frame work: the
ribbon is an index lookup and a slice.

Memory, same fixture:

| Item | Size |
|---|---:|
| `FightNightEvent` (shallow) | 48 bytes |
| Broadcast `ribbon_entries` | 728 objects, 5,864-byte tuple |
| Broadcast `ribbon_cursor` | 3,001 ints, 24,048-byte tuple |
| Approx retained per plan | **63.3 KiB** |
| Approx retained, all five modes | **≤ 316.7 KiB** |

No eviction architecture was added; none is justified at this scale, and the
brief (§46) explicitly says not to add one without measured need.

## 24. Qualification integrity

| Check | Before full suite | After full suite |
|---|---|---|
| `HEAD` | `13daf72fe0ea30867c20d823027145c5f22b3600` | `13daf72fe0ea30867c20d823027145c5f22b3600` (unchanged) |
| `git status --short` | clean | clean (unchanged) |
| SHA-256 of 11 critical files | recorded | **identical** |

```text
c62e6c7a5af098bf9f6ce9c4418994d0cba8515b6e31b4a804b0f43c9cd59b87  engine/src/battle_engine/spectator_director.py
1bd143b5528177edf178f579dc6f0e361029e09c152b8b8c07b03540feffc788  engine/src/battle_engine/spectator_fight_night.py
978bc346111af6a23d25dc364e223e778cc639ef905d2abf3d7702b115e5ce11  engine/src/battle_engine/spectator_derivation.py
7d32ef4f9e70d3f94450104f4f55b0c53643bd92e97468fac8146a5ce4f58d97  engine/src/battle_engine/spectator_perspective.py
1ef7c43c56a3e54c0179f45bf4855f5d66b63eb657ae841657e9834823e48f17  client/src/battle_client/director.py
68d34ecc1bafef7f5ddcdffd4d594f7d9f0c25968a2d77726298c73745c69fbe  client/src/battle_client/fight_night.py
ff9ad9af3af77f438926511317cfe57211c63d25ec306a0df2fb3c34fae22e1a  client/src/battle_client/perspective.py
2878c805fe2e93c4898785472cb610ba52f507d0b7fc236869dc28c89ee39eda  client/src/battle_client/player.py
711d8f004972666951cf6931612ad9e4fe7fb98fc13f29190f74f5b85c3c6922  client/src/battle_client/hud_layout.py
5927754122906b05aa79e43a1290216f752146d30319f52fc0aca0891349573b  client/src/battle_client/cli.py
f0387b3eaf2722fe1350c5486b7641fed8f989f583802aed8a0065901ccc1e93  client/src/battle_client/renderers/pygame_renderer.py
```

### 24.1 Simulation and replay isolation (§61)

The real renderer was driven through all four Fight Night × Director
combinations over the same replay, seeking to ticks 0/3/45/90 in each:

```text
replay sha256 before/after: 022ffe6cd31b8f3a33df36fd4b31c595ea294a5a70dff0cd309f9321c83828af
trace  sha256 before/after: ac3315406b82ea7333a8950f8e6de74233364713a451b346698e932d71368f42
ARTIFACTS UNCHANGED: True

    FN    DIR   winner      termination   tick   arena
 False  False     None       tick_limit     90     400
 False   True     None       tick_limit     90     400
  True  False     None       tick_limit     90     400
  True   True     None       tick_limit     90     400

ALL FOUR COMBINATIONS PRODUCE ONE IDENTICAL RESULT IDENTITY: True
```

Winner, termination reason, tick count, arena state, per-entrant score and
per-entrant alive flags were all compared and are identical.
**Fight Night has zero simulation authority.**

### 24.2 Static qualification

```text
ruff check .                   -> All checks passed! (plus the pre-existing,
                                  unrelated .pytest-cache-v141 access warning)
mypy engine/src/battle_engine  -> Success: no issues found in 101 source files
mypy client/src/battle_client  -> Success: no issues found in 15 source files
git diff --check               -> clean
```

`mypy` file counts increased by exactly one on each side (100→101 engine,
14→15 client), matching the one new module added to each package. No broad
autofix churn: the only `ruff` findings during development were two `RUF022`
`__all__` ordering notes and two `PIE808` `range(0, n)` notes, all fixed by
hand in the lines concerned.

## 25. Tests

| Suite | Count |
|---|---:|
| `engine/tests/test_v4_spectator_multi_entrant.py` (Phase 8A) | **7 passed** |
| `engine/tests/test_v4_spectator_fight_night.py` (Phase 8B–D) | **19 passed** |
| `client/tests/test_fight_night.py` (Phase 8C–D) | **22 passed** |
| **Phase 8 focused total** | **48 passed** |
| Phase 1–7 regression gate, **Phase 7's exact file set** | **308 passed** (identical to Phase 7's reported figure) |
| Phase 1–7 gate extended with `test_v4_spectator_director.py` + `test_hud_layout.py` | 413 passed |
| `client/tests/` (full) | **432 passed, 2 deselected** |
| `engine/tests/` (full, isolation) | **2372 passed, 14 skipped** |
| **True full repository suite** | **2806 passed, 14 skipped, 2 deselected**, 300.55 s |

Suites were run sequentially with distinct `--basetemp` directories
throughout; no two overlapped.

### 25.1 Arithmetic reconciliation

Phase 7 closed at 2758 passed / 14 skipped / 2 deselected.
**2758 + 7 + 19 + 22 = 2806** — exact match, no unexplained residual. Client
410 + 22 = 432 and engine 2346 + 26 = 2372 reconcile independently. The
Phase-7-identical regression subset reproduces **308** exactly.

### 25.2 Coverage against the §55 checklist

Every named item has at least one focused test: multi-entrant Broadcast
Director; multi-entrant Perspective Director; sustained-activity fatigue
(counterfactual); hidden-event timing safety; 2/3/4-entrant presentation state;
event-ribbon determinism; Fight Night seek equivalence; restart behavior; mode
switch clearing; hidden-event suppression; co-location anonymity; READ-owner
separation; long-name layout; minimum-window layout; Fight Night disabled
compatibility.

### 25.3 Three defects found by testing, not by inspection

1. `test_perspective_plans_are_independent_across_four_entrants` initially
   asserted whole-decision equality for two blind entrants and failed on
   `visibility_basis`. The **test** was wrong, not the code; the assertion was
   narrowed to pacing fields and the reason documented in the test itself
   rather than the assertion being deleted.
2. `test_no_ribbon_entry_ever_names_more_than_one_entrant` first substring-
   searched labels for entrant ids and failed on `"C" in "CONTACT"`. Replaced
   with a strictly stronger and correct property — every label is one of the
   fixed `RIBBON_LABELS` constants, so no entrant id can be interpolated into a
   label by any code path.
3. `test_read_owner_never_becomes_an_opponent_identity` failed because the
   co-location fixture's reader was sampling an **unowned** cell, producing no
   hostile read at all. The fixture was corrected (the converging agents now
   claim their destination) rather than the assertion weakened.

The `test_perspective_cam_keyboard_dispatch` mock gap (`K_n` missing from a
hand-built `SimpleNamespace` key table) is the same class of issue Phase 7 hit
with `K_g`; the key was added to keep the mock matching the renderer's real
table. It adds zero test count.

## 26. Integration surface

Minimal, matching §48 and Phase 7's restraint. **Default OFF.**

| Surface | Detail |
|---|---|
| CLI | `--fight-night` (requires a trace, like `--director`) |
| Keyboard | `N` toggles in-viewer |
| Manager | Built whenever a trace exists, so `N` works without a restart; only the *initial* enabled state depends on the flag |
| Help | Footer expanded-help line documents `N night` |

The expanded-help line hit exactly the condition Phase 7 anticipated: it had
5 characters of slack and `N night` needs 10. Following Phase 7's own recorded
instruction — *"if a future addition finds no slack left, drop something here
rather than truncating silently"* — `0 fit` was dropped rather than
abbreviating every other binding down to a zero-slack line. Zoom-to-fit remains
bound to `0`; it is simply no longer advertised, being both the viewer's
default state and adjacent to the still-listed `[/]` zoom hint. The line now
measures **86 characters against the 89-character budget** at 640 px — 3 to
spare, re-verified by test.

Manual controls (play, pause, step, seek, restart, Director toggle, manual
speed, Perspective switching) are entirely untouched: `dispatch_key` returns
`toggle_fight_night` without calling any controller method, asserted directly.

---

## 27. Hostile self-review (§51)

| Question | Answer |
|---|---|
| Does Fight Night derive any new combat semantics? | **No.** Every entry restates one derived event, verified by resolving all entries back to `(tick, sequence)`. |
| Does the renderer decide what is true? | **No.** It receives `FightNightState` and chooses only where/how to draw. |
| Can hidden Perspective events trigger card emphasis? | **No.** Filtered before assembly; no card emphasis exists at all. |
| Can hidden identity leak through entrant color? | **No.** One fixed accent; entries never vary by entrant. |
| Can co-located anonymous contacts be associated with cards? | **No** — asserted in tests and confirmed visually (`P_05`). |
| Can READ owner become opponent identity? | **No.** Only the reader is presented; asserted per entry. |
| Can the event ribbon depend on playback path? | **No.** Pure index slice; four traversals verified. |
| Can event volume flood the ribbon? | **No.** Bounded by entrant count per cooldown window, not event volume. |
| Does the multi-entrant Director remain watchable? | **Yes** — 1.52–1.84x on ≥ 60-tick multi-entrant matches. |
| Does one active pair make four-player Broadcast permanently slow? | **No** — `p4_long_quiet` measures 1.52x with 86% CRUISE. |
| Do cards fit with four entrants? | **Yes**, at 640×480. |
| Do long names fit? | **Yes** — §21, closing Phase 6's open item. |
| Does 640×480 remain usable? | **Yes**, with the arena fully unobstructed. |
| Does the arena remain visually primary? | **Yes** — the ribbon takes the letterbox column. |
| Does Director OFF still work? | **Yes** — independent managers, verified in all four combinations. |
| Does Fight Night OFF reproduce existing viewer behavior? | **Yes** — no layout input, no draw call. |
| Does Perspective switching clear presentation residue? | **Yes** — there is no residue to clear by construction. |
| Does seeking reproduce identical presentation state? | **Yes**, verified at every tick. |
| Does Fight Night mutate simulation/replay/trace state? | **No** — artifact hashes and result identity unchanged (§24.1). |
| Is the feature actually easier to understand when watched? | **Yes** — §22.3, with the honest caveat that this is one reviewer's judgment on 37 screenshots, not a user study. |

## 28. Limitations

Disclosed plainly rather than omitted.

1. **The existing top-band entrant cards remain omniscient in Perspective
   mode** (§11.1) — showing every entrant's canonical core, territory, score
   and kills beside a knowledge-limited arena. Pre-existing Phase 5/6 behavior,
   outside Phase 8's scope, neither relied on nor widened by Fight Night, but a
   real asymmetry and the single strongest Phase 9 candidate.
2. **The existing header spoils the match result from tick 0** — line 2 reads
   `MATCH COMPLETE — …` at every tick, including tick 0 (visible in every
   screenshot). Pre-existing Phase 4 HUD behavior, unrelated to Fight Night,
   but it does undercut the opening card's purpose and is worth a future pass.
3. **The Perspective and Director debug overlays genuinely overlap at 640 px**
   (`G_01_diagnostics`), clipping the perspective panel's right edge. Phase 7
   disclosed this as "adjacent, not overlapping" (§23.4); at this width it is a
   real overlap. Diagnostic-only, `F3`-gated, unrelated to Fight Night.
4. **The ribbon overlays the arena band's lower-left when no ≥150 px letterbox
   column exists** — a tall narrow window whose arena spans the full width
   (e.g. 640×820 with two entrants). Bounded, toggleable with `N`, and the same
   tradeoff the already-qualified capture callout makes against the top band.
5. **Comprehension improvement is a reviewer judgment, not a measured one.**
   §22.3's OFF/ON comparison is my assessment of 37 screenshots; no user study
   was run, and none is claimed.
6. **Sustained-activity fatigue remains tuned to ~1.8x, not ~1x** — carried
   forward unchanged from Phase 7 §23.2 and re-confirmed acceptable at 3 and 4
   entrants rather than re-tuned.
7. **Ribbon cooldown and size were set from corpus measurement, not from
   viewer preference testing.** `repeat_cooldown_ticks=12` and `ribbon_size=4`
   are both `FightNightConfig` fields, overridable, and their monotonicity is
   tested — but no one has watched a match at cooldown 20 and said it read
   better.
8. **No `--fight-night` documentation exists outside this document, the CLI's
   `--help`, and the in-viewer `?` panel** — the same three surfaces Phase 7
   judged sufficient for a feature of this scale; no dedicated user guide was
   written.

None are classified as blocking. Items 1–3 are pre-existing and inherited.

## 29. Phase 9 Color Commentator readiness

**GO WITH PREREQUISITES.**

Phase 8 leaves a commentator able to consume four qualified, stable inputs
without inventing a single combat fact:

- qualified semantic events with an explicit `visible_to` audience (Phase 3);
- entrant-safe `PerspectiveState` (Phases 4–6);
- deterministic `DirectorPlan` state, rate and reason (Phase 7);
- `FightNightPlan`/`FightNightState` — already-labelled, already-subjected,
  already-flood-controlled presentation facts with `(tick, sequence)`
  provenance (Phase 8).

That last one matters most: a commentator consuming `FightNightEvent` inherits
the vocabulary restriction, the repeat cooldown, the single-subject rule and
the domain filter for free, rather than re-deriving any of them.

Prerequisites before commentary ships:

1. **Resolve limitation 1** (omniscient cards in Perspective mode) first. A
   commentator speaking in an entrant's voice beside a HUD showing that
   entrant's opponents' core state would be incoherent, and the fix belongs
   below the commentary layer.
2. **Define the commentary information domain explicitly and up front**, the
   way §11 does here — a spoken line is the loudest reactive channel yet, and
   the Policy A/B question must be settled before any generation.
3. **Prose generation must stay outside the deterministic plan.** The
   Phase 7/8 pattern — deterministic plan in the engine, presentation in the
   client — should hold, with any LLM or template stage consuming plan output
   and never feeding back into it.
4. **Cadence needs the §6.1 finding.** In busy multi-entrant matches the
   Director state is ~constant, so a commentator keyed to state *transitions*
   would fall silent for 95% of exactly the matches most worth commenting on.
   Ribbon entries (bounded per entrant per window) are the better clock.

## 30. Release-readiness assessment

**PUBLISH NEXT V4 ALPHA.**

| Dimension | Assessment |
|---|---|
| Perspective Cam | Qualified Phases 4–6; unmodified and fully regression-covered this phase (308 identical). |
| Dynamic Director pacing | Qualified Phase 7; now qualified at 3 and 4 entrants with **no remediation needed** — the last open Phase 7 item is closed by measurement. |
| Fight Night presentation | Implemented, visually qualified, default OFF, zero simulation authority. |
| Multi-entrant watchability | Measured 1.52–1.84x on ≥60-tick 3- and 4-entrant matches, better than the two-entrant worst case. |
| Windows visual quality | 37 real-SDL screenshots across 2/3/4 entrants, three window sizes, long names, and every disclosure case. |
| Ordinary replay compatibility | Both new features default OFF; OFF reproduces existing viewer behavior exactly; artifacts and result identity provably unchanged. |

v4 now has a distinct spectator identity that a two-entrant flat-speed replay
viewer did not: you can watch a four-way match, follow it from the ribbon, see
it paced around real events, and cut to any entrant's own limited view — with
the information boundary between those modes tested rather than asserted.

**Color Commentator is not required to justify this release**, and the brief is
right that it should not be. The three residual pre-existing HUD items (§28.1–3)
are all cosmetic or scope-inherited, none blocks a prerelease, and §28.1 is
better fixed as deliberate Phase 9 work than rushed in now.

Recommended sequencing: publish the alpha from this branch's feature work,
then open Phase 9 with limitation 1 as its first task.

## 31. Recommended Phase 9

**Perspective HUD coherence, then Color Commentator.**

Phase 9 should open by resolving §28.1 — deciding what the top-band cards may
show in Perspective mode — because it is both the largest remaining
information-boundary inconsistency in the viewer and a hard prerequisite for
coherent commentary. §28.2 (the header spoiling the result at tick 0) is a
small, self-contained fix worth folding into the same pass. Only then should
commentary work begin, on the terms in §29.
