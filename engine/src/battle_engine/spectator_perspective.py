"""Deterministic API-v2 entrant-perspective projection.

Canonical replay state is omniscient.  This module deliberately does not
project that state.  It folds only the ordered observations delivered to one
entrant after the replay/trace pair has passed Phase 3 binding and consistency
validation.  See ``docs/specs/v4_spectator_perspective.md``.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from battle_engine.agent_trace import (
    DecisionRecordV2,
    TraceFormatError,
    read_trace_v2,
)
from battle_engine.spectator_derivation import (
    SpectatorDerivation,
    SpectatorPairError,
    analyze_pair,
)

PERSPECTIVE_SCHEMA = "bytefray.spectator_perspective"
PERSPECTIVE_SCHEMA_VERSION = 1


class PerspectiveError(ValueError):
    """A validated pair cannot support a truthful perspective projection."""


class PerspectiveConsistencyError(PerspectiveError):
    """Trace observations contradict the API-v2 callback contract."""


class KnowledgeStatus(str, Enum):
    """Status of anonymous occupancy at one address."""

    UNKNOWN = "UNKNOWN"
    CURRENT = "CURRENT"
    STALE = "STALE"


class TickBoundary(str, Enum):
    """The callback boundary represented by a tick query."""

    START = "START"
    END = "END"
    CALLBACK = "CALLBACK"


@dataclass(frozen=True)
class CallbackPoint:
    """One callback's stable location in the API-v2 trace."""

    tick: int
    decision_index: int
    process_id: str


@dataclass(frozen=True)
class DeclaredProcess:
    """One process declaration made by the selected entrant."""

    process_id: str
    reach: int
    share: float


@dataclass(frozen=True)
class ContactKnowledge:
    """Memory of anonymous enemy occupancy at one address.

    This object intentionally has no entrant ID, process ID, multiplicity, or
    synthetic track ID.  Reappearance means only that the same address was
    observed again.
    """

    address: int
    status: KnowledgeStatus
    first_observed_at: CallbackPoint
    last_observed_at: CallbackPoint
    observation_count: int
    became_stale_at: CallbackPoint | None = None


@dataclass(frozen=True)
class ReadKnowledge:
    """Historical feedback for one prior READ, delivered on a later callback.

    ``owner`` is the sampled memory cell's last-writer owner.  It never
    identifies an anonymous spatial contact at the same address.
    """

    process_id: str
    requested_address: int
    normalized_address: int | None
    applied: bool
    value: int | None
    owner: str | None
    sampled_at: CallbackPoint
    delivered_at: CallbackPoint

    @property
    def is_cell_sample(self) -> bool:
        """Whether this feedback contains a successfully sampled cell."""

        return self.applied


@dataclass(frozen=True)
class OwnProcessKnowledge:
    """The latest self sample delivered for one selected-entrant process."""

    process_id: str
    reach: int
    share: float
    anchor: int | None
    last_observed_at: CallbackPoint | None


@dataclass(frozen=True)
class PerspectiveFrame:
    """One selected-entrant callback and the observation it delivered."""

    point: CallbackPoint
    entrant_callback_index: int
    last_callback_tick: int
    previous_action_tick: int
    previous_action_applied: bool
    own_core_base: int
    own_core_size: int
    self_anchor: int
    self_reach: int
    visible_contact_addresses: tuple[int, ...]
    gained_contact_addresses: tuple[int, ...]
    staled_contact_addresses: tuple[int, ...]
    delivered_read: ReadKnowledge | None = None


@dataclass(frozen=True)
class PerspectiveState:
    """Selected entrant knowledge folded through one requested boundary."""

    entrant_id: str
    tick: int
    boundary: TickBoundary
    through_decision_index: int | None
    last_visibility_sample_at: CallbackPoint | None
    sampled_this_tick: bool
    own_core_base: int | None
    own_core_size: int | None
    current_contacts: tuple[ContactKnowledge, ...]
    stale_contacts: tuple[ContactKnowledge, ...]
    read_history: tuple[ReadKnowledge, ...]
    own_processes: tuple[OwnProcessKnowledge, ...]
    arena_size: int

    def contact_status(self, address: int) -> KnowledgeStatus:
        """Return CURRENT, STALE, or UNKNOWN for one canonical address."""

        if isinstance(address, bool) or not isinstance(address, int):
            raise TypeError("contact address must be an integer")
        if not 0 <= address < self.arena_size:
            raise ValueError(f"contact address {address} outside arena [0, {self.arena_size})")
        if any(contact.address == address for contact in self.current_contacts):
            return KnowledgeStatus.CURRENT
        if any(contact.address == address for contact in self.stale_contacts):
            return KnowledgeStatus.STALE
        return KnowledgeStatus.UNKNOWN


