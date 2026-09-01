"""Deterministic spectator-event derivation from a validated v4 artifact pair.

Phase 3 research infrastructure, not a public spectator API. Where
:mod:`battle_engine.spectator_events` derives what it can from the canonical
replay alone, this module consumes the **pair** -- a canonical Schema 4
replay plus its API-v2 agent trace (``bytefray.agent_trace`` schema version
2) -- and derives only facts that at least one of those two artifacts states
outright.

Why the pair matters
--------------------
The replay is omniscient: it records where every process was and every byte
that changed, but nothing about what any entrant was *told*. The trace is
subjective: it records the exact ``ObservationV2`` the engine handed each
process and the exact applied outcome of each action, but nothing about the
world outside those callbacks. Perspective-aware semantics -- "who could
actually know this happened" -- need both, which is why binding verification
(:func:`verify_pair`) is a hard precondition here rather than a convenience.

What this module deliberately does not do
-----------------------------------------
It derives no dramatic interpretation (momentum, comebacks, pressure). Every
event kind in :class:`SpectatorEventKind` restates something the engine
either recorded or delivered, and every one carries an explicit
``visible_to`` audience derived from actual v4 mechanics rather than from
what would make a nicer broadcast. Several important events turn out to be
visible to *nobody* -- see :data:`_OMNISCIENT_ONLY` and
``docs/research/v4/V4_SPECTATOR_PHASE_3_RESEARCH.md`` -- and that is recorded
as a finding rather than papered over.

Determinism contract
--------------------
- Trace record order is execution order and is never re-sorted. Every
  intra-tick ordinal assigned here descends from a trace record's position in
  its file, because ``DecisionRecordV2`` carries no explicit action-slot
  ordinal of its own (see the Phase 3 research document).
- Every other ordering is an explicit ``sorted()`` on a total key made of
  strings and integers. No dict-insertion, set-iteration, hash, wall-clock,
  or filesystem ordering reaches the output.
- ``wall_time_ms`` and ``diagnostic`` message text -- the trace's two
  declared nondeterministic fields -- are never read into an event.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any

from battle_engine.agent_trace import (
    BindingRecord,
    DecisionRecordV2,
    TraceDocumentV2,
    TraceFormatError,
    read_trace_v2,
)
from battle_engine.replay import (
    AgentEvent,
    KillDeathEvent,
    MemoryDiff,
    RuntimeEvent,
    TickSnapshot,
)
from battle_engine.spectator_events import (
    LoadedReplay,
    SpectatorAnalysisError,
    load_schema4_replay,
)

DERIVATION_SCHEMA = "bytefray.spectator_derivation"
DERIVATION_SCHEMA_VERSION = 1


class SpectatorPairError(ValueError):
    """A replay/trace pair cannot support trustworthy spectator derivation."""


class PairBindingError(SpectatorPairError):
    """The trace's replay binding is absent, malformed, or does not match."""


class PairConsistencyError(SpectatorPairError):
    """Replay and trace agree on their binding but disagree on match state."""


# --------------------------------------------------------------------------
# Binding verification
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PairBinding:
    """A verified replay/trace pairing.

    Holding one of these is the analyzer's proof that the two artifacts
    describe the same execution of the same match: the trace's
    :class:`~battle_engine.agent_trace.BindingRecord` names a
    ``replay_sha256`` that the replay file's actual bytes hash to, and its
    ``match_id``/``entrant_identities`` agree with the replay header's.
    """

    replay_path: Path
    trace_path: Path
    replay_sha256: str
    match_id: str
    ruleset_id: str
    entrant_identities: tuple[str, ...]


def _read_trace_document(trace_path: Path) -> TraceDocumentV2:
    """Parse a V2 trace, mapping every parse failure onto a binding error.

    Kept separate from the digest comparison so that "this file is not a
    readable V2 trace" (malformed, truncated, or a V1 trace) is reported as a
    distinct condition from "this is a valid V2 trace for a different match"
    -- the two call for different operator responses.
    """

    try:
        return read_trace_v2(trace_path)
    except TraceFormatError as exc:
        raise PairBindingError(f"unusable API-v2 trace {trace_path}: {exc}") from exc


