"""``bytefray.agent_trace`` v1 — a deterministic, optional development trace.

Separate from and independent of ``battle2.replay``/``battle2.result``
(see ``docs/specs/agent_lab.md`` §5/§14). A trace file records the Agent
API boundary data (:class:`~battle_engine.agent_api.Observation`,
:class:`~battle_engine.agent_api.AgentAction`,
:class:`~battle_engine.python_runtime.RuntimeDiagnostic`) exchanged at
each ``reset()``/``act()`` call, so an agent author can answer "what did
my agent see and do on tick N" without re-executing agent code or reading
raw replay JSONL by hand.

This module is Qt-free and executes no agent code -- it only builds and
parses trace records. Writing happens from
:mod:`battle_engine.python_runtime`/:mod:`battle_engine.agent_worker`;
reading happens from :mod:`battle_engine.agent_inspect` (CLI) and the
Designer's Trace Inspector dialog.

**Compatibility policy**, effective once this schema ships in a release
(intended to become a stable surface at v0.5, mirroring how
``battle2.replay``/``battle2.result`` are already versioned protocol
identifiers -- see ``AGENTS.md``'s "Compatibility requirements"):

- Readers ignore unknown JSON object keys on any record (this module only
  ever reads the fields it knows about via explicit ``payload.get``/
  :func:`_required` lookups) -- a future minor addition of a new,
  optional field is not a breaking change for existing readers.
- Readers reject any ``schema`` value other than :data:`TRACE_SCHEMA` and
  any ``schema_version`` other than :data:`TRACE_SCHEMA_VERSION` outright
  (:func:`_parse_header`) rather than guessing at forward/backward
  compatibility -- a version bump is a deliberate, visible break, not a
  silent reinterpretation.
- Record order is append order, always: a trace file is written strictly
  sequentially by one writer and read back the same way; nothing in this
  module reorders, sorts, or buffers records out of the order they were
  written (see :meth:`TraceDocument.decisions`/``resets``, which are
  filtered views over the same original ``records`` tuple, not resorted).
- A structurally malformed record (missing required field, wrong type, a
  ``record_type`` this reader has never heard of) is a hard
  :class:`TraceFormatError`, not a value silently skipped -- see
  :class:`TraceWriter`'s docstring for the parallel decision on malformed
  *trailing* lines specifically.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TextIO

TRACE_SCHEMA = "bytefray.agent_trace"
TRACE_SCHEMA_VERSION = 1


class TraceFormatError(ValueError):
    """A trace file is missing, unreadable, malformed, or unsupported."""


@dataclass(frozen=True)
class TraceObservation:
    """Field-for-field mirror of :class:`battle_engine.agent_api.Observation`."""

    tick: int
    agent_id: str
    pc: int
    register_a: int
    register_p: int
    zero_flag: bool
    last_read: int | None
    alive: bool


@dataclass(frozen=True)
class TraceAction:
    """Field-for-field mirror of :class:`battle_engine.agent_api.AgentAction`."""

    kind: str
    operand: int | None = None
    value: int | None = None


@dataclass(frozen=True)
class TraceDiagnostic:
    """Field-for-field mirror of :class:`battle_engine.python_runtime.RuntimeDiagnostic`."""

    code: str
    stage: str
    message: str
    agent_id: str | None = None
    slot: int | None = None
    exception_type: str | None = None
    tick: int | None = None
    action_slot: int | None = None


@dataclass(frozen=True)
class TraceHeader:
    """First record of every trace file."""

    match_seed: int
    agents: Mapping[str, str]
    supervised: bool
    agent_call_timeout: float | None = None
    schema: str = TRACE_SCHEMA
    schema_version: int = TRACE_SCHEMA_VERSION
    record_type: str = "header"


@dataclass(frozen=True)
class ResetRecord:
    """One entrant's ``reset()`` call."""

    agent_id: str
    wall_time_ms: float
    diagnostic: TraceDiagnostic | None = None
    record_type: str = "reset"


@dataclass(frozen=True)
class DecisionRecord:
    """One entrant's single ``act()`` call attempt.

    ``tick`` is exactly the tick value passed into the Observation for
    this call -- the same integer the canonical replay's
    ``TickSnapshot.tick`` uses for the tick this decision shapes. See
    ``docs/specs/agent_lab.md`` §5 for the unambiguous tick-meaning
    contract this supports.
    """

    tick: int
    agent_id: str
    action_slot: int
    wall_time_ms: float
    observation: TraceObservation
    action: TraceAction | None = None
    diagnostic: TraceDiagnostic | None = None
    record_type: str = "decision"


TraceRecord = TraceHeader | ResetRecord | DecisionRecord


