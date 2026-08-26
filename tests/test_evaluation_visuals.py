"""GUI regression coverage for v3.0 Phase 3's visual evaluation widgets.

Constructs each widget from real (not mocked) ``battle_engine`` analysis
dataclasses and forces a real paint via ``.grab()`` -- catching any
QPainter-usage error the widget's own construction wouldn't surface, not
just checking that ``__init__`` doesn't raise.

Marked ``gui`` like the existing Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow (or run
directly on a real Windows session with ``-m gui``).
"""

from __future__ import annotations

import os

import pytest


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.mark.gui
def test_win_rate_bar_renders_three_segments_and_ci():
    _make_app()
    from battle_engine.evaluation_analysis import RateEstimate

    from app.widgets.evaluation_visuals import ProportionBar, win_rate_bar_data

    estimate = RateEstimate(
        scope_label="all", subject_role="candidate", subject_id="cand", matches_played=10, wins=7, losses=2, ties=1
    )
    data = win_rate_bar_data(estimate)
    assert len(data.segments) == 3
    assert data.ci is not None
    widget = ProportionBar(data)
    try:
        widget.resize(240, widget.minimumHeight())
        pixmap = widget.grab()
        assert not pixmap.isNull()
    finally:
        widget.deleteLater()


@pytest.mark.gui
def test_win_rate_bar_handles_zero_matches_without_crashing():
    _make_app()
    from battle_engine.evaluation_analysis import RateEstimate

    from app.widgets.evaluation_visuals import ProportionBar, win_rate_bar_data

    estimate = RateEstimate(
        scope_label="all", subject_role="candidate", subject_id="cand", matches_played=0, wins=0, losses=0, ties=0
    )
    data = win_rate_bar_data(estimate)
    assert data.segments == ()
    widget = ProportionBar(data)
    try:
        widget.resize(240, widget.minimumHeight())
        assert not widget.grab().isNull()
    finally:
        widget.deleteLater()


@pytest.mark.gui
def test_rate_stat_bar_renders_with_wilson_interval():
    _make_app()
    from battle_engine.evaluation_group_analysis import RateStat

    from app.widgets.evaluation_visuals import ProportionBar, rate_stat_bar_data

    stat = RateStat(successes=3, trials=8)
    data = rate_stat_bar_data("winner", stat)
    assert data.ci is not None
    widget = ProportionBar(data)
    try:
        widget.resize(240, widget.minimumHeight())
        assert not widget.grab().isNull()
    finally:
        widget.deleteLater()


@pytest.mark.gui
def test_plain_rate_bar_has_no_ci():
    _make_app()
    from app.widgets.evaluation_visuals import ProportionBar, plain_rate_bar_data

    data = plain_rate_bar_data("capture rate", 0.25, count=2, total=8)
    assert data.ci is None
    assert "2/8" in data.caption
    widget = ProportionBar(data)
    try:
        widget.resize(240, widget.minimumHeight())
        assert not widget.grab().isNull()
    finally:
        widget.deleteLater()


@pytest.mark.gui
def test_dimension_delta_row_renders_each_unit_kind():
    _make_app()
    from battle_engine.evaluation_behavior import DimensionDelta

    from app.widgets.evaluation_visuals import DimensionDeltaRow

    deltas = [
        DimensionDelta(
            name="survival_fraction", label="survival", unit="fraction_0_1", left=0.8, right=0.5, delta=0.3
        ),
        DimensionDelta(
            name="territory_avg_pct", label="territory (avg)", unit="percent_0_100", left=40.0, right=30.0, delta=10.0
        ),
        DimensionDelta(
            name="writes_per_tick", label="writes/tick", unit="rate_unbounded", left=1.2, right=0.9, delta=0.3
        ),
        DimensionDelta(name="deaths_per_match", label="deaths/match", unit="rate_unbounded", left=None, right=1.0, delta=None),
    ]
    for delta in deltas:
        widget = DimensionDeltaRow(delta, highlighted=(delta.name == "survival_fraction"))
        try:
            widget.resize(280, widget.minimumHeight())
            assert not widget.grab().isNull()
        finally:
            widget.deleteLater()


@pytest.mark.gui
def test_interaction_matrix_grid_renders_and_exposes_pairs():
    _make_app()
    from battle_engine.evaluation_group_analysis import InteractionMatrix, InteractionPair

    from app.widgets.evaluation_visuals import InteractionMatrixGrid

    matrix = InteractionMatrix(
        pairs=(
            InteractionPair(
                captor_agent_id="a", victim_agent_id="b", count=3, rate=0.3, capture_ticks=(10, 20), mean_capture_tick=15.0, median_capture_tick=15.0
            ),
            InteractionPair(
                captor_agent_id="b", victim_agent_id="c", count=1, rate=0.1, capture_ticks=(), mean_capture_tick=None, median_capture_tick=None
            ),
        ),
        unattributed_captures=2,
        cells_analyzed=10,
    )
    widget = InteractionMatrixGrid(matrix)
    try:
        assert widget.agents == ["a", "b", "c"]
        assert widget.pair("a", "b").count == 3
        assert widget.pair("a", "c") is None
        assert "2 unattributed" in widget.caption()
        assert not widget.grab().isNull()
    finally:
        widget.deleteLater()


@pytest.mark.gui
def test_interaction_matrix_grid_handles_no_pairs():
    _make_app()
    from battle_engine.evaluation_group_analysis import InteractionMatrix

    from app.widgets.evaluation_visuals import InteractionMatrixGrid

    matrix = InteractionMatrix(pairs=(), unattributed_captures=0, cells_analyzed=5)
    widget = InteractionMatrixGrid(matrix)
    try:
        assert widget.agents == []
        assert not widget.grab().isNull()
    finally:
        widget.deleteLater()
