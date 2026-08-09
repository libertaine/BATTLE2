"""``bytefray agents inspect``/``bytefray agents diverge`` — trace inspection CLI.

Parses an already-written ``bytefray.agent_trace`` v1 file
(:mod:`battle_engine.agent_trace`) and answers the questions Agent Lab
exists to answer: what did an agent see and do on a given tick, why did a
call fail, and where did two runs first disagree. Executes **no agent
code** -- this module only reads JSONL already produced by a prior
``agents test``/``agents validate`` run, so unlike those two tools it
needs no timeout and no worker subprocess. See
``docs/specs/agent_lab.md`` §9/§10.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from battle_engine.agent_trace import (
    DecisionRecord,
    Divergence,
    ResetRecord,
    TraceDocument,
    TraceFormatError,
    first_divergence,
    read_trace,
)


class TraceInspectionError(RuntimeError):
    """A tool-level failure (missing/unreadable/malformed trace); exit 2."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_trace_path(value: str) -> Path:
    """Accept either a run directory (containing ``trace.jsonl``) or a direct file path."""

    path = Path(value).expanduser()
    if path.is_dir():
        candidate = path / "trace.jsonl"
        if not candidate.is_file():
            raise TraceInspectionError(
                "trace_file_missing", f"No trace.jsonl found under directory: {path}"
            )
        return candidate
    if path.is_file():
        return path
    raise TraceInspectionError("trace_file_missing", f"Trace path not found: {path}")


def load_trace(value: str) -> TraceDocument:
    path = resolve_trace_path(value)
    try:
        return read_trace(path)
    except TraceFormatError as exc:
        raise TraceInspectionError("trace_format_invalid", str(exc)) from exc


def _format_observation(record: DecisionRecord) -> list[str]:
    observation = record.observation
    return [
        f"  observation.pc: {observation.pc}",
        f"  observation.register_a: {observation.register_a}",
        f"  observation.register_p: {observation.register_p}",
        f"  observation.zero_flag: {observation.zero_flag}",
        f"  observation.last_read: {observation.last_read}",
        f"  observation.alive: {observation.alive}",
    ]


def _format_decision(record: DecisionRecord) -> str:
    lines = [
        f"tick: {record.tick}",
        f"agent: {record.agent_id}",
        f"action_slot: {record.action_slot}",
        f"wall_time_ms: {record.wall_time_ms:.3f}",
        *_format_observation(record),
    ]
    if record.action is not None:
        lines.append(
            f"  action: {record.action.kind} operand={record.action.operand} value={record.action.value}"
        )
    if record.diagnostic is not None:
        diagnostic = record.diagnostic
        lines.append(f"  diagnostic.code: {diagnostic.code}")
        lines.append(f"  diagnostic.stage: {diagnostic.stage}")
        lines.append(f"  diagnostic.message: {diagnostic.message}")
    return "\n".join(lines)


def _format_reset(record: ResetRecord) -> str:
    lines = [
        f"reset agent: {record.agent_id}",
        f"wall_time_ms: {record.wall_time_ms:.3f}",
    ]
    if record.diagnostic is not None:
        diagnostic = record.diagnostic
        lines.append(f"  diagnostic.code: {diagnostic.code}")
        lines.append(f"  diagnostic.stage: {diagnostic.stage}")
        lines.append(f"  diagnostic.message: {diagnostic.message}")
    return "\n".join(lines)


def _print_summary(document: TraceDocument) -> None:
    header = document.header
    print(f"trace: {document.path}")
    print(f"schema: {header.schema} v{header.schema_version}")
    print(f"match_seed: {header.match_seed}")
    print(f"supervised: {header.supervised}")
    if header.agent_call_timeout is not None:
        print(f"agent_call_timeout: {header.agent_call_timeout:g}")
    print(f"agents: {', '.join(f'{slot}={name}' for slot, name in sorted(header.agents.items()))}")
    tick_range = document.tick_range()
    if tick_range is None:
        print("ticks: none")
    else:
        print(f"ticks: {tick_range[0]}-{tick_range[1]}")
    print(f"decisions: {len(document.decisions)}")
    print(f"resets: {len(document.resets)}")
    failures = document.failures()
    print(f"failures: {len(failures)}")
    for record in failures:
        if isinstance(record, ResetRecord):
            assert record.diagnostic is not None
            print(f"  reset {record.agent_id}: {record.diagnostic.code}")
        else:
            assert record.diagnostic is not None
            print(f"  tick {record.tick} {record.agent_id}: {record.diagnostic.code}")


