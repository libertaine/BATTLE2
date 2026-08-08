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
"""

from __future__ import annotations

import bisect
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from battle_engine.replay import AgentEvent, AgentState, EngineEvent, KillDeathEvent, RuntimeEvent

from battle_client.player import PlaybackController
from battle_client.renderers.base import RendererDependencyError
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

HELP_TEXT = (
    "Space play/pause  Right/Left step  Shift+Right/Left seek 10  "
    "Home/End first/last  +/- speed  [/] zoom  T trails  "
    "click event to seek  click cell to inspect  Esc/Q quit"
)


# ---------------------------------------------------------------------------
# HUD content: pure functions over ReplaySession/PlaybackController/
# ReplayState, deliberately kept free of any Pygame dependency so they can
# be unit tested without opening a window.
# ---------------------------------------------------------------------------
def _agent_display_line(
    agent_id: str,
    display_name: str,
    state: ReplayState,
    territory: tuple[int, float] | None = None,
) -> str:
    """One HUD line for one entrant, labeled for its actual runtime kind.

    VM: ``pc`` is a real fetch address, ``cpu_used`` an instruction count,
    ``region`` a real code-load footprint. Python: the controller value is
    never called "pc"/labeled as a source location, ``cpu_used`` is
    labeled as an action/callback count, and the always-degenerate
    ``(0, 0)`` region is never presented as a meaningful footprint -- see
    the runtime-kind semantics table in docs/REPLAY_SCHEMA.md.

    ``territory``, if given, is this agent's ``(owned_cell_count,
    percentage_of_arena)`` from :func:`territory_summary` -- rendered as
    its own ``territory=`` token, deliberately never merged into or
    confused with ``score=``: territory is a point-in-time ownership
    snapshot, while score (see ``battle_engine.scoring.ScoringPolicy``)
    accumulates cumulatively in bucketed steps and is not proportional to
    it.
    """
    agent = state.agents.get(agent_id)
    if agent is None:
        return f"{agent_id} ({display_name})  no data at this tick"

    status = "alive" if agent.alive else "dead"
    score = state.score.get(agent_id, 0)

    if state.runtime_kind == "python":
        position_label = f"ctrl={agent.pc}"
        cpu_label = f"actions={agent.cpu_used}"
        region_label = "region=n/a (python controller)"
    else:
        position_label = f"pc={agent.pc}"
        cpu_label = f"cpu={agent.cpu_used}"
        region_label = f"region={list(agent.region)}" if agent.region else "region=?"

    territory_label = ""
    if territory is not None:
        count, percentage = territory
        territory_label = f"  territory={count}/{len(state.owners)} ({percentage:.1f}%)"

    return (
        f"{agent_id} ({display_name})  {status}  score={score:g}{territory_label}  "
        f"{cpu_label}  writes={agent.mem_writes}  {position_label}  {region_label}"
    )


def territory_summary(state: ReplayState) -> dict[str, tuple[int, float]]:
    """Each entrant's ``(owned_cell_count, percentage_of_arena)``.

    Derived entirely from ``state.owners`` -- an ownership snapshot, not
    canonical score (see ``_agent_display_line``'s docstring for why the
    two must not be conflated). Every agent present in ``state.agents`` is
    included, even at zero owned cells, so a viewer never has to treat a
    missing entry as "unknown" versus "owns nothing".
    """
    total = len(state.owners)
    counts = Counter(owner for owner in state.owners if owner is not None)
    summary: dict[str, tuple[int, float]] = {}
    for agent_id in state.agents:
        count = counts.get(agent_id, 0)
        percentage = (count / total * 100.0) if total else 0.0
        summary[agent_id] = (count, percentage)
    return summary


@dataclass(frozen=True)
class TerritoryHistory:
    """Every entrant's owned-cell percentage at every recorded tick.

    ``ticks`` is strictly increasing (it is ``session.recorded_ticks`` in
    order); ``percentages[agent_id]`` is a tuple aligned index-for-index
    with ``ticks``. An agent absent from a given tick's ``ReplayState.
    agents`` -- never happens for a canonical replay, which reports every
    entrant every tick, but handled honestly rather than assumed for a
    legacy one -- is recorded as ``0.0`` for that tick rather than
    omitted, so every agent's series has exactly ``len(ticks)`` points.
    This is a territory (ownership) metric derived only from ``state.
    owners``, same as ``territory_summary``; it is never a substitute for
    canonical score.
    """

    ticks: tuple[int, ...]
    percentages: Mapping[str, tuple[float, ...]]


def compute_territory_history(session: ReplaySession) -> TerritoryHistory:
    """Derive :class:`TerritoryHistory` by walking ``session`` forward once.

    Uses only ``ReplaySession``'s own existing incremental reconstruction
    (``restart``/``step_forward``) -- there is no second, renderer-owned
    replay of memory diffs, and no per-tick full arena snapshot is stored,
    only each tick's small ``{agent_id: percentage}`` summary. Intended to
    be called once, right after a session is loaded (see ``PygameRenderer.
    run``), not on every rendered frame -- walking ~3000 ticks once at
    startup is cheap; doing it every frame would not be.

    The session's cursor is restored to wherever it was before this call
    (via ``seek`` back to the original tick), so calling this mid-playback
    -- as tests do -- never disturbs the caller's position. Returns an
    empty history for a replay with no tick records.
    """
    if not session.loaded or session.final_tick is None:
        return TerritoryHistory(ticks=(), percentages={})

    original_tick = session.current_tick
    ticks: list[int] = []
    points: list[dict[str, float]] = []
    agent_ids: set[str] = set()

    state = session.restart()
    while True:
        ticks.append(state.tick)
        summary = territory_summary(state)
        points.append({agent_id: percentage for agent_id, (_count, percentage) in summary.items()})
        agent_ids.update(summary)
        if session.at_end:
            break
        state = session.step_forward()

    percentages = {
        agent_id: tuple(point.get(agent_id, 0.0) for point in points) for agent_id in agent_ids
    }
    session.seek(original_tick)
    return TerritoryHistory(ticks=tuple(ticks), percentages=percentages)


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


def collect_match_events(session: ReplaySession) -> list[tuple[int, EngineEvent]]:
    """Every recorded event in ``session``, as ``(tick, event)`` pairs.

    ``session.recorded_ticks`` is already strictly increasing (see
    ``ReplaySession``'s own tick-identity guarantee), so this list comes
    out chronologically ordered for free. In practice, for a canonical
    v3 replay, every event is a ``KillDeathEvent`` or a ``RuntimeEvent``
    (Python-only ``forfeit``) -- the native writer never emits
    ``AgentEvent`` (``spawn``/``move``/``territory``/``claim``), which
    exists solely to represent historical v0.1/v0.2 records. Both are
    handled the same way here regardless: nothing about this function
    depends on which event types a given replay happens to contain.
    """
    events: list[tuple[int, EngineEvent]] = []
    for tick in session.recorded_ticks:
        for event in session.events_at_tick(tick):
            events.append((tick, event))
    return events


def events_near_tick(
    events: list[tuple[int, EngineEvent]], tick: int, window: int = 5
) -> list[tuple[int, EngineEvent]]:
    """Up to ``window`` most recent events at or before ``tick``.

    ``events`` is assumed already in ascending tick order (as
    ``collect_match_events`` returns it); the result stays in that same
    ascending order, so it reads top-to-bottom the same direction as the
    match itself played out.
    """
    at_or_before = [pair for pair in events if pair[0] <= tick]
    return at_or_before[-window:] if window > 0 else []


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


@dataclass(frozen=True)
class SelectedCellInfo:
    """The authoritative replay state at one selected arena address.

    Every field is read straight off an existing ``ReplayState`` (or, for
    ``recently_changed``, off the renderer's existing per-address flash
    bookkeeping in ``_advance_transient_effects`` -- itself derived only
    from a genuine ownership change on the immediately preceding linear
    step); nothing here is fabricated. ``occupant`` is only ever populated
    for a VM replay (``AgentState.pc`` is a real fetch address there and
    only there -- see ``_vm_marker_xy``'s docstring); for a Python replay
    it stays ``None`` unconditionally, since the Python controller's ``pc``
    value is not a position an agent can be said to "occupy".
    """

    address: int
    byte_value: int | None
    owner: str | None
    occupant: str | None
    recently_changed: bool = False


def selected_cell_info(
    state: ReplayState, address: int, *, recently_changed: bool = False
) -> SelectedCellInfo | None:
    """``SelectedCellInfo`` for ``address`` in ``state``, or ``None`` if
    ``address`` is outside ``state.owners``' range (out-of-range for the
    replay's arena).
    """
    if address < 0 or address >= len(state.owners):
        return None
    byte_value = state.arena[address] if address < len(state.arena) else None
    owner = state.owners[address]
    occupant = None
    if state.runtime_kind == "vm":
        for agent_id, agent in state.agents.items():
            if agent.alive and isinstance(agent.pc, int) and agent.pc == address:
                occupant = agent_id
                break
    return SelectedCellInfo(
        address=address,
        byte_value=byte_value,
        owner=owner,
        occupant=occupant,
        recently_changed=recently_changed,
    )


def format_inspector_lines(info: SelectedCellInfo | None) -> list[str]:
    """HUD lines for a "Selected cell:" panel, or ``[]`` if ``info`` is
    ``None`` (nothing selected -- the panel is simply omitted, matching
    how ``build_hud_lines`` already omits "Recent events:" when empty).
    """
    if info is None:
        return []
    byte_label = f"byte=0x{info.byte_value:02x}" if info.byte_value is not None else "byte=?"
    owner_label = f"owner={info.owner}" if info.owner is not None else "owner=none"
    agent_label = f"agent={info.occupant}" if info.occupant is not None else "agent=none"
    line = f"  addr={info.address}  {byte_label}  {owner_label}  {agent_label}"
    if info.recently_changed:
        line += "  (recently changed)"
    return ["Selected cell:", line]


def _event_section_start(lines: list[str]) -> int | None:
    """The index in ``lines`` (as returned by :func:`build_hud_lines`)
    where the "Recent events:" section's event rows begin, or ``None`` if
    that call included no such section (no events at/before that tick).
    """
    try:
        return lines.index("Recent events:") + 1
    except ValueError:
        return None


def build_hud_lines(
    session: ReplaySession,
    controller: PlaybackController,
    *,
    match_events: list[tuple[int, EngineEvent]] | None = None,
    selected: SelectedCellInfo | None = None,
) -> list[str]:
    """The HUD's text content for the session/controller's current state.

    Kept readable rather than exhaustive: one status line, one line per
    entrant (now including territory alongside score -- see
    ``_agent_display_line``), a compact "Selected cell:" panel (Phase 7b
    Slice 2, see ``format_inspector_lines``) when ``selected`` is given, a
    short "Recent events" section, and winner/termination once the
    replay's terminal record establishes them -- which is independent of
    the current playback position, since that metadata comes straight
    from the canonical replay's own terminal ``MatchResult``, not from
    scrubbing to the end.

    ``match_events`` lets a caller that already computed
    ``collect_match_events(session)`` once (it scans every recorded tick,
    so a real renderer should cache it for the session's lifetime rather
    than repeat that scan every frame) pass it in; if omitted, it is
    computed fresh here, which keeps this function usable standalone in
    tests without that caching concern.
    """
    state = session.current_state
    runtime_label = state.runtime_kind or "unknown"
    status = "PLAYING" if controller.playing else "PAUSED"
    if session.at_end:
        status = "PAUSED (end)" if not controller.playing else status

    territory = territory_summary(state)

    lines = [
        f"Bytefray Replay -- runtime: {runtime_label}",
        f"Tick {state.tick} / {session.final_tick}   [{status}]   speed {controller.speed:g}x",
        "",
    ]

    agent_names = dict(session.header.agents) if session.header is not None else {}
    for agent_id in sorted(state.agents):
        display_name = agent_names.get(agent_id, agent_id)
        lines.append(
            _agent_display_line(agent_id, display_name, state, territory.get(agent_id))
        )

    inspector_lines = format_inspector_lines(selected)
    if inspector_lines:
        lines.append("")
        lines.extend(inspector_lines)

    events = collect_match_events(session) if match_events is None else match_events
    recent = events_near_tick(events, state.tick)
    if recent:
        lines.append("")
        lines.append("Recent events:")
        for event_tick, event in recent:
            lines.append(f"  {format_event_line(event_tick, event)}")

    if session.result is not None:
        winner = session.winner or "tie"
        lines.append("")
        lines.append(f"Winner: {winner}   Termination: {session.termination_reason}")

    lines.append("")
    lines.append(HELP_TEXT)
    return lines


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

    def __init__(self, scale: int = 4, title: str = "Bytefray - Replay") -> None:
        self.scale = max(1, int(scale))
        self.title = title

        self.pg: Any = None
        self.screen: Any = None
        self.grid_surf: Any = None
        self.font: Any = None
        self.hud_font: Any = None

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
        # every frame (see build_hud_lines's ``match_events`` parameter).
        self._match_events: list[tuple[int, EngineEvent]] = []
        # Where the HUD's "Recent events" panel was last drawn on screen,
        # and which tick each of its lines corresponds to -- set fresh by
        # _draw_hud every frame, read by _loop's click handling. None/empty
        # when the current tick has no events to show.
        self._event_panel_origin: tuple[int, int] | None = None
        self._event_panel_size: tuple[int, int] | None = None
        self._event_panel_ticks: tuple[int, ...] = ()

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

    def _screen_xy(self, x: int, y: int) -> tuple[int, int]:
        w, h = self.screen.get_size()
        return (
            int((x + 0.5) * w / self.grid_cols),
            int((y + 0.5) * h / self.grid_rows),
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

    def _configure_window(self) -> None:
        pg = self.pg
        try:
            di = pg.display.Info()
            max_w, max_h = int(di.current_w * 0.90), int(di.current_h * 0.90)
        except (pg.error, AttributeError, TypeError, ValueError):
            max_w, max_h = 1920, 1080

        fit_scale = max(1, min(max_w // self.grid_cols, max_h // self.grid_rows))
        self.scale = max(1, min(self.scale, fit_scale))
        window_size = (self.grid_cols * self.scale, self.grid_rows * self.scale)
        self.screen = pg.display.set_mode(window_size, pg.RESIZABLE)
        pg.display.set_caption(self.title)
        self.grid_surf = pg.Surface((self.grid_cols, self.grid_rows))
        self.font = pg.font.SysFont("consolas", 14)
        self.hud_font = pg.font.SysFont("consolas", 13)

    def _resize_window(self) -> None:
        size = (self.grid_cols * self.scale, self.grid_rows * self.scale)
        self.screen = self.pg.display.set_mode(size, self.pg.RESIZABLE)
        self.pg.display.set_caption(self.title)

    def _fit_to_display(self) -> None:
        pg = self.pg
        try:
            di = pg.display.Info()
            max_w, max_h = int(di.current_w * 0.90), int(di.current_h * 0.90)
        except (pg.error, AttributeError, TypeError, ValueError):
            max_w, max_h = 1920, 1080
        fit_scale = max(1, min(max_w // self.grid_cols, max_h // self.grid_rows))
        old = self.scale
        self.scale = max(1, min(self.scale, fit_scale))
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
                        old = self.scale
                        self.scale = max(1, min(16, self.scale + action.rescale))
                        if self.scale != old:
                            self._resize_window()
                    if action.fit_to_display:
                        self._fit_to_display()
                elif event.type in (pg.VIDEORESIZE, getattr(pg, "WINDOWRESIZED", 32769)):
                    w, h = getattr(event, "size", self.screen.get_size())
                    new_scale = max(1, min(w // self.grid_cols, h // self.grid_rows))
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
        """Seek to an event's tick, or select an arena cell, for a click at
        ``pos``.

        The "Recent events" panel takes priority when both could apply (it
        is drawn on top of the grid): a click resolving to an event tick
        seeks and returns immediately, without also touching cell
        selection. ``ReplaySession.seek`` is called directly rather than
        through ``PlaybackController`` because seeking to an arbitrary
        already-recorded tick isn't one of the controller's own navigation
        primitives (see ``player.py``'s module docstring on why
        ``ReplaySession`` stays the sole source of reconstructed state).

        Otherwise, if the click lands on a valid arena cell, it becomes the
        selected address (see ``_selected_address``) -- a presentation-only
        selection, not a navigation command, so it never pauses playback.
        A click that hits neither the event panel nor a valid arena cell
        (outside the window, or before the renderer has a real screen --
        e.g. in a unit test that never called ``run()``) leaves the
        current selection untouched.
        """
        if self._event_panel_origin is not None and self._event_panel_size is not None:
            tick = resolve_event_click(
                self._event_panel_ticks, self._event_panel_origin, self._event_panel_size, 16, pos
            )
            if tick is not None:
                controller.pause()
                controller.session.seek(tick)
                return

        if self.screen is None or self.grid_cols <= 0 or self.grid_rows <= 0:
            return
        address = screen_pos_to_address(
            pos, self.screen.get_size(), self.grid_cols, self.grid_rows, self.arena
        )
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

        scaled = pg.transform.scale(gs, self.screen.get_size())
        self.screen.blit(scaled, (0, 0))

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
        self._draw_territory_graph(state)
        self._draw_hud(controller)

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
        cell_scale = min(
            self.screen.get_width() / self.grid_cols,
            self.screen.get_height() / self.grid_rows,
        )
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
        w, h = self.screen.get_size()
        cell_w = w / self.grid_cols
        cell_h = h / self.grid_rows
        rect = self.pg.Rect(
            int(x * cell_w), int(y * cell_h), max(1, math.ceil(cell_w)), max(1, math.ceil(cell_h))
        )
        self.pg.draw.rect(self.screen, SELECTION_COLOR, rect, 2)

    def _draw_territory_graph(self, state: ReplayState) -> None:
        """Draw the compact territory-history trend panel in the bottom-right
        corner: one polyline per agent, its owned-cell percentage over a
        trailing window of ticks ending at the current tick.

        Reads only ``self._territory_history`` (precomputed once in
        ``run()`` -- see ``compute_territory_history``); no replay
        reconstruction happens here, only windowing/downsampling/coordinate
        math (``select_history_window``/``downsample_series``/
        ``territory_graph_points``), all pure and cheap. A no-op if no
        history was computed (e.g. a replay with no tick records).
        """
        history = self._territory_history
        if not history.ticks:
            return

        w, h = self.screen.get_size()
        panel_w, panel_h, margin = 190, 70, 8
        panel_x, panel_y = w - panel_w - margin, h - panel_h - margin
        if panel_x < 0 or panel_y < 0:
            return
        # Local (panel-surface) coordinates -- the plot area, inset from the
        # panel's own border, leaving a bottom strip for the legend labels.
        local_plot_rect = (4, 4, panel_w - 8, panel_h - 20)

        panel = self.pg.Surface((panel_w, panel_h), flags=self.pg.SRCALPHA)
        panel.fill((0, 0, 0, 150))
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
        width = max(1, min(self.screen.get_size()) // max(self.grid_cols, self.grid_rows) // 3)
        self.pg.draw.lines(self.screen, color, False, screen_points, width)

    def _selected_cell_info(self, state: ReplayState) -> SelectedCellInfo | None:
        """The current ``SelectedCellInfo`` for ``self._selected_address``,
        or ``None`` if nothing is selected.

        ``recently_changed`` comes from ``self._flash`` -- the renderer's
        existing per-address ownership-change bookkeeping (see
        ``_advance_transient_effects``), which only ever fires on a
        genuine ownership change on the immediately preceding *linear*
        step and is cleared on any seek/restart. Reusing it here, rather
        than inventing separate "last write" tracking, keeps the signal
        honest: it reflects an owner change, not literally every write.
        """
        if self._selected_address is None:
            return None
        xy = self._to_xy(self._selected_address)
        recently_changed = xy is not None and xy in self._flash
        return selected_cell_info(state, self._selected_address, recently_changed=recently_changed)

    def _draw_hud(self, controller: PlaybackController) -> None:
        session = controller.session
        selected = self._selected_cell_info(session.current_state)
        lines = build_hud_lines(
            session, controller, match_events=self._match_events, selected=selected
        )
        w, _ = self.screen.get_size()
        line_height = 16
        hud_h = line_height * len(lines) + 12
        hud = self.pg.Surface((w, hud_h), flags=self.pg.SRCALPHA)
        hud.fill((0, 0, 0, 150))
        for index, text in enumerate(lines):
            rendered = self.hud_font.render(text, True, (235, 235, 235))
            hud.blit(rendered, (10, 6 + index * line_height))
        self.screen.blit(hud, (0, 0))

        # Track where the "Recent events" lines just landed on screen (HUD
        # surface origin is (0, 0)) so a click can be resolved against them
        # -- see _handle_click. None/empty whenever there's nothing to
        # click, e.g. no events at/before the current tick.
        recent = events_near_tick(self._match_events, session.current_tick)
        start_index = _event_section_start(lines)
        if start_index is not None and recent:
            self._event_panel_origin = (0, 6 + start_index * line_height)
            self._event_panel_size = (w, line_height * len(recent))
            self._event_panel_ticks = tuple(tick for tick, _event in recent)
        else:
            self._event_panel_origin = None
            self._event_panel_size = None
            self._event_panel_ticks = ()
