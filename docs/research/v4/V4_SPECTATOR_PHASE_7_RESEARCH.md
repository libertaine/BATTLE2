# Bytefray v4 Spectator Research Phase 7 — Spectator Director, Dynamic Pacing, and Timing-Disclosure Research

## Verdict

**PASS.**

Phase 7 asked whether Bytefray matches can be made more watchable by varying
playback speed around meaningful factual events, without ever letting *when*
a tick is shown leak information a viewer is not entitled to. The answer is
yes: a deterministic Director plan can be built as a pure function of an
already-derived event stream, Perspective mode's plan can be made
structurally incapable of reacting to a hidden fact (not merely filtered
after the fact), and a real corpus run surfaced and fixed a genuine
"five-minute slog" defect before any of this reached a GUI. The research
gate (§39 of the phase brief) passed on all eight criteria, so minimal GUI
integration was completed and visually qualified on real Windows pygame.

| Area | Classification |
|---|---|
| Deterministic `DirectorPlan` (pure function of derivation/mode/config) | **IMPLEMENTED AND QUALIFIED** |
| Broadcast vs. Perspective information-domain separation | **IMPLEMENTED AND QUALIFIED** |
| Timing-disclosure negative regression (hidden event → no reaction) | **IMPLEMENTED AND QUALIFIED** |
| Sustained-activity "five-minute slog" defect | **FOUND, ROOT-CAUSED, AND FIXED** |
| Wall-clock runtime layer (`PlaybackDirectorRuntime`) | **IMPLEMENTED AND QUALIFIED** |
| Per-mode plan/runtime caching (`DirectorManager`) | **IMPLEMENTED AND QUALIFIED** |
| Manual-control precedence | **IMPLEMENTED AND QUALIFIED** |
| Minimal GUI integration (CLI flag, keybinding, indicator, diagnostics) | **IMPLEMENTED AND VISUALLY QUALIFIED** |
| Shared-analysis reuse (no duplicate `analyze_pair`) | **CONFIRMED** |
| Full repository suite | **PASS (2758 passed, 14 skipped, 2 deselected)** |
| **Phase 7 overall** | **PASS** |

---

## 1. Baseline