class TraceWriter:
    """Append-only ``bytefray.agent_trace`` v1 writer.

    Each record is serialized once, written in two ``write()`` calls (the
    JSON payload, then a newline), then flushed. Because both writes only
    append to this process's own buffered text stream and nothing reaches
    the OS until :meth:`_write`'s single :meth:`flush` call, a process
    kill either lands strictly before that flush (in which case the file
    on disk ends exactly at the previous complete record, unchanged) or
    strictly after it returns (in which case the new record is fully
    present) -- there is no window in which half of one record's `write()`
    calls reach disk and the other half doesn't. What this does *not*
    guarantee is durability against the OS/filesystem itself tearing a
    single ``flush()``'s underlying write syscall for a pathologically
    large line (there is no ``fsync``, and POSIX does not promise regular
    -file write atomicity the way it does for small pipe writes) -- for
    the realistic decision/reset record sizes this module actually
    produces, that residual risk is theoretical, not something this
    module claims to have eliminated. This is deliberately *not* described
    as transactional durability anywhere in this module or its docs: it is
    "flush-per-record, single-writer, no torn in-buffer writes," and nothing
    stronger. :func:`read_trace` treats a malformed trailing line as a hard
    parse error (with an exact file:line diagnostic) rather than silently
    dropping it, on the view that for a development-debugging artifact, a
    loud "this file is corrupt at line N" is more useful than quietly
    losing data the author might have needed -- see
    ``docs/specs/agent_lab.md``'s trace-durability note and
    ``engine/tests/test_agent_trace.py``'s malformed-line coverage.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = path.open("w", encoding="utf-8")

    def write_header(self, header: TraceHeader) -> None:
        self._write(asdict(header))

    def write_reset(self, record: ResetRecord) -> None:
        self._write(asdict(record))

    def write_decision(self, record: DecisionRecord) -> None:
        self._write(asdict(record))

    def _write(self, payload: dict[str, Any]) -> None:
        self._fh.write(json.dumps(payload, sort_keys=True))
        self._fh.write("\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _required(payload: Mapping[str, Any], key: str, path: Path, line_no: int) -> Any:
    if key not in payload:
        raise TraceFormatError(f"{path}:{line_no}: missing required field {key!r}")
    return payload[key]


def _parse_observation(payload: Any, path: Path, line_no: int) -> TraceObservation:
    if not isinstance(payload, Mapping):
        raise TraceFormatError(f"{path}:{line_no}: 'observation' must be an object")
    return TraceObservation(
        tick=_required(payload, "tick", path, line_no),
        agent_id=_required(payload, "agent_id", path, line_no),
        pc=_required(payload, "pc", path, line_no),
        register_a=_required(payload, "register_a", path, line_no),
        register_p=_required(payload, "register_p", path, line_no),
        zero_flag=_required(payload, "zero_flag", path, line_no),
        last_read=payload.get("last_read"),
        alive=_required(payload, "alive", path, line_no),
    )


def _parse_action(payload: Any, path: Path, line_no: int) -> TraceAction | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise TraceFormatError(f"{path}:{line_no}: 'action' must be an object or null")
    return TraceAction(
        kind=_required(payload, "kind", path, line_no),
        operand=payload.get("operand"),
        value=payload.get("value"),
    )


def _parse_diagnostic(payload: Any, path: Path, line_no: int) -> TraceDiagnostic | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise TraceFormatError(f"{path}:{line_no}: 'diagnostic' must be an object or null")
    return TraceDiagnostic(
        code=_required(payload, "code", path, line_no),
        stage=_required(payload, "stage", path, line_no),
        message=_required(payload, "message", path, line_no),
        agent_id=payload.get("agent_id"),
        slot=payload.get("slot"),
        exception_type=payload.get("exception_type"),
        tick=payload.get("tick"),
        action_slot=payload.get("action_slot"),
    )


def _parse_header(payload: Mapping[str, Any], path: Path, line_no: int) -> TraceHeader:
    header = TraceHeader(
        match_seed=_required(payload, "match_seed", path, line_no),
        agents=dict(_required(payload, "agents", path, line_no)),
        supervised=_required(payload, "supervised", path, line_no),
        agent_call_timeout=payload.get("agent_call_timeout"),
        schema=payload.get("schema", TRACE_SCHEMA),
        schema_version=payload.get("schema_version", TRACE_SCHEMA_VERSION),
    )
    if header.schema != TRACE_SCHEMA:
        raise TraceFormatError(
            f"{path}: unsupported trace schema {header.schema!r} (expected {TRACE_SCHEMA!r})"
        )
    if header.schema_version != TRACE_SCHEMA_VERSION:
        raise TraceFormatError(
            f"{path}: unsupported trace schema version {header.schema_version!r} "
            f"(expected {TRACE_SCHEMA_VERSION!r})"
        )
    return header


def _parse_reset(payload: Mapping[str, Any], path: Path, line_no: int) -> ResetRecord:
    return ResetRecord(
        agent_id=_required(payload, "agent_id", path, line_no),
        wall_time_ms=_required(payload, "wall_time_ms", path, line_no),
        diagnostic=_parse_diagnostic(payload.get("diagnostic"), path, line_no),
    )


def _parse_decision(payload: Mapping[str, Any], path: Path, line_no: int) -> DecisionRecord:
    return DecisionRecord(
        tick=_required(payload, "tick", path, line_no),
        agent_id=_required(payload, "agent_id", path, line_no),
        action_slot=_required(payload, "action_slot", path, line_no),
        wall_time_ms=_required(payload, "wall_time_ms", path, line_no),
        observation=_parse_observation(
            _required(payload, "observation", path, line_no), path, line_no
        ),
        action=_parse_action(payload.get("action"), path, line_no),
        diagnostic=_parse_diagnostic(payload.get("diagnostic"), path, line_no),
    )


@dataclass(frozen=True)
class TraceDocument:
    """A fully parsed trace file: one header plus its ordered records."""

    path: Path
    header: TraceHeader
    records: tuple[ResetRecord | DecisionRecord, ...]

    @property
    def decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(r for r in self.records if isinstance(r, DecisionRecord))

    @property
    def resets(self) -> tuple[ResetRecord, ...]:
        return tuple(r for r in self.records if isinstance(r, ResetRecord))

    def tick_range(self) -> tuple[int, int] | None:
        ticks = [d.tick for d in self.decisions]
        return (min(ticks), max(ticks)) if ticks else None

    def for_tick(self, tick: int) -> tuple[DecisionRecord, ...]:
        return tuple(d for d in self.decisions if d.tick == tick)

    def for_agent(self, agent_id: str) -> tuple[DecisionRecord, ...]:
        return tuple(d for d in self.decisions if d.agent_id == agent_id)

    def around_tick(self, tick: int, window: int) -> tuple[DecisionRecord, ...]:
        low, high = tick - window, tick + window
        return tuple(d for d in self.decisions if low <= d.tick <= high)

    def failures(self) -> tuple[ResetRecord | DecisionRecord, ...]:
        return tuple(r for r in self.records if r.diagnostic is not None)


def read_trace(path: Path) -> TraceDocument:
    """Parse one ``bytefray.agent_trace`` v1 file. Executes no agent code."""

    if not path.is_file():
        raise TraceFormatError(f"Trace file not found: {path}")

    header: TraceHeader | None = None
    records: list[ResetRecord | DecisionRecord] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TraceFormatError(f"Could not read trace file {path}: {exc}") from exc

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TraceFormatError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise TraceFormatError(f"{path}:{line_no}: record must be a JSON object")
        record_type = payload.get("record_type")
        if record_type == "header":
            header = _parse_header(payload, path, line_no)
        elif record_type == "reset":
            records.append(_parse_reset(payload, path, line_no))
        elif record_type == "decision":
            records.append(_parse_decision(payload, path, line_no))
        else:
            raise TraceFormatError(f"{path}:{line_no}: unknown record_type {record_type!r}")

    if header is None:
        raise TraceFormatError(f"{path}: missing header record")
    return TraceDocument(path=path, header=header, records=tuple(records))


@dataclass(frozen=True)
class Divergence:
    """The first point at which two traces disagree."""

    tick: int
    agent_id: str
    reason: str
    record_a: DecisionRecord | None
    record_b: DecisionRecord | None


def first_divergence(a: TraceDocument, b: TraceDocument) -> Divergence | None:
    """Find the first ``(tick, agent_id, action_slot)`` decision where two traces disagree.

    Walks every key present in either trace, in increasing tick order,
    then in each trace's own first-appearance agent order. A key present
    in only one trace is itself reported as a divergence (a length
    mismatch is not silently ignored); otherwise two decisions "agree"
    when their ``action`` and ``diagnostic`` are equal. Returns ``None``
    only if every matched key agrees.
    """

    index_a = {(d.tick, d.agent_id, d.action_slot): d for d in a.decisions}
    index_b = {(d.tick, d.agent_id, d.action_slot): d for d in b.decisions}

    agent_order: list[str] = []
    for document in (a, b):
        for decision in document.decisions:
            if decision.agent_id not in agent_order:
                agent_order.append(decision.agent_id)

    all_keys = set(index_a) | set(index_b)
    ticks = sorted({key[0] for key in all_keys})
    for tick in ticks:
        for agent_id in agent_order:
            slots = sorted(
                {key[2] for key in all_keys if key[0] == tick and key[1] == agent_id}
            )
            for action_slot in slots:
                key = (tick, agent_id, action_slot)
                record_a = index_a.get(key)
                record_b = index_b.get(key)
                if record_a is None or record_b is None:
                    return Divergence(
                        tick, agent_id, "one trace is missing this decision", record_a, record_b
                    )
                if record_a.action != record_b.action or record_a.diagnostic != record_b.diagnostic:
                    return Divergence(tick, agent_id, "action/diagnostic differ", record_a, record_b)
    return None


__all__ = [
    "TRACE_SCHEMA",
    "TRACE_SCHEMA_VERSION",
    "DecisionRecord",
    "Divergence",
    "ResetRecord",
    "TraceAction",
    "TraceDiagnostic",
    "TraceDocument",
    "TraceFormatError",
    "TraceHeader",
    "TraceObservation",
    "TraceRecord",
    "TraceWriter",
    "first_divergence",
    "read_trace",
]
