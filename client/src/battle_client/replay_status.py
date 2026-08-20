"""Ruleset-aware, replay-derived entrant status model (Beta1 Phase 3).

This module answers one question for the eventual Replay Viewer HUD (Beta1
Phase 4): *what is the status of every entrant at the replay's current
position?* -- alive/dead, core integrity/capture, capture attribution, and
the existing score/territory/kill facts the replay already carries. It is a
renderer-neutral domain layer, exactly like ``battle_client.analysis``: no
Pygame import, directly or indirectly, and it derives everything from
``battle_client.session`` (``ReplaySession``/``ReplayState``) plus a small,
explicitly justified set of shared domain helpers imported from
``battle_engine.python_runtime`` (never the reverse -- ``battle_engine``
never imports ``battle_client``).

See ``docs/V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md`` for the full audit this
model is built on. Three points from that audit matter most while reading
this module:

1. **No replay schema change was needed.** Every fact below -- including
   each entrant's own fixed core-anchor address -- is already present in a
   canonical ``battle2.replay`` v3 artifact; nothing new is persisted.
2. **Core integrity is ownership, never byte content.** Every derivation
   here counts ``ReplayState.owners`` entries; it never inspects
   ``ReplayState.arena`` byte values. This is what makes a beacon-restored
   cell "intact" and a non-zero-but-foreign-owned cell "damaged" --
   matching ``bytefray-rules-2``'s runtime semantics exactly (see
   ``docs/RULES_V2.md``'s "How is a core damaged" section).
3. **Status reflects a completed tick.** ``ReplayState`` (whatever tick it
   was reconstructed at) already represents state *after* that tick's
   capture check and maintenance ran -- there is no separate "mid-tick"
   status to compute.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from battle_engine.python_runtime import CORE_SIZE, core_addresses, has_vulnerable_core
from battle_engine.replay import (
    EngineEvent,
    KillDeathEvent,
    ReplayHeader,
    RuntimeEvent,
    resolve_replay_ruleset,
)

from battle_client.analysis import collect_match_events, territory_summary
from battle_client.session import ReplaySession, ReplaySessionError, ReplayState

MatchEvents = Sequence[tuple[int, EngineEvent]]


@dataclass(frozen=True)
class CoreStatus:
    """One entrant's Ruleset-v2 core state, derived from ownership alone.

    ``core_addresses`` is the entrant's fixed 8-cell window (see
    ``battle_engine.python_runtime.core_addresses``); it never changes
    across a match. ``intact_cells``/``damaged_cells`` are authoritative
    counts -- ``integrity_fraction`` is a display convenience derived from
    them, never a separately tracked value.
    """

    core_addresses: tuple[int, ...]
    total_cells: int
    intact_cells: int
    damaged_cells: int
    integrity_fraction: float
    captured: bool
    capture_tick: int | None


@dataclass(frozen=True)
class EntrantReplayStatus:
    """One entrant's full replay-derived status at one replay tick.

    ``order`` preserves this entrant's position in the replay's own
    recorded entrant order (spawn/request order), never re-sorted -- a
    caller that wants alphabetical or score-sorted display order can sort
    this tuple itself, but the model's own order is always authoritative
    and N-entrant generic (see ``get_entrant_statuses``).

    ``core`` is ``None`` whenever Ruleset-v2 core semantics do not apply --
    Ruleset v1, a VM match (including a VM-dispatched historical alpha
    match, where the core mechanic is inert), or a replay whose Ruleset
    identity cannot be established with confidence (see
    ``battle_engine.replay.resolve_replay_ruleset``). This is a deliberate
    "unavailable, not fabricated" ``None`` -- never a fake ``8/8``.
    """

    agent_id: str
    name: str
    order: int
    start_address: int | None
    alive: bool
    death_tick: int | None
    death_reason: str | None
    killer_id: str | None
    core: CoreStatus | None
    tick: int
    score: int | float
    territory_cells: int
    territory_percentage: float
    kills_so_far: int


def _entrant_core_start(session: ReplaySession, agent_id: str) -> int | None:
    """This entrant's fixed core-anchor address, derived from tick 0.

    ``seed_core_ownership`` (``battle_engine.python_runtime``) is the only
    write any Python entrant performs before its first ``act()`` call, and
    it writes its own 8 core cells, in address order starting at its own
    anchor, before any other entrant's seeding begins -- so the *first*
    tick-0 ``MemoryDiff`` owned by ``agent_id``, taken in recorded (write)
    order, starts at exactly that anchor address, even if the core later
    wraps the arena boundary (which splits it into two diffs) or another
    entrant's overlapping core partially overwrites it later in the same
    tick (which appears as a *separate*, later diff attributed to that
    other owner -- this entrant's own original diff is unaffected).

    Returns ``None`` if tick 0 was not recorded (a sparse legacy replay)
    or if ``agent_id`` never wrote anything at tick 0 (Ruleset v1, or a VM
    match, where tick 0's diffs are code-load footprints, not core seeds).
    """
    try:
        diffs = session.memory_diffs_at_tick(0)
    except ReplaySessionError:
        return None
    for diff in diffs:
        if diff.owner == agent_id and diff.length > 0:
            return diff.address
    return None


def _death_tick_and_killer(events: MatchEvents, agent_id: str) -> tuple[int | None, str | None]:
    """The tick ``agent_id`` died and its attributed killer, if any.

    Scans ``events`` (already filtered to ticks at or before the status
    being computed -- see ``get_entrant_statuses``) in ascending order and
    returns the first death-shaped event naming ``agent_id`` as victim --
    an entrant dies at most once, so the first match is the match. Covers
    both event shapes a Python death can produce: ``KillDeathEvent``
    (``"kill"`` with an attributed killer, or unattributed ``"death"`` --
    this is what a core capture produces) and ``RuntimeEvent`` (a
    malformed-action/callback-failure forfeit, which is never attributed).
    """
    for tick, event in events:
        if isinstance(event, KillDeathEvent) and event.victim == agent_id:
            return tick, event.killer
        if isinstance(event, RuntimeEvent) and event.victim == agent_id:
            return tick, None
    return None, None


def _core_status(
    session: ReplaySession,
    state: ReplayState,
    agent_id: str,
    *,
    alive: bool,
    death_reason: str | None,
    death_tick: int | None,
) -> CoreStatus | None:
    """``CoreStatus`` for ``agent_id``, or ``None`` if unavailable.

    Ruleset-aware per docs/RULES_V2.md: only a *Python* match (the core
    mechanic has no VM implementation -- a VM-dispatched historical alpha
    match is inert) under a Ruleset identity in
    ``battle_engine.python_runtime.VULNERABLE_CORE_RULESET_IDS`` (alpha.1,
    alpha.11, or permanent v2 -- distinct identities, identical derivation,
    per docs/RULES_V2.md's "Ruleset identity and history") is eligible.
    An unrecoverable/unknown Ruleset identity (``resolve_replay_ruleset``
    returns ``value=None``) fails closed to ``None``, never a guess.
    """
    if state.runtime_kind != "python":
        return None
    header = session.header
    assert header is not None
    ruleset_id = resolve_replay_ruleset(header).value
    if ruleset_id is None or not has_vulnerable_core(ruleset_id):
        return None
    start = _entrant_core_start(session, agent_id)
    if start is None:
        return None
    addresses = core_addresses(start, len(state.owners))
    intact = sum(1 for address in addresses if state.owners[address] == agent_id)
    captured = (not alive) and death_reason == "core_captured"
    return CoreStatus(
        core_addresses=addresses,
        total_cells=CORE_SIZE,
        intact_cells=intact,
        damaged_cells=CORE_SIZE - intact,
        integrity_fraction=intact / CORE_SIZE,
        captured=captured,
        capture_tick=death_tick if captured else None,
    )


def get_entrant_statuses(
    session: ReplaySession,
    *,
    state: ReplayState | None = None,
    match_events: MatchEvents | None = None,
) -> tuple[EntrantReplayStatus, ...]:
    """Every entrant's status at ``state`` (default: ``session``'s current
    position), in the replay's own recorded entrant order.

    Works identically for any entrant count -- there is no two-slot
    assumption anywhere in this function; a 3+-entrant replay returns one
    ``EntrantReplayStatus`` per entrant, in order, exactly like a 2-entrant
    one (see ``docs/V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md``'s N-entrant
    qualification).

    ``match_events``, if supplied, must be ``battle_client.analysis.
    collect_match_events(session)``'s own return value (or an equivalent
    ascending-tick-order sequence) -- pass it explicitly to avoid this
    function re-walking the whole replay's event stream on every call, the
    same optional-precomputed-events pattern
    ``pygame_renderer.build_hud_lines`` already uses. Left unset, this
    function computes it itself, which is the right default for one-off
    callers (a CLI inspection command, a test) but not for a per-frame
    render loop over a long replay.
    """
    if not session.loaded:
        raise ReplaySessionError("no replay loaded")
    header = session.header
    assert header is not None
    current = state if state is not None else session.current_state
    events = list(match_events) if match_events is not None else collect_match_events(session)
    relevant_events = [pair for pair in events if pair[0] <= current.tick]
    territory = territory_summary(current)

    # ``header.entrants`` (v3 canonical only) carries each entrant's own
    # display name; the older, simpler ``header.agents`` id->name mapping
    # is what the raw live-match header actually populates for a Python
    # match (``ReplayPublisher.publish_header`` writes no agent names at
    # all), so it is empty in practice for a real Python replay -- prefer
    # the richer, always-correct source when it exists, exactly like
    # ``agent_order`` already does below, and only fall back to
    # ``header.agents`` for a legacy v0.1/v0.2 replay that has no
    # ``entrants`` field at all.
    if header.entrants:
        agent_order = [entry["agent_id"] for entry in header.entrants]
        agent_names = {
            entry["agent_id"]: str(entry.get("name", entry["agent_id"]))
            for entry in header.entrants
        }
    else:
        agent_order = list(current.agents)
        agent_names = dict(header.agents)

    statuses: list[EntrantReplayStatus] = []
    for order, agent_id in enumerate(agent_order):
        agent_state = current.agents.get(agent_id)
        if agent_state is None:
            continue
        alive = agent_state.alive
        death_tick, killer_id = (
            (None, None) if alive else _death_tick_and_killer(relevant_events, agent_id)
        )
        kills_so_far = sum(
            1
            for _tick, event in relevant_events
            if isinstance(event, KillDeathEvent)
            and event.event_type == "kill"
            and event.killer == agent_id
        )
        territory_cells, territory_percentage = territory.get(agent_id, (0, 0.0))
        core = _core_status(
            session,
            current,
            agent_id,
            alive=alive,
            death_reason=agent_state.termination_reason,
            death_tick=death_tick,
        )
        statuses.append(
            EntrantReplayStatus(
                agent_id=agent_id,
                name=agent_names.get(agent_id, agent_id),
                order=order,
                start_address=core.core_addresses[0] if core is not None else None,
                alive=alive,
                death_tick=death_tick,
                death_reason=agent_state.termination_reason,
                killer_id=killer_id,
                core=core,
                tick=current.tick,
                score=current.score.get(agent_id, 0),
                territory_cells=territory_cells,
                territory_percentage=territory_percentage,
                kills_so_far=kills_so_far,
            )
        )
    return tuple(statuses)


def resolve_match_ruleset_label(header: ReplayHeader) -> str:
    """A short, confidence-qualified display label for a replay's Ruleset
    identity (Beta1 Phase 4's "is this v1 or v2" requirement -- see
    ``docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md``).

    Thin presentation wrapper around ``resolve_replay_ruleset`` -- the same
    confidence-qualified resolution ``_core_status`` already uses -- kept in
    this domain module rather than the renderer so the renderer never
    re-derives Ruleset identity itself. ``"recorded"`` confidence (the
    normal case for any replay written by this codebase) shows the bare
    identity string; ``"recovered"``/``"unknown"`` are shown qualified,
    exactly like ``docs/REPLAY_SCHEMA.md`` documents them, rather than
    silently presented as equally certain.
    """
    resolved = resolve_replay_ruleset(header)
    if resolved.value is None:
        return "unknown"
    if resolved.confidence == "recorded":
        return resolved.value
    return f"{resolved.value} ({resolved.confidence})"


__all__ = [
    "CoreStatus",
    "EntrantReplayStatus",
    "get_entrant_statuses",
    "resolve_match_ruleset_label",
]