| Fact | Value |
|---|---|
| Repository | `D:\Projects\BATTLE2` |
| Starting branch | `v4-spectator-phase6-development` |
| Starting `HEAD` | `8a2f08ecbd09419bcf6d4a117da9acb468b87cc9` (matched the phase brief's expected starting `HEAD` exactly) |
| `origin/main` | `4aa8ac3a4cc0deccfdd6c5b94136933b315335be` |
| Initial `git status` | clean (aside from the pre-existing unreadable `.pytest-cache-v141`) |
| Development branch | `v4-spectator-phase7-development` (created from `8a2f08e`) |
| Implementation commit | `b309749dd681de92826196268f35ef9f69f8b77e` |

Twelve peer Claude Code sessions were present on the machine at session start
(`ListAgents`). Unlike Phase 6, no ambiguous same-repository signal was
present requiring a live confirmation: the working tree was hashed
immediately before branching, re-verified for drift immediately before the
final qualification run, and found byte-identical throughout (§19). No
unexplained external write occurred at any point.

Phase 1–6 commits (`d7b46bb` … `8a2f08e`) were confirmed present as ancestors
of the branch before any work began. `docs/research/v4/V4_SPECTATOR_PHASE_
{3,4,5,6}_RESEARCH.md` and `docs/specs/v4_spectator_perspective.md` were read
in full before any design decision.

---

## 2. Information-Channel Analysis

The phase brief's central risk (§6–7) is that a Director slowing playback in
response to an omniscient-only fact — one the selected entrant was never
told — discloses that fact through timing even if the renderer draws
nothing. Phase 3 had already answered "who is told what" exhaustively for
all 13 event kinds (`SpectatorEventKind`): 8 of 13 are `_OMNISCIENT_ONLY`
(`HOSTILE_WRITE`, `FIRST_HOSTILE_WRITE`, `CORE_CELL_LOST`,
`PROCESS_DISRUPTED`, `AGENT_ELIMINATED`, `AGENT_FORFEITED`, `MATCH_ENDED`,
`VICTORY` — `visible_to == ()` always), and the remaining 5 carry
`visible_to` naming exactly the entrant the v4 engine actually informed.

The design decision this phase made is to **reuse that existing
computation as the Director's entire information boundary**, rather than
build a second one: a Perspective Director's input stream is
`tuple(event for event in derivation.events if entrant_id in
event.visible_to)`, computed *before* the pacing state machine ever runs.
Because the omniscient-only kinds' `visible_to` is always empty, they can
never appear in that filtered stream for any entrant — the state machine
that computes CONTACT/ENGAGEMENT/holds physically never sees them, rather
than seeing them and being told to ignore them. This is the difference the
brief's §7 explicitly asks for ("do not simply filter event labels after
making an omniscient pacing decision — the decision itself must be derived
from an allowed information set").

---

## 3. Broadcast vs. Perspective Director Policy

Both are the *same* function, `build_director_plan(derivation, mode=...,
entrant_id=...)`, differing only in which event stream is handed to the
state machine (§2). No second interpretation engine, no parallel pacing
logic, no per-mode special-casing beyond the input filter and one
mode-independent terminal-hold rule (§6).

One deliberate exception was designed and tested: **match termination**.
`MATCH_ENDED`/`VICTORY` are always omniscient-only, so they can never reach
a Perspective stream — yet by the time the whole match has ended there is no
further hidden gameplay left to protect, and the renderer already shows the
same terminal banner identically in Broadcast and every Perspective mode
(Phase 6 §11 item 09, re-confirmed unmodified this phase). The Director's
terminal hold is therefore driven by `SpectatorDerivation.result_ticks` — a
match-level fact on the derivation object itself, never a per-entrant-
filtered event — so Broadcast and every Perspective mode end on the same
tick with the same hold, without the Perspective state machine ever reading
an omniscient event kind to get there. `AGENT_ELIMINATED` (a *specific*
entrant's death, which may occur while the whole match continues in a
larger bracket) remains fully excluded from Perspective streams; only the
whole-match-is-over fact is treated as safe.

---

## 4. Director Data Model

```
DirectorMode           BROADCAST | PERSPECTIVE
DirectorPacingState    CRUISE | CONTACT | ENGAGEMENT | IMPACT_HOLD | RECOVERY
EventSignificance       NONE | LOW | MEDIUM | HIGH | MAJOR
DirectorReason          NO_SIGNIFICANT_ACTIVITY | CONTACT_SIGNAL |
                        ENGAGEMENT_SIGNAL | SUSTAINED_CONTACT |
                        SUSTAINED_ENGAGEMENT | MAJOR_EVENT_HOLD |
                        TERMINAL_HOLD | RECOVERY_RAMP
DirectorConfig          rates, hold_ms, lookback windows, fatigue params
DirectorDecision        tick, state, rate_tps, hold_ms, reason,
                        source_events, visibility_basis, boundary
DirectorPlan            mode, entrant_id, visibility_basis, match_id,
                        replay_sha256, config_fingerprint, decisions
```

No event bus, no plugin system, no generic workflow/state-machine
framework, no abstraction for a future commentator — matching the
repository's established Phase 3 restraint. `source_events` names
`(tick, sequence)` identities into `SpectatorDerivation.events`, never
event *content*, so a decision is auditable back to the exact record that
justified it without the plan itself needing to embed any interpreted
prose.

---

## 5. Candidate States Selected and Rejected

Selected: `CRUISE, CONTACT, ENGAGEMENT, IMPACT_HOLD, RECOVERY` (brief §11's
first candidate list).

Rejected: `BUILD_UP, SUSPENSE, BRAWL, IMPACT_HOLD, NORMAL` (the second
candidate list) — not on vocabulary size (both are five states) but on
naming discipline. The chosen names describe *what triggers and decays each
state* (contact = a MEDIUM-tier signal is within lookback; engagement = a
HIGH-tier signal is within lookback; recovery = decaying out of either),
which keeps the state machine self-documenting and avoids narrative/mood
language that the repository's Phase 1–3 documents have already flagged as
a scope-creep risk ("no dramatic interpretation... no editorial language").
`SUSPENSE`/`BRAWL`/`NORMAL` read as commentary judgments about a match; the
five chosen names read as facts about a lookback window.

Every state was corpus-confirmed to produce a materially different rate
(§9): CRUISE 18 TPS, CONTACT 3 TPS, ENGAGEMENT 6 TPS, RECOVERY 10 TPS, plus
a sixth *rate value* (`sustained_rate_tps`, 12 TPS) applied to CONTACT/
ENGAGEMENT after sustained continuous activity (§8) — deliberately not a
sixth *state*, since the label shown to the viewer is still honestly
CONTACT/ENGAGEMENT (the fact is still active), only the rate and the
`DirectorReason` change.

---

## 6. Event Significance Mapping

The brief's §14 starting hypothesis was corpus-validated **unchanged**:

| Tier | Kinds |
|---|---|
| MAJOR | `AGENT_ELIMINATED`, `AGENT_FORFEITED`, `VICTORY`, `MATCH_ENDED` |
| HIGH | `PROCESS_DISRUPTED`, `CORE_CELL_LOST`, `FIRST_HOSTILE_WRITE` |
| MEDIUM | `DETECTION_GAINED`, `FIRST_HOSTILE_READ`, `HOSTILE_WRITE` |
| LOW | `HOSTILE_READ`, `DETECTION_LOST`, `EFFECTIVE_MOVE` |

No event was reclassified between tiers after running the corpus (§9). The
`test_default_significance_matches_the_phase_7_starting_hypothesis` engine
test pins this mapping exactly and asserts every one of the 13 kinds has a
tier. **No event mappings were rejected or revised** — the corpus problem
found (§8) was a *state-machine* defect (sustained repeated MEDIUM/HIGH
events never decaying), not a *tier* defect, and was fixed without moving
any event between tiers.

---

## 7. Rejected State/Event Mappings

None, beyond §5's rejection of the second state-name candidate list. The
brief's explicitly-forbidden invented events (`AMBUSH`, `DESPERATION`,
`MOMENTUM`, `DOMINANCE`, `COMEBACK`, `NEAR_DEATH`) were never introduced;
`DirectorReason` contains no free-text or subjective values.