@dataclass(frozen=True)
class PerspectiveProjection:
    """Immutable callback timeline for one entrant.

    Frames are compact observation deltas.  State queries fold them in their
    existing trace order; this keeps arbitrary seeking simple and avoids
    quadratic duplication of cumulative READ/contact history.
    """

    entrant_id: str
    replay_sha256: str
    match_id: str
    ruleset_id: str | None
    arena_size: int
    first_tick: int
    last_tick: int
    result_ticks: int
    decision_count: int
    declarations: tuple[DeclaredProcess, ...]
    frames: tuple[PerspectiveFrame, ...]
    _decision_ticks: tuple[int, ...]

    def state_at_tick(
        self, tick: int, *, boundary: TickBoundary = TickBoundary.END
    ) -> PerspectiveState:
        """Fold knowledge to tick START or END.

        END includes selected-entrant observations from ``tick``.  START does
        not.  A tick with no such callback carries the prior sample unchanged.
        """

        if boundary not in (TickBoundary.START, TickBoundary.END):
            raise ValueError("tick queries support START or END boundaries")
        if isinstance(tick, bool) or not isinstance(tick, int):
            raise TypeError("tick must be an integer")
        if tick < self.first_tick or tick > self.result_ticks:
            raise ValueError(
                f"tick {tick} outside projection range [{self.first_tick}, {self.result_ticks}]"
            )
        selected = tuple(
            frame
            for frame in self.frames
            if frame.point.tick < tick
            or (boundary is TickBoundary.END and frame.point.tick == tick)
        )
        sampled = boundary is TickBoundary.END and any(
            frame.point.tick == tick for frame in selected
        )
        return _fold_frames(self, selected, tick, boundary, sampled)

    def state_at_decision(self, decision_index: int) -> PerspectiveState:
        """Fold through one global trace decision index.

        ``-1`` denotes the state before the first decision.  Other entrants'
        decisions affect the query boundary but never directly alter this
        entrant's state.
        """

        if isinstance(decision_index, bool) or not isinstance(decision_index, int):
            raise TypeError("decision_index must be an integer")
        if decision_index < -1 or decision_index >= self.decision_count:
            raise ValueError(f"decision_index {decision_index} outside [-1, {self.decision_count})")
        selected = tuple(
            frame for frame in self.frames if frame.point.decision_index <= decision_index
        )
        tick = self.first_tick if decision_index == -1 else self._decision_ticks[decision_index]
        sampled = any(frame.point.tick == tick for frame in selected)
        return _fold_frames(self, selected, tick, TickBoundary.CALLBACK, sampled)

    def state_at_callback(self, entrant_callback_index: int) -> PerspectiveState:
        """Fold through one selected-entrant callback ordinal."""

        if isinstance(entrant_callback_index, bool) or not isinstance(entrant_callback_index, int):
            raise TypeError("entrant_callback_index must be an integer")
        if not 0 <= entrant_callback_index < len(self.frames):
            raise ValueError(
                f"entrant_callback_index {entrant_callback_index} outside [0, {len(self.frames)})"
            )
        return self.state_at_decision(self.frames[entrant_callback_index].point.decision_index)

    def cursor(self) -> PerspectiveCursor:
        """Return a retained incremental cursor for efficient sequential playback.

        Equivalent to repeated :meth:`state_at_tick` END-boundary calls, but
        sequential and same-tick queries amortize to O(1) instead of re-folding
        the full callback history on every call.  See
        :class:`PerspectiveCursor`.
        """

        return PerspectiveCursor(self)


@dataclass
class _ContactAccumulator:
    first: CallbackPoint
    last: CallbackPoint
    count: int
    stale_at: CallbackPoint | None = None


