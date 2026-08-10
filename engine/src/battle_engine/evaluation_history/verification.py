"""Shared deep-verification path for ``show --verify``/``compare --verify`` (B3/Sec 15).

Ordinary (non-``--verify``) adaptation never calls into this module -- its
output is evidence read and recomputed from the artifact's own recorded
fields, never independently verified against nested result/replay
artifacts. Only an explicit ``--verify`` should claim verified evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from battle_engine.agent_test import OPPONENT_SLOT, TESTED_AGENT_SLOT
from battle_engine.result_model import ReplayIntegrityError, read_result, verify_replay_digest
from battle_engine.results import WINNER_TIE_SENTINEL

from .models import (
    AdaptedCell,
    ArtifactPathEscapeError,
    EvaluationSummary,
    FieldConfidence,
    resolve_contained_path,
)

_EXPECTED_ENTRANT_ORDER = (TESTED_AGENT_SLOT, OPPONENT_SLOT)
# Identity fields both a frozen `agent_identity()`-shaped ConfidenceValue
# (recorded planned/opponent identity) and a real result envelope's
# per-entrant `metadata` (Python kind) carry -- the intersection usable to
# cross-check recorded plan identity against what the canonical result
# actually recorded for that entrant.
_IDENTITY_METADATA_FIELDS = ("source_sha256", "api_version", "agent_version")


@dataclass(frozen=True)
class CellVerificationOutcome:
    schedule_id: str
    eligible: bool
    verified: bool
    error: str | None = None


def verify_cell(cell: AdaptedCell, base_dir: Path) -> CellVerificationOutcome:
    """Deep-verify one completed, scored cell against its nested artifacts.

    Checks (as appropriate/available): nested result exists and is
    readable; the artifact path is contained beneath ``base_dir`` (M4);
    replay exists and its digest matches; the result's ``match_id``, seed,
    and entrant order match the evaluation cell's own recorded values; the
    canonical result's winner is consistent with the cell's recorded
    outcome; and, when the opponent's identity was actually ``RECORDED``
    (v2 only -- v1 identity is always ``UNKNOWN`` and is never silently
    treated as matching), the opponent's recorded source/version identity
    matches the result's own per-entrant metadata.

    Cells that never claim a real, scored outcome (pending/failed/
    corrupted/drift-detected) are ``eligible=False`` -- skipped, never
    silently counted toward "verified".
    """

    if not cell.is_scored:
        return CellVerificationOutcome(cell.schedule_id, eligible=False, verified=False)

    try:
        result_path = resolve_contained_path(base_dir, cell.artifact_dir) / "result.json"
    except ArtifactPathEscapeError as exc:
        return CellVerificationOutcome(cell.schedule_id, True, False, str(exc))

    if not result_path.is_file():
        return CellVerificationOutcome(
            cell.schedule_id, True, False, f"missing nested result: {result_path}"
        )
    try:
        envelope = read_result(result_path)
    except (OSError, ValueError, KeyError) as exc:
        return CellVerificationOutcome(
            cell.schedule_id, True, False, f"result unreadable: {exc}"
        )

    if envelope.replay is None:
        return CellVerificationOutcome(
            cell.schedule_id, True, False, "result has no replay reference to verify"
        )
    replay_path = result_path.parent / envelope.replay.filename
    try:
        verify_replay_digest(envelope, replay_path)
    except ReplayIntegrityError as exc:
        return CellVerificationOutcome(
            cell.schedule_id, True, False, f"replay verification failed ({exc.code}): {exc}"
        )

    if cell.match_id is not None and envelope.match_id != cell.match_id:
        return CellVerificationOutcome(
            cell.schedule_id,
            True,
            False,
            f"result match_id {envelope.match_id!r} does not match the recorded "
            f"cell match_id {cell.match_id!r}",
        )

    entrant_order = tuple(str(entry.get("agent_id")) for entry in envelope.entrants)
    if entrant_order != _EXPECTED_ENTRANT_ORDER:
        return CellVerificationOutcome(
            cell.schedule_id,
            True,
            False,
            f"entrant order {entrant_order} does not match expected {_EXPECTED_ENTRANT_ORDER}",
        )

    actual_seed = envelope.reproducibility.get("seed")
    if actual_seed != cell.seed:
        return CellVerificationOutcome(
            cell.schedule_id,
            True,
            False,
            f"result seed {actual_seed!r} does not match the recorded cell seed {cell.seed!r}",
        )

    winner = envelope.winner
    expected_outcome = (
        "tie"
        if winner == WINNER_TIE_SENTINEL
        else "win"
        if winner == TESTED_AGENT_SLOT
        else "loss"
    )
    if expected_outcome != cell.outcome:
        return CellVerificationOutcome(
            cell.schedule_id,
            True,
            False,
            f"result winner implies outcome {expected_outcome!r}, but the evaluation "
            f"cell recorded {cell.outcome!r}",
        )

    if cell.opponent_identity.confidence == FieldConfidence.RECORDED:
        opponent_entry = next(
            (entry for entry in envelope.entrants if entry.get("agent_id") == OPPONENT_SLOT), {}
        )
        opponent_metadata = opponent_entry.get("metadata") or {}
        planned = cell.opponent_identity.value or {}
        mismatched = sorted(
            field
            for field in _IDENTITY_METADATA_FIELDS
            if field in planned and planned[field] != opponent_metadata.get(field)
        )
        if mismatched:
            return CellVerificationOutcome(
                cell.schedule_id,
                True,
                False,
                f"opponent identity fields {mismatched} do not match the recorded plan",
            )

    return CellVerificationOutcome(cell.schedule_id, True, True)


@dataclass(frozen=True)
class SummaryVerification:
    outcomes: tuple[CellVerificationOutcome, ...]
    eligible_count: int
    verified_count: int
    failed: tuple[CellVerificationOutcome, ...]

    @property
    def all_eligible_verified(self) -> bool:
        """True only when at least one cell was eligible and every eligible
        cell verified -- never vacuously true for zero eligible cells."""

        return self.eligible_count > 0 and not self.failed


def verify_summary(summary: EvaluationSummary) -> tuple[EvaluationSummary, SummaryVerification]:
    """Deep-verify every eligible cell in ``summary`` and return an updated copy.

    The returned :class:`EvaluationSummary` has each cell's
    ``verified``/``verify_error`` populated -- the input ``summary`` itself
    is never mutated (frozen dataclasses throughout).
    """

    outcomes: list[CellVerificationOutcome] = []
    new_cells: list[AdaptedCell] = []
    for cell in summary.cells:
        outcome = verify_cell(cell, summary.location.directory)
        outcomes.append(outcome)
        if outcome.eligible:
            new_cells.append(replace(cell, verified=outcome.verified, verify_error=outcome.error))
        else:
            new_cells.append(cell)

    eligible = [outcome for outcome in outcomes if outcome.eligible]
    failed = tuple(outcome for outcome in eligible if not outcome.verified)
    verification = SummaryVerification(
        outcomes=tuple(outcomes),
        eligible_count=len(eligible),
        verified_count=sum(1 for outcome in eligible if outcome.verified),
        failed=failed,
    )
    return replace(summary, cells=tuple(new_cells)), verification


__all__ = [
    "CellVerificationOutcome",
    "SummaryVerification",
    "verify_cell",
    "verify_summary",
]
