# Bytefray v2.0.0-beta1 Phase 4 — Replay Viewer HUD Separation

This document records Beta1 Phase 4: redesigning the interactive Pygame
Replay Viewer's presentation so entrant status, Ruleset-v2 core integrity,
capture state, score/territory, and controls are visually separated from
the battlefield, consuming the Phase-3 replay status model
(`battle_client.replay_status.get_entrant_statuses`) rather than deriving
Ruleset semantics in the renderer. Phase 1 froze gameplay semantics; Phase 2
made the permanent v2 identity selectable through product CLI surfaces;
Phase 3 made status derivable from replay data. None of those are touched
here — this phase changes only `battle_client`'s presentation layer, plus
tests and documentation. See `docs/V2_0_BETA1_PLAN.md` for the overall phase
sequence.

## 1. Starting repository state

Verified before any change:

- branch `v2.0-beta1-development`, HEAD `4e29fb3fcc5fca6a024cd4359c07046d2cce7150`
  (Phase 3's final commit — `docs(v2.0-beta1): document replay status
  model`);
- `main` at `5593d287f95a24996bb3b105befbc625a00795db`, unchanged;
- `v2.0-development` at `ad67a0fe0778fdc40c804618e8ec5ea8ea9cf7d3`, unchanged;
- `origin/v2.0-development` at `151866c6d862fec4facb78596204861b26889b61`,
  unrelated origin history, untouched;
- working tree clean (`git status --porcelain` empty).

## 2. Verified baseline

Re-measured independently on the untouched Phase-3 tree via JUnit-XML
summary:

| Check | Result |
|---|---|
| `python -m pytest` (full) | **1687 passed, 6 skipped, 2 deselected, 0 failed** (203.8s) |

This exactly matches the committed Phase-3 baseline recorded in the
governing prompt (1687/6/2/0) — no drift between Phase 3's commit and Phase
4's start.

## 3. Pre-change Replay Viewer layout (audit)

Audited directly from `client/src/battle_client/renderers/pygame_renderer.py`
before any Phase-4 edit.

### Window sizing

- `PygameRenderer.__init__`: `scale` (integer cell size in pixels), no
  concept of reserved UI space — the window **is** the arena, pixel-for-
  pixel (`window_size = (grid_cols * scale, grid_rows * scale)`).
- `_configure_window`/`choose_initial_window_scale`/`integer_scale_to_fit`:
  choose the largest integer cell scale that fits the arena grid into a
  `PREFERRED_WINDOW_SIZE = (960, 600)` viewport, capped to 90% of the real
  display (`DISPLAY_USAGE_FRACTION`). The chosen scale directly determines
  the window's total size — there was no separate "UI chrome" allowance.
- `_resize_window`/`_fit_to_display`/`_rescale`/the `VIDEORESIZE` handler
  all follow the same pattern: window size is always exactly
  `grid_cols * scale` by `grid_rows * scale`.

### Arena rectangle

- The arena occupies `(0, 0)` to `(window_w, window_h)` — the entire
  window, always. `_redraw` fills `grid_surf` (a `grid_cols` x `grid_rows`
  logical surface), then `pg.transform.scale`s it to `self.screen.get_size()`
  and blits at `(0, 0)`.

### Overlays drawn on/around the arena (pre-change)

All of the following are drawn **directly on top of** the full-window arena
image, several as semi-transparent (`SRCALPHA`) panels overlaid at fixed
screen corners:

1. **HUD text block** (`_draw_hud`/`build_hud_lines`) — a single
   semi-transparent panel anchored at `(0, 0)`, height proportional to line
   count, spanning the *full window width*, containing (in order):
   - one status line (`"Bytefray Replay -- runtime: {kind}"`, tick/total,
     play state, speed);
   - one line per entrant (`_agent_display_line`): alive/dead, score,
     territory, plus low-level runtime diagnostics (`ctrl=`/`pc=`,
     `actions=`/`cpu=`, `writes=`, `region=`);
   - an optional "Selected cell:" inspector panel (address/byte/owner/
     agent for a clicked cell);
   - an optional "Recent events:" section (up to 5 nearby events, each
     clickable to seek);
   - an optional "Winner: X Termination: Y" line once the replay's
     terminal record is known;
   - a trailing `HELP_TEXT` line listing every keyboard shortcut,
     rendered unconditionally on every frame.

   This panel directly covers the top-left portion of the arena for as
   long as it is tall — which grows with entrant count and event/inspector
   content, so on a 3-entrant replay with recent events *and* a selection
   it could obscure a substantial fraction of the visible battlefield.

2. **Territory-history trend graph** (`_draw_territory_graph`) — a second,
   independent semi-transparent panel, anchored at the *bottom-right*
   corner of the arena, fixed at 190x70px, showing one polyline per
   entrant's owned-cell percentage over a trailing tick window.

3. **Selection highlight** (`_draw_selection_highlight`) — a colored
   rectangle outline on the clicked arena cell. This one *is* spatially
   meaningful (it marks a specific cell) and correctly stays on the arena.

4. **Agent markers, trails, ownership tint, recent-activity heatmap,
   write-flash** — all correctly spatial (tied to specific arena
   addresses/cells) and correctly arena-only already.

### Status text / score text

Both were already fields inside the single HUD text block above
(`_agent_display_line`'s `score=`/`territory=` tokens) — not visually
distinct from the low-level runtime diagnostics on the same line, and not
distinct from any other HUD content; everything was one flat list of
strings in one panel.

### Controls/help presentation

`HELP_TEXT`, one long single-line string of every keyboard shortcut,
unconditionally appended as the last line of the same HUD panel — always
present, always full length, never contextual, permanently overlapping the
arena's top-left area (mixed in with entrant status and events).

### Event/status messages

The "Recent events:" section inside the HUD panel — up to `events_near_tick`'s
default window of 5 events at/before the current tick, each independently
clickable (`resolve_event_click`) to seek. Also overlapping the arena.

### Resize behavior (pre-change)

`VIDEORESIZE` recomputes the integer scale to fit the new size and calls
`_resize_window`, which sets an exact `grid_cols*scale` x `grid_rows*scale`
window — always exactly the arena, no separate UI region to preserve or
grow.

### Two-entrant representation

`_agent_display_line` is called once per `sorted(state.agents)` id inside
`build_hud_lines` — genuinely N-entrant generic in its *loop structure* (no
hardcoded "left"/"right" or "A"/"B" positional slots). However:

- entrant lines stack **vertically**, one full-width line per entrant, so
  the HUD panel's height (and thus how much of the arena it obscures) grows
  linearly with entrant count;
- `AGENT_COLORS`/`OWNERSHIP_TINT`/`PROCESS_FLASH` are keyed dictionaries
  with explicit `"A"`/`"B"`/`"C"`/`"D"` entries and a shared
  `DEFAULT_*`/`DEFAULT_AGENT_COLOR` fallback for any other id — already
  functionally N-entrant safe (any 5th+ entrant gets the default color,
  not a crash), so this was not a blocking assumption, just a a small
  cosmetic ceiling above 4 uniquely-colored entrants.
- **No entrant-count-aware layout existed at all** — there was no per-
  entrant "slot"/"card"/"region" concept, spatial or otherwise, to break
  for 3 entrants; the flat vertical text list simply grows.

### What becomes awkward for three entrants

- The vertically-stacked HUD panel gets taller (three entrant lines
  instead of two, each already long with diagnostics), covering
  proportionally more of the arena's top edge — directly contrary to the
  "arena remains visually primary" requirement.
- Nothing was laid out *side by side*, so there was no comparative "at a
  glance" view across entrants — a viewer had to read down a growing list.

## 4. Information classification (per the governing task's Phase 4A audit)

### Spatially meaningful (stays on/around the battlefield)

- arena cell ownership tint;
- recent-activity heatmap;
- write-flash highlights;
- agent trails and VM position markers;
- selected-cell highlight outline.

### Non-spatial match status (moves to HUD/status bands)

- entrant name, alive/dead, core integrity, capture status/attribution,
  score, territory, kills — all now sourced from
  `battle_client.replay_status.get_entrant_statuses` (Phase 3) rather than
  `_agent_display_line`'s own ad hoc formatting;
- Ruleset identity, runtime kind, arena size, entrant count (match header);
- winner/termination once known;
- current tick / playback state / speed;
- the low-level runtime diagnostics (`pc`/`cpu_used`/`mem_writes`/`region`)
  previously mixed into the same line as score/territory — deliberately
  **not** carried into the new default entrant card (see §9 of the Phase-4
  design notes below); not part of the Phase-3 status model's field list
  and not part of the governing task's Phase 4D content list. This is a
  restrained scoping decision, not a silent removal: the information was
  low-level VM/controller debugging detail, not match status:
  "what is the state of the battle" versus "what is one particular
  runtime's internal bookkeeping."
- the territory-history trend graph (non-spatial — a trend over time, not
  tied to any specific cell).

### Controls/help

- keyboard shortcuts (`HELP_TEXT`);
- event/status message (was "Recent events:", now a single compact
  most-recent-event line, still click-to-seek).

## 5. Disposition

This audit directly motivated the Phase 4B design: a fixed-height top HUD
band (match header + entrant status cards), an unobstructed arena band, and
a fixed-height footer band (playback/tick, one compact status/event
message, controls, and the relocated territory-history graph) — see
`docs/V2_0_BETA1_PLAN.md` §7.

## 6. HUD layout design

New module `client/src/battle_client/hud_layout.py` — pure geometry and
text-formatting functions, no Pygame import anywhere, directly testable
without a window (governing task's Phase 4R "separate geometry / text
construction / drawing").

### Band structure

```text
+------------------------------------------------------+  y=0
| Bytefray Replay — Ruleset X | runtime Y | arena Z |...|  header line 1
| Winner: A   Termination: last_agent_standing (or "")  |  header line 2
|                                                        |
| CLAIMER          HUNTER            CORE_DEFENDER      |  one card per
| Alive | Core 8/8 Alive             CAPTURED @ T84 ... |  entrant, equal-
| Score.. Territory.. Kills..        Core 0/8 by X       |  ish width row
+------------------------------------------------------+  y=TOP_BAND_HEIGHT
|                                                        |
|                        ARENA                          |  y grows/shrinks
|                                                        |  with window size
+------------------------------------------------------+  y=window_h-FOOTER_HEIGHT
| Tick 84/200   [PAUSED]   speed 1x                      |  footer line 1
| T084 kill: core_defender by core_tracker    [graph]    |  footer line 2 (+
| Space play/pause  Right/Left step  ...                 |  footer line 3   territory
+------------------------------------------------------+  y=window_h        graph panel)
```

`calculate_layout(window_size, entrant_count) -> ViewerLayout` returns six
rects (`header_rect`, `entrant_card_rects` — always exactly
`entrant_count`, tiled left-to-right with no two-slot assumption,
`arena_rect`, `footer_text_rect`, `footer_graph_rect`), all mutually
non-overlapping by construction:

- `TOP_BAND_HEIGHT` and `FOOTER_HEIGHT` are **fixed pixel constants**
  (`100`/`60` respectively — 2 header lines + a 3-line card row, and 3
  footer lines, each with fixed line heights and padding), independent of
  window size or arena scale.
- `arena_rect`'s height is always exactly `window_h - TOP_BAND_HEIGHT -
  FOOTER_HEIGHT` (clamped at `0`, never negative) — the single invariant
  that makes "no overlap" true by construction rather than by a runtime
  check.
- `entrant_card_rects` divide the window width into `entrant_count`
  columns, the last absorbing any integer-division remainder so the row
  always tiles exactly to the window's own width with no gap or overlap.
- `footer_graph_rect` is a fixed `150`-wide panel on the footer's right
  edge, present only when the window is at least `FOOTER_GRAPH_MIN_WINDOW_
  WIDTH` (`460`) wide — a degenerate zero-size rect otherwise, so a narrow
  window gives its full footer width back to text rather than compressing
  both.

### Arena rectangle strategy

The renderer's existing integer-cell-scale machinery
(`integer_scale_to_fit`/`choose_initial_window_scale`, both left
byte-for-byte unchanged — see §8) now fits the arena grid into the
**display bounds minus the fixed band heights**
(`PygameRenderer._arena_display_bounds`) instead of the whole display. The
window's total size is then `grid_cols*scale` wide by `TOP_BAND_HEIGHT +
grid_rows*scale + FOOTER_HEIGHT` tall
(`PygameRenderer._window_size_for_scale`) — the arena's own pixel
footprint is unchanged from Phase 3 (still `PREFERRED_WINDOW_SIZE =
(960, 600)` at default scale-fit, still resize/`[`/`]`/`0`-fit-capable at
the same integer-scale granularity); only the window's *total* height
grows to fit the two new fixed-height bands around it.

### Footer/control strip strategy

Three fixed lines: tick/playback/speed, one adaptive status/event message,
and the keyboard-shortcut controls string. The message line shows (in
priority order) the selected-cell inspector when a cell is selected, else
the single most recent recorded event at/before the current tick, else
"No recent events" — always exactly one line, never a growing list, per
the governing task's explicit "avoid a paragraph, prefer a compact form"
guidance (Phase 4K). Clicking that line still seeks to the shown event's
tick when it is showing one (`PygameRenderer._event_panel_*`, the same
click-resolution mechanism as before, now scoped to a single tick instead
of up to five).

### Default/minimum window-size decision

`PREFERRED_WINDOW_SIZE` (the arena's own target viewport) is **unchanged**
at `(960, 600)` — the default arena area is therefore identical before and
after this phase (see §14). The default *total* window grows by exactly
`TOP_BAND_HEIGHT + FOOTER_HEIGHT` (`160px`) to make room for the two new
bands — e.g. a `128`-cell arena's default window grows from `960x480` to
`960x640` (verified in `test_configure_window_uses_display_margin_and_
preferred_viewport`). This is the "modestly increase the default initial
window size" option the governing task named as acceptable when additional
vertical space is needed (Phase 4I) — justified because the arena itself
does not shrink, normal desktop/laptop displays have ample headroom for an
extra `160px`, and resize/fit-to-display/manual-rescale behavior is
otherwise unchanged (see §8).

No separate hard-coded "minimum window size" constant was introduced:
`arena_rect`'s height is clamped at `0` (never negative) rather than
enforced positive, so an extremely short window degrades to a crushed-but-
present arena rather than crashing — the natural floor is the existing
`integer_scale_to_fit`'s own `scale >= 1` guarantee, unchanged from before
this phase (verified in `test_minimum_window_size_never_produces_negative_
arena`).

## 7. Long-name / narrow-window handling

Deterministic truncation only (governing task's explicit preference over
dynamic font shrinking — Phase 4H):

- `hud_layout.truncate_with_ellipsis(text, max_chars)` — the shared
  primitive every truncating call site uses.
- Entrant card lines (`format_entrant_card_lines`) accept an optional
  `max_chars` computed from the card's actual pixel width
  (`PygameRenderer._draw_entrant_card`, `HUD_CHAR_WIDTH_PX`-per-glyph
  estimate). A long name truncates with an ellipsis; the status line drops
  its killer-attribution clause first (keeping life-state and core
  integrity, the two highest-priority facts per Phase 4N), falling back to
  ellipsis truncation only if even the core-inclusive form doesn't fit; the
  stats line drops kills, then the territory percentage, then territory
  itself, in that order — score is the last thing ever shortened.
- The header lines and all three footer lines are truncated the same way
  to their own rects' widths (`header_rect`/`footer_text_rect`) — added
  after a real headless screenshot smoke (see §22) caught the un-truncated
  controls string visually running underneath the territory graph panel on
  a moderately-sized window; `test_footer_controls_line_truncates_to_its_
  column_width` regression-guards this.

## 8. Phase-3 status-model integration / renderer files changed

- `client/src/battle_client/replay_status.py` (extended): one new
  function, `resolve_match_ruleset_label(header) -> str` — a thin
  presentation wrapper around the existing `resolve_replay_ruleset`, kept
  in this domain module (not the renderer) so Ruleset-identity resolution
  stays out of `pygame_renderer.py` entirely, consistent with `_core_
  status`'s own existing use of the same underlying function. No change to
  `get_entrant_statuses`/`CoreStatus`/`EntrantReplayStatus` — Phase 3's
  status model is consumed exactly as designed, not modified.
- `client/src/battle_client/hud_layout.py` (new): geometry (`calculate_
  layout`) and text formatting (`format_entrant_card_lines`, `format_
  entrant_status_line`, `format_entrant_stats_line`, `format_match_header_
  lines`, `format_playback_line`, `truncate_with_ellipsis`) — see §6-7.
- `client/src/battle_client/renderers/pygame_renderer.py` (extended):
  - removed `_agent_display_line`, `build_hud_lines`, `_event_section_
    start` (the old single-panel flat-text HUD, replaced by band drawing);
  - added `_arena_rect`, `_window_size_for_scale`, `_arena_display_
    bounds`, `_draw_top_band`, `_draw_entrant_card`, `_draw_footer` (renamed
    from `_draw_hud`), `_draw_footer_graph` (renamed/relocated from
    `_draw_territory_graph`);
  - `_configure_window`/`_resize_window`/`_fit_to_display`/`_rescale`/the
    `VIDEORESIZE` handler updated to size the arena within the band-reduced
    bounds (§6) rather than the whole window;
  - `_screen_xy`/`_draw_agent_marker`/`_draw_selection_highlight`/`_draw_
    polyline`/`_handle_click` updated to operate relative to `_arena_rect()`
    (the arena band's own rect) instead of the whole screen — with a
    documented fallback to "whole screen is the arena" when `self._layout`
    is `None` (a unit test that pokes renderer internals directly without
    calling `run()`), preserving every pre-Phase-4 pure-geometry unit
    test's exact original meaning unmodified.

### Proof no gameplay logic is duplicated

`pygame_renderer.py` and `hud_layout.py` both import only
`battle_client.replay_status`/`battle_client.analysis`/`battle_client.
session` for any Ruleset-specific fact (core integrity, capture,
attribution, alive/dead, Ruleset identity) — grep confirms neither module
imports `battle_engine.python_runtime`'s core-mechanics symbols
(`CORE_SIZE`, `core_addresses`, `has_vulnerable_core`,
`VULNERABLE_CORE_RULESET_IDS`, `seed_core_ownership`, `apply_core_
capture`) directly; those stay exclusively inside `replay_status.py`
(Phase 3) and `battle_engine.python_runtime` (the engine itself). The only
per-entrant fields `_draw_entrant_card`/`hud_layout`'s formatters read are
already-derived `EntrantReplayStatus`/`CoreStatus` attributes — never a raw
`TickSnapshot`/`MemoryDiff`/`AgentState` field.

### Layout helper / formatting helper architecture

Matches the governing task's Phase 4R example almost exactly:

```text
calculate_layout(window_size, entrant_count) -> ViewerLayout     (geometry)
format_entrant_card_lines(status, max_chars) -> (str, str, str)  (text)
format_match_header_lines(...) -> (str, str)                     (text)
format_playback_line(...) -> str                                 (text)
PygameRenderer._draw_top_band / _draw_entrant_card / _draw_footer /
    _draw_footer_graph                                            (drawing)
```

No Ruleset-specific branching exists in any drawing method — `_draw_
entrant_card` only ever asks "is `status.core` `None`?" (a presentation
question already answered by Phase 3) and "is `status.core.captured`?" to
choose a color, never a Ruleset-identity string comparison.

## 9. v1 presentation

`status.core is None` for a v1 replay (Phase 3's own guarantee), so
`format_entrant_status_line` renders exactly `"Alive"` / `"Dead[ @ Ttick][
by killer]"` — no `"Core"` token anywhere, and certainly no fabricated
`"Core N/A"`. Verified directly: `test_v1_alive_entrant_has_no_core_field`,
`test_v1_dead_entrant_has_no_core_field`,
`test_top_band_renders_v1_entrants_with_no_core_field` (through the real
renderer method, not just the pure formatter), plus a real headless
screenshot (§22) visually confirming a clean two-card v1 layout with no
core row. All pre-existing v1/VM replay tests (`test_replay_session.py`,
the VM-runtime cases in `test_pygame_renderer.py`) pass unmodified.

