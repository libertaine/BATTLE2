"""Qt-free adapters between the Designer and ``battle_engine.evaluation_history``/
``battle_engine.agent_revisions`` (v1.1 "Evaluation Insight" slice).

Deliberately thin: ``battle_engine.evaluation_history``'s ``EvaluationSummary``/
``AlignedComparison``/``ArtifactListing``/``DiscoveredEvaluation`` are already
presentation-neutral, Qt-free, fully typed domain objects -- this module does
not re-model them a second time. It only (a) supplies Designer-appropriate
defaults, (b) translates the engine layer's own exceptions into
``DesignerValidationError`` the same way ``designer_workflows.py`` already
does for match/tournament/evaluate reads, and (c) adds the one small
presentation type (``AgentRevisionPresentation``) that the engine layer has
no typed equivalent for, since ``agent_revisions.read_manifest`` returns a
raw ``dict`` by design (mirrors ``agent_revisions_cli.py``'s own ``_print_show``
field selection).

No agent code executes anywhere in this module -- every read here is a plain
filesystem/JSON read, exactly like ``TraceInspectorDialog``'s trace read, so
callers never need a ``QProcess`` for any of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from battle_engine.agent_evaluation import ORIENTATION_MODE_CANDIDATE_FIRST_ONLY, methodology_lines
from battle_engine.agent_revisions import (
    agent_revision_fingerprint,
    agent_revision_id,
    agent_revisions_root,
    read_manifest,
    verify_revision,
)
from battle_engine.evaluation_history import (
    AdaptedCell,
    AlignedComparison,
    ArtifactListing,
    ArtifactReadError,
    ComparisonRow,
    DiscoveredEvaluation,
    EvaluationSummary,
    adapt_any,
    align,
    default_roots,
    discover,
    verify_summary,
)

from app.services.designer_workflows import DesignerValidationError


def discover_evaluation_listing(*, roots: tuple[Path, ...] = ()) -> ArtifactListing:
    """Shallow-health discovery across the default (or explicit) evaluation roots.

    Never raises for a malformed sibling (Sec 13 of
    ``docs/specs/evaluation_history.md``) -- an unreadable artifact becomes a
    ``DiscoveredEvaluation`` with ``summary=None``, reported as a row, not an
    exception.
    """

    return discover(roots=roots)


def sorted_listing_entries(
    listing: ArtifactListing,
) -> tuple[DiscoveredEvaluation, ...]:
    """Most-recently-modified first -- the one ordering criterion populated
    for every artifact regardless of schema/version (``created_at`` is only
    ``RECORDED`` from v2 onward, but filesystem mtime is always known)."""

    return tuple(
        sorted(listing.entries, key=lambda entry: entry.location.file_modified_at, reverse=True)
    )


def load_evaluation_summary(
    path: Path, *, verify: bool = False, data_root: Path | None = None
) -> tuple[EvaluationSummary, str | None]:
    """Read one ``evaluation.json`` (v1 or current) into its typed summary.

    Mirrors ``evaluation_history.cli._cmd_show`` exactly: on ``verify=True``,
    runs deep verification and returns a ``verify_error`` describing the
    first failure (a failed cell, a failed revision check, or "no eligible
    cells"), never a bare ``True``/``False`` that would hide *which* check
    failed. ``verify_error is None`` after a ``verify=True`` call means
    verification actually succeeded, not merely that it was skipped.

    ``data_root`` scopes the agent-revision-store cross-check (Sec 7.2 of
    ``docs/specs/agent_revision.md``) -- it defaults to the live
    ``get_data_root()`` (matching ``verify_summary``'s own default) but the
    Designer always passes its own resolved ``battle_root`` explicitly, the
    same "make the dependency visible at the call site" practice
    ``docs/specs/agent_designer_workflow.md`` Sec 3 already establishes for
    every other Designer-to-engine call.
    """

    try:
        summary = adapt_any(Path(path))
    except ArtifactReadError as exc:
        raise DesignerValidationError(str(exc)) from exc

    if not verify:
        return summary, None

    summary, verification = verify_summary(summary, data_root=data_root)
    if verification.failed:
        first = verification.failed[0]
        return summary, f"{first.schedule_id}: {first.error}"
    if verification.revision_issues:
        return summary, verification.revision_issues[0]
    if verification.eligible_count == 0:
        return summary, "no eligible (completed/scored) cells to verify"
    return summary, None


@dataclass(frozen=True)
class EvaluationComparisonResult:
    left: EvaluationSummary
    right: EvaluationSummary
    comparison: AlignedComparison
    left_verify_error: str | None
    right_verify_error: str | None

    @property
    def fully_verified(self) -> bool:
        """True only when verification was requested on both sides *and*
        actually succeeded on both -- never merely "was requested"
        (mirrors ``evaluation_history.cli._cmd_compare``'s ``fully_verified``)."""

        return (
            self.comparison.deep_verified
            and self.left_verify_error is None
            and self.right_verify_error is None
        )


def compare_evaluations(
    left_path: Path, right_path: Path, *, verify: bool = False, data_root: Path | None = None
) -> EvaluationComparisonResult:
    """Load both sides and align them -- the exact same call sequence
    ``evaluation_history.cli._cmd_compare`` uses, so the Designer's
    comparison view can never silently diverge from what
    ``bytefray agents evaluations compare`` itself would report for the
    same pair of artifacts. ``data_root`` is forwarded to both sides' deep
    verification identically (see :func:`load_evaluation_summary`).
    """

    left, left_error = load_evaluation_summary(left_path, verify=verify, data_root=data_root)
    right, right_error = load_evaluation_summary(right_path, verify=verify, data_root=data_root)
    comparison = align(left, right, deep_verified=bool(verify))
    return EvaluationComparisonResult(
        left=left,
        right=right,
        comparison=comparison,
        left_verify_error=left_error,
        right_verify_error=right_error,
    )


def find_candidate_cell(
    summary: EvaluationSummary,
    row: ComparisonRow,
    *,
    role: str = "candidate",
    side: Literal["left", "right"] | None = None,
) -> AdaptedCell | None:
    """Recover the ``AdaptedCell`` a comparison row was aligned from.

    ``ComparisonRow`` is a flattened, cross-artifact summary row (Sec 14).
    Alignment retains an internal, non-serialized schedule-id reference for
    each side.  GUI callers pass ``side`` so lookup uses that exact reference
    within the corresponding summary.  Hand-built/legacy rows without those
    references may fall back to the comparison coordinate, but only when it
    identifies exactly one cell.  Returning the first of multiple matches
    would be unsafe: current both-orientation evaluations legitimately have
    candidate-first and opponent-first cells with the same opponent, seed,
    and occurrence index.

    This is read-only lookup over already-loaded data, with no re-parsing.
    """

    if side not in (None, "left", "right"):
        raise ValueError(f"Unknown comparison side: {side!r}")

    schedule_id = None
    if side == "left":
        schedule_id = row.left_schedule_id
    elif side == "right":
        schedule_id = row.right_schedule_id

    def _same_coordinate(cell: AdaptedCell) -> bool:
        return (
            cell.subject_role == role
            and cell.opponent_id == row.opponent_id
            and cell.seed == row.seed
            and row.condition_occurrence_index is not None
            and cell.condition_occurrence_index.value == row.condition_occurrence_index
        )

    if schedule_id is not None:
        matches = [
            cell
            for cell in summary.cells
            if cell.schedule_id == schedule_id and _same_coordinate(cell)
        ]
    else:
        if row.condition_occurrence_index is None:
            return None
        matches = [cell for cell in summary.cells if _same_coordinate(cell)]
    return matches[0] if len(matches) == 1 else None


def distinct_opponent_ids(summary: EvaluationSummary) -> tuple[str, ...]:
    """Opponent ids referenced by this evaluation, first-occurrence order,
    deduplicated -- used to populate the revision-browser's opponent picker."""

    return tuple(dict.fromkeys(cell.opponent_id for cell in summary.cells))


@dataclass(frozen=True)
class AgentRevisionPresentation:
    """Typed view over one ``agent_revisions/<id>/manifest.json``, plus a
    live verification result -- mirrors ``agent_revisions_cli.py``'s
    ``_print_show`` field selection exactly, so the Designer never invents
    a second description of what a revision manifest contains."""

    revision_id: str
    fingerprint_version: int | None
    archived_at: str | None
    source_agent_id: str | None
    complete: bool
    files: tuple[str, ...]
    omitted: tuple[dict, ...]
    verified: bool
    # Area D ("whether that revision still matches current source"): live
    # comparison against the *current* on-disk agent directory named by
    # ``current_agent_id`` (the evaluation's own candidate/baseline/opponent
    # id -- not the manifest's informational ``source_agent_id``, per
    # Sec 1.2/6 of docs/specs/agent_revision.md). One of "unknown" (no
    # ``current_agent_id`` was supplied), "agent_missing" (that id no
    # longer exists under this data root), "matches_current_source", or
    # "changed_since_evaluation". Never persisted -- recomputed live every
    # time, exactly like ``verified`` above.
    live_source_status: str = "unknown"


def load_agent_revision(
    revision_id: str, *, data_root: Path, current_agent_id: str | None = None
) -> AgentRevisionPresentation:
    """Read and live-verify one stored agent revision.

    Availability/integrity are always checked live against the current
    revision store (never a persisted claim -- ``docs/specs/agent_revision.md``
    Sec 6) -- this is the same check ``bytefray agents revisions show`` runs.
    When ``current_agent_id`` is given (the role's own agent id, e.g. the
    evaluation's ``candidate_id``), also live-compares this revision against
    that agent's *current* on-disk content, mirroring
    ``agent_revisions_cli._live_agent_revision_id``.
    """

    store_root = agent_revisions_root(data_root)
    manifest = read_manifest(store_root, revision_id)
    if manifest is None:
        raise DesignerValidationError(
            f"No readable revision found for {revision_id!r} under {store_root}."
        )
    files = manifest.get("files")
    omitted = manifest.get("omitted")
    if not isinstance(files, list) or not (omitted is None or isinstance(omitted, list)):
        raise DesignerValidationError(f"Revision manifest for {revision_id!r} is malformed.")

    live_source_status = "unknown"
    if current_agent_id is not None:
        agent_dir = data_root / "agents" / current_agent_id
        if not agent_dir.is_dir():
            live_source_status = "agent_missing"
        else:
            fingerprint = agent_revision_fingerprint(agent_dir)
            live_id = agent_revision_id(fingerprint) if fingerprint is not None else None
            live_source_status = (
                "matches_current_source" if live_id == revision_id else "changed_since_evaluation"
            )

    return AgentRevisionPresentation(
        revision_id=revision_id,
        fingerprint_version=manifest.get("fingerprint_version"),
        archived_at=manifest.get("archived_at"),
        source_agent_id=manifest.get("source_agent_id"),
        complete=bool(manifest.get("complete")),
        files=tuple(str(item) for item in files),
        omitted=tuple(dict(item) for item in (omitted or ()) if isinstance(item, dict)),
        verified=verify_revision(store_root, revision_id),
        live_source_status=live_source_status,
    )


def format_evaluation_summary_text(
    summary: EvaluationSummary, *, verified: bool | None = None, verify_error: str | None = None
) -> str:
    """Human-readable detail block for one evaluation -- field selection and
    wording deliberately mirror ``evaluation_history.cli._print_show``
    exactly, so the Designer's detail pane and ``bytefray agents evaluations
    show`` never drift into two descriptions of the same artifact. Returns a
    plain string (no printing, no Qt) so it is independently testable and so
    a Qt view only has to set it as one widget's text.
    """

    lines: list[str] = []
    lines.append(f"evaluation_id: {summary.evaluation_id}")
    lines.append(f"schema: {summary.schema.schema} v{summary.schema.schema_version}")
    lines.append(f"path: {summary.location.evaluation_json_path}")
    lines.append(f"candidate: {summary.candidate_id}  baseline: {summary.baseline_id or 'none'}")
    lines.append(f"opponents: {', '.join(summary.opponent_ids)}")
    lines.append(f"seeds: {', '.join(str(s) for s in summary.seeds)}  ticks: {summary.ticks}")
    lines.append(
        f"lifecycle: {summary.lifecycle_state.value} ({summary.lifecycle_state.confidence.value})  "
        f"created_at: {summary.created_at.value or 'unknown'}  "
        f"finished_at: {summary.finished_at.value or 'unknown'}"
    )
    lines.append(
        f"rules_compatibility_id: {summary.rules_compatibility_id.value or 'unknown'} "
        f"({summary.rules_compatibility_id.confidence.value})"
    )
    orientation_mode_value = summary.orientation_mode.value or ORIENTATION_MODE_CANDIDATE_FIRST_ONLY
    lines.extend(methodology_lines(orientation_mode_value))
    lines.append(
        f"  orientation_mode: {orientation_mode_value} ({summary.orientation_mode.confidence.value})  "
        f"arena_alignment_mode: {summary.arena_alignment_mode.value or 'unknown'} "
        f"({summary.arena_alignment_mode.confidence.value})"
    )
    codes = ", ".join(code.value for code in summary.health.codes) or "unknown"
    lines.append(f"health: {codes}")
    for detail in summary.health.detail:
        lines.append(f"  - {detail}")
    lines.append(f"matrix: {len(summary.cells)}/{summary.matrix_size} cells")

    status_counts: dict[str, int] = {}
    for cell in summary.cells:
        status_counts[cell.status] = status_counts.get(cell.status, 0) + 1
    lines.append("cell status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items())))

    for aggregate in summary.aggregates_recomputed:
        if aggregate.orientation_scope != "all":
            continue
        lines.append(f"[{aggregate.subject_role}] {aggregate.subject_id}  win_rate={aggregate.win_rate_display}")
        candidate_first = next(
            (
                a
                for a in summary.aggregates_recomputed
                if a.subject_role == aggregate.subject_role
                and a.subject_id == aggregate.subject_id
                and a.orientation_scope == "candidate_first"
            ),
            None,
        )
        opponent_first = next(
            (
                a
                for a in summary.aggregates_recomputed
                if a.subject_role == aggregate.subject_role
                and a.subject_id == aggregate.subject_id
                and a.orientation_scope == "opponent_first"
            ),
            None,
        )
        if opponent_first is not None and opponent_first.matches_played > 0:
            lines.append(
                f"    candidate_first: {candidate_first.win_rate_display if candidate_first else 'n/a'}   "
                f"opponent_first: {opponent_first.win_rate_display}"
            )

    if not summary.execution_contexts:
        lines.append("execution contexts: none recorded (legacy/v1 artifact)")
    else:
        used_ids = {
            cell.execution_context_id.value
            for cell in summary.cells
            if cell.execution_context_id.value is not None
        }
        lines.append(
            f"execution contexts: {len(summary.execution_contexts)} recorded, {len(used_ids)} used by cells"
        )
        for context in summary.execution_contexts:
            marker = "*" if context.get("context_id") in used_ids else " "
            lines.append(
                f"  {marker} {context.get('context_id')}: bytefray={context.get('bytefray_version')} "
                f"python={context.get('python_version')} agent_api={context.get('agent_api_version')} "
                f"rules={context.get('rules_compatibility_id')}"
            )
        if len(used_ids) > 1:
            lines.append(
                "  MIXED EXECUTION CONTEXTS: this evaluation's cells did not all run under the same runtime."
            )

    lines.extend(_format_agent_revisions_lines(summary))

    if verified is not None:
        lines.append(f"verified: {verified}" + (f"  ({verify_error})" if verify_error else ""))

    return "\n".join(lines)


def _format_agent_revisions_lines(summary: EvaluationSummary) -> list[str]:
    def _line(label: str, revision_id_cv, error_cv, status) -> str:
        if not revision_id_cv.value:
            return f"  {label}: unknown"
        text = f"  {label}: {revision_id_cv.value}"
        if error_cv.value:
            text += f"  ARCHIVE ERROR: {error_cv.value}"
        if status.value != "not_checked":
            text += f"  [{status.value}]"
        return text

    lines = ["agent revisions:"]
    lines.append(
        _line(
            "candidate",
            summary.candidate_agent_revision_id,
            summary.candidate_agent_revision_error,
            summary.candidate_revision_verification,
        )
    )
    if summary.baseline_id is not None:
        lines.append(
            _line(
                "baseline",
                summary.baseline_agent_revision_id,
                summary.baseline_agent_revision_error,
                summary.baseline_revision_verification,
            )
        )
    seen_opponents: dict[str, AdaptedCell] = {}
    for cell in summary.cells:
        if cell.opponent_id not in seen_opponents:
            seen_opponents[cell.opponent_id] = cell
    for opponent_id, cell in seen_opponents.items():
        lines.append(
            _line(
                f"opponent:{opponent_id}",
                cell.opponent_agent_revision_id,
                cell.opponent_agent_revision_error,
                cell.opponent_revision_verification,
            )
        )
    return lines


def format_comparison_text(result: EvaluationComparisonResult) -> str:
    """Human-readable comparison summary -- mirrors
    ``evaluation_history.cli._print_compare`` exactly (same evidence/
    comparability disclosure, same denominators), minus the per-row
    improved/regressed lines (the Designer renders those as a separate,
    selectable, verdict-highlighted list widget instead of flat text)."""

    left, right, comparison = result.left, result.right, result.comparison
    lines: list[str] = []
    lines.append(f"orientation: {comparison.orientation}")
    lines.append(f"left:  {left.evaluation_id}  candidate={left.candidate_id}")
    lines.append(f"right: {right.evaluation_id}  candidate={right.candidate_id}")

    if result.fully_verified:
        lines.append("evidence: deep-verified (Verify)")
    elif comparison.deep_verified:
        detail = ""
        if result.left_verify_error is not None:
            detail += f"  LEFT FAILED: {result.left_verify_error}"
        if result.right_verify_error is not None:
            detail += f"  RIGHT FAILED: {result.right_verify_error}"
        lines.append("evidence: NOT deep-verified -- verification failed" + detail)
    else:
        lines.append(
            "evidence: NOT deep-verified -- read and recomputed from each artifact's own "
            "recorded fields only; enable Verify to cross-check nested result/replay artifacts"
        )

    if comparison.candidate_changed:
        lines.append("candidate identity: DIFFERENT CANDIDATES (logical id changed)")
    elif comparison.candidate_diff:
        lines.append(f"candidate identity changed: {comparison.candidate_diff}")
    else:
        lines.append("candidate identity: unchanged (or unknown on one side)")

    baseline = comparison.baseline_context
    lines.append(f"baseline: {baseline.identity_status}")
    if baseline.control_anomaly:
        lines.append("  ANOMALY: identical baseline produced different outcomes under identical conditions")

    d = comparison.denominators
    lines.append(
        f"comparable: {d.directly_comparable}  improved={d.improved} regressed={d.regressed} "
        f"unchanged={d.unchanged} inconclusive={d.inconclusive}"
    )
    lines.append(
        f"unmatched: left={d.unmatched_left} right={d.unmatched_right}  "
        f"changed_condition={d.changed_condition}  "
        # Found during v1.1 interactive qualification: a comparison whose
        # cells all fall into duplicate (opponent, seed) groups that could
        # not be unambiguously paired (Sec 14 of
        # docs/specs/evaluation_history.md) otherwise renders as an
        # uninformative wall of zeros with no visible signal that "Show
        # Unmatched / Changed-Condition / Ambiguous Details" has anything to
        # show. v1.1 fixed this here; v1.3 closed the matching gap in the
        # CLI's own ``_print_compare`` human-readable output (its
        # ``--json`` mode always carried the full list) for CLI/GUI
        # consistency (docs/specs/evaluation_history.md Sec 16 of the v1.3
        # task).
        f"ambiguous_duplicate_groups={d.ambiguous_duplicate_groups}  corrupt_or_missing={d.corrupt_or_missing}"
    )
    if comparison.reproducibility_anomalies:
        lines.append("REPRODUCIBILITY ANOMALIES (deep-verified identical candidate, differing outcome):")
        for row in comparison.reproducibility_anomalies:
            lines.append(
                f"  opponent={row.opponent_id} seed={row.seed} left={row.left_outcome} right={row.right_outcome}"
            )
    return "\n".join(lines)


def format_comparison_gaps_text(comparison: AlignedComparison) -> str:
    """Detail for the three "could not be directly compared" buckets
    (Sec 14's denominators): unmatched-left/right and changed-condition
    pairs. Kept separate from :func:`format_comparison_text` so the
    Designer can show it behind an explicit "Show details" toggle rather
    than always dumping every gap inline -- the counts alone (already in
    the main summary) are enough for the common case."""

    lines: list[str] = []
    if comparison.unmatched_left:
        lines.append(f"unmatched (left only, {len(comparison.unmatched_left)}):")
        for cell in comparison.unmatched_left:
            lines.append(f"  - opponent={cell.opponent_id} seed={cell.seed} status={cell.status}")
    if comparison.unmatched_right:
        lines.append(f"unmatched (right only, {len(comparison.unmatched_right)}):")
        for cell in comparison.unmatched_right:
            lines.append(f"  - opponent={cell.opponent_id} seed={cell.seed} status={cell.status}")
    if comparison.changed_condition:
        lines.append(f"changed condition ({len(comparison.changed_condition)}):")
        for left_cell, right_cell in comparison.changed_condition:
            lines.append(
                f"  - opponent={left_cell.opponent_id} seed={left_cell.seed}  "
                "effective conditions, rules, methodology, or opponent revision differ "
                "(not a like-for-like comparison)"
            )
    if comparison.ambiguous_duplicate_groups:
        lines.append(
            f"ambiguous duplicate groups ({len(comparison.ambiguous_duplicate_groups)}): "
            "duplicate (opponent, seed) pairs could not be unambiguously paired"
        )
    if not lines:
        lines.append("No unmatched, changed-condition, or ambiguous cells.")
    return "\n".join(lines)


def format_agent_revision_text(revision: AgentRevisionPresentation) -> str:
    """Mirrors ``agent_revisions_cli.py``'s ``_print_show`` field selection."""

    lines = [
        f"revision_id: {revision.revision_id}",
        f"fingerprint_version: {revision.fingerprint_version}",
        f"archived_at: {revision.archived_at}",
        (
            "source_agent_id (informational breadcrumb only, not authoritative): "
            f"{revision.source_agent_id}"
        ),
        f"complete: {revision.complete}",
        f"included files: {len(revision.files)}",
    ]
    for path in revision.files[:20]:
        lines.append(f"  + {path}")
    if len(revision.files) > 20:
        lines.append(f"  ... and {len(revision.files) - 20} more")
    if revision.omitted:
        lines.append(f"omitted ({len(revision.omitted)}) -- NOT preserved, evidence only:")
        for item in revision.omitted:
            target = item.get("target")
            suffix = f" -> {target}" if target else ""
            lines.append(f"  - {item.get('relative_path')}: {item.get('reason')}{suffix}")
    else:
        lines.append("omitted: none")
    lines.append(f"local snapshot verified (recomputed live from stored bytes): {revision.verified}")
    live_source_labels = {
        "unknown": "not checked",
        "agent_missing": "this agent id no longer exists under the current agents/ catalog",
        "matches_current_source": "MATCHES the agent's current on-disk source",
        "changed_since_evaluation": "CHANGED since this evaluation was run (live source differs)",
    }
    lines.append(
        f"current source: {live_source_labels.get(revision.live_source_status, revision.live_source_status)}"
    )
    if revision.complete:
        lines.append(
            "reproducibility: revision-preserved candidate (complete=True; see docs/specs/agent_revision.md Sec 8)"
        )
    else:
        lines.append(
            "reproducibility: NOT revision-preserved -- this revision has omissions; "
            "restoring it reproduces less than the original tree (Sec 8)"
        )
    return "\n".join(lines)


__all__ = [
    "AgentRevisionPresentation",
    "EvaluationComparisonResult",
    "compare_evaluations",
    "default_roots",
    "discover_evaluation_listing",
    "distinct_opponent_ids",
    "find_candidate_cell",
    "format_agent_revision_text",
    "format_comparison_gaps_text",
    "format_comparison_text",
    "format_evaluation_summary_text",
    "load_agent_revision",
    "load_evaluation_summary",
    "sorted_listing_entries",
]
