"""Deterministic HUD layout/formatting for the Pygame Replay Viewer
(Beta1 Phase 4).

This module is the "geometry calculation" and "text construction" halves of
the three-way split the governing task calls for (geometry / text / drawing
kept separate). Nothing here imports ``pygame`` -- every function is a pure,
directly-testable computation over primitive values and the Phase-3
``battle_client.replay_status.EntrantReplayStatus`` model. ``pygame_renderer.
PygameRenderer`` is the only "drawing" consumer of this module.

Two governing rules, both enforced by construction here:

* **The arena shows the battle. The HUD explains the battle.** Every rect
  this module hands back tiles the window into non-overlapping bands: a top
  HUD band (match header + one card per entrant), a middle arena band, and
  a bottom footer band (playback/tick, one compact status line, controls,
  and the territory-history graph). The arena band is never covered by any
  of the others.
* **The Replay Viewer renders the Phase-3 status model; it does not decide
  what a core, capture, death, or winner means.** Every formatting function
  below only ever reads already-derived fields off ``EntrantReplayStatus``/
  ``CoreStatus`` (or plain already-resolved strings/numbers the caller
  supplies) -- never raw replay structures, never a Ruleset identity
  membership check.
"""

from __future__ import annotations

from dataclasses import dataclass

from battle_client.replay_status import EntrantReplayStatus

Rect = tuple[int, int, int, int]  # (x, y, w, h), pixels

# ---------------------------------------------------------------------------
# Fixed band geometry. All heights are constants, independent of window size
# or arena scale -- this is what guarantees the arena band's height is
# always exactly ``window_height - TOP_BAND_HEIGHT - FOOTER_HEIGHT`` with no
# possibility of a negative-height or overlapping band (see
# ``calculate_layout``).
# ---------------------------------------------------------------------------
HEADER_LINE_HEIGHT = 18
HEADER_LINES = 2  # match identity line, winner/termination line
CARD_LINE_HEIGHT = 16
CARD_LINES = 3  # name, status(+core), stats
TOP_BAND_PADDING = 6
CARD_GAP = 4  # vertical gap between the header lines and the card row
CARD_PADDING_X = 8  # horizontal gutter between/around entrant cards

TOP_BAND_HEIGHT = (
    TOP_BAND_PADDING
    + HEADER_LINES * HEADER_LINE_HEIGHT
    + CARD_GAP
    + CARD_LINES * CARD_LINE_HEIGHT
    + TOP_BAND_PADDING
)

FOOTER_LINE_HEIGHT = 16
FOOTER_LINES = 3  # tick/playback/speed, status/event message, controls
FOOTER_PADDING = 6
FOOTER_HEIGHT = FOOTER_PADDING * 2 + FOOTER_LINES * FOOTER_LINE_HEIGHT

# The territory-history trend graph (relocated off the arena, see
# docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md) lives in the right side of the
# footer band. Below this window width it is omitted entirely (degenerate
# zero-size rect) rather than crowding the text columns.
FOOTER_GRAPH_WIDTH = 150
FOOTER_GRAPH_MIN_WINDOW_WIDTH = 460


@dataclass(frozen=True)
class ViewerLayout:
    """One window size's worth of non-overlapping HUD/arena/footer rects.

    ``entrant_card_rects`` is always exactly ``entrant_count`` rects, in
    the same order the caller's entrant list is in (the replay's own
    recorded order -- see ``get_entrant_statuses``); there is no two-slot
    "left card"/"right card" special case anywhere in this module.
    """

    window_size: tuple[int, int]
    header_rect: Rect
    entrant_card_rects: tuple[Rect, ...]
    arena_rect: Rect
    footer_text_rect: Rect
    footer_graph_rect: Rect