## 10. v2 presentation

- **Healthy**: `"Alive | Core 8/8"` (`test_v2_healthy_core_shows_full_
  integrity`, `test_top_band_renders_v2_healthy_and_damaged_core`).
- **Damaged**: `"Alive | Core 5/8"` (same tests, second assertion).
- **Captured, attributed**: `"CAPTURED @ T84 by core_tracker | Core 0/8"`
  (`test_v2_captured_with_attribution_shows_killer`, `test_top_band_
  renders_v2_capture_with_attribution`).
- **Captured, unattributed**: `"CAPTURED @ T84 | Core 0/8"` — no fake
  killer (`test_v2_captured_unattributed_shows_no_fake_killer`, `test_top_
  band_unattributed_capture_shows_no_fake_killer`).
- **Forfeit under a core-having Ruleset** (dead, not captured):
  `"Dead @ T9 | Core 6/8"` — worded distinctly from a capture
  (`test_v2_forfeit_death_is_not_worded_as_capture`).
- **Alive/dead**: color-coded (green/red/amber for captured) *and* always
  textual (`"Alive"`/`"Dead"`/`"CAPTURED"`) — color is never the only
  signal (Phase 4M).
- **Score/territory/kills**: their own line, below the life/core line —
  never implying "highest score = winning" independent of life state
  (Phase 4N; `format_entrant_stats_line` never reads `alive`/`core` at
  all, so the two are structurally decoupled, matching Phase 3's own
  design intent recorded in `docs/V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md`
  §15).
