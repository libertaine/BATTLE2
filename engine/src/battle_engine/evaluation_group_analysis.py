"""v2.0.0-beta2 Phase 3 multi-entrant ("group") strategic analysis
(``docs/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md``).

Sibling of ``evaluation_analysis.py`` (Phase 4, outcome/win-rate),
``evaluation_behavior.py`` (Phase 5, behavior profile), and
``evaluation_capture.py`` (Beta2 Phase 1, capture/core evidence) -- not a
replacement or extension of any of them. Those three modules are, and
remain, exactly what they always were: a fixed, two-role (subject/
opponent) worldview appropriate for a pairwise cell. This module answers
the equivalent questions for a *group* (multi-entrant, N >= 3) cell,
where "subject vs. opponent" is not a meaningful frame -- every roster
entrant is a first-class subject of analysis, symmetrically, and
candidate designation is presentation metadata layered on top (see
``candidate_focused_view``), never baked into the underlying computation.
``analyze_group`` does not even take a candidate id as an argument -- the
per-entrant results it produces cannot depend on which entrant a caller
later chooses to present as "the candidate" (Sec 6/21 of the design doc).

One data tier, matching ``evaluation_behavior``/``evaluation_capture``'s own
Tier 2: each scored group cell's already-written, sibling ``result.json``
(``battle2.result`` v1, read via ``result_model.read_result``). No replay
reconstruction -- every metric here is derived from a cell's own persisted
``entrants``/``score``/``winner``/``ticks`` fields, read once per cell and
fanned out into one record per seat (not one ``result.json`` read per
entrant per cell -- N reads collapse to 1).

Outcome model (Sec 9 of the design doc): the engine's own winner semantics
(``battle_engine.results.resolve_winner``, survivor-only eligible, reused
unchanged) are authoritative. Three per-entrant states are derived from it,
never a flat win/loss: ``WINNER`` (this seat's agent_id is literally the
cell's resolved winner), ``SURVIVING_NON_WINNER`` (alive at match end but
not the winner -- includes every entrant in a tied/no-unique-winner cell,
which is exactly what "no entrant here is WINNER" already expresses without
a fourth enum value), and ``ELIMINATED`` (not alive at match end). A
surviving non-winner and an eliminated entrant are never collapsed into one
"loss" bucket the way ``agent_evaluation.EvaluationCell.outcome`` (kept
unchanged, for compatibility) does.

Captor/victim attribution (Sec 13/14): ``result.json`` records each
entrant's own aggregate ``kills``/``deaths`` counts, not a per-death event
log (the per-tick ``{"type": "kill", "victim": ..., "by": ...}`` events
python_runtime.apply_core_capture actually produces are published to the
*replay*, a materially higher cost tier -- deliberately not read here, see
"Deferred" below). For a cell with exactly one death total, attribution is
unambiguous by the same elimination logic ``evaluation_capture.py`` already
uses for the 2-entrant case (there is only one possible killer once there
is only one victim and only one entrant with a nonzero kill count) --
generalized here to N by checking "exactly one victim this cell" up front,
which happens to always be true at N=2 (so this function's N=2 behavior is
identical in spirit, though it lives in this module only for group cells
and never replaces ``evaluation_capture.load_cell_capture_sample``). For a
cell with two or more deaths, aggregate kill counts alone cannot say which
death which entrant is responsible for -- attribution is left ``None``
(unattributable), the same honest "never guessed" contract every capture
sample in this codebase already follows, disclosed via
``InteractionMatrix.unattributed_captures`` rather than hidden.

Capture *timing* (Sec 14 "mean/median capture tick"): a cell's own
``ticks`` is the match's own final tick count, not necessarily the tick any
particular capture happened on -- those coincide only when the capture
event is itself what ended the match (``termination_reason`` is
alive-count-driven: ``last_agent_standing``/``all_agents_dead``). At N >= 3
a capture frequently does *not* end the match (two or more entrants can
remain alive afterward), so the match keeps running to the tick budget
under ``tick_limit`` -- reporting ``ticks`` as that capture's tick would
overstate it, often by hundreds of ticks (found via this phase's own
characterization runs, not merely hypothesized). ``capture_tick``/
``capture_tick_caused`` are therefore populated only when
``termination_reason`` confirms the capture was terminal; the fact of the
capture itself (``captured``, ``captor_of``, every rate in
``EntrantSummary``) is unaffected and always reported when known -- only
the numeric tick is withheld when it cannot be trusted.

Deferred (see the design doc's "analysis compatibility" / "remaining
limitations" sections): full per-tick directed kill/capture event logs
(would require replay reconstruction, a Tier-3 cost class); minimum core
integrity over time (Phase 1L's deferral, unchanged, same reason); any
combined cross-dimension "strategic score" (mirrors
``evaluation_behavior``'s Sec 11 refusal to manufacture weights across
incommensurate units -- this module reports transparent per-dimension
ranges, never an opaque composite).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from statistics import median
from typing import Any

from battle_engine.agent_evaluation import EvaluationCell, seat_label
from battle_engine.evaluation_analysis import WilsonInterval, wilson_interval
from battle_engine.evaluation_capture import CORE_CAPTURED_TERMINATION_REASON
from battle_engine.result_model import read_result
from battle_engine.ruleset_policy import TerminationReason

# A capture's own tick is trustworthy as `envelope.ticks` only when the
# capture is what ended the match -- see the module docstring's "Capture
# timing" section.
_ALIVE_COUNT_TERMINATED = frozenset(
    {TerminationReason.LAST_AGENT_STANDING.value, TerminationReason.ALL_AGENTS_DEAD.value}
)

# ---------------------------------------------------------------------------
# Input: a resolved reference to one scored group cell's own artifacts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupCellRef:
    """One scored group (``EvaluationCell.is_group``) cell's identity plus a
    resolved path to its own ``result.json``, if any.

    Mirrors ``evaluation_behavior.CellRef`` exactly, generalized from a
    fixed (subject, opponent) pair to a roster/seat-assignment. Path
    resolution -- including path-containment checking for untrusted
    historical artifacts -- is entirely the caller's responsibility; see
    ``group_cell_ref_from_evaluation_cell`` (trusted/already-resolved
    paths, live-run) and ``evaluation_history.group_adapter``
    (containment-checked historical paths).
    """

    schedule_id: str
    roster_agent_ids: tuple[str, ...]
    seat_agent_ids: tuple[str, ...]
    layout_id: str
    seed: int
    result_path: Path | None


def group_cell_ref_from_evaluation_cell(cell: EvaluationCell) -> GroupCellRef:
    """Build a ``GroupCellRef`` from a live/trusted group ``EvaluationCell``.

    ``cell.artifact_dir`` is used verbatim, appropriate for the live
    ``agents evaluate --group`` run path -- mirrors
    ``evaluation_behavior.cell_ref_from_evaluation_cell``'s identical
    trust-level precedent exactly. Callers reading an arbitrary on-disk
    artifact by path (``evaluations show``) must not use this function --
    see ``evaluation_history.group_adapter`` instead.
    """

    if not cell.is_group:
        raise ValueError("group_cell_ref_from_evaluation_cell requires a group cell")
    return GroupCellRef(
        schedule_id=cell.schedule_id,
        roster_agent_ids=cell.roster_agent_ids,
        seat_agent_ids=cell.seat_agent_ids,
        layout_id=cell.layout_id,
        seed=cell.seed,
        result_path=cell.artifact_dir / "result.json",
    )


# ---------------------------------------------------------------------------
# Per-entrant, per-cell raw evidence (Sec 8: kept distinct from aggregates)
# ---------------------------------------------------------------------------


class EntrantOutcome(str, Enum):
    WINNER = "winner"
    SURVIVING_NON_WINNER = "surviving_non_winner"
    ELIMINATED = "eliminated"


@dataclass(frozen=True)
class EntrantCellRecord:
    """One entrant's own raw evidence from one group cell.

    ``available=False`` means the ``result.json`` read did not succeed (or
    this seat is missing from it) -- every evidence field beyond identity
    is then ``None``/empty, mirroring ``CellBehaviorSample``/
    ``CellCaptureSample``'s identical honest-unavailability contract.
    """

    schedule_id: str
    layout_id: str
    seed: int
    seat_agent_ids: tuple[str, ...]
    seat: str
    agent_id: str
    available: bool
    unavailable_reason: str | None = None
    outcome: EntrantOutcome | None = None
    alive: bool | None = None
    score: float | None = None
    score_rank: int | None = None
    margin_to_winner: float | None = None
    ticks_run: int | None = None
    alive_ticks: int | None = None
    mem_writes: int | None = None
    kills: int | None = None
    deaths: int | None = None
    territory_last_pct: float | None = None
    territory_max_pct: float | None = None
    territory_avg_pct: float | None = None
    termination_reason: str | None = None
    captured: bool | None = None
    capture_tick: int | None = None
    # Victim agent_ids this entrant is unambiguously credited with
    # capturing this cell (usually 0 or 1 entries; see module docstring).
    captor_of: tuple[str, ...] = ()
    capture_tick_caused: int | None = None

    @property
    def territory_retention(self) -> float | None:
        if self.territory_last_pct is None or self.territory_max_pct is None or self.territory_max_pct <= 0:
            return None
        return max(0.0, min(1.0, self.territory_last_pct / self.territory_max_pct))

    def to_json(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "layout_id": self.layout_id,
            "seed": self.seed,
            "seat_agent_ids": list(self.seat_agent_ids),
            "seat": self.seat,
            "agent_id": self.agent_id,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "outcome": self.outcome.value if self.outcome is not None else None,
            "alive": self.alive,
            "score": self.score,
            "score_rank": self.score_rank,
            "margin_to_winner": self.margin_to_winner,
            "ticks_run": self.ticks_run,
            "alive_ticks": self.alive_ticks,
            "mem_writes": self.mem_writes,
            "kills": self.kills,
            "deaths": self.deaths,
            "territory_last_pct": self.territory_last_pct,
            "territory_max_pct": self.territory_max_pct,
            "territory_avg_pct": self.territory_avg_pct,
            "territory_retention": self.territory_retention,
            "termination_reason": self.termination_reason,
            "captured": self.captured,
            "capture_tick": self.capture_tick,
            "captor_of": list(self.captor_of),
            "capture_tick_caused": self.capture_tick_caused,
        }


def _resolve_group_captors(entrants: Sequence[Mapping[str, Any]]) -> dict[str, str | None]:
    """Map each core-captured victim seat to its unambiguous captor seat.

    See the module docstring's "Captor/victim attribution" section for the
    full rationale. ``None`` means "a capture occurred but this cell's own
    result.json cannot attribute it unambiguously" -- never guessed.
    """

    victims = [e for e in entrants if e.get("termination_reason") == CORE_CAPTURED_TERMINATION_REASON]
    if not victims:
        return {}
    total_deaths = sum(1 for e in entrants if e.get("alive") is False)
    result: dict[str, str | None] = {}
    for victim in victims:
        victim_seat = str(victim.get("agent_id"))
        if total_deaths != 1:
            result[victim_seat] = None
            continue
        candidates = [
            e.get("agent_id")
            for e in entrants
            if e.get("agent_id") != victim_seat and ((e.get("statistics") or {}).get("kills") or 0) >= 1
        ]
        result[victim_seat] = candidates[0] if len(candidates) == 1 else None
    return result


def load_group_cell_records(ref: GroupCellRef) -> tuple[EntrantCellRecord, ...]:
    """Read ``ref``'s ``result.json`` (Tier 2) into one record per seat.

    Never raises: any failure to locate/parse the result, or a seat
    missing from it, degrades every seat to ``available=False`` rather
    than failing the whole cell's contribution -- mirrors
    ``load_cell_behavior_sample``/``load_cell_capture_sample``'s identical
    contract, generalized to N records instead of one.
    """

    seats = ref.seat_agent_ids
    common: dict[str, Any] = {
        "schedule_id": ref.schedule_id,
        "layout_id": ref.layout_id,
        "seed": ref.seed,
        "seat_agent_ids": seats,
    }

    def _unavailable(reason: str) -> tuple[EntrantCellRecord, ...]:
        return tuple(
            EntrantCellRecord(
                **common, seat=seat_label(i), agent_id=agent_id, available=False, unavailable_reason=reason
            )
            for i, agent_id in enumerate(seats)
        )

    if ref.result_path is None:
        return _unavailable("no result artifact path resolved for this cell")
    try:
        envelope = read_result(ref.result_path)
    except (OSError, ValueError, KeyError) as exc:
        return _unavailable(f"result unreadable: {exc}")

    entrants_by_seat = {e.get("agent_id"): e for e in envelope.entrants}
    expected_seats = [seat_label(i) for i in range(len(seats))]
    if any(seat not in entrants_by_seat for seat in expected_seats):
        return _unavailable("one or more seats missing from result")

    winner = envelope.winner
    capture_tick_known = envelope.termination_reason in _ALIVE_COUNT_TERMINATED
    scores = {seat: float(envelope.score.get(seat, 0)) for seat in expected_seats}
    ranked_seats = sorted(expected_seats, key=lambda s: (-scores[s], s))
    rank_by_seat = {seat: index + 1 for index, seat in enumerate(ranked_seats)}
    winner_score = scores.get(winner)

    captors = _resolve_group_captors(list(envelope.entrants))
    captor_of_by_seat: dict[str, list[str]] = defaultdict(list)
    for victim_seat, captor_seat in captors.items():
        if captor_seat is not None:
            victim_index = expected_seats.index(victim_seat)
            captor_of_by_seat[captor_seat].append(seats[victim_index])

    records = []
    for index, agent_id in enumerate(seats):
        seat = seat_label(index)
        entrant = entrants_by_seat[seat]
        stats = entrant.get("statistics") or {}
        alive = entrant.get("alive")
        outcome = (
            EntrantOutcome.WINNER
            if seat == winner
            else EntrantOutcome.SURVIVING_NON_WINNER
            if alive
            else EntrantOutcome.ELIMINATED
        )
        captured = entrant.get("termination_reason") == CORE_CAPTURED_TERMINATION_REASON
        this_captor_of = tuple(captor_of_by_seat.get(seat, ()))
        records.append(
            EntrantCellRecord(
                **common,
                seat=seat,
                agent_id=agent_id,
                available=True,
                outcome=outcome,
                alive=alive,
                score=scores[seat],
                score_rank=rank_by_seat[seat],
                margin_to_winner=(winner_score - scores[seat]) if winner_score is not None else None,
                ticks_run=envelope.ticks,
                alive_ticks=stats.get("alive_ticks"),
                mem_writes=stats.get("mem_writes"),
                kills=stats.get("kills"),
                deaths=stats.get("deaths"),
                territory_last_pct=stats.get("territory_pct_last"),
                territory_max_pct=stats.get("territory_pct_max"),
                territory_avg_pct=stats.get("territory_pct_avg"),
                termination_reason=entrant.get("termination_reason"),
                captured=captured,
                capture_tick=(envelope.ticks if captured and capture_tick_known else None),
                captor_of=this_captor_of,
                capture_tick_caused=(envelope.ticks if this_captor_of and capture_tick_known else None),
            )
        )
    return tuple(records)


# ---------------------------------------------------------------------------
# Descriptive/inferential building blocks, reused across every aggregate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stat:
    """Descriptive mean + range for a continuous dimension.

    Deliberately mean + min/max, never a confidence interval -- mirrors
    ``evaluation_behavior.DimensionValue``'s identical reasoning (score/
    territory/kill-count are not literal per-cell Bernoulli trials).
    """

    mean: float | None
    n: int
    minimum: float | None
    maximum: float | None

    @staticmethod
    def from_values(values: Sequence[float]) -> Stat:
        if not values:
            return Stat(mean=None, n=0, minimum=None, maximum=None)
        return Stat(mean=sum(values) / len(values), n=len(values), minimum=min(values), maximum=max(values))

    def to_json(self) -> dict[str, Any]:
        return {"mean": self.mean, "n": self.n, "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True)
class RateStat:
    """Descriptive + Wilson-interval summary of a binary per-cell fact
    (won/not-won, survived/not-survived, captured/not-captured, ...).
    """

    successes: int
    trials: int
    confidence_level: float = 0.95

    @property
    def rate(self) -> float | None:
        return (self.successes / self.trials) if self.trials else None

    @property
    def interval(self) -> WilsonInterval | None:
        return wilson_interval(self.successes, self.trials, self.confidence_level) if self.trials else None

    def to_json(self) -> dict[str, Any]:
        interval = self.interval
        return {
            "successes": self.successes,
            "trials": self.trials,
            "rate": self.rate,
            "interval": interval.to_json() if interval is not None else None,
        }


# ---------------------------------------------------------------------------
# Per-entrant summary over some scope's records (all / one seat / one
# layout / one seed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntrantSummary:
    agent_id: str
    scope_label: str
    sample_count: int
    available_count: int
    winner: RateStat
    survival: RateStat
    elimination: RateStat
    score: Stat
    margin_to_winner: Stat
    territory_last_pct: Stat
    territory_max_pct: Stat
    territory_avg_pct: Stat
    territory_retention: Stat
    kills_per_match: Stat
    deaths_per_match: Stat
    kill_involvement: RateStat
    capture_caused: RateStat
    capture_suffered: RateStat
    capture_tick_caused: Stat
    capture_tick_suffered: Stat

    def to_json(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "scope_label": self.scope_label,
            "sample_count": self.sample_count,
            "available_count": self.available_count,
            "winner": self.winner.to_json(),
            "survival": self.survival.to_json(),
            "elimination": self.elimination.to_json(),
            "score": self.score.to_json(),
            "margin_to_winner": self.margin_to_winner.to_json(),
            "territory_last_pct": self.territory_last_pct.to_json(),
            "territory_max_pct": self.territory_max_pct.to_json(),
            "territory_avg_pct": self.territory_avg_pct.to_json(),
            "territory_retention": self.territory_retention.to_json(),
            "kills_per_match": self.kills_per_match.to_json(),
            "deaths_per_match": self.deaths_per_match.to_json(),
            "kill_involvement": self.kill_involvement.to_json(),
            "capture_caused": self.capture_caused.to_json(),
            "capture_suffered": self.capture_suffered.to_json(),
            "capture_tick_caused": self.capture_tick_caused.to_json(),
            "capture_tick_suffered": self.capture_tick_suffered.to_json(),
        }


def _values(records: Sequence[EntrantCellRecord], extractor: Any) -> list[float]:
    return [v for r in records if (v := extractor(r)) is not None]


def entrant_summary(
    agent_id: str, scope_label: str, records: Sequence[EntrantCellRecord]
) -> EntrantSummary:
    """One entrant's descriptive + inferential summary over ``records``.

    ``records`` is expected to already be filtered to the scope this
    summary describes (all cells, one seat, one layout, or one seed) --
    this function itself only filters by ``agent_id``, so the same
    building block serves every scope in this module.
    """

    own = [r for r in records if r.agent_id == agent_id]
    available = [r for r in own if r.available]
    n = len(available)
    wins = sum(1 for r in available if r.outcome == EntrantOutcome.WINNER)
    survivors = sum(1 for r in available if r.outcome in (EntrantOutcome.WINNER, EntrantOutcome.SURVIVING_NON_WINNER))
    eliminated = sum(1 for r in available if r.outcome == EntrantOutcome.ELIMINATED)
    kill_known = [r for r in available if r.kills is not None]
    kill_values = [r.kills for r in kill_known if r.kills is not None]
    captured_known = [r for r in available if r.captured is not None]
    capture_ticks_suffered = [float(r.capture_tick) for r in available if r.capture_tick is not None]
    capture_ticks_caused = [float(r.capture_tick_caused) for r in available if r.capture_tick_caused is not None]

    return EntrantSummary(
        agent_id=agent_id,
        scope_label=scope_label,
        sample_count=len(own),
        available_count=n,
        winner=RateStat(wins, n),
        survival=RateStat(survivors, n),
        elimination=RateStat(eliminated, n),
        score=Stat.from_values(_values(available, lambda r: r.score)),
        margin_to_winner=Stat.from_values(_values(available, lambda r: r.margin_to_winner)),
        territory_last_pct=Stat.from_values(_values(available, lambda r: r.territory_last_pct)),
        territory_max_pct=Stat.from_values(_values(available, lambda r: r.territory_max_pct)),
        territory_avg_pct=Stat.from_values(_values(available, lambda r: r.territory_avg_pct)),
        territory_retention=Stat.from_values(_values(available, lambda r: r.territory_retention)),
        kills_per_match=Stat.from_values([float(k) for k in kill_values]),
        deaths_per_match=Stat.from_values([float(r.deaths) for r in available if r.deaths is not None]),
        kill_involvement=RateStat(sum(1 for r in kill_known if (r.kills or 0) >= 1), len(kill_known)),
        capture_caused=RateStat(sum(1 for r in available if r.captor_of), n),
        capture_suffered=RateStat(sum(1 for r in captured_known if r.captured), len(captured_known)),
        capture_tick_caused=Stat.from_values(capture_ticks_caused),
        capture_tick_suffered=Stat.from_values(capture_ticks_suffered),
    )


# ---------------------------------------------------------------------------
# Sensitivity: seat / layout / seed (Sec 15/16/17/18)
# ---------------------------------------------------------------------------


def _group_by(records: Sequence[EntrantCellRecord], key: Any) -> dict[Any, list[EntrantCellRecord]]:
    """Generic grouping over an explicit dimension (Sec 19) -- e.g.
    ``_group_by(records, lambda r: r.seat)``. Never used to permanently
    collapse a dimension: callers always retain ``records`` itself
    (full-permutation detail) alongside any grouped view built from it.
    """

    buckets: dict[Any, list[EntrantCellRecord]] = defaultdict(list)
    for record in records:
        buckets[key(record)].append(record)
    return buckets


def _rate_range(summaries: Sequence[EntrantSummary], rate: Any) -> float | None:
    values = [v for s in summaries if (v := rate(s)) is not None]
    return (max(values) - min(values)) if len(values) >= 2 else None


@dataclass(frozen=True)
class SeatSensitivity:
    agent_id: str
    by_seat: tuple[EntrantSummary, ...]
    winner_rate_range: float | None
    survival_rate_range: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "by_seat": [s.to_json() for s in self.by_seat],
            "winner_rate_range": self.winner_rate_range,
            "survival_rate_range": self.survival_rate_range,
        }


def seat_sensitivity(agent_id: str, records: Sequence[EntrantCellRecord]) -> SeatSensitivity:
    own = [r for r in records if r.agent_id == agent_id]
    buckets = _group_by(own, lambda r: r.seat)
    by_seat = tuple(entrant_summary(agent_id, seat, buckets[seat]) for seat in sorted(buckets))
    return SeatSensitivity(
        agent_id=agent_id,
        by_seat=by_seat,
        winner_rate_range=_rate_range(by_seat, lambda s: s.winner.rate),
        survival_rate_range=_rate_range(by_seat, lambda s: s.survival.rate),
    )


@dataclass(frozen=True)
class LayoutSensitivity:
    agent_id: str
    by_layout: tuple[EntrantSummary, ...]
    winner_rate_range: float | None
    survival_rate_range: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "by_layout": [s.to_json() for s in self.by_layout],
            "winner_rate_range": self.winner_rate_range,
            "survival_rate_range": self.survival_rate_range,
        }


def layout_sensitivity(agent_id: str, records: Sequence[EntrantCellRecord]) -> LayoutSensitivity:
    own = [r for r in records if r.agent_id == agent_id]
    buckets = _group_by(own, lambda r: r.layout_id)
    by_layout = tuple(entrant_summary(agent_id, layout_id, buckets[layout_id]) for layout_id in sorted(buckets))
    return LayoutSensitivity(
        agent_id=agent_id,
        by_layout=by_layout,
        winner_rate_range=_rate_range(by_layout, lambda s: s.winner.rate),
        survival_rate_range=_rate_range(by_layout, lambda s: s.survival.rate),
    )


@dataclass(frozen=True)
class SeedSummary:
    agent_id: str
    by_seed: tuple[EntrantSummary, ...]
    best_seed: int | None
    worst_seed: int | None
    winner_rate_range: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "by_seed": [s.to_json() for s in self.by_seed],
            "best_seed": self.best_seed,
            "worst_seed": self.worst_seed,
            "winner_rate_range": self.winner_rate_range,
        }


def seed_summary(agent_id: str, records: Sequence[EntrantCellRecord]) -> SeedSummary:
    own = [r for r in records if r.agent_id == agent_id]
    buckets = _group_by(own, lambda r: r.seed)
    by_seed = tuple(entrant_summary(agent_id, str(seed), buckets[seed]) for seed in sorted(buckets))
    ranked = [s for s in by_seed if s.winner.rate is not None]
    ranked.sort(key=lambda s: (-(s.winner.rate or 0.0), s.scope_label))
    best = int(ranked[0].scope_label) if ranked else None
    worst = int(ranked[-1].scope_label) if ranked else None
    return SeedSummary(
        agent_id=agent_id,
        by_seed=by_seed,
        best_seed=best,
        worst_seed=worst,
        winner_rate_range=_rate_range(by_seed, lambda s: s.winner.rate),
    )


# ---------------------------------------------------------------------------
# Directed captor -> victim interaction matrix (Sec 13/14/31)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InteractionPair:
    captor_agent_id: str
    victim_agent_id: str
    count: int
    rate: float | None
    # Ticks are known only for the subset of ``count`` captures that were
    # also the cell's terminal event (see the module docstring's "Capture
    # timing" section) -- ``len(capture_ticks) <= count`` in general, never
    # padded with a guessed value for the rest.
    capture_ticks: tuple[int, ...]
    mean_capture_tick: float | None
    median_capture_tick: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "captor_agent_id": self.captor_agent_id,
            "victim_agent_id": self.victim_agent_id,
            "count": self.count,
            "rate": self.rate,
            "capture_ticks": list(self.capture_ticks),
            "mean_capture_tick": self.mean_capture_tick,
            "median_capture_tick": self.median_capture_tick,
        }


@dataclass(frozen=True)
class InteractionMatrix:
    pairs: tuple[InteractionPair, ...]
    unattributed_captures: int
    cells_analyzed: int

    def to_json(self) -> dict[str, Any]:
        return {
            "pairs": [p.to_json() for p in self.pairs],
            "unattributed_captures": self.unattributed_captures,
            "cells_analyzed": self.cells_analyzed,
        }


def interaction_matrix(records: Sequence[EntrantCellRecord]) -> InteractionMatrix:
    cells_analyzed = len({r.schedule_id for r in records})
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    pair_ticks: dict[tuple[str, str], list[int]] = defaultdict(list)
    for record in records:
        if not record.available:
            continue
        for victim in record.captor_of:
            key = (record.agent_id, victim)
            pair_counts[key] += 1
            if record.capture_tick_caused is not None:
                pair_ticks[key].append(record.capture_tick_caused)
    unattributed = sum(
        1
        for record in records
        if record.available
        and record.captured
        and not any(record.agent_id in victims for victims in (r.captor_of for r in records if r.schedule_id == record.schedule_id))
    )
    pairs = []
    for (captor, victim), count in sorted(pair_counts.items()):
        ticks = pair_ticks.get((captor, victim), [])
        pairs.append(
            InteractionPair(
                captor_agent_id=captor,
                victim_agent_id=victim,
                count=count,
                rate=(count / cells_analyzed) if cells_analyzed else None,
                capture_ticks=tuple(ticks),
                mean_capture_tick=(sum(ticks) / len(ticks)) if ticks else None,
                median_capture_tick=float(median(ticks)) if ticks else None,
            )
        )
    return InteractionMatrix(pairs=tuple(pairs), unattributed_captures=unattributed, cells_analyzed=cells_analyzed)


# ---------------------------------------------------------------------------
# Top-level group analysis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupAnalysis:
    roster_agent_ids: tuple[str, ...]
    cells_analyzed: int
    available_cells: int
    records: tuple[EntrantCellRecord, ...]
    entrant_summaries: tuple[EntrantSummary, ...]
    seat_sensitivity: tuple[SeatSensitivity, ...]
    layout_sensitivity: tuple[LayoutSensitivity, ...]
    seed_summary: tuple[SeedSummary, ...]
    interaction_matrix: InteractionMatrix

    def summary_for(self, agent_id: str) -> EntrantSummary | None:
        return next((s for s in self.entrant_summaries if s.agent_id == agent_id), None)

    def to_json(self) -> dict[str, Any]:
        return {
            "roster_agent_ids": list(self.roster_agent_ids),
            "cells_analyzed": self.cells_analyzed,
            "available_cells": self.available_cells,
            "entrant_summaries": [s.to_json() for s in self.entrant_summaries],
            "seat_sensitivity": [s.to_json() for s in self.seat_sensitivity],
            "layout_sensitivity": [s.to_json() for s in self.layout_sensitivity],
            "seed_summary": [s.to_json() for s in self.seed_summary],
            "interaction_matrix": self.interaction_matrix.to_json(),
        }


def analyze_group(roster_agent_ids: Sequence[str], refs: Sequence[GroupCellRef]) -> GroupAnalysis:
    """Top-level Phase 3 entry point: every group cell's ``GroupCellRef`` ->
    a full, entrant-symmetric ``GroupAnalysis``.

    Deliberately takes no candidate id -- see the module docstring's
    outcome-model section and ``candidate_focused_view`` below. Reads each
    ref's ``result.json`` exactly once (never once per entrant), consistent
    with ``evaluation_behavior``/``evaluation_capture``'s own real-I/O
    discipline: callers must call this deliberately, never from evaluation-
    history discovery/listing code.
    """

    records: list[EntrantCellRecord] = []
    for ref in refs:
        records.extend(load_group_cell_records(ref))
    records_t = tuple(records)

    unique_agents = tuple(dict.fromkeys(roster_agent_ids))
    entrant_summaries = tuple(entrant_summary(agent_id, "all", records_t) for agent_id in unique_agents)
    seat_views = tuple(seat_sensitivity(agent_id, records_t) for agent_id in unique_agents)
    layout_views = tuple(layout_sensitivity(agent_id, records_t) for agent_id in unique_agents)
    seed_views = tuple(seed_summary(agent_id, records_t) for agent_id in unique_agents)

    return GroupAnalysis(
        roster_agent_ids=tuple(roster_agent_ids),
        cells_analyzed=len(refs),
        available_cells=len({r.schedule_id for r in records_t if r.available}),
        records=records_t,
        entrant_summaries=entrant_summaries,
        seat_sensitivity=seat_views,
        layout_sensitivity=layout_views,
        seed_summary=seed_views,
        interaction_matrix=interaction_matrix(records_t),
    )


# ---------------------------------------------------------------------------
# Candidate-focused compatibility view (Sec 6/22): pure selection, no
# separate computation -- reruns nothing, recomputes nothing.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateGroupView:
    candidate_id: str
    candidate: EntrantSummary | None
    candidate_seat_sensitivity: SeatSensitivity | None
    candidate_layout_sensitivity: LayoutSensitivity | None
    candidate_seed_summary: SeedSummary | None
    other_entrants: tuple[EntrantSummary, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate": self.candidate.to_json() if self.candidate is not None else None,
            "candidate_seat_sensitivity": (
                self.candidate_seat_sensitivity.to_json() if self.candidate_seat_sensitivity is not None else None
            ),
            "candidate_layout_sensitivity": (
                self.candidate_layout_sensitivity.to_json()
                if self.candidate_layout_sensitivity is not None
                else None
            ),
            "candidate_seed_summary": (
                self.candidate_seed_summary.to_json() if self.candidate_seed_summary is not None else None
            ),
            "other_entrants": [s.to_json() for s in self.other_entrants],
        }


def candidate_focused_view(analysis: GroupAnalysis, candidate_id: str) -> CandidateGroupView:
    """Select ``candidate_id``'s own results out of ``analysis`` for
    candidate-oriented presentation (Sec 22) -- pure selection over
    ``analysis``'s already-symmetric per-entrant results; computes nothing
    new. Swapping which roster entrant is passed here changes only which
    entrant's fields are pulled to the front -- never the values
    themselves (Sec 21's symmetry invariant, enforced by construction
    since ``analyze_group`` never receives a candidate id to begin with).
    """

    return CandidateGroupView(
        candidate_id=candidate_id,
        candidate=analysis.summary_for(candidate_id),
        candidate_seat_sensitivity=next(
            (s for s in analysis.seat_sensitivity if s.agent_id == candidate_id), None
        ),
        candidate_layout_sensitivity=next(
            (s for s in analysis.layout_sensitivity if s.agent_id == candidate_id), None
        ),
        candidate_seed_summary=next((s for s in analysis.seed_summary if s.agent_id == candidate_id), None),
        other_entrants=tuple(s for s in analysis.entrant_summaries if s.agent_id != candidate_id),
    )


__all__ = [
    "CandidateGroupView",
    "EntrantCellRecord",
    "EntrantOutcome",
    "EntrantSummary",
    "GroupAnalysis",
    "GroupCellRef",
    "InteractionMatrix",
    "InteractionPair",
    "LayoutSensitivity",
    "RateStat",
    "SeatSensitivity",
    "SeedSummary",
    "Stat",
    "analyze_group",
    "candidate_focused_view",
    "entrant_summary",
    "group_cell_ref_from_evaluation_cell",
    "interaction_matrix",
    "layout_sensitivity",
    "load_group_cell_records",
    "seat_sensitivity",
    "seed_summary",
]