class PerspectiveCursor:
    """Retained incremental fold cursor over one :class:`PerspectiveProjection`.

    Sequential 60fps playback repeatedly asks for state at consecutive or
    unchanged ticks.  Re-folding the full callback history from scratch on
    every displayed frame would introduce rendering stutter on longer
    matches.  This cursor keeps running accumulators and only folds the
    frames newly covered by a query, advancing monotonically for consecutive
    ticks.  Backward steps and arbitrary seeks reset the accumulators and
    replay forward from the start of the callback history to the target
    tick.  Repeated calls at the same tick (while paused, or rendering
    multiple display frames per tick) return the cached
    :class:`PerspectiveState` in O(1).

    Results are always equivalent to calling
    :meth:`PerspectiveProjection.state_at_tick` directly; this cursor is a
    performance optimization only and folds the same frames in the same
    trace order.
    """

    def __init__(self, projection: PerspectiveProjection) -> None:
        self._projection = projection
        self._reset_accumulators()

    def _reset_accumulators(self) -> None:
        self._frame_index = 0
        self._last_point: CallbackPoint | None = None
        self._contacts: dict[int, _ContactAccumulator] = {}
        self._current: set[int] = set()
        self._reads: list[ReadKnowledge] = []
        self._own: dict[str, OwnProcessKnowledge] = {
            declaration.process_id: OwnProcessKnowledge(
                process_id=declaration.process_id,
                reach=declaration.reach,
                share=declaration.share,
                anchor=None,
                last_observed_at=None,
            )
            for declaration in self._projection.declarations
        }
        self._core_base: int | None = None
        self._core_size: int | None = None
        self._cached_query: tuple[int, TickBoundary] | None = None
        self._cached_state: PerspectiveState | None = None

    def _fold_one(self, frame: PerspectiveFrame) -> None:
        visible = set(frame.visible_contact_addresses)
        for address in self._current - visible:
            self._contacts[address].stale_at = frame.point
        for address in visible:
            known = self._contacts.get(address)
            if known is None:
                self._contacts[address] = _ContactAccumulator(
                    first=frame.point,
                    last=frame.point,
                    count=1,
                )
            else:
                known.last = frame.point
                known.count += 1
                known.stale_at = None
        self._current = visible

        declared = self._own[frame.point.process_id]
        self._own[frame.point.process_id] = OwnProcessKnowledge(
            process_id=frame.point.process_id,
            reach=frame.self_reach,
            share=declared.share,
            anchor=frame.self_anchor,
            last_observed_at=frame.point,
        )
        self._core_base = frame.own_core_base
        self._core_size = frame.own_core_size
        if frame.delivered_read is not None:
            self._reads.append(frame.delivered_read)
        self._last_point = frame.point

    def _advance_to(self, target_index: int) -> None:
        if target_index < self._frame_index:
            self._reset_accumulators()
        frames = self._projection.frames
        while self._frame_index < target_index:
            self._fold_one(frames[self._frame_index])
            self._frame_index += 1

    def state_at_tick(
        self, tick: int, *, boundary: TickBoundary = TickBoundary.END
    ) -> PerspectiveState:
        """Incremental equivalent of ``PerspectiveProjection.state_at_tick``."""

        if boundary not in (TickBoundary.START, TickBoundary.END):
            raise ValueError("tick queries support START or END boundaries")
        if isinstance(tick, bool) or not isinstance(tick, int):
            raise TypeError("tick must be an integer")
        if tick < self._projection.first_tick or tick > self._projection.result_ticks:
            raise ValueError(
                f"tick {tick} outside projection range "
                f"[{self._projection.first_tick}, {self._projection.result_ticks}]"
            )

        query = (tick, boundary)
        if query == self._cached_query and self._cached_state is not None:
            return self._cached_state

        frames = self._projection.frames
        if boundary is TickBoundary.END:
            target_index = bisect.bisect_right(frames, tick, key=lambda frame: frame.point.tick)
        else:
            target_index = bisect.bisect_left(frames, tick, key=lambda frame: frame.point.tick)
        self._advance_to(target_index)

        sampled_this_tick = (
            boundary is TickBoundary.END
            and self._last_point is not None
            and self._last_point.tick == tick
        )
        current_contacts = tuple(
            ContactKnowledge(
                address=address,
                status=KnowledgeStatus.CURRENT,
                first_observed_at=self._contacts[address].first,
                last_observed_at=self._contacts[address].last,
                observation_count=self._contacts[address].count,
            )
            for address in sorted(self._current)
        )
        stale_contacts = tuple(
            ContactKnowledge(
                address=address,
                status=KnowledgeStatus.STALE,
                first_observed_at=known.first,
                last_observed_at=known.last,
                observation_count=known.count,
                became_stale_at=known.stale_at,
            )
            for address, known in sorted(self._contacts.items())
            if address not in self._current
        )
        state = PerspectiveState(
            entrant_id=self._projection.entrant_id,
            tick=tick,
            boundary=boundary,
            through_decision_index=(
                None if self._last_point is None else self._last_point.decision_index
            ),
            last_visibility_sample_at=self._last_point,
            sampled_this_tick=sampled_this_tick,
            own_core_base=self._core_base,
            own_core_size=self._core_size,
            current_contacts=current_contacts,
            stale_contacts=stale_contacts,
            read_history=tuple(self._reads),
            own_processes=tuple(self._own[key] for key in sorted(self._own)),
            arena_size=self._projection.arena_size,
        )
        self._cached_query = query
        self._cached_state = state
        return state