def _filtered_decisions(
    document: TraceDocument,
    *,
    tick: int | None,
    around: int | None,
    window: int,
    agent: str | None,
    failures_only: bool,
) -> list[DecisionRecord]:
    if tick is not None:
        records: list[DecisionRecord] = list(document.for_tick(tick))
    elif around is not None:
        records = list(document.around_tick(around, window))
    else:
        records = list(document.decisions)
    if agent is not None:
        records = [r for r in records if r.agent_id == agent]
    if failures_only:
        records = [r for r in records if r.diagnostic is not None]
    return records


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray agents inspect",
        description=(
            "Inspect a bytefray.agent_trace v1 development trace: show a summary, "
            "one tick's decisions, decisions around a tick, or only failures. "
            "Executes no agent code."
        ),
    )
    parser.add_argument("run", help="run directory (containing trace.jsonl) or a direct trace path")
    parser.add_argument("--tick", type=int, default=None, help="show decisions at exactly this tick")
    parser.add_argument(
        "--around", type=int, default=None, help="show decisions within --window ticks of this tick"
    )
    parser.add_argument("--window", type=int, default=5, help="tick window for --around (default: 5)")
    parser.add_argument("--agent", default=None, help="restrict to one agent id/slot")
    parser.add_argument(
        "--failures", action="store_true", help="show only decisions/resets carrying a diagnostic"
    )
    return parser


def inspect_main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document = load_trace(args.run)
    except TraceInspectionError as exc:
        print("status: error", file=sys.stderr)
        print(f"code: {exc.code}", file=sys.stderr)
        print(f"error: {exc.message}", file=sys.stderr)
        return 2

    if args.tick is None and args.around is None and not args.failures and args.agent is None:
        _print_summary(document)
        return 0

    if args.failures and args.tick is None and args.around is None:
        blocks = [_format_reset(r) for r in document.resets if r.diagnostic is not None]
        blocks += [
            _format_decision(r)
            for r in document.decisions
            if r.diagnostic is not None and (args.agent is None or r.agent_id == args.agent)
        ]
        if not blocks:
            print("no failures recorded")
        else:
            print("\n\n".join(blocks))
        return 0

    records = _filtered_decisions(
        document,
        tick=args.tick,
        around=args.around,
        window=args.window,
        agent=args.agent,
        failures_only=args.failures,
    )
    if not records:
        print("no matching decisions")
        return 0
    print("\n\n".join(_format_decision(r) for r in records))
    return 0


def _diverge_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray agents diverge",
        description=(
            "Compare two bytefray.agent_trace v1 files and report the first tick/agent "
            "decision at which they disagree. Executes no agent code."
        ),
    )
    parser.add_argument("run_a", help="first run directory or trace path")
    parser.add_argument("run_b", help="second run directory or trace path")
    return parser


def _print_divergence(divergence: Divergence) -> None:
    print(f"tick: {divergence.tick}")
    print(f"agent: {divergence.agent_id}")
    print(f"reason: {divergence.reason}")
    if divergence.record_a is not None:
        print("--- trace a ---")
        print(_format_decision(divergence.record_a))
    else:
        print("--- trace a: no decision at this key ---")
    if divergence.record_b is not None:
        print("--- trace b ---")
        print(_format_decision(divergence.record_b))
    else:
        print("--- trace b: no decision at this key ---")


def diverge_main(argv: list[str] | None = None) -> int:
    args = _diverge_parser().parse_args(argv)
    try:
        document_a = load_trace(args.run_a)
        document_b = load_trace(args.run_b)
    except TraceInspectionError as exc:
        print("status: error", file=sys.stderr)
        print(f"code: {exc.code}", file=sys.stderr)
        print(f"error: {exc.message}", file=sys.stderr)
        return 2

    divergence = first_divergence(document_a, document_b)
    if divergence is None:
        print("status: identical")
        print(f"trace_a: {document_a.path}")
        print(f"trace_b: {document_b.path}")
        print("No divergence found: every matched decision agrees.")
        return 0

    print("status: diverged")
    print(f"trace_a: {document_a.path}")
    print(f"trace_b: {document_b.path}")
    _print_divergence(divergence)
    return 0


__all__ = ["diverge_main", "inspect_main", "load_trace", "resolve_trace_path"]
