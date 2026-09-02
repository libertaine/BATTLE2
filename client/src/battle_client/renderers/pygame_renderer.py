"""Interactive Pygame replay viewer, driven entirely by ``ReplaySession``.

``PygameRenderer`` is no longer an ``AbstractRenderer`` subclass and is not
driven by ``ReplayPlayer``'s one-shot forward stream: it is interactive
(play/pause/step/seek/restart/speed), and a forward-only record iterator
cannot represent "go back". Instead, ``PygameRenderer.run(session, ...)``
owns a normal Pygame event/render loop and reads reconstructed state
directly from a ``battle_client.session.ReplaySession`` on every frame via
``session.current_state`` -- there is no second, renderer-owned
reconstruction of arena bytes, ownership, agent state, or score anywhere
in this module. The only per-frame state this renderer keeps for itself is
purely visual and transient (recent write flashes, agent trails, and --
Phase 7b Slice 3 -- a tick-indexed "recent activity" recency map); all of
it is cleared on any non-linear tick change (a seek/restart, as opposed to
a plain forward step), so it never implies history that didn't actually
happen at the tick currently on screen. The one exception is the
territory-history trend graph, which is precomputed once per loaded
session (see ``compute_territory_history``) rather than accumulated
per-frame, since it reads as "this match's territory history up to now"
regardless of how the viewer got to the current tick.

``HeadlessRenderer`` (a different renderer, in ``renderers/headless.py``)
is unaffected by any of this and still uses the original
``ReplayPlayer``/``AbstractRenderer`` streaming path.

**Beta1 Phase 4 (HUD separation).** The window is tiled into three
non-overlapping bands -- a top HUD band (match header + one status card
per entrant), a middle arena band, and a bottom footer band (playback/tick,
a compact status/event message, controls, and the territory-history graph)
-- via ``battle_client.hud_layout.calculate_layout``. Only spatially
meaningful overlays (ownership tint, recent-activity heatmap, write
flashes, agent trails/markers, the selected-cell highlight) are drawn on
the arena band itself; everything else lives in a band. Per-entrant status
(alive/dead, Ruleset-v2 core integrity/capture/attribution, score,
territory, kills) is read entirely from ``battle_client.replay_status.
get_entrant_statuses`` (the Phase-3 status model) -- this module never
derives core addresses, ownership, capture state, death state, killer, or
Ruleset semantics from raw replay structures itself. See
``docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md`` for the full design record.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from battle_engine.paths import get_branding_icon_path
from battle_engine.replay import AgentEvent, AgentState, EngineEvent, KillDeathEvent, RuntimeEvent

from battle_client.analysis import (
    SelectedCellInfo,
    TerritoryHistory,
    collect_match_events,
    compute_territory_history,
    events_near_tick,
    nearest_recorded_tick,
    selected_cell_info,
    timeline_event_marks,
)
from battle_client.director import DirectorManager, PlaybackDirectorRuntime
from battle_client.fight_night import (
    FightNightManager,
    FightNightPhase,
    FightNightState,
)
from battle_client.hud_layout import (
    CARD_LINE_HEIGHT,
    COMPACT_HELP_TEXT,
    FIGHT_NIGHT_LINE_HEIGHT,
    FIGHT_NIGHT_PADDING,
    FOOTER_HEIGHT,
    FOOTER_LINE_HEIGHT,
    HEADER_LINE_HEIGHT,
    HEADER_LINES,
    MIN_VIEWER_SIZE,
    CardMode,
    ViewerLayout,
    calculate_layout,
    entrant_card_known,
    fight_night_card_rect,
    fight_night_ribbon_capacity,
    fight_night_ribbon_rect,
    format_entrant_card_lines,
    format_fight_night_opening_lines,
    format_fight_night_result_lines,
    format_fight_night_ribbon_line,
    format_fight_night_ribbon_title,
    format_help_lines,
    format_match_header_lines,
    format_playback_line,
    integer_scale_to_fit,
    timeline_contains,
    timeline_tick_for_x,
    timeline_x_for_tick,
    truncate_with_ellipsis,
)
from battle_client.perspective import (
    BROADCAST_MODE,
    KnowledgeStatus,
    PerspectiveManager,
    PerspectiveState,
)
from battle_client.player import PlaybackController
from battle_client.renderers.base import RendererDependencyError
from battle_client.replay_status import (
    EntrantReplayStatus,
    get_entrant_statuses,
    resolve_match_ruleset_label,
)
from battle_client.session import ReplaySession, ReplayState

FLASH_TTL = 6
TRAIL_LENGTH = 200

# Phase 7b Slice 3: territory-history trend graph and recent-activity heatmap.
# All three are deliberately small: the graph shows only a trailing window of
# ticks (not the whole match) downsampled to a point cap, and the activity
# heatmap only remembers a bounded number of recent per-address changes -- see
# compute_territory_history's and _advance_transient_effects's docstrings.
TERRITORY_HISTORY_WINDOW_TICKS = 300
TERRITORY_GRAPH_MAX_POINTS = 120
ACTIVITY_WINDOW_TICKS = 30
ACTIVITY_COLOR: tuple[int, int, int] = (255, 200, 80)

# Ordinary replay launches choose the largest uniform integer cell scale
# that fits inside this preferred viewport, then clamp it to 90% of the
# actual display.  This is a target rather than a forced window size: the
# arena's aspect ratio remains authoritative.
PREFERRED_WINDOW_SIZE = (960, 600)
DISPLAY_USAGE_FRACTION = 0.90

# Color palette (unchanged from the prior renderer).
AGENT_COLORS: dict[str, tuple[int, int, int]] = {
    "A": (220, 70, 70),  # red-ish
    "B": (70, 120, 220),  # blue-ish
    "C": (80, 200, 120),  # green-ish
    "D": (200, 180, 70),  # amber
}
GRID_BG: tuple[int, int, int] = (12, 12, 14)
GRID_LINE: tuple[int, int, int] = (26, 26, 30)
OWNERSHIP_TINT: dict[str, tuple[int, int, int]] = {
    "A": (120, 30, 30),
    "B": (30, 60, 120),
    "C": (30, 110, 70),
    "D": (110, 95, 30),
}
PROCESS_FLASH: dict[str, tuple[int, int, int]] = {
    "A": (255, 80, 80),
    "B": (80, 140, 255),
    "C": (90, 255, 170),
    "D": (255, 230, 100),
}
DEFAULT_TINT = (80, 80, 80)
DEFAULT_FLASH = (255, 255, 255)
DEFAULT_AGENT_COLOR = (200, 200, 200)
SELECTION_COLOR: tuple[int, int, int] = (255, 255, 0)

# HUD band colors (Beta1 Phase 4). Bands are solid, not translucent -- they
# no longer overlay the arena, so there is nothing beneath them to blend
# with (see docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md). Status color is always a
# color *plus* text ("Alive"/"Dead"/"CAPTURED" are never conveyed by color
# alone -- see the governing task's Phase 4M).
PANEL_BG: tuple[int, int, int] = (16, 16, 19)
PANEL_BORDER: tuple[int, int, int] = (48, 48, 54)
TEXT_COLOR: tuple[int, int, int] = (225, 225, 225)
DIM_TEXT_COLOR: tuple[int, int, int] = (150, 150, 155)
STATUS_ALIVE_COLOR: tuple[int, int, int] = (120, 220, 140)
STATUS_DEAD_COLOR: tuple[int, int, int] = (225, 100, 100)
STATUS_CAPTURED_COLOR: tuple[int, int, int] = (235, 150, 70)
# Phase 8.5: a Perspective card whose life/core state is not known to the
# selected entrant (see hud_layout.entrant_card_known) is colored neutrally
# -- never the real alive/dead/captured color, which would leak the hidden
# fact through styling even while the text itself correctly reads "UNKNOWN"
# (the Phase 8.5 brief's Sec. 13 "no hidden association through styling").
STATUS_UNKNOWN_COLOR: tuple[int, int, int] = (150, 150, 155)
TERMINAL_TEXT_COLOR: tuple[int, int, int] = (255, 220, 120)
# Rough monospace glyph width for the HUD font, used only to convert a
# card's pixel width into a character budget for deterministic truncation
# (see hud_layout.truncate_with_ellipsis) -- an estimate, not a font metric
# query, since the exact figure only affects how eagerly text truncates,
# never correctness (see test_hud_layout.py's truncation tests).
HUD_CHAR_WIDTH_PX = 7

# Header identity icon (Phase 1 branding parity with Agent Designer's
# DesignerIdentityHeader): small enough to sit inside the fixed two-line
# header band (HEADER_LINES * HEADER_LINE_HEIGHT = 36px) with margin.
# Purely decorative -- degrades silently to icon-free text when the shared
# branding asset is unavailable, exactly like the Designer's own
# _apply_optional_branding_icon.
HEADER_ICON_SIZE = 24
HEADER_ICON_GAP = 8

# Compatibility import surface for tests/consumers that historically imported
# the footer help text from this module. Beta3 makes it deliberately compact;
# the full two-line help panel is toggled with ``?``.
HELP_TEXT = COMPACT_HELP_TEXT

# v3.0 "fun feature": a temporary Core Capture Callout (see
# docs/V3_CORE_CAPTURE_CALLOUT.md). Matches the replay-evidence check
# battle_client.replay_status.CoreStatus.captured already performs (see
# that module's _core_status) -- not a new fact, a presentation-local
# re-check of the same recorded AgentState.termination_reason field.
CORE_CAPTURE_TERMINATION_REASON = "core_captured"

# Tick-denominated, not frame- or wall-clock-based: the callout's
# visibility is a pure function of the current replay tick relative to the
# tick it was captured on, so pausing freezes it exactly in place for
# free, and a speed change needs no special-casing. 40 ticks is ~2 seconds
# of match time at the CLI's DEFAULT_TICK_INTERVAL (0.05s/tick) 1x default
# -- a short, restrained interval, not a lingering banner.
CAPTURE_CALLOUT_DURATION_TICKS = 40
# The linear fade in/out portion of that lifetime, in ticks each end.
CAPTURE_CALLOUT_FADE_TICKS = 8
# Title line plus at most this many attribution lines before the overflow
# collapses into one "+N more" summary line -- keeps the box concise even
# for a hypothetical many-entrant match with several simultaneous captures.
CAPTURE_CALLOUT_MAX_LINES = 4
# Match timeline (the footer's whole-match scrub track). Deliberately
# low-contrast chrome: the track and its elapsed fill sit at the same
# brightness as the existing footer panel border and dim text, so the
# playhead -- the one thing that moves -- is what the eye follows.
TIMELINE_TRACK_COLOR: tuple[int, int, int] = (30, 30, 35)
TIMELINE_TRACK_BORDER: tuple[int, int, int] = PANEL_BORDER
TIMELINE_ELAPSED_COLOR: tuple[int, int, int] = (58, 62, 76)
TIMELINE_PLAYHEAD_COLOR: tuple[int, int, int] = TEXT_COLOR
# Event marks are drawn in the affected entrant's own arena color, so a
# mark on the track and that entrant's card/territory share one identity.
TIMELINE_MARK_HEIGHT = 4
TIMELINE_MARK_WIDTH = 2

CAPTURE_CALLOUT_BG: tuple[int, int, int] = (20, 16, 10)
CAPTURE_CALLOUT_MAX_WIDTH = 360
CAPTURE_CALLOUT_MARGIN = 40

# Fight Night chrome (Phase 8). Deliberately one fixed accent pair, not the
# per-entrant OWNERSHIP_TINT/AGENT_COLORS palette: a ribbon entry tinted with
# its subject's own color would let a viewer associate an anonymous on-arena
# contact with a named entrant purely from matching hues, which is exactly
# the identity leak the Phase 8 brief's Sec. 27/37 name as a negative
# regression. Entry text therefore never varies by entrant.
FIGHT_NIGHT_BG: tuple[int, int, int] = (10, 12, 18)
FIGHT_NIGHT_BORDER: tuple[int, int, int] = (90, 130, 190)
FIGHT_NIGHT_TITLE_COLOR: tuple[int, int, int] = (140, 190, 255)
FIGHT_NIGHT_ENTRY_COLOR: tuple[int, int, int] = (225, 228, 235)
FIGHT_NIGHT_PANEL_ALPHA = 205
FIGHT_NIGHT_CARD_ALPHA = 235


@dataclass(frozen=True)
class CoreCaptureAttribution:
    """One entrant's core-capture fact at a single tick.

    Mirrors the identical victim/killer facts
    ``battle_client.replay_status.CoreStatus``/``_death_tick_and_killer``
    already derive from the same replay evidence (a recorded
    ``KillDeathEvent`` plus the victim's own ``AgentState.
    termination_reason``) -- this is a presentation-local re-derivation of
    those facts for the callout's own tick-by-tick trigger, not a second
    source of truth.
    """

    victim: str
    killer: str | None


def core_captures_at_tick(
    events: Sequence[tuple[int, EngineEvent]],
    tick: int,
    agents: Mapping[str, AgentState],
) -> tuple[CoreCaptureAttribution, ...]:
    """Every core-capture recorded at exactly ``tick``, in recorded order.

    A recorded ``KillDeathEvent`` (``"kill"`` or unattributed ``"death"``)
    is a core capture iff its victim's ``AgentState`` at this tick carries
    ``termination_reason == "core_captured"`` -- the same check
    ``battle_client.replay_status._core_status`` performs, applied here
    directly to one tick's own events/agents instead of by re-deriving a
    full ``EntrantReplayStatus``. Returns one attribution per distinct
    victim captured at this tick -- more than one is possible, since
    ``battle_engine.python_runtime.apply_core_capture`` checks every
    living entrant each tick before scoring. Returns ``()`` for a
    Ruleset-v1 or VM replay, where ``termination_reason`` is never
    ``"core_captured"``, and for any tick with no recorded capture.
    """
    captures: list[CoreCaptureAttribution] = []
    for event_tick, event in events:
        if event_tick != tick or not isinstance(event, KillDeathEvent):
            continue
        agent_state = agents.get(event.victim)
        if agent_state is not None and agent_state.termination_reason == CORE_CAPTURE_TERMINATION_REASON:
            captures.append(CoreCaptureAttribution(victim=event.victim, killer=event.killer))
    return tuple(captures)


def _perspective_safe_captures(
    captures: Sequence[CoreCaptureAttribution],
    *,
    selected_entrant_id: str | None,
    is_terminal: bool,
) -> tuple[CoreCaptureAttribution, ...]:
    """Which of ``captures`` the capture callout may show for one tick
    (Phase 8.5's remediation for the brief's Sec. 16 "hidden core-loss
    regression": the callout is a reactive banner in the same top HUD band
    as the entrant cards, and naming *both* victim and killer makes it a
    more severe leak than the ambient cards were -- it must obey the same
    knowledge boundary ``hud_layout.entrant_card_known`` gives the cards,
    computed from the same ``(selected_entrant_id, is_terminal)`` basis.

    Broadcast (``selected_entrant_id is None``) and the terminal tick show
    every capture unchanged, matching ``entrant_card_known``'s own "no more
    hidden gameplay to protect" exception. Otherwise a capture is shown only
    when the selected entrant is its *victim* -- an entrant trivially knows
    its own core was captured -- and even then with ``killer`` stripped to
    ``None``: the attacker's identity is never delivered to the victim
    through the qualified anonymous-contact model (spec Sec. 6), so naming
    one here would associate a named entrant with the victim's own
    anonymous-contact history exactly as Sec. 13 forbids. An opponent-vs-
    opponent capture, or one where the selected entrant is the *attacker*,
    is suppressed entirely, with no "unless you did it" exception --
    ``AGENT_ELIMINATED`` is omniscient-only unconditionally (Phase 7 §2),
    and this callout does not invent a narrower rule than the Director and
    Fight Night already settled on.
    """
    if selected_entrant_id is None or is_terminal:
        return tuple(captures)
    return tuple(
        CoreCaptureAttribution(victim=capture.victim, killer=None)
        for capture in captures
        if capture.victim == selected_entrant_id
    )


def format_core_capture_callout_lines(
    captures: Sequence[CoreCaptureAttribution], names: Mapping[str, str]
) -> tuple[str, ...]:
    """"CORE CAPTURED" callout text: a title line plus one attribution
    line per victim captured together at the same tick.

    Factual replay evidence only -- ``"{killer} eliminated {victim}"``
    when a killer is attributed, ``"{victim} eliminated"`` when it is not
    -- never invented strategic prose (see
    docs/V3_CORE_CAPTURE_CALLOUT.md §7). ``names`` maps agent id to
    display name (``EntrantReplayStatus.name``); an id missing from it
    falls back to the bare id. More than ``CAPTURE_CALLOUT_MAX_LINES - 1``
    simultaneous captures collapse the overflow into one summary line
    rather than growing the box unboundedly -- the total line count
    (title + shown attributions + one optional summary line) never
    exceeds ``CAPTURE_CALLOUT_MAX_LINES``.
    """
    title = "CORE CAPTURED"
    if not captures:
        return (title,)
    if len(captures) <= CAPTURE_CALLOUT_MAX_LINES - 1:
        shown, remaining = captures, 0
    else:
        shown = captures[: CAPTURE_CALLOUT_MAX_LINES - 2]
        remaining = len(captures) - len(shown)
    lines = [title]
    for capture in shown:
        victim = names.get(capture.victim, capture.victim)
        if capture.killer:
            killer = names.get(capture.killer, capture.killer)
            lines.append(f"{killer} eliminated {victim}")
        else:
            lines.append(f"{victim} eliminated")
    if remaining > 0:
        lines.append(f"+{remaining} more")
    return tuple(lines)


def capture_callout_alpha(tick_into_window: int, duration: int, fade_ticks: int) -> float:
    """Linear fade in/out envelope for the callout's visible lifetime, as
    a fraction in ``[0, 1]``.

    Ramps up over the first ``fade_ticks`` ticks, holds at ``1.0``, then
    ramps down over the last ``fade_ticks`` ticks before ``duration`` --
    the same tick-denominated linear-decay shape ``activity_intensity``
    already uses elsewhere in this module, applied here to a callout's own
    bounded window instead of a per-cell recency map. ``tick_into_window``
    is ``current_tick - capture_tick`` (``0`` at the instant of capture).
    Purely a function of tick position, so it needs no separate per-frame
    animation clock and stays exact under any playback speed, or a pause
    (which simply stops ``tick_into_window`` from advancing). Returns
    ``0.0`` outside ``[0, duration)`` -- but never at ``tick_into_window ==
    0`` itself (the capture's own tick always renders at at least a sliver
    of visibility, ``1 / fade_ticks``, rather than being invisible on the
    very tick it happens).
    """
    if duration <= 0 or tick_into_window < 0 or tick_into_window >= duration:
        return 0.0
    fade = max(0, min(fade_ticks, duration // 2))
    if fade == 0:
        return 1.0
    if tick_into_window < fade:
        return (tick_into_window + 1) / fade
    remaining = duration - tick_into_window
    if remaining <= fade:
        return remaining / fade
    return 1.0


def choose_initial_window_scale(
    grid_cols: int,
    grid_rows: int,
    display_bounds: tuple[int, int],
    *,
    requested_scale: int | None = None,
    preferred_size: tuple[int, int] = PREFERRED_WINDOW_SIZE,
) -> int:
    """Choose the initial uniform integer cell scale for a replay window.

    With no explicit request, the preferred viewport selects a useful
    cross-platform default without forcing one exact pixel geometry.
    Explicit scales retain their existing meaning as an initial preference,
    subject to the same display-safety cap as automatic sizing.
    """

    display_width = max(1, int(display_bounds[0]))
    display_height = max(1, int(display_bounds[1]))
    display_scale = integer_scale_to_fit(
        grid_cols, grid_rows, (display_width, display_height)
    )
    if requested_scale is not None:
        return min(max(1, int(requested_scale)), display_scale)

    target = (
        min(max(1, int(preferred_size[0])), display_width),
        min(max(1, int(preferred_size[1])), display_height),
    )
    return min(integer_scale_to_fit(grid_cols, grid_rows, target), display_scale)


# ---------------------------------------------------------------------------
# HUD content: pure functions over ReplaySession/PlaybackController/
# ReplayState, deliberately kept free of any Pygame dependency so they can
# be unit tested without opening a window. Per-entrant status text
# construction (name/alive/core/score/territory/kills) lives in
# battle_client.hud_layout, over the Phase-3 battle_client.replay_status
# model -- not here (see docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md).
# ---------------------------------------------------------------------------
def select_history_window(
    ticks: Sequence[int], values: Sequence[float], current_tick: int, window: int
) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """The trailing slice of ``(ticks, values)`` covering
    ``[current_tick - window, current_tick]``.

    ``ticks``/``values`` must already be aligned and in ascending tick
    order (as :class:`TerritoryHistory` guarantees). Never includes a tick
    after ``current_tick``: the graph shows the match's history up to the
    replay's current playback position, never a preview of ticks the
    replay hasn't reached yet. Returns empty tuples for an empty input.
    """
    if not ticks:
        return (), ()
    start = bisect.bisect_left(ticks, current_tick - window)
    end = bisect.bisect_right(ticks, current_tick)
    return tuple(ticks[start:end]), tuple(values[start:end])


def downsample_series(
    ticks: Sequence[int], values: Sequence[float], max_points: int
) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """Evenly sample ``(ticks, values)`` down to at most ``max_points``
    points, always including the first and last (most recent) point so the
    graph's right edge always reflects the current tick exactly. A no-op
    if there are already ``max_points`` or fewer points (including
    ``max_points <= 0``, which would otherwise mean "keep none").
    """
    n = len(ticks)
    if n <= max_points or max_points <= 0:
        return tuple(ticks), tuple(values)
    if max_points == 1:
        return (ticks[-1],), (values[-1],)
    indices = sorted({round(i * (n - 1) / (max_points - 1)) for i in range(max_points)})
    return tuple(ticks[i] for i in indices), tuple(values[i] for i in indices)


def territory_graph_points(
    ticks: Sequence[int],
    values: Sequence[float],
    rect: tuple[int, int, int, int],
    value_max: float = 100.0,
) -> list[tuple[int, int]]:
    """Map ``(tick, value)`` pairs onto screen coordinates inside ``rect``.

    ``rect`` is ``(x, y, w, h)``. ``value`` is a percentage in ``[0,
    value_max]``; ``0`` maps to the bottom of ``rect`` and ``value_max`` to
    the top, so the graph reads the conventional way (higher = more
    territory). Pure coordinate math, no Pygame dependency, so this is
    directly unit-testable without a window. Returns ``[]`` for no input
    points or a degenerate (zero/negative size) rect.
    """
    x, y, w, h = rect
    if not ticks or w <= 0 or h <= 0:
        return []
    first_tick, last_tick = ticks[0], ticks[-1]
    span = last_tick - first_tick
    screen_points: list[tuple[int, int]] = []
    for tick, value in zip(ticks, values):
        fx = (tick - first_tick) / span if span > 0 else 0.0
        clamped = max(0.0, min(value_max, value))
        fy = 1.0 - (clamped / value_max if value_max > 0 else 0.0)
        screen_points.append((int(x + fx * (w - 1)), int(y + fy * (h - 1))))
    return screen_points


def activity_intensity(current_tick: int, last_changed_tick: int, window: int) -> float:
    """How "recently active" a cell that last changed at
    ``last_changed_tick`` is, viewed from ``current_tick``.

    ``1.0`` the tick it changed, decaying linearly to ``0.0`` by
    ``window`` ticks later, floored at ``0.0``: a cell that "changed" at a
    tick after ``current_tick`` (never happens through normal playback,
    since the recency tracker is only ever updated up to the tick just
    rendered) is simply treated as not recently active rather than
    producing a value above ``1.0``. This is the decay/window model for
    the "recent activity" overlay -- tied to replay ticks, not real-time
    frames, so it is identical however many frames a real playback loop
    happens to render for that tick.
    """
    if window <= 0:
        return 0.0
    age = current_tick - last_changed_tick
    if age < 0:
        return 0.0
    return max(0.0, 1.0 - age / window)


def format_event_line(tick: int, event: EngineEvent) -> str:
    """One human-readable line for a single recorded event, e.g.
    ``"T042 kill: B by A"`` or ``"T017 forfeit: C (invalid_action)"``.
    """
    prefix = f"T{tick:03d}"
    if isinstance(event, KillDeathEvent):
        by = f" by {event.killer}" if event.killer else ""
        return f"{prefix} {event.event_type}: {event.victim}{by}"
    if isinstance(event, RuntimeEvent):
        return f"{prefix} {event.event_type}: {event.victim} ({event.reason})"
    if isinstance(event, AgentEvent):
        return f"{prefix} {event.event_type}: {event.agent_id or '?'}"
    return f"{prefix} event"


def resolve_event_click(
    ticks: Sequence[int],
    origin: tuple[int, int],
    size: tuple[int, int],
    line_height: int,
    click: tuple[int, int],
) -> int | None:
    """Which recorded tick (if any) a click at ``click`` selects.

    ``ticks`` is the ordered sequence of tick numbers currently rendered
    as one line each, starting at screen position ``origin`` and spanning
    ``size``, each ``line_height`` pixels tall. Pure coordinate math, no
    Pygame dependency, so this is directly testable without a window.
    Returns ``None`` if the click misses the panel entirely or falls past
    the last rendered line.
    """
    ox, oy = origin
    w, h = size
    cx, cy = click
    if not (ox <= cx < ox + w and oy <= cy < oy + h):
        return None
    if line_height <= 0:
        return None
    index = (cy - oy) // line_height
    if index < 0 or index >= len(ticks):
        return None
    return ticks[index]


def screen_pos_to_address(
    pos: tuple[int, int],
    screen_size: tuple[int, int],
    grid_cols: int,
    grid_rows: int,
    arena_size: int,
) -> int | None:
    """The arena address rendered at screen position ``pos``, or ``None``.

    Inverts the grid-to-screen mapping ``_redraw`` uses (a ``grid_cols`` x
    ``grid_rows`` surface uniformly scaled to fill ``screen_size``): pure
    coordinate math, no Pygame dependency, so it is directly testable
    without a window. Returns ``None`` if ``pos`` falls outside
    ``screen_size`` entirely, or if the grid geometry is degenerate
    (``grid_cols``/``grid_rows``/screen dimensions <= 0). The
    ``address >= arena_size`` guard is a defensive no-op in practice --
    ``_resolve_grid_dims`` always returns a rectangle whose cell count is
    exactly ``arena_size`` -- but is kept here honestly rather than assumed.
    """
    x, y = pos
    w, h = screen_size
    if grid_cols <= 0 or grid_rows <= 0 or w <= 0 or h <= 0:
        return None
    if not (0 <= x < w and 0 <= y < h):
        return None
    col = min((x * grid_cols) // w, grid_cols - 1)
    row = min((y * grid_rows) // h, grid_rows - 1)
    address = row * grid_cols + col
    if address >= arena_size:
        return None
    return address


def format_inspector_lines(
    info: SelectedCellInfo | None, *, recently_changed: bool = False
) -> list[str]:
    """HUD lines for a "Selected cell:" panel, or ``[]`` if ``info`` is
    ``None`` (nothing selected -- ``PygameRenderer._draw_footer`` falls
    back to its idle/event message in that case).

    ``recently_changed`` is renderer-local presentation state (sourced
    from ``PygameRenderer._flash`` -- see ``_selected_cell_info`` below),
    not a field on the domain ``SelectedCellInfo`` itself: see
    ``docs/specs/replay_analysis.md`` §6 for why that boundary was drawn
    here rather than on the analysis-layer dataclass.
    """
    if info is None:
        return []
    byte_label = f"byte=0x{info.byte_value:02x}" if info.byte_value is not None else "byte=?"
    owner_label = f"owner={info.owner}" if info.owner is not None else "owner=none"
    agent_label = f"agent={info.occupant}" if info.occupant is not None else "agent=none"
    line = f"  addr={info.address}  {byte_label}  {owner_label}  {agent_label}"
    if recently_changed:
        line += "  (recently changed)"
    return ["Selected cell:", line]


# ---------------------------------------------------------------------------
# Keyboard dispatch: pure mapping from a Pygame key/modifier pair to a
# PlaybackController command. Uses real Pygame key constants (plain
# integers -- importing them does not require a display or pygame.init()),
# so this is directly unit-testable without opening a window.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KeyAction:
    """The result of dispatching one keypress: what to do, if anything."""

    quit_requested: bool = False
    toggle_trails: bool = False
    toggle_help: bool = False
    rescale: int = 0  # +1/-1 window scale step
    fit_to_display: bool = False
    cycle_perspective: bool = False
    select_perspective_index: int | None = None
    toggle_perspective_debug: bool = False
    toggle_director: bool = False
    toggle_fight_night: bool = False
    restarted: bool = False


def dispatch_key(
    pygame_module: Any,
    key: int,
    mods: int,
    controller: PlaybackController,
) -> KeyAction:
    """Apply one keypress to ``controller`` and report any renderer-local
    (non-controller) action the caller should also perform.
    """
    pg = pygame_module
    shift = bool(mods & pg.KMOD_SHIFT)

    if key in (pg.K_ESCAPE, pg.K_q):
        return KeyAction(quit_requested=True)
    if key == pg.K_SPACE:
        controller.toggle_play_pause()
    elif key == pg.K_RIGHT:
        controller.seek_relative(10) if shift else controller.step_forward()
    elif key == pg.K_LEFT:
        controller.seek_relative(-10) if shift else controller.step_backward()
    elif key == pg.K_HOME:
        controller.restart()
        return KeyAction(restarted=True)
    elif key == pg.K_END:
        controller.jump_to_end()
    elif key in (pg.K_PLUS, pg.K_EQUALS, pg.K_PAGEUP):
        controller.speed_up()
    elif key in (pg.K_MINUS, pg.K_UNDERSCORE, pg.K_PAGEDOWN):
        controller.speed_down()
    elif key == pg.K_LEFTBRACKET:
        return KeyAction(rescale=-1)
    elif key == pg.K_RIGHTBRACKET:
        return KeyAction(rescale=1)
    elif key == pg.K_t:
        return KeyAction(toggle_trails=True)
    elif key in (pg.K_v, pg.K_p):
        return KeyAction(cycle_perspective=True)
    elif key in (getattr(pg, "K_F3", -3), pg.K_d):
        return KeyAction(toggle_perspective_debug=True)
    elif key == pg.K_g:
        return KeyAction(toggle_director=True)
    elif key == pg.K_n:
        return KeyAction(toggle_fight_night=True)
    elif key == getattr(pg, "K_1", -10) and not shift:
        return KeyAction(select_perspective_index=0)
    elif key == getattr(pg, "K_2", -11) and not shift:
        return KeyAction(select_perspective_index=1)
    elif key == getattr(pg, "K_3", -12) and not shift:
        return KeyAction(select_perspective_index=2)
    elif key == getattr(pg, "K_4", -13) and not shift:
        return KeyAction(select_perspective_index=3)
    elif key == getattr(pg, "K_5", -14) and not shift:
        return KeyAction(select_perspective_index=4)
    elif key == getattr(pg, "K_6", -15) and not shift:
        return KeyAction(select_perspective_index=5)
    elif key == getattr(pg, "K_7", -16) and not shift:
        return KeyAction(select_perspective_index=6)
    elif key == getattr(pg, "K_8", -17) and not shift:
        return KeyAction(select_perspective_index=7)
    elif key == getattr(pg, "K_9", -18) and not shift:
        return KeyAction(select_perspective_index=8)
    elif key == getattr(pg, "K_QUESTION", -1) or (
        key == getattr(pg, "K_SLASH", -2) and shift
    ):
        return KeyAction(toggle_help=True)
    elif key == pg.K_0:
        return KeyAction(fit_to_display=True)
    return KeyAction()


class PygameRenderer:
    """Interactive Pygame replay viewer over a ``ReplaySession``."""

    def __init__(self, scale: int | None = None, title: str = "Bytefray - Replay") -> None:
        # ``None`` is the ordinary auto-sized launch.  An explicit value is
        # retained as an initial preference (and capped to the display in
        # _configure_window).  Once configured, ``self.scale`` remains the
        # one live integer cell scale used by manual and resize controls.
        self._requested_scale = None if scale is None else max(1, int(scale))
        self.scale = self._requested_scale or 1
        self.title = title

        self.pg: Any = None
        self.screen: Any = None
        self.grid_surf: Any = None
        self.font: Any = None
        self.hud_font: Any = None
        # Header identity icon surface, set by _configure_window(). None
        # before the first configure (e.g. a unit test that never called
        # run()) and None permanently if the shared branding asset is
        # unavailable -- every header-drawing method below must treat
        # None as "draw text only", matching this renderer's pre-Phase-1
        # behavior exactly.
        self._header_icon: Any = None
        # Captured before the first set_mode() call. Some SDL backends report
        # the current window rather than the desktop from display.Info()
        # after a mode exists, which would otherwise make later manual/fit
        # operations treat the current window as their maximum.
        self._display_safe_bounds: tuple[int, int] | None = None

        self.arena = 0
        self.grid_cols = 0
        self.grid_rows = 0

        # Purely visual, transient state -- never authoritative. Cleared on
        # any non-linear tick change (see _advance_transient_effects).
        self.trails_enabled = True
        self.help_visible = False
        self._trail_points: dict[str, list[tuple[int, int]]] = {}
        self._flash: dict[tuple[int, int], tuple[tuple[int, int, int], int]] = {}
        self._last_rendered_tick: int | None = None
        self._last_owners: tuple[str | None, ...] | None = None

        # Every recorded (tick, event) pair for the loaded session, computed
        # once in run() -- collect_match_events scans every recorded tick,
        # so this is cached for the session's lifetime rather than redone
        # every frame (see get_entrant_statuses's own ``match_events``
        # parameter, which this same cache is passed into every frame).
        self._match_events: list[tuple[int, EngineEvent]] = []
        # Where the footer's compact event/status message was last drawn on
        # screen, and which tick it corresponds to -- set fresh by
        # _draw_footer every frame, read by _loop's click handling. None/
        # empty whenever the footer isn't currently showing a clickable
        # event (nothing recorded yet, or a cell selection is showing
        # instead -- see _draw_footer).
        self._event_panel_origin: tuple[int, int] | None = None
        self._event_panel_size: tuple[int, int] | None = None
        self._event_panel_ticks: tuple[int, ...] = ()

        # The current window's responsive HUD/arena/footer geometry
        # (battle_client.hud_layout.calculate_layout), recomputed whenever
        # the window is (re)configured or resized -- never per-frame, since
        # it depends only on window size, grid, and entrant count, none of
        # which changes between resizes. ``None`` before the first
        # _configure_window() call (e.g. in a unit test that never called
        # run()) -- every geometry-consuming method below falls back to
        # treating the whole screen as the arena in that case, matching
        # this renderer's pre-Phase-4 behavior exactly.
        self._layout: ViewerLayout | None = None
        self._entrant_count = 1
        # The replay's own Ruleset identity label and arena size, resolved
        # once in run() (see battle_client.replay_status.
        # resolve_match_ruleset_label) -- match-level facts that do not
        # change across a replay, so there is no reason to re-resolve them
        # every frame.
        self._ruleset_label = "unknown"

        # Presentation-only selected-cell inspector state (Phase 7b Slice 2).
        # Set by a click on the arena grid (never on the event panel, which
        # takes priority -- see _handle_click); intentionally never cleared
        # by playback navigation (step/seek/restart), so a selection
        # persists across the whole replay for as long as its address stays
        # in range -- which, since a session's arena size never changes,
        # is always, once loaded.
        self._selected_address: int | None = None

        # Match-timeline state. ``_timeline_marks`` is derived once in run()
        # from the same self._match_events cache the footer already uses --
        # no second event scan. ``_timeline_scrubbing`` is true only between
        # a mouse-down that grabbed the track and its matching mouse-up;
        # while it is set, _loop resolves the *current* mouse position once
        # per frame rather than handling every queued MOUSEMOTION, which
        # bounds a drag to at most one ReplaySession.seek per frame no
        # matter how many motion events the platform delivers.
        self._timeline_marks: tuple[tuple[int, str | None], ...] = ()
        self._timeline_scrubbing = False

        # Territory-history trend graph (Phase 7b Slice 3): precomputed once
        # in run() by compute_territory_history, never recomputed per frame.
        self._territory_history = TerritoryHistory(ticks=(), percentages={})

        # Recent-activity heatmap (Phase 7b Slice 3): address -> the tick it
        # last changed owner, maintained incrementally in
        # _advance_transient_effects (same changed-address detection as
        # _flash, reused rather than duplicated). Tick-indexed rather than a
        # per-frame TTL like _flash, so its decay (see activity_intensity)
        # is identical regardless of real frame rate. Cleared on any
        # non-linear tick change -- see _advance_transient_effects's
        # docstring for why "clear" was chosen over "rebuild from history".
        self._recent_changes: dict[int, int] = {}

        # Core-capture callout (v3.0 "fun feature" -- see
        # docs/V3_CORE_CAPTURE_CALLOUT.md). A small FIFO queue, maintained
        # by _advance_capture_callout: captures encountered via genuine
        # continuous forward playback are queued so none are ever silently
        # dropped, and shown one at a time so overlapping captures never
        # stack into unreadable simultaneous boxes. A seek/restart clears
        # both, matching this renderer's existing convention that seeking
        # never replays a transient notification (see
        # _advance_capture_callout's own docstring for why it computes its
        # own tick delta rather than reusing _advance_transient_effects's
        # is_linear_step verbatim). Visibility is a pure function of the
        # current tick vs. the active entry's own expiry tick, never a
        # per-frame counter.
        self._capture_callout_queue: list[tuple[int, tuple[CoreCaptureAttribution, ...]]] = []
        self._active_capture_callout: tuple[int, tuple[CoreCaptureAttribution, ...]] | None = None
        self._capture_callout_expires_after_tick = 0

        # Entrant Perspective Cam state (Phase 5).
        self._perspective_manager: PerspectiveManager | None = None
        self._perspective_debug: bool = False

        # Spectator Director state (Phase 7). Off by default even when a
        # DirectorManager is supplied -- see the CLI's --director flag.
        self._director_manager: DirectorManager | None = None
        self._director_enabled: bool = False

        # Fight Night presentation state (Phase 8). Off by default even when
        # a FightNightManager is supplied -- see the CLI's --fight-night flag.
        # Independent of the Director in both directions: Fight Night draws
        # from its own plan and never consults Director state, so either can
        # be enabled without the other.
        self._fight_night_manager: FightNightManager | None = None
        self._fight_night_enabled: bool = False

    # ---------- grid geometry (pure, presentation-only) ----------

    def _resolve_grid_dims(self, arena_cells: int) -> tuple[int, int]:
        if arena_cells <= 0:
            return 1, 1
        root = int(math.sqrt(arena_cells))
        for c in range(root, 0, -1):
            if arena_cells % c == 0:
                r = arena_cells // c
                return max(c, r), min(c, r)
        c = math.ceil(math.sqrt(arena_cells))
        r = math.ceil(arena_cells / c)
        return c, r

    def _to_xy(self, address: int) -> tuple[int, int] | None:
        if self.arena <= 0 or self.grid_cols <= 0:
            return None
        a = address % self.arena
        return (a % self.grid_cols, a // self.grid_cols)

    def _vm_marker_xy(self, state: ReplayState, agent: AgentState) -> tuple[int, int] | None:
        """The on-grid position of a VM agent's marker, or ``None``.

        ``AgentState.pc`` is typed ``Position = int | tuple[int, int]``
        (see ``battle_engine.replay``), but is only ever a real fetch
        address (``int``) for a VM-runtime replay -- never for a Python
        one, where ``runtime_kind`` is already checked. The ``isinstance``
        check narrows that union for the type checker rather than
        asserting it from ``runtime_kind`` alone.
        """
        if state.runtime_kind != "vm" or not isinstance(agent.pc, int):
            return None
        return self._to_xy(agent.pc)

    def _arena_rect(self) -> tuple[int, int, int, int]:
        """The arena's current on-screen rect.

        Sourced from ``self._layout`` (set by ``_configure_window``/
        ``_resize_window`` -- see ``battle_client.hud_layout.
        calculate_layout``) whenever a real window has been configured.
        Falls back to treating the whole screen as the arena when no layout
        has been computed yet (a unit test that pokes ``self.screen``/
        ``self.grid_cols``/``self.grid_rows`` directly without going through
        ``run()``) -- this is exactly this renderer's pre-Phase-4 behavior,
        preserved deliberately so those tests keep their original meaning.
        """
        if self._layout is not None:
            return self._layout.arena_rect
        w, h = self.screen.get_size()
        return (0, 0, w, h)

    def _screen_xy(self, x: int, y: int) -> tuple[int, int]:
        ax, ay, aw, ah = self._arena_rect()
        return (
            ax + int((x + 0.5) * aw / self.grid_cols),
            ay + int((y + 0.5) * ah / self.grid_rows),
        )

    # ---------- lifecycle ----------

    def run(
        self,
        session: ReplaySession,
        *,
        tick_interval: float,
        start_tick: int | None = None,
        start_paused: bool = False,
        initial_speed: float | None = None,
        perspective_manager: PerspectiveManager | None = None,
        initial_perspective: str | None = None,
        director_manager: DirectorManager | None = None,
        initial_director_enabled: bool = False,
        fight_night_manager: FightNightManager | None = None,
        initial_fight_night_enabled: bool = False,
    ) -> None:
        """Open an interactive window and play ``session`` until the user
        quits. Blocks until then. Raises ``RendererDependencyError`` if
        Pygame is not installed.
        """
        try:
            import pygame
        except ImportError as exc:
            raise RendererDependencyError(
                "Pygame not available. Install pygame or choose --renderer headless."
            ) from exc
        self.pg = pygame
        pygame.init()

        self._perspective_manager = perspective_manager
        if perspective_manager is not None and initial_perspective is not None:
            perspective_manager.set_mode(initial_perspective)

        self._director_manager = director_manager
        self._director_enabled = (
            initial_director_enabled
            and director_manager is not None
            and director_manager.available
        )

        self._fight_night_manager = fight_night_manager
        self._fight_night_enabled = (
            initial_fight_night_enabled
            and fight_night_manager is not None
            and fight_night_manager.available
        )

        self.arena = session.header.config.arena_size if session.header else 0
        self.grid_cols, self.grid_rows = self._resolve_grid_dims(self.arena)
        self._display_safe_bounds = None
        # Match-level facts that never change across a replay (Beta1 Phase
        # 4): entrant count sizes the top band's card row, the Ruleset
        # label answers "is this v1 or v2" in the match header -- see
        # battle_client.replay_status.resolve_match_ruleset_label. Resolved
        # once here, never re-derived by this renderer per frame.
        # ``match_events=()`` here deliberately skips get_entrant_statuses's
        # own internal collect_match_events scan -- only the *count* of
        # entrants is needed for layout sizing, not correct death/kill
        # fields, and self._match_events (the real cache every per-frame
        # call below uses) is computed separately just below.
        self._entrant_count = max(1, len(get_entrant_statuses(session, match_events=())))
        self._ruleset_label = (
            resolve_match_ruleset_label(session.header) if session.header is not None else "unknown"
        )
        self._configure_window()
        # Scans every recorded tick once; see _match_events's docstring in
        # __init__ for why this is cached rather than redone per frame.
        self._match_events = collect_match_events(session)
        # Reduces the already-collected events above to their timeline
        # marks; no additional pass over the replay.
        self._timeline_marks = timeline_event_marks(self._match_events)
        # Also walks every recorded tick once (restoring the cursor
        # afterward); see compute_territory_history's docstring.
        self._territory_history = compute_territory_history(session)

        controller = PlaybackController(
            session, tick_interval=tick_interval, playing=not start_paused
        )
        if initial_speed is not None:
            controller.set_speed(initial_speed)
        if start_tick is not None:
            controller.seek_relative(start_tick - session.current_tick)

        try:
            self._loop(controller)
        finally:
            pygame.quit()

    def _window_size_for_scale(self, scale: int) -> tuple[int, int]:
        """Supported outer size for a deliberate manual/initial scale.

        The 640x480 minimum keeps ordinary launches useful, while the HUD
        height is measured from the same responsive layout helper used for
        rendering rather than copied as another fixed constant.
        """

        arena_w = self.grid_cols * scale
        arena_h = self.grid_rows * scale
        width = max(MIN_VIEWER_SIZE[0], arena_w)
        probe = calculate_layout(
            (width, MIN_VIEWER_SIZE[1]),
            self._entrant_count,
            (self.grid_cols, self.grid_rows),
            preferred_arena_scale=scale,
        )
        height = max(
            MIN_VIEWER_SIZE[1], probe.top_band_height + arena_h + FOOTER_HEIGHT
        )
        return width, height

    def _arena_display_bounds(self) -> tuple[int, int]:
        """Display-safe bounds available to the responsive arena viewport."""
        bounds = self._display_bounds()
        layout = calculate_layout(
            bounds, self._entrant_count, (self.grid_cols, self.grid_rows)
        )
        return layout.arena_viewport_rect[2], layout.arena_viewport_rect[3]

    def _clamp_window_to_display(self, size: tuple[int, int]) -> tuple[int, int]:
        display_w, display_h = self._display_bounds()
        return min(max(1, int(size[0])), display_w), min(max(1, int(size[1])), display_h)

    def _apply_window_size(
        self,
        size: tuple[int, int],
        *,
        preferred_scale: int | None = None,
    ) -> None:
        """Set exactly ``size`` and recompute presentation inside it.

        Ordinary resize callers pass no preferred scale, selecting the
        largest fitting integer scale. Manual zoom callers pass their chosen
        scale and intentionally resize the outer window around it.
        """

        requested = max(1, int(size[0])), max(1, int(size[1]))
        self.screen = self.pg.display.set_mode(requested, self.pg.RESIZABLE)
        self.pg.display.set_caption(self.title)
        self._layout = calculate_layout(
            requested,
            self._entrant_count,
            (self.grid_cols, self.grid_rows),
            preferred_arena_scale=preferred_scale,
        )
        self.scale = self._layout.arena_scale

    def _configure_window(self) -> None:
        pg = self.pg
        self.scale = choose_initial_window_scale(
            self.grid_cols,
            self.grid_rows,
            self._arena_display_bounds(),
            requested_scale=self._requested_scale,
        )
        window_size = self._window_size_for_scale(self.scale)
        # Some platforms ignore an icon set after the window is created, so
        # this must run before set_mode().
        icon_path = get_branding_icon_path()
        if icon_path is not None:
            pg.display.set_icon(pg.image.load(str(icon_path)))
        self._apply_window_size(
            self._clamp_window_to_display(window_size),
            preferred_scale=self.scale,
        )
        self.grid_surf = pg.Surface((self.grid_cols, self.grid_rows))
        self.font = pg.font.SysFont("consolas", 14)
        self.hud_font = pg.font.SysFont("consolas", 13)
        self._header_icon = self._load_header_icon(icon_path)

    def _load_header_icon(self, icon_path: Path | None) -> Any:
        """The header band's small identity icon, or ``None`` if the shared
        branding asset is missing or fails to load -- never raises, matching
        the Designer's own silent-degrade branding pattern. Purely
        decorative, so any failure (a missing/corrupt asset file, or a
        test double standing in for the real ``pygame`` module) degrades to
        icon-free text rather than breaking window configuration.
        """
        if icon_path is None:
            return None
        try:
            loaded = self.pg.image.load(str(icon_path))
            if hasattr(loaded, "convert_alpha"):
                loaded = loaded.convert_alpha()
            return self.pg.transform.smoothscale(loaded, (HEADER_ICON_SIZE, HEADER_ICON_SIZE))
        except Exception:
            return None

    def _display_bounds(self) -> tuple[int, int]:
        if self._display_safe_bounds is not None:
            return self._display_safe_bounds
        pg = self.pg
        try:
            di = pg.display.Info()
            width = int(di.current_w * DISPLAY_USAGE_FRACTION)
            height = int(di.current_h * DISPLAY_USAGE_FRACTION)
        except (pg.error, AttributeError, TypeError, ValueError):
            width, height = 1920, 1080
        self._display_safe_bounds = max(1, width), max(1, height)
        return self._display_safe_bounds

    def _resize_window(self) -> None:
        """Deliberate zoom/fit resize around the current integer scale."""

        size = self._clamp_window_to_display(self._window_size_for_scale(self.scale))
        self._apply_window_size(size, preferred_scale=self.scale)

    def _handle_window_resize(self, size: tuple[int, int]) -> None:
        """Honor an ordinary OS resize without snapping to arena geometry."""

        self._apply_window_size(size)

    def _fit_to_display(self) -> None:
        fit_scale = integer_scale_to_fit(
            self.grid_cols, self.grid_rows, self._arena_display_bounds()
        )
        self.scale = fit_scale
        # ``0 fit`` is an explicit window-sizing command: restore the ideal
        # outer geometry even if an arbitrary resize already happens to use
        # the same integer arena scale.
        self._resize_window()

    def _rescale(self, change: int) -> None:
        """Apply one manual integer scale step within display-safe bounds."""

        display_scale = integer_scale_to_fit(
            self.grid_cols, self.grid_rows, self._arena_display_bounds()
        )
        old = self.scale
        self.scale = max(1, min(display_scale, self.scale + change))
        if self.scale != old:
            self._resize_window()

    def _active_director_runtime(self) -> PlaybackDirectorRuntime | None:
        """The Director runtime for the currently-selected view mode, if
        Director pacing is enabled and available for that mode.

        Broadcast and each entrant's Perspective have independent cached
        runtimes (`DirectorManager.runtime_for`), so cutting between modes
        mid-match never shares or resets another mode's own hold-consumption
        history -- this lookup simply follows whichever mode
        ``self._perspective_manager`` currently reports.
        """
        if not self._director_enabled or self._director_manager is None:
            return None
        mode_key = (
            self._perspective_manager.mode
            if self._perspective_manager is not None
            else BROADCAST_MODE
        )
        return self._director_manager.runtime_for(mode_key)

    # ---------- main loop ----------

    def _loop(self, controller: PlaybackController) -> None:
        pg = self.pg
        clock = pg.time.Clock()
        running = True
        while running:
            elapsed_ms = clock.tick(60)
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False
                    break
                if event.type == pg.KEYDOWN:
                    speed_before = controller.speed
                    action = dispatch_key(pg, event.key, event.mod, controller)
                    if action.quit_requested:
                        running = False
                        break
                    if action.toggle_trails:
                        self.trails_enabled = not self.trails_enabled
                    if action.toggle_help:
                        self.help_visible = not self.help_visible
                    if action.rescale:
                        self._rescale(action.rescale)
                    if action.fit_to_display:
                        self._fit_to_display()
                    if action.cycle_perspective and self._perspective_manager is not None:
                        self._perspective_manager.cycle_mode()
                    if (
                        action.select_perspective_index is not None
                        and self._perspective_manager is not None
                    ):
                        idx = action.select_perspective_index
                        if idx == 0:
                            self._perspective_manager.set_mode(BROADCAST_MODE)
                        elif 1 <= idx <= len(self._perspective_manager.entrants):
                            entrant_id = self._perspective_manager.entrants[idx - 1]
                            self._perspective_manager.set_mode(entrant_id)
                    if action.toggle_perspective_debug:
                        self._perspective_debug = not self._perspective_debug
                    if (
                        action.toggle_director
                        and self._director_manager is not None
                        and self._director_manager.available
                    ):
                        self._director_enabled = not self._director_enabled
                    if (
                        action.toggle_fight_night
                        and self._fight_night_manager is not None
                        and self._fight_night_manager.available
                    ):
                        self._fight_night_enabled = not self._fight_night_enabled
                    if action.restarted and self._director_manager is not None:
                        self._director_manager.restart()
                    # Fight Night deliberately has nothing to reset on
                    # restart: its whole presentation is a pure function of
                    # (plan, tick), so returning to tick 0 already produces
                    # exactly the tick-0 presentation with no residue.
                    if controller.speed != speed_before:
                        # Manual speed selection is an explicit user action
                        # (Sec. 21): it must win outright rather than being
                        # silently overridden by the Director's own rate on
                        # the very next frame, so it disables the Director
                        # instead of fighting it. The user can re-enable
                        # with G if they want automatic pacing back.
                        self._director_enabled = False
                elif event.type in (pg.VIDEORESIZE, getattr(pg, "WINDOWRESIZED", 32769)):
                    w, h = getattr(event, "size", self.screen.get_size())
                    self._handle_window_resize((w, h))
                elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(controller, event.pos)
                elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
                    self._timeline_scrubbing = False
            if not running:
                break

            # A timeline drag is resolved from the mouse's current position
            # once per frame rather than from every queued MOUSEMOTION, so a
            # fast drag costs at most one seek per frame. Held deliberately
            # before controller.update(): _timeline_seek pauses playback, and
            # a scrub should not be fighting an auto-advance in the same
            # frame.
            if self._timeline_scrubbing:
                self._timeline_seek(controller, pg.mouse.get_pos())

            director_runtime = self._active_director_runtime()
            if director_runtime is not None:
                director_runtime.update(controller, elapsed_ms / 1000.0)
            else:
                controller.update(elapsed_ms / 1000.0)
            self._advance_transient_effects(controller.session.current_state)
            self._redraw(controller)
            pg.display.flip()

    def _handle_click(self, controller: PlaybackController, pos: tuple[int, int]) -> None:
        """Grab the timeline, seek to the footer's clickable event
        message, or select an arena cell, for a click at ``pos``.

        The three hit targets are disjoint bands by construction (see
        ``hud_layout.calculate_layout``), so their order is about intent
        rather than overlap resolution: the timeline is checked first
        because grabbing it also begins a drag (see ``_timeline_scrubbing``),
        which must not be started by a click that merely landed near it.

        The footer's event message takes priority over the arena when both
        could apply: a click resolving to its (single) event tick seeks and
        returns immediately, without also touching cell selection.
        ``ReplaySession.seek`` is called directly rather than through
        ``PlaybackController`` because seeking to an arbitrary already-
        recorded tick isn't one of the controller's own navigation
        primitives (see ``player.py``'s module docstring on why
        ``ReplaySession`` stays the sole source of reconstructed state).

        Otherwise, if the click lands on a valid arena cell (translated into
        the arena band's own local coordinates -- see ``_arena_rect``), it
        becomes the selected address (see ``_selected_address``) -- a
        presentation-only selection, not a navigation command, so it never
        pauses playback. A click that hits neither the footer's event
        message nor a valid arena cell (outside the arena band, or before
        the renderer has a real screen -- e.g. in a unit test that never
        called ``run()``) leaves the current selection untouched.
        """
        if self._timeline_seek(controller, pos):
            self._timeline_scrubbing = True
            return

        if self._event_panel_origin is not None and self._event_panel_size is not None:
            tick = resolve_event_click(
                self._event_panel_ticks,
                self._event_panel_origin,
                self._event_panel_size,
                FOOTER_LINE_HEIGHT,
                pos,
            )
            if tick is not None:
                controller.pause()
                controller.session.seek(tick)
                return

        if self.screen is None or self.grid_cols <= 0 or self.grid_rows <= 0:
            return
        ax, ay, aw, ah = self._arena_rect()
        local_pos = (pos[0] - ax, pos[1] - ay)
        address = screen_pos_to_address(local_pos, (aw, ah), self.grid_cols, self.grid_rows, self.arena)
        if address is not None:
            self._selected_address = address

    # ---------- transient (visual-only) effect bookkeeping ----------

    def _advance_transient_effects(self, state: ReplayState) -> None:
        """Update flashes/trails/recent-activity for the newly-current
        ``state``.

        A genuine single-tick forward step extends them; anything else (a
        seek, a restart, the very first frame) clears them first, so a
        backward seek never shows a flash, trail, or "recently changed"
        highlight implying activity that hasn't happened yet relative to
        the tick now on screen.

        Seek/restart policy for ``_recent_changes`` (Phase 7b Slice 3):
        cleared, not rebuilt from nearby replay history. Rebuilding would
        mean re-scanning the target tick's preceding ``window`` ticks'
        memory diffs on every non-linear jump; clearing is the simplest
        policy that is still correct -- like ``_flash``/``_trail_points``,
        this is presentation-only bookkeeping of what the *viewer* has
        actually observed happen tick-by-tick, not a claim about the
        replay's full history, so "nothing recently observed yet at the
        new position" is an honest, deterministic state, not a gap.
        """
        is_linear_step = (
            self._last_rendered_tick is not None and state.tick == self._last_rendered_tick + 1
        )
        if not is_linear_step:
            self._trail_points.clear()
            self._flash.clear()
            self._recent_changes.clear()

        if is_linear_step and self._last_owners is not None:
            for address, (old, new) in enumerate(zip(self._last_owners, state.owners)):
                if new is not None and new != old:
                    self._recent_changes[address] = state.tick
                    xy = self._to_xy(address)
                    if xy is not None:
                        self._flash[xy] = (PROCESS_FLASH.get(new, DEFAULT_FLASH), FLASH_TTL)

        if self._recent_changes:
            stale = [
                address
                for address, changed_tick in self._recent_changes.items()
                if state.tick - changed_tick > ACTIVITY_WINDOW_TICKS
            ]
            for address in stale:
                del self._recent_changes[address]

        if self.trails_enabled and (is_linear_step or self._last_rendered_tick is None):
            for agent_id, agent in state.agents.items():
                if not agent.alive:
                    continue
                xy = self._vm_marker_xy(state, agent)
                if xy is None:
                    continue
                points = self._trail_points.setdefault(agent_id, [])
                if not points or points[-1] != xy:
                    points.append(xy)
                    del points[:-TRAIL_LENGTH]

        # Fade existing flashes regardless of step linearity.
        expired = []
        for xy, (color, ttl) in self._flash.items():
            ttl -= 1
            if ttl <= 0:
                expired.append(xy)
            else:
                self._flash[xy] = (color, ttl)
        for xy in expired:
            del self._flash[xy]

        self._advance_capture_callout(state)

        self._last_rendered_tick = state.tick
        self._last_owners = state.owners

    def _advance_capture_callout(self, state: ReplayState) -> None:
        """Advance the core-capture callout queue for the newly-current
        ``state`` (v3.0 "fun feature" -- see
        docs/V3_CORE_CAPTURE_CALLOUT.md).

        Captures are filtered through ``_perspective_safe_captures`` (Phase
        8.5) before being queued, so a capture the selected entrant has no
        basis to know about is never queued at all -- it does not flash
        briefly and get hidden by a later check; it is simply never a
        candidate for the queue for that Perspective mode, the same
        filter-before-assembly discipline Fight Night's ribbon already uses.

        Deliberately does **not** reuse ``is_linear_step`` as computed
        above in ``_advance_transient_effects``: that check treats "the
        tick hasn't changed since the last call" (an entirely ordinary
        *paused* frame -- this renderer re-renders at up to 60fps while
        ``state.tick`` sits still) the same as "the tick jumped" --
        harmless for the flash/trail/activity effects above (each is
        already re-derived from scratch on every linear step, and their
        own lifetimes are sub-second regardless), but wrong for a callout
        meant to stay visible, unchanged, across a multi-second *pause*.
        This method instead compares ``state.tick`` against
        ``self._last_rendered_tick`` (still the *previous* call's tick --
        read here before ``_advance_transient_effects`` overwrites it) and
        only ever advances the queue on an exact ``+1`` step: genuine
        continuous forward playback, whether driven by auto-play or a
        single manual step. A delta of exactly ``0`` is a deliberate
        no-op -- the active callout and queue are left exactly as they
        are, so pausing freezes the callout in place for free. Any other
        delta (backward, or a forward jump of more than one tick -- a
        seek, restart, or jump-to-end) clears both: seeking reconstructs
        state without replaying every transient notification, so a
        callout is never shown merely because the playhead crossed an old
        capture tick.

        Multiple entrants captured on the very same tick are already
        bundled into one queue entry by ``core_captures_at_tick`` (see its
        own docstring); this method never splits or drops them.
        """
        last = self._last_rendered_tick
        if last is not None and state.tick == last + 1:
            captures = core_captures_at_tick(self._match_events, state.tick, state.agents)
            if captures:
                selected_entrant_id, is_terminal = self._perspective_card_knowledge_basis(
                    state.tick
                )
                captures = _perspective_safe_captures(
                    captures, selected_entrant_id=selected_entrant_id, is_terminal=is_terminal
                )
            if captures:
                self._capture_callout_queue.append((state.tick, captures))
        elif last is not None and state.tick != last:
            self._capture_callout_queue.clear()
            self._active_capture_callout = None

        if self._active_capture_callout is None and self._capture_callout_queue:
            self._active_capture_callout = self._capture_callout_queue.pop(0)
            self._capture_callout_expires_after_tick = state.tick + CAPTURE_CALLOUT_DURATION_TICKS
        elif (
            self._active_capture_callout is not None
            and state.tick >= self._capture_callout_expires_after_tick
        ):
            self._active_capture_callout = (
                self._capture_callout_queue.pop(0) if self._capture_callout_queue else None
            )
            if self._active_capture_callout is not None:
                self._capture_callout_expires_after_tick = state.tick + CAPTURE_CALLOUT_DURATION_TICKS

    # ---------- drawing ----------

    def _redraw(self, controller: PlaybackController) -> None:
        pg = self.pg
        gs = self.grid_surf
        state = controller.session.current_state

        perspective_state: PerspectiveState | None = None
        if self._perspective_manager is not None and self._perspective_manager.available:
            perspective_state = self._perspective_manager.state_at_tick(state.tick)

        # The window background, visible only where a band doesn't paint
        # over it (e.g. a footer graph panel narrower than its rect) --
        # matches the panel bands' own color rather than the arena's, since
        # it is chrome, not battlefield (Beta1 Phase 4).
        self.screen.fill(PANEL_BG)

        gs.fill(GRID_BG)
        max_dim = max(self.grid_cols, self.grid_rows)
        step = max(1, max_dim // 32)
        for x in range(0, self.grid_cols, step):
            pg.draw.line(gs, GRID_LINE, (x, 0), (x, self.grid_rows - 1))
        for y in range(0, self.grid_rows, step):
            pg.draw.line(gs, GRID_LINE, (0, y), (self.grid_cols - 1, y))

        if perspective_state is None:
            # BROADCAST / OMNISCIENT MODE
            for address, owner in enumerate(state.owners):
                if owner is None:
                    continue
                xy = self._to_xy(address)
                if xy is None:
                    continue
                tint = OWNERSHIP_TINT.get(owner, DEFAULT_TINT)
                gs.set_at(xy, self._blend(GRID_BG, tint, 0.65))

            for address, changed_tick in self._recent_changes.items():
                intensity = activity_intensity(state.tick, changed_tick, ACTIVITY_WINDOW_TICKS)
                if intensity <= 0.0:
                    continue
                xy = self._to_xy(address)
                if xy is None:
                    continue
                current = tuple(gs.get_at(xy))[:3]
                gs.set_at(xy, self._blend(current, ACTIVITY_COLOR, 0.6 * intensity))

            for xy, (color, _ttl) in self._flash.items():
                if 0 <= xy[0] < self.grid_cols and 0 <= xy[1] < self.grid_rows:
                    gs.set_at(xy, color)

            ax, ay, aw, ah = self._arena_rect()
            scaled = pg.transform.scale(gs, (max(1, aw), max(1, ah)))
            self.screen.blit(scaled, (ax, ay))

            if self.trails_enabled:
                for agent_id, points in self._trail_points.items():
                    if len(points) < 2:
                        continue
                    color = self._blend(
                        AGENT_COLORS.get(agent_id, DEFAULT_AGENT_COLOR), (255, 255, 255), 0.25
                    )
                    self._draw_polyline(points[-TRAIL_LENGTH:], color)

            for agent_id, agent in state.agents.items():
                if not agent.alive:
                    continue
                xy = self._vm_marker_xy(state, agent)
                if xy is None:
                    continue
                self._draw_agent_marker(agent_id, xy)

            for process in state.processes.values():
                xy = self._to_xy(process.anchor)
                if xy is not None:
                    self._draw_process_anchor(
                        process.entrant_id,
                        process.process_id,
                        xy,
                        disrupted=process.disrupted,
                    )
        else:
            # ENTRANT PERSPECTIVE MODE (Knowledge-Limited)
            # 1. Own core cells
            if (
                perspective_state.own_core_base is not None
                and perspective_state.own_core_size is not None
            ):
                own_tint = OWNERSHIP_TINT.get(perspective_state.entrant_id, DEFAULT_TINT)
                for offset in range(perspective_state.own_core_size):
                    addr = (perspective_state.own_core_base + offset) % self.arena
                    xy = self._to_xy(addr)
                    if xy is not None:
                        gs.set_at(xy, self._blend(GRID_BG, own_tint, 0.70))

            # 2. Historical delivered READ cell samples
            for read in perspective_state.read_history:
                if read.normalized_address is not None and read.applied:
                    xy = self._to_xy(read.normalized_address)
                    if xy is not None:
                        read_tint = (
                            OWNERSHIP_TINT.get(read.owner, (60, 65, 85))
                            if read.owner
                            else (50, 50, 60)
                        )
                        current_c = tuple(gs.get_at(xy))[:3]
                        gs.set_at(xy, self._blend(current_c, read_tint, 0.45))

            ax, ay, aw, ah = self._arena_rect()
            scaled = pg.transform.scale(gs, (max(1, aw), max(1, ah)))
            self.screen.blit(scaled, (ax, ay))

            # 3. Own process anchors and sensor reach
            for proc in perspective_state.own_processes:
                if proc.anchor is not None:
                    xy = self._to_xy(proc.anchor)
                    if xy is not None:
                        self._draw_sensor_reach(
                            perspective_state.entrant_id, proc.anchor, proc.reach
                        )
                        self._draw_process_anchor(
                            perspective_state.entrant_id,
                            proc.process_id,
                            xy,
                            disrupted=False,
                        )

            # 4. Anonymous CURRENT sensor contacts
            for contact in perspective_state.current_contacts:
                self._draw_perspective_contact(contact.address, KnowledgeStatus.CURRENT)

            # 5. Anonymous STALE sensor contacts
            for contact in perspective_state.stale_contacts:
                age = state.tick - contact.last_observed_at.tick
                self._draw_perspective_contact(contact.address, KnowledgeStatus.STALE, age=age)

            if self._perspective_debug:
                self._draw_perspective_debug_overlay(state, perspective_state)

        if self._perspective_debug:
            director_runtime = self._active_director_runtime()
            if director_runtime is not None:
                self._draw_director_debug_overlay(state, director_runtime)

        self._draw_selection_highlight()
        statuses = self._draw_top_band(controller)
        self._draw_fight_night(controller, statuses)
        self._draw_capture_callout(controller, statuses)
        self._draw_footer(controller)

    def _blend(
        self, a: tuple[int, int, int], b: tuple[int, int, int], alpha: float
    ) -> tuple[int, int, int]:
        return (
            int(a[0] * (1 - alpha) + b[0] * alpha),
            int(a[1] * (1 - alpha) + b[1] * alpha),
            int(a[2] * (1 - alpha) + b[2] * alpha),
        )

    def _draw_perspective_contact(
        self,
        address: int,
        status: KnowledgeStatus,
        *,
        age: int = 0,
    ) -> None:
        """Draw an anonymous sensor contact marker on the arena.

        Never renders opponent identity, process identity, process count, or
        synthetic track ID.
        """
        xy = self._to_xy(address)
        if xy is None:
            return
        sx, sy = self._screen_xy(*xy)
        _ax, _ay, aw, ah = self._arena_rect()
        cell_scale = min(aw / self.grid_cols, ah / self.grid_rows)

        if status == KnowledgeStatus.CURRENT:
            radius = max(3, int(0.65 * cell_scale))
            contact_color = (255, 215, 0)
            self.pg.draw.circle(self.screen, contact_color, (sx, sy), radius, 2)
            self.pg.draw.circle(self.screen, (255, 255, 255), (sx, sy), max(1, radius // 3))
            label = self.hud_font.render("CONTACT", True, contact_color)
            label_w = getattr(label, "get_width", lambda: 0)()
            label_h = getattr(label, "get_height", lambda: 0)()
            self.screen.blit(label, (sx - label_w // 2, sy - radius - 2 - label_h))
        elif status == KnowledgeStatus.STALE:
            radius = max(2, int(0.5 * cell_scale))
            stale_color = (150, 150, 160)
            self.pg.draw.circle(self.screen, stale_color, (sx, sy), radius, 1)
            age_label = self.hud_font.render(f"T-{age}", True, stale_color)
            label_w = getattr(age_label, "get_width", lambda: 0)()
            label_h = getattr(age_label, "get_height", lambda: 0)()
            self.screen.blit(age_label, (sx - label_w // 2, sy - radius - 1 - label_h))

    def _draw_sensor_reach(
        self,
        entrant_id: str,
        anchor: int,
        reach: int,
    ) -> None:
        """Draw sensor reach boundary around an observed anchor."""
        xy = self._to_xy(anchor)
        if xy is None:
            return
        sx, sy = self._screen_xy(*xy)
        _ax, _ay, aw, ah = self._arena_rect()
        cell_scale = min(aw / self.grid_cols, ah / self.grid_rows)
        reach_px = max(1, int(reach * cell_scale))
        reach_surf = self.pg.Surface((reach_px * 2 + 4, reach_px * 2 + 4), flags=self.pg.SRCALPHA)
        agent_color = AGENT_COLORS.get(entrant_id, DEFAULT_AGENT_COLOR)
        reach_color = (*agent_color, 45)
        self.pg.draw.circle(reach_surf, reach_color, (reach_px + 2, reach_px + 2), reach_px, 1)
        self.screen.blit(reach_surf, (sx - reach_px - 2, sy - reach_px - 2))

    def _draw_perspective_debug_overlay(
        self, state: ReplayState, perspective_state: PerspectiveState
    ) -> None:
        """Draw diagnostic debug overlay for perspective qualification."""
        ax, ay, aw, _ah = self._arena_rect()
        overlay_w = min(460, max(280, aw - 40))
        last_pt = perspective_state.last_visibility_sample_at
        last_pt_str = (
            f"T{last_pt.tick} (D{last_pt.decision_index}, {last_pt.process_id})"
            if last_pt is not None
            else "never"
        )
        lines = [
            f"PERSPECTIVE DEBUG: Entrant {perspective_state.entrant_id}",
            f"Tick: {state.tick} (Boundary: {perspective_state.boundary.value})",
            f"Sampled this tick: {'yes' if perspective_state.sampled_this_tick else 'no'}",
            f"Latest visibility sample: {last_pt_str}",
            f"Current contacts ({len(perspective_state.current_contacts)}): {[c.address for c in perspective_state.current_contacts]}",
            f"Stale contacts ({len(perspective_state.stale_contacts)}): {[c.address for c in perspective_state.stale_contacts]}",
            f"Delivered READs: {len(perspective_state.read_history)}",
            f"Own processes: {len(perspective_state.own_processes)}",
        ]
        padding = 8
        line_height = 16
        overlay_h = padding * 2 + len(lines) * line_height
        overlay_surf = self.pg.Surface((overlay_w, overlay_h), flags=self.pg.SRCALPHA)
        overlay_surf.fill((12, 14, 20, 230))
        self.pg.draw.rect(overlay_surf, (80, 150, 240), overlay_surf.get_rect(), 1)
        for idx, line in enumerate(lines):
            color = (255, 220, 100) if idx == 0 else TEXT_COLOR
            rendered = self.hud_font.render(
                truncate_with_ellipsis(line, (overlay_w - 2 * padding) // HUD_CHAR_WIDTH_PX),
                True,
                color,
            )
            overlay_surf.blit(rendered, (padding, padding + idx * line_height))
        self.screen.blit(overlay_surf, (ax + 10, ay + 10))

    def _draw_director_debug_overlay(
        self, state: ReplayState, director_runtime: PlaybackDirectorRuntime
    ) -> None:
        """Developer-only Director diagnostics (Phase 7 brief Sec. 24).

        Anchored to the arena's top-right corner rather than the top-left
        used by ``_draw_perspective_debug_overlay`` so the two never overlap
        when both are visible at once (Perspective Cam + Director, both
        gated by the same F3/D toggle). Source event identities are shown as
        bare ``(tick, sequence)`` pairs -- developer-only detail, not the
        restrained on-screen indicator in the footer -- and never resolve to
        the underlying event's actual field content, so this overlay cannot
        itself become a second, undisclosed presentation path for omniscient
        facts in Perspective mode.
        """
        decision = director_runtime.decision_for_tick(state.tick)
        ax, ay, aw, _ah = self._arena_rect()
        overlay_w = min(360, max(240, aw - 40))
        if decision.hold_ms > 0:
            rate_line = f"Hold: {decision.hold_ms}ms (remaining {director_runtime.hold_remaining_ms(state.tick):.0f}ms)"
        else:
            rate_line = f"Rate: {decision.rate_tps:g} TPS"
        lines = [
            f"DIRECTOR DEBUG: {decision.visibility_basis}",
            f"Tick: {decision.tick}  State: {decision.state.value}",
            rate_line,
            f"Reason: {decision.reason.value}",
            f"Boundary: {'yes' if decision.boundary else 'no'}",
            f"Source events: {list(decision.source_events)}",
        ]
        padding = 8
        line_height = 16
        overlay_h = padding * 2 + len(lines) * line_height
        overlay_surf = self.pg.Surface((overlay_w, overlay_h), flags=self.pg.SRCALPHA)
        overlay_surf.fill((12, 14, 20, 230))
        self.pg.draw.rect(overlay_surf, (240, 150, 80), overlay_surf.get_rect(), 1)
        for idx, line in enumerate(lines):
            color = (255, 220, 100) if idx == 0 else TEXT_COLOR
            rendered = self.hud_font.render(
                truncate_with_ellipsis(line, (overlay_w - 2 * padding) // HUD_CHAR_WIDTH_PX),
                True,
                color,
            )
            overlay_surf.blit(rendered, (padding, padding + idx * line_height))
        self.screen.blit(overlay_surf, (ax + aw - overlay_w - 10, ay + 10))

    def _draw_agent_marker(self, agent_id: str, pos: tuple[int, int]) -> None:
        color = AGENT_COLORS.get(agent_id, DEFAULT_AGENT_COLOR)
        x, y = pos
        sx, sy = self._screen_xy(x, y)
        _ax, _ay, aw, ah = self._arena_rect()
        cell_scale = min(aw / self.grid_cols, ah / self.grid_rows)
        r = max(3, int(0.7 * cell_scale))
        self.pg.draw.circle(self.screen, color, (sx, sy), r)
        self.pg.draw.circle(self.screen, (0, 0, 0), (sx, sy), r, 1)
        label = self.font.render(agent_id, True, (255, 255, 255))
        self.screen.blit(label, label.get_rect(center=(sx, sy - r - 8)))

    def _draw_process_anchor(
        self,
        entrant_id: str,
        process_id: str,
        pos: tuple[int, int],
        *,
        disrupted: bool,
    ) -> None:
        """Draw a small labeled ring for one recorded v4 process anchor."""

        color = AGENT_COLORS.get(entrant_id, DEFAULT_AGENT_COLOR)
        if disrupted:
            color = self._blend(color, (110, 110, 110), 0.65)
        sx, sy = self._screen_xy(*pos)
        _ax, _ay, aw, ah = self._arena_rect()
        cell_scale = min(aw / self.grid_cols, ah / self.grid_rows)
        radius = max(2, int(0.45 * cell_scale))
        self.pg.draw.circle(self.screen, color, (sx, sy), radius, 2)
        if disrupted:
            self.pg.draw.line(
                self.screen,
                color,
                (sx - radius, sy - radius),
                (sx + radius, sy + radius),
                1,
            )
        label = self.font.render(process_id, True, color)
        self.screen.blit(label, label.get_rect(midtop=(sx, sy + radius + 1)))

    def _draw_selection_highlight(self) -> None:
        """Outline the selected cell (if any and if on-screen) in
        ``SELECTION_COLOR``. A no-op if nothing is selected.
        """
        if self._selected_address is None:
            return
        xy = self._to_xy(self._selected_address)
        if xy is None:
            return
        x, y = xy
        ax, ay, aw, ah = self._arena_rect()
        cell_w = aw / self.grid_cols
        cell_h = ah / self.grid_rows
        rect = self.pg.Rect(
            int(ax + x * cell_w),
            int(ay + y * cell_h),
            max(1, math.ceil(cell_w)),
            max(1, math.ceil(cell_h)),
        )
        self.pg.draw.rect(self.screen, SELECTION_COLOR, rect, 2)

    def _draw_timeline(self, controller: PlaybackController) -> None:
        """Draw the footer's whole-match timeline: an elapsed-progress track
        across every recorded tick, a mark at each tick that recorded an
        event, and the playhead at the current tick.

        Complements, rather than repeats, the two things already in the
        footer. The territory graph beside it plots a *trailing window* of
        ownership; this plots the *whole match* and is the only control that
        can reach an arbitrary tick. The core-capture callout announces a
        capture as playback passes it; this shows where that moment sits so
        it can be returned to afterwards.

        Reads only ``self._timeline_marks`` (derived once in ``run()``) and
        the session's own first/final recorded ticks -- no replay
        reconstruction, no per-frame event scan. A no-op whenever no layout
        has been computed yet (a unit test that never called ``run()``) or
        the footer was too short for a timeline rect at all (see
        ``hud_layout.calculate_layout``'s ``show_timeline``).
        """
        layout = self._layout
        if layout is None:
            return
        rect = layout.footer_timeline_rect
        tx, ty, tw, th = rect
        if tw <= 0 or th <= 0:
            return
        session = controller.session
        recorded = session.recorded_ticks
        if not recorded:
            return
        first_tick, final_tick = recorded[0], recorded[-1]
        current_tick = session.current_state.tick

        self.pg.draw.rect(self.screen, TIMELINE_TRACK_COLOR, self.pg.Rect(tx, ty, tw, th))

        playhead_x = timeline_x_for_tick(current_tick, first_tick, final_tick, rect)
        elapsed_w = max(0, playhead_x - tx)
        if elapsed_w > 0:
            self.pg.draw.rect(
                self.screen, TIMELINE_ELAPSED_COLOR, self.pg.Rect(tx, ty, elapsed_w, th)
            )

        # Drawn above the elapsed fill but below the playhead: where the two
        # are merely close, the mark stays readable beside the playhead;
        # where they resolve to the same pixel, the playhead wins, which is
        # the right precedence for the only element that moves.
        mark_y = ty + (th - TIMELINE_MARK_HEIGHT) // 2
        for mark_tick, agent_id in self._timeline_marks:
            color = (
                AGENT_COLORS.get(agent_id, DEFAULT_AGENT_COLOR)
                if agent_id is not None
                else DEFAULT_AGENT_COLOR
            )
            # timeline_x_for_tick returns the mark's left edge, so a mark on
            # the final tick would otherwise start at the last pixel of the
            # track and finish just past it. Clamped by its own width, the
            # last mark ends flush with the track instead.
            mark_x = min(
                timeline_x_for_tick(mark_tick, first_tick, final_tick, rect),
                tx + tw - TIMELINE_MARK_WIDTH,
            )
            self.pg.draw.rect(
                self.screen,
                color,
                self.pg.Rect(mark_x, mark_y, TIMELINE_MARK_WIDTH, TIMELINE_MARK_HEIGHT),
            )

        self.pg.draw.rect(
            self.screen, TIMELINE_TRACK_BORDER, self.pg.Rect(tx, ty, tw, th), 1
        )
        # Clamped by its own width for the same reason as the marks above:
        # the playhead at the final tick reads as "at the end" rather than
        # spilling one pixel past the track.
        head_x = min(playhead_x, tx + tw - 2)
        self.pg.draw.rect(
            self.screen, TIMELINE_PLAYHEAD_COLOR, self.pg.Rect(head_x, ty - 1, 2, th + 2)
        )

    def _timeline_seek(self, controller: PlaybackController, pos: tuple[int, int]) -> bool:
        """Seek to the tick a click/drag at ``pos`` selects on the timeline.

        Returns whether ``pos`` was on the track at all, so a caller can tell
        "handled here" from "try the next hit target". The requested tick is
        snapped to a genuinely recorded one before seeking (see
        ``battle_client.analysis.nearest_recorded_tick``) -- ``ReplaySession.
        seek`` rejects a tick that falls in a sparse legacy replay's gap, and
        an arbitrary pixel position can land in one.

        Playback is paused first, matching every other navigation command in
        ``PlaybackController`` (see its class docstring): a manual seek while
        auto-playing would otherwise be overridden by the next ``update()``.
        A seek that resolves to the tick already on screen is skipped, so
        holding the mouse still during a drag costs nothing.
        """
        layout = self._layout
        if layout is None:
            return False
        rect = layout.footer_timeline_rect
        if not timeline_contains(rect, pos):
            return False
        session = controller.session
        recorded = session.recorded_ticks
        if not recorded:
            return False
        requested = timeline_tick_for_x(pos[0], recorded[0], recorded[-1], rect)
        if requested is None:
            return False
        target = nearest_recorded_tick(recorded, requested)
        controller.pause()
        if target is not None and target != session.current_tick:
            session.seek(target)
        return True

    def _draw_footer_graph(self, state: ReplayState, rect: tuple[int, int, int, int]) -> None:
        """Draw the compact territory-history trend panel at ``rect``
        (the footer band's own graph rect -- see ``battle_client.
        hud_layout.calculate_layout``'s ``footer_graph_rect``): one
        polyline per agent, its owned-cell percentage over a trailing
        window of ticks ending at the current tick.

        Relocated off the arena in Beta1 Phase 4 (previously an overlay
        floating in the arena's own bottom-right corner -- see
        docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md §3): the graph is a trend over
        time, not tied to any specific arena cell, so it belongs in the
        HUD, not the battlefield. Reads only ``self._territory_history``
        (precomputed once in ``run()`` -- see ``compute_territory_
        history``); no replay reconstruction happens here, only windowing/
        downsampling/coordinate math (``select_history_window``/
        ``downsample_series``/``territory_graph_points``), all pure and
        cheap. A no-op if no history was computed, or if ``rect`` is
        degenerate (zero-size -- narrow windows omit the graph entirely,
        see ``hud_layout.FOOTER_GRAPH_MIN_WINDOW_WIDTH``).
        """
        history = self._territory_history
        panel_x, panel_y, panel_w, panel_h = rect
        if not history.ticks or panel_w <= 0 or panel_h <= 0:
            return

        # Local (panel-surface) coordinates -- the plot area, inset from the
        # panel's own border, leaving a bottom strip for the legend labels.
        local_plot_rect = (4, 4, max(1, panel_w - 8), max(1, panel_h - 20))

        panel = self.pg.Surface((panel_w, panel_h), flags=self.pg.SRCALPHA)
        panel.fill((0, 0, 0, 90))
        self.pg.draw.rect(panel, (90, 90, 90, 255), panel.get_rect(), 1)

        legend_x = local_plot_rect[0]
        for agent_id in sorted(history.percentages):
            ticks, values = select_history_window(
                history.ticks,
                history.percentages[agent_id],
                state.tick,
                TERRITORY_HISTORY_WINDOW_TICKS,
            )
            ticks, values = downsample_series(ticks, values, TERRITORY_GRAPH_MAX_POINTS)
            points = territory_graph_points(ticks, values, local_plot_rect)
            color = AGENT_COLORS.get(agent_id, DEFAULT_AGENT_COLOR)
            if len(points) >= 2:
                self.pg.draw.lines(panel, color, False, points, 1)
            current_pct = values[-1] if values else 0.0
            label = self.hud_font.render(f"{agent_id} {current_pct:.0f}%", True, color)
            panel.blit(label, (legend_x, panel_h - 14))
            legend_x += label.get_width() + 10

        self.screen.blit(panel, (panel_x, panel_y))

    def _draw_polyline(self, points: list[tuple[int, int]], color: tuple[int, int, int]) -> None:
        screen_points = [self._screen_xy(x, y) for (x, y) in points]
        _ax, _ay, aw, ah = self._arena_rect()
        width = max(1, min(aw, ah) // max(self.grid_cols, self.grid_rows) // 3)
        self.pg.draw.lines(self.screen, color, False, screen_points, width)

    def _selected_cell_info(self, state: ReplayState) -> SelectedCellInfo | None:
        """The current (domain-only) ``SelectedCellInfo`` for
        ``self._selected_address``, or ``None`` if nothing is selected.

        Whether that address was "recently changed" is renderer-local
        presentation state, not part of this domain fact -- see
        ``_selected_recently_changed``.
        """
        if self._selected_address is None:
            return None
        return selected_cell_info(state, self._selected_address)

    def _selected_recently_changed(self) -> bool:
        """Whether ``self._selected_address`` was flashed by the most
        recent linear step.

        Sourced from ``self._flash`` -- the renderer's existing per-address
        ownership-change bookkeeping (see ``_advance_transient_effects``),
        which only ever fires on a genuine ownership change on the
        immediately preceding *linear* step and is cleared on any
        seek/restart. Reusing it here, rather than inventing separate
        "last write" tracking, keeps the signal honest: it reflects an
        owner change, not literally every write. This is deliberately kept
        out of ``battle_client.analysis.SelectedCellInfo`` -- see
        ``docs/specs/replay_analysis.md`` §6.
        """
        if self._selected_address is None:
            return False
        xy = self._to_xy(self._selected_address)
        return xy is not None and xy in self._flash

    def _draw_top_band(
        self, controller: PlaybackController
    ) -> tuple[EntrantReplayStatus, ...]:
        """Draw the top HUD band: the match-identity header and one status
        card per entrant. Returns the entrant statuses just drawn (empty
        if no layout has been computed yet), so a caller that also needs
        per-entrant display names this frame -- e.g. ``_draw_capture_
        callout`` -- doesn't have to re-derive them with a second
        ``get_entrant_statuses`` call.

        Entrant status comes entirely from ``battle_client.replay_status.
        get_entrant_statuses`` (the Phase-3 status model) -- this method
        never inspects raw replay structures, ownership, or Ruleset
        identity itself (see the governing architectural rule in
        docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md). A no-op if no layout has
        been computed yet (a unit test that never called ``run()``).
        """
        layout = self._layout
        if layout is None:
            return ()
        session = controller.session
        state = session.current_state

        band_height = layout.top_band_height
        band_rect = self.pg.Rect(0, 0, layout.window_size[0], band_height)
        self.pg.draw.rect(self.screen, PANEL_BG, band_rect)
        if band_height > 0:
            self.pg.draw.line(
                self.screen,
                PANEL_BORDER,
                (0, band_height - 1),
                (layout.window_size[0], band_height - 1),
            )

        statuses = get_entrant_statuses(session, state=state, match_events=self._match_events)

        hx, hy, hw, _hh = layout.header_rect
        icon_reserved = 0
        if self._header_icon is not None:
            icon_reserved = HEADER_ICON_SIZE + HEADER_ICON_GAP
            icon_y = hy + (HEADER_LINES * HEADER_LINE_HEIGHT - HEADER_ICON_SIZE) // 2
            self.screen.blit(self._header_icon, (hx + 6, icon_y))
        text_x = hx + 6 + icon_reserved

        view_label: str | None = None
        if self._perspective_manager is not None and self._perspective_manager.available:
            if self._perspective_manager.mode == BROADCAST_MODE:
                view_label = "View: BROADCAST [V to switch]"
            else:
                ent_id = self._perspective_manager.mode
                ent_name = next((s.name for s in statuses if s.agent_id == ent_id), ent_id)
                view_label = f"View: ENTRANT {ent_id} ({ent_name}) · PERSPECTIVE CAM"
        elif self._perspective_manager is not None and not self._perspective_manager.available:
            view_label = "View: BROADCAST (No Perspective)"

        header_lines = format_match_header_lines(
            ruleset_label=self._ruleset_label,
            runtime_kind=state.runtime_kind or "unknown",
            arena_size=self.arena,
            entrant_count=len(statuses),
            winner=session.winner,
            termination_reason=session.termination_reason,
            result_available=session.result is not None,
            view_label=view_label,
        )
        header_max_chars = max(6, (hw - 6 - icon_reserved) // HUD_CHAR_WIDTH_PX)
        for index, text in enumerate(header_lines):
            if not text:
                continue
            color = TERMINAL_TEXT_COLOR if index == 1 and session.result is not None else TEXT_COLOR
            rendered = self.hud_font.render(
                truncate_with_ellipsis(text, header_max_chars), True, color
            )
            line_y = hy + index * HEADER_LINE_HEIGHT
            if line_y + HEADER_LINE_HEIGHT <= hy + layout.header_rect[3]:
                self.screen.blit(rendered, (text_x, line_y))

        selected_entrant_id, is_terminal = self._perspective_card_knowledge_basis(state.tick)
        for ordinal, (status, rect) in enumerate(
            zip(statuses, layout.entrant_card_rects), start=1
        ):
            known = entrant_card_known(
                status, selected_entrant_id=selected_entrant_id, is_terminal=is_terminal
            )
            self._draw_entrant_card(status, rect, ordinal=ordinal, mode=layout.card_mode, known=known)

        return statuses

    def _perspective_card_knowledge_basis(self, tick: int) -> tuple[str | None, bool]:
        """``(selected_entrant_id, is_terminal)`` for ``entrant_card_known``.

        ``selected_entrant_id`` is ``None`` in Broadcast (or whenever no
        Perspective is active), matching ``entrant_card_known``'s own
        "nothing hidden" case. ``is_terminal`` reuses ``SpectatorDerivation.
        result_ticks`` -- the same match-over boundary already computed by
        ``DirectorManager`` (Phase 7) and ``FightNightManager.state_at_tick``
        (Phase 8) -- rather than a third independent terminal check; it is
        conservatively ``False`` whenever a derivation isn't available (a
        Perspective mode cannot actually be entered without one, so this
        only matters for defensive robustness, never live behavior).
        """
        if self._perspective_manager is None or not self._perspective_manager.available:
            return None, False
        mode = self._perspective_manager.mode
        if mode == BROADCAST_MODE:
            return None, False
        derivation = self._perspective_manager.derivation
        is_terminal = derivation is not None and tick >= derivation.result_ticks
        return mode, is_terminal

    # ---------- Fight Night presentation (Phase 8) ----------

    def _active_fight_night_state(self, tick: int) -> FightNightState | None:
        """This frame's Fight Night state for the selected view mode.

        Keyed on ``PerspectiveManager.mode`` exactly like
        ``_active_director_runtime``, so Broadcast and each entrant's
        Perspective consume separately-built plans. In an entrant's
        Perspective that plan was assembled from *only* that entrant's
        visible events, so a hidden fact is absent from the ribbon
        structurally -- it was never in the list the plan was built from --
        rather than being drawn and then skipped here.
        """

        if not self._fight_night_enabled or self._fight_night_manager is None:
            return None
        mode_key = (
            self._perspective_manager.mode
            if self._perspective_manager is not None
            else BROADCAST_MODE
        )
        return self._fight_night_manager.state_at_tick(mode_key, tick)

    def _draw_fight_night(
        self, controller: PlaybackController, statuses: Sequence[EntrantReplayStatus]
    ) -> None:
        """Draw the Fight Night ribbon and opening/result cards.

        Drawn as overlays inside the already-computed arena viewport, after
        the top band and before the footer, reserving no layout space of its
        own -- ``self._layout`` is never consulted for a Fight Night band
        because there isn't one (see ``hud_layout``'s Fight Night section for
        why a reserved band would break the four-entrant 640x480 grid). A
        no-op whenever Fight Night is disabled, unavailable, or no layout has
        been computed yet.

        ``statuses`` (this frame's already-computed status tuple from
        ``_draw_top_band``) supplies display names and the alive set, so this
        method never issues a second ``get_entrant_statuses`` call and never
        derives liveness itself.
        """

        layout = self._layout
        if layout is None:
            return
        state = self._active_fight_night_state(controller.session.current_state.tick)
        if state is None:
            return

        names = {status.agent_id: status.name for status in statuses}
        viewport = layout.arena_viewport_rect

        if state.phase is FightNightPhase.OPENING:
            self._draw_fight_night_card(
                viewport,
                format_fight_night_opening_lines(
                    state.entrants,
                    names,
                    ruleset_label=self._ruleset_label,
                    max_chars=self._fight_night_card_chars(viewport),
                ),
                accent=TERMINAL_TEXT_COLOR,
            )
        elif state.phase is FightNightPhase.RESULT:
            self._draw_fight_night_card(
                viewport,
                format_fight_night_result_lines(
                    winner=state.winner,
                    termination_reason=state.termination_reason,
                    result_ticks=state.result_ticks,
                    survivors=tuple(s.agent_id for s in statuses if s.alive),
                    names=names,
                    max_chars=self._fight_night_card_chars(viewport),
                ),
                accent=TERMINAL_TEXT_COLOR,
            )

        self._draw_fight_night_ribbon(viewport, layout.arena_rect, state)

    def _fight_night_card_chars(self, viewport: tuple[int, int, int, int]) -> int:
        rect = fight_night_card_rect(viewport, 1)
        return max(6, (rect[2] - 2 * FIGHT_NIGHT_PADDING) // HUD_CHAR_WIDTH_PX)

    def _draw_fight_night_ribbon(
        self,
        viewport: tuple[int, int, int, int],
        arena_rect: tuple[int, int, int, int],
        state: FightNightState,
    ) -> None:
        """The recent-events ribbon, anchored to the arena band's lower-left.

        The title line always names the ribbon's information domain
        (``BROADCAST`` or ``<entrant> KNOWS``), so a viewer never has to
        infer whether they are reading canonical facts or the selected
        entrant's own knowledge -- the Phase 8 brief's Sec. 18 "no ambiguous
        middle state" requirement, answered on screen rather than only in
        documentation.

        Entry text is drawn in the ribbon's own single accent color, never in
        the subject entrant's palette color. Coloring an entry by entrant
        would create exactly the identity association Sec. 27/37 forbid: an
        anonymous contact and a colored ribbon entry appearing together would
        let a viewer join the two.
        """

        capacity = fight_night_ribbon_capacity(viewport, len(state.ribbon))
        if capacity <= 0:
            return
        entries = state.ribbon[-capacity:]
        # The real arena rect (not the viewport) is passed so the ribbon can
        # take the letterbox column beside the battlefield instead of sitting
        # on top of it whenever one is wide enough.
        rect = fight_night_ribbon_rect(viewport, len(entries), arena_rect)
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            return

        panel = self.pg.Surface((width, height), flags=self.pg.SRCALPHA)
        panel.fill((*FIGHT_NIGHT_BG, FIGHT_NIGHT_PANEL_ALPHA))
        self.pg.draw.rect(panel, FIGHT_NIGHT_BORDER, panel.get_rect(), 1)

        max_chars = max(6, (width - 2 * FIGHT_NIGHT_PADDING) // HUD_CHAR_WIDTH_PX)
        title = truncate_with_ellipsis(
            format_fight_night_ribbon_title(state.visibility_basis), max_chars
        )
        panel.blit(
            self.hud_font.render(title, True, FIGHT_NIGHT_TITLE_COLOR),
            (FIGHT_NIGHT_PADDING, FIGHT_NIGHT_PADDING),
        )
        for index, entry in enumerate(entries, start=1):
            text = format_fight_night_ribbon_line(
                entry.label, entry.subject, entry.tick, max_chars=max_chars
            )
            panel.blit(
                self.hud_font.render(text, True, FIGHT_NIGHT_ENTRY_COLOR),
                (FIGHT_NIGHT_PADDING, FIGHT_NIGHT_PADDING + index * FIGHT_NIGHT_LINE_HEIGHT),
            )
        self.screen.blit(panel, (x, y))

    def _draw_fight_night_card(
        self,
        viewport: tuple[int, int, int, int],
        lines: Sequence[str],
        *,
        accent: tuple[int, int, int],
    ) -> None:
        """One centered opening/result card. Shown only outside live play."""

        rect = fight_night_card_rect(viewport, len(lines))
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            return
        panel = self.pg.Surface((width, height), flags=self.pg.SRCALPHA)
        panel.fill((*FIGHT_NIGHT_BG, FIGHT_NIGHT_CARD_ALPHA))
        self.pg.draw.rect(panel, accent, panel.get_rect(), 2)
        max_chars = max(6, (width - 2 * FIGHT_NIGHT_PADDING) // HUD_CHAR_WIDTH_PX)
        for index, line in enumerate(lines):
            line_y = FIGHT_NIGHT_PADDING + index * FIGHT_NIGHT_LINE_HEIGHT
            if line_y + FIGHT_NIGHT_LINE_HEIGHT > height:
                break
            if not line:
                continue
            color = accent if index == 0 else TEXT_COLOR
            rendered = self.hud_font.render(
                truncate_with_ellipsis(line, max_chars), True, color
            )
            panel.blit(rendered, ((width - rendered.get_width()) // 2, line_y))
        self.screen.blit(panel, (x, y))

    def _draw_capture_callout(
        self, controller: PlaybackController, statuses: Sequence[EntrantReplayStatus]
    ) -> None:
        """Draw the active core-capture callout, if any (v3.0 "fun
        feature" -- see docs/V3_CORE_CAPTURE_CALLOUT.md): a small bordered
        banner centered in the top HUD band.

        Drawn last, after ``_draw_top_band``, so it overlays part of the
        entrant-card row for its brief, tick-bounded lifetime rather than
        reserving permanent layout space -- ``self._layout`` itself is
        never touched, so nothing else about the HUD/arena/footer tiling
        changes. Sized and positioned to stay strictly inside
        ``layout.top_band_height`` (never past it), so the arena band
        below is never obscured, by construction rather than convention.
        A no-op whenever no callout is active, no layout has been
        computed yet, or the top band is too short to fit even a minimal
        box (never the case at the supported 640x480 minimum -- see
        docs/V3_CORE_CAPTURE_CALLOUT.md's minimum-viewport evidence).

        ``statuses`` (this frame's already-computed
        ``EntrantReplayStatus`` tuple from ``_draw_top_band``) supplies
        display names for attribution text, so this method never issues
        its own second ``get_entrant_statuses`` call.
        """
        layout = self._layout
        if layout is None or self._active_capture_callout is None:
            return
        capture_tick, captures = self._active_capture_callout
        current_tick = controller.session.current_state.tick

        names = {status.agent_id: status.name for status in statuses}
        lines = format_core_capture_callout_lines(captures, names)

        window_w = layout.window_size[0]
        box_w = max(1, min(CAPTURE_CALLOUT_MAX_WIDTH, window_w - CAPTURE_CALLOUT_MARGIN))
        padding = 8
        content_h = padding * 2 + len(lines) * CARD_LINE_HEIGHT
        box_h = min(content_h, max(0, layout.top_band_height - 8))
        if box_h <= 0:
            return

        alpha = capture_callout_alpha(
            current_tick - capture_tick, CAPTURE_CALLOUT_DURATION_TICKS, CAPTURE_CALLOUT_FADE_TICKS
        )
        if alpha <= 0.0:
            return

        box_x = (window_w - box_w) // 2
        box_y = max(0, (layout.top_band_height - box_h) // 2)

        # Full opacity at the envelope's own peak (alpha == 1.0), not a
        # permanently translucent panel: this callout is drawn on top of
        # already-rendered entrant-card text (see this method's own
        # docstring), and anything less than fully opaque at the hold
        # phase lets that text show through in the gaps between this
        # panel's own glyphs, muddling both. Only the brief fade in/out
        # itself is genuinely translucent.
        panel = self.pg.Surface((box_w, box_h), flags=self.pg.SRCALPHA)
        panel.fill((*CAPTURE_CALLOUT_BG, int(255 * alpha)))
        self.pg.draw.rect(panel, STATUS_CAPTURED_COLOR, panel.get_rect(), 2)

        max_chars = max(6, (box_w - 2 * padding) // HUD_CHAR_WIDTH_PX)
        for index, text in enumerate(lines):
            if (index + 1) * CARD_LINE_HEIGHT > box_h - padding:
                break
            color = STATUS_CAPTURED_COLOR if index == 0 else TEXT_COLOR
            rendered = self.hud_font.render(truncate_with_ellipsis(text, max_chars), True, color)
            panel.blit(rendered, (padding, padding + index * CARD_LINE_HEIGHT))

        self.screen.blit(panel, (box_x, box_y))

    def _draw_entrant_card(
        self,
        status: EntrantReplayStatus,
        rect: tuple[int, int, int, int],
        *,
        ordinal: int,
        mode: CardMode,
        known: bool = True,
    ) -> None:
        """One entrant's responsive status card, entirely
        formatted by ``battle_client.hud_layout.format_entrant_card_lines``
        -- this method only chooses colors and blit positions.

        ``known`` (Phase 8.5, computed once per entrant per frame by
        ``_perspective_card_knowledge_basis`` + ``hud_layout.
        entrant_card_known``) governs both the text (threaded into
        ``format_entrant_card_lines``) and the status color: a card whose
        real life state is not known to the selected entrant is colored
        ``STATUS_UNKNOWN_COLOR`` rather than the real alive/dead/captured
        color, so the hidden fact cannot leak through styling alone even if
        a future caller ever draws the color without the text.
        """
        cx, cy, cw, ch = rect
        if cw <= 0 or ch <= 0:
            return
        max_chars = max(6, cw // HUD_CHAR_WIDTH_PX)
        lines = format_entrant_card_lines(
            status,
            max_chars=max_chars,
            ordinal=ordinal,
            mode="compact" if mode == "compact" else "detailed",
            known=known,
        )

        if not known:
            status_color = STATUS_UNKNOWN_COLOR
        elif status.core is not None and status.core.captured:
            status_color = STATUS_CAPTURED_COLOR
        elif status.alive:
            status_color = STATUS_ALIVE_COLOR
        else:
            status_color = STATUS_DEAD_COLOR
        name_color = AGENT_COLORS.get(status.agent_id, DEFAULT_AGENT_COLOR)

        colors = (
            (name_color, status_color, DIM_TEXT_COLOR)
            if mode == "detailed"
            else (name_color, status_color)
        )
        for index, (text, color) in enumerate(zip(lines, colors)):
            if (index + 1) * CARD_LINE_HEIGHT > ch:
                break
            rendered = self.hud_font.render(text, True, color)
            self.screen.blit(rendered, (cx, cy + index * CARD_LINE_HEIGHT))

    def _draw_footer(self, controller: PlaybackController) -> None:
        """Draw the bottom footer band: the whole-match timeline,
        tick/playback/speed, one compact status/event message,
        controls/help, and the territory-history graph.

        Also updates ``self._event_panel_*`` (read by ``_handle_click``) to
        reflect whether the status/event message line drawn this frame is
        currently showing a clickable event -- cleared whenever it is
        instead showing the selected-cell inspector or the idle message,
        neither of which seeks anywhere on click.
        """
        layout = self._layout
        if layout is None:
            return
        session = controller.session
        state = session.current_state

        perspective_state: PerspectiveState | None = None
        if self._perspective_manager is not None and self._perspective_manager.available:
            perspective_state = self._perspective_manager.state_at_tick(state.tick)

        footer_y = layout.window_size[1] - layout.footer_height
        band_rect = self.pg.Rect(0, footer_y, layout.window_size[0], layout.footer_height)
        self.pg.draw.rect(self.screen, PANEL_BG, band_rect)
        self.pg.draw.line(self.screen, PANEL_BORDER, (0, footer_y), (layout.window_size[0], footer_y))
        self._draw_timeline(controller)

        tx, ty, tw, text_h = layout.footer_text_rect
        status_label = "PLAYING" if controller.playing else "PAUSED"
        if session.at_end and not controller.playing:
            status_label = "PAUSED (end)"

        # Restrained by design (Sec. 22/23): shown only while Director is
        # actually active, so a trace-backed replay with Director available
        # but off (the default) looks exactly like ordinary replay.
        director_label: str | None = None
        director_runtime = self._active_director_runtime()
        if director_runtime is not None:
            decision = director_runtime.decision_for_tick(state.tick)
            if decision.hold_ms > 0:
                remaining = director_runtime.hold_remaining_ms(state.tick)
                director_label = f"DIRECTOR {decision.state.value} HOLD {remaining:.0f}ms"
            else:
                director_label = f"DIRECTOR {decision.state.value} {decision.rate_tps:g}tps"

        line1 = format_playback_line(
            tick=state.tick,
            final_tick=session.final_tick,
            status_label=status_label,
            speed=controller.speed,
            director_label=director_label,
        )

        selected = self._selected_cell_info(state)
        recent = events_near_tick(self._match_events, state.tick, window=1)
        if selected is not None:
            if perspective_state is not None:
                addr = selected.address
                contact = next(
                    (c for c in perspective_state.current_contacts if c.address == addr),
                    None,
                )
                stale = next(
                    (c for c in perspective_state.stale_contacts if c.address == addr),
                    None,
                )
                matching_reads = [
                    r for r in perspective_state.read_history if r.normalized_address == addr
                ]
                if contact is not None:
                    desc = (
                        f"[CURRENT CONTACT] (first T{contact.first_observed_at.tick}, "
                        f"last T{contact.last_observed_at.tick}, count={contact.observation_count})"
                    )
                elif stale is not None:
                    age = state.tick - stale.last_observed_at.tick
                    staled_t = (
                        f"T{stale.became_stale_at.tick}"
                        if stale.became_stale_at is not None
                        else "?"
                    )
                    desc = (
                        f"[STALE CONTACT] (last confirmed T{stale.last_observed_at.tick}, "
                        f"staled {staled_t}, age={age}t)"
                    )
                elif matching_reads:
                    latest_read = matching_reads[-1]
                    val_str = (
                        f"0x{latest_read.value:02x}"
                        if latest_read.value is not None
                        else "?"
                    )
                    owner_str = (
                        latest_read.owner
                        if latest_read.owner is not None
                        else "none"
                    )
                    desc = (
                        f"[DELIVERED READ] byte={val_str}  cell_owner={owner_str} "
                        f"(sampled T{latest_read.sampled_at.tick} by {latest_read.process_id}, "
                        f"delivered T{latest_read.delivered_at.tick})"
                    )
                else:
                    desc = "[UNKNOWN / UNSAMPLED]"
                line2 = f"Selected cell:   addr={addr}  {desc}"
            else:
                inspector = format_inspector_lines(
                    selected, recently_changed=self._selected_recently_changed()
                )
                line2 = (
                    "Selected cell: " + inspector[1].strip()
                    if len(inspector) > 1
                    else "Selected cell:"
                )
            self._event_panel_origin = None
            self._event_panel_size = None
            self._event_panel_ticks = ()
        elif perspective_state is not None:
            if perspective_state.sampled_this_tick:
                sample_status = f"Sampled: tick {state.tick}"
            else:
                last_t = (
                    perspective_state.last_visibility_sample_at.tick
                    if perspective_state.last_visibility_sample_at is not None
                    else 0
                )
                sample_status = f"Unsampled this tick (last sample: tick {last_t})"
            curr_n = len(perspective_state.current_contacts)
            stale_n = len(perspective_state.stale_contacts)
            line2 = (
                f"Perspective Cam: Entrant {perspective_state.entrant_id}  |  "
                f"{sample_status}  |  Contacts: {curr_n} current, {stale_n} stale"
            )
            self._event_panel_origin = None
            self._event_panel_size = None
            self._event_panel_ticks = ()
        elif recent:
            event_tick, event = recent[-1]
            line2 = format_event_line(event_tick, event)
            self._event_panel_origin = (tx, ty + FOOTER_LINE_HEIGHT)
            self._event_panel_size = (tw, FOOTER_LINE_HEIGHT)
            self._event_panel_ticks = (event_tick,)
        else:
            line2 = "No recent events"
            self._event_panel_origin = None
            self._event_panel_size = None
            self._event_panel_ticks = ()

        if self.help_visible:
            # Expanded help replaces the event/status line and graph rather
            # than becoming a permanent panel or covering the arena.
            lines = (line1, *format_help_lines(expanded=True))
            tw = max(0, layout.window_size[0] - 2 * tx)
            self._event_panel_origin = None
            self._event_panel_size = None
            self._event_panel_ticks = ()
            graph_rect = (0, 0, 0, 0)
        else:
            lines = (line1, line2, *format_help_lines(expanded=False))
            graph_rect = layout.footer_graph_rect

        # Deterministic truncation keeps even undersized platform windows
        # bounded. At the supported 640px minimum, both compact and expanded
        # help variants fit their intended columns without ellipsis.
        max_chars = max(6, tw // HUD_CHAR_WIDTH_PX)
        for index, text in enumerate(lines):
            # Bounded by the text rect's own height rather than the whole
            # band's: the timeline strip above it is part of the band but
            # not available to text.
            if (index + 1) * FOOTER_LINE_HEIGHT > text_h:
                break
            rendered = self.hud_font.render(truncate_with_ellipsis(text, max_chars), True, TEXT_COLOR)
            self.screen.blit(rendered, (tx, ty + index * FOOTER_LINE_HEIGHT))

        self._draw_footer_graph(state, graph_rect)