def _fail(index: int, message: str) -> PerspectiveConsistencyError:
    return PerspectiveConsistencyError(f"trace decision {index}: {message}")


def _validate_addresses(values: tuple[int, ...], arena_size: int, decision_index: int) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise _fail(decision_index, "visible contact addresses must be integers")
    if any(value < 0 or value >= arena_size for value in values):
        raise _fail(
            decision_index,
            f"visible contact address outside arena [0, {arena_size})",
        )
    if values != tuple(sorted(set(values))):
        raise _fail(
            decision_index,
            "visible contact addresses must be sorted and de-duplicated",
        )


def _validate_initial_feedback(decision_index: int, decision: DecisionRecordV2) -> None:
    observation = decision.observation
    if observation.last_callback_tick != 0 or observation.previous_action_tick != 0:
        raise _fail(decision_index, "first process callback must reference tick 0")
    if observation.previous_action_applied:
        raise _fail(decision_index, "first process callback cannot report an applied action")
    if observation.previous_read_value is not None or observation.previous_read_owner is not None:
        raise _fail(decision_index, "first process callback cannot carry READ feedback")


def _read_delivered_on(
    previous_index: int,
    previous: DecisionRecordV2,
    decision_index: int,
    decision: DecisionRecordV2,
    arena_size: int,
) -> ReadKnowledge | None:
    """Validate previous-action feedback and return delivered READ knowledge."""

    observation = decision.observation
    previous_observation = previous.observation
    if observation.last_callback_tick != previous_observation.current_tick:
        raise _fail(
            decision_index,
            "last_callback_tick does not name this process's preceding callback",
        )
    if observation.previous_action_tick != previous_observation.current_tick:
        raise _fail(
            decision_index,
            "previous_action_tick does not name this process's preceding action",
        )

    result = previous.applied_result
    if result is None:
        raise _fail(previous_index, "a callback followed by another callback has no result")
    applied = result.status == "APPLIED"
    if observation.previous_action_applied is not applied:
        raise _fail(
            decision_index,
            "previous_action_applied contradicts the preceding trace result",
        )

    action = previous.action
    if action is None:
        raise _fail(previous_index, "a callback followed by another callback has no action")
    if action.kind != "read":
        if (
            observation.previous_read_value is not None
            or observation.previous_read_owner is not None
        ):
            raise _fail(
                decision_index,
                "non-READ preceding action cannot deliver READ feedback",
            )
        return None

    operand = action.operand
    if isinstance(operand, bool) or not isinstance(operand, int):
        raise _fail(previous_index, "READ action has no integer requested address")

    if applied:
        normalized = result.normalized_address
        if isinstance(normalized, bool) or not isinstance(normalized, int):
            raise _fail(previous_index, "applied READ has no normalized address")
        if not 0 <= normalized < arena_size:
            raise _fail(previous_index, "applied READ normalized address is outside arena")
        if result.read_value is None:
            raise _fail(previous_index, "applied READ has no sampled value")
        if observation.previous_read_value != result.read_value:
            raise _fail(
                decision_index,
                "delivered READ value contradicts the preceding sampled result",
            )
        if observation.previous_read_owner != result.read_owner:
            raise _fail(
                decision_index,
                "delivered READ owner contradicts the preceding sampled result",
            )
    else:
        normalized = None
        if (
            observation.previous_read_value is not None
            or observation.previous_read_owner is not None
        ):
            raise _fail(decision_index, "non-applied READ cannot deliver a cell sample")

    return ReadKnowledge(
        process_id=decision.process_id,
        requested_address=operand,
        normalized_address=normalized,
        applied=applied,
        value=observation.previous_read_value,
        owner=observation.previous_read_owner,
        sampled_at=CallbackPoint(
            tick=previous_observation.current_tick,
            decision_index=previous_index,
            process_id=previous.process_id,
        ),
        delivered_at=CallbackPoint(
            tick=observation.current_tick,
            decision_index=decision_index,
            process_id=decision.process_id,
        ),
    )


