"""Beta1 Phase 4: ``battle_client.hud_layout`` acceptance coverage.

Geometry tests operate purely on ``calculate_layout``'s returned rects
(no Pygame, no window) -- the governing task's explicit preference over
pixel-perfect screenshot testing. Formatting tests construct
``battle_client.replay_status.EntrantReplayStatus``/``CoreStatus`` objects
directly (the Phase-3 status model's own types) rather than reconstructing
replay semantics by hand -- per the governing task's Phase 4T guidance.
"""

from __future__ import annotations

from itertools import pairwise

from battle_client.hud_layout import (
    FOOTER_GRAPH_MIN_WINDOW_WIDTH,
    FOOTER_HEIGHT,
    TOP_BAND_HEIGHT,
    calculate_layout,
    format_entrant_card_lines,
    format_entrant_stats_line,
    format_entrant_status_line,
    format_match_header_lines,
    format_playback_line,
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


def test_entrant_card_rects_tile_exactly_to_window_width():
    for count in (1, 2, 3, 4, 5):
        layout = calculate_layout((900, 700), count)
        cards = layout.entrant_card_rects
        assert len(cards) == count
        last_x, last_w = cards[-1][0], cards[-1][2]
        assert last_x + last_w <= layout.window_size[0]
        # No overlap between consecutive cards (a gutter is expected).
        for left, right in pairwise(cards):
            assert left[0] + left[2] <= right[0]


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
    assert "last_agent_standing" in line2


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