- **Ruleset identification**: the header's first line always names the
  resolved Ruleset identity (`resolve_match_ruleset_label`) — a v1 replay
  and a v2 replay are visibly distinguishable without opening raw JSON
  (Phase 4O), confirmed in the real screenshots (§22).

## 11. Multi-entrant (two and three)

`calculate_layout`/`format_entrant_card_lines`/`PygameRenderer._draw_top_
band` have no positional two-slot assumption anywhere — `entrant_card_
rects` is sized from `entrant_count` alone and iterated in the replay's own
recorded order (matching `get_entrant_statuses`'s own N-entrant-generic
order, per Phase 3 §16). Verified:

- **Two entrants**: `test_two_entrant_bands_do_not_overlap`, `test_two_
  entrant_arena_within_window`, plus the real v1 screenshot (§22).
- **Three entrants**: `test_three_entrant_bands_do_not_overlap`, `test_
  three_entrant_cards_have_valid_positive_size`, `test_three_entrant_
  cards_tile_left_to_right_in_order`, `test_top_band_renders_three_
  entrants_all_represented` (all three names and all three `Core 8/8`
  values present through the real renderer method), plus three real
  screenshots at decreasing window widths (§22) showing a readable,
  non-overlapping three-card row at a normal size and graceful, still-
  non-overlapping degradation (dropped territory percentage, dropped
  territory, ellipsis-truncated capture line) down to a `420px`-wide
  window.