def _fold_frames(
    projection: PerspectiveProjection,
    frames: tuple[PerspectiveFrame, ...],
    tick: int,
    boundary: TickBoundary,
    sampled_this_tick: bool,
) -> PerspectiveState:
    contacts: dict[int, _ContactAccumulator] = {}
    current: set[int] = set()
    reads: list[ReadKnowledge] = []
    own: dict[str, OwnProcessKnowledge] = {
        declaration.process_id: OwnProcessKnowledge(
            process_id=declaration.process_id,
            reach=declaration.reach,
            share=declaration.share,
            anchor=None,
            last_observed_at=None,
        )
        for declaration in projection.declarations
    }
    core_base: int | None = None
    core_size: int | None = None

    for frame in frames:
        visible = set(frame.visible_contact_addresses)
        for address in current - visible:
            contacts[address].stale_at = frame.point
        for address in visible:
            known = contacts.get(address)
            if known is None:
                contacts[address] = _ContactAccumulator(
                    first=frame.point,
                    last=frame.point,
                    count=1,
                )
            else:
                known.last = frame.point
                known.count += 1
                known.stale_at = None
        current = visible

        declared = own[frame.point.process_id]
        own[frame.point.process_id] = OwnProcessKnowledge(
            process_id=frame.point.process_id,
            reach=frame.self_reach,
            share=declared.share,
            anchor=frame.self_anchor,
            last_observed_at=frame.point,
        )
        core_base = frame.own_core_base
        core_size = frame.own_core_size
        if frame.delivered_read is not None:
            reads.append(frame.delivered_read)

    current_contacts = tuple(
        ContactKnowledge(
            address=address,
            status=KnowledgeStatus.CURRENT,
            first_observed_at=contacts[address].first,
            last_observed_at=contacts[address].last,
            observation_count=contacts[address].count,
        )
        for address in sorted(current)
    )
    stale_contacts = tuple(
        ContactKnowledge(
            address=address,
            status=KnowledgeStatus.STALE,
            first_observed_at=known.first,
            last_observed_at=known.last,
            observation_count=known.count,
            became_stale_at=known.stale_at,
        )
        for address, known in sorted(contacts.items())
        if address not in current
    )
    last_point = frames[-1].point if frames else None
    return PerspectiveState(
        entrant_id=projection.entrant_id,
        tick=tick,
        boundary=boundary,
        through_decision_index=(None if last_point is None else last_point.decision_index),
        last_visibility_sample_at=last_point,
        sampled_this_tick=sampled_this_tick,
        own_core_base=core_base,
        own_core_size=core_size,
        current_contacts=current_contacts,
        stale_contacts=stale_contacts,
        read_history=tuple(reads),
        own_processes=tuple(own[key] for key in sorted(own)),
        arena_size=projection.arena_size,
    )


