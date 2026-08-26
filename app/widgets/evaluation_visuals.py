"""Visual (QPainter-drawn) presentation widgets for evaluation evidence.

v3.0 Phase 3 (docs/V3_PRODUCT_SCOPE.md): every widget here only renders
values an existing ``battle_engine`` analysis dataclass already computed
(``evaluation_analysis``/``evaluation_behavior``/``evaluation_capture``/
``evaluation_group_analysis``) -- no statistic, ranking, or derived score is
computed in this module, and none of it is a composite/opaque rating. This
is evidence *presentation*, matching the Phase 3 scope guard against
inventing a new rating/scoring system.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from battle_engine.evaluation_behavior import DIMENSION_NAMES, BehaviorAnalysis, DimensionDelta
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

# Reuses this app's existing improved/regressed/neutral palette
# (app/views/evaluation_history.py's _VERDICT_COLORS and verify-status
# labels) rather than inventing a second color vocabulary for the same
# improved/regressed/neutral concepts.
COLOR_WIN = QColor("#1a7f37")
COLOR_LOSS = QColor("#cf222e")
COLOR_TIE = QColor("#6e7781")
COLOR_BASELINE = QColor("#9a6700")
COLOR_TRACK = QColor("#d0d7de")
COLOR_MARK = QColor("#24292f")


@dataclass(frozen=True)
class BarSegment:
    fraction: float
    color: QColor
    label: str = ""


@dataclass(frozen=True)
class ProportionBarData:
    segments: tuple[BarSegment, ...] = field(default_factory=tuple)
    ci: tuple[float, float] | None = None
    point_estimate: float | None = None
    caption: str = ""


class ProportionBar(QWidget):
    """A stacked horizontal proportion bar with an optional CI whisker.

    Renders exactly the numbers a caller already computed elsewhere (e.g.
    an ``evaluation_analysis.RateEstimate``'s win/tie/loss share and its
    own Wilson interval, or a plain rate with no interval) -- see the
    ``*_bar`` factory functions below, which are the only place engine
    dataclasses are read. This class itself is Qt-only and knows nothing
    about evaluation semantics.
    """

    def __init__(self, data: ProportionBarData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data = data
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(34 if data.caption else 18)
        if data.caption:
            self.setToolTip(data.caption)
            self.setAccessibleDescription(data.caption)

    def sizeHint(self) -> QSize:
        return QSize(260, self.minimumHeight())

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bar_top = 2.0
        bar_height = 14.0
        rect = QRectF(0.0, bar_top, max(self.width() - 1, 1), bar_height)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_TRACK)
        painter.drawRoundedRect(rect, 3, 3)

        x = rect.left()
        for segment in self.data.segments:
            width = rect.width() * max(0.0, min(1.0, segment.fraction))
            if width <= 0:
                continue
            painter.setBrush(segment.color)
            painter.drawRect(QRectF(x, rect.top(), width, rect.height()))
            x += width

        if self.data.ci is not None:
            lower, upper = self.data.ci
            x_lower = rect.left() + rect.width() * max(0.0, min(1.0, lower))
            x_upper = rect.left() + rect.width() * max(0.0, min(1.0, upper))
            pen = QPen(COLOR_MARK)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(int(x_lower), int(rect.top() - 2), int(x_lower), int(rect.bottom() + 2))
            painter.drawLine(int(x_upper), int(rect.top() - 2), int(x_upper), int(rect.bottom() + 2))
            mid_y = rect.top() + rect.height() / 2
            painter.drawLine(int(x_lower), int(mid_y), int(x_upper), int(mid_y))
            if self.data.point_estimate is not None:
                x_point = rect.left() + rect.width() * max(0.0, min(1.0, self.data.point_estimate))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(COLOR_MARK)
                painter.drawEllipse(QRectF(x_point - 3, mid_y - 3, 6, 6))

        if self.data.caption:
            painter.setPen(QPen(self.palette().windowText().color()))
            painter.drawText(
                QRectF(0, bar_top + bar_height + 2, self.width(), 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.data.caption,
            )


def win_rate_bar_data(estimate) -> ProportionBarData:
    """From an ``evaluation_analysis.RateEstimate`` -- win/tie/loss share
    plus that same estimate's own Wilson interval on the win rate.
    """

    played = estimate.matches_played
    label = f"{estimate.subject_role} {estimate.subject_id}"
    if played == 0:
        return ProportionBarData(caption=f"{label}: no scored cells")
    win = estimate.observed_win_rate or 0.0
    tie = estimate.tie_rate or 0.0
    loss = estimate.loss_rate or 0.0
    interval = estimate.win_interval
    caption = f"{label}: {estimate.wins}W {estimate.ties}T {estimate.losses}L / {played} ({100.0 * win:.0f}% win)"
    if interval is not None:
        caption += (
            f"  {round(interval.confidence_level * 100)}% CI "
            f"[{100.0 * interval.lower:.0f}%, {100.0 * interval.upper:.0f}%]"
        )
    return ProportionBarData(
        segments=(
            BarSegment(win, COLOR_WIN, "win"),
            BarSegment(tie, COLOR_TIE, "tie"),
            BarSegment(loss, COLOR_LOSS, "loss"),
        ),
        ci=(interval.lower, interval.upper) if interval is not None else None,
        point_estimate=win,
        caption=caption,
    )


def rate_stat_bar_data(label: str, stat, color: QColor = COLOR_WIN) -> ProportionBarData:
    """From any ``successes``/``trials``/``rate``/``interval``-shaped object
    -- ``evaluation_group_analysis.RateStat`` (winner/survival/elimination/
    kill-involvement/capture rate in group mode).
    """

    if not stat.trials:
        return ProportionBarData(caption=f"{label}: no data")
    rate = stat.rate or 0.0
    interval = stat.interval
    caption = f"{label}: {stat.successes}/{stat.trials} ({100.0 * rate:.0f}%)"
    if interval is not None:
        caption += (
            f"  {round(interval.confidence_level * 100)}% CI "
            f"[{100.0 * interval.lower:.0f}%, {100.0 * interval.upper:.0f}%]"
        )
    return ProportionBarData(
        segments=(BarSegment(rate, color, label),),
        ci=(interval.lower, interval.upper) if interval is not None else None,
        point_estimate=rate,
        caption=caption,
    )


def plain_rate_bar_data(
    label: str, rate: float | None, *, count: int | None = None, total: int | None = None, color: QColor = COLOR_WIN
) -> ProportionBarData:
    """A bare 0..1 rate with no confidence interval -- e.g.
    ``evaluation_capture.CaptureAggregate``'s capture/survival rates, which
    are descriptive-only and were never given a Wilson interval.
    """

    if rate is None:
        return ProportionBarData(caption=f"{label}: no data")
    caption = f"{label}: {100.0 * rate:.0f}%"
    if count is not None and total is not None:
        caption = f"{label}: {count}/{total} ({100.0 * rate:.0f}%)"
    return ProportionBarData(
        segments=(BarSegment(rate, color, label),),
        point_estimate=rate,
        caption=caption,
    )


def _format_dimension_values(delta) -> str:
    unit = delta.unit
    left, right = delta.left, delta.right

    def fmt(value: float | None) -> str:
        if value is None:
            return "n/a"
        if unit == "fraction_0_1":
            return f"{100.0 * value:.0f}%"
        if unit == "percent_0_100":
            return f"{value:.1f}%"
        return f"{value:.2f}"

    text = f"candidate {fmt(left)}  baseline {fmt(right)}"
    if delta.delta is not None:
        sign = "+" if delta.delta >= 0 else ""
        if unit == "fraction_0_1":
            text += f"  Δ {sign}{100.0 * delta.delta:.0f}pp"
        elif unit == "percent_0_100":
            text += f"  Δ {sign}{delta.delta:.1f}pp"
        else:
            text += f"  Δ {sign}{delta.delta:.2f} (unbounded rate)"
    return text


class DimensionDeltaRow(QWidget):
    """One behavior dimension: candidate vs. baseline, from an
    ``evaluation_behavior.DimensionDelta`` already computed by
    ``dimension_deltas``.

    Each row's bar is scaled only against *that dimension's own* range
    (its intrinsic 0..1/0..100 bound, or the larger of the two raw values
    for an unbounded rate) -- consistent with
    ``evaluation_behavior.largest_bounded_differences``'s own rule that
    different dimensions' units are never compared on one shared scale.
    """

    def __init__(self, delta, *, highlighted: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.delta = delta
        self.highlighted = highlighted
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tooltip = _format_dimension_values(delta)
        self.setToolTip(tooltip)
        self.setAccessibleDescription(f"{delta.label}: {tooltip}")

    def sizeHint(self) -> QSize:
        return QSize(280, 40)

    def _scale(self) -> float:
        if self.delta.unit == "percent_0_100":
            return 100.0
        if self.delta.unit == "rate_unbounded":
            return max(abs(self.delta.left or 0.0), abs(self.delta.right or 0.0), 1e-9)
        return 1.0

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        text_color = self.palette().windowText().color()

        label = self.delta.label + ("  ★" if self.highlighted else "")
        painter.setPen(QPen(text_color))
        painter.drawText(QRectF(0, 0, self.width(), 16), Qt.AlignmentFlag.AlignLeft, label)

        scale = self._scale()
        bar_top = 18.0
        bar_height = 8.0
        width = max(self.width() - 1, 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_TRACK)
        painter.drawRoundedRect(QRectF(0, bar_top, width, bar_height), 2, 2)

        if self.delta.left is not None:
            painter.setBrush(COLOR_WIN)
            frac = max(0.0, min(1.0, abs(self.delta.left) / scale))
            painter.drawRect(QRectF(0, bar_top, width * frac, bar_height))
        if self.delta.right is not None:
            pen = QPen(COLOR_BASELINE)
            pen.setWidth(2)
            painter.setPen(pen)
            frac = max(0.0, min(1.0, abs(self.delta.right) / scale))
            x = width * frac
            painter.drawLine(int(x), int(bar_top - 2), int(x), int(bar_top + bar_height + 2))

        painter.setPen(QPen(text_color))
        painter.drawText(
            QRectF(0, bar_top + bar_height + 2, self.width(), 14),
            Qt.AlignmentFlag.AlignLeft,
            _format_dimension_values(self.delta),
        )


def ordered_behavior_deltas(behavior: BehaviorAnalysis) -> list[tuple[DimensionDelta, bool]]:
    """Every dimension, in ``evaluation_behavior``'s own presentation order,
    paired with whether it is one of the (already-computed, already-ranked)
    largest candidate-vs-baseline differences.

    With a baseline, this is exactly ``candidate_vs_baseline_deltas``. With
    none, there is no delta to compute -- each dimension is instead shown
    as a candidate-only value (``right``/``delta`` left ``None``, reusing
    the same ``DimensionDeltaRow`` widget rather than a second one), and
    nothing is highlighted, since "largest difference" has no meaning
    without a baseline to differ from. Shared by both
    ``app.views.evaluation`` (live-run results) and
    ``app.views.evaluation_history`` (historical browsing) so the two
    surfaces never diverge on how a dimension list is built.
    """

    if behavior.candidate_vs_baseline_deltas is not None:
        largest = set(behavior.candidate_vs_baseline_largest or ())
        return [(delta, delta.name in largest) for delta in behavior.candidate_vs_baseline_deltas]
    overall = behavior.candidate_overall
    return [
        (
            DimensionDelta(
                name=name,
                label=overall.dimension(name).label,
                unit=overall.dimension(name).unit,
                left=overall.dimension(name).mean,
                right=None,
                delta=None,
            ),
            False,
        )
        for name in DIMENSION_NAMES
    ]


class InteractionMatrixGrid(QWidget):
    """Captor -> victim heatmap for an
    ``evaluation_group_analysis.InteractionMatrix``.

    Cell shading encodes ``InteractionPair.rate``; cell text is the raw
    ``count``. Rows/columns are the union of every agent id that appears as
    a captor or a victim, sorted for a stable layout -- nothing beyond
    that union/lookup is computed here.
    """

    _CELL = 56
    _HEADER = 96

    def __init__(self, matrix, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.matrix = matrix
        agent_ids = sorted({pair.captor_agent_id for pair in matrix.pairs} | {pair.victim_agent_id for pair in matrix.pairs})
        self.agents = agent_ids
        self._by_pair = {(pair.captor_agent_id, pair.victim_agent_id): pair for pair in matrix.pairs}
        n = max(len(agent_ids), 1)
        self.setMinimumSize(self._HEADER + self._CELL * n, self._HEADER + self._CELL * n)

    def pair(self, captor_agent_id: str, victim_agent_id: str):
        return self._by_pair.get((captor_agent_id, victim_agent_id))

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        text_color = self.palette().windowText().color()
        max_rate = max((pair.rate or 0.0 for pair in self.matrix.pairs), default=0.0) or 1.0

        for row, captor in enumerate(self.agents):
            y = self._HEADER + row * self._CELL
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRectF(0, y, self._HEADER - 4, self._CELL),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                captor,
            )
        for col, victim in enumerate(self.agents):
            x = self._HEADER + col * self._CELL
            painter.save()
            painter.translate(x + self._CELL / 2, self._HEADER - 6)
            painter.rotate(-45)
            painter.setPen(QPen(text_color))
            painter.drawText(QRectF(-self._CELL, -12, self._CELL * 2, 16), Qt.AlignmentFlag.AlignCenter, victim)
            painter.restore()

        for row, captor in enumerate(self.agents):
            for col, victim in enumerate(self.agents):
                x = self._HEADER + col * self._CELL
                y = self._HEADER + row * self._CELL
                cell_rect = QRectF(x + 2, y + 2, self._CELL - 4, self._CELL - 4)
                if captor == victim:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor("#eaeef2"))
                    painter.drawRect(cell_rect)
                    continue
                pair = self._by_pair.get((captor, victim))
                painter.setPen(QPen(COLOR_TRACK))
                intensity = (pair.rate or 0.0) / max_rate if pair is not None else 0.0
                fill = QColor(COLOR_LOSS)
                fill.setAlphaF(0.15 + 0.65 * max(0.0, min(1.0, intensity)) if pair is not None else 0.0)
                painter.setBrush(fill)
                painter.drawRect(cell_rect)
                if pair is not None and pair.count:
                    painter.setPen(QPen(text_color))
                    painter.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, str(pair.count))

    def caption(self) -> str:
        if self.matrix.unattributed_captures:
            return f"captures: {len(self.matrix.pairs)} attributed pair(s); {self.matrix.unattributed_captures} unattributed"
        return f"captures: {len(self.matrix.pairs)} attributed pair(s)"


__all__ = [
    "BarSegment",
    "DimensionDeltaRow",
    "InteractionMatrixGrid",
    "ProportionBar",
    "ProportionBarData",
    "ordered_behavior_deltas",
    "plain_rate_bar_data",
    "rate_stat_bar_data",
    "win_rate_bar_data",
]