---

## 8. Rate Research and the Sustained-Activity Defect

### 8.1 Starting values and corpus method

A seven-scenario corpus (`no_contact`, `early_contact`, `elimination`,
`high_volume`, `competitive`, `long_quiet_then_wander`, `forfeit`) was built
from small, real, purpose-written v4 agents and run through
`analyze_pair` → `build_director_plan` for Broadcast and every entrant's
Perspective, using `tools/spectator_director.py`'s underlying module
directly. Per-match statistics recorded: flat-rate duration (at CRUISE's 18
TPS), Director duration, state-occupancy percentages, hold count, and
longest continuous slow/fast run.

### 8.2 The finding

`long_quiet_then_wander` (two entrants oscillating in and out of detection
range for nearly the whole match) spent **97 of 101 ticks (96%) continuously
re-triggering CONTACT** — every few ticks a fresh `DETECTION_GAINED`/`LOST`
pair refreshed the lookback window before it could expire. Broadcast
duration measured **33.40 s against a 5.61 s flat baseline — a 5.95x
inflation**, matching the exact "five-minute slog" antipattern the phase
brief names by example (§16: "A 600-tick match should not become a
five-minute slog because the Director classifies everything as important").
`early_contact` (a seeker permanently pinning a stationary hermit) showed
the same shape at ENGAGEMENT's rate: 95% ENGAGEMENT, 7.46 s against 2.28 s
flat (3.27x).

### 8.3 Root cause and fix

The lookback-window decay rule (§9) correctly prevents a *single* event from
holding CONTACT/ENGAGEMENT forever, but a *stream* of repeated same-tier
events refreshes the window indefinitely — each new event arrives before
the previous one's window expires, so the state never reaches RECOVERY. A
"sustained-activity fatigue" rule was added: once CONTACT or ENGAGEMENT (or
IMPACT_HOLD) has held continuously for more than `sustain_ticks_before_
fatigue` (10) ticks, a still-elevated tick's rate is overridden to
`sustained_rate_tps` (12 TPS — between ENGAGEMENT's 6 and CRUISE's 18) with
reason `SUSTAINED_CONTACT`/`SUSTAINED_ENGAGEMENT`, while the *state* label
stays honestly CONTACT/ENGAGEMENT (the fact is still true; only the pace of
showing it changes). This is the smallest addition that fixes the defect:
one new threshold, one new rate, no new state, no probabilistic smoothing
(explicitly forbidden by brief §17).

### 8.4 Measured result after the fix

| Scenario | Before fix | After fix | Flat baseline |
|---|---:|---:|---:|
| `long_quiet_then_wander` (Broadcast) | 33.40 s | **11.65 s** (2.08x) | 5.61 s |
| `early_contact` (Broadcast) | 7.46 s | **5.04 s** (2.21x) | 2.28 s |

Worst-case inflation dropped from ~6x to ~2x. The remaining ~2x is judged
acceptable and disclosed rather than driven further toward 1x: a
continuously active match *is* more watchable slowed down somewhat, and 2x
on a match under two minutes is not a slog by the brief's own illustrative
standard. `no_contact`, `high_volume`, and `competitive` (98–99% CRUISE)
showed Director duration only marginally exceeding flat (by exactly the one
900 ms terminal hold), confirming high write/move volume alone never
triggers slowdown (Phase 3's own "3,416 writes → 1 meaningful event"
finding, carried forward: `EFFECTIVE_MOVE` and ordinary `HOSTILE_READ` are
LOW-tier and never independently escalate state).

### 8.5 Final rate configuration

| Parameter | Value |
|---|---:|
| `cruise_rate_tps` | 18.0 |
| `contact_rate_tps` | 3.0 |
| `engagement_rate_tps` | 6.0 |
| `recovery_rate_tps` | 10.0 |
| `sustained_rate_tps` | 12.0 |
| `impact_hold_ms` | 900 |
| `contact_lookback_ticks` | 8 |
| `engagement_lookback_ticks` | 6 |
| `recovery_ticks` | 5 |
| `sustain_ticks_before_fatigue` | 10 |

All are `DirectorConfig` fields, overridable per call (and via
`tools/spectator_director.py --cruise-rate` etc. for further research). The
non-monotonic curve is deliberate: CONTACT (first detection — the suspense
moment) is the *slowest* rate, slower than ENGAGEMENT (sustained active
exchange), matching the brief's own example behavior ("slow when opponents
make meaningful contact... moderate speed during active exchanges").

---

## 9. Hysteresis and Cooldown Design

Three mechanisms, each the smallest addition that solved a real,
corpus-observed problem — no probabilistic smoother was introduced:

1. **Event lookback** (`contact_lookback_ticks`, `engagement_lookback_ticks`)
   — a tier's state persists for N ticks after its *most recent* qualifying
   event, so a single isolated event does not cause an immediate
   fast/slow/fast flicker on the very next tick.
2. **Recovery state** — after a lookback expires, `RECOVERY_TICKS` (5) more
   ticks at an intermediate rate (10 TPS) precede a full return to CRUISE,
   rather than snapping directly from CONTACT/ENGAGEMENT to CRUISE.
3. **Sustained-activity fatigue** (§8.3) — bounds worst-case total duration
   when the first two mechanisms alone would otherwise never decay.

`test_contact_decays_through_recovery_back_to_cruise` proves the full
CONTACT → RECOVERY → CRUISE decay curve against a real derived event, with
an explicit rate ordering assertion (`contact_rate < recovery_rate <
cruise_rate`). Corpus transition counts (`long_quiet_then_wander`,
Perspective:B) showed 11 state transitions over 101 ticks — real, bounded
oscillation driven by genuinely repeated real contact, not tick-to-tick
flicker.

---

## 10. Impact Holds and Terminal Behavior

A MAJOR-tier event (or the terminal-hold override, §3) produces
`IMPACT_HOLD` with `hold_ms = 900`. A hold is a **wall-clock pause on the
currently-displayed tick**, implemented entirely in the client-side runtime
(§12) — it never inserts a simulation tick, never duplicates replay state,
and never changes event order; `DirectorPlan` construction and
`ReplaySession`/replay bytes are completely unaffected (confirmed by
`build_director_plan` never importing anything from `battle_engine.replay`,
`match_service`, or `agent_trace`).

Terminal behavior, tested directly: the tick equal to
`SpectatorDerivation.result_ticks` always resolves to `IMPACT_HOLD` — either
because the real `MATCH_ENDED`/`VICTORY` events are themselves MAJOR-tier
and already produce it (Broadcast; `test_broadcast_terminal_hold_is_driven_
by_the_real_match_ended_event`), or via the mode-independent override when
those events are absent from the filtered stream (Perspective;
`test_perspective_terminal_hold_uses_the_mode_independent_override`). After
the hold, the session naturally reaches `at_end` and `PlaybackController`
auto-pauses (pre-existing, unmodified behavior) — Director does not force a
resume; a user pressing Play at the end restarts from tick 0 (also
pre-existing `PlaybackController.play()` behavior, unmodified).

---

## 11. Deterministic Plan Architecture and Look-Ahead Policy

`build_director_plan(derivation, mode, entrant_id, config)` is a pure
function: it imports nothing that could vary run to run, its ordering is
either trace-file position (already fixed by Phase 3) or an explicit
tick-indexed loop, and `DirectorPlan.plan_fingerprint()` hashes every
decision field via `json.dumps(..., sort_keys=True)` — a wall-clock
timestamp is never part of a plan or its identity.

**Look-ahead**: a decision at tick N is computed from trackers
(`last_medium_tick`, `last_high_tick`, `last_elevated_tick`,
`elevated_streak_start`) updated using only events at ticks `<= N`, proven
directly: `test_a_decision_at_tick_n_never_depends_on_events_after_tick_n`
truncates a real derivation's event stream and `last_tick` at a cutoff, and
asserts every decision up to that cutoff is **byte-for-byte identical**
between the full and truncated derivation — a Director computing tick 20's
decision cannot possibly have used tick 25's event, because the truncated
derivation never contained it. The one disclosed exception (§3, §10) is the
terminal-hold override, which uses `result_ticks` — a fact about the whole
match, known before tick 1 exists to be rendered — but only ever changes
the decision *at* the terminal tick itself, never an earlier one; the same
truncation test's cutoff was deliberately chosen below `result_ticks` to
isolate this from the general no-lookahead proof.

---

## 12. Runtime Wall-Clock Architecture

`battle_client.director.PlaybackDirectorRuntime` is the **only** place in
either the engine or client Director code that calls a clock. It holds
exactly three pieces of mutable state: `_consumed_holds` (a set of ticks
whose hold has already been waited out this traversal), `_active_hold_tick`,
and `_active_hold_started_at` (an injected-clock timestamp). Everything else
about a decision — state, rate, hold duration, reason — comes from the
immutable `DirectorPlan` and is looked up, never recomputed, per frame.

A genuine bug was found and fixed here during testing (§16): the original
implementation only reset stale hold-in-progress bookkeeping when *returning
to the same tick*, so leaving a held tick to visit a third, hold-free tick
before returning left the old start timestamp in place — a path-dependent
defect the brief's own §48 checklist asks about by name ("does seeking
produce path-dependent pacing decisions"). The fix makes any observed tick
change (to *any* different tick, whether or not it has a hold of its own)
unconditionally clear the stale bookkeeping before evaluating the new tick's
own decision.

`PlaybackController.reset_accumulator()` — one new public method, four lines
— was added so the runtime can discard the real elapsed time that passed
during a hold without reaching into the controller's private accumulator
field.

---

## 13. Timing-Disclosure Regression (Mandatory)

`test_perspective_director_never_reacts_to_omniscient_only_events` (engine)
is the direct implementation of brief §31. Fixture: an `EXECUTIONER` walks
toward a stationary `SLEEPER` (reach 1) and strips its core cell by cell,
ending in a real `AGENT_ELIMINATED`. Precondition proven from the real
derivation before asserting anything else: `[e for e in derivation.events if
"B" in e.visible_to] == []` — the victim is delivered **zero** events for
the entire match, a fact about the real artifact, not an assumption. Given
that precondition, the test asserts:

- Broadcast reaches both `ENGAGEMENT` and `IMPACT_HOLD` over the match.
- Perspective(B) stays `CRUISE` at **every tick strictly before the terminal
  tick**, with `source_events == ()`.
- Perspective(B) only reaches `IMPACT_HOLD` at the terminal tick itself, via
  `TERMINAL_HOLD` (the mode-independent override, §3) — never via a
  `MAJOR_EVENT_HOLD` citing the (invisible-to-B) elimination event.

This was also directly visually confirmed on real pygame (§15, screenshot
`D_perspective_victim_01`): while Broadcast/omniscient view of the same
match shows active core-loss combat, entrant B's own Perspective Director
footer reads `DIRECTOR CRUISE 18tps` with `Contacts: 0 current` — the
same match, the same tick, two honestly different pacing experiences.

---

## 14. Research Corpus

| Scenario | Shape | Purpose |
|---|---|---|
| `no_contact` | two hermits, no interaction | high-volume-immune CRUISE baseline |
| `early_contact` | seeker permanently pins a hermit | sustained-ENGAGEMENT stress test |
| `elimination` | executioner strips a core, real kill | escalation → MAJOR hold |
| `high_volume` | max self-write rate, zero aggression | write volume ≠ escalation |
| `competitive` | two seekers, never in range | move volume ≠ escalation |
| `long_quiet_then_wander` | detection opens/closes repeatedly | sustained-CONTACT stress test (found the defect) |
| `forfeit` | scripted crash, forfeit victory | short/decisive match readability |
| `_drift_by` / `_kill` (engine tests) | isolated single-event decay; core-capture escalation | exact-tick regression fixtures |

Each scenario is named to the specific design decision it drove (§8's
sustained-activity fix came directly from `long_quiet_then_wander` and
`early_contact`; the terminal-hold override came directly from `no_contact`
having no in-stream terminal event other than `MATCH_ENDED` itself).

---

## 15. Duration Comparisons

See §8.4 for the two matches that mattered most. Full corpus summary
(Broadcast, post-fix):

| Scenario | Ticks | Flat (18 TPS) | Director | Holds |
|---|---:|---:|---:|---:|
| `no_contact` | 61 | 3.39 s | 4.23 s | 1 |
| `early_contact` | 41 | 2.28 s | 5.04 s | 1 |
| `elimination` | 3 | 0.17 s | 1.12 s | 1 |
| `high_volume` | 61 | 3.39 s | 4.23 s | 1 |
| `competitive` | 81 | 4.50 s | 5.34 s | 1 |
| `long_quiet_then_wander` | 101 | 5.61 s | 11.65 s | 1 |
| `forfeit` | 4 | 0.22 s | 1.07 s | 1 |

Short/decisive matches (`elimination`, `forfeit`) show the largest
*relative* inflation but the smallest *absolute* one — exactly the intended
effect: a 2-tick blink-and-miss-it match becomes long enough (~1.1 s) to
actually read, without adding meaningful wall-clock time to the session.

---

## 16. Startup Analysis Reuse

`DirectorManager.__init__` takes an already-computed `SpectatorDerivation`
and does no work beyond storing it — no `verify_pair`, no `derive_events`.
`PerspectiveManager` gained one new public property, `derivation`, returning
the same `SpectatorDerivation` its own (already-eager) `_probe_availability`
built. `cli.py`'s `_run_interactive` constructs `DirectorManager(
perspective_manager.derivation if perspective_manager is not None else
None, ...)` — the Phase 6-documented ~2.7 s `analyze_pair` cost on a large
match is paid at most once per session, exactly as it already was before
this phase, confirmed by inspection (no second `analyze_pair`/`verify_pair`
call site was added anywhere in this phase's diff).

---

## 17. Performance

Measured on a purpose-built 3,000-tick / 1,024-cell-arena fixture (two
processes, continuous READ/MOVE activity, mirroring the Phase 5/6 large-
fixture methodology):

| Operation | Cost |
|---|---:|
| `analyze_pair` (shared prerequisite, paid once, reused) | 1655.76 ms |
| Broadcast plan build | 6.945 ms |
| Entrant A plan build | 7.103 ms |
| Entrant B plan build | 6.289 ms |
| Warm `decision_for_tick` (avg of 1000 lookups) | 0.00008 ms |
| `DirectorManager` first `plan_for("broadcast")` (cold) | 5.907 ms |
| `DirectorManager` warm `plan_for("broadcast")` | 0.00150 ms |
| `DirectorManager` first `plan_for("A")` (cold) | 5.932 ms |

Every plan-build cost is under 0.5% of this fixture's own `analyze_pair`
cost, and warm per-tick lookup is four orders of magnitude under the 16.7 ms
60 fps frame budget (§45's requirement). Because plan-build cost is
dominated by the O(ticks) per-tick loop rather than event count (this
fixture derived only 1 event across 3,000 ticks, yet cost the same order as
the richer 40–100-tick corpus scenarios scaled up), a match with many more
events is not expected to cost meaningfully more — the per-tick loop does a
small, bounded amount of additional list-comprehension work per event, not
a new pass over the whole match.

Eager precomputation of every entrant's plan would in fact have been
*affordable* at these costs (a 4-entrant match: ~28 ms total, still
negligible next to `analyze_pair`) — but lazy per-mode construction (§16,
mirroring `PerspectiveManager`'s own lazy design) was kept anyway, since it
costs nothing extra to do so and stays consistent with the existing pattern
rather than introducing an unjustified asymmetry.

---

## 18. Memory

One `DirectorDecision` is a small frozen dataclass (8 scalar/tuple fields);
shallow `sys.getsizeof` on a populated instance measured 48 bytes, and a
3,001-tick plan retains exactly 3,001 such objects (`len(plan.decisions) ==
3001`, confirmed) plus small per-decision tuples (`source_events`, usually
empty). This is two to three orders of magnitude smaller than a single
entrant's `PerspectiveProjection` frame list on the same fixture (Phase 6
§17: tens of thousands of retained `ReadKnowledge`/`CallbackPoint` objects
for the large fixture). No eviction policy was implemented — none is
justified at this scale, and the brief (§46) explicitly says not to add one
without measured need.

---

## 19. Manual Visual Assessment (Real Windows Pygame)

Twenty screenshots were captured driving the actual `PygameRenderer` (real
SDL, real Windows video driver, not the dummy driver) through eight real
matches, using `PygameRenderer.run()`'s own production setup path with only
the blocking event loop replaced by a scripted sequence (frames advanced via
the real `PlaybackDirectorRuntime.update()`/`PlaybackController.update()`
methods, using the real wall clock — genuine `time.sleep` between some
frames to exercise real hold-waiting, not a simulated clock).

| # | Scenario | Checklist item | Result |
|---|---|---|---|
| A | Quiet match (two hermits, 60 ticks) | Fast enough? | `DIRECTOR CRUISE 18tps` for the entire match; terminal `IMPACT_HOLD` at the end. Correct. |
| B | First contact / elimination | Readable? | "CORE CAPTURED" callout and "MATCH COMPLETE — Winner: A" banner both visible at the paused terminal hold. Correct. |
| C | Heavy repetitive activity (seeker pins hermit) | Avoids permanent slow-stick? | Reaches the true match end (tick 40/40) within a bounded scripted advance; footer shows `ENGAGEMENT`/`SUSTAINED_ENGAGEMENT` transitions rather than an unbounded crawl. Correct — the §8 fatigue fix is directly visible here. |
| D | Perspective Cam, victim's own view | Reacts only to entrant-allowed info? | `DIRECTOR CRUISE 18tps`, `Contacts: 0 current` at tick 30, on the *same match* Broadcast shows actively engaged at that tick. This is the mandatory §13 finding, visually confirmed. |
| E | Broadcast ↔ Perspective switching | Sensible transitions? | At tick 4: Broadcast `ENGAGEMENT 6tps`; switched to Perspective(B) shows `CONTACT 3tps` (B's own brief real contact, correctly *not* CRUISE, correctly *not* ENGAGEMENT — an honest, different, real signal); switched back to Broadcast reproduces `ENGAGEMENT 6tps` exactly — same-tick determinism confirmed visually, not just by unit test. |
| F | Manual pause / seek | Pause wins immediately? Seek recomputes cleanly? | Paused mid-`ENGAGEMENT`; stayed frozen through 500 ms of real elapsed wall-clock time with no advance. Seeking to tick 5 while still paused immediately showed the correctly recomputed `ENGAGEMENT 6tps` for that tick. Correct. |
| G | Restart | State resets? | Before restart: tick 16, engaged. Immediately after: tick 0, `DIRECTOR CRUISE 18tps` — no stale elevated/hold state carried over. Correct. |
| H | Diagnostic overlay | Developer-only detail, no extra disclosure? | `DIRECTOR DEBUG: perspective:B` panel (top-right) and the existing `PERSPECTIVE DEBUG` panel (top-left) both visible without overlapping; Director panel shows tick/state/rate/reason/source-event-identity only — no resolved event content, no omniscient fact. Correct. |

Screenshots are retained in the session's scratch directory (not committed;
they are qualification evidence, not project assets, matching Phase 6's own
convention of not committing venv/screenshot artifacts).

One cosmetic-only observation, not a defect: the footer indicator continues
to read `DIRECTOR IMPACT_HOLD HOLD 0ms` once a hold has already been fully
consumed and the session has reached its true end — factually accurate
(zero milliseconds remain) but could read more clearly as "hold complete."
Left as a disclosed limitation (§23) rather than engineered around, since it
only ever appears at the very last, already-paused frame of a match.

---

## 20. Manual-Control Behavior

Audited and tested directly:

- **Pause** wins immediately: `PlaybackDirectorRuntime.update()`'s first
  check is `if not controller.playing or controller.session.at_end: return`
  — identical guard shape to `PlaybackController.update()`'s own, so a
  paused controller is untouched by the Director in every possible frame,
  proven by `test_manual_pause_makes_update_a_no_op` and visually confirmed
  (§19.F).
- **Step** and **seek** are not mediated by the Director at all — the
  renderer's key dispatch calls `PlaybackController.step_forward()` /
  `seek_relative()` / `session.seek()` directly, exactly as it did before
  this phase; the Director only ever influences the *next* frame's
  `runtime.update()` call, which recomputes the new tick's decision
  deterministically (no path dependence — §11).
- **Manual speed** (`+`/`-`/`[`/`]` are unrelated to speed;
  `+`/`-`/PageUp/PageDown are) disables the Director rather than fighting
  it: `_loop` compares `controller.speed` before and after `dispatch_key`
  and sets `self._director_enabled = False` on any change, so the user's
  explicit choice always wins outright rather than being silently
  overridden on the very next frame. The user can re-enable with `G`.
- **Restart** clears every cached mode's runtime hold state
  (`DirectorManager.restart()` iterates every built runtime), confirmed by
  `test_manager_restart_clears_every_cached_runtime_independently` and
  visually (§19.G).

---

## 21. Tests

| Suite | Count |
|---|---:|
| Engine focused (`test_v4_spectator_director.py`) | **13 passed** |
| Client focused (`test_director.py`) | **9 passed** |
| **Phase 7 focused total** | **22 passed** |
| Phase 1–6 regression gate (`test_spectator_analyzer`, `test_spectator_aggregation`, `test_agent_trace`, `test_v4_trace_equivalence`, `test_v4_spectator_derivation`, `test_v4_spectator_perspective`, `test_perspective.py`, `test_pygame_renderer.py`, `test_playback_controller.py`) | **308 passed** |
| `client/tests/` (full) | **410 passed, 2 deselected** |
| `engine/tests/` (full, isolation) | **2346 passed, 14 skipped** |
| **True full repository suite** (`_legacy/tests`, `engine/tests`, `client/tests`) | **2758 passed, 14 skipped, 2 deselected**, 282.92 s |

### 21.1 Arithmetic reconciliation

Phase 6 closed at 2736 passed / 14 skipped / 2 deselected. Phase 7:
**2736 + 13 (engine) + 9 (client) = 2758** — exact match, no unexplained
residual. The one pre-existing test touched
(`test_perspective_cam_keyboard_dispatch` in `client/tests/test_perspective.
py`) was not new; its hand-built `SimpleNamespace` pygame-key mock was
missing the new `K_g` key entirely (a real `AttributeError`, not a design
defect) and was extended with `K_g=103` to stay in sync with the renderer's
real key-dispatch table — this added zero test count, only fixed a mock gap
the new key exposed.

### 21.2 A real defect found by testing, not merely reported

`test_leaving_an_unfinished_hold_and_returning_restarts_its_timer` initially
failed against my first `PlaybackDirectorRuntime.update()` implementation,
which only reset stale hold bookkeeping when *returning to the same tick*
(§12). The test's failure led directly to the fix, not the other way
around — the test was not adjusted to match buggy behavior.

---

## 22. Qualification Integrity

| Check | Before full suite | After full suite |
|---|---|---|
| `HEAD` | `b309749dd681de92826196268f35ef9f69f8b77e` | `b309749dd681de92826196268f35ef9f69f8b77e` (unchanged) |
| `git status --short` | clean | clean (unchanged) |
| SHA-256 of 9 critical files | recorded | **identical** |

Critical files hashed: `engine/src/battle_engine/spectator_director.py`,
`client/src/battle_client/director.py`, `client/src/battle_client/player.py`,
`client/src/battle_client/renderers/pygame_renderer.py`,
`client/src/battle_client/perspective.py`, `client/src/battle_client/cli.py`,
`client/src/battle_client/hud_layout.py`,
`engine/src/battle_engine/spectator_derivation.py`,
`engine/src/battle_engine/spectator_perspective.py`.

Static checks (against the final commit):

```text
ruff check . -> All checks passed! (plus the pre-existing, unrelated
                 .pytest-cache-v141 "Access is denied" warning)