def project_perspective(derivation: SpectatorDerivation, entrant_id: str) -> PerspectiveProjection:
    """Project one entrant from an already verified and derived pair.

    The supported path-based entry point is :func:`analyze_perspective`.
    Requiring ``SpectatorDerivation`` here prevents a normal caller from
    supplying an arbitrary unverified trace document.
    """

    if not isinstance(derivation, SpectatorDerivation):
        raise TypeError("project_perspective requires a SpectatorDerivation")
    if entrant_id not in derivation.binding.entrant_identities:
        raise PerspectiveError(
            f"entrant {entrant_id!r} is not present in validated pair "
            f"{derivation.binding.entrant_identities}"
        )

    try:
        document = read_trace_v2(derivation.binding.trace_path)
    except TraceFormatError as exc:
        raise PerspectiveConsistencyError(f"validated trace became unreadable: {exc}") from exc
    decisions = document.decisions
    if len(decisions) != derivation.decision_count:
        raise PerspectiveConsistencyError(
            "trace decision count changed after semantic derivation: "
            f"expected {derivation.decision_count}, got {len(decisions)}"
        )

    declaration_records = [
        declaration for declaration in document.declarations if declaration.agent_id == entrant_id
    ]
    declaration_by_id = {record.process_id: record for record in declaration_records}
    if len(declaration_by_id) != len(declaration_records):
        raise PerspectiveConsistencyError(
            f"entrant {entrant_id!r} has duplicate process declarations"
        )
    if not declaration_by_id:
        raise PerspectiveConsistencyError(f"entrant {entrant_id!r} has no process declarations")
    declarations = tuple(
        DeclaredProcess(
            process_id=record.process_id,
            reach=record.reach,
            share=record.share,
        )
        for record in sorted(declaration_records, key=lambda item: item.process_id)
    )

    previous_by_process: dict[str, tuple[int, DecisionRecordV2]] = {}
    previous_visible: set[int] = set()
    frames: list[PerspectiveFrame] = []
    core_identity: tuple[int, int] | None = None
    previous_tick = derivation.first_tick

    for decision_index, decision in enumerate(decisions):
        if decision.agent_id != entrant_id:
            continue
        observation = decision.observation
        if decision.process_id not in declaration_by_id:
            raise _fail(
                decision_index,
                f"undeclared selected-entrant process {decision.process_id!r}",
            )
        if observation.self_process_id != decision.process_id:
            raise _fail(
                decision_index,
                "observation self_process_id does not match decision process_id",
            )
        if observation.self_reach != declaration_by_id[decision.process_id].reach:
            raise _fail(
                decision_index,
                "observation self_reach contradicts the process declaration",
            )
        if observation.current_tick < previous_tick:
            raise _fail(decision_index, "selected-entrant callbacks are out of tick order")
        previous_tick = observation.current_tick
        if not 0 <= observation.self_anchor < derivation.arena_size:
            raise _fail(decision_index, "self anchor is outside the canonical arena")
        if not 0 <= observation.own_core_base < derivation.arena_size:
            raise _fail(decision_index, "own core base is outside the canonical arena")
        if observation.own_core_size <= 0:
            raise _fail(decision_index, "own core size must be positive")
        current_core = (observation.own_core_base, observation.own_core_size)
        if core_identity is None:
            core_identity = current_core
        elif current_core != core_identity:
            raise _fail(decision_index, "own core metadata changed between callbacks")

        visible = observation.visible_enemy_anchor_addresses
        _validate_addresses(visible, derivation.arena_size, decision_index)
        point = CallbackPoint(
            tick=observation.current_tick,
            decision_index=decision_index,
            process_id=decision.process_id,
        )

        previous = previous_by_process.get(decision.process_id)
        if previous is None:
            _validate_initial_feedback(decision_index, decision)
            delivered_read = None
        else:
            previous_index, previous_decision = previous
            delivered_read = _read_delivered_on(
                previous_index,
                previous_decision,
                decision_index,
                decision,
                derivation.arena_size,
            )

        now = set(visible)
        frames.append(
            PerspectiveFrame(
                point=point,
                entrant_callback_index=len(frames),
                last_callback_tick=observation.last_callback_tick,
                previous_action_tick=observation.previous_action_tick,
                previous_action_applied=observation.previous_action_applied,
                own_core_base=observation.own_core_base,
                own_core_size=observation.own_core_size,
                self_anchor=observation.self_anchor,
                self_reach=observation.self_reach,
                visible_contact_addresses=visible,
                gained_contact_addresses=tuple(sorted(now - previous_visible)),
                staled_contact_addresses=tuple(sorted(previous_visible - now)),
                delivered_read=delivered_read,
            )
        )
        previous_visible = now
        previous_by_process[decision.process_id] = (decision_index, decision)

    return PerspectiveProjection(
        entrant_id=entrant_id,
        replay_sha256=derivation.binding.replay_sha256,
        match_id=derivation.binding.match_id,
        ruleset_id=derivation.ruleset_id,
        arena_size=derivation.arena_size,
        first_tick=derivation.first_tick,
        last_tick=derivation.last_tick,
        result_ticks=derivation.result_ticks,
        decision_count=len(decisions),
        declarations=declarations,
        frames=tuple(frames),
        _decision_ticks=tuple(decision.observation.current_tick for decision in decisions),
    )


def analyze_perspective(
    replay_path: str | Path, trace_path: str | Path, entrant_id: str
) -> PerspectiveProjection:
    """Verify, consistency-check, derive, then project one entrant."""

    return project_perspective(analyze_pair(replay_path, trace_path), entrant_id)


def _point_to_dict(point: CallbackPoint | None) -> dict[str, Any] | None:
    if point is None:
        return None
    return {
        "decision_index": point.decision_index,
        "process_id": point.process_id,
        "tick": point.tick,
    }


def _read_to_dict(read: ReadKnowledge) -> dict[str, Any]:
    return {
        "applied": read.applied,
        "delivered_at": _point_to_dict(read.delivered_at),
        "knowledge_kind": ("HISTORICAL_CELL_SAMPLE" if read.applied else "NOT_APPLIED_FEEDBACK"),
        "normalized_address": read.normalized_address,
        "owner": read.owner,
        "process_id": read.process_id,
        "requested_address": read.requested_address,
        "sampled_at": _point_to_dict(read.sampled_at),
        "value": read.value,
    }


