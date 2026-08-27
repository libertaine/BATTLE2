"""Beta1 Phase 4: ``battle_client.hud_layout`` acceptance coverage.

Geometry tests operate purely on ``calculate_layout``'s returned rects
(no Pygame, no window) -- the governing task's explicit preference over
pixel-perfect screenshot testing. Formatting tests construct
``battle_client.replay_status.EntrantReplayStatus``/``CoreStatus`` objects
directly (the Phase-3 status model's own types) rather than reconstructing
replay semantics by hand -- per the governing task's Phase 4T guidance.
"""

from __future__ import annotations

from itertools import combinations

import pytest
from battle_client.hud_layout import (
    COMPACT_HELP_TEXT,
    EXPANDED_HELP_LINES,
    FOOTER_GRAPH_MIN_WINDOW_WIDTH,
    FOOTER_HEIGHT,
    FOOTER_PADDING,
    MAX_TOP_BAND_FRACTION,
    MIN_USEFUL_ARENA_HEIGHT,
    MIN_VIEWER_SIZE,
    TOP_BAND_HEIGHT,
    calculate_layout,
    format_entrant_card_lines,
    format_entrant_stats_line,
    format_entrant_status_line,
    format_help_lines,
    format_match_header_lines,
    format_playback_line,
    format_terminal_state_line,
    integer_scale_to_fit,
    timeline_contains,
    timeline_tick_for_x,
    timeline_x_for_tick,
    truncate_with_ellipsis,
)
from battle_client.replay_status import CoreStatus, EntrantReplayStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _core(
    *,
    intact=8,
    total=8,
    captured=False,
    capture_tick=None,
    addresses=(0, 1, 2, 3, 4, 5, 6, 7),
) -> CoreStatus:
    return CoreStatus(
        core_addresses=addresses,
        total_cells=total,
        intact_cells=intact,
        damaged_cells=total - intact,
        integrity_fraction=(intact / total) if total else 0.0,
        captured=captured,
        capture_tick=capture_tick,
    )


def _status(
    *,
    agent_id="A",
    name="Claimer",
    order=0,
    alive=True,
    death_tick=None,
    death_reason=None,
    killer_id=None,
    core=None,
    tick=84,
    score=1842,
    territory_cells=1130,
    territory_percentage=44.1,
    kills_so_far=0,
    start_address=None,
) -> EntrantReplayStatus:
    return EntrantReplayStatus(
        agent_id=agent_id,
        name=name,
        order=order,
        start_address=start_address,
        alive=alive,
        death_tick=death_tick,
        death_reason=death_reason,
        killer_id=killer_id,
        core=core,
        tick=tick,
        score=score,
        territory_cells=territory_cells,
        territory_percentage=territory_percentage,
        kills_so_far=kills_so_far,
    )


def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return False
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


# ---------------------------------------------------------------------------
# calculate_layout: two entrants
# ---------------------------------------------------------------------------
def test_two_entrant_bands_do_not_overlap():
    layout = calculate_layout((960, 700), 2)
    assert not _overlaps(layout.header_rect, layout.arena_rect)
    for card in layout.entrant_card_rects:
        assert not _overlaps(card, layout.arena_rect)
    assert not _overlaps(layout.arena_rect, layout.footer_text_rect)
    assert not _overlaps(layout.arena_rect, layout.footer_graph_rect)
    assert not _overlaps(layout.footer_text_rect, layout.footer_graph_rect)
    assert len(layout.entrant_card_rects) == 2
    assert not _overlaps(layout.entrant_card_rects[0], layout.entrant_card_rects[1])


def test_two_entrant_arena_within_window():
    layout = calculate_layout((960, 700), 2)
    ax, ay, aw, ah = layout.arena_rect
    ww, wh = layout.window_size
    assert 0 <= ax and ax + aw <= ww
    assert 0 <= ay and ay + ah <= wh


# ---------------------------------------------------------------------------
# calculate_layout: three entrants
# ---------------------------------------------------------------------------
def test_three_entrant_bands_do_not_overlap():
    layout = calculate_layout((960, 700), 3)
    assert len(layout.entrant_card_rects) == 3
    cards = layout.entrant_card_rects
    for card in cards:
        assert not _overlaps(card, layout.arena_rect)
    assert not _overlaps(cards[0], cards[1])
    assert not _overlaps(cards[1], cards[2])
    assert not _overlaps(cards[0], cards[2])
    assert not _overlaps(layout.arena_rect, layout.footer_text_rect)
    assert not _overlaps(layout.arena_rect, layout.footer_graph_rect)


