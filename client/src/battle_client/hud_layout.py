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
  a bottom footer band (the whole-match timeline, playback/tick, one
  compact status line, controls, and the territory-history graph). The
  arena band is never covered by any of the others.
* **The Replay Viewer renders the Phase-3 status model; it does not decide
  what a core, capture, death, or winner means.** Every formatting function
  below only ever reads already-derived fields off ``EntrantReplayStatus``/
  ``CoreStatus`` (or plain already-resolved strings/numbers the caller
  supplies) -- never raw replay structures, never a Ruleset identity
  membership check.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from battle_client.replay_status import EntrantReplayStatus

Rect = tuple[int, int, int, int]  # (x, y, w, h), pixels

# ---------------------------------------------------------------------------
# Responsive band/card geometry (Beta3 Phase 2).
# ---------------------------------------------------------------------------
HEADER_LINE_HEIGHT = 18
HEADER_LINES = 2  # match identity line, winner/termination line
CARD_LINE_HEIGHT = 16
CARD_LINES = 3  # detailed: identity, status(+core), stats
COMPACT_CARD_LINES = 2  # compact: identity, essential status/core/score
TOP_BAND_PADDING = 6
CARD_GAP = 4  # gap between the header and cards, and between card rows
CARD_PADDING_X = 8  # horizontal gutter between/around entrant cards

# 640px gives a two-entrant detailed row about 300px per card (roughly 43
# monospace HUD characters). 480px leaves at least the 256px useful arena
# viewport below a one/two-row HUD and the 60px footer. Ordinary OS resize
# events are still honored below this preferred supported minimum; the pure
# layout clips bands instead of overlapping or crashing.
MIN_VIEWER_SIZE = (640, 480)
MIN_USEFUL_ARENA_HEIGHT = 256

# Detailed cards retain all three existing information lines. At narrower
# widths they reflow to a balanced two-row grid; five-plus entrants use the
# denser two-line roster. The 35% cap is also bounded by
# MIN_USEFUL_ARENA_HEIGHT at supported sizes, so extra entrants cannot consume
# an unreasonable share of the viewer.
DETAILED_CARD_MIN_WIDTH = 220
COMPACT_CARD_MIN_WIDTH = 180
MAX_TOP_BAND_FRACTION = 0.35

CardMode = Literal["detailed", "compact"]

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

# The match timeline: a thin full-width scrub track across the top of the
# footer band, spanning the whole match from its first to its final recorded
# tick (unlike the territory graph beside it, which deliberately shows only a
# trailing window). Recorded matches run from tens to a couple of thousand
# ticks while the keyboard's coarsest step is ten ticks, so without a
# position-proportional track there is no way to reach an arbitrary point in a
# long replay at all.
#
# The 8px total (FOOTER_TIMELINE_BLOCK) is a deliberate ceiling, not a
# stylistic preference. _top_height_cap reserves MIN_USEFUL_ARENA_HEIGHT out
# of whatever the footer leaves, so every pixel the footer gains is taken
# from the top band's cap at the supported 640x480 minimum. Eight pixels is
# the largest growth at which every existing entrant-count layout there --
# including the densest twelve-entrant compact roster, which needs a 156px
# cap for its four-column grid -- keeps the exact card geometry it had before
# this band existed. A taller track would silently re-flow that roster into
# narrower columns. The strip itself stays an easy mouse target regardless:
# timeline_contains widens the grab area vertically past the drawn track.
FOOTER_TIMELINE_HEIGHT = 6
FOOTER_TIMELINE_GAP = 2
FOOTER_TIMELINE_BLOCK = FOOTER_TIMELINE_HEIGHT + FOOTER_TIMELINE_GAP
FOOTER_HEIGHT = (
    FOOTER_PADDING * 2 + FOOTER_TIMELINE_BLOCK + FOOTER_LINES * FOOTER_LINE_HEIGHT
)

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
    card_mode: CardMode
    card_columns: int
    card_rows: int
    top_band_height: int
    arena_viewport_rect: Rect
    arena_rect: Rect
    arena_scale: int
    footer_text_rect: Rect
    footer_timeline_rect: Rect
    footer_graph_rect: Rect
    footer_height: int