- **General N**: `test_entrant_card_rects_tile_exactly_to_window_width`
  parametrized over `1..5` entrants; `test_entrant_count_below_one_is_
  clamped_to_one_card` for the degenerate `0` case.
- **No overlap, generally**: every geometry test above uses a shared
  `_overlaps` helper checked against every pairwise combination of bands/
  cards — not just the two- and three-entrant cases individually asserted.

## 12. Battlefield decluttering

Removed from the arena band entirely (relocated, not deleted — see §4):

- the single flat HUD text panel (entrant lines, selected-cell inspector,
  recent-events list, winner/termination, keyboard help) — now the top HUD
  band and footer band;
- the territory-history trend graph — now the footer's `footer_graph_rect`
  panel (`_draw_footer_graph`), since it is a trend over time, not tied to
  any specific arena cell.

Retained on the arena band (all spatially meaningful — tied to specific
arena cells/positions):

- ownership tint, recent-activity heatmap, write-flash highlights;
- agent trails and VM position markers;
- the selected-cell highlight outline (`_draw_selection_highlight`) — the
  clicked cell's own on-arena marker; its *textual* readout (address/byte/
  owner/agent) moved to the footer's status/event message slot (§6), since
  that is non-spatial information *about* a spatial target, not the target
  marker itself.