def test_three_entrant_cards_have_valid_positive_size():
    layout = calculate_layout((960, 700), 3)
    for x, y, w, h in layout.entrant_card_rects:
        assert w > 0
        assert h > 0
        assert x >= 0
        assert y >= 0


def test_three_entrant_cards_tile_left_to_right_in_order():
    layout = calculate_layout((960, 700), 3)
    xs = [rect[0] for rect in layout.entrant_card_rects]
    assert xs == sorted(xs)


def test_entrant_card_rects_stay_inside_hud_and_never_overlap():
    for count in (1, 2, 3, 4, 5, 8):
        layout = calculate_layout((900, 700), count)
        cards = layout.entrant_card_rects
        assert len(cards) == count
        for x, y, width, height in cards:
            assert 0 <= x <= layout.window_size[0]
            assert x + width <= layout.window_size[0]
            assert 0 <= y <= layout.top_band_height
            assert y + height <= layout.top_band_height
        for left, right in combinations(cards, 2):
            assert not _overlaps(left, right)


def test_entrant_count_below_one_is_clamped_to_one_card():
    layout = calculate_layout((900, 700), 0)
    assert len(layout.entrant_card_rects) == 1


# ---------------------------------------------------------------------------
# calculate_layout: resize / minimum size
# ---------------------------------------------------------------------------
def test_larger_window_increases_or_maintains_arena_size():
    small = calculate_layout((960, 700), 2)
    large = calculate_layout((1400, 1000), 2)
    assert large.arena_rect[2] >= small.arena_rect[2]
    assert large.arena_rect[3] >= small.arena_rect[3]


def test_minimum_window_size_never_produces_negative_arena():
    layout = calculate_layout((100, 80), 3)
    _ax, _ay, aw, ah = layout.arena_rect
    assert aw >= 0
    assert ah >= 0
    # Bands still tile without overlap even in this degenerate case.
    assert not _overlaps(layout.arena_rect, layout.footer_text_rect)


def test_footer_and_top_band_heights_leave_room_for_a_reasonable_arena():
    # A window sized for the default preferred arena viewport (960x600)
    # plus the fixed band chrome should have an arena at least that tall.
    layout = calculate_layout((960, TOP_BAND_HEIGHT + 600 + FOOTER_HEIGHT), 2)
    assert layout.arena_rect[3] == 600


# ---------------------------------------------------------------------------
# calculate_layout: footer graph visibility
# ---------------------------------------------------------------------------
def test_footer_graph_omitted_below_min_window_width():
    layout = calculate_layout((FOOTER_GRAPH_MIN_WINDOW_WIDTH - 1, 700), 2)
    assert layout.footer_graph_rect[2] == 0
    assert layout.footer_graph_rect[3] == 0


def test_footer_graph_shown_at_or_above_min_window_width():
    layout = calculate_layout((FOOTER_GRAPH_MIN_WINDOW_WIDTH, 700), 2)
    assert layout.footer_graph_rect[2] > 0
    assert layout.footer_graph_rect[3] > 0
    assert not _overlaps(layout.footer_graph_rect, layout.footer_text_rect)


# ---------------------------------------------------------------------------
# Beta3 Phase 2: responsive cards, HUD cap, and centered integer arena
# ---------------------------------------------------------------------------
def test_supported_minimum_is_derived_from_detailed_cards_footer_and_arena():
    layout = calculate_layout(MIN_VIEWER_SIZE, 2, (64, 64))

    assert MIN_VIEWER_SIZE == (640, 480)
    assert layout.card_mode == "detailed"
    assert (layout.card_columns, layout.card_rows) == (2, 1)
    assert all(card[2] >= 300 for card in layout.entrant_card_rects)
    assert layout.footer_height == FOOTER_HEIGHT
    assert layout.arena_viewport_rect[3] >= MIN_USEFUL_ARENA_HEIGHT


