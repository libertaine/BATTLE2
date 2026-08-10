"""``bytefray agents evaluations list|show|compare`` (Sec 15)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .comparison import align
from .discovery import AmbiguousSelectorError, adapt_any, discover, resolve_selector
from .models import ArtifactReadError


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
        from battle_engine.result_model import ReplayIntegrityError, verify_result_replay

        for cell in summary.cells:
            if cell.status != "completed" or cell.outcome not in ("win", "loss", "tie"):
                continue
            result_path = summary.location.directory / cell.artifact_dir / "result.json"
            try:
                verify_result_replay(result_path)
            except (ReplayIntegrityError, OSError, ValueError) as exc:
                verify_error = f"{cell.schedule_id}: {exc}"
                break
        verified = verify_error is None

    if args.json:
        data = summary.to_json()
        data["verified"] = verified
        data["verify_error"] = verify_error
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        _print_show(summary, verified=verified if args.verify else None, verify_error=verify_error)

    if args.verify and verify_error is not None:
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
    codes = ", ".join(code.value for code in summary.health.codes) or "unknown"
    print(f"health: {codes}")
    for detail in summary.health.detail:
        print(f"  - {detail}")
    print(f"matrix: {len(summary.cells)}/{summary.matrix_size} cells")
    status_counts: dict[str, int] = {}
    for cell in summary.cells:
        status_counts[cell.status] = status_counts.get(cell.status, 0) + 1
    print("cell status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items())))
    for aggregate in summary.aggregates_recomputed:
        print(f"[{aggregate.subject_role}] {aggregate.subject_id}  win_rate={aggregate.win_rate_display}")
    if verified is not None:
        print(f"verified: {verified}" + (f"  ({verify_error})" if verify_error else ""))


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

    result = align(left, right)

    if args.json:
        print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    else:
        _print_compare(left, right, result)

    if result.denominators.directly_comparable == 0 and not result.rows:
        return 1
    return 0


def _print_compare(left, right, result) -> None:
    print(f"orientation: {result.orientation}")
    print(f"left:  {left.evaluation_id}  candidate={left.candidate_id}")
    print(f"right: {right.evaluation_id}  candidate={right.candidate_id}")
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
        print("REPRODUCIBILITY ANOMALIES (identical verified candidate, differing outcome):")
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
