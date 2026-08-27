"""Renderer-independent replay analysis facts.

Territory ownership, match events, and selected-cell state, derived only
from ``battle_client.session`` (``ReplaySession``/``ReplayState``) and
``battle_engine.replay``. No Pygame import, directly or indirectly -- this
module is safe to import and use with no display and no renderer package
installed. See ``docs/specs/replay_analysis.md`` (v0.4 Phase 5) for the
extraction rationale: every function/dataclass here was previously a
private, duplicated implementation inside
``battle_client.renderers.pygame_renderer``, moved here verbatim (see that
spec's §6 for the one deliberate behavior boundary correction --
``SelectedCellInfo`` no longer carries the renderer-local
``recently_changed`` flag).
"""

from __future__ import annotations

import bisect
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from battle_engine.replay import AgentEvent, EngineEvent, KillDeathEvent, RuntimeEvent

from battle_client.session import ReplaySession, ReplayState


def territory_summary(state: ReplayState) -> dict[str, tuple[int, float]]:
    """Each entrant's ``(owned_cell_count, percentage_of_arena)``.

    Derived entirely from ``state.owners`` -- an ownership snapshot, not
    canonical score. Every agent present in ``state.agents`` is included,
    even at zero owned cells, so a caller never has to treat a missing
    entry as "unknown" versus "owns nothing".
    """
    total = len(state.owners)
    counts = Counter(owner for owner in state.owners if owner is not None)
    summary: dict[str, tuple[int, float]] = {}
    for agent_id in state.agents:
        count = counts.get(agent_id, 0)
        percentage = (count / total * 100.0) if total else 0.0
        summary[agent_id] = (count, percentage)
    return summary


@dataclass(frozen=True)
class TerritoryHistory:
    """Every entrant's owned-cell percentage at every recorded tick.

    ``ticks`` is strictly increasing (it is ``session.recorded_ticks`` in
    order); ``percentages[agent_id]`` is a tuple aligned index-for-index
    with ``ticks``. An agent absent from a given tick's ``ReplayState.
    agents`` -- never happens for a canonical replay, which reports every
    entrant every tick, but handled honestly rather than assumed for a
    legacy one -- is recorded as ``0.0`` for that tick rather than
    omitted, so every agent's series has exactly ``len(ticks)`` points.
    This is a territory (ownership) metric derived only from ``state.
    owners``, same as :func:`territory_summary`; it is never a substitute
    for canonical score.
    """

    ticks: tuple[int, ...]
    percentages: Mapping[str, tuple[float, ...]]


def compute_territory_history(session: ReplaySession) -> TerritoryHistory:
    """Derive :class:`TerritoryHistory` by walking ``session`` forward once.

    Uses only ``ReplaySession``'s own existing incremental reconstruction
    (``restart``/``step_forward``) -- there is no second reconstruction of
    memory diffs, and no per-tick full arena snapshot is stored, only each
    tick's small ``{agent_id: percentage}`` summary. Intended to be called
    once per loaded session, not on every rendered frame -- walking ~3000
    ticks once is cheap; doing it every frame would not be.

    The session's cursor is restored to wherever it was before this call
    (via ``seek`` back to the original tick), so calling this mid-playback
    never disturbs the caller's position. Returns an empty history for a
    replay with no tick records.
    """
    if not session.loaded or session.final_tick is None:
        return TerritoryHistory(ticks=(), percentages={})

    original_tick = session.current_tick
    ticks: list[int] = []
    points: list[dict[str, float]] = []
    agent_ids: set[str] = set()

    state = session.restart()
    while True:
        ticks.append(state.tick)
        summary = territory_summary(state)
        points.append({agent_id: percentage for agent_id, (_count, percentage) in summary.items()})
        agent_ids.update(summary)
        if session.at_end:
            break
        state = session.step_forward()

    percentages = {
        agent_id: tuple(point.get(agent_id, 0.0) for point in points) for agent_id in agent_ids
    }
    session.seek(original_tick)
    return TerritoryHistory(ticks=tuple(ticks), percentages=percentages)


def collect_match_events(session: ReplaySession) -> list[tuple[int, EngineEvent]]:
    """Every recorded event in ``session``, as ``(tick, event)`` pairs.

    ``session.recorded_ticks`` is already strictly increasing (see
    ``ReplaySession``'s own tick-identity guarantee), so this list comes
    out chronologically ordered for free. Both ``events_at_tick`` and
    ``recorded_ticks`` are non-mutating lookups (see
    ``docs/specs/replay_session.md`` §14), so this never touches the
    session's playback cursor.
    """
    events: list[tuple[int, EngineEvent]] = []
    for tick in session.recorded_ticks:
        for event in session.events_at_tick(tick):
            events.append((tick, event))
    return events