def test_three_entrant_layout_reflows_between_wide_and_minimum_windows():
    wide = calculate_layout((960, 640), 3, (32, 16))
    minimum = calculate_layout(MIN_VIEWER_SIZE, 3, (32, 16))

    assert (wide.card_mode, wide.card_columns, wide.card_rows) == ("detailed", 3, 1)
    assert (minimum.card_mode, minimum.card_columns, minimum.card_rows) == (
        "detailed",
        2,
        2,
    )


def test_four_entrant_layout_is_one_row_wide_and_two_by_two_at_minimum():
    wide = calculate_layout((960, 640), 4, (32, 16))
    minimum = calculate_layout(MIN_VIEWER_SIZE, 4, (32, 16))

    assert (wide.card_mode, wide.card_columns, wide.card_rows) == ("detailed", 4, 1)
    assert (minimum.card_mode, minimum.card_columns, minimum.card_rows) == (
        "detailed",
        2,
        2,
    )


def test_five_plus_entrants_use_dense_compact_roster_grid():
    five = calculate_layout(MIN_VIEWER_SIZE, 5, (32, 16))
    twelve = calculate_layout(MIN_VIEWER_SIZE, 12, (32, 16))

    assert (five.card_mode, five.card_columns, five.card_rows) == ("compact", 3, 2)
    assert twelve.card_mode == "compact"
    assert twelve.card_columns == 4
    assert twelve.card_rows == 3
    assert len(twelve.entrant_card_rects) == 12


def test_hud_height_is_capped_and_preserves_useful_arena_at_supported_size():
    layout = calculate_layout(MIN_VIEWER_SIZE, 20, (64, 64))
    proportional_cap = int(MIN_VIEWER_SIZE[1] * MAX_TOP_BAND_FRACTION)

    assert layout.top_band_height <= proportional_cap
    assert layout.arena_viewport_rect[3] >= MIN_USEFUL_ARENA_HEIGHT
    assert layout.top_band_height + layout.arena_viewport_rect[3] + layout.footer_height == 480


def test_centered_arena_uses_largest_uniform_integer_scale():
    layout = calculate_layout((1000, 700), 3, (32, 16))
    vx, vy, vw, vh = layout.arena_viewport_rect
    ax, ay, aw, ah = layout.arena_rect

    assert layout.arena_scale == integer_scale_to_fit(32, 16, (vw, vh))
    assert aw == 32 * layout.arena_scale
    assert ah == 16 * layout.arena_scale
    assert ax == vx + (vw - aw) // 2
    assert ay == vy + (vh - ah) // 2
    assert not _overlaps(layout.arena_rect, layout.header_rect)
    assert not _overlaps(layout.arena_rect, layout.footer_text_rect)


def test_preferred_manual_scale_is_centered_and_capped_to_viewport():
    small = calculate_layout((960, 640), 2, (32, 16), preferred_arena_scale=4)
    too_large = calculate_layout((960, 640), 2, (32, 16), preferred_arena_scale=100)

    assert small.arena_scale == 4
    assert small.arena_rect[2:] == (128, 64)
    assert too_large.arena_scale == integer_scale_to_fit(
        32, 16, too_large.arena_viewport_rect[2:]
    )


def test_below_minimum_window_remains_bounded_and_non_overlapping():
    layout = calculate_layout((320, 180), 8, (64, 64))

    assert layout.window_size == (320, 180)
    assert layout.top_band_height <= int(180 * MAX_TOP_BAND_FRACTION)
    assert layout.arena_viewport_rect[3] >= 0
    for rect in (*layout.entrant_card_rects, layout.arena_rect, layout.footer_text_rect):
        x, y, width, height = rect
        assert 0 <= x <= 320 and x + width <= 320
        assert 0 <= y <= 180 and y + height <= 180
    assert not _overlaps(layout.arena_rect, layout.footer_text_rect)


# ---------------------------------------------------------------------------
# format_entrant_status_line: v1 (no core)
# ---------------------------------------------------------------------------
def test_v1_alive_entrant_has_no_core_field():
    status = _status(core=None, alive=True)
    line = format_entrant_status_line(status)
    assert line == "Alive"
    assert "Core" not in line
    assert "N/A" not in line


def test_v1_dead_entrant_has_no_core_field():
    status = _status(core=None, alive=False, death_tick=12)
    line = format_entrant_status_line(status)
    assert line == "Dead @ T12"
    assert "Core" not in line