def calculate_layout(window_size: tuple[int, int], entrant_count: int) -> ViewerLayout:
    """Tile ``window_size`` into header/cards/arena/footer bands.

    Deterministic and pure. ``entrant_count`` cards are laid out in one
    equal-width row (the last card absorbs any integer-division remainder
    so the row always tiles exactly to the window width, with no gap or
    overlap). The arena band's height is always exactly ``window_h -
    TOP_BAND_HEIGHT - FOOTER_HEIGHT`` -- by construction never overlapping
    either fixed band, though it can be very small (never negative; clamped
    at 0) for a pathologically short window.
    """
    window_w = max(1, int(window_size[0]))
    window_h = max(1, int(window_size[1]))
    count = max(1, int(entrant_count))

    header_rect: Rect = (0, 0, window_w, TOP_BAND_PADDING + HEADER_LINES * HEADER_LINE_HEIGHT)

    card_y = header_rect[1] + header_rect[3] + CARD_GAP
    card_h = CARD_LINES * CARD_LINE_HEIGHT
    raw_card_w = max(1, (window_w - CARD_PADDING_X * (count + 1)) // count)
    card_rects: list[Rect] = []
    x = CARD_PADDING_X
    for index in range(count):
        if index == count - 1:
            this_w = max(1, window_w - x - CARD_PADDING_X)
        else:
            this_w = raw_card_w
        card_rects.append((x, card_y, this_w, card_h))
        x += this_w + CARD_PADDING_X

    footer_y = max(TOP_BAND_HEIGHT, window_h - FOOTER_HEIGHT)
    arena_rect: Rect = (0, TOP_BAND_HEIGHT, window_w, max(0, footer_y - TOP_BAND_HEIGHT))

    show_graph = window_w >= FOOTER_GRAPH_MIN_WINDOW_WIDTH
    graph_w = FOOTER_GRAPH_WIDTH if show_graph else 0
    graph_h = FOOTER_HEIGHT - 2 * FOOTER_PADDING if show_graph else 0
    graph_rect: Rect = (
        max(0, window_w - graph_w - FOOTER_PADDING),
        footer_y + FOOTER_PADDING,
        graph_w,
        graph_h,
    )
    text_w = max(0, graph_rect[0] - FOOTER_PADDING * 2) if show_graph else max(0, window_w - FOOTER_PADDING * 2)
    footer_text_rect: Rect = (FOOTER_PADDING, footer_y, text_w, FOOTER_HEIGHT)

    return ViewerLayout(
        window_size=(window_w, window_h),
        header_rect=header_rect,
        entrant_card_rects=tuple(card_rects),
        arena_rect=arena_rect,
        footer_text_rect=footer_text_rect,
        footer_graph_rect=graph_rect,
    )


# ---------------------------------------------------------------------------
# Text formatting -- pure string construction, no drawing. Every function
# accepts an optional ``max_chars`` so a caller with a real font/pixel
# budget can request deterministic truncation (drop lowest-priority clause
# first, then ellipsis) instead of relying on dynamic font shrinking (the
# governing task's explicit preference -- see Phase 4H).
# ---------------------------------------------------------------------------
def truncate_with_ellipsis(text: str, max_chars: int | None) -> str:
    """``text``, shortened to fit ``max_chars`` (an ellipsis replacing the
    trailing content when it doesn't), or unchanged if ``max_chars`` is
    ``None`` or already satisfied.
    """
    if max_chars is None or len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    if max_chars == 1:
        return text[:1]
    return text[: max_chars - 1].rstrip() + "…"


def format_entrant_status_line(status: EntrantReplayStatus, *, max_chars: int | None = None) -> str:
    """One entrant's alive/dead/captured (+ core, when applicable) line.

    Ruleset-v1 (``status.core is None``) never shows a core field -- no
    fabricated ``Core N/A`` (Phase 4E). A core capture is worded distinctly
    from an ordinary death (``"CAPTURED"`` vs. ``"Dead"``) and only shows a
    killer when one is actually attributed (never invented for an
    unattributed capture/forfeit -- Phase 4L/4T). When ``max_chars`` forces
    a choice, the killer clause is dropped before anything else (life state
    and core integrity are always kept, per the governing task's Phase 4N
    hierarchy: identity/alive state and core integrity outrank
    attribution), with a final ellipsis fallback if even that doesn't fit.
    """
    core = status.core
    captured = core is not None and core.captured
    if captured:
        assert core is not None
        life = f"CAPTURED @ T{core.capture_tick}" if core.capture_tick is not None else "CAPTURED"
    elif status.alive:
        life = "Alive"
    else:
        life = f"Dead @ T{status.death_tick}" if status.death_tick is not None else "Dead"

    show_killer = status.killer_id is not None and (captured or not status.alive)
    life_with_killer = f"{life} by {status.killer_id}" if show_killer else life

    core_clause = f"Core {core.intact_cells}/{core.total_cells}" if core is not None else None
    full = f"{life_with_killer} | {core_clause}" if core_clause else life_with_killer
    without_killer = f"{life} | {core_clause}" if core_clause else life

    if max_chars is None or len(full) <= max_chars:
        return full
    if len(without_killer) <= max_chars:
        return without_killer
    return truncate_with_ellipsis(without_killer, max_chars)


def format_entrant_stats_line(status: EntrantReplayStatus, *, max_chars: int | None = None) -> str:
    """One entrant's score/territory/kills line, in that priority order
    (Phase 4N: score outranks territory outranks kills). When ``max_chars``
    forces a choice, the lowest-priority clause is dropped first: kills,
    then the territory percentage refinement, then territory itself,
    leaving score as the last thing ever dropped (and even then only
    ellipsis-truncated, never omitted outright).
    """
    score_part = f"Score {status.score:g}"
    territory_full = f"Territory {status.territory_cells} ({status.territory_percentage:.1f}%)"
    territory_short = f"Territory {status.territory_cells}"
    kills_part = f"Kills {status.kills_so_far}"

    candidates = [
        f"{score_part} | {territory_full} | {kills_part}",
        f"{score_part} | {territory_full}",
        f"{score_part} | {territory_short}",
        score_part,
    ]
    if max_chars is None:
        return candidates[0]
    for candidate in candidates:
        if len(candidate) <= max_chars:
            return candidate
    return truncate_with_ellipsis(candidates[-1], max_chars)


def format_entrant_card_lines(
    status: EntrantReplayStatus, *, max_chars: int | None = None
) -> tuple[str, str, str]:
    """The three lines of one entrant's status card: name, status(+core),
    stats -- always exactly ``CARD_LINES`` (3) lines, so every card in a
    row occupies the same fixed height regardless of entrant state.
    """
    name = status.name.upper()
    if max_chars is not None and len(name) > max_chars:
        name = truncate_with_ellipsis(name, max_chars)
    return (
        name,
        format_entrant_status_line(status, max_chars=max_chars),
        format_entrant_stats_line(status, max_chars=max_chars),
    )


def format_match_header_lines(
    *,
    ruleset_label: str,
    runtime_kind: str,
    arena_size: int,
    entrant_count: int,
    winner: str | None,
    termination_reason: str | None,
    result_available: bool,
) -> tuple[str, str]:
    """The top band's two match-identity lines.

    Line 1 is always present and answers Phase 4O's "is this v1 or v2"
    requirement directly (``ruleset_label`` is the caller's already-resolved
    identity string -- see ``battle_client.replay_status.
    resolve_match_ruleset_label`` -- never re-derived here). Line 2 is
    reserved (returned as ``""`` when absent) rather than omitted, so the
    top band's total height never changes between an in-progress and a
    finished replay.
    """
    line1 = (
        f"Bytefray Replay — Ruleset {ruleset_label}  |  runtime {runtime_kind}  |  "
        f"arena {arena_size}  |  entrants {entrant_count}"
    )
    if result_available:
        line2 = f"Winner: {winner or 'tie'}   Termination: {termination_reason or 'unknown'}"
    else:
        line2 = ""
    return (line1, line2)


def format_playback_line(*, tick: int, final_tick: int | None, status_label: str, speed: float) -> str:
    """The footer's first line: current tick / total, playback state, speed."""
    total = "?" if final_tick is None else str(final_tick)
    return f"Tick {tick}/{total}   [{status_label}]   speed {speed:g}x"


__all__ = [
    "CARD_GAP",
    "CARD_LINES",
    "CARD_LINE_HEIGHT",
    "CARD_PADDING_X",
    "FOOTER_GRAPH_MIN_WINDOW_WIDTH",
    "FOOTER_GRAPH_WIDTH",
    "FOOTER_HEIGHT",
    "FOOTER_LINES",
    "FOOTER_LINE_HEIGHT",
    "FOOTER_PADDING",
    "HEADER_LINES",
    "HEADER_LINE_HEIGHT",
    "TOP_BAND_HEIGHT",
    "TOP_BAND_PADDING",
    "Rect",
    "ViewerLayout",
    "calculate_layout",
    "format_entrant_card_lines",
    "format_entrant_stats_line",
    "format_entrant_status_line",
    "format_match_header_lines",
    "format_playback_line",
    "truncate_with_ellipsis",
]
