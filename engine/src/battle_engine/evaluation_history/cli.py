"""``bytefray agents evaluations list|show|compare`` (Sec 15)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from battle_engine.agent_evaluation import ORIENTATION_MODE_CANDIDATE_FIRST_ONLY, methodology_lines

from .comparison import align
from .discovery import AmbiguousSelectorError, adapt_any, discover, resolve_selector
from .models import ArtifactReadError
from .verification import verify_summary


def _print_list_row(entry, verbose: bool = False) -> None:
    summary = entry.summary
    codes = ",".join(code.value for code in entry.health.codes) or "unknown"
    if summary is None:
        print(f"UNREADABLE  {entry.location.evaluation_json_path}  [{codes}]")
        return
    created = summary.created_at.value or f"(file mtime {entry.location.file_modified_at})"
    print(
        f"{summary.evaluation_id}  schema=v{summary.schema.schema_version}  "
        f"candidate={summary.candidate_id}  baseline={summary.baseline_id or 'none'}  "
        f"created={created}  lifecycle={summary.lifecycle_state.value}  health=[{codes}]  "
        f"cells={len(summary.cells)}/{summary.matrix_size}  path={entry.location.evaluation_json_path}"
    )


def _cmd_list(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.root or [])]
    artifacts = [Path(a) for a in (args.artifact or [])]
    listing = discover(roots=roots, artifacts=artifacts)
    if args.json:
        print(
            json.dumps(
                {
                    "entries": [entry.to_json() for entry in listing.entries],
                    "duplicate_identity_groups": [
                        {"evaluation_id": eid, "paths": [str(p) for p in paths]}
                        for eid, paths in listing.duplicate_identity_groups
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if not listing.entries:
            print("No evaluations found.")
        for entry in listing.entries:
            _print_list_row(entry)
        if listing.duplicate_identity_groups:
            print("duplicate evaluation_id locations:")
            for evaluation_id, paths in listing.duplicate_identity_groups:
                print(f"  {evaluation_id}: {', '.join(str(p) for p in paths)}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.root or [])]
    try:
        path = resolve_selector(args.selector, roots=roots)
    except AmbiguousSelectorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        summary = adapt_any(path)
    except ArtifactReadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    verified = False
    verify_error: str | None = None
    if args.verify:
        summary, verification = verify_summary(summary)
        verified = verification.all_eligible_verified
        if verification.failed:
            first = verification.failed[0]
            verify_error = f"{first.schedule_id}: {first.error}"
        elif verification.revision_issues:
            verify_error = verification.revision_issues[0]
        elif verification.eligible_count == 0:
            verify_error = "no eligible (completed/scored) cells to verify"

    if args.json:
        data = summary.to_json()
        data["verified"] = verified
        data["verify_error"] = verify_error
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        _print_show(summary, verified=verified if args.verify else None, verify_error=verify_error)

    if args.verify and not verified:
        return 1
    return 0


def _print_show(summary, *, verified: bool | None, verify_error: str | None) -> None:
    print(f"evaluation_id: {summary.evaluation_id}")
    print(f"schema: {summary.schema.schema} v{summary.schema.schema_version}")
    print(f"path: {summary.location.evaluation_json_path}")
    print(f"candidate: {summary.candidate_id}  baseline: {summary.baseline_id or 'none'}")
    print(f"opponents: {', '.join(summary.opponent_ids)}")
    print(f"seeds: {', '.join(str(s) for s in summary.seeds)}  ticks: {summary.ticks}")
    print(
        f"lifecycle: {summary.lifecycle_state.value} ({summary.lifecycle_state.confidence.value})  "
        f"created_at: {summary.created_at.value or 'unknown'}  "
        f"finished_at: {summary.finished_at.value or 'unknown'}"
    )
    print(
        f"rules_compatibility_id: {summary.rules_compatibility_id.value or 'unknown'} "
        f"({summary.rules_compatibility_id.confidence.value})"
    )
    # v0.9 Phase 6 (Phase 5 spec Sec O.2/AA.5): same shared methodology
    # lines the live `agents evaluate` CLI prints, alongside each field's
    # own recorded/recovered confidence so a reader can tell a fresh
    # schema-4 evaluation's disclosure from a pre-v0.9 artifact's certain
    # recovery.
    orientation_mode_value = summary.orientation_mode.value or ORIENTATION_MODE_CANDIDATE_FIRST_ONLY
    for line in methodology_lines(orientation_mode_value):
        print(line)
    print(
        f"  orientation_mode: {orientation_mode_value} ({summary.orientation_mode.confidence.value})  "
        f"arena_alignment_mode: {summary.arena_alignment_mode.value or 'unknown'} "
        f"({summary.arena_alignment_mode.confidence.value})"
    )
    codes = ", ".join(code.value for code in summary.health.codes) or "unknown"
    print(f"health: {codes}")
    for detail in summary.health.detail:
        print(f"  - {detail}")
    print(f"matrix: {len(summary.cells)}/{summary.matrix_size} cells")
    status_counts: dict[str, int] = {}
    for cell in summary.cells:
        status_counts[cell.status] = status_counts.get(cell.status, 0) + 1
    print("cell status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items())))
    # v0.9 Phase 6 (Sec O.2/K.2): pooled ("all") row per subject, plus a
    # per-orientation win-rate breakdown line when the recomputed cells
    # actually cover more than one orientation.
    for aggregate in summary.aggregates_recomputed:
        if aggregate.orientation_scope != "all":
            continue
        print(f"[{aggregate.subject_role}] {aggregate.subject_id}  win_rate={aggregate.win_rate_display}")
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
            print(
                f"    candidate_first: {candidate_first.win_rate_display if candidate_first else 'n/a'}   "
                f"opponent_first: {opponent_first.win_rate_display}"
            )
    _print_execution_contexts(summary)
    _print_agent_revisions(summary)
    if verified is not None:
        print(f"verified: {verified}" + (f"  ({verify_error})" if verify_error else ""))


def _print_agent_revisions(summary) -> None:
    """Sec 5.4/7.2: durable revision provenance next to each role, when
    present -- ``unknown`` (v1/v2 artifacts, or a v3 artifact that never
    recorded one for this role) is shown explicitly, never silently
    omitted. Verification status (``[invalid]``/``[not_available]``/
    ``[verified]``) is only shown once ``--verify`` has actually populated
    it; plain ``show`` never claims local-store evidence it didn't check.
    """

    def _line(label: str, revision_id_cv, error_cv, status) -> None:
        if not revision_id_cv.value:
            print(f"  {label}: unknown")
            return
        line = f"  {label}: {revision_id_cv.value}"
        if error_cv.value:
            line += f"  ARCHIVE ERROR: {error_cv.value}"
        if status.value != "not_checked":
            line += f"  [{status.value}]"
        print(line)

    print("agent revisions:")
    _line(
        "candidate",
        summary.candidate_agent_revision_id,
        summary.candidate_agent_revision_error,
        summary.candidate_revision_verification,
    )
    if summary.baseline_id is not None:
        _line(
            "baseline",
            summary.baseline_agent_revision_id,
            summary.baseline_agent_revision_error,
            summary.baseline_revision_verification,
        )
    seen_opponents = {}
    for cell in summary.cells:
        if cell.opponent_id not in seen_opponents:
            seen_opponents[cell.opponent_id] = cell
    for opponent_id, cell in seen_opponents.items():
        _line(
            f"opponent:{opponent_id}",
            cell.opponent_agent_revision_id,
            cell.opponent_agent_revision_error,
            cell.opponent_revision_verification,
        )


def _print_execution_contexts(summary) -> None:
    """H2: surface execution provenance -- which runtime(s) actually ran the
    matrix, and whether cells are split across more than one."""

    if not summary.execution_contexts:
        print("execution contexts: none recorded (legacy/v1 artifact)")
        return
    used_ids = {
        cell.execution_context_id.value
        for cell in summary.cells
        if cell.execution_context_id.value is not None
    }
    print(f"execution contexts: {len(summary.execution_contexts)} recorded, {len(used_ids)} used by cells")
    for context in summary.execution_contexts:
        marker = "*" if context.get("context_id") in used_ids else " "
        print(
            f"  {marker} {context.get('context_id')}: bytefray={context.get('bytefray_version')} "
            f"python={context.get('python_version')} agent_api={context.get('agent_api_version')} "
            f"rules={context.get('rules_compatibility_id')}"
        )
    if len(used_ids) > 1:
        print("  MIXED EXECUTION CONTEXTS: this evaluation's cells did not all run under the same runtime.")


def _verify_side(summary):
    """Deep-verify one side of a comparison; returns (summary, error-or-None).

    Shared by both sides of ``compare --verify`` -- the same "no vacuous
    verified=true for zero eligible cells" rule ``show --verify`` applies
    (B3/Sec 15).
    """

    summary, verification = verify_summary(summary)
    if verification.failed:
        first = verification.failed[0]
        return summary, f"{first.schedule_id}: {first.error}"
    if verification.revision_issues:
        return summary, verification.revision_issues[0]
    if verification.eligible_count == 0:
        return summary, "no eligible (completed/scored) cells to verify"
    return summary, None


def _cmd_compare(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.root or [])]
    try:
        left_path = resolve_selector(args.left, roots=roots)
        right_path = resolve_selector(args.right, roots=roots)
    except (AmbiguousSelectorError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        left = adapt_any(left_path)
        right = adapt_any(right_path)
    except ArtifactReadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    left_verify_error: str | None = None
    right_verify_error: str | None = None
    if args.verify:
        left, left_verify_error = _verify_side(left)
        right, right_verify_error = _verify_side(right)

    result = align(left, right, deep_verified=bool(args.verify))
    # B3: `align()`'s own `deep_verified` reflects "--verify was requested"
    # (which is also what drives its internal per-pair verified-evidence
    # gating, independent of whether some *other* cell elsewhere failed to
    # verify) -- but the claim surfaced to a caller/consumer here must be
    # narrower: true only when verification was requested *and* actually
    # succeeded on both sides. A side that failed (or had zero eligible
    # cells) must never be reported as deep-verified.
    fully_verified = bool(args.verify) and left_verify_error is None and right_verify_error is None

    if args.json:
        data = result.to_json()
        data["deep_verified"] = fully_verified
        data["left_verify_error"] = left_verify_error
        data["right_verify_error"] = right_verify_error
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        _print_compare(left, right, result, left_verify_error, right_verify_error, fully_verified)

    if args.verify and (left_verify_error is not None or right_verify_error is not None):
        return 1
    if result.denominators.directly_comparable == 0 and not result.rows:
        return 1
    return 0


def _print_compare(
    left, right, result, left_verify_error=None, right_verify_error=None, fully_verified=None
) -> None:
    print(f"orientation: {result.orientation}")
    print(f"left:  {left.evaluation_id}  candidate={left.candidate_id}")
    print(f"right: {right.evaluation_id}  candidate={right.candidate_id}")
    if fully_verified is None:
        fully_verified = result.deep_verified and left_verify_error is None and right_verify_error is None
    if fully_verified:
        print("evidence: deep-verified (--verify)")
    elif result.deep_verified:
        # B3: --verify was requested but failed on at least one side --
        # never claim "deep-verified" for this comparison's evidence.
        print(
            "evidence: NOT deep-verified -- verification failed"
            + ("" if left_verify_error is None else f"  LEFT FAILED: {left_verify_error}")
            + ("" if right_verify_error is None else f"  RIGHT FAILED: {right_verify_error}")
        )
    else:
        print(
            "evidence: NOT deep-verified -- read and recomputed from each artifact's own "
            "recorded fields only; pass --verify to cross-check nested result/replay artifacts"
        )
    if result.candidate_changed:
        print("candidate identity: DIFFERENT CANDIDATES (logical id changed)")
    elif result.candidate_diff:
        print(f"candidate identity changed: {result.candidate_diff}")
    else:
        print("candidate identity: unchanged (or unknown on one side)")
    baseline = result.baseline_context
    print(f"baseline: {baseline.identity_status}")
    if baseline.control_anomaly:
        print("  ANOMALY: identical baseline produced different outcomes under identical conditions")
    d = result.denominators
    print(
        f"comparable: {d.directly_comparable}  improved={d.improved} regressed={d.regressed} "
        f"unchanged={d.unchanged} inconclusive={d.inconclusive}"
    )
    print(
        f"unmatched: left={d.unmatched_left} right={d.unmatched_right}  "
        f"changed_condition={d.changed_condition}  corrupt_or_missing={d.corrupt_or_missing}"
    )
    if result.reproducibility_anomalies:
        print("REPRODUCIBILITY ANOMALIES (deep-verified identical candidate, differing outcome):")
        for row in result.reproducibility_anomalies:
            print(f"  opponent={row.opponent_id} seed={row.seed} left={row.left_outcome} right={row.right_outcome}")
    for row in result.rows:
        if row.verdict in ("improved", "regressed"):
            print(f"  {row.verdict}: opponent={row.opponent_id} seed={row.seed} left={row.left_outcome} right={row.right_outcome}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bytefray agents evaluations")
    sub = parser.add_subparsers(dest="verb", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--root", action="append", default=None)
    list_parser.add_argument("--artifact", action="append", default=None)
    list_parser.add_argument("--json", action="store_true")

    show_parser = sub.add_parser("show")
    show_parser.add_argument("selector")
    show_parser.add_argument("--root", action="append", default=None)
    show_parser.add_argument("--verify", action="store_true")
    show_parser.add_argument("--json", action="store_true")

    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("left")
    compare_parser.add_argument("right")
    compare_parser.add_argument("--root", action="append", default=None)
    compare_parser.add_argument("--verify", action="store_true")
    compare_parser.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verb == "list":
        return _cmd_list(args)
    if args.verb == "show":
        return _cmd_show(args)
    if args.verb == "compare":
        return _cmd_compare(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