def test_v1_dead_entrant_with_attributed_killer_shows_it():
    status = _status(core=None, alive=False, death_tick=12, killer_id="hunter")
    assert format_entrant_status_line(status) == "Dead @ T12 by hunter"


# ---------------------------------------------------------------------------
# format_entrant_status_line: v2 healthy/damaged/captured
# ---------------------------------------------------------------------------
def test_v2_healthy_core_shows_full_integrity():
    status = _status(core=_core(intact=8), alive=True)
    assert format_entrant_status_line(status) == "Alive | Core 8/8"


def test_v2_damaged_core_shows_reduced_integrity():
    status = _status(core=_core(intact=5), alive=True)
    assert format_entrant_status_line(status) == "Alive | Core 5/8"


def test_v2_captured_shows_capture_tick_and_zero_core():
    core = _core(intact=0, captured=True, capture_tick=84)
    status = _status(core=core, alive=False, death_tick=84, death_reason="core_captured")
    line = format_entrant_status_line(status)
    assert line == "CAPTURED @ T84 | Core 0/8"


def test_v2_captured_with_attribution_shows_killer():
    core = _core(intact=0, captured=True, capture_tick=84)
    status = _status(
        core=core, alive=False, death_tick=84, death_reason="core_captured", killer_id="core_tracker"
    )
    line = format_entrant_status_line(status)
    assert line == "CAPTURED @ T84 by core_tracker | Core 0/8"


def test_v2_captured_unattributed_shows_no_fake_killer():
    core = _core(intact=0, captured=True, capture_tick=84)
    status = _status(core=core, alive=False, death_tick=84, death_reason="core_captured", killer_id=None)
    line = format_entrant_status_line(status)
    assert "by" not in line
    assert line == "CAPTURED @ T84 | Core 0/8"


def test_v2_forfeit_death_is_not_worded_as_capture():
    core = _core(intact=6, captured=False)
    status = _status(core=core, alive=False, death_tick=9, death_reason="forfeit")
    line = format_entrant_status_line(status)
    assert "CAPTURED" not in line
    assert line == "Dead @ T9 | Core 6/8"


# ---------------------------------------------------------------------------
# format_entrant_status_line: truncation priority (killer dropped first)
# ---------------------------------------------------------------------------
def test_narrow_width_drops_killer_before_core_value():
    core = _core(intact=0, captured=True, capture_tick=84)
    status = _status(core=core, alive=False, killer_id="core_tracker")
    full = format_entrant_status_line(status)
    narrow = format_entrant_status_line(status, max_chars=len(full) - 1)
    assert "by core_tracker" not in narrow
    assert "Core 0/8" in narrow


def test_status_line_ellipsis_fallback_when_even_core_does_not_fit():
    core = _core(intact=0, captured=True, capture_tick=84)
    status = _status(core=core, alive=False, killer_id="core_tracker")
    truncated = format_entrant_status_line(status, max_chars=6)
    assert len(truncated) <= 6


# ---------------------------------------------------------------------------
# format_entrant_stats_line: score/territory/kills hierarchy
# ---------------------------------------------------------------------------
def test_stats_line_shows_score_territory_kills_in_priority_order():
    status = _status(score=1842, territory_cells=1130, territory_percentage=44.1, kills_so_far=2)
    line = format_entrant_stats_line(status)
    assert line == "Score 1842 | Territory 1130 (44.1%) | Kills 2"


def test_narrow_width_drops_kills_before_territory_percentage():
    status = _status(score=1842, territory_cells=1130, territory_percentage=44.1, kills_so_far=2)
    full = format_entrant_stats_line(status)
    narrow = format_entrant_stats_line(status, max_chars=len(full) - 1)
    assert "Kills" not in narrow
    assert "Territory 1130" in narrow


def test_narrower_width_drops_territory_percentage_before_territory_itself():
    status = _status(score=1842, territory_cells=1130, territory_percentage=44.1, kills_so_far=2)
    narrow = format_entrant_stats_line(status, max_chars=len("Score 1842 | Territory 1130"))
    assert "%" not in narrow
    assert "Territory 1130" in narrow


