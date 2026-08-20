"""Bridges evaluation-history's ``AdaptedCell`` to Phase 3 group-analysis
refs (``docs/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md``).

Deliberately a separate module from ``models.py``/``cli.py``, mirroring
``behavior_adapter.py``'s identical precedent exactly: it is the one place
``evaluation_history`` composes its own path-containment discipline
(``resolve_contained_path``) with
``battle_engine.evaluation_group_analysis``'s cell-detail read, so
containment checking is never silently skipped for a historical (on-disk,
potentially hand-edited) artifact the way it is legitimately skipped for
the live-run path (``agent_evaluation.py`` already trusts a directory it
just created).

Never called by ``discovery.py``/``adapt_v1``/``adapt_v2`` -- like Phase 5's
``behavior``/Beta2 Phase 1's ``capture``, group analysis performs real I/O
(one ``result.json`` read per scored group cell), so it must stay opt-in
and never run merely because an evaluation was discovered/listed.
"""

from __future__ import annotations

from battle_engine.evaluation_group_analysis import GroupCellRef

from .models import ArtifactPathEscapeError, EvaluationSummary, resolve_contained_path


def group_cell_refs(summary: EvaluationSummary) -> tuple[GroupCellRef, ...]:
    """Resolved, containment-checked ``GroupCellRef``\\ s for every scored
    group cell in ``summary``.

    Only schema-6+ ("group") cells carry a non-empty ``seat_agent_ids`` --
    a v1/v4/v5 (pairwise) cell is silently skipped rather than producing a
    malformed ref, so callers can pass any ``EvaluationSummary`` (mixed
    schema history) without pre-filtering by ``summary.group.value``
    themselves. A cell whose recorded ``artifact_dir`` escapes the
    evaluation's own directory gets ``result_path=None`` (refused, never
    followed) rather than raising -- mirrors
    ``behavior_adapter.cell_refs_for_behavior``'s identical refusal
    contract.
    """

    base_dir = summary.location.directory
    refs = []
    for cell in summary.cells:
        if not cell.is_scored:
            continue
        seat_agent_ids = cell.seat_agent_ids.value
        if not seat_agent_ids:
            continue
        try:
            result_path = resolve_contained_path(base_dir, cell.artifact_dir) / "result.json"
        except ArtifactPathEscapeError:
            result_path = None
        refs.append(
            GroupCellRef(
                schedule_id=cell.schedule_id,
                roster_agent_ids=tuple(cell.roster.value or ()),
                seat_agent_ids=tuple(seat_agent_ids),
                layout_id=cell.layout_id.value or "",
                seed=cell.seed,
                result_path=result_path,
            )
        )
    return tuple(refs)


__all__ = ["group_cell_refs"]