def integer_scale_to_fit(grid_cols: int, grid_rows: int, bounds: tuple[int, int]) -> int:
    """Largest positive integer cell scale fitting ``bounds``.

    One pixel per cell remains the irreducible fallback for a pathologically
    small viewport. At every supported viewer size the ordinary arena grids
    fit at a true positive integer scale; the fallback only keeps undersized
    platform/window-manager states total and crash-free.
    """

    cols = max(1, int(grid_cols))
    rows = max(1, int(grid_rows))
    width = max(1, int(bounds[0]))
    height = max(1, int(bounds[1]))
    return max(1, min(width // cols, height // rows))


def _columns_for_width(window_w: int, count: int, minimum_card_width: int) -> int:
    return max(
        1,
        min(
            count,
            max(1, (window_w - CARD_PADDING_X) // (minimum_card_width + CARD_PADDING_X)),
        ),
    )


def _balanced_columns(count: int, maximum_columns: int) -> int:
    columns = max(1, min(count, maximum_columns))
    rows = (count + columns - 1) // columns
    return max(1, min(columns, (count + rows - 1) // rows))


def _top_content_height(rows: int, card_lines: int) -> int:
    return (
        TOP_BAND_PADDING
        + HEADER_LINES * HEADER_LINE_HEIGHT
        + CARD_GAP
        + rows * card_lines * CARD_LINE_HEIGHT
        + max(0, rows - 1) * CARD_GAP
        + TOP_BAND_PADDING
    )


def _top_height_cap(window_h: int, footer_h: int) -> int:
    available = max(0, window_h - footer_h)
    proportional = int(window_h * MAX_TOP_BAND_FRACTION)
    if window_h >= MIN_VIEWER_SIZE[1]:
        preserve_arena = max(0, window_h - footer_h - MIN_USEFUL_ARENA_HEIGHT)
        return max(0, min(available, proportional, preserve_arena))
    return max(0, min(available, proportional))


def calculate_layout(
    window_size: tuple[int, int],
    entrant_count: int,
    grid_size: tuple[int, int] | None = None,
    *,
    preferred_arena_scale: int | None = None,
) -> ViewerLayout:
    """Tile one requested outer window into responsive HUD/arena/footer.

    ``grid_size`` makes ``arena_rect`` the largest centered integer-scaled
    arena that fits the separate ``arena_viewport_rect``. When omitted (old
    helper consumers/tests), the arena occupies the whole viewport. A manual
    zoom may supply ``preferred_arena_scale``; it is capped to what fits.

    Two through four entrants use detailed three-line cards whenever a
    balanced grid fits the explicit top-band cap. Five-plus entrants use a
    compact two-line roster. Compact columns may become narrower than their
    preferred width only when necessary to keep every entrant inside the HUD
    without starving the arena.
    """
    window_w = max(1, int(window_size[0]))
    window_h = max(1, int(window_size[1]))
    count = max(1, int(entrant_count))

    footer_h = min(FOOTER_HEIGHT, window_h)
    top_cap = _top_height_cap(window_h, footer_h)

    detailed_columns = _balanced_columns(
        count, _columns_for_width(window_w, count, DETAILED_CARD_MIN_WIDTH)
    )
    detailed_rows = (count + detailed_columns - 1) // detailed_columns
    detailed_height = _top_content_height(detailed_rows, CARD_LINES)

    if count <= 4 and detailed_height <= top_cap:
        card_mode: CardMode = "detailed"
        columns = detailed_columns
        rows = detailed_rows
        card_lines = CARD_LINES
        content_height = detailed_height
    else:
        card_mode = "compact"
        columns = _columns_for_width(window_w, count, COMPACT_CARD_MIN_WIDTH)
        rows = (count + columns - 1) // columns
        content_height = _top_content_height(rows, COMPACT_CARD_LINES)
        while content_height > top_cap and columns < count:
            columns += 1
            rows = (count + columns - 1) // columns
            content_height = _top_content_height(rows, COMPACT_CARD_LINES)
        card_lines = COMPACT_CARD_LINES

    top_h = min(content_height, top_cap, max(0, window_h - footer_h))
    header_required_h = TOP_BAND_PADDING + HEADER_LINES * HEADER_LINE_HEIGHT
    header_rect: Rect = (0, 0, window_w, min(top_h, header_required_h))

    card_y = min(top_h, header_required_h + CARD_GAP)
    card_h = card_lines * CARD_LINE_HEIGHT
    available_card_w = max(0, window_w - CARD_PADDING_X * (columns + 1))
    base_card_w = max(0, available_card_w // columns)
    card_rects: list[Rect] = []
    for index in range(count):
        row, column = divmod(index, columns)
        x = CARD_PADDING_X + column * (base_card_w + CARD_PADDING_X)
        if column == columns - 1:
            this_w = max(0, window_w - x - CARD_PADDING_X)
        else:
            this_w = base_card_w
        y = card_y + row * (card_h + CARD_GAP)
        visible_h = max(0, min(card_h, top_h - y))
        card_rects.append((x, y, this_w, visible_h))

    footer_y = max(top_h, window_h - footer_h)
    viewport: Rect = (0, top_h, window_w, max(0, footer_y - top_h))

    if grid_size is None:
        arena_rect = viewport
        arena_scale = 1
    else:
        cols = max(1, int(grid_size[0]))
        grid_rows = max(1, int(grid_size[1]))
        fit_scale = integer_scale_to_fit(cols, grid_rows, (viewport[2], viewport[3]))
        arena_scale = (
            fit_scale
            if preferred_arena_scale is None
            else max(1, min(fit_scale, int(preferred_arena_scale)))
        )
        # If a platform forces a viewport smaller than the logical grid, no
        # positive integer scale can fit. Clamp only that pathological case
        # to the viewport so rendering remains bounded and non-overlapping.
        arena_w = min(viewport[2], cols * arena_scale)
        arena_h = min(viewport[3], grid_rows * arena_scale)
        arena_rect = (
            viewport[0] + max(0, (viewport[2] - arena_w) // 2),
            viewport[1] + max(0, (viewport[3] - arena_h) // 2),
            arena_w,
            arena_h,
        )

    # The timeline occupies the top of the footer band and pushes the text
    # columns and graph below it. It is omitted (degenerate zero-size rect)
    # whenever the footer itself had to be clipped -- the same "only when the
    # band is at its full designed height" guard show_graph already uses --
    # so a pathologically short window degrades instead of overlapping.
    show_timeline = footer_h == FOOTER_HEIGHT
    timeline_rect: Rect = (
        FOOTER_PADDING,
        footer_y + FOOTER_PADDING,
        max(0, window_w - 2 * FOOTER_PADDING) if show_timeline else 0,
        FOOTER_TIMELINE_HEIGHT if show_timeline else 0,
    )
    content_offset = FOOTER_PADDING + FOOTER_TIMELINE_BLOCK if show_timeline else 0
    content_y = footer_y + content_offset

    show_graph = window_w >= FOOTER_GRAPH_MIN_WINDOW_WIDTH and footer_h == FOOTER_HEIGHT
    graph_w = FOOTER_GRAPH_WIDTH if show_graph else 0
    graph_h = footer_h - content_offset - FOOTER_PADDING if show_graph else 0
    graph_rect: Rect = (
        max(0, window_w - graph_w - FOOTER_PADDING),
        content_y,
        graph_w,
        max(0, graph_h),
    )
    text_w = max(0, graph_rect[0] - FOOTER_PADDING * 2) if show_graph else max(0, window_w - FOOTER_PADDING * 2)
    footer_text_rect: Rect = (FOOTER_PADDING, content_y, text_w, max(0, footer_h - content_offset))

    return ViewerLayout(
        window_size=(window_w, window_h),
        header_rect=header_rect,
        entrant_card_rects=tuple(card_rects),
        card_mode=card_mode,
        card_columns=columns,
        card_rows=rows,
        top_band_height=top_h,
        arena_viewport_rect=viewport,
        arena_rect=arena_rect,
        arena_scale=arena_scale,
        footer_text_rect=footer_text_rect,
        footer_timeline_rect=timeline_rect,
        footer_graph_rect=graph_rect,
        footer_height=footer_h,
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


def entrant_card_known(
    status: EntrantReplayStatus,
    *,
    selected_entrant_id: str | None,
    is_terminal: bool,
) -> bool:
    """Whether ``status``'s life/core/score/territory/kills fields may show
    their real canonical values on an entrant card (Phase 8.5).

    This is the remediation for the leak Phase 8 §11.1 disclosed and left
    unfixed: "the existing top-band cards show canonical core/territory/
    score/kills for every entrant, unchanged, in Perspective mode."
    ``selected_entrant_id`` is ``None`` in Broadcast, where nothing is ever
    hidden. The selected entrant's own card (``status.agent_id ==
    selected_entrant_id``) is always known -- an entrant is never "spied on"
    by itself, so its own life/core/score/territory/kills are its own facts,
    not an opponent's. Every card is also known once the match has reached
    its terminal tick: this is the same "the whole match is over, there is
    no more hidden gameplay to protect" boundary the Director's
    ``TERMINAL_HOLD`` override (Phase 7 §3) and Fight Night's result card
    (Phase 8 §12) already use, reused here rather than inventing a second
    terminal concept -- callers should pass ``tick >=
    SpectatorDerivation.result_ticks`` for ``is_terminal``, exactly what
    ``FightNightManager.state_at_tick`` already computes for its own
    OPENING/LIVE/RESULT phase split.

    Every other card, at every other tick, is not known: the engine never
    delivers an opponent's core damage, territory, score, kill count, or
    lifecycle change to a Perspective viewer (all eight of
    ``CORE_CELL_LOST``, ``PROCESS_DISRUPTED``, ``AGENT_ELIMINATED``,
    ``AGENT_FORFEITED`` and friends are omniscient-only per Phase 3's
    ``visible_to`` computation -- Phase 7 §2), so presenting the canonical
    value would show the selected entrant a fact it has no basis to know.
    """
    if selected_entrant_id is None:
        return True
    if status.agent_id == selected_entrant_id:
        return True
    return is_terminal


def format_entrant_status_line(
    status: EntrantReplayStatus, *, max_chars: int | None = None, known: bool = True
) -> str:
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

    ``known=False`` (Phase 8.5, see :func:`entrant_card_known`) renders life
    state as ``UNKNOWN`` and core integrity as ``Core ?/N`` (``N`` -- the
    core's fixed size -- is a Ruleset-wide constant, never a secret; only the
    *intact count* is hidden) instead of this entrant's real canonical
    values -- the least-misleading presentation available, since Perspective
    mode has no entrant-safe substitute value to show instead.
    """
    if not known:
        core = status.core
        core_clause = f"Core ?/{core.total_cells}" if core is not None else None
        full = f"UNKNOWN | {core_clause}" if core_clause else "UNKNOWN"
        return truncate_with_ellipsis(full, max_chars)

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


def format_entrant_stats_line(
    status: EntrantReplayStatus, *, max_chars: int | None = None, known: bool = True
) -> str:
    """One entrant's score/territory/kills line, in that priority order
    (Phase 4N: score outranks territory outranks kills). When ``max_chars``
    forces a choice, the lowest-priority clause is dropped first: kills,
    then the territory percentage refinement, then territory itself,
    leaving score as the last thing ever dropped (and even then only
    ellipsis-truncated, never omitted outright).

    ``known=False`` (Phase 8.5, see :func:`entrant_card_known`) replaces all
    three values with ``?`` placeholders. Unlike life/core state, none of
    score, territory or kills has *any* entrant-safe equivalent anywhere in
    ``PerspectiveState`` -- there is no semantic event for "your opponent's
    score changed" -- so there is no qualified alternative value to show
    instead of a placeholder.
    """
    if not known:
        candidates = ["Score ? | Territory ? | Kills ?", "Score ? | Territory ?", "Score ?"]
        if max_chars is None:
            return candidates[0]
        for candidate in candidates:
            if len(candidate) <= max_chars:
                return candidate
        return truncate_with_ellipsis(candidates[-1], max_chars)

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
    status: EntrantReplayStatus,
    *,
    max_chars: int | None = None,
    ordinal: int | None = None,
    mode: CardMode = "detailed",
    known: bool = True,
) -> tuple[str, ...]:
    """One entrant card's detailed or compact text lines.

    ``ordinal`` is a presentation-only recorded-order badge (``#1``,
    ``#2``, …), used alongside the real agent id/name so identification
    remains possible after the four-color palette is exhausted. It is shown
    for every entrant rather than appearing suddenly at entrant five.

    Detailed cards preserve the existing three-line hierarchy. Compact cards
    retain identity on line one and textual life/core/score state on line two;
    lower-priority name/core/score clauses yield deliberately as width narrows,
    while the ordinal+agent id and Alive/Dead/CAPTURED state remain last.

    ``known`` (Phase 8.5, see :func:`entrant_card_known`) never affects the
    identity line -- an entrant's display name, ordinal badge and agent id
    are public roster metadata (the established Phase 4-8 policy: a
    Perspective viewer may already know who is participating even when
    on-arena contact identity stays anonymous), never derived from
    engine-delivered knowledge, so there is nothing to hide there. It is
    threaded through to :func:`format_entrant_status_line` and
    :func:`format_entrant_stats_line` for the detailed card, and applied
    directly to the equivalent compact-card fields below.
    """

    bare_identity = status.name.upper()
    token = f"#{ordinal} {status.agent_id}" if ordinal is not None else status.agent_id
    identity = f"{token} · {bare_identity}" if ordinal is not None else bare_identity
    identity = truncate_with_ellipsis(identity, max_chars)
    if mode == "detailed":
        return (
            identity,
            format_entrant_status_line(status, max_chars=max_chars, known=known),
            format_entrant_stats_line(status, max_chars=max_chars, known=known),
        )

    core = status.core
    if not known:
        life = "UNKNOWN"
        core_part = f"Core ?/{core.total_cells}" if core is not None else None
        score_part = "Score ?"
    else:
        captured = core is not None and core.captured
        life = "CAPTURED" if captured else ("Alive" if status.alive else "Dead")
        core_part = f"Core {core.intact_cells}/{core.total_cells}" if core is not None else None
        score_part = f"Score {status.score:g}"
    candidates = [
        " | ".join(part for part in (life, core_part, score_part) if part),
        " | ".join(part for part in (life, core_part) if part),
        life,
    ]
    if max_chars is None:
        compact_status = candidates[0]
    else:
        compact_status = next(
            (candidate for candidate in candidates if len(candidate) <= max_chars),
            truncate_with_ellipsis(life, max_chars),
        )
    return identity, compact_status


COMPACT_HELP_TEXT = "Space play/pause · arrows step · drag timeline · ? controls"
# The footer's help panel is a fixed 3 lines (status + these 2) at the
# supported 640px-wide minimum, and this second line already sat at its
# character budget there before Phase 7 (see test_expanded_help_replaces_
# event_and_graph_without_covering_arena) -- Phase 6 dropped "drag timeline"
# from this line to make room for the perspective bindings rather than
# growing to an unsupported 4th line or a wider column (the compact hint
# above still advertises dragging). Phase 7's "G director" addition measured
# 5 characters of remaining slack at the 640px minimum before adding it
# (see the Phase 7 research document); if a future addition finds no slack
# left, drop something here rather than truncating silently.
#
# Phase 8 hit exactly that case: "N night" needs 10 characters against the 5
# that remained, so following the instruction above, "0 fit" was dropped
# rather than every other binding being abbreviated down to a zero-slack
# line. Zoom-to-fit stays bound to `0`; it is simply no longer advertised
# here, being both the viewer's own default state and adjacent to the `[/]`
# zoom hint that is still listed. The line now measures 86 characters
# against the 89-character budget at the 640px minimum -- 3 to spare.
EXPANDED_HELP_LINES = (
    "Space play/pause · arrows step · Shift+arrows seek 10 · Home/End first/last · Esc/Q quit",
    "+/- speed · [/] zoom · T trails · V/1-9 persp · D/F3 debug · G dir · N night · ? close",
)


def format_help_lines(*, expanded: bool) -> tuple[str, ...]:
    """Compact always-visible help or the two-line footer help panel."""

    return EXPANDED_HELP_LINES if expanded else (COMPACT_HELP_TEXT,)


def format_terminal_state_line(
    *, winner: str | None, termination_reason: str | None, result_available: bool
) -> str:
    """Prominent text for an already-authoritative replay terminal result.

    This does not infer a winner or termination condition. It only labels the
    result fields already loaded by :class:`ReplaySession` and keeps the same
    historical no-winner-as-tie presentation used by the prior HUD.
    """

    if not result_available:
        return ""
    outcome = f"Winner: {winner}" if winner is not None else "Draw / tie"
    reason = (termination_reason or "unknown").replace("_", " ")
    return f"MATCH COMPLETE — {outcome} — {reason}"


def format_match_header_lines(
    *,
    ruleset_label: str,
    runtime_kind: str,
    arena_size: int,
    entrant_count: int,
    winner: str | None,
    termination_reason: str | None,
    result_available: bool,
    view_label: str | None = None,
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
    view_part = f"entrants {entrant_count}" if view_label is None else view_label
    line1 = (
        f"Bytefray Replay — Ruleset {ruleset_label}  |  runtime {runtime_kind}  |  "
        f"arena {arena_size}  |  {view_part}"
    )
    line2 = format_terminal_state_line(
        winner=winner,
        termination_reason=termination_reason,
        result_available=result_available,
    )
    return (line1, line2)


def format_playback_line(
    *,
    tick: int,
    final_tick: int | None,
    status_label: str,
    speed: float,
    director_label: str | None = None,
) -> str:
    """The footer's first line: current tick / total, playback state, speed.

    ``director_label`` (Phase 7), when given, is appended as a short
    restrained suffix rather than a new footer line -- the footer's line
    budget is already fully used at the documented 640x480 minimum (see the
    Phase 6 research document), so a Director indicator piggybacks on this
    existing line instead of claiming one of its own. It is the last thing
    in the string, so the existing tick/status/speed information -- already
    relied on by manual QA and clicks -- survives truncation on an
    undersized window; only the suffix itself is at risk of being clipped.
    """
    total = "?" if final_tick is None else str(final_tick)
    line = f"Tick {tick}/{total}   [{status_label}]   speed {speed:g}x"
    if director_label:
        line += f"   {director_label}"
    return line


# ---------------------------------------------------------------------------
# Fight Night presentation (Phase 8) -- pure geometry and text, no drawing.
#
# Every function below is an *overlay* computation: Fight Night reserves no
# band of its own and ``calculate_layout`` is completely untouched by it, so
# turning Fight Night on never shrinks the arena, never re-flows the entrant
# cards, and never moves the footer. This follows the already-qualified
# core-capture callout's precedent (see ``pygame_renderer._draw_capture_
# callout``) rather than growing the HUD: at the documented 640x480 minimum a
# four-entrant detailed card grid already sits within 4px of the top band's
# cap, so a reserved ribbon band there would silently re-flow that layout.
# ---------------------------------------------------------------------------
FIGHT_NIGHT_LINE_HEIGHT = 15
FIGHT_NIGHT_PADDING = 6
FIGHT_NIGHT_RIBBON_MAX_WIDTH = 260
FIGHT_NIGHT_CARD_MAX_WIDTH = 420

# Below this viewport height the ribbon is dropped entirely rather than
# squeezed: a two-line ribbon over a very short arena band obscures more than
# it explains. Above it, the ribbon is capped to whatever whole lines fit.
FIGHT_NIGHT_MIN_VIEWPORT_HEIGHT = 120

# The narrowest letterbox column the ribbon will move into rather than
# overlay the arena. 150px is ~19 monospace HUD characters, which fits every
# label in the ribbon vocabulary once the droppable tick prefix is shed (the
# longest, "A · FIRST HOSTILE WRITE", is 23 characters and truncates
# gracefully below that). Narrower than this the ribbon would be shedding
# text to avoid covering cells it barely covers anyway, so it overlays
# instead.
FIGHT_NIGHT_MIN_GUTTER_WIDTH = 150


def fight_night_ribbon_capacity(viewport_rect: Rect, requested: int) -> int:
    """How many ribbon lines actually fit above ``viewport_rect``'s bottom.

    Graceful degradation for small windows (Phase 8 brief Sec. 34): the
    ribbon shrinks line by line and then disappears, rather than either
    overflowing the arena band or forcing a larger minimum window. The
    header line is counted, so a return of ``0`` means "not even a titled
    single-entry ribbon fits".
    """

    _vx, _vy, vw, vh = viewport_rect
    if vw < 200 or vh < FIGHT_NIGHT_MIN_VIEWPORT_HEIGHT or requested <= 0:
        return 0
    # Half the viewport is the ceiling: the arena stays visually primary even
    # on a short band (Phase 8 brief Sec. 33).
    budget = min(vh // 2, vh - FIGHT_NIGHT_PADDING * 2)
    fits = budget // FIGHT_NIGHT_LINE_HEIGHT - 1  # -1 for the header line
    return max(0, min(requested, fits))


def fight_night_ribbon_rect(
    viewport_rect: Rect, line_count: int, arena_rect: Rect | None = None
) -> Rect:
    """The ribbon's rect, preferring the arena's own letterbox gutter.

    Bottom-left rather than centered or top-anchored: the top band already
    carries the entrant cards and the match header, the footer is at its
    line budget, and the arena's own action is centered -- so the lower-left
    corner is the least contended real estate on screen.

    When ``arena_rect`` is supplied, the ribbon is placed in the empty
    letterbox column to the *left of the arena* whenever that column is wide
    enough to be useful. The arena is drawn at an integer cell scale centered
    in its band, so a horizontal gutter is the normal case rather than a
    lucky one: measured across the supported window sizes and entrant counts,
    that column runs 130-320px wide while the gutter *below* the arena is
    only ever 0-6px. Preferring it means the ribbon covers no battlefield
    cell at all in the ordinary case, honoring the standing "the arena shows
    the battle, the HUD explains the battle" rule rather than merely staying
    inside the band. A window whose arena already spans the full width (no
    gutter) falls back to overlaying the band's lower-left corner, which is
    the same tradeoff the already-qualified core-capture callout makes
    against the top band.

    Returns a degenerate (zero-size) rect when nothing fits, which every
    drawing caller already treats as "skip".
    """

    vx, vy, vw, vh = viewport_rect
    if line_count <= 0 or vw <= 0 or vh <= 0:
        return (vx, vy, 0, 0)
    height = FIGHT_NIGHT_PADDING * 2 + (line_count + 1) * FIGHT_NIGHT_LINE_HEIGHT
    height = min(height, vh)
    width = min(FIGHT_NIGHT_RIBBON_MAX_WIDTH, max(0, vw - FIGHT_NIGHT_PADDING * 2))

    if arena_rect is not None:
        gutter = max(0, arena_rect[0] - vx - FIGHT_NIGHT_PADDING * 2)
        if gutter >= FIGHT_NIGHT_MIN_GUTTER_WIDTH:
            width = min(width, gutter)

    return (vx + FIGHT_NIGHT_PADDING, vy + vh - height - FIGHT_NIGHT_PADDING, width, height)


def fight_night_card_rect(viewport_rect: Rect, line_count: int) -> Rect:
    """The opening/result card's rect: centered in the arena band.

    A card is shown only at the first tick or at/after the result tick --
    never during live play -- so centering it costs no mid-match visibility.
    """

    vx, vy, vw, vh = viewport_rect
    if line_count <= 0 or vw <= 0 or vh <= 0:
        return (vx, vy, 0, 0)
    height = min(vh, FIGHT_NIGHT_PADDING * 2 + line_count * FIGHT_NIGHT_LINE_HEIGHT)
    width = min(FIGHT_NIGHT_CARD_MAX_WIDTH, max(0, vw - FIGHT_NIGHT_PADDING * 2))
    return (vx + (vw - width) // 2, vy + max(0, (vh - height) // 2), width, height)


def format_fight_night_ribbon_title(visibility_basis: str) -> str:
    """The ribbon's own header line, naming its information domain out loud.

    Phase 8 brief Sec. 18 forbids an ambiguous middle state between "these
    are broadcast facts" and "this is what the selected entrant knows". The
    ribbon resolves that by *saying which it is* on every frame it is
    visible, rather than relying on the viewer to remember which view mode
    they selected.
    """

    if visibility_basis.startswith("perspective:"):
        entrant = visibility_basis.split(":", 1)[1]
        return f"FIGHT NIGHT · {entrant} KNOWS"
    return "FIGHT NIGHT · BROADCAST"


def format_fight_night_ribbon_line(
    label: str,
    subject: str | None,
    tick: int,
    *,
    max_chars: int | None = None,
) -> str:
    """One ribbon entry: ``T12 A · CORE CELL LOST``.

    Names at most one entrant, by construction -- ``subject`` is a single
    optional id and there is no second slot to put a counterparty in. When
    ``max_chars`` forces a choice the tick prefix is dropped first (it is the
    lowest-value clause; the ribbon is ordered anyway), then the text is
    ellipsis-truncated, so the label itself survives longest.
    """

    who = f"{subject} · " if subject else ""
    full = f"T{tick} {who}{label}"
    if max_chars is None or len(full) <= max_chars:
        return full
    without_tick = f"{who}{label}"
    if len(without_tick) <= max_chars:
        return without_tick
    return truncate_with_ellipsis(without_tick, max_chars)


def format_fight_night_opening_lines(
    entrants: Sequence[str],
    names: Mapping[str, str],
    *,
    ruleset_label: str,
    max_chars: int | None = None,
) -> tuple[str, ...]:
    """The pre-match opening card's lines.

    Deliberately one line per entrant rather than a single "A vs B vs C vs D"
    string: at the documented 640x480 minimum a four-entrant single line with
    realistic display names does not fit, and wrapping it would put the
    breaks in arbitrary places. One line each also lets each name truncate
    independently instead of the last entrant losing its whole name.
    """

    lines = ["BYTEFRAY FIGHT NIGHT", ""]
    for index, entrant in enumerate(entrants):
        if index:
            lines.append("vs")
        display = names.get(entrant, entrant)
        lines.append(truncate_with_ellipsis(f"{entrant} · {display.upper()}", max_chars))
    lines.append("")
    lines.append(truncate_with_ellipsis(f"Ruleset {ruleset_label}", max_chars))
    return tuple(lines)


def format_fight_night_result_lines(
    *,
    winner: str | None,
    termination_reason: str | None,
    result_ticks: int,
    survivors: Sequence[str],
    names: Mapping[str, str],
    max_chars: int | None = None,
) -> tuple[str, ...]:
    """The end-of-match result card's lines.

    Every value shown is already publicly qualified: the winner and
    termination reason come from the canonical replay's own result record
    (via the Fight Night plan), and ``survivors`` is the caller's
    already-derived alive set. Nothing is inferred here, and a match with no
    winner is reported as a draw exactly the way
    :func:`format_terminal_state_line` already reports it, rather than
    inventing a different wording for the same fact.
    """

    outcome = (
        f"WINNER · {names.get(winner, winner).upper()}" if winner is not None else "DRAW / TIE"
    )
    lines = [
        "MATCH COMPLETE",
        "",
        truncate_with_ellipsis(outcome, max_chars),
        truncate_with_ellipsis((termination_reason or "unknown").replace("_", " "), max_chars),
        truncate_with_ellipsis(f"tick {result_ticks}", max_chars),
    ]
    if survivors:
        joined = ", ".join(survivors)
        lines.append(truncate_with_ellipsis(f"survivors: {joined}", max_chars))
    return tuple(lines)


# ---------------------------------------------------------------------------
# Match-timeline coordinate math -- pure, inverse-consistent, no drawing.
# Both directions are deliberately defined over the *whole* match (first to
# final recorded tick), so the track always represents the same span no
# matter where playback currently is.
# ---------------------------------------------------------------------------
def timeline_x_for_tick(tick: int, first_tick: int, final_tick: int, rect: Rect) -> int:
    """The x pixel inside ``rect`` that represents ``tick``.

    Clamped into ``rect`` horizontally, so an out-of-range tick pins to an
    end rather than drawing outside the track. A single-tick replay
    (``final_tick == first_tick``) has no span to divide by and reports the
    track's right edge, matching "this replay is entirely complete".
    """
    rx, _ry, rw, _rh = rect
    if rw <= 0:
        return rx
    span = final_tick - first_tick
    if span <= 0:
        return rx + rw - 1
    fraction = min(1.0, max(0.0, (tick - first_tick) / span))
    return rx + round(fraction * (rw - 1))


def timeline_tick_for_x(x: int, first_tick: int, final_tick: int, rect: Rect) -> int | None:
    """The tick a click/drag at horizontal position ``x`` selects.

    The inverse of :func:`timeline_x_for_tick`, clamped to the replay's
    recorded range so a drag that leaves the track's ends still resolves to
    its first/final tick instead of an impossible one. Returns ``None`` only
    for a degenerate (zero-width) track -- i.e. a footer too short to show a
    timeline at all. The result is a tick *number*, not necessarily a
    *recorded* tick: a caller seeking a possibly-sparse legacy replay must
    still snap it (see ``battle_client.analysis.nearest_recorded_tick``).
    """
    rx, _ry, rw, _rh = rect
    if rw <= 0:
        return None
    fraction = min(1.0, max(0.0, (x - rx) / (rw - 1))) if rw > 1 else 0.0
    return first_tick + round(fraction * (final_tick - first_tick))


def timeline_contains(rect: Rect, pos: tuple[int, int], *, grab_padding: int = 3) -> bool:
    """Whether a click at ``pos`` should be treated as grabbing the track.

    ``grab_padding`` widens the vertical hit area only: a 10px-tall strip is
    an unforgiving mouse target, and the rows immediately above/below it are
    footer padding that no other control claims. Horizontally the track is
    already full width, so it is matched exactly. Always ``False`` for a
    degenerate rect.
    """
    rx, ry, rw, rh = rect
    if rw <= 0 or rh <= 0:
        return False
    return rx <= pos[0] < rx + rw and ry - grab_padding <= pos[1] < ry + rh + grab_padding


__all__ = [
    "CARD_GAP",
    "CARD_LINES",
    "CARD_LINE_HEIGHT",
    "CARD_PADDING_X",
    "COMPACT_CARD_LINES",
    "COMPACT_CARD_MIN_WIDTH",
    "COMPACT_HELP_TEXT",
    "DETAILED_CARD_MIN_WIDTH",
    "EXPANDED_HELP_LINES",
    "FIGHT_NIGHT_CARD_MAX_WIDTH",
    "FIGHT_NIGHT_LINE_HEIGHT",
    "FIGHT_NIGHT_MIN_GUTTER_WIDTH",
    "FIGHT_NIGHT_MIN_VIEWPORT_HEIGHT",
    "FIGHT_NIGHT_PADDING",
    "FIGHT_NIGHT_RIBBON_MAX_WIDTH",
    "FOOTER_GRAPH_MIN_WINDOW_WIDTH",
    "FOOTER_GRAPH_WIDTH",
    "FOOTER_HEIGHT",
    "FOOTER_LINES",
    "FOOTER_LINE_HEIGHT",
    "FOOTER_PADDING",
    "FOOTER_TIMELINE_BLOCK",
    "FOOTER_TIMELINE_GAP",
    "FOOTER_TIMELINE_HEIGHT",
    "HEADER_LINES",
    "HEADER_LINE_HEIGHT",
    "MAX_TOP_BAND_FRACTION",
    "MIN_USEFUL_ARENA_HEIGHT",
    "MIN_VIEWER_SIZE",
    "TOP_BAND_HEIGHT",
    "TOP_BAND_PADDING",
    "CardMode",
    "Rect",
    "ViewerLayout",
    "calculate_layout",
    "entrant_card_known",
    "fight_night_card_rect",
    "fight_night_ribbon_capacity",
    "fight_night_ribbon_rect",
    "format_entrant_card_lines",
    "format_entrant_stats_line",
    "format_entrant_status_line",
    "format_fight_night_opening_lines",
    "format_fight_night_result_lines",
    "format_fight_night_ribbon_line",
    "format_fight_night_ribbon_title",
    "format_help_lines",
    "format_match_header_lines",
    "format_playback_line",
    "format_terminal_state_line",
    "integer_scale_to_fit",
    "timeline_contains",
    "timeline_tick_for_x",
    "timeline_x_for_tick",
    "truncate_with_ellipsis",
]
