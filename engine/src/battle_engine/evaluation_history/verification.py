"""Shared deep-verification path for ``show --verify``/``compare --verify`` (B3/Sec 15).

Ordinary (non-``--verify``) adaptation never calls into this module -- its
output is evidence read and recomputed from the artifact's own recorded
fields, never independently verified against nested result/replay
artifacts. Only an explicit ``--verify`` should claim verified evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from battle_engine.agent_test import OPPONENT_SLOT, TESTED_AGENT_SLOT
from battle_engine.paths import contained_path
from battle_engine.replay import ReplayHeader, iter_replay
from battle_engine.result_model import ReplayIntegrityError, read_result, verify_replay_digest
from battle_engine.results import WINNER_TIE_SENTINEL

from .models import (
    AdaptedCell,
    ArtifactPathEscapeError,
    ConfidenceValue,
    EvaluationSummary,
    FieldConfidence,
    resolve_contained_path,
)

_EXPECTED_ENTRANT_ORDER = (TESTED_AGENT_SLOT, OPPONENT_SLOT)
# Identity fields both a frozen `agent_identity()`-shaped ConfidenceValue
# (recorded planned candidate/baseline/opponent identity) and a real result
# envelope's per-entrant `metadata` (Python kind) carry -- the intersection
# usable to cross-check recorded plan identity against what the canonical
# result actually recorded for that entrant. `entry_point`/
# `local_source_fingerprint` (H1/B1, v0.7 closure pass): the executor now
# records both (see `match_service._build_python_result`), so a tampered or
# stale candidate/opponent identity claim can be caught on either of those
# dimensions too, not just source_sha256/api_version/agent_version.
_IDENTITY_METADATA_FIELDS = (
    "source_sha256",
    "api_version",
    "agent_version",
    "entry_point",
    "local_source_fingerprint",
)


@dataclass(frozen=True)
class CellVerificationOutcome:
    schedule_id: str
    eligible: bool
    verified: bool
    error: str | None = None


def _identity_mismatch(
    envelope_entrants: tuple[Mapping[str, Any], ...], slot: str, planned: ConfidenceValue
) -> list[str]:
    if planned.confidence != FieldConfidence.RECORDED:
        return []
    entry = next((entry for entry in envelope_entrants if entry.get("agent_id") == slot), {})
    actual_metadata = entry.get("metadata") or {}
    planned_value = planned.value or {}
    return sorted(
        field
        for field in _IDENTITY_METADATA_FIELDS
        if field in planned_value and planned_value[field] != actual_metadata.get(field)
    )


def verify_cell(
    cell: AdaptedCell, base_dir: Path, subject_identity: ConfidenceValue | None = None
) -> CellVerificationOutcome:
    """Deep-verify one completed, scored cell against its nested artifacts.

    Checks (as appropriate/available): nested result exists and is
    readable; the artifact path is contained beneath ``base_dir`` (M4), and
    so is the replay it references (H5) -- a tampered ``result.json`` whose
    replay filename tries to escape the cell's own artifact directory is
    refused rather than followed; replay exists, its digest matches, and
    its own header is internally consistent with the result envelope
    (H1); the result's ``result_id``, ``match_id``, seed, and entrant order
    match the evaluation cell's own recorded values; the canonical result's
    winner is consistent with the cell's recorded outcome; and, when the
    subject's (candidate/baseline) or opponent's identity was actually
    ``RECORDED`` (v2 only -- v1 identity is always ``UNKNOWN`` and is never
    silently treated as matching), that identity matches the result's own
    per-entrant metadata (H1: now including ``entry_point``/
    ``local_source_fingerprint``, not just source_sha256/api_version/
    agent_version).

    ``subject_identity`` is the candidate/baseline identity ``ConfidenceValue``
    from the owning summary appropriate to ``cell.subject_role`` -- passed
    in by :func:`verify_summary` rather than looked up here, since a single
    cell has no reference back to its owning summary. ``None`` is treated
    the same as ``ConfidenceValue.unknown()`` (candidate check skipped).

    Cells that never claim a real, scored outcome (pending/failed/
    corrupted/drift-detected) are ``eligible=False`` -- skipped, never
    silently counted toward "verified".
    """

    if not cell.is_scored:
        return CellVerificationOutcome(cell.schedule_id, eligible=False, verified=False)

    try:
        result_dir = resolve_contained_path(base_dir, cell.artifact_dir)
    except ArtifactPathEscapeError as exc:
        return CellVerificationOutcome(cell.schedule_id, True, False, str(exc))
    result_path = result_dir / "result.json"

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
    # H5: the replay filename comes from a persisted result.json this
    # module does not control -- resolve it through the same containment
    # discipline as any other nested artifact path (M4) rather than a bare
    # join, which a `../`, absolute, or symlink-escaping filename could
    # otherwise walk outside the cell's own artifact directory.
    replay_path = contained_path(result_dir, envelope.replay.filename)
    if replay_path is None:
        return CellVerificationOutcome(
            cell.schedule_id,
            True,
            False,
            f"result replay filename {envelope.replay.filename!r} escapes the "
            "cell's artifact directory",
        )
    try:
        verify_replay_digest(envelope, replay_path)
        header = next(
            (record for record in iter_replay(replay_path) if isinstance(record, ReplayHeader)),
            None,
        )
    except ReplayIntegrityError as exc:
        return CellVerificationOutcome(
            cell.schedule_id, True, False, f"replay verification failed ({exc.code}): {exc}"
        )
    except (OSError, ValueError) as exc:
        return CellVerificationOutcome(
            cell.schedule_id, True, False, f"replay header could not be read: {exc}"
        )

    # H1: the replay's own header must agree with the result envelope it
    # was published alongside -- a tampered/mismatched header would
    # otherwise pass unnoticed as long as the replay's byte digest still
    # matched (digest verification alone says nothing about the header
    # record's own field values).
    if header is None:
        return CellVerificationOutcome(cell.schedule_id, True, False, "replay has no header")
    if header.match_id != envelope.match_id:
        return CellVerificationOutcome(
            cell.schedule_id, True, False, "replay header match_id does not match result envelope"
        )
    if header.result_id != envelope.result_id:
        return CellVerificationOutcome(
            cell.schedule_id, True, False, "replay header result_id does not match result envelope"
        )

    # H1: the result's own result_id, as recorded on the evaluation cell,
    # must match what the canonical result actually carries -- catches a
    # tampered/substituted result_id that leaves match_id/outcome alone.
    if cell.result_id is not None and envelope.result_id != cell.result_id:
        return CellVerificationOutcome(
            cell.schedule_id,
            True,
            False,
            f"result result_id {envelope.result_id!r} does not match the recorded "
            f"cell result_id {cell.result_id!r}",
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

    # H1: candidate/baseline planned identity -- previously only the
    # opponent's identity was cross-checked here, so a tampered candidate
    # `source_sha256`/entry_point/etc. in either the plan or the result
    # went entirely uncaught by deep verification.
    subject_mismatched = _identity_mismatch(
        envelope.entrants, TESTED_AGENT_SLOT, subject_identity or ConfidenceValue.unknown()
    )
    if subject_mismatched:
        return CellVerificationOutcome(
            cell.schedule_id,
            True,
            False,
            f"{cell.subject_role} identity fields {subject_mismatched} do not match the recorded plan",
        )

    opponent_mismatched = _identity_mismatch(envelope.entrants, OPPONENT_SLOT, cell.opponent_identity)
    if opponent_mismatched:
        return CellVerificationOutcome(
            cell.schedule_id,
            True,
            False,
            f"opponent identity fields {opponent_mismatched} do not match the recorded plan",
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
        subject_identity = (
            summary.candidate_identity if cell.subject_role == "candidate" else summary.baseline_identity
        )
        outcome = verify_cell(cell, summary.location.directory, subject_identity)
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