def frame_to_dict(frame: PerspectiveFrame) -> dict[str, Any]:
    """Return one deterministic research/debug frame object."""

    payload: dict[str, Any] = {
        "decision_index": frame.point.decision_index,
        "delivered_read": (
            None if frame.delivered_read is None else _read_to_dict(frame.delivered_read)
        ),
        "entrant_callback_index": frame.entrant_callback_index,
        "gained_contact_addresses": list(frame.gained_contact_addresses),
        "last_callback_tick": frame.last_callback_tick,
        "observation_source": "observation.visible_enemy_anchor_addresses",
        "own_core_base": frame.own_core_base,
        "own_core_size": frame.own_core_size,
        "previous_action_applied": frame.previous_action_applied,
        "previous_action_tick": frame.previous_action_tick,
        "process_id": frame.point.process_id,
        "record_type": "perspective_frame",
        "self_anchor": frame.self_anchor,
        "self_reach": frame.self_reach,
        "staled_contact_addresses": list(frame.staled_contact_addresses),
        "tick": frame.point.tick,
        "visible_contact_addresses": list(frame.visible_contact_addresses),
    }
    return payload


def _contact_to_dict(contact: ContactKnowledge) -> dict[str, Any]:
    return {
        "address": contact.address,
        "became_stale_at": _point_to_dict(contact.became_stale_at),
        "first_observed_at": _point_to_dict(contact.first_observed_at),
        "last_observed_at": _point_to_dict(contact.last_observed_at),
        "observation_count": contact.observation_count,
        "source": "observation.visible_enemy_anchor_addresses",
        "status": contact.status.value,
    }


def state_to_dict(state: PerspectiveState) -> dict[str, Any]:
    """Return one deterministic selected-boundary perspective state."""

    return {
        "boundary": state.boundary.value,
        "current_contacts": [_contact_to_dict(contact) for contact in state.current_contacts],
        "entrant_id": state.entrant_id,
        "hidden_not_projected": [
            "opponent_identity_for_contacts",
            "canonical_opponent_process_state",
            "hostile_writes_and_core_loss",
            "process_disruption",
            "entrant_elimination_or_forfeit",
            "match_result_and_victory",
        ],
        "last_visibility_sample_at": _point_to_dict(state.last_visibility_sample_at),
        "own_core_base": state.own_core_base,
        "own_core_size": state.own_core_size,
        "own_processes": [
            {
                "anchor": process.anchor,
                "last_observed_at": _point_to_dict(process.last_observed_at),
                "process_id": process.process_id,
                "reach": process.reach,
                "share": process.share,
            }
            for process in state.own_processes
        ],
        "read_history": [_read_to_dict(read) for read in state.read_history],
        "record_type": "perspective_state",
        "sampled_this_tick": state.sampled_this_tick,
        "schema": PERSPECTIVE_SCHEMA,
        "schema_version": PERSPECTIVE_SCHEMA_VERSION,
        "stale_contacts": [_contact_to_dict(contact) for contact in state.stale_contacts],
        "through_decision_index": state.through_decision_index,
        "tick": state.tick,
    }


def projection_records(
    projection: PerspectiveProjection,
) -> tuple[dict[str, Any], ...]:
    """Return deterministic JSONL-ready projection header and callback frames."""

    header = {
        "callback_count": len(projection.frames),
        "contact_identity": "anonymous_address_only",
        "declarations": [
            {
                "process_id": declaration.process_id,
                "reach": declaration.reach,
                "share": declaration.share,
            }
            for declaration in projection.declarations
        ],
        "decision_count": projection.decision_count,
        "entrant_id": projection.entrant_id,
        "first_tick": projection.first_tick,
        "last_tick": projection.last_tick,
        "match_id": projection.match_id,
        "record_type": "perspective_header",
        "replay_sha256": projection.replay_sha256,
        "result_ticks": projection.result_ticks,
        "ruleset_id": projection.ruleset_id,
        "schema": PERSPECTIVE_SCHEMA,
        "schema_version": PERSPECTIVE_SCHEMA_VERSION,
        "tick_end_semantics": "after all selected-entrant callbacks at tick",
    }
    return (header, *(frame_to_dict(frame) for frame in projection.frames))


def serialize_projection(projection: PerspectiveProjection) -> str:
    """Serialize the full callback projection as deterministic JSONL."""

    return "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in projection_records(projection)
    )


def serialize_state(state: PerspectiveState) -> str:
    """Serialize one selected-boundary state as deterministic JSON."""

    return json.dumps(state_to_dict(state), sort_keys=True, separators=(",", ":")) + "\n"


def _point_label(point: CallbackPoint | None) -> str:
    if point is None:
        return "never"
    return f"tick {point.tick}, decision {point.decision_index}, process {point.process_id}"


