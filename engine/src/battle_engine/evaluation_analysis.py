"""Phase 4 aggregate/statistical analysis over already-authoritative
evaluation data (``docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md``).

Pure, derived interpretation layer over ``agent_evaluation.SubjectAggregate``/
``ComparisonEntry`` — computes nothing that changes match execution,
scoring, canonical identity, or the persisted ``bytefray.evaluation``
schema. Every function here is a pure function of already-computed
evaluation cells; nothing in this module performs I/O or executes agent
code.

Statistical design (full rationale in the durable record above):

- Wilson score interval (never the naive normal/Wald approximation) for a
  single observed win proportion, computed over "win" vs. "not win"
  (ties folded into "not win", never credited as a half-win); tie/loss
  rates are always reported alongside so this choice is never hidden.
- An exact two-sided binomial test (the exact sign test / exact McNemar
  test at p=0.5) over *discordant* paired candidate/baseline outcomes —
  "discordant" and "better"/"worse" reuse ``agent_evaluation.classify()``
  unchanged (``win > tie > loss``); no second concept of improvement is
  invented here.
- Opponent and orientation are real blocking factors: the overall paired
  test pools across both (disclosed, not hidden), but a per-opponent and
  a per-orientation breakdown are always computed alongside it, plus a
  plain-language consistency label — never a single pooled verdict
  standing alone.
- Every quantity with a zero denominator reports an explicit
  insufficient-data state instead of a fabricated number.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from statistics import NormalDist
from typing import Any

from battle_engine.agent_evaluation import (
    BASELINE,
    CANDIDATE,
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_OPPONENT_FIRST,
    ComparisonEntry,
    EvaluationCell,
    SubjectAggregate,
    all_subject_aggregates,
    compare_candidate_baseline,
)

DEFAULT_CONFIDENCE_LEVEL = 0.95


def _z_value(confidence_level: float) -> float:
    if not 0.0 < confidence_level < 1.0:
        raise ValueError(f"confidence_level must be in (0, 1), got {confidence_level!r}")
    return NormalDist().inv_cdf(1.0 - (1.0 - confidence_level) / 2.0)


# ---------------------------------------------------------------------------
# Wilson score interval
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WilsonInterval:
    """A Wilson score interval for an observed binomial proportion.

    Formula (Wilson 1927; standard reference form, e.g. Brown/Cai/DasGupta
    2001)::

        p_hat = successes / trials
        z     = two-sided normal quantile for `confidence_level`
        center = (p_hat + z^2/(2n)) / (1 + z^2/n)
        half_width = z * sqrt(p_hat*(1-p_hat)/n + z^2/(4n^2)) / (1 + z^2/n)
        interval = [max(0, center - half_width), min(1, center + half_width)]

    Preferred over the naive normal ("Wald") approximation because it
    stays well-behaved (and inside [0, 1]) at small n and at p_hat near 0
    or 1 — exactly the regime Bytefray evaluation matrices commonly
    produce.
    """

    lower: float
    upper: float
    confidence_level: float

    def to_json(self) -> dict[str, Any]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "confidence_level": self.confidence_level,
        }


def wilson_interval(
    successes: int, trials: int, confidence_level: float = DEFAULT_CONFIDENCE_LEVEL
) -> WilsonInterval | None:
    """Wilson score interval for ``successes`` out of ``trials``.

    Returns ``None`` when ``trials == 0`` — there is no meaningful interval
    to report, not a fabricated ``[0, 1]`` or ``[0, 0]``.
    """

    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError(f"invalid successes/trials: {successes}/{trials}")
    if trials == 0:
        return None
    z = _z_value(confidence_level)
    n = float(trials)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half_width = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
    return WilsonInterval(
        lower=max(0.0, center - half_width),
        upper=min(1.0, center + half_width),
        confidence_level=confidence_level,
    )


# ---------------------------------------------------------------------------
# Exact paired significance test (exact sign test / exact McNemar at p=0.5)
# ---------------------------------------------------------------------------


def exact_two_sided_binomial_p_value(successes: int, trials: int, p: float = 0.5) -> float:
    """Exact two-sided binomial test p-value, by doubling the smaller tail.

    At ``p=0.5`` (the only value this module ever calls this with — the
    null hypothesis that candidate and baseline are equally likely to be
    the better side of a discordant pair) the binomial distribution is
    symmetric, so "double the smaller tail" coincides exactly with the
    more general "sum every outcome at least as improbable as the
    observed one" definition of a two-sided exact test (they can differ
    for ``p != 0.5``, but never here). Implemented with ``math.comb``
    (stdlib, exact integer binomial coefficients) rather than a normal
    approximation, per the preference for exact methods at small N.
    """

    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError(f"invalid successes/trials: {successes}/{trials}")
    if trials == 0:
        raise ValueError("exact_two_sided_binomial_p_value requires trials > 0")

    def pmf(k: int) -> float:
        return math.comb(trials, k) * (p**k) * ((1.0 - p) ** (trials - k))

    lower_tail = sum(pmf(k) for k in range(successes + 1))
    upper_tail = sum(pmf(k) for k in range(successes, trials + 1))
    return min(1.0, 2.0 * min(lower_tail, upper_tail))


# ---------------------------------------------------------------------------
# Descriptive + inferential rate estimate (one subject, one scope)
# ---------------------------------------------------------------------------


class SampleState(str, Enum):
    EVALUATED = "evaluated"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class RateEstimate:
    """Descriptive + Wilson-interval summary of one subject's observed
    win/loss/tie record over its scored cells in some scope (pooled or one
    orientation).

    Tie handling: the Wilson interval is over "win" vs. "not win" (loss or
    tie) — ties are never counted as half a win. ``tie_rate``/``loss_rate``
    are always reported alongside so a high tie rate is never hidden
    behind a win-rate number that implicitly treated ties as losses
    without saying so.
    """

    scope_label: str
    subject_role: str
    subject_id: str
    matches_played: int
    wins: int
    losses: int
    ties: int
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL

    @property
    def state(self) -> SampleState:
        return SampleState.EVALUATED if self.matches_played > 0 else SampleState.INSUFFICIENT_DATA

    @property
    def observed_win_rate(self) -> float | None:
        return (self.wins / self.matches_played) if self.matches_played else None

    @property
    def tie_rate(self) -> float | None:
        return (self.ties / self.matches_played) if self.matches_played else None

    @property
    def loss_rate(self) -> float | None:
        return (self.losses / self.matches_played) if self.matches_played else None

    @property
    def win_interval(self) -> WilsonInterval | None:
        return wilson_interval(self.wins, self.matches_played, self.confidence_level)

    def to_json(self) -> dict[str, Any]:
        interval = self.win_interval
        return {
            "scope_label": self.scope_label,
            "subject_role": self.subject_role,
            "subject_id": self.subject_id,
            "matches_played": self.matches_played,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "state": self.state.value,
            "observed_win_rate": self.observed_win_rate,
            "tie_rate": self.tie_rate,
            "loss_rate": self.loss_rate,
            "win_interval": interval.to_json() if interval is not None else None,
        }


def rate_estimate_from_aggregate(
    aggregate: SubjectAggregate,
    *,
    scope_label: str | None = None,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> RateEstimate:
    return RateEstimate(
        scope_label=scope_label if scope_label is not None else aggregate.orientation_scope,
        subject_role=aggregate.subject_role,
        subject_id=aggregate.subject_id,
        matches_played=aggregate.matches_played,
        wins=aggregate.wins,
        losses=aggregate.losses,
        ties=aggregate.ties,
        confidence_level=confidence_level,
    )


# ---------------------------------------------------------------------------
# Exact paired candidate-vs-baseline evidence (one scope)
# ---------------------------------------------------------------------------


class EvidenceState(str, Enum):
    EVALUATED = "evaluated"
    NO_MATCHED_CONDITIONS = "no_matched_conditions"
    NO_DISCORDANT_PAIRS = "no_discordant_pairs"


class PairedDirection(str, Enum):
    FAVORS_CANDIDATE = "favors_candidate"
    FAVORS_BASELINE = "favors_baseline"
    EVEN = "even"
    UNDETERMINED = "undetermined"


def _mean(values: Sequence[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


@dataclass(frozen=True)
class PairedEvidence:
    """Exact paired candidate-vs-baseline evidence over one scope (overall,
    one opponent, or one orientation) — built from ``ComparisonEntry`` rows
    (or, via ``paired_evidence_from_verdicts``, an equivalent verdict
    sequence), which already pair candidate and baseline cells by exact
    matched conditions.

    "Better"/"equal"/"worse" reuse the existing ``classify()`` outcome-rank
    comparator unchanged (``win > tie > loss``) — no second concept of
    "improvement" is invented here. A discordant pair is one classified
    ``"improved"`` or ``"regressed"``; the exact test/interval below are
    computed over discordant pairs only, matching the standard exact-
    McNemar/sign-test definition of "discordant" for a paired binary
    comparison.
    """

    scope_label: str
    paired_count: int
    improved: int
    regressed: int
    unchanged: int
    inconclusive: int
    candidate_score_differential_avg: float | None = None
    baseline_score_differential_avg: float | None = None
    candidate_territory_avg: float | None = None
    baseline_territory_avg: float | None = None
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL

    @property
    def discordant(self) -> int:
        return self.improved + self.regressed

    @property
    def state(self) -> EvidenceState:
        if self.paired_count == 0:
            return EvidenceState.NO_MATCHED_CONDITIONS
        if self.discordant == 0:
            return EvidenceState.NO_DISCORDANT_PAIRS
        return EvidenceState.EVALUATED

    @property
    def direction(self) -> PairedDirection:
        if self.discordant == 0:
            return PairedDirection.UNDETERMINED
        if self.improved > self.regressed:
            return PairedDirection.FAVORS_CANDIDATE
        if self.regressed > self.improved:
            return PairedDirection.FAVORS_BASELINE
        return PairedDirection.EVEN

    @property
    def better_proportion_of_discordant(self) -> float | None:
        return (self.improved / self.discordant) if self.discordant else None

    @property
    def better_interval(self) -> WilsonInterval | None:
        if self.discordant == 0:
            return None
        return wilson_interval(self.improved, self.discordant, self.confidence_level)

    @property
    def exact_p_value(self) -> float | None:
        if self.discordant == 0:
            return None
        return exact_two_sided_binomial_p_value(self.improved, self.discordant)

    def to_json(self) -> dict[str, Any]:
        interval = self.better_interval
        return {
            "scope_label": self.scope_label,
            "paired_count": self.paired_count,
            "improved": self.improved,
            "regressed": self.regressed,
            "unchanged": self.unchanged,
            "inconclusive": self.inconclusive,
            "discordant": self.discordant,
            "state": self.state.value,
            "direction": self.direction.value,
            "better_proportion_of_discordant": self.better_proportion_of_discordant,
            "better_interval": interval.to_json() if interval is not None else None,
            "exact_p_value": self.exact_p_value,
            "candidate_score_differential_avg": self.candidate_score_differential_avg,
            "baseline_score_differential_avg": self.baseline_score_differential_avg,
            "candidate_territory_avg": self.candidate_territory_avg,
            "baseline_territory_avg": self.baseline_territory_avg,
        }


def paired_evidence_from_entries(
    scope_label: str,
    entries: Sequence[ComparisonEntry],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> PairedEvidence:
    improved = sum(1 for entry in entries if entry.classification == "improved")
    regressed = sum(1 for entry in entries if entry.classification == "regressed")
    unchanged = sum(1 for entry in entries if entry.classification == "unchanged")
    inconclusive = sum(1 for entry in entries if entry.classification == "inconclusive")
    candidate_score_diffs = [
        entry.candidate_score_differential
        for entry in entries
        if entry.candidate_score_differential is not None
    ]
    baseline_score_diffs = [
        entry.baseline_score_differential
        for entry in entries
        if entry.baseline_score_differential is not None
    ]
    candidate_territories = [
        entry.candidate_territory for entry in entries if entry.candidate_territory is not None
    ]
    baseline_territories = [
        entry.baseline_territory for entry in entries if entry.baseline_territory is not None
    ]
    return PairedEvidence(
        scope_label=scope_label,
        paired_count=len(entries),
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
        inconclusive=inconclusive,
        candidate_score_differential_avg=_mean(candidate_score_diffs),
        baseline_score_differential_avg=_mean(baseline_score_diffs),
        candidate_territory_avg=_mean(candidate_territories),
        baseline_territory_avg=_mean(baseline_territories),
        confidence_level=confidence_level,
    )


def paired_evidence_from_verdicts(
    scope_label: str,
    verdicts: Sequence[str],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> PairedEvidence:
    """Same computation, generalized over a plain
    ``"improved"``/``"regressed"``/``"unchanged"``/``"inconclusive"``
    verdict sequence — e.g. ``evaluation_history.comparison.
    ComparisonRow.verdict``, which uses the identical vocabulary
    (``comparison.py``'s ``verdict()`` is documented as "the identical
    mapping to ``agent_evaluation.classify``, oriented right-vs-left").
    Used for ``evaluations compare`` (no ``ComparisonEntry`` of its own —
    it compares two separate evaluation artifacts, not candidate vs.
    baseline within one).
    """

    improved = sum(1 for v in verdicts if v == "improved")
    regressed = sum(1 for v in verdicts if v == "regressed")
    unchanged = sum(1 for v in verdicts if v == "unchanged")
    inconclusive = sum(1 for v in verdicts if v == "inconclusive")
    return PairedEvidence(
        scope_label=scope_label,
        paired_count=len(verdicts),
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
        inconclusive=inconclusive,
        confidence_level=confidence_level,
    )


def _consistency_label(scopes: Sequence[PairedEvidence]) -> str:
    evaluated = [scope for scope in scopes if scope.discordant > 0]
    if not evaluated:
        return "insufficient evidence to assess consistency (no discordant pairs in any group)"
    directions = {scope.direction for scope in evaluated}
    if directions == {PairedDirection.FAVORS_CANDIDATE}:
        return "consistent: every group with discordant pairs favors the candidate"
    if directions == {PairedDirection.FAVORS_BASELINE}:
        return "consistent: every group with discordant pairs favors the baseline"
    if directions == {PairedDirection.EVEN}:
        return "consistent: no group with discordant pairs favors either side"
    return "mixed: groups disagree on direction -- see the by-opponent/by-orientation breakdown"


# ---------------------------------------------------------------------------
# Top-level evaluation analysis
# ---------------------------------------------------------------------------

_NOT_APPLICABLE_NO_BASELINE = "not applicable: no baseline set for this evaluation"


@dataclass(frozen=True)
class EvaluationAnalysis:
    candidate_id: str
    baseline_id: str | None
    confidence_level: float
    candidate_overall: RateEstimate
    candidate_by_orientation: tuple[RateEstimate, ...]
    baseline_overall: RateEstimate | None
    baseline_by_orientation: tuple[RateEstimate, ...]
    overall_paired: PairedEvidence | None
    by_opponent: tuple[PairedEvidence, ...]
    by_orientation: tuple[PairedEvidence, ...]
    opponent_consistency: str
    orientation_consistency: str

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "baseline_id": self.baseline_id,
            "confidence_level": self.confidence_level,
            "candidate_overall": self.candidate_overall.to_json(),
            "candidate_by_orientation": [r.to_json() for r in self.candidate_by_orientation],
            "baseline_overall": self.baseline_overall.to_json() if self.baseline_overall else None,
            "baseline_by_orientation": [r.to_json() for r in self.baseline_by_orientation],
            "overall_paired": self.overall_paired.to_json() if self.overall_paired else None,
            "by_opponent": [p.to_json() for p in self.by_opponent],
            "by_orientation": [p.to_json() for p in self.by_orientation],
            "opponent_consistency": self.opponent_consistency,
            "orientation_consistency": self.orientation_consistency,
        }


def analyze(
    candidate_id: str,
    baseline_id: str | None,
    cells: Sequence[EvaluationCell],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> EvaluationAnalysis:
    """Top-level Phase 4 entry point: derive descriptive + inferential
    analysis from already-canonical evaluation cells.

    Pure; reads nothing from disk, executes no agent code, and never
    recomputes anything ``agent_evaluation.all_subject_aggregates``/
    ``compare_candidate_baseline`` already compute -- this function only
    interprets their output.
    """

    aggregates = all_subject_aggregates(candidate_id, baseline_id, cells)
    aggregates_by_key: dict[tuple[str, str, str], SubjectAggregate] = {
        (a.subject_role, a.subject_id, a.orientation_scope): a for a in aggregates
    }
    orientation_scopes = (ORIENTATION_CANDIDATE_FIRST, ORIENTATION_OPPONENT_FIRST)

    candidate_overall = rate_estimate_from_aggregate(
        aggregates_by_key[(CANDIDATE, candidate_id, "all")],
        scope_label="overall",
        confidence_level=confidence_level,
    )
    candidate_by_orientation = tuple(
        rate_estimate_from_aggregate(
            aggregates_by_key[(CANDIDATE, candidate_id, scope)],
            scope_label=scope,
            confidence_level=confidence_level,
        )
        for scope in orientation_scopes
    )

    baseline_overall: RateEstimate | None = None
    baseline_by_orientation: tuple[RateEstimate, ...] = ()
    overall_paired: PairedEvidence | None = None
    by_opponent: tuple[PairedEvidence, ...] = ()
    by_orientation: tuple[PairedEvidence, ...] = ()
    opponent_consistency = _NOT_APPLICABLE_NO_BASELINE
    orientation_consistency = _NOT_APPLICABLE_NO_BASELINE

    if baseline_id is not None:
        baseline_overall = rate_estimate_from_aggregate(
            aggregates_by_key[(BASELINE, baseline_id, "all")],
            scope_label="overall",
            confidence_level=confidence_level,
        )
        baseline_by_orientation = tuple(
            rate_estimate_from_aggregate(
                aggregates_by_key[(BASELINE, baseline_id, scope)],
                scope_label=scope,
                confidence_level=confidence_level,
            )
            for scope in orientation_scopes
        )

        comparison = compare_candidate_baseline(cells)
        overall_paired = paired_evidence_from_entries(
            "overall", comparison, confidence_level=confidence_level
        )

        opponent_ids = sorted({entry.opponent_id for entry in comparison})
        by_opponent = tuple(
            paired_evidence_from_entries(
                opponent_id,
                [entry for entry in comparison if entry.opponent_id == opponent_id],
                confidence_level=confidence_level,
            )
            for opponent_id in opponent_ids
        )
        orientations = sorted({entry.orientation for entry in comparison})
        by_orientation = tuple(
            paired_evidence_from_entries(
                orientation,
                [entry for entry in comparison if entry.orientation == orientation],
                confidence_level=confidence_level,
            )
            for orientation in orientations
        )
        opponent_consistency = _consistency_label(by_opponent)
        orientation_consistency = _consistency_label(by_orientation)

    return EvaluationAnalysis(
        candidate_id=candidate_id,
        baseline_id=baseline_id,
        confidence_level=confidence_level,
        candidate_overall=candidate_overall,
        candidate_by_orientation=candidate_by_orientation,
        baseline_overall=baseline_overall,
        baseline_by_orientation=baseline_by_orientation,
        overall_paired=overall_paired,
        by_opponent=by_opponent,
        by_orientation=by_orientation,
        opponent_consistency=opponent_consistency,
        orientation_consistency=orientation_consistency,
    )


__all__ = [
    "DEFAULT_CONFIDENCE_LEVEL",
    "EvaluationAnalysis",
    "EvidenceState",
    "PairedDirection",
    "PairedEvidence",
    "RateEstimate",
    "SampleState",
    "WilsonInterval",
    "analyze",
    "exact_two_sided_binomial_p_value",
    "paired_evidence_from_entries",
    "paired_evidence_from_verdicts",
    "rate_estimate_from_aggregate",
    "wilson_interval",
]
