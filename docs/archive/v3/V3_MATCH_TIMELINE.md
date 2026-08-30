# Bytefray v3.0 — Match Timeline

Branch: `v3.0-development`. Status: complete, not merged, not tagged, not
published.

A small, bounded Replay Viewer addition: a whole-match timeline across the
top of the footer band. It shows where playback currently is within the
entire match, marks the ticks that recorded an event, and can be clicked or
dragged to seek anywhere in the replay. No Ruleset, scoring, scheduler,
Agent API, or replay-schema change of any kind — the Viewer only reads
replay facts that already existed.

---

## A. Initial state

Verified before any change:

- Branch `v3.0-development`, HEAD `26484d0` ("feat: add Replay Viewer
  core-capture callouts"), working tree clean.
- Read `docs/V3_PRODUCT_SCOPE.md` (thesis, compatibility freeze, phase
  plan, non-goals) and `docs/V3_CORE_CAPTURE_CALLOUT.md` (the immediately
  preceding fun feature, so this one would not duplicate it).
- Inspected `client/src/battle_client/` (`pygame_renderer.py`,
  `hud_layout.py`, `player.py`, `session.py`, `analysis.py`), `app/`
  (Designer views/widgets/services), and the existing v3 Phase 1–3 and
  core-capture screenshot sets.

---

## B. Why this, and why not something else

### The gap, measured rather than assumed

A survey of 400 recorded replays under `runs/` established two facts that
together decided this feature:

| observation | figure |
|---|---|
| replays containing **any** recorded event | **6 of 400** (8 kill events in total) |
| final tick across those replays | **50 to 2000+** |
| coarsest keyboard navigation step | **10 ticks** (`Shift`+arrow) |

Before this change the Replay Viewer had **no position-proportional
control at all**. Reaching an arbitrary point in a 2000-tick replay meant
roughly 200 keypresses; `Home`/`End` reached only the two extremes. The
footer's territory graph is deliberately a *trailing 300-tick window*
(`TERRITORY_HISTORY_WINDOW_TICKS`), so it answers "what happened recently",
never "where am I in this match". Nothing in the viewer answered the second
question.

### What the same evidence ruled out

The obvious adjacent idea — "jump to the next/previous recorded event"
keys — was **rejected** by the same measurement: in 98.5% of real replays
there are no events to jump to, so the control would do nothing almost
every time it was pressed. For the same reason, event marks are treated
here as a near-free bonus on top of the track (they reuse the already
collected `self._match_events`, and cost about fifteen lines), never as the
feature's justification. The eventless track is the common case and is
fully useful on its own — see §F's first screenshot.

### Why it is not duplicative

The two neighbouring footer features answer different questions, and the
timeline was deliberately shaped not to overlap either:

* **Territory graph** — a trailing window of *ownership percentages*. A
  trend readout, not a control; not clickable, not whole-match.
* **Core-capture callout** (the previous v3.0 fun feature) — announces a
  capture *as forward playback passes it*, then disappears. It is the
  moment. The timeline is the **map**: it shows where that moment sits so a
  user can go back to it, which the callout by design cannot do (it is
  cleared by any seek, and never replays).
* **Footer event line** — the single most recent event, as text.

---

## C. Files changed

| File | Change |
|---|---|
| `client/src/battle_client/hud_layout.py` | Timeline band constants, `ViewerLayout.footer_timeline_rect`, footer re-tiling in `calculate_layout`, three pure coordinate helpers, updated help text |
| `client/src/battle_client/analysis.py` | `timeline_event_marks`, `nearest_recorded_tick` (both pure) |
| `client/src/battle_client/renderers/pygame_renderer.py` | Timeline palette constants, `_timeline_marks`/`_timeline_scrubbing` state, `_draw_timeline`, `_timeline_seek`, click/drag wiring in `_handle_click`/`_loop` |
| `client/tests/test_hud_layout.py` | 38 new tests (tiling, degenerate track, coordinate math, layout-regression guard, help budget) |
| `client/tests/test_analysis.py` | 10 new tests (mark derivation, tick snapping) |
| `client/tests/test_pygame_renderer.py` | 15 new tests; `_FakeDraw` now records rects so overlay geometry is assertable |
| `docs/screenshots/v3-match-timeline/*.png` | **new** — 4 real screenshots (§F) |
| `docs/V3_MATCH_TIMELINE.md` | **new** — this report |

No engine file was touched. No Ruleset, Agent API, scoring, scheduler, or
replay-schema file was touched.

---

## D. Behavior

A full-width 6px track sits at the top of the footer band, spanning the
replay's first to final **recorded** tick:

* **Elapsed fill** — the portion of the match already played, in a
  deliberately low-contrast chrome tone, so the playhead is what the eye
  follows.
* **Playhead** — a 2px bright caret at the current tick, overhanging the
  track vertically so it stays readable over a mark.
* **Event marks** — a 2×4px mark at each tick that recorded an event, in
  the affected entrant's own arena color (`AGENT_COLORS`), so a mark on the
  track and that entrant's card/territory share one identity. Usually there
  are none (§B).
* **Click to seek** — a click anywhere on the track jumps there.
* **Drag to scrub** — holding the button and moving walks the replay
  continuously.

Existing controls are unchanged; nothing was removed. The compact help line
now reads `Space play/pause · arrows step · drag timeline · ? controls`,
and the expanded (`?`) panel gained `drag timeline` while keeping every
shortcut it already listed — both verified to fit their real character
budget at the supported 640px minimum without ellipsis, by test and by
screenshot.

### Deliberate semantics

* **A scrub is a seek, and obeys every existing seek rule.** It pauses
  playback first, matching every navigation command in
  `PlaybackController` (whose class docstring gives the reason: a manual
  navigation while auto-playing is immediately overridden by the next
  `update()`). It also clears the core-capture callout and the write-flash/
  trail/recent-activity bookkeeping, because it is a non-linear tick jump —
  the renderer's existing "transient effects never survive a seek" rule
  applies unchanged and was not special-cased. Verified directly
  (`test_a_timeline_seek_clears_an_in_progress_capture_callout`).
* **A drag costs at most one seek per frame.** `_loop` resolves the drag
  from the mouse's *current* position once per frame rather than handling
  every queued `MOUSEMOTION`, so a fast drag cannot queue up an unbounded
  number of reconstructions. A seek resolving to the tick already on screen
  is skipped entirely, so holding the mouse still is free.
* **The requested tick is always snapped to a recorded one.**
  `ReplaySession.seek` rejects a tick falling in a sparse legacy replay's
  gap, and an arbitrary pixel position can land in one, so
  `nearest_recorded_tick` snaps first. For a canonical replay (which
  records every integer tick) this is an identity.
* **Seek cost is not a new performance class.** A backward seek resets to
  tick 0 and replays forward — measured at ~13ms across 200 ticks of a
  65536-cell arena, the same work `Home` and `Shift`+`Left` already do, and
  a fraction of what `compute_territory_history` already does once at load.

---

## E. Layout: the one load-bearing decision

The footer band grew, and the size it grew by was chosen by measurement,
not by taste.

`_top_height_cap` reserves `MIN_USEFUL_ARENA_HEIGHT` (256px) out of
whatever the footer leaves, so **every pixel the footer gains is taken from
the top band's cap, not from the arena** — the arena keeps its documented
floor by construction, at every supported size and entrant count (asserted
by `test_arena_keeps_its_useful_height_floor_with_the_timeline_present`).

That protects the arena but not the entrant cards. An initial 12px band
(a 10px track) silently re-flowed the densest twelve-entrant compact roster
at 640×480 from a 4-column grid of 150px cards into a 6-column grid of 97px
cards, which the existing suite caught. **8px is the largest growth at
which every existing entrant-count layout at the minimum viewport keeps the
exact card geometry it had before this band existed**, so the track is 6px
with a 2px gap. `test_minimum_viewport_card_geometry_is_unchanged_by_the_
timeline_band` now pins those grids so a future change cannot re-break them
silently.

A 6px strip is a poor mouse target, so `timeline_contains` widens the grab
area vertically past the drawn track into the footer padding no other
control claims — the track is easy to hit without being tall.

Like the territory graph before it, the timeline degrades to a degenerate
zero-size rect whenever the footer itself had to be clipped, rather than
overlapping the text it would otherwise sit above.

---

## F. Visual evidence

Captured through the real `PygameRenderer._redraw()` path (the method the
interactive viewer calls every frame) under `SDL_VIDEODRIVER=dummy`,
driving genuine replays produced by the actual engine CLI under
`bytefray-rules-2` — not hand-built fixtures. This mirrors the v3 Phase 1
and core-capture dummy-driver precedent. The driver script was disposable
and run from a scratch directory outside the repository.

| file | shows |
|---|---|
| `01-eventless-match-click-to-tick-300-of-400.png` | The common case: a real 3-entrant, 400-tick, arena-512 match with **no recorded events**. One click reached tick 300/400 — previously 30 `Shift`+arrow presses |
| `02-marks-mid-match.png` | A real match with events: playhead at tick 89/178, a red mark at tick 34 (Hunter's capture, matching its card's `CAPTURED @ T34 by B`), and a blue mark flush at the right edge for the tick-178 capture |
| `03-match-end-with-expanded-help.png` | The `?` panel open: both help lines render in full without ellipsis, and the timeline stays visible (it is a control, not a message line) |
| `04-minimum-viewport-640x480.png` | The supported minimum: track full width, playhead and mark legible, entrant cards and arena unaffected |

Click accuracy was verified numerically as well as visually: a click at 75%
of the track resolved to tick 300 of 400, and to tick 133 of 178, in the
two replays above.

---

## G. Tests / validation

**63 new focused tests** (38 + 10 + 15, several parametrized across window
sizes and entrant counts), split by the module boundary they belong to —
pure geometry in `test_hud_layout.py`, pure replay-fact derivation in
`test_analysis.py`, and drawing/interaction against real `ReplaySession`
fixtures in `test_pygame_renderer.py`. Coverage includes: footer tiling
with no overlap across sizes and entrant counts; the clipped-footer
degenerate case; coordinate round-tripping, clamping, non-zero first tick,
and single-tick replays; mark derivation per event kind, anonymous events,
duplicate collapsing, and the empty case; recorded-tick snapping including
gaps, ties, and clamping; click/drag seeking, pause-on-grab, off-track
rejection, drag-arming, callout clearing; and the minimum viewport.

One real defect was found by these tests and fixed: an event mark on the
**final** tick drew one pixel past the track's right border, because
`timeline_x_for_tick` returns a left edge and the mark's own width was not
accounted for. Both the mark and the playhead are now clamped by their own
width.

| check | result |
|---|---|
| `client/tests/test_hud_layout.py` | 92 passed |
| `client/tests/test_analysis.py` | 34 passed |
| `client/tests/test_pygame_renderer.py` | 137 passed |
| Full `client/tests` suite | 385 passed, 2 deselected (`gui`) — 200 before |
| Full `python -m pytest` (whole repo) | **2328 passed, 14 skipped, 2 deselected** — exactly the 2265-passing pre-change baseline plus this task's 63 new tests, with no regressions |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine client/src/battle_client` | Success, 96 source files |
| Real-render verification | 4 screenshots through the actual `_redraw()` path against genuine engine-produced replays (§F), inspected manually including magnified crops of the track's left and right ends |

Two pre-existing tests were updated, both because they pinned the old
footer height rather than because behavior regressed:
`test_configure_window_uses_display_margin_and_preferred_viewport` now
derives the expected window height from `FOOTER_HEIGHT` (its real subject,
the arena's own 960×480, is unchanged), and `test_hud_layout.py`'s
five-plus-entrant grid assertion is superseded by the stricter
minimum-viewport geometry guard described in §E.

---

## H. Compatibility impact

None. Only `client/` changed (§C). No `battle2.replay`/`battle2.result`
schema field was added or altered; no `docs/REPLAY_SCHEMA.md` update was
required. No Ruleset, scoring, scheduler, Agent API, evaluation, or
canonical-identity code was touched, and match determinism is untouched —
the Viewer only reads recorded facts (`KillDeathEvent`, `RuntimeEvent`,
`AgentEvent`, `ReplaySession.recorded_ticks`) that already existed and were
already read elsewhere in the same package. `ViewerLayout` gained one
field; `calculate_layout` is its only constructor.

The one externally observable change is that a default-launched viewer
window is 8px taller, because the footer band is 8px taller. The arena
inside it is unchanged.

---

## I. Deliberately left alone

- **Keyboard event-jump** (`N`/`P` to the next/previous recorded event) —
  rejected on the evidence in §B, not merely deferred.
- **Hover tooltips / a tick readout on the track** — would need per-frame
  hover state and a popup surface this renderer has no precedent for. The
  footer already prints `Tick N/total` beneath the track.
- **Distinguishing a core capture from an ordinary kill on the track** —
  possible, but that distinction lives in `AgentState.termination_reason`
  (tick state, not event data), and `battle_client.replay_status` is
  deliberately the single place that check lives. Duplicating it into the
  timeline would create a second source of truth for a Ruleset-semantic
  question, which this codebase explicitly avoids.
- **A separate marker for the winner / match end** — the header already
  states the terminal result, and the playhead already reaches the end.
- `EvaluationComparisonDialog`, the Agent Designer, sound, a general
  overlay framework, and anything belonging to Phase 4 (evaluation worker
  controls, large-run/resume infrastructure, history architecture,
  research-CLI disposition) were all out of scope and were not started.