## 13. Before/after usable arena size

Identical at the default window size — `PREFERRED_WINDOW_SIZE` (the arena's
own target viewport) is unchanged at `(960, 600)`; only the *total* window
grows by the fixed `160px` band allowance (§6). Concretely, for the
existing `test_automatic_initial_window_uses_a_useful_integer_scale`
parametrization (unchanged, still passing): a `256`-cell arena still
renders its `16x16` grid at scale `37` (`592x592` arena pixels), a
`512`-cell arena still renders its `32x16` grid at scale `30`
(`960x480` arena pixels) — the *arena* pixel footprint in every case is
byte-for-byte what it was before this phase; the window around it is
taller by `160px` to make room for the two new bands.

## 14. Controls / footer contents

- **Footer line 1**: `Tick {tick}/{final_tick}   [{PLAYING|PAUSED|PAUSED
  (end)}]   speed {x}x` (`format_playback_line`).
- **Footer line 2** (adaptive, one line, truncated to its column): selected-
  cell inspector when a cell is selected, else the single most recent
  event at/before the current tick (still click-to-seek), else `"No recent
  events"`.
- **Footer line 3**: `HELP_TEXT` (the existing keyboard-shortcut string,
  unchanged content, now deterministically truncated to its own column
  width rather than left to run arbitrarily wide — §7).