def events_near_tick(
    events: Sequence[tuple[int, EngineEvent]], tick: int, window: int = 5
) -> list[tuple[int, EngineEvent]]:
    """Up to ``window`` most recent events at or before ``tick``.

    ``events`` is assumed already in ascending tick order (as
    :func:`collect_match_events` returns it); the result stays in that
    same ascending order, so it reads top-to-bottom the same direction as
    the match itself played out.
    """
    at_or_before = [pair for pair in events if pair[0] <= tick]
    return at_or_before[-window:] if window > 0 else []


def timeline_event_marks(
    events: Sequence[tuple[int, EngineEvent]],
) -> tuple[tuple[int, str | None], ...]:
    """Each recorded event reduced to ``(tick, affected_agent_id)``.

    Used to mark where notable moments sit along a whole-match timeline. The
    "affected agent" is the event's own victim (a kill/death or a runtime
    forfeit) or its acting agent (a historical ``AgentEvent``), and is
    ``None`` when the event names no agent at all -- never guessed. Nothing
    here classifies *why* an entrant died: a core capture is distinguished
    from an ordinary kill only by ``AgentState.termination_reason``, which is
    tick state rather than event data, and ``battle_client.replay_status``
    remains the single place that check lives.

    Duplicates are collapsed, so several events naming the same agent on the
    same tick contribute one mark rather than overdrawing each other. The
    result stays in ascending tick order, matching
    :func:`collect_match_events`'s own ordering.
    """
    marks: list[tuple[int, str | None]] = []
    seen: set[tuple[int, str | None]] = set()
    for tick, event in events:
        if isinstance(event, (KillDeathEvent, RuntimeEvent)):
            agent_id: str | None = event.victim
        elif isinstance(event, AgentEvent):
            agent_id = event.agent_id
        else:  # pragma: no cover - EngineEvent is a closed union
            agent_id = None
        key = (tick, agent_id)
        if key not in seen:
            seen.add(key)
            marks.append(key)
    return tuple(marks)


def nearest_recorded_tick(recorded_ticks: Sequence[int], tick: int) -> int | None:
    """The recorded tick closest to ``tick``, or ``None`` if there are none.

    ``recorded_ticks`` is assumed strictly increasing (as
    ``ReplaySession.recorded_ticks`` guarantees). A canonical replay records
    every integer tick, so this is an identity for any in-range request; it
    exists for the sparse legacy case, where an arbitrary requested tick may
    fall in a gap and ``ReplaySession.seek`` would reject it. Ties (a request
    exactly between two recorded ticks) resolve to the earlier one, so the
    mapping is deterministic rather than dependent on rounding direction.
    """
    if not recorded_ticks:
        return None
    index = bisect.bisect_left(recorded_ticks, tick)
    if index == 0:
        return recorded_ticks[0]
    if index >= len(recorded_ticks):
        return recorded_ticks[-1]
    before, after = recorded_ticks[index - 1], recorded_ticks[index]
    return after if (after - tick) < (tick - before) else before


@dataclass(frozen=True)
class SelectedCellInfo:
    """The authoritative replay-domain state at one selected arena address.

    Every field is read straight off an existing ``ReplayState``; nothing
    here is fabricated. ``occupant`` is only ever populated for a VM
    replay (``AgentState.pc`` is a real fetch address there and only
    there); for a Python replay it stays ``None`` unconditionally, since
    the Python controller's ``pc`` value is not a position an agent can be
    said to "occupy". Deliberately carries no renderer-local/temporal
    state (e.g. "was this cell's owner just changed?") -- that is UI
    observation history, not a replay fact; see
    ``docs/specs/replay_analysis.md`` §6.
    """

    address: int
    byte_value: int | None
    owner: str | None
    occupant: str | None


def selected_cell_info(state: ReplayState, address: int) -> SelectedCellInfo | None:
    """``SelectedCellInfo`` for ``address`` in ``state``, or ``None`` if
    ``address`` is outside ``state.owners``' range (out-of-range for the
    replay's arena).
    """
    if address < 0 or address >= len(state.owners):
        return None
    byte_value = state.arena[address] if address < len(state.arena) else None
    owner = state.owners[address]
    occupant = None
    if state.runtime_kind == "vm":
        for agent_id, agent in state.agents.items():
            if agent.alive and isinstance(agent.pc, int) and agent.pc == address:
                occupant = agent_id
                break
    return SelectedCellInfo(
        address=address,
        byte_value=byte_value,
        owner=owner,
        occupant=occupant,
    )