def _replay_digest(replay_path: Path) -> str:
    """Hash the replay exactly as ``NativeMatchService`` hashed it.

    Read in binary: the canonical replay is written through a text-mode
    stream, so its on-disk bytes carry the writing platform's line endings,
    and any re-encoding of the file (a text-mode copy, a Git checkout under
    this repository's ``* text=auto eol=lf`` attribute) changes the digest
    without changing a single logical record. Reading bytes is what makes
    that visible instead of silently tolerated.
    """

    try:
        return hashlib.sha256(replay_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PairBindingError(f"cannot read replay {replay_path}: {exc}") from exc


def verify_pair(replay_path: str | Path, trace_path: str | Path) -> PairBinding:
    """Verify that one trace is bound to one canonical replay.

    Uses the binding contract Phase 2 already established -- no second
    binding mechanism is introduced, and the canonical replay is neither
    modified nor re-identified for spectator purposes. Raises
    :class:`PairBindingError` when the trace is unreadable, carries no
    binding footer, or names a different replay/match; a caller is expected
    to treat any of those as "do not analyze this pair".
    """

    replay = Path(replay_path)
    trace = Path(trace_path)

    document = _read_trace_document(trace)
    binding: BindingRecord | None = document.binding
    if binding is None:
        raise PairBindingError(
            f"{trace}: trace has no binding record; an API-v2 trace is only "
            "analyzable once its match finalized and appended one"
        )

    actual_digest = _replay_digest(replay)
    if actual_digest != binding.replay_sha256:
        raise PairBindingError(
            f"binding mismatch: {trace} is bound to replay sha256 "
            f"{binding.replay_sha256} but {replay} hashes to {actual_digest}"
        )

    try:
        loaded = load_schema4_replay(replay)
    except SpectatorAnalysisError as exc:
        raise PairBindingError(f"unusable canonical replay {replay}: {exc}") from exc

    header_match_id = loaded.header.match_id
    if header_match_id is not None and header_match_id != binding.match_id:
        raise PairBindingError(
            f"binding mismatch: {trace} names match_id {binding.match_id!r} but "
            f"{replay} declares {header_match_id!r}"
        )
    replay_entrants = tuple(
        str(entrant["agent_id"]) for entrant in loaded.header.entrants if "agent_id" in entrant
    )
    if replay_entrants and replay_entrants != binding.entrant_identities:
        raise PairBindingError(
            f"binding mismatch: {trace} names entrants {binding.entrant_identities} but "
            f"{replay} declares {replay_entrants}"
        )

    return PairBinding(
        replay_path=replay,
        trace_path=trace,
        replay_sha256=actual_digest,
        match_id=binding.match_id,
        ruleset_id=binding.ruleset_id,
        entrant_identities=binding.entrant_identities,
    )


# --------------------------------------------------------------------------
# Event model
# --------------------------------------------------------------------------


class SpectatorEventKind(str, Enum):
    """The Phase 3 accepted event vocabulary.

    Every member is derivable from the artifact pair without heuristics.
    Candidate kinds the v4 engine turned out not to support
    (``PROCESS_CREATED``, ``PROCESS_DEATH``) and kinds whose definitions
    would be editorial rather than factual (``FIRST_BLOOD`` and the whole
    subjective set) are deliberately absent; see the Phase 3 research
    document's candidate matrix.
    """

    DETECTION_GAINED = "DETECTION_GAINED"
    DETECTION_LOST = "DETECTION_LOST"
    HOSTILE_READ = "HOSTILE_READ"
    FIRST_HOSTILE_READ = "FIRST_HOSTILE_READ"
    HOSTILE_WRITE = "HOSTILE_WRITE"
    FIRST_HOSTILE_WRITE = "FIRST_HOSTILE_WRITE"
    CORE_CELL_LOST = "CORE_CELL_LOST"
    PROCESS_DISRUPTED = "PROCESS_DISRUPTED"
    EFFECTIVE_MOVE = "EFFECTIVE_MOVE"
    AGENT_ELIMINATED = "AGENT_ELIMINATED"
    AGENT_FORFEITED = "AGENT_FORFEITED"
    MATCH_ENDED = "MATCH_ENDED"
    VICTORY = "VICTORY"


#: Event kinds no entrant is informed of by any v4 mechanic. The engine never
#: tells a writer whose cell it overwrote, never tells a victim that its cell
#: changed, that one of its processes was disrupted, or that an opponent
#: died. These facts are true, and omniscient-only; a perspective projection
#: must not hand them to an entrant.
_OMNISCIENT_ONLY = frozenset(
    {
        SpectatorEventKind.HOSTILE_WRITE,
        SpectatorEventKind.FIRST_HOSTILE_WRITE,
        SpectatorEventKind.CORE_CELL_LOST,
        SpectatorEventKind.PROCESS_DISRUPTED,
        SpectatorEventKind.AGENT_ELIMINATED,
        SpectatorEventKind.AGENT_FORFEITED,
        SpectatorEventKind.MATCH_ENDED,
        SpectatorEventKind.VICTORY,
    }
)


@dataclass(frozen=True)
class Provenance:
    """Why one event was derived, in terms an independent reviewer can check.

    Research-mode only: :func:`derive_events` attaches these when asked, and
    the JSONL/explain surfaces render them, but no event semantics depend on
    them. ``record_index`` indexes
    :attr:`~battle_engine.agent_trace.TraceDocumentV2.decisions` for
    trace-derived events, and is ``None`` for events derived at a tick
    boundary or from the replay alone.
    """

    rule: str
    source: str
    record_index: int | None
    before: str
    after: str


@dataclass(frozen=True)
class SpectatorEvent:
    """One deterministic, objectively-defined spectator fact.

    ``(tick, sequence)`` is the event's identity: ``sequence`` is its
    zero-based position among the events derived for that tick, assigned in
    the single deterministic construction order documented on
    :func:`derive_events`. No random or wall-clock identity is used.

    ``visible_to`` names the entrants the v4 engine actually informs of this
    fact. An **empty** ``visible_to`` means no entrant is told -- the fact is
    omniscient-only. It never means "unknown".
    """

    tick: int
    sequence: int
    kind: SpectatorEventKind
    actors: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    visible_to: tuple[str, ...] = ()
    process_id: str | None = None
    address: int | None = None
    addresses: tuple[int, ...] = ()
    from_address: int | None = None
    to_address: int | None = None
    value: int | None = None
    previous_owner: str | None = None
    read_value: int | None = None
    remaining_core_cells: int | None = None
    cause: str | None = None
    reason: str | None = None
    stage: str | None = None
    action_slot: int | None = None
    termination_reason: str | None = None
    provenance: Provenance | None = None


@dataclass(frozen=True)
class SpectatorDerivation:
    """The full derived stream for one verified pair, plus its provenance."""

    binding: PairBinding
    ruleset_id: str | None
    arena_size: int
    first_tick: int
    last_tick: int
    result_ticks: int
    winner: str | None
    termination_reason: str | None
    decision_count: int
    events: tuple[SpectatorEvent, ...]


# --------------------------------------------------------------------------
# Derivation
# --------------------------------------------------------------------------

# Sub-order within one trace decision. The observation the engine delivered
# precedes the action the agent returned, and an action's consequences are
# ordered as the engine applies them, so a reader of the output sees the same
# causal order the runtime executed.
_SUB_DETECTION_GAINED = 0
_SUB_HOSTILE_READ = 1
_SUB_FIRST_HOSTILE_READ = 2
_SUB_HOSTILE_WRITE = 3
_SUB_FIRST_HOSTILE_WRITE = 4
_SUB_CORE_CELL_LOST = 5
_SUB_PROCESS_DISRUPTED = 6


@dataclass
class _MatchState:
    """Mutable reconstruction state carried tick to tick.

    Every field here is reconstructed from the artifacts, never guessed. The
    reconstruction is checked against the replay at every tick boundary (see
    :func:`_check_tick_agreement`), so a silent drift between what this
    module believes and what actually happened becomes a hard error rather
    than a plausible-looking event stream.
    """

    owners: list[str | None]
    anchors: dict[tuple[str, str], int] = field(default_factory=dict)
    alive: set[str] = field(default_factory=set)
    detected: dict[str, frozenset[int]] = field(default_factory=dict)
    core_cells: dict[str, tuple[int, ...]] = field(default_factory=dict)
    hostile_reads_seen: set[tuple[str, str]] = field(default_factory=set)
    hostile_writes_seen: set[tuple[str, str]] = field(default_factory=set)


def _expand(diff: MemoryDiff, arena_size: int) -> list[tuple[int, str | None, int]]:
    return [
        ((diff.address + offset) % arena_size, diff.owner, value)
        for offset, value in enumerate(diff.values)
    ]


def _applied(decision: DecisionRecordV2, kind: str) -> bool:
    return (
        decision.action is not None
        and decision.action.kind == kind
        and decision.applied_result is not None
        and decision.applied_result.status == "APPLIED"
    )


def _effective_address(decision: DecisionRecordV2) -> int:
    """The address an applied action actually reached.

    Only ever called for decisions :func:`_applied` has accepted, so
    ``applied_result`` is present. A missing ``normalized_address`` on such a
    decision means the trace itself is incomplete, and is reported as a pair
    consistency failure rather than defaulted to zero.
    """

    result = decision.applied_result
    if result is None or result.normalized_address is None:
        raise PairConsistencyError(
            f"tick {decision.observation.current_tick}: applied "
            f"{decision.agent_id}/{decision.process_id} action records no effective address"
        )
    return result.normalized_address


def _seed_state(loaded: LoadedReplay, arena_size: int) -> _MatchState:
    """Build initial ownership, core membership, and anchors from tick 0.

    Tick 0 is where the v4 runtime's core seeding lands: every entrant's
    fixed core region is written through the same ``VM._wr8`` path as any
    other write, so the tick-0 memory diffs *are* the initial ownership map
    and the initial core membership. Nothing else in a v4 match changes
    ownership except an applied ``WRITE``, every one of which the trace
    records -- which is what makes forward reconstruction exact rather than
    approximate.
    """

    zero = loaded.ticks[0]
    owners: list[str | None] = [None] * arena_size
    core_cells: dict[str, list[int]] = {}
    for diff in zero.memory_diffs:
        for address, owner, _value in _expand(diff, arena_size):
            owners[address] = owner
            if owner is not None:
                core_cells.setdefault(owner, []).append(address)
    state = _MatchState(owners=owners)
    state.core_cells = {
        entrant: tuple(sorted(set(cells))) for entrant, cells in sorted(core_cells.items())
    }
    state.anchors = {
        (process.entrant_id, process.process_id): process.anchor for process in zero.processes
    }
    state.alive = {agent.agent_id for agent in zero.agents if agent.alive}
    return state


def _check_core_declaration(state: _MatchState, decision: DecisionRecordV2) -> None:
    """Cross-check the trace's own core description against the replay seed."""

    observation = decision.observation
    seeded = state.core_cells.get(decision.agent_id)
    if seeded is None:
        raise PairConsistencyError(
            f"{decision.agent_id} acts in the trace but owns no seeded core in the replay"
        )
    if len(seeded) != observation.own_core_size:
        raise PairConsistencyError(
            f"{decision.agent_id}: trace reports core size {observation.own_core_size} but the "
            f"replay seeds {len(seeded)} core cells"
        )
    if observation.own_core_base not in seeded:
        raise PairConsistencyError(
            f"{decision.agent_id}: trace reports core base {observation.own_core_base} which "
            "the replay does not seed to this entrant"
        )


def _check_tick_agreement(
    state: _MatchState,
    snapshot: TickSnapshot,
    disrupted: set[tuple[str, str]],
    writes: list[tuple[int, str | None, int]],
    arena_size: int,
) -> None:
    """Assert this module's reconstruction still equals canonical truth.

    Three independent checks, all of which held on every match in the Phase 3
    corpus: the applied-write sequence the trace reports for the tick equals
    the sequence the replay's memory diffs expand to; every process anchor
    reconstructed from applied ``MOVE`` records equals the replay's
    end-of-tick anchor; and the disruption set reconstructed by replaying the
    anchor-hit rule equals the replay's ``disrupted`` flags. A pair that
    passes binding verification but fails any of these is describing
    something this module does not understand, and analysis stops.
    """

    replay_writes = [entry for diff in snapshot.memory_diffs for entry in _expand(diff, arena_size)]
    if replay_writes != writes:
        raise PairConsistencyError(
            f"tick {snapshot.tick}: the applied-write sequence the trace records "
            f"({len(writes)} writes) does not match the replay's memory diffs "
            f"({len(replay_writes)} writes)"
        )
    for process in snapshot.processes:
        key = (process.entrant_id, process.process_id)
        reconstructed = state.anchors.get(key)
        if reconstructed != process.anchor:
            raise PairConsistencyError(
                f"tick {snapshot.tick}: {process.entrant_id}/{process.process_id} anchor "
                f"reconstructed from the trace is {reconstructed} but the replay records "
                f"{process.anchor}"
            )
    replay_disrupted = {
        (process.entrant_id, process.process_id)
        for process in snapshot.processes
        if process.disrupted
    }
    if replay_disrupted != disrupted:
        raise PairConsistencyError(
            f"tick {snapshot.tick}: disruption reconstructed from the trace "
            f"{sorted(disrupted)} does not match the replay's {sorted(replay_disrupted)}"
        )


def _detection_events(
    tick: int,
    entrant: str,
    decisions: Sequence[tuple[int, DecisionRecordV2]],
    state: _MatchState,
    with_provenance: bool,
) -> tuple[list[tuple[int, int, SpectatorEvent]], list[SpectatorEvent], frozenset[int]]:
    """Derive one entrant's detection transitions for one tick.

    Detection is an **entrant-wide** fact in v4: ``_visible_enemy_anchors``
    uses every currently-eligible friendly process as a sensor and returns
    occupied addresses only -- never the identity of who occupies them. So
    these events name addresses, not targets: claiming the observer knows
    *which* opponent it detected would invent knowledge the engine
    deliberately withholds.

    The observation is re-evaluated before every callback, so an entrant's
    visible set can oscillate several times inside one tick purely because
    its own processes moved. Comparing per decision would emit that
    oscillation as spectator events. This compares the tick's **union**
    against the previous sampled tick's union instead: an address the entrant
    was told about at any point during the tick counts as detected for that
    tick, which is both quieter and strictly more faithful to what the
    entrant was actually handed.

    ``DETECTION_GAINED`` is anchored to the exact decision whose observation
    first carried the address, so it orders before the hostile action that
    detection enabled. ``DETECTION_LOST`` cannot be anchored that way -- it
    is evidenced by absence across the whole tick -- so it is emitted at the
    tick boundary. The asymmetry is deliberate.

    An entrant's very first sample starts from an empty set, so first contact
    is a real ``DETECTION_GAINED`` rather than a silent initial condition.
    """

    previous = state.detected.get(entrant, frozenset())
    union: set[int] = set()
    first_seen: dict[int, int] = {}
    for index, decision in decisions:
        for address in decision.observation.visible_enemy_anchor_addresses:
            if address not in union:
                union.add(address)
                first_seen[address] = index

    by_index: dict[int, list[int]] = {}
    for address in sorted(union - previous):
        by_index.setdefault(first_seen[address], []).append(address)

    anchored: list[tuple[int, int, SpectatorEvent]] = []
    for index in sorted(by_index):
        anchored.append(
            (
                index,
                _SUB_DETECTION_GAINED,
                SpectatorEvent(
                    tick=tick,
                    sequence=-1,
                    kind=SpectatorEventKind.DETECTION_GAINED,
                    actors=(entrant,),
                    visible_to=(entrant,),
                    addresses=tuple(sorted(by_index[index])),
                    provenance=(
                        Provenance(
                            rule="detection_union_per_entrant_tick",
                            source="trace",
                            record_index=index,
                            before=f"visible={sorted(previous)}",
                            after=f"visible={sorted(union)}",
                        )
                        if with_provenance
                        else None
                    ),
                ),
            )
        )

    lost = tuple(sorted(previous - union))
    boundary: list[SpectatorEvent] = []
    if lost:
        boundary.append(
            SpectatorEvent(
                tick=tick,
                sequence=-1,
                kind=SpectatorEventKind.DETECTION_LOST,
                actors=(entrant,),
                visible_to=(entrant,),
                addresses=lost,
                provenance=(
                    Provenance(
                        rule="detection_union_per_entrant_tick",
                        source="trace",
                        record_index=None,
                        before=f"visible={sorted(previous)}",
                        after=f"visible={sorted(union)}",
                    )
                    if with_provenance
                    else None
                ),
            )
        )
    return anchored, boundary, frozenset(union)


def _hostile_read_events(
    index: int,
    decision: DecisionRecordV2,
    state: _MatchState,
    with_provenance: bool,
) -> list[tuple[int, int, SpectatorEvent]]:
    """Derive hostile-read events from one applied ``READ`` decision.

    A read is hostile when the engine's own applied result names an owner
    that is another entrant. Nothing is inferred: ``read_owner`` is a value
    the engine computed and handed back, and the reading entrant receives it
    on its next observation as ``previous_read_owner`` -- which is why the
    reader, and only the reader, is in ``visible_to``. A v4 read mutates
    nothing, so the entrant that owns the cell is never told it was inspected.
    """

    result = decision.applied_result
    if result is None or result.read_owner is None or result.read_owner == decision.agent_id:
        return []
    address = _effective_address(decision)
    target = result.read_owner
    pair = (decision.agent_id, target)
    provenance = (
        Provenance(
            rule="applied_read_with_foreign_owner",
            source="trace",
            record_index=index,
            before=f"owner[{address}]={target}",
            after=f"{decision.agent_id} read value {result.read_value}",
        )
        if with_provenance
        else None
    )
    events = [
        (
            index,
            _SUB_HOSTILE_READ,
            SpectatorEvent(
                tick=decision.observation.current_tick,
                sequence=-1,
                kind=SpectatorEventKind.HOSTILE_READ,
                actors=(decision.agent_id,),
                targets=(target,),
                visible_to=(decision.agent_id,),
                process_id=decision.process_id,
                address=address,
                read_value=result.read_value,
                provenance=provenance,
            ),
        )
    ]
    if pair not in state.hostile_reads_seen:
        state.hostile_reads_seen.add(pair)
        events.append(
            (
                index,
                _SUB_FIRST_HOSTILE_READ,
                SpectatorEvent(
                    tick=decision.observation.current_tick,
                    sequence=-1,
                    kind=SpectatorEventKind.FIRST_HOSTILE_READ,
                    actors=(decision.agent_id,),
                    targets=(target,),
                    visible_to=(decision.agent_id,),
                    process_id=decision.process_id,
                    address=address,
                    read_value=result.read_value,
                    provenance=provenance,
                ),
            )
        )
    return events


def _hostile_write_events(
    index: int,
    decision: DecisionRecordV2,
    address: int,
    previous_owner: str | None,
    state: _MatchState,
    with_provenance: bool,
) -> list[tuple[int, int, SpectatorEvent]]:
    """Derive hostile-write and core-loss events from one applied ``WRITE``.

    ``previous_owner`` is the reconstructed owner of the cell immediately
    before this write, and the write is hostile exactly when that owner was
    another entrant. Writing an unowned cell is territory claim, not
    aggression, and is deliberately not an event.

    ``visible_to`` is empty for all of these. The v4 engine tells the writer
    only that its action applied -- never whose cell it took -- and tells the
    victim nothing at all; a victim can discover the loss only by reading the
    cell itself, which would surface as that entrant's own ``HOSTILE_READ``.
    """

    if previous_owner is None or previous_owner == decision.agent_id:
        return []
    tick = decision.observation.current_tick
    action = decision.action
    pair = (decision.agent_id, previous_owner)
    provenance = (
        Provenance(
            rule="applied_write_over_foreign_ownership",
            source="trace",
            record_index=index,
            before=f"owner[{address}]={previous_owner}",
            after=f"owner[{address}]={decision.agent_id}",
        )
        if with_provenance
        else None
    )
    events = [
        (
            index,
            _SUB_HOSTILE_WRITE,
            SpectatorEvent(
                tick=tick,
                sequence=-1,
                kind=SpectatorEventKind.HOSTILE_WRITE,
                actors=(decision.agent_id,),
                targets=(previous_owner,),
                process_id=decision.process_id,
                address=address,
                value=None if action is None else action.value,
                previous_owner=previous_owner,
                provenance=provenance,
            ),
        )
    ]
    if pair not in state.hostile_writes_seen:
        state.hostile_writes_seen.add(pair)
        events.append(
            (
                index,
                _SUB_FIRST_HOSTILE_WRITE,
                SpectatorEvent(
                    tick=tick,
                    sequence=-1,
                    kind=SpectatorEventKind.FIRST_HOSTILE_WRITE,
                    actors=(decision.agent_id,),
                    targets=(previous_owner,),
                    process_id=decision.process_id,
                    address=address,
                    value=None if action is None else action.value,
                    previous_owner=previous_owner,
                    provenance=provenance,
                ),
            )
        )
    if address in state.core_cells.get(previous_owner, ()):
        remaining = sum(
            1
            for cell in state.core_cells[previous_owner]
            if state.owners[cell] == previous_owner and cell != address
        )
        events.append(
            (
                index,
                _SUB_CORE_CELL_LOST,
                SpectatorEvent(
                    tick=tick,
                    sequence=-1,
                    kind=SpectatorEventKind.CORE_CELL_LOST,
                    actors=(decision.agent_id,),
                    targets=(previous_owner,),
                    process_id=decision.process_id,
                    address=address,
                    previous_owner=previous_owner,
                    remaining_core_cells=remaining,
                    provenance=(
                        Provenance(
                            rule="applied_write_over_victim_core_cell",
                            source="trace",
                            record_index=index,
                            before=(
                                f"{previous_owner} core cells owned="
                                f"{remaining + 1}/{len(state.core_cells[previous_owner])}"
                            ),
                            after=(
                                f"{previous_owner} core cells owned="
                                f"{remaining}/{len(state.core_cells[previous_owner])}"
                            ),
                        )
                        if with_provenance
                        else None
                    ),
                ),
            )
        )
    return events


def _disruption_events(
    index: int,
    decision: DecisionRecordV2,
    address: int,
    state: _MatchState,
    already_disrupted: set[tuple[str, str]],
    with_provenance: bool,
) -> list[tuple[int, int, SpectatorEvent]]:
    """Derive process disruptions caused by one applied ``WRITE``.

    Replays the engine's shared-location rule exactly: every live enemy
    process whose anchor currently occupies the written cell is disrupted;
    friendly processes are immune even when co-located. Because the anchor
    timeline is reconstructed from the trace's own applied ``MOVE`` records
    rather than from the replay's end-of-tick snapshot, attribution is exact
    even when a victim moved onto (or off) the address earlier in the same
    tick -- a case where matching on the end-of-tick anchor alone would name
    the wrong attacker.

    Only the transition is an event. The engine re-arms the disruption timer
    on every subsequent hit within the tick, and its telemetry counts each as
    a separate hit, but the process is already out of action; emitting one
    event per repeated hit would report a single suppression as up to eight
    identical "moments" per tick. Repeat hits are deliberately silent.
    """

    tick = decision.observation.current_tick
    events: list[tuple[int, int, SpectatorEvent]] = []
    victims = sorted(
        key
        for key, anchor in state.anchors.items()
        if anchor == address
        and key[0] in state.alive
        and key[0] != decision.agent_id
        and key not in already_disrupted
    )
    for entrant_id, process_id in victims:
        already_disrupted.add((entrant_id, process_id))
        events.append(
            (
                index,
                _SUB_PROCESS_DISRUPTED,
                SpectatorEvent(
                    tick=tick,
                    sequence=-1,
                    kind=SpectatorEventKind.PROCESS_DISRUPTED,
                    actors=(decision.agent_id,),
                    targets=(entrant_id,),
                    process_id=process_id,
                    address=address,
                    provenance=(
                        Provenance(
                            rule="applied_write_on_enemy_process_anchor",
                            source="trace",
                            record_index=index,
                            before=f"{entrant_id}/{process_id} anchored at {address}",
                            after=f"{entrant_id}/{process_id} disrupted for tick {tick}",
                        )
                        if with_provenance
                        else None
                    ),
                ),
            )
        )
    return events


def _engine_events(
    snapshot: TickSnapshot, with_provenance: bool
) -> list[SpectatorEvent]:
    """Translate the replay's own tick events, in the replay's own order."""

    events: list[SpectatorEvent] = []
    for position, engine_event in enumerate(snapshot.events):
        provenance = (
            Provenance(
                rule="canonical_replay_tick_event",
                source="replay",
                record_index=None,
                before=f"tick {snapshot.tick} events[{position}]",
                after=type(engine_event).__name__,
            )
            if with_provenance
            else None
        )
        if isinstance(engine_event, KillDeathEvent):
            events.append(
                SpectatorEvent(
                    tick=snapshot.tick,
                    sequence=-1,
                    kind=SpectatorEventKind.AGENT_ELIMINATED,
                    actors=() if engine_event.killer is None else (engine_event.killer,),
                    targets=(engine_event.victim,),
                    cause=engine_event.event_type,
                    provenance=provenance,
                )
            )
        elif isinstance(engine_event, RuntimeEvent):
            events.append(
                SpectatorEvent(
                    tick=snapshot.tick,
                    sequence=-1,
                    kind=SpectatorEventKind.AGENT_FORFEITED,
                    targets=(engine_event.victim,),
                    cause=engine_event.event_type,
                    reason=engine_event.reason,
                    stage=engine_event.stage,
                    action_slot=engine_event.action_slot,
                    provenance=provenance,
                )
            )
        elif not isinstance(engine_event, AgentEvent):
            raise PairConsistencyError(
                f"tick {snapshot.tick}: unsupported canonical event "
                f"{type(engine_event).__name__}"
            )
    return events


def _move_events(
    tick: int,
    start_anchors: dict[tuple[str, str], int],
    state: _MatchState,
    with_provenance: bool,
) -> list[SpectatorEvent]:
    """Emit one net-movement event per process whose anchor changed this tick.

    Coalesced to the tick boundary on purpose. A process may take several
    ``MOVE`` actions inside one tick and end where it started; per-action
    movement is engine detail, while "this process is somewhere else now" is
    the spectator-relevant fact and the one the replay's own per-tick anchor
    snapshot agrees with.
    """

    events: list[SpectatorEvent] = []
    for key in sorted(state.anchors):
        before = start_anchors.get(key)
        after = state.anchors[key]
        if before is None or before == after:
            continue
        entrant_id, process_id = key
        events.append(
            SpectatorEvent(
                tick=tick,
                sequence=-1,
                kind=SpectatorEventKind.EFFECTIVE_MOVE,
                actors=(entrant_id,),
                visible_to=(entrant_id,),
                process_id=process_id,
                from_address=before,
                to_address=after,
                provenance=(
                    Provenance(
                        rule="net_anchor_change_per_process_tick",
                        source="trace",
                        record_index=None,
                        before=f"anchor={before}",
                        after=f"anchor={after}",
                    )
                    if with_provenance
                    else None
                ),
            )
        )
    return events


def _finalize(tick_events: list[SpectatorEvent]) -> list[SpectatorEvent]:
    """Stamp one tick's events with their zero-based intra-tick sequence."""

    return [replace(event, sequence=index) for index, event in enumerate(tick_events)]


def derive_events(
    binding: PairBinding, *, with_provenance: bool = False
) -> SpectatorDerivation:
    """Derive the ordered semantic event stream for one verified pair.

    Construction order, which is what ``sequence`` numbers, is fixed:

    1. Events anchored to a trace decision, sorted by ``(decision position in
       the trace file, sub-order)``. The sub-order runs observation-derived
       (``DETECTION_GAINED``) before action-derived, and orders an action's
       consequences the way the engine applies them.
    2. Tick-boundary events: ``EFFECTIVE_MOVE`` by ``(entrant, process)``,
       then ``DETECTION_LOST`` by entrant, then the replay's own tick events
       in the replay's own order.
    3. After the last tick, ``MATCH_ENDED`` and then ``VICTORY``.

    Nothing here iterates a set or relies on dict insertion order for output
    ordering; every step is either trace file order or an explicit sort on a
    total key.
    """

    loaded = load_schema4_replay(binding.replay_path)
    document = _read_trace_document(binding.trace_path)
    arena_size = loaded.header.config.arena_size
    state = _seed_state(loaded, arena_size)

    decisions_by_tick: dict[int, list[tuple[int, DecisionRecordV2]]] = {}
    for index, decision in enumerate(document.decisions):
        decisions_by_tick.setdefault(decision.observation.current_tick, []).append(
            (index, decision)
        )
    snapshot_ticks = {snapshot.tick for snapshot in loaded.ticks}
    unknown = sorted(set(decisions_by_tick) - snapshot_ticks)
    if unknown:
        raise PairConsistencyError(
            f"trace records decisions for tick(s) {unknown} that the replay does not contain"
        )

    checked_cores: set[str] = set()
    # Accumulated per tick rather than appended straight to one flat list:
    # the terminal MATCH_ENDED/VICTORY events share the final tick's number,
    # so they must continue that tick's `sequence` run instead of restarting
    # it and colliding with the events already derived there.
    per_tick: dict[int, list[SpectatorEvent]] = {}

    for snapshot in loaded.ticks:
        if snapshot.tick == 0:
            continue
        tick_decisions = decisions_by_tick.get(snapshot.tick, ())
        start_anchors = dict(state.anchors)
        anchored: list[tuple[int, int, SpectatorEvent]] = []
        boundary: list[SpectatorEvent] = []
        writes: list[tuple[int, str | None, int]] = []
        disrupted: set[tuple[str, str]] = set()

        acting = sorted({decision.agent_id for _, decision in tick_decisions})
        for entrant in acting:
            entrant_decisions = [
                item for item in tick_decisions if item[1].agent_id == entrant
            ]
            gained, lost, current = _detection_events(
                snapshot.tick, entrant, entrant_decisions, state, with_provenance
            )
            anchored.extend(gained)
            boundary.extend(lost)
            # Only ticks the entrant was actually called on update its
            # detection state. An entrant whose every process is disrupted
            # receives no callback at all that tick (the runtime filters
            # disrupted processes before `act()`), and treating that silence
            # as "sees nothing" would emit a DETECTION_LOST the entrant never
            # experienced.
            state.detected[entrant] = current

        for index, decision in tick_decisions:
            if decision.agent_id not in checked_cores:
                _check_core_declaration(state, decision)
                checked_cores.add(decision.agent_id)
            key = (decision.agent_id, decision.process_id)
            if _applied(decision, "read"):
                anchored.extend(_hostile_read_events(index, decision, state, with_provenance))
            elif _applied(decision, "write"):
                address = _effective_address(decision)
                previous_owner = state.owners[address]
                anchored.extend(
                    _hostile_write_events(
                        index, decision, address, previous_owner, state, with_provenance
                    )
                )
                anchored.extend(
                    _disruption_events(
                        index, decision, address, state, disrupted, with_provenance
                    )
                )
                state.owners[address] = decision.agent_id
                action = decision.action
                value = 0 if action is None or action.value is None else action.value & 0xFF
                writes.append((address, decision.agent_id, value))
            elif _applied(decision, "move"):
                state.anchors[key] = _effective_address(decision)

            # Invalid/exceptional callbacks forfeit immediately in the
            # runtime. A later entrant in the same tick therefore cannot
            # disrupt that forfeited entrant's retained replay anchor.
            if (
                decision.applied_result is not None
                and decision.applied_result.status in {"EXCEPTION", "REJECTED_INVALID"}
            ):
                state.alive.discard(decision.agent_id)

        _check_tick_agreement(state, snapshot, disrupted, writes, arena_size)
        # Core-capture elimination is resolved after the scheduler finishes.
        # Retain every anchor for replay agreement, but use only these living
        # entrants as disruption targets on the following tick.
        state.alive = {agent.agent_id for agent in snapshot.agents if agent.alive}

        tick_events = [event for _, _, event in sorted(anchored, key=lambda item: item[:2])]
        tick_events.extend(_move_events(snapshot.tick, start_anchors, state, with_provenance))
        tick_events.extend(
            sorted(boundary, key=lambda event: event.actors[0] if event.actors else "")
        )
        tick_events.extend(_engine_events(snapshot, with_provenance))
        per_tick.setdefault(snapshot.tick, []).extend(tick_events)

    result = loaded.result
    terminal: list[SpectatorEvent] = [
        SpectatorEvent(
            tick=result.ticks,
            sequence=-1,
            kind=SpectatorEventKind.MATCH_ENDED,
            termination_reason=result.termination_reason,
            provenance=(
                Provenance(
                    rule="canonical_replay_result_record",
                    source="replay",
                    record_index=None,
                    before=f"last tick {loaded.ticks[-1].tick}",
                    after=f"terminated: {result.termination_reason}",
                )
                if with_provenance
                else None
            ),
        )
    ]
    if result.winner is not None:
        terminal.append(
            SpectatorEvent(
                tick=result.ticks,
                sequence=-1,
                kind=SpectatorEventKind.VICTORY,
                actors=(result.winner,),
                cause=result.win_mode,
                termination_reason=result.termination_reason,
                provenance=(
                    Provenance(
                        rule="canonical_replay_result_record",
                        source="replay",
                        record_index=None,
                        before=f"terminated: {result.termination_reason}",
                        after=f"winner={result.winner}",
                    )
                    if with_provenance
                    else None
                ),
            )
        )
    per_tick.setdefault(result.ticks, []).extend(terminal)

    events: list[SpectatorEvent] = []
    for tick in sorted(per_tick):
        events.extend(_finalize(per_tick[tick]))

    return SpectatorDerivation(
        binding=binding,
        ruleset_id=loaded.header.ruleset_id,
        arena_size=arena_size,
        first_tick=loaded.ticks[0].tick,
        last_tick=loaded.ticks[-1].tick,
        result_ticks=result.ticks,
        winner=result.winner,
        termination_reason=result.termination_reason,
        decision_count=len(document.decisions),
        events=tuple(events),
    )


def analyze_pair(
    replay_path: str | Path, trace_path: str | Path, *, with_provenance: bool = False
) -> SpectatorDerivation:
    """Verify a replay/trace pair, then derive its semantic event stream."""

    return derive_events(verify_pair(replay_path, trace_path), with_provenance=with_provenance)


# --------------------------------------------------------------------------
# Serialization and CLI
# --------------------------------------------------------------------------

_EVENT_SCALAR_FIELDS = (
    "process_id",
    "address",
    "from_address",
    "to_address",
    "value",
    "previous_owner",
    "read_value",
    "remaining_core_cells",
    "cause",
    "reason",
    "stage",
    "action_slot",
    "termination_reason",
)


def event_to_dict(event: SpectatorEvent) -> dict[str, Any]:
    """Render one event as a flat JSON object.

    ``visible_to`` is always present, including when empty: an empty audience
    is the finding (nobody is told), not a missing field, and a consumer must
    be able to tell it apart from a field this writer happened to omit.
    """

    payload: dict[str, Any] = {
        "tick": event.tick,
        "sequence": event.sequence,
        "kind": event.kind.value,
        "visible_to": list(event.visible_to),
    }
    if event.actors:
        payload["actors"] = list(event.actors)
    if event.targets:
        payload["targets"] = list(event.targets)
    if event.addresses:
        payload["addresses"] = list(event.addresses)
    for name in _EVENT_SCALAR_FIELDS:
        value = getattr(event, name)
        if value is not None:
            payload[name] = value
    if event.provenance is not None:
        payload["provenance"] = {
            "rule": event.provenance.rule,
            "source": event.provenance.source,
            "record_index": event.provenance.record_index,
            "before": event.provenance.before,
            "after": event.provenance.after,
        }
    return payload


def derivation_records(derivation: SpectatorDerivation) -> tuple[dict[str, Any], ...]:
    """The full JSONL record sequence: one header, one line per event, one result."""

    header: dict[str, Any] = {
        "schema": DERIVATION_SCHEMA,
        "schema_version": DERIVATION_SCHEMA_VERSION,
        "record_type": "header",
        "source": {
            "match_id": derivation.binding.match_id,
            "replay_sha256": derivation.binding.replay_sha256,
            "ruleset_id": derivation.ruleset_id,
            "entrants": list(derivation.binding.entrant_identities),
            "arena_size": derivation.arena_size,
        },
    }
    records: list[dict[str, Any]] = [header]
    for event in derivation.events:
        records.append(
            {
                "schema": DERIVATION_SCHEMA,
                "schema_version": DERIVATION_SCHEMA_VERSION,
                "record_type": "event",
                **event_to_dict(event),
            }
        )
    records.append(
        {
            "schema": DERIVATION_SCHEMA,
            "schema_version": DERIVATION_SCHEMA_VERSION,
            "record_type": "result",
            "first_tick": derivation.first_tick,
            "last_tick": derivation.last_tick,
            "result_ticks": derivation.result_ticks,
            "winner": derivation.winner,
            "termination_reason": derivation.termination_reason,
            "decision_count": derivation.decision_count,
            "event_count": len(derivation.events),
        }
    )
    return tuple(records)


def serialize_derivation(derivation: SpectatorDerivation) -> str:
    return "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in derivation_records(derivation)
    )