- **Footer right edge** (window `>= 460px` wide only): the relocated
  territory-history trend graph.

No keyboard behavior changed — `dispatch_key`/`KeyAction`/`PlaybackController`
are untouched by this phase; only *where* their resulting state is drawn
changed.

## 15. Capture presentation

Restrained per the governing task's explicit scope (Phase 4L: "HUD/status
polish, not effects design"): the entrant's status line changes color
(amber) and text (`"CAPTURED @ Ttick[ by killer]"`), the core value reads
`Core 0/8`, and the footer's status/event message shows the plain-text
kill/death event line (e.g. `"T002 kill: core_defender by core_tracker"`)
when the current tick is at or after the capture. No animation, no
particle effect, no color-only signal — verified in the real three-entrant
capture screenshot (§22).

## 16. Testing

| Category | File | Count |
|---|---|---|
| Geometry + formatting (pure, no Pygame) | `client/tests/test_hud_layout.py` (new) | 41 |
| Renderer integration (band drawing, click-to-select, window sizing) | `client/tests/test_pygame_renderer.py` | see §17 delta |
| Playback-controller HUD content (re-pointed to the new formatters) | `client/tests/test_playback_controller.py` | see §17 delta |

`test_hud_layout.py` covers every Phase 4S/4T requirement directly: two-
and three-entrant no-overlap, arena-within-window, footer-does-not-overlap-
arena, resize increases/maintains arena size, minimum-size degrades without
going negative, footer-graph visibility threshold, v1/v2-healthy/v2-
damaged/v2-captured/v2-captured-unattributed/v1-with-killer status-line
formatting, score/territory/kills hierarchy and its drop order under
narrowing width, long-name truncation, and match-header/playback-line
formatting including the v1-vs-v2 label distinction.

