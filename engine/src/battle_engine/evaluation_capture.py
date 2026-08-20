"""v2.0.0-beta2 Phase 1 capture/core-interaction analysis
(``docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md`` Sec Capture).

Sibling of ``evaluation_analysis.py`` (outcome/win-rate evidence) and
``evaluation_behavior.py`` (behavior profile) -- not a replacement or
extension of either. This module answers a third, distinct question: "did
Ruleset v2's Vulnerable Core mechanism actually get exercised, and by
whom" -- capture, capture tick, and killer attribution, deliberately kept
separate from win/loss/score (Phase 1M: a captured entrant can still be
ahead on score at the moment of capture, per alpha.3's founding evidence;
win/loss alone would erase this). Nothing here reads or derives from win
rate or score, and nothing here feeds back into either sibling module.

One data tier, matching ``evaluation_behavior``'s own Tier 2: each scored
cell's already-written, sibling ``result.json`` (``battle2.result`` v1,
read via ``result_model.read_result``). No replay reconstruction --
per-entrant ``termination_reason`` (Ruleset v2's ``"core_captured"``),
``statistics.kills``, and the match's own ``ticks`` (which, for a match
that terminated via capture, *is* the capture tick -- Vulnerable Core
capture ends the match at the tick it is detected) are already sufficient.
Minimum core integrity over time is deliberately deferred (Phase 1L): it
would require per-tick replay reconstruction, a materially higher cost
class than every other v2 Phase 1 metric, and is not required for this
phase's methodology validation.

Meaningful for Ruleset v2 cells only -- a v1 cell's entrants never carry a
``"core_captured"`` termination reason (Ruleset v1 has no core-capture
mechanism), so ``captured`` is simply always ``False`` for v1 cells; this
module never special-cases Ruleset identity itself, it just reflects
whatever ``result.json`` actually recorded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any

from battle_engine.agent_evaluation import BASELINE, CANDIDATE, physical_slots_for_orientation
from battle_engine.evaluation_behavior import CellRef
from battle_engine.result_model import read_result

CORE_CAPTURED_TERMINATION_REASON = "core_captured"


@dataclass(frozen=True)
class CellCaptureSample:
    """One scored cell's capture facts, from its own ``result.json``.

    ``available=False`` means the read did not succeed -- missing/
    unreadable/corrupt result, or either entrant missing from it -- and
    every capture-specific field is ``None``, exactly mirroring
    ``evaluation_behavior.CellBehaviorSample``'s own honest-unavailability
    contract (design doc Sec Capture: never fail a whole aggregate over one
    unreadable cell).
    """

    schedule_id: str
    subject_role: str
    subject_id: str
    opponent_id: str
    seed: int
    orientation: str
    available: bool
    unavailable_reason: str | None = None
    subject_captured: bool | None = None
    opponent_captured: bool | None = None
    capture_tick: int | None = None
    # "subject" | "opponent" | None -- None covers both "no capture
    # occurred" and "a capture occurred but the killer is not attributable
    # from result.json alone" (self-inflicted capture, or the killer's own
    # kill credit was not recorded for some other reason). Never guessed.
    killer: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "subject_role": self.subject_role,
            "subject_id": self.subject_id,
            "opponent_id": self.opponent_id,
            "seed": self.seed,
            "orientation": self.orientation,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "subject_captured": self.subject_captured,
            "opponent_captured": self.opponent_captured,
            "capture_tick": self.capture_tick,
            "killer": self.killer,
        }


def load_cell_capture_sample(ref: CellRef) -> CellCaptureSample:
    """Read ``ref``'s ``result.json`` into a ``CellCaptureSample``. Never raises."""

    base: dict[str, Any] = {
        "schedule_id": ref.schedule_id,
        "subject_role": ref.subject_role,
        "subject_id": ref.subject_id,
        "opponent_id": ref.opponent_id,
        "seed": ref.seed,
        "orientation": ref.orientation,
    }
    if ref.result_path is None:
        return CellCaptureSample(
            **base, available=False, unavailable_reason="no result artifact path resolved for this cell"
        )
    try:
        envelope = read_result(ref.result_path)
    except (OSError, ValueError, KeyError) as exc:
        return CellCaptureSample(**base, available=False, unavailable_reason=f"result unreadable: {exc}")

    subject_slot, opponent_slot = physical_slots_for_orientation(ref.orientation)
    subject_entrant = next((e for e in envelope.entrants if e.get("agent_id") == subject_slot), None)
    opponent_entrant = next((e for e in envelope.entrants if e.get("agent_id") == opponent_slot), None)
    if subject_entrant is None or opponent_entrant is None:
        return CellCaptureSample(
            **base, available=False, unavailable_reason="subject or opponent entrant missing from result"
        )

    subject_captured = subject_entrant.get("termination_reason") == CORE_CAPTURED_TERMINATION_REASON
    opponent_captured = opponent_entrant.get("termination_reason") == CORE_CAPTURED_TERMINATION_REASON
    # Vulnerable Core capture is checked once per tick and ends the match
    # at the tick it is detected (docs/RULES_V2.md) -- for a cell that
    # terminated via capture, the match's own recorded tick count already
    # *is* the capture tick; no separate replay-derived timestamp is needed.
    capture_tick = envelope.ticks if (subject_captured or opponent_captured) else None

    killer: str | None = None
    if subject_captured or opponent_captured:
        subject_kills = (subject_entrant.get("statistics") or {}).get("kills") or 0
        opponent_kills = (opponent_entrant.get("statistics") or {}).get("kills") or 0
        if subject_captured and opponent_kills >= 1:
            killer = "opponent"
        elif opponent_captured and subject_kills >= 1:
            killer = "subject"

    return CellCaptureSample(
        **base,
        available=True,
        unavailable_reason=None,
        subject_captured=subject_captured,
        opponent_captured=opponent_captured,
        capture_tick=capture_tick,
        killer=killer,
    )


