"""Bridges evaluation-history's ``AdaptedCell`` to Phase 5 behavior refs
(``docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md``).

Deliberately a separate module from ``models.py``/``cli.py``: it is the one
place ``evaluation_history`` composes its own path-containment discipline
(``resolve_contained_path``, the same M4 rule ``verification.verify_cell``
already applies to a cell's nested ``result.json``) with
``battle_engine.evaluation_behavior``'s cell-detail read, so containment
checking is never silently skipped for a historical (on-disk, potentially
hand-edited) artifact the way it is legitimately skipped for the live-run
path (``agent_evaluation.py`` already trusts a directory it just created).

Never called by ``discovery.py``/``adapt_v1``/``adapt_v2`` -- unlike Phase
4's ``analysis`` (pure, free), behavior computation performs real I/O (one
``result.json`` read per scored cell), so it must stay opt-in and never
run merely because an evaluation was discovered/listed (Sec 10/24 of the
design doc).
"""

from __future__ import annotations

from battle_engine.agent_evaluation import ORIENTATION_CANDIDATE_FIRST
from battle_engine.evaluation_behavior import CellRef

from .models import ArtifactPathEscapeError, EvaluationSummary, resolve_contained_path


def cell_refs_for_behavior(summary: EvaluationSummary) -> tuple[CellRef, ...]:
    """Resolved, containment-checked ``CellRef``\\ s for every scored cell.

    A cell whose recorded ``artifact_dir`` escapes the evaluation's own
    directory gets ``result_path=None`` (refused, never followed) rather
    than raising -- the loader already treats that identically to a
    missing file, so one refusal never aborts the whole profile.
    """

    base_dir = summary.location.directory
    refs = []
    for cell in summary.cells:
        if not cell.is_scored:
            continue
        try:
            result_path = resolve_contained_path(base_dir, cell.artifact_dir) / "result.json"
        except ArtifactPathEscapeError:
            result_path = None
        refs.append(
            CellRef(
                schedule_id=cell.schedule_id,
                subject_role=cell.subject_role,
                subject_id=cell.subject_id,
                opponent_id=cell.opponent_id,
                seed=cell.seed,
                orientation=cell.orientation.value or ORIENTATION_CANDIDATE_FIRST,
                territory_last_fallback=cell.territory_subject,
                result_path=result_path,
            )
        )
    return tuple(refs)


__all__ = ["cell_refs_for_behavior"]