def test_score_is_never_dropped_even_at_minimal_width():
    status = _status(score=1842, territory_cells=1130, territory_percentage=44.1, kills_so_far=2)
    narrow = format_entrant_stats_line(status, max_chars=4)
    assert "Score" in narrow or narrow.startswith("Sco")


# ---------------------------------------------------------------------------
# format_entrant_card_lines: always three lines, long-name truncation
# ---------------------------------------------------------------------------
def test_card_lines_are_always_exactly_three():
    status = _status(core=_core(intact=8))
    lines = format_entrant_card_lines(status)
    assert len(lines) == 3


def test_card_name_line_is_uppercased():
    status = _status(name="claimer")
    lines = format_entrant_card_lines(status)
    assert lines[0] == "CLAIMER"


def test_long_name_truncates_with_ellipsis():
    status = _status(name="A Very Long Entrant Display Name Indeed")
    lines = format_entrant_card_lines(status, max_chars=12)
    assert len(lines[0]) <= 12
    assert lines[0].endswith("…")


def test_short_name_is_not_truncated():
    status = _status(name="Claimer")
    lines = format_entrant_card_lines(status, max_chars=40)
    assert lines[0] == "CLAIMER"


def test_recorded_order_badge_provides_non_color_identity_beyond_four():
    status = _status(agent_id="E", name="fifth entrant", order=4)
    lines = format_entrant_card_lines(status, ordinal=5, mode="compact", max_chars=40)

    assert lines[0].startswith("#5 E")
    assert "FIFTH ENTRANT" in lines[0]
    assert "Alive" in lines[1]


def test_compact_card_deliberately_keeps_token_and_text_state_when_narrow():
    status = _status(agent_id="entrant-five", name="A very long fifth entrant")
    identity, state = format_entrant_card_lines(
        status, ordinal=5, mode="compact", max_chars=12
    )

    assert len(identity) <= 12
    assert identity.startswith("#5")
    assert state == "Alive"