mypy engine/src/battle_engine -> Success: no issues found in 100 source files
mypy client/src/battle_client  -> Success: no issues found in 14 source files
git diff --check -> clean, no warnings
```

`mypy` file counts increased by exactly one on each side (99→100 engine,
13→14 client), matching the one new module added to each package.

---

## 23. Limitations

Disclosed plainly rather than omitted:

1. **The footer's terminal hold indicator reads "HOLD 0ms" once already
   consumed**, rather than a clearer "hold complete" state (§19). Cosmetic
   only, confined to the final paused frame of a match.
2. **Sustained-activity fatigue (§8) was tuned to ~2x worst-case duration
   inflation, not driven all the way to ~1x.** This was a deliberate
   judgment call (a continuously active match reads better somewhat
   slowed), disclosed rather than defended as objectively optimal; a future
   pass could research whether an even gentler `sustained_rate_tps` (closer
   to `cruise_rate_tps`) reads better without losing the "something is
   happening" signal.
3. **Only a two-entrant corpus was used.** The engine test suite includes a
   3/4-entrant equivalence test at the *derivation* layer (Phase 3), and
   nothing in `build_director_plan` distinguishes entrant count (it only
   ever looks at `event.kind` and `event.tick`), but no multi-entrant
   Director-specific corpus match was built this phase to visually confirm
   pacing coherence when two independent fights proceed simultaneously —
   flagged as a Phase 8 corpus item rather than assumed safe by inspection
   alone.
4. **The Director debug overlay and the perspective debug overlay can sit
   close together at narrow window widths** (visually adjacent, not
   overlapping, in the captured 640-class screenshots) — not a defect, but
   not stress-tested at the documented 640×480 minimum specifically for
   this pairing.
5. **No `--director`-specific help/README documentation was added outside
   this research document and the CLI's own `--help` text and in-viewer `?`
   panel** — those three surfaces were judged sufficient for a Phase-7-scale
   feature, matching the restraint the brief asks for, but a dedicated user
   guide was not written.

None of these are classified as blocking. The phase brief's own explicit
information-boundary and pacing-sanity requirements are met and evidenced;
the items above are honestly-scoped residuals.

---

## 24. Phase 8 Recommendation

**GO, with the multi-entrant corpus item from §23.3 as a prerequisite before
building presentation on top of Director output.**

The three layers Phase 8's brief anticipates building on —
qualified factual events (Phase 3), qualified Perspective Cam (Phase 4–6),
and qualified dynamic pacing (Phase 7) — are each independently evidenced
and none needed to be reopened to build the next: Director consumes Phase
3's `visible_to` computation unchanged, and never touches
`spectator_perspective.py`'s knowledge-boundary logic at all (confirmed by
import inspection — `spectator_director.py` imports only from
`spectator_derivation`). A future Fight Night presentation phase can treat
Director's `DirectorPlan`/`PlaybackDirectorRuntime` boundary the same way
this phase treated Perspective's `PerspectiveManager`/`PerspectiveCursor`
boundary: a stable seam to build on, not a layer to reopen.
