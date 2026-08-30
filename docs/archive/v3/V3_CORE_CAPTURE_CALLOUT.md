# Bytefray v3.0 — Core Capture Callout

Branch: `v3.0-development`. Status: complete, not merged, not tagged, not
published.

A small, restrained "fun feature": when a core-capture event occurs during
normal forward Replay Viewer playback, a temporary "CORE CAPTURED" callout
appears in the top HUD band, factually names the victim (and the captor,
when the replay attributes one), and disappears automatically. No Ruleset,
scoring, scheduler, Agent API, or replay-schema change of any kind — the
Viewer only observes replay facts that already exist.

---

## A. Initial state

Verified before any change:

- Branch `v3.0-development`, HEAD `b5cd7fa` ("initial commit phase 4"),
  working tree clean.
- `origin/v3.0-development` matched local HEAD exactly (no unpushed or
  behind state).
- `main` == `origin/main` (`1093393b...`).
- `python -m pytest` (full suite): 2265 passed, 14 skipped, 2 deselected
  (pre-existing `gui`-marked tests), before any change — a clean baseline.
- No unrelated local changes present.

---

## B. Existing replay-event findings

A core capture is **already fully representable** in the existing replay
model; no new schema field was needed:

- `battle_engine.python_runtime.apply_core_capture` (`bytefray-rules-2`
  family) kills an entrant once it owns zero of its own fixed 8-cell core
  region. It sets that entrant's `AgentState.termination_reason =
  "core_captured"` and appends a `KillDeathEvent`: `event_type="kill"`
  with `killer=<attacker id>` when the last capturing write is
  unambiguously attributable, or `event_type="death"` with `killer=None`
  otherwise.
- `client/src/battle_client/replay_status.py`'s existing `_core_status`
  already performs the identical check
  (`captured = (not alive) and death_reason == "core_captured"`) to drive
  the entrant status cards' permanent "CAPTURED @ T…" indicator — this
  feature reuses the exact same replay-evidence check for its own,
  separate, *transient* trigger, not a new source of truth.
- Victim and captor identity are both already available: `KillDeathEvent.
  victim`/`.killer` plus `AgentState.termination_reason`, all already
  serialized on the tick's own `TickSnapshot`.
- Playback/seek state: `ReplaySession` is a pure, deterministic
  tick-cursor (`step_forward`/`seek`/`restart`); `PygameRenderer` already
  has an established convention for *transient, presentation-only* state
  that must not survive a non-linear tick jump — `_advance_transient_
  effects`'s `is_linear_step` check, which clears write-flash/trail/
  recent-activity bookkeeping on any seek or restart and only extends it
  on a genuine `state.tick == last + 1` step. This is the convention the
  task asked to locate and integrate with (see §E for one deliberate,
  documented deviation from reusing it verbatim).
- HUD/header/footer: `battle_client.hud_layout.calculate_layout` already
  tiles the window into three non-overlapping bands (top HUD, arena,
  footer) — Phase 1's branding icon and every existing status/event line
  live in the top or footer band, never over the arena. The footer already
  has a generic "recent event" line, but it is a permanent, un-styled,
  single-line subtitle shown for *any* recorded event indefinitely (via
  `events_near_tick(..., window=1)`, which is "most recent event", not
  tick-distance-bounded) — not a distinct, temporary, capture-specific
  callout, so it was not repurposed.
- No existing generic "toast"/notification overlay mechanism exists in
  this renderer; none was invented — this feature is deliberately narrow
  (core capture only), per the task's explicit scope limit.

---

## C. Files changed

| File | Change |
|---|---|
| `client/src/battle_client/renderers/pygame_renderer.py` | New pure detection/formatting/fade functions, new `PygameRenderer` transient-callout state, `_advance_capture_callout`, `_draw_capture_callout`; `_draw_top_band` now returns the entrant statuses it computed (avoids a second lookup) |
| `client/tests/test_pygame_renderer.py` | 30 new focused tests (pure functions, queue/lifetime bookkeeping, end-to-end real-replay driving, rendered-content/geometry) |
| `docs/screenshots/v3-core-capture-callout/*.png` | **new** — 4 real screenshots (see §H) |
| `docs/V3_CORE_CAPTURE_CALLOUT.md` | **new** — this report |

No other file changed. No Ruleset, Agent API, scoring, scheduler, or
replay-schema file was touched.

---

## D. Callout behavior

When the current tick's recorded events include one or more core captures
(§B), the renderer shows a small bordered banner in the top HUD band:

```
┌────────────────────────────┐
│ CORE CAPTURED               │
│ Core Seeker eliminated Hunter│
└────────────────────────────┘
```

- **Attribution wording is factual only** (`format_core_capture_callout_
  lines`): `"{killer} eliminated {victim}"` when a killer is attributed,
  `"{victim} eliminated"` when it is not — never invented strategic prose.
  Names are the entrant's own `EntrantReplayStatus.name` (falling back to
  the bare agent id if somehow absent), matching how the rest of the HUD
  already identifies entrants.
- **Visual language**: reuses the existing HUD palette verbatim —
  `STATUS_CAPTURED_COLOR` (the same amber already used for a captured
  entrant's permanent card text) for the border/title, `TEXT_COLOR` for
  the attribution line, the same `hud_font` and `truncate_with_ellipsis`
  every other HUD line already uses. No new colors, fonts, or assets.
- **Placement**: horizontally centered, vertically centered inside
  `layout.top_band_height` — by construction (`box_h` is clamped to
  `top_band_height`, `box_y + box_h` never exceeds it), so the callout
  can never reach the arena band. It is drawn last, on top of the
  already-drawn entrant-card row, for its brief lifetime, rather than
  reserving new permanent layout space — no `hud_layout.py` geometry
  changed.
- **A subtle fade, not an animation clock**: `capture_callout_alpha` is a
  pure, tick-denominated linear envelope (the same decay shape
  `activity_intensity` already uses elsewhere in this module) — fades in
  over the first 8 ticks, holds at full opacity, fades out over the last 8
  ticks. It needs no separate per-frame timer; alpha is recomputed fresh
  every frame from `current_tick - capture_tick` alone, so it is exact
  under any playback speed and freezes correctly on pause. The panel is
  fully opaque at its hold phase (not permanently translucent) — an
  interim 84%-opacity version visibly let the entrant-card text
  underneath show through between its own glyphs; full opacity at the
  envelope's peak was required for clean readability (see the real
  screenshots in §H, and `_draw_capture_callout`'s own code comment).
- **Lifetime**: 40 ticks (`CAPTURE_CALLOUT_DURATION_TICKS`), tick-
  denominated rather than frame- or wall-clock-based — about 2 seconds of
  match time at the CLI's 1x default (`DEFAULT_TICK_INTERVAL = 0.05s/
  tick`). Because visibility is a pure function of `current_tick` versus
  the callout's own expiry tick, pausing freezes it exactly in place for
  free, and a speed change needs no special-casing.
- **No new dependencies, no sound, no settings/preferences infrastructure,
  no particle effects, no screen shake.**

---

## E. Playback / seek semantics

This is the load-bearing part of the feature, and is deliberately
documented in code (`_advance_capture_callout`'s own docstring) as well as
here.

**Trigger condition — exact `+1` forward steps only.** A new capture is
only ever detected when `state.tick == self._last_rendered_tick + 1`
(read from `_advance_transient_effects`'s own tracked tick, before it is
overwritten) — the same boundary this renderer's existing `is_linear_step`
check already draws for flash/trail/recent-activity bookkeeping. This
covers both auto-play (`PlaybackController.update()`'s internal
`step_forward()` calls) and a single manual step (Right arrow), and
excludes every seek-shaped operation (`seek_relative`, `restart`,
`jump_to_end`, an event-panel click-to-seek) by construction, since none
of those ever produces an exact `+1` delta except by rare coincidence.

**Seeking never replays a transient notification.** Any tick delta other
than exactly `+1` (backward, or a forward jump of more than one tick)
clears both the active callout and its pending queue — verified directly
(`test_seek_clears_pending_and_active_callout`,
`test_forward_seek_past_a_capture_tick_does_not_trigger_its_callout`).
Seeking straight onto a capture tick, or repeatedly crossing it while
scrubbing, never shows the callout; only genuinely walking forward through
it, one tick at a time, does.

**Restart permits it again, naturally.** `restart()` (tick jumps to the
first tick) is itself a non-linear jump by the same rule, so it clears any
in-progress callout; subsequent forward playback through the same capture
tick re-triggers it exactly as the first time
(`test_restart_clears_an_in_progress_callout_and_permits_it_again`).

**Pause freezes it — a deliberate, necessary deviation from reusing
`is_linear_step` verbatim.** `_advance_transient_effects` (and therefore
this feature's own `_advance_capture_callout`) is called once per
*rendered frame*, up to 60fps, not once per tick — `PlaybackController.
update()` is a documented no-op while paused, so a paused replay calls
this method repeatedly with the *same* `state.tick`. The existing
`is_linear_step` check (`state.tick == last + 1`) treats that "delta 0"
case identically to an actual seek (both fail the `+1` test) — harmless
for flash/trail effects, whose own lifetimes are sub-second and already
re-derived from scratch every linear step, but would have silently wiped
a multi-second callout on the very next paused frame if reused as-is.
`_advance_capture_callout` therefore computes its own three-way
comparison — delta `0` is a deliberate no-op (leave the callout exactly
as it is), delta `1` advances, anything else clears — verified directly
(`test_pause_freezes_active_callout_across_repeated_frames_at_the_same_
tick`, simulating five repeated same-tick frames).

**One documented, accepted limitation.** `PlaybackController.update()` can
call `session.step_forward()` more than once inside a single frame (e.g.
at high playback speed, or a slow frame), producing a `state.tick` delta
greater than 1 even though every intermediate tick was individually,
genuinely stepped through. This renderer's *existing* flash/trail/
recent-activity effects already have the identical latent gap (a change
on a "skipped" intermediate tick is never flashed). Rather than invent new
forward-batch-vs-seek disambiguation machinery not proven anywhere else in
this codebase (which the task's own scope-discipline section warns
against), this feature accepts the same boundary: a capture on a tick
skipped within one frame's multi-tick auto-play batch does not get its own
callout. This is judged the lesser risk, since the alternative (treating
any multi-tick forward delta as "still continuous playback, scan the
range") would make an ordinary Shift+Right seek over a capture tick
incorrectly show its callout — a direct violation of the seek requirement
above, which is explicitly load-bearing. In practice this only matters at
speeds where more than one tick can elapse within one 60fps frame (roughly
4x/8x, given the default 0.05s tick interval).

---

## F. Multiple-capture behavior

`battle_engine.python_runtime.apply_core_capture` checks *every* living
entrant each tick before scoring, so more than one core capture on the
same tick is possible (e.g. a 3+-entrant match). This is handled two ways,
without building a general notification framework:

- **Same tick → one bundled callout.** `core_captures_at_tick` returns
  every capture recorded at that exact tick as a single tuple; they are
  queued and shown together as one box with one attribution line per
  victim (`test_multiple_captures_on_the_same_tick_bundle_into_one_
  callout`), capped at `CAPTURE_CALLOUT_MAX_LINES` (4) total lines —
  beyond that, the overflow collapses into one `"+N more"` summary line
  rather than growing the box unboundedly.
- **Different ticks → a small FIFO queue, never dropped.** A capture
  encountered while another callout is still active is appended to a
  queue and shown next, once the active one's own duration elapses —
  verified with two captures 4 ticks apart
  (`test_multiple_captures_close_together_are_queued_not_dropped`): the
  second capture is confirmed still queued (not shown, not discarded)
  while the first is active, then confirmed promoted to active once the
  first expires.

---

## G. Minimum-size behavior

Verified at the supported 640×480 minimum (both by test and by a real
screenshot, §H): `top_band_height` at that size is always at least ~150px
for up to several entrants (well above the callout's own ~48–64px
content height), so the callout always has room to draw, by construction
never extends past the top band, and truncates any line too long for its
own pixel budget via the same `truncate_with_ellipsis` every other HUD
line uses (`test_capture_callout_truncates_unusually_long_agent_names`,
`test_capture_callout_fits_within_the_minimum_supported_viewport`).

One accepted cosmetic trade-off at the narrowest supported width: with
3 entrants at 640×480, the responsive HUD lays entrant cards out in a
2-column grid, and the callout's own (deliberately width-capped, ≤360px)
box does not always fully span the card column it draws over — a sliver
of an adjacent card's text can remain visible beside the box (see
`05-minimum-viewport-640x480-active-callout.png`). The callout text itself
stays fully legible in every case; only a fragment of already-transient,
non-critical card text beside it is partially exposed for the callout's
own ~2-second lifetime. No arena content is ever affected.

---

## H. Visual evidence

Generated through the actual `PygameRenderer._redraw()` path (the same
method the interactive viewer calls every frame) under
`SDL_VIDEODRIVER=dummy`/`SDL_AUDIODRIVER=dummy`, driving a **real** replay
produced by `NativeMatchService` under `bytefray-rules-2` (three Python
entrants: `Hunter` — idle, `Core Seeker` — a scripted writer that captures
Hunter's core, `Wanderer` — idle bystander that keeps the match alive well
past the capture) — not a hand-built fixture, not a stub. This mirrors the
v3 Phase 1 dummy-driver precedent
(`docs/V3_PHASE1_PRESENTATION_BASELINE.md` §1). The driver script was
disposable, run from a scratch directory outside the repository.

| file | shows |
|---|---|
| `01-before-capture-tick0.png` | Ordinary playback immediately before the event (tick 0, all three entrants alive, "No recent events") |
| `02-active-callout.png` | The active callout mid-hold: **"CORE CAPTURED" / "Core Seeker eliminated Hunter"**, fully opaque, over the entrant-card row, arena untouched |
| `04-after-expiration.png` | Tick 46 (well past the 40-tick duration from the tick-1 capture) — callout gone, normal HUD resumed, entrant cards show Hunter's permanent "CAPTURED @ T1 by B" status unaffected |
| `05-minimum-viewport-640x480-active-callout.png` | The same active callout at the supported 640×480 minimum — legible, still fully inside the top band |

---

## I. Tests / validation

**New focused tests** (`client/tests/test_pygame_renderer.py`, 30 total),
covering every scenario the task named:

- Known captor + victim, and victim with an unavailable captor — both via
  pure-function unit tests *and* an end-to-end real `NativeMatchService`-
  style replay fixture already established in this file
  (`_v2_two_entrant_session`).
- Callout lifetime and expiration (fade-envelope shape, exact expiry
  tick).
- Pause behavior (repeated same-tick frames leave the callout untouched).
- Seek behavior (backward seek and forward seek both clear; seeking never
  retriggers).
- Replay restart (clears, then permits the callout again naturally).
- Multiple captures: same-tick bundling, and close-together queuing with
  none dropped.
- Long agent names (truncated, box never breaks).
- Minimum supported viewport (640×480, renders without crashing, content
  present).
- No callout when no capture occurs (driven through a real replay with
  genuine, non-capture VM kill/death events).

**Validation run:**

| check | result |
|---|---|
| `client/tests/test_pygame_renderer.py` | 122 passed |
| Full `client/tests` suite | 322 passed, 2 deselected (`gui`) |
| Full `python -m pytest` (whole repo) | 2265 passed, 14 skipped, 2 deselected — unchanged from the pre-change baseline |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success, 84 source files |
| `mypy client/src/battle_client` | Success, 12 source files |
| Real-render verification | 4 screenshots captured through the actual `_redraw()` path against a genuine replay (§H); re-inspected after an opacity fix found during that same verification (see §D) |

---

## J. Compatibility impact

None. Confirmed by the diff scope itself (§C): only
`client/src/battle_client/renderers/pygame_renderer.py` and its own test
file changed. No `battle2.replay`/`battle2.result` schema field was added
or altered; no `docs/REPLAY_SCHEMA.md` update was required. No Ruleset,
scoring, scheduler, Agent API, or canonical-identity code was touched. The
Viewer only reads replay facts (`KillDeathEvent`, `AgentState.
termination_reason`) that already existed and were already read elsewhere
in this same module (`replay_status.py`). `_draw_top_band`'s signature
gained a return value (previously `None`); every existing call site
already ignored its return value, so this is source- and behavior-
compatible.

---

## K. Commit

Committed as a single commit once validation passed and the working tree
contained only this task's changes (source, tests, screenshots, this
report) — see the repository log for the exact commit.

---

## L. Deferred ideas

Not pursued, consistent with the task's scope discipline:

- **High-speed multi-tick-per-frame batching** (§E) — a capture on a tick
  skipped within one frame's auto-play batch at ~4x/8x speed does not get
  its own callout. This matches an identical, pre-existing boundary
  already accepted by this renderer's write-flash/recent-activity
  overlays, for the same reason (no proven forward-batch-vs-seek
  disambiguation exists in this codebase to build on). Worth revisiting
  only if it proves disruptive in practice.
- **Full-width minimum-viewport card coverage** (§G) — the callout box
  could be widened to always fully span whatever card column(s) it
  overlaps at the narrowest supported width, eliminating the small
  partial-card-text sliver noted in §G. Deferred as a minor cosmetic
  polish item, not a functional gap.
- A general toast/notification framework, sound, match-intro/victory
  animation, or new HUD mode were all explicitly out of scope and were not
  started.