def test_compact_help_fits_minimum_footer_text_column_and_expands_to_two_lines():
    layout = calculate_layout(MIN_VIEWER_SIZE, 2, (64, 64))
    max_chars = layout.footer_text_rect[2] // 7
    compact = format_help_lines(expanded=False)
    expanded = format_help_lines(expanded=True)

    assert len(compact) == 1
    assert len(compact[0]) <= max_chars
    assert "? controls" in compact[0]
    assert len(expanded) == 2
    # Expanded help replaces the graph, so it has the full window text width.
    assert all(len(line) <= (MIN_VIEWER_SIZE[0] - 12) // 7 for line in expanded)


# ---------------------------------------------------------------------------
# truncate_with_ellipsis
# ---------------------------------------------------------------------------
def test_truncate_with_ellipsis_none_max_chars_is_unchanged():
    assert truncate_with_ellipsis("hello world", None) == "hello world"


def test_truncate_with_ellipsis_exact_fit_is_unchanged():
    assert truncate_with_ellipsis("hello", 5) == "hello"


def test_truncate_with_ellipsis_shortens_with_marker():
    result = truncate_with_ellipsis("hello world", 6)
    assert len(result) == 6
    assert result.endswith("…")


def test_truncate_with_ellipsis_degenerate_budget():
    assert truncate_with_ellipsis("hello", 0) == ""
    assert truncate_with_ellipsis("hello", 1) == "h"


# ---------------------------------------------------------------------------
# format_match_header_lines / format_playback_line
# ---------------------------------------------------------------------------
def test_match_header_shows_ruleset_runtime_arena_entrants():
    line1, _line2 = format_match_header_lines(
        ruleset_label="bytefray-rules-2",
        runtime_kind="python",
        arena_size=512,
        entrant_count=3,
        winner=None,
        termination_reason=None,
        result_available=False,
    )
    assert "bytefray-rules-2" in line1
    assert "python" in line1
    assert "512" in line1
    assert "3" in line1


def test_match_header_second_line_blank_until_result_available():
    _line1, line2 = format_match_header_lines(
        ruleset_label="bytefray-rules-1",
        runtime_kind="vm",
        arena_size=256,
        entrant_count=2,
        winner=None,
        termination_reason=None,
        result_available=False,
    )
    assert line2 == ""


def test_match_header_second_line_shows_winner_and_termination():
    _line1, line2 = format_match_header_lines(
        ruleset_label="bytefray-rules-1",
        runtime_kind="vm",
        arena_size=256,
        entrant_count=2,
        winner="A",
        termination_reason="last_agent_standing",
        result_available=True,
    )
    assert "Winner: A" in line2
    assert "MATCH COMPLETE" in line2
    assert "last agent standing" in line2


def test_terminal_state_helper_distinguishes_draw_without_inventing_winner():
    line = format_terminal_state_line(
        winner=None,
        termination_reason="tick_limit",
        result_available=True,
    )
    assert line == "MATCH COMPLETE — Draw / tie — tick limit"


def test_terminal_state_helper_is_blank_without_authoritative_result():
    assert (
        format_terminal_state_line(
            winner="A", termination_reason="last_agent_standing", result_available=False
        )
        == ""
    )


def test_match_header_distinguishes_v1_from_v2_label():
    v1_line, _ = format_match_header_lines(
        ruleset_label="bytefray-rules-1",
        runtime_kind="vm",
        arena_size=256,
        entrant_count=2,
        winner=None,
        termination_reason=None,
        result_available=False,
    )
    v2_line, _ = format_match_header_lines(
        ruleset_label="bytefray-rules-2",
        runtime_kind="python",
        arena_size=256,
        entrant_count=2,
        winner=None,
        termination_reason=None,
        result_available=False,
    )
    assert v1_line != v2_line
    assert "bytefray-rules-1" in v1_line
    assert "bytefray-rules-2" in v2_line


def test_playback_line_shows_tick_status_and_speed():
    line = format_playback_line(tick=84, final_tick=200, status_label="PAUSED", speed=1.0)
    assert line == "Tick 84/200   [PAUSED]   speed 1x"


def test_playback_line_handles_unknown_final_tick():
    line = format_playback_line(tick=0, final_tick=None, status_label="PLAYING", speed=2.0)
    assert "Tick 0/?" in line


# ---------------------------------------------------------------------------
# Match timeline (v3.0) -- see docs/V3_MATCH_TIMELINE.md.
# ---------------------------------------------------------------------------
def _footer_rects(layout):
    return {
        "timeline": layout.footer_timeline_rect,
        "text": layout.footer_text_rect,
        "graph": layout.footer_graph_rect,
    }


@pytest.mark.parametrize("window_size", [(640, 480), (800, 600), (960, 600), (1280, 800)])
@pytest.mark.parametrize("entrant_count", [1, 2, 3, 5, 12])
def test_footer_timeline_tiles_the_footer_without_overlapping_anything(
    window_size, entrant_count
):
    layout = calculate_layout(window_size, entrant_count, (32, 16))
    rects = _footer_rects(layout)
    timeline = rects["timeline"]

    assert timeline[2] > 0 and timeline[3] > 0
    # Strictly inside the footer band, so the arena above is never touched.
    footer_y = window_size[1] - layout.footer_height
    assert footer_y <= timeline[1]
    assert timeline[1] + timeline[3] <= window_size[1]
    assert not _overlaps(timeline, layout.arena_rect)
    assert not _overlaps(timeline, rects["text"])
    assert not _overlaps(timeline, rects["graph"])
    # The track sits above the text/graph columns it shares the band with.
    assert timeline[1] + timeline[3] <= rects["text"][1]


def test_footer_timeline_is_omitted_when_the_footer_had_to_be_clipped():
    """A window too short for a whole footer band degrades to no timeline
    rather than overlapping the text it would otherwise sit above -- the
    same guard the territory graph already uses."""
    layout = calculate_layout((640, FOOTER_HEIGHT - 10), 2, (32, 16))

    assert layout.footer_height < FOOTER_HEIGHT
    assert layout.footer_timeline_rect[2] == 0
    assert layout.footer_timeline_rect[3] == 0


def test_minimum_viewport_card_geometry_is_unchanged_by_the_timeline_band():
    """The timeline's height was chosen so the footer's growth is absorbed by
    _top_height_cap's arena reservation, not by re-flowing entrant cards.
    These are the pre-timeline grids at the supported 640x480 minimum."""
    assert calculate_layout(MIN_VIEWER_SIZE, 2, (32, 16)).card_columns == 2
    five = calculate_layout(MIN_VIEWER_SIZE, 5, (32, 16))
    assert (five.card_mode, five.card_columns, five.card_rows) == ("compact", 3, 2)
    twelve = calculate_layout(MIN_VIEWER_SIZE, 12, (32, 16))
    assert (twelve.card_mode, twelve.card_columns, twelve.card_rows) == ("compact", 4, 3)


@pytest.mark.parametrize("entrant_count", [1, 2, 3, 4, 5, 8, 12])
def test_arena_keeps_its_useful_height_floor_with_the_timeline_present(entrant_count):
    layout = calculate_layout(MIN_VIEWER_SIZE, entrant_count, (32, 16))

    assert layout.arena_viewport_rect[3] >= MIN_USEFUL_ARENA_HEIGHT


def test_timeline_x_for_tick_spans_the_whole_track():
    rect = (10, 0, 101, 6)

    assert timeline_x_for_tick(0, 0, 100, rect) == 10
    assert timeline_x_for_tick(50, 0, 100, rect) == 60
    assert timeline_x_for_tick(100, 0, 100, rect) == 110


def test_timeline_x_for_tick_clamps_an_out_of_range_tick_to_an_end():
    rect = (10, 0, 101, 6)

    assert timeline_x_for_tick(-40, 0, 100, rect) == 10
    assert timeline_x_for_tick(500, 0, 100, rect) == 110


def test_timeline_x_for_tick_uses_a_non_zero_first_tick_as_the_origin():
    """A sparse replay need not start at tick 0; the track still spans only
    what was actually recorded."""
    rect = (0, 0, 101, 6)

    assert timeline_x_for_tick(200, 200, 300, rect) == 0
    assert timeline_x_for_tick(300, 200, 300, rect) == 100


def test_timeline_x_for_tick_pins_a_single_tick_replay_to_the_track_end():
    assert timeline_x_for_tick(7, 7, 7, (0, 0, 50, 6)) == 49


def test_timeline_tick_for_x_inverts_timeline_x_for_tick():
    rect = (6, 0, 401, 6)

    for tick in (0, 1, 137, 399, 400):
        x = timeline_x_for_tick(tick, 0, 400, rect)
        assert timeline_tick_for_x(x, 0, 400, rect) == tick


def test_timeline_tick_for_x_clamps_a_drag_that_leaves_the_track():
    rect = (10, 0, 101, 6)

    assert timeline_tick_for_x(-999, 0, 100, rect) == 0
    assert timeline_tick_for_x(9999, 0, 100, rect) == 100


def test_timeline_helpers_are_safe_on_a_degenerate_track():
    """The omitted-timeline rect must never produce a division or an
    off-track coordinate."""
    degenerate = (6, 400, 0, 0)

    assert timeline_tick_for_x(50, 0, 100, degenerate) is None
    assert timeline_x_for_tick(50, 0, 100, degenerate) == 6
    assert timeline_contains(degenerate, (6, 400)) is False


def test_timeline_contains_matches_the_track_and_its_vertical_grab_margin():
    rect = (10, 100, 100, 6)

    assert timeline_contains(rect, (10, 100)) is True
    assert timeline_contains(rect, (109, 105)) is True
    # Just above/below the drawn track still grabs it (footer padding).
    assert timeline_contains(rect, (50, 97)) is True
    assert timeline_contains(rect, (50, 108)) is True
    # Further away, and outside it horizontally, does not.
    assert timeline_contains(rect, (50, 96)) is False
    assert timeline_contains(rect, (50, 110)) is False
    assert timeline_contains(rect, (9, 102)) is False
    assert timeline_contains(rect, (110, 102)) is False


def test_help_lines_still_fit_their_footer_columns_at_the_minimum_width():
    """Both help variants gained a timeline hint; neither may start
    ellipsising at the supported 640px minimum (see _draw_footer's own
    max_chars budget, which uses hud_layout-independent HUD_CHAR_WIDTH_PX=7)."""
    layout = calculate_layout(MIN_VIEWER_SIZE, 2, (32, 16))
    compact_budget = layout.footer_text_rect[2] // 7
    expanded_budget = (MIN_VIEWER_SIZE[0] - 2 * FOOTER_PADDING) // 7

    assert len(COMPACT_HELP_TEXT) <= compact_budget
    for line in EXPANDED_HELP_LINES:
        assert len(line) <= expanded_budget
