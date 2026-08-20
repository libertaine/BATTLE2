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
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from battle_engine.paths import get_branding_icon_path
from battle_engine.replay import AgentEvent, AgentState, EngineEvent, KillDeathEvent, RuntimeEvent

from battle_client.analysis import (
    SelectedCellInfo,
    TerritoryHistory,
    collect_match_events,
    compute_territory_history,
    events_near_tick,
    selected_cell_info,
)
from battle_client.hud_layout import (
    CARD_LINE_HEIGHT,
    FOOTER_HEIGHT,
    FOOTER_LINE_HEIGHT,
    HEADER_LINE_HEIGHT,
    TOP_BAND_HEIGHT,
    ViewerLayout,
    calculate_layout,
    format_entrant_card_lines,
    format_match_header_lines,
    format_playback_line,
    truncate_with_ellipsis,
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
# Rough monospace glyph width for the HUD font, used only to convert a
# card's pixel width into a character budget for deterministic truncation
# (see hud_layout.truncate_with_ellipsis) -- an estimate, not a font metric
# query, since the exact figure only affects how eagerly text truncates,
# never correctness (see test_hud_layout.py's truncation tests).
HUD_CHAR_WIDTH_PX = 7

HELP_TEXT = (
    "Space play/pause  Right/Left step  Shift+Right/Left seek 10  "
    "Home/End first/last  +/- speed  [/] zoom  0 fit  T trails  "
    "click event to seek  click cell to inspect  Esc/Q quit"
)


def integer_scale_to_fit(
    grid_cols: int,
    grid_rows: int,
    bounds: tuple[int, int],
) -> int:
    """Largest positive integer cell scale fitting ``bounds``.

    A one-pixel scale is the irreducible fallback when given degenerate
    dimensions or a display smaller than the logical arena grid.  Real
    supported displays are larger than Bytefray's maximum arena grid, but
    keeping the helper total prevents zero-sized Pygame windows when a
    display backend briefly reports unusable dimensions.
    """

    cols = max(1, int(grid_cols))
    rows = max(1, int(grid_rows))
    width = max(1, int(bounds[0]))
    height = max(1, int(bounds[1]))
    return max(1, min(width // cols, height // rows))


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
    rescale: int = 0  # +1/-1 window scale step
    fit_to_display: bool = False


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

        # Beta1 Phase 4: the current window's HUD/arena/footer band geometry
        # (battle_client.hud_layout.calculate_layout), recomputed whenever
        # the window is (re)configured or resized -- never per-frame, since
        # it depends only on window size and entrant count, neither of
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
        """The total window size for arena cell ``scale``: the arena's own
        ``grid_cols*scale`` by ``grid_rows*scale`` pixel size, plus the
        fixed-height top HUD and footer bands (Beta1 Phase 4) -- see
        ``battle_client.hud_layout.TOP_BAND_HEIGHT``/``FOOTER_HEIGHT``.
        """
        return (
            self.grid_cols * scale,
            TOP_BAND_HEIGHT + self.grid_rows * scale + FOOTER_HEIGHT,
        )

    def _arena_display_bounds(self) -> tuple[int, int]:
        """The display-safe bounds available to the *arena* alone: the
        full display-safe bounds (``_display_bounds``) minus the fixed HUD/
        footer band heights, so scale-fitting logic (``integer_scale_to_
        fit``/``choose_initial_window_scale``, both left otherwise
        unchanged -- see docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md) sizes the
        arena to the space it will actually occupy, never the whole
        display.
        """
        bounds = self._display_bounds()
        return (bounds[0], max(1, bounds[1] - TOP_BAND_HEIGHT - FOOTER_HEIGHT))

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
        self.screen = pg.display.set_mode(window_size, pg.RESIZABLE)
        pg.display.set_caption(self.title)
        self.grid_surf = pg.Surface((self.grid_cols, self.grid_rows))
        self.font = pg.font.SysFont("consolas", 14)
        self.hud_font = pg.font.SysFont("consolas", 13)
        self._layout = calculate_layout(window_size, self._entrant_count)

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
        size = self._window_size_for_scale(self.scale)
        self.screen = self.pg.display.set_mode(size, self.pg.RESIZABLE)
        self.pg.display.set_caption(self.title)
        self._layout = calculate_layout(size, self._entrant_count)

    def _fit_to_display(self) -> None:
        fit_scale = integer_scale_to_fit(
            self.grid_cols, self.grid_rows, self._arena_display_bounds()
        )
        old = self.scale
        self.scale = fit_scale
        if self.scale != old:
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
                    action = dispatch_key(pg, event.key, event.mod, controller)
                    if action.quit_requested:
                        running = False
                        break
                    if action.toggle_trails:
                        self.trails_enabled = not self.trails_enabled
                    if action.rescale:
                        self._rescale(action.rescale)
                    if action.fit_to_display:
                        self._fit_to_display()
                elif event.type in (pg.VIDEORESIZE, getattr(pg, "WINDOWRESIZED", 32769)):
                    w, h = getattr(event, "size", self.screen.get_size())
                    arena_bounds = (w, max(1, h - TOP_BAND_HEIGHT - FOOTER_HEIGHT))
                    new_scale = integer_scale_to_fit(
                        self.grid_cols, self.grid_rows, arena_bounds
                    )
                    if new_scale != self.scale:
                        self.scale = new_scale
                        self._resize_window()
                elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(controller, event.pos)
            if not running:
                break

            controller.update(elapsed_ms / 1000.0)
            self._advance_transient_effects(controller.session.current_state)
            self._redraw(controller)
            pg.display.flip()

    def _handle_click(self, controller: PlaybackController, pos: tuple[int, int]) -> None:
        """Seek to the footer's clickable event message, or select an arena
        cell, for a click at ``pos``.

        The footer's event message takes priority when both could apply: a
        click resolving to its (single) event tick seeks and returns
        immediately, without also touching cell selection.
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

        self._last_rendered_tick = state.tick
        self._last_owners = state.owners

    # ---------- drawing ----------

    def _redraw(self, controller: PlaybackController) -> None:
        pg = self.pg
        gs = self.grid_surf
        state = controller.session.current_state

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

        self._draw_selection_highlight()
        self._draw_top_band(controller)
        self._draw_footer(controller)

    def _blend(
        self, a: tuple[int, int, int], b: tuple[int, int, int], alpha: float
    ) -> tuple[int, int, int]:
        return (
            int(a[0] * (1 - alpha) + b[0] * alpha),
            int(a[1] * (1 - alpha) + b[1] * alpha),
            int(a[2] * (1 - alpha) + b[2] * alpha),
        )

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

    def _draw_top_band(self, controller: PlaybackController) -> None:
        """Draw the top HUD band: the match-identity header and one status
        card per entrant.

        Entrant status comes entirely from ``battle_client.replay_status.
        get_entrant_statuses`` (the Phase-3 status model) -- this method
        never inspects raw replay structures, ownership, or Ruleset
        identity itself (see the governing architectural rule in
        docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md). A no-op if no layout has
        been computed yet (a unit test that never called ``run()``).
        """
        layout = self._layout
        if layout is None:
            return
        session = controller.session
        state = session.current_state

        band_rect = self.pg.Rect(0, 0, layout.window_size[0], TOP_BAND_HEIGHT)
        self.pg.draw.rect(self.screen, PANEL_BG, band_rect)
        self.pg.draw.line(
            self.screen,
            PANEL_BORDER,
            (0, TOP_BAND_HEIGHT - 1),
            (layout.window_size[0], TOP_BAND_HEIGHT - 1),
        )

        statuses = get_entrant_statuses(session, state=state, match_events=self._match_events)

        hx, hy, hw, _hh = layout.header_rect
        header_lines = format_match_header_lines(
            ruleset_label=self._ruleset_label,
            runtime_kind=state.runtime_kind or "unknown",
            arena_size=self.arena,
            entrant_count=len(statuses),
            winner=session.winner,
            termination_reason=session.termination_reason,
            result_available=session.result is not None,
        )
        header_max_chars = max(6, (hw - 6) // HUD_CHAR_WIDTH_PX)
        for index, text in enumerate(header_lines):
            if not text:
                continue
            rendered = self.hud_font.render(
                truncate_with_ellipsis(text, header_max_chars), True, TEXT_COLOR
            )
            self.screen.blit(rendered, (hx + 6, hy + index * HEADER_LINE_HEIGHT))

        for status, rect in zip(statuses, layout.entrant_card_rects):
            self._draw_entrant_card(status, rect)

    def _draw_entrant_card(self, status: EntrantReplayStatus, rect: tuple[int, int, int, int]) -> None:
        """One entrant's status card (name / status+core / stats), entirely
        formatted by ``battle_client.hud_layout.format_entrant_card_lines``
        -- this method only chooses colors and blit positions.
        """
        cx, cy, cw, _ch = rect
        max_chars = max(6, cw // HUD_CHAR_WIDTH_PX)
        name_line, status_line, stats_line = format_entrant_card_lines(status, max_chars=max_chars)

        if status.core is not None and status.core.captured:
            status_color = STATUS_CAPTURED_COLOR
        elif status.alive:
            status_color = STATUS_ALIVE_COLOR
        else:
            status_color = STATUS_DEAD_COLOR
        name_color = AGENT_COLORS.get(status.agent_id, DEFAULT_AGENT_COLOR)

        for index, (text, color) in enumerate(
            ((name_line, name_color), (status_line, status_color), (stats_line, DIM_TEXT_COLOR))
        ):
            rendered = self.hud_font.render(text, True, color)
            self.screen.blit(rendered, (cx, cy + index * CARD_LINE_HEIGHT))

    def _draw_footer(self, controller: PlaybackController) -> None:
        """Draw the bottom footer band: tick/playback/speed, one compact
        status/event message, controls/help, and the territory-history
        graph.

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

        footer_y = layout.window_size[1] - FOOTER_HEIGHT
        band_rect = self.pg.Rect(0, footer_y, layout.window_size[0], FOOTER_HEIGHT)
        self.pg.draw.rect(self.screen, PANEL_BG, band_rect)
        self.pg.draw.line(self.screen, PANEL_BORDER, (0, footer_y), (layout.window_size[0], footer_y))

        tx, ty, tw, _th = layout.footer_text_rect
        status_label = "PLAYING" if controller.playing else "PAUSED"
        if session.at_end and not controller.playing:
            status_label = "PAUSED (end)"
        line1 = format_playback_line(
            tick=state.tick,
            final_tick=session.final_tick,
            status_label=status_label,
            speed=controller.speed,
        )

        selected = self._selected_cell_info(state)
        recent = events_near_tick(self._match_events, state.tick, window=1)
        if selected is not None:
            inspector = format_inspector_lines(selected, recently_changed=self._selected_recently_changed())
            line2 = "Selected cell: " + inspector[1].strip() if len(inspector) > 1 else "Selected cell:"
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

        # Deterministic truncation (never dynamic font shrinking -- Phase
        # 4H) so a long controls string can never visually run past its own
        # column and under the graph panel drawn just to its right.
        max_chars = max(6, tw // HUD_CHAR_WIDTH_PX)
        for index, text in enumerate((line1, line2, HELP_TEXT)):
            rendered = self.hud_font.render(truncate_with_ellipsis(text, max_chars), True, TEXT_COLOR)
            self.screen.blit(rendered, (tx, ty + index * FOOTER_LINE_HEIGHT))

        self._draw_footer_graph(state, layout.footer_graph_rect)