`test_pygame_renderer.py` adds real-replay integration tests (Phase 4U):
hand-built `battle2.replay` v3 fixtures for a v2 two-entrant
healthy→damaged→captured sequence (with an unattributed-capture variant)
and a v2 three-entrant healthy fixture, each driven through the actual
`PygameRenderer._draw_top_band`/`_draw_footer` methods (not a
reimplementation) against minimal fakes for the low-level Pygame
primitives (`_FakeSurface`/`_FakeFont`/`_FakeDraw`/`_FakePygame` — the same
"fake the display, drive the real code" convention this file already used
for window sizing/cell selection), plus a parametrized "renders without
crashing" sweep across VM, Python, v2-two-entrant, and v2-three-entrant
replay kinds. Arena-rect-aware click translation is directly tested
(`test_handle_click_translates_into_arena_local_coordinates`, `test_
handle_click_above_the_arena_band_does_not_select_a_cell`).

## 17. Real-replay integration

Beyond the fixture-based tests in §16, this phase's manual/headful smoke
(§22) rendered actual replays — one produced by a real `NativeMatchService`
run through `bytefray`'s own CLI (`--a-type writer --b-type runner`) and
several hand-built `battle2.replay` v3 fixtures loaded through the real
`ReplaySession`/`PygameRenderer.run()`-adjacent setup path — end to end
through the genuine renderer code, using a real (headless SDL "dummy"
driver) Pygame font/surface/draw stack, not a fake. See §22 for what was
observed.

## 18. Manual/headful smoke disposition

