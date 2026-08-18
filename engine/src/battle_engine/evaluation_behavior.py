"""Phase 5 behavior-profile analysis over already-authoritative evaluation
data (``docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md``).

Sibling of ``evaluation_analysis.py`` (Phase 4), not a replacement or an
extension of it: Phase 4 answers "did the candidate do better," measured
from outcome (win/loss/tie, score, statistical evidence). This module
answers a different question -- "how did the candidate play" -- from
observable strategy characteristics (survival, write activity, territory
occupancy/retention, kill interaction) that are deliberately kept separate
from outcome. Two subjects can have a similar behavior profile with very
different win rates, or a similar win rate with very different behavior
profiles; nothing in this module reads or derives from win rate, score, or
any Phase 4 statistic, and nothing here feeds back into Phase 4.

Two data tiers, by availability and cost (see the design doc for the
measured cost basis):

* **Tier 1** -- already inside a canonical ``EvaluationCell``
  (``ticks_run``, ``territory_subject`` last-tick percentage). Free: no
  I/O beyond what the caller already did to have the cell at all.
* **Tier 2** -- each cell's own already-written, sibling ``result.json``
  (``battle2.result`` v1, read via ``result_model.read_result``) --
  ``alive_ticks``, ``kills``, ``deaths``, ``mem_writes``,
  ``territory_pct_max``/``territory_pct_avg``, ``termination_reason``. One
  small JSON file per cell, not the tick-by-tick replay -- cheap, but
  real I/O the caller must opt into (see ``CellRef``/loader functions
  below), never performed implicitly by discovery/listing code.

Full replay-derived trajectory metrics (early expansion rate, peak
timing, contraction after peak) and replay-derived write-concentration
metrics are **not implemented in this phase** -- see the design doc's
"Deferred" section for why (a genuine architecture-boundary finding, not
an oversight): the incremental ownership reconstruction those metrics need
lives in ``battle_client.session``/``battle_client.analysis``, and
``battle_engine`` must never depend on ``battle_client`` (AGENTS.md's
acyclic dependency direction) -- duplicating that reconstruction inside
``battle_engine`` would create a second, drift-prone implementation of
logic that already exists once.

Pure aggregation, no clustering, no composite score, no archetype naming.
Every dimension is reported independently; comparisons are per-dimension
deltas, never a single combined "behavioral distance" (deferred -- see the
design doc's "combining dimensions" section for why manufacturing weights
across incommensurate units was judged not defensible yet).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from battle_engine.agent_evaluation import (
    BASELINE,
    CANDIDATE,
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_OPPONENT_FIRST,
    EvaluationCell,
    physical_slots_for_orientation,
)
from battle_engine.result_model import read_result

# ---------------------------------------------------------------------------
# Input: a resolved reference to one scored cell's own artifacts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellRef:
    """One scored (``is_scored``) cell's identity plus a resolved path to its
    own ``result.json``, if any.

    Deliberately narrower than ``EvaluationCell``/``AdaptedCell`` and
    independent of either: this module never reads ``cell.artifact_dir``
    itself, so it never has to know which trust model produced it (a
    freshly-created directory from the live run path, or an arbitrary
    on-disk artifact reached via ``evaluations show``). Path resolution --
    including path-containment checking for untrusted historical artifacts
    -- is entirely the caller's responsibility; see
    ``cell_ref_from_evaluation_cell`` (trusted/already-resolved paths) and
    ``evaluation_history.behavior_adapter.cell_refs_for_behavior``
    (containment-checked historical paths).

    ``result_path=None`` means "no cell-detail artifact to read" (the
    caller could not resolve one, e.g. a path-escape refusal) -- handled
    identically to a missing/unreadable file by the loader below, never
    treated as an error.
    """

    schedule_id: str
    subject_role: str
    subject_id: str
    opponent_id: str
    seed: int
    orientation: str
    territory_last_fallback: float | None
    result_path: Path | None


def cell_ref_from_evaluation_cell(cell: EvaluationCell) -> CellRef:
    """Build a ``CellRef`` from a live/trusted ``EvaluationCell``.

    ``cell.artifact_dir`` is used verbatim -- appropriate for the live
    ``agents evaluate`` run path (a directory this process just created)
    and for Designer's ``read_evaluation_presentation`` (which already
    joins ``artifact_dir`` against the opened evaluation's own directory
    with the same trust level the rest of that function uses for every
    other field). Callers reading an arbitrary on-disk artifact by path
    (``evaluations show``) must not use this function -- see
    ``evaluation_history.behavior_adapter`` instead.
    """

    return CellRef(
        schedule_id=cell.schedule_id,
        subject_role=cell.subject_role,
        subject_id=cell.subject_id,
        opponent_id=cell.opponent_id,
        seed=cell.seed,
        orientation=cell.orientation,
        territory_last_fallback=cell.territory_subject,
        result_path=cell.artifact_dir / "result.json",
    )


# ---------------------------------------------------------------------------
# Loaded per-cell sample (Tier 1 always; Tier 2 when available)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellBehaviorSample:
    """One cell's behavioral measurements, from the subject's own physical slot.

    ``available=False`` means the Tier 2 (``result.json``) read did not
    succeed -- missing file, unreadable/corrupt JSON, or the subject's
    entrant missing from it -- and every Tier-2-only field is ``None``.
    ``territory_last_pct`` still falls back to the cell's own persisted
    ``territory_subject`` (Tier 1) in that case, so territory-occupancy
    "last" values degrade gracefully even for an artifact whose nested
    result was pruned or never captured (Sec 17 of the design doc:
    historical compatibility, no all-or-nothing failure).
    """

    schedule_id: str
    subject_role: str
    subject_id: str
    opponent_id: str
    seed: int
    orientation: str
    available: bool
    unavailable_reason: str | None
    ticks_run: int | None = None
    alive_ticks: int | None = None
    alive: bool | None = None
    mem_writes: int | None = None
    kills: int | None = None
    deaths: int | None = None
    territory_last_pct: float | None = None
    territory_max_pct: float | None = None
    territory_avg_pct: float | None = None
    termination_reason: str | None = None


def load_cell_behavior_sample(ref: CellRef) -> CellBehaviorSample:
    """Read ``ref``'s ``result.json`` (Tier 2) into a ``CellBehaviorSample``.

    Never raises: any failure to locate/parse the result, or to find the
    subject's own entrant inside it, degrades to ``available=False`` with
    an explanatory ``unavailable_reason`` -- exactly the "expose
    unavailable metrics honestly rather than failing the whole profile"
    contract the design doc requires (Sec 17).
    """

    base: dict[str, Any] = {
        "schedule_id": ref.schedule_id,
        "subject_role": ref.subject_role,
        "subject_id": ref.subject_id,
        "opponent_id": ref.opponent_id,
        "seed": ref.seed,
        "orientation": ref.orientation,
    }
    if ref.result_path is None:
        return CellBehaviorSample(
            **base,
            available=False,
            unavailable_reason="no result artifact path resolved for this cell",
            territory_last_pct=ref.territory_last_fallback,
        )
    try:
        envelope = read_result(ref.result_path)
    except (OSError, ValueError, KeyError) as exc:
        return CellBehaviorSample(
            **base,
            available=False,
            unavailable_reason=f"result unreadable: {exc}",
            territory_last_pct=ref.territory_last_fallback,
        )

    subject_slot, _opponent_slot = physical_slots_for_orientation(ref.orientation)
    entrant = next(
        (e for e in envelope.entrants if e.get("agent_id") == subject_slot), None
    )
    if entrant is None:
        return CellBehaviorSample(
            **base,
            available=False,
            unavailable_reason="subject entrant missing from result",
            ticks_run=envelope.ticks,
            territory_last_pct=ref.territory_last_fallback,
        )
    stats: Mapping[str, Any] = entrant.get("statistics") or {}
    return CellBehaviorSample(
        **base,
        available=True,
        unavailable_reason=None,
        ticks_run=envelope.ticks,
        alive_ticks=stats.get("alive_ticks"),
        alive=entrant.get("alive"),
        mem_writes=stats.get("mem_writes"),
        kills=stats.get("kills"),
        deaths=stats.get("deaths"),
        territory_last_pct=stats.get("territory_pct_last", ref.territory_last_fallback),
        territory_max_pct=stats.get("territory_pct_max"),
        territory_avg_pct=stats.get("territory_pct_avg"),
        termination_reason=entrant.get("termination_reason"),
    )


# ---------------------------------------------------------------------------
# Behavioral dimensions: one named, pure extractor per dimension
# ---------------------------------------------------------------------------


def _survival_fraction(s: CellBehaviorSample) -> float | None:
    if s.alive_ticks is None or not s.ticks_run:
        return None
    return max(0.0, min(1.0, s.alive_ticks / s.ticks_run))


def _writes_per_tick(s: CellBehaviorSample) -> float | None:
    if s.mem_writes is None or not s.ticks_run:
        return None
    return s.mem_writes / s.ticks_run


def _writes_per_alive_tick(s: CellBehaviorSample) -> float | None:
    if s.mem_writes is None or not s.alive_ticks:
        return None
    return s.mem_writes / s.alive_ticks


def _territory_retention(s: CellBehaviorSample) -> float | None:
    """Fraction of peak territory still held at match end (last / max).

    A cheap, purely scalar proxy for late-game volatility -- *not* a
    trajectory reconstruction (no peak timing, no early-expansion rate;
    see the module docstring's "Deferred" note). Low retention means the
    subject lost ground after its peak; ``None`` when max is zero (never
    held any territory) rather than a misleading ``0/0`` division.
    """

    if s.territory_last_pct is None or s.territory_max_pct is None or s.territory_max_pct <= 0:
        return None
    return max(0.0, min(1.0, s.territory_last_pct / s.territory_max_pct))


def _territory_spread(s: CellBehaviorSample) -> float | None:
    """Peak-minus-average territory percentage: how "peaky" vs. sustained
    occupancy was, in percentage points. Always >= 0 in practice (avg is a
    running mean of values each <= the running max at that point)."""

    if s.territory_max_pct is None or s.territory_avg_pct is None:
        return None
    return s.territory_max_pct - s.territory_avg_pct


def _kills_per_match(s: CellBehaviorSample) -> float | None:
    return float(s.kills) if s.kills is not None else None


def _kill_involvement_rate(s: CellBehaviorSample) -> float | None:
    return None if s.kills is None else (1.0 if s.kills > 0 else 0.0)


def _deaths_per_match(s: CellBehaviorSample) -> float | None:
    return float(s.deaths) if s.deaths is not None else None


@dataclass(frozen=True)
class _Dimension:
    name: str
    label: str
    unit: str  # "fraction_0_1" | "percent_0_100" | "rate_unbounded"
    extractor: Callable[[CellBehaviorSample], float | None]


# Order here is presentation order everywhere (CLI, JSON dimension list).
# ``unit`` documents intrinsic bounds (Sec 8 of the design doc): a
# fraction/percent dimension never needs dataset-relative normalization to
# be interpretable; a "rate_unbounded" dimension (writes/kills/deaths per
# match) is reported as-is, disclosed as unbounded, and deliberately
# excluded from any cross-dimension "largest difference" ranking that
# would otherwise silently compare it against a 0-1 quantity.
_DIMENSIONS: tuple[_Dimension, ...] = (
    _Dimension("survival_fraction", "survival (alive_ticks / ticks_run)", "fraction_0_1", _survival_fraction),
    _Dimension("writes_per_tick", "writes per tick", "rate_unbounded", _writes_per_tick),
    _Dimension("writes_per_alive_tick", "writes per alive tick", "rate_unbounded", _writes_per_alive_tick),
    _Dimension("territory_last_pct", "territory occupancy (last)", "percent_0_100", lambda s: s.territory_last_pct),
    _Dimension("territory_max_pct", "territory occupancy (peak)", "percent_0_100", lambda s: s.territory_max_pct),
    _Dimension("territory_avg_pct", "territory occupancy (average)", "percent_0_100", lambda s: s.territory_avg_pct),
    _Dimension("territory_retention", "territory retention (last / peak)", "fraction_0_1", _territory_retention),
    _Dimension("territory_spread", "territory spread (peak - average)", "percent_0_100", _territory_spread),
    _Dimension("kills_per_match", "kills per match", "rate_unbounded", _kills_per_match),
    _Dimension("kill_involvement_rate", "matches with >=1 kill", "fraction_0_1", _kill_involvement_rate),
    _Dimension("deaths_per_match", "deaths per match", "rate_unbounded", _deaths_per_match),
)

_DIMENSIONS_BY_NAME: dict[str, _Dimension] = {d.name: d for d in _DIMENSIONS}
DIMENSION_NAMES: tuple[str, ...] = tuple(d.name for d in _DIMENSIONS)


class BehaviorSampleState(str, Enum):
    EVALUATED = "evaluated"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class DimensionValue:
    """Descriptive mean + range for one dimension over some scope's samples.

    Deliberately mean + min/max, not a confidence interval: most
    dimensions here are not literal per-match Bernoulli trial counts (a
    rate like writes/tick or an average-of-ratios like survival_fraction
    is not the same statistical object a Wilson interval applies to), so
    inventing one would misrepresent what was actually measured. ``n`` is
    the number of cells that actually contributed a value for *this*
    dimension (which can be smaller than the scope's total sample count --
    e.g. ``territory_retention`` is undefined for a cell that never held
    any territory).
    """

    name: str
    label: str
    unit: str
    mean: float | None
    n: int
    minimum: float | None
    maximum: float | None

    @property
    def state(self) -> BehaviorSampleState:
        return BehaviorSampleState.EVALUATED if self.n > 0 else BehaviorSampleState.INSUFFICIENT_DATA

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "unit": self.unit,
            "state": self.state.value,
            "mean": self.mean,
            "n": self.n,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


def _dimension_value(dimension: _Dimension, samples: Sequence[CellBehaviorSample]) -> DimensionValue:
    values = [v for s in samples if (v := dimension.extractor(s)) is not None]
    return DimensionValue(
        name=dimension.name,
        label=dimension.label,
        unit=dimension.unit,
        mean=(sum(values) / len(values)) if values else None,
        n=len(values),
        minimum=min(values) if values else None,
        maximum=max(values) if values else None,
    )


# ---------------------------------------------------------------------------
# Behavior profile: one subject, one scope (overall / one orientation / one opponent)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BehaviorProfile:
    subject_role: str
    subject_id: str
    scope_label: str
    sample_count: int
    available_count: int
    dimensions: Mapping[str, DimensionValue]
    termination_reason_counts: Mapping[str, int] = field(default_factory=dict)

    def dimension(self, name: str) -> DimensionValue:
        return self.dimensions[name]

    def to_json(self) -> dict[str, Any]:
        return {
            "subject_role": self.subject_role,
            "subject_id": self.subject_id,
            "scope_label": self.scope_label,
            "sample_count": self.sample_count,
            "available_count": self.available_count,
            "dimensions": {name: value.to_json() for name, value in self.dimensions.items()},
            "termination_reason_counts": dict(self.termination_reason_counts),
        }


def _profile_from_samples(
    subject_role: str, subject_id: str, scope_label: str, samples: Sequence[CellBehaviorSample]
) -> BehaviorProfile:
    dims = {d.name: _dimension_value(d, samples) for d in _DIMENSIONS}
    term_counts: dict[str, int] = {}
    for s in samples:
        if s.termination_reason:
            term_counts[s.termination_reason] = term_counts.get(s.termination_reason, 0) + 1
    return BehaviorProfile(
        subject_role=subject_role,
        subject_id=subject_id,
        scope_label=scope_label,
        sample_count=len(samples),
        available_count=sum(1 for s in samples if s.available),
        dimensions=dims,
        termination_reason_counts=term_counts,
    )


def _profile_views(
    subject_role: str, subject_id: str, samples: Sequence[CellBehaviorSample]
) -> tuple[BehaviorProfile, tuple[BehaviorProfile, ...], tuple[BehaviorProfile, ...]]:
    own = [s for s in samples if s.subject_role == subject_role and s.subject_id == subject_id]
    overall = _profile_from_samples(subject_role, subject_id, "all", own)
    by_orientation = tuple(
        _profile_from_samples(subject_role, subject_id, scope, [s for s in own if s.orientation == scope])
        for scope in (ORIENTATION_CANDIDATE_FIRST, ORIENTATION_OPPONENT_FIRST)
    )
    opponent_ids = sorted({s.opponent_id for s in own})
    by_opponent = tuple(
        _profile_from_samples(subject_role, subject_id, opponent_id, [s for s in own if s.opponent_id == opponent_id])
        for opponent_id in opponent_ids
    )
    return overall, by_orientation, by_opponent


# ---------------------------------------------------------------------------
# Per-dimension deltas between two profiles (no combined distance -- Sec 11)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionDelta:
    name: str
    label: str
    unit: str
    left: float | None
    right: float | None
    delta: float | None  # left - right, only when both sides have a value

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "unit": self.unit,
            "left": self.left,
            "right": self.right,
            "delta": self.delta,
        }


def dimension_deltas(left: BehaviorProfile, right: BehaviorProfile) -> tuple[DimensionDelta, ...]:
    """Every dimension's (left - right) delta, symmetric, no combined score.

    ``left``/``right`` are deliberately generic labels (not "candidate"/
    "baseline") -- the same function serves candidate-vs-baseline within
    one evaluation and (via ``evaluation_history``) two independently
    evaluated subjects being compared.
    """

    deltas = []
    for dimension in _DIMENSIONS:
        left_value = left.dimensions[dimension.name].mean
        right_value = right.dimensions[dimension.name].mean
        delta = (left_value - right_value) if (left_value is not None and right_value is not None) else None
        deltas.append(
            DimensionDelta(
                name=dimension.name, label=dimension.label, unit=dimension.unit,
                left=left_value, right=right_value, delta=delta,
            )
        )
    return tuple(deltas)


def largest_bounded_differences(deltas: Sequence[DimensionDelta], limit: int = 3) -> tuple[str, ...]:
    """Dimension names with the largest |delta|, restricted to intrinsically
    bounded units (``fraction_0_1``, normalized ``percent_0_100`` / 100).

    Deliberately excludes ``rate_unbounded`` dimensions (writes/kills/
    deaths per match): comparing their raw magnitude against a 0-1
    quantity would silently imply a shared scale that does not exist (Sec
    11 of the design doc -- this is exactly the "arbitrary weighting"
    problem a combined distance would have, scoped down to just the
    ranking step, so it is resolved the same way: don't pretend
    incommensurate units compare, rather than inventing a normalization).
    Unbounded-rate deltas are still available -- every raw delta is in
    ``dimension_deltas``'s full result -- just never mixed into this
    specific ranking.
    """

    def normalized_magnitude(entry: DimensionDelta) -> float | None:
        if entry.delta is None:
            return None
        if entry.unit == "fraction_0_1":
            return abs(entry.delta)
        if entry.unit == "percent_0_100":
            return abs(entry.delta) / 100.0
        return None

    scored = [
        (magnitude, entry.name)
        for entry in deltas
        if (magnitude := normalized_magnitude(entry)) is not None
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return tuple(name for _magnitude, name in scored[:limit])


# ---------------------------------------------------------------------------
# Top-level behavior analysis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BehaviorAnalysis:
    candidate_id: str
    baseline_id: str | None
    candidate_overall: BehaviorProfile
    candidate_by_orientation: tuple[BehaviorProfile, ...]
    candidate_by_opponent: tuple[BehaviorProfile, ...]
    baseline_overall: BehaviorProfile | None
    baseline_by_orientation: tuple[BehaviorProfile, ...]
    baseline_by_opponent: tuple[BehaviorProfile, ...]
    # Candidate's own candidate_first-vs-opponent_first deltas -- an agent
    # can win at the same rate from both slots yet *behave* differently by
    # slot (e.g. a territory-timing strategy that only pays off when
    # acting second); this is deliberately about the profile itself, never
    # about the win-rate orientation split Phase 4 already reports.
    candidate_orientation_deltas: tuple[DimensionDelta, ...]
    baseline_orientation_deltas: tuple[DimensionDelta, ...] | None
    # Candidate-vs-baseline behavioral deltas -- descriptive only; never
    # interpreted as "better"/"worse" (Sec 19 of the design doc).
    candidate_vs_baseline_deltas: tuple[DimensionDelta, ...] | None
    candidate_vs_baseline_largest: tuple[str, ...] | None

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "baseline_id": self.baseline_id,
            "candidate_overall": self.candidate_overall.to_json(),
            "candidate_by_orientation": [p.to_json() for p in self.candidate_by_orientation],
            "candidate_by_opponent": [p.to_json() for p in self.candidate_by_opponent],
            "baseline_overall": self.baseline_overall.to_json() if self.baseline_overall else None,
            "baseline_by_orientation": [p.to_json() for p in self.baseline_by_orientation],
            "baseline_by_opponent": [p.to_json() for p in self.baseline_by_opponent],
            "candidate_orientation_deltas": [d.to_json() for d in self.candidate_orientation_deltas],
            "baseline_orientation_deltas": (
                [d.to_json() for d in self.baseline_orientation_deltas]
                if self.baseline_orientation_deltas is not None
                else None
            ),
            "candidate_vs_baseline_deltas": (
                [d.to_json() for d in self.candidate_vs_baseline_deltas]
                if self.candidate_vs_baseline_deltas is not None
                else None
            ),
            "candidate_vs_baseline_largest": (
                list(self.candidate_vs_baseline_largest)
                if self.candidate_vs_baseline_largest is not None
                else None
            ),
        }


def analyze_behavior(
    candidate_id: str, baseline_id: str | None, refs: Sequence[CellRef]
) -> BehaviorAnalysis:
    """Top-level Phase 5 entry point: derive a behavior profile from
    already-scored evaluation cells' own resolved artifact references.

    Performs real I/O (one ``result.json`` read per ref) -- unlike
    ``evaluation_analysis.analyze`` (Phase 4, pure/in-memory), this
    function is not free, and callers must call it deliberately (never
    from evaluation-history discovery/listing code) -- see the module
    docstring and the design doc's replay-cost discipline section.
    """

    samples = tuple(load_cell_behavior_sample(ref) for ref in refs)

    candidate_overall, candidate_by_orientation, candidate_by_opponent = _profile_views(
        CANDIDATE, candidate_id, samples
    )
    candidate_orientation_deltas = dimension_deltas(candidate_by_orientation[0], candidate_by_orientation[1])

    baseline_overall: BehaviorProfile | None = None
    baseline_by_orientation: tuple[BehaviorProfile, ...] = ()
    baseline_by_opponent: tuple[BehaviorProfile, ...] = ()
    baseline_orientation_deltas: tuple[DimensionDelta, ...] | None = None
    candidate_vs_baseline_deltas: tuple[DimensionDelta, ...] | None = None
    candidate_vs_baseline_largest: tuple[str, ...] | None = None

    if baseline_id is not None:
        baseline_overall, baseline_by_orientation, baseline_by_opponent = _profile_views(
            BASELINE, baseline_id, samples
        )
        baseline_orientation_deltas = dimension_deltas(baseline_by_orientation[0], baseline_by_orientation[1])
        candidate_vs_baseline_deltas = dimension_deltas(candidate_overall, baseline_overall)
        candidate_vs_baseline_largest = largest_bounded_differences(candidate_vs_baseline_deltas)

    return BehaviorAnalysis(
        candidate_id=candidate_id,
        baseline_id=baseline_id,
        candidate_overall=candidate_overall,
        candidate_by_orientation=candidate_by_orientation,
        candidate_by_opponent=candidate_by_opponent,
        baseline_overall=baseline_overall,
        baseline_by_orientation=baseline_by_orientation,
        baseline_by_opponent=baseline_by_opponent,
        candidate_orientation_deltas=candidate_orientation_deltas,
        baseline_orientation_deltas=baseline_orientation_deltas,
        candidate_vs_baseline_deltas=candidate_vs_baseline_deltas,
        candidate_vs_baseline_largest=candidate_vs_baseline_largest,
    )


__all__ = [
    "DIMENSION_NAMES",
    "BehaviorAnalysis",
    "BehaviorProfile",
    "BehaviorSampleState",
    "CellBehaviorSample",
    "CellRef",
    "DimensionDelta",
    "DimensionValue",
    "analyze_behavior",
    "cell_ref_from_evaluation_cell",
    "dimension_deltas",
    "largest_bounded_differences",
    "load_cell_behavior_sample",
]