def explain_state(state: PerspectiveState) -> str:
    """Render an auditable text explanation of one perspective state."""

    lines = [
        f"PERSPECTIVE {state.entrant_id}",
        f"tick: {state.tick} ({state.boundary.value})",
        f"latest delivered visibility: {_point_label(state.last_visibility_sample_at)}",
        f"sampled this tick: {'yes' if state.sampled_this_tick else 'no'}",
        "",
        "CURRENT CONTACTS",
    ]
    if not state.current_contacts:
        lines.append("  none")
    for contact in state.current_contacts:
        lines.extend(
            [
                f"  address {contact.address} (anonymous occupancy)",
                f"    first observed: {_point_label(contact.first_observed_at)}",
                f"    last confirmed: {_point_label(contact.last_observed_at)}",
                "    source: observation.visible_enemy_anchor_addresses",
            ]
        )

    lines.extend(["", "STALE CONTACTS"])
    if not state.stale_contacts:
        lines.append("  none")
    for contact in state.stale_contacts:
        lines.extend(
            [
                f"  address {contact.address} (anonymous historical occupancy)",
                f"    first observed: {_point_label(contact.first_observed_at)}",
                f"    last confirmed: {_point_label(contact.last_observed_at)}",
                f"    absent at: {_point_label(contact.became_stale_at)}",
            ]
        )

    lines.extend(["", "KNOWN READ RESULTS"])
    if not state.read_history:
        lines.append("  none")
    for read in state.read_history:
        if read.applied:
            lines.extend(
                [
                    f"  address {read.normalized_address} sampled by {read.process_id}",
                    f"    value: {read.value}",
                    f"    cell owner: {read.owner!r} (not contact identity)",
                    f"    sampled: {_point_label(read.sampled_at)}",
                    f"    delivered: {_point_label(read.delivered_at)}",
                ]
            )
        else:
            lines.extend(
                [
                    f"  READ requested at {read.requested_address} by {read.process_id}",
                    "    previous action applied: no; no cell sample",
                    f"    delivered: {_point_label(read.delivered_at)}",
                ]
            )

    lines.extend(["", "OWN STATE"])
    for process in state.own_processes:
        lines.append(
            f"  process {process.process_id}: anchor={process.anchor!r}, "
            f"reach={process.reach}, last observed={_point_label(process.last_observed_at)}"
        )

    lines.extend(
        [
            "",
            "HIDDEN / NOT PROJECTED",
            "  opponent identity or multiplicity for contacts",
            "  canonical opponent process state",
            "  hostile writes, core loss, and disruption",
            "  entrant elimination, match result, and victory",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Research CLI for validated API-v2 perspective projection."""

    parser = argparse.ArgumentParser(
        description="Project one API-v2 entrant perspective from a validated pair"
    )
    parser.add_argument("replay", type=Path, help="canonical schema-4 replay JSONL")
    parser.add_argument("trace", type=Path, help="bound API-v2 trace JSONL")
    parser.add_argument("--perspective", required=True, help="entrant identity to project")
    parser.add_argument("--tick", type=int, help="emit state at this tick")
    parser.add_argument(
        "--tick-start",
        action="store_true",
        help="with --tick, query before that tick's callbacks instead of after",
    )
    parser.add_argument(
        "--explain", action="store_true", help="emit auditable text instead of JSON"
    )
    arguments = parser.parse_args(argv)
    if arguments.tick_start and arguments.tick is None:
        parser.error("--tick-start requires --tick")

    try:
        projection = analyze_perspective(
            arguments.replay,
            arguments.trace,
            arguments.perspective,
        )
        if arguments.tick is None and not arguments.explain:
            output = serialize_projection(projection)
        else:
            tick = projection.result_ticks if arguments.tick is None else arguments.tick
            boundary = TickBoundary.START if arguments.tick_start else TickBoundary.END
            state = projection.state_at_tick(tick, boundary=boundary)
            output = explain_state(state) if arguments.explain else serialize_state(state)
    except (SpectatorPairError, PerspectiveError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0


__all__ = [
    "PERSPECTIVE_SCHEMA",
    "PERSPECTIVE_SCHEMA_VERSION",
    "CallbackPoint",
    "ContactKnowledge",
    "DeclaredProcess",
    "KnowledgeStatus",
    "OwnProcessKnowledge",
    "PerspectiveConsistencyError",
    "PerspectiveCursor",
    "PerspectiveError",
    "PerspectiveFrame",
    "PerspectiveProjection",
    "PerspectiveState",
    "ReadKnowledge",
    "TickBoundary",
    "analyze_perspective",
    "explain_state",
    "frame_to_dict",
    "main",
    "project_perspective",
    "projection_records",
    "serialize_projection",
    "serialize_state",
    "state_to_dict",
]


if __name__ == "__main__":
    raise SystemExit(main())