This session has no attached interactive display. Per the governing task's
explicit guidance ("If the environment cannot display pygame: document the
limitation and rely on the strongest available automated/headless
rendering path"), the strongest available path was used: SDL's `dummy`
video/audio drivers (`SDL_VIDEODRIVER=dummy`), which let a *real* Pygame
(real `Surface`/font rasterization/`pygame.draw`, not a mock) run
end-to-end through `PygameRenderer._configure_window`/`_redraw` without a
physical window, with the resulting frame buffer saved via
`pygame.image.save` and visually inspected as a PNG. This is real
rendering output, genuinely observed — not a claim of qualification without
having actually viewed it.

### Observed v1 result

Two-entrant VM replay (`writer` vs. `runner`), `912x616` window: clean
header (`Ruleset bytefray-rules-1 | runtime vm | arena 128 | entrants 2`)
plus a winner/termination line; two side-by-side cards, `WRITER` (red,
`Dead @ T1`) and `RUNNER` (blue-green, `Alive`) — **no `Core` field on
either**, confirming the v1 no-bogus-core requirement visually, not just by
assertion. Arena fully unobstructed, agent marker and ownership tint
visible and undisturbed. Footer shows the tick/status/speed line, the
`T001 death: A` event message, and a cleanly ellipsis-truncated controls
line ending exactly at the graph panel's left edge (post-fix — see §7).

### Observed v2 result (healthy/damaged)

Three-entrant hand-built v2 fixture at tick 1, `520x550` window:
`CORE_TRACKER`/`CLAIMER` both `Alive | Core 8/8`; `CORE_DEFENDER` reads
`Alive | Core 5/8` (green name, green "Alive", correct reduced integrity)
after three of its core cells were reassigned to another entrant in the
fixture — core integrity visibly distinct from score/territory, matching
Phase 4N's hierarchy.

### Observed capture result

Same fixture at tick 2 (`440x490` window, deliberately narrow):
`CORE_DEFENDER`'s card turns amber, reads `CAPTURED @ T2 | Co…`
(ellipsis-truncated — this card width is narrower than the full string
needs; the killer clause was already dropped first per priority, and the
remaining `"CAPTURED @ T2 | Core 0/8"` still doesn't fit `~19` characters,
so it falls through to the documented final ellipsis fallback) while
`CORE_TRACKER`/`CLAIMER` remain green/alive. The footer shows `T002 kill:
core_defender by core_tracker`. Capture is visually obvious (color change +
distinct wording + footer event) without any animation.

### Observed three-entrant result

At a realistic default-scale window (`704x688` for this fixture's small
48-cell arena, no artificial narrowing): all three cards fully legible,
identical widths, complete `Score N | Territory 8 (16.7%)` lines with
nothing dropped — confirming the earlier truncation observations are a
narrow-window degradation path, not the normal experience.

### Observed resize result

Verified structurally (§6, §13) and via the geometry test suite
(`test_larger_window_increases_or_maintains_arena_size`); the same real
renderer method (`_redraw`) was exercised at three different window sizes
in the smoke above (`912x616`, `520x550`/`440x490`/`420x520`), each
producing a valid non-overlapping layout with the arena visibly resizing
while the two chrome bands' heights stayed fixed.

### Screenshot disposition

Not committed to `docs/screenshots/`. The captures above are genuine and
representative, but per the governing task's explicit optionality ("this
is optional if screenshot capture infrastructure is awkward... a v2
screenshot can be used later in beta/readme work") and its instruction not
to replace the existing historical `docs/screenshots/replay-viewer.png`
"solely for novelty," this phase deliberately leaves the repository's
tracked screenshot untouched and defers adding a new one to later beta/
README work, where it can be chosen to match whatever match/branding
context that work wants to showcase.

## 19. Performance

No profiling was necessary to reach this conclusion, matching Phase 3's
own "bound is evident by construction" precedent:

- **Status retrieval**: `_draw_top_band` calls `get_entrant_statuses`
  once per frame with the renderer's already-cached `self._match_events`
  passed in explicitly (never recomputed) — the same O(entrants x 8)
  core-integrity bound and O(1)-relative-to-replay-length anchor
  derivation Phase 3 already established, now actually exercised on the
  documented "per-frame render loop" hot path its own docstring
  anticipated.
- **No replay reconstruction from tick zero per frame**: `ReplaySession`'s
  own incremental `step_forward`/`seek` (unchanged) remains the only state
  reconstruction; `_draw_top_band` reads `session.current_state`, it does
  not re-walk the replay.
- **No whole-arena rescan added for HUD**: entrant cards read only the
  already-reconstructed `ReplayState`/`EntrantReplayStatus` fields; no new
  per-cell scan was introduced anywhere in this phase.
- **Text rendering**: the same number of `hud_font.render`/`blit` calls as
  before (one call per HUD line), merely redistributed across three
  drawing methods instead of one — no new per-frame Pygame surface
  allocation beyond the existing per-frame HUD/footer/graph panel
  surfaces, which existed pre-Phase-4 too (the old `_draw_hud`'s
  `SRCALPHA` panel, the always-present territory-graph panel).

## 20. Regression qualification

| Check | Result |
|---|---|
| New Phase-4 pure formatting/geometry tests (`test_hud_layout.py`, new file) | 41 |
| `test_pygame_renderer.py` (band-drawing integration, arena-rect-aware clicks, updated window-sizing expectations; 15 old flat-HUD tests removed, replaced by band-based equivalents) | 86 collected |
| `test_playback_controller.py` (HUD-content tests re-pointed at the new formatters; 2 VM/Python low-level-diagnostics tests removed as an explicit, documented scoping decision — §4) | 40 collected |
| `python -m pytest` (full, clean run — no concurrent pytest processes) | **1731 passed, 6 skipped, 0 failed** (1737 collected, 202.6s) |
| Reconciliation | Phase-4 baseline 1687 passed + 44 net new passing tests = 1731 — exact; 6 skipped unchanged (no new skips introduced) |
| `ruff check engine client` | All checks passed |
| `mypy engine/src/battle_engine` | Success: no issues found in 70 source files |
| `mypy client/src/battle_client` | Success: no issues found in 12 source files |
| `git diff --check` | clean |
| `git diff --stat -- engine/src/battle_engine` | empty — zero engine source lines changed this phase |

One transient failure was observed and diagnosed, not counted above:
`engine/tests/test_agent_evaluation_parallel.py::test_resume_after_
coordinator_interruption_matches_uninterrupted_reference` failed once with
a Windows `PermissionError` while two `pytest` processes were briefly
running concurrently against the shared repo-local `.pytest-tmp` directory
during this session's own iterative verification — exactly the documented
concurrency class of issue in `docs/WINDOWS_DEV_NOTES.md`, not a real
regression, and in a file this phase never touched. Re-run in isolation,
and in every subsequent clean (non-concurrent) full-suite run, it passed;
the reconciled numbers above are all from clean, non-concurrent runs.

## 21. Beta1 Phase-5 boundary

Explicitly not started by this phase, per the governing task's scope
exclusions: Agent Designer visual work (recorded as deferred — see below),
gameplay/replay-schema/evaluation changes, multi-entrant product/evaluation
workflow, VM Ruleset-v2 support, packaging/release work. Phase 4's job was
the Replay Viewer HUD redesign only, and it is complete pending the final
reconciled test count (§21 above) and commit.

### Designer visual treatment: recorded as deferred

Per the governing task's Phase 4X, the previously researched Agent
Designer branded empty-state treatment was **not** implemented in this
phase — deliberately, since the Replay Viewer HUD redesign is sufficient
for the first visible v2 milestone, the Designer's Ruleset-v2 workflow
integration has not happened yet, and combining both interfaces in one
phase would dilute qualification focus. This idea is not lost: it remains
recorded as a candidate for a later Beta1 phase or for `v2.0.0-beta3`
("Workflow & Compatibility Stabilization" — see `docs/V2_0_BETA1_PLAN.md`
§8), whichever the roadmap reaches first.