def explain_derivation(derivation: SpectatorDerivation) -> str:
    """Render the stream as an auditable source-record -> event walkthrough."""

    lines: list[str] = [
        f"match:   {derivation.binding.match_id}",
        f"ruleset: {derivation.ruleset_id}",
        f"replay:  {derivation.binding.replay_path} (sha256 {derivation.binding.replay_sha256})",
        f"trace:   {derivation.binding.trace_path} ({derivation.decision_count} decisions)",
        "",
    ]
    for event in derivation.events:
        audience = ", ".join(event.visible_to) if event.visible_to else "omniscient only"
        lines.append(f"Tick:        {event.tick}  (sequence {event.sequence})")
        lines.append(f"Event:       {event.kind.value}")
        if event.actors:
            lines.append(f"Actors:      {', '.join(event.actors)}")
        if event.targets:
            lines.append(f"Targets:     {', '.join(event.targets)}")
        if event.process_id is not None:
            lines.append(f"Process:     {event.process_id}")
        if event.address is not None:
            lines.append(f"Address:     {event.address}")
        if event.addresses:
            lines.append(f"Addresses:   {list(event.addresses)}")
        if event.from_address is not None and event.to_address is not None:
            lines.append(f"Anchor:      {event.from_address} -> {event.to_address}")
        lines.append(f"Visible to:  {audience}")
        provenance = event.provenance
        if provenance is not None:
            lines.append("Derived from:")
            lines.append(f"  rule:      {provenance.rule}")
            source = provenance.source
            if provenance.record_index is not None:
                source = f"{source} record #{provenance.record_index}"
            lines.append(f"  source:    {source}")
            lines.append(f"  before:    {provenance.before}")
            lines.append(f"  after:     {provenance.after}")
        lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spectator_derive",
        description=(
            "Verify a canonical v4 replay against its API-v2 agent trace and derive the "
            "deterministic semantic spectator-event stream for the pair."
        ),
    )
    parser.add_argument("replay", help="canonical battle2.replay Schema 4 JSONL file")
    parser.add_argument("trace", help="bytefray.agent_trace schema-2 JSONL file")
    parser.add_argument(
        "--provenance",
        action="store_true",
        help="attach the derivation rule and source record to every event",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="print the human-readable derivation walkthrough instead of JSONL",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify the replay/trace binding and exit without deriving events",
    )
    arguments = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    try:
        binding = verify_pair(arguments.replay, arguments.trace)
        if arguments.verify_only:
            print(
                f"binding OK: match {binding.match_id} replay sha256 {binding.replay_sha256}"
            )
            return 0
        derivation = derive_events(
            binding, with_provenance=arguments.provenance or arguments.explain
        )
    except (SpectatorPairError, SpectatorAnalysisError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(
        explain_derivation(derivation)
        if arguments.explain
        else serialize_derivation(derivation)
    )
    return 0


__all__ = [
    "DERIVATION_SCHEMA",
    "DERIVATION_SCHEMA_VERSION",
    "PairBinding",
    "PairBindingError",
    "PairConsistencyError",
    "Provenance",
    "SpectatorDerivation",
    "SpectatorEvent",
    "SpectatorEventKind",
    "SpectatorPairError",
    "analyze_pair",
    "derivation_records",
    "derive_events",
    "event_to_dict",
    "explain_derivation",
    "main",
    "serialize_derivation",
    "verify_pair",
]


if __name__ == "__main__":
    raise SystemExit(main())