# ---------------------------------------------------------------------------
# Aggregate: one subject's capture evidence across a set of cells
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptureAggregate:
    subject_role: str
    subject_id: str
    sample_count: int
    available_count: int
    captures_caused: int
    captures_suffered: int
    capture_rate_caused: float | None
    capture_rate_suffered: float | None
    # Fraction of available cells this subject was *not* captured in --
    # deliberately distinct from evaluation_behavior's continuous, within-
    # match "survival_fraction" (alive_ticks / ticks_run); this is a binary
    # per-match capture-avoidance rate (Phase 1M: capture and survival are
    # related but not the same fact).
    survival_rate: float | None
    capture_ticks: tuple[int, ...]
    mean_capture_tick: float | None
    median_capture_tick: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "subject_role": self.subject_role,
            "subject_id": self.subject_id,
            "sample_count": self.sample_count,
            "available_count": self.available_count,
            "captures_caused": self.captures_caused,
            "captures_suffered": self.captures_suffered,
            "capture_rate_caused": self.capture_rate_caused,
            "capture_rate_suffered": self.capture_rate_suffered,
            "survival_rate": self.survival_rate,
            "capture_ticks": list(self.capture_ticks),
            "mean_capture_tick": self.mean_capture_tick,
            "median_capture_tick": self.median_capture_tick,
        }


def _aggregate_from_samples(
    subject_role: str, subject_id: str, samples: Sequence[CellCaptureSample]
) -> CaptureAggregate:
    own = [s for s in samples if s.subject_role == subject_role and s.subject_id == subject_id]
    available = [s for s in own if s.available]
    n = len(available)
    captures_caused = sum(1 for s in available if s.opponent_captured)
    captures_suffered = sum(1 for s in available if s.subject_captured)
    capture_ticks = tuple(s.capture_tick for s in available if s.capture_tick is not None)
    return CaptureAggregate(
        subject_role=subject_role,
        subject_id=subject_id,
        sample_count=len(own),
        available_count=n,
        captures_caused=captures_caused,
        captures_suffered=captures_suffered,
        capture_rate_caused=(captures_caused / n) if n else None,
        capture_rate_suffered=(captures_suffered / n) if n else None,
        survival_rate=(1.0 - captures_suffered / n) if n else None,
        capture_ticks=capture_ticks,
        mean_capture_tick=(sum(capture_ticks) / len(capture_ticks)) if capture_ticks else None,
        median_capture_tick=float(median(capture_ticks)) if capture_ticks else None,
    )


@dataclass(frozen=True)
class CaptureAnalysis:
    candidate_id: str
    baseline_id: str | None
    candidate_overall: CaptureAggregate
    baseline_overall: CaptureAggregate | None

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "baseline_id": self.baseline_id,
            "candidate_overall": self.candidate_overall.to_json(),
            "baseline_overall": (
                self.baseline_overall.to_json() if self.baseline_overall is not None else None
            ),
        }


def analyze_capture(
    candidate_id: str, baseline_id: str | None, refs: Sequence[CellRef]
) -> CaptureAnalysis:
    """Top-level entry point: every scored cell's ``CellRef`` -> a full ``CaptureAnalysis``.

    Mirrors ``evaluation_behavior.analyze_behavior``'s call shape (a plain
    list of already-resolved ``CellRef``s, one ``result.json`` read per
    cell) so both the CLI and ``evaluation_history``'s presentation code
    can reuse the exact same cell-reference construction for both modules.
    """

    samples = [load_cell_capture_sample(ref) for ref in refs]
    candidate_overall = _aggregate_from_samples(CANDIDATE, candidate_id, samples)
    baseline_overall = (
        _aggregate_from_samples(BASELINE, baseline_id, samples) if baseline_id is not None else None
    )
    return CaptureAnalysis(
        candidate_id=candidate_id,
        baseline_id=baseline_id,
        candidate_overall=candidate_overall,
        baseline_overall=baseline_overall,
    )


__all__ = [
    "CORE_CAPTURED_TERMINATION_REASON",
    "CaptureAggregate",
    "CaptureAnalysis",
    "CellCaptureSample",
    "analyze_capture",
    "load_cell_capture_sample",
]
