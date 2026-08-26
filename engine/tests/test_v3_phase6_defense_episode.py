"""v3 Phase 6: focused tests for the cross-tick active-defense episode
detector (``tools/v3_phase6_defense_episode.py``).

These are hermetic unit tests against synthetic ``TickSnapshot`` sequences,
not real match executions -- the broader empirical validation against the
committed Phase 1 corpus (selectivity, budget robustness, replay
auditability) lives in the module's own ``qualify``/``determinism`` CLI
commands and is reported in
``docs/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md``, which this
module does not duplicate. Each test builds the smallest tick sequence that
isolates one mechanic from the governing Phase 6O checklist.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import v3_phase6_defense_episode as m
from battle_engine.replay import AgentState, KillDeathEvent, MemoryDiff, TickSnapshot

ARENA = 200
CORE = 8


def _agents(*specs: tuple[str, int]) -> tuple[AgentState, ...]:
    return tuple(AgentState(agent_id=agent_id, pc=pc) for agent_id, pc in specs)


def _diff(address: int, length: int, owner: str | None) -> MemoryDiff:
    return MemoryDiff(address=address, length=length, owner=owner, values=tuple([0] * length))


def _seed_tick(specs: tuple[tuple[str, int], ...]) -> TickSnapshot:
    """Tick 0: every entrant claims its own CORE-cell window, exactly like
    ``seed_core_ownership`` does under ``bytefray-rules-2`` before any
    ``act()`` call runs."""

    diffs = [_diff(pc, CORE, agent_id) for agent_id, pc in specs]
    return TickSnapshot(tick=0, agents=_agents(*specs), memory_diffs=tuple(diffs))


def _tick(tick: int, diffs: list[MemoryDiff], events: tuple = ()) -> TickSnapshot:
    return TickSnapshot(tick=tick, memory_diffs=tuple(diffs), events=events)


def _run(records: list[TickSnapshot], *, threshold: int = 1, window: int = 100):
    return m.reconstruct_episodes(records, arena_size=ARENA, threshold=threshold, window=window)


# V's core: addresses 0-7. A's core: 50-57. T's core: 100-107.
V, A, T = ("V", 0), ("A", 50), ("T", 100)


def test_hostile_core_ownership_transition_opens_an_episode():
    records = [_seed_tick((V, A)), _tick(1, [_diff(0, 1, "A")])]
    episodes, _ = _run(records)
    assert len(episodes) == 1
    ep = episodes[0]
    assert (ep.victim, ep.attacker) == ("V", "A")
    assert ep.cells_taken == {0}
    assert ep.start_tick == 1
    assert ep.end_reason == "match_end"


def test_victim_reclaim_closes_the_episode_and_records_a_qualifying_instance():
    records = [
        _seed_tick((V, A)),
        _tick(1, [_diff(0, 1, "A")]),
        _tick(2, [_diff(0, 1, "V")]),
    ]
    episodes, _ = _run(records, threshold=1, window=10)
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.end_reason == "reclaimed_all"
    assert ep.end_tick == 2
    assert len(ep.reclaims) == 1
    reclaim = ep.reclaims[0]
    assert reclaim.tick == 2
    assert reclaim.cells == (0,)
    assert reclaim.qualifying is True
    assert ep.qualified is True


def test_self_write_to_an_already_owned_cell_creates_no_episode():
    """An entrant's own write to a cell it already owns is not an
    ownership *transition* -- Phase 6E's structural self-farming argument:
    there is no path by which V's own action can open a (V, V) episode."""

    records = [_seed_tick((V, A)), _tick(1, [_diff(0, 1, "V")])]
    episodes, _ = _run(records)
    assert episodes == []


def test_same_attacker_continuation_extends_one_episode_across_ticks():
    records = [
        _seed_tick((V, A)),
        _tick(1, [_diff(0, 1, "A")]),
        _tick(2, [_diff(1, 1, "A")]),
    ]
    episodes, _ = _run(records)
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.cells_taken == {0, 1}
    assert ep.cumulative_cells == {0, 1}
    assert ep.start_tick == 1
    assert ep.progress_ticks == [1, 2]


def test_third_party_interruption_closes_the_original_episode_and_opens_a_new_one():
    records = [
        _seed_tick((V, A, T)),
        _tick(1, [_diff(0, 1, "A")]),  # A opens (V, A)
        _tick(2, [_diff(0, 1, "T")]),  # T takes the same cell from A
    ]
    episodes, _ = _run(records)
    by_attacker = {ep.attacker: ep for ep in episodes}
    assert set(by_attacker) == {"A", "T"}
    va = by_attacker["A"]
    assert va.end_reason == "third_party_takeover"
    assert va.end_tick == 2
    assert va.reclaims == []  # the victim never acted -- not a reclaim
    vt = by_attacker["T"]
    assert vt.cells_taken == {0}
    assert vt.end_reason == "match_end"


def test_cross_tick_episode_qualifies_when_progress_and_reclaim_are_both_delayed():
    """The mechanism Phase 5A's same-tick event could never express: the
    assault spans two ticks and the reclaim happens on a third, well after
    the attacker's own turn -- exactly what a low-action-budget match forces
    (Sec 3 C3 of docs/V3_PHASE5A_DEFENSIVE_EVENT_QUALIFICATION.md)."""

    records = [
        _seed_tick((V, A)),
        _tick(1, [_diff(0, 1, "A")]),
        _tick(2, [_diff(1, 1, "A")]),
        _tick(5, [_diff(0, 1, "V"), _diff(1, 1, "V")]),
    ]
    episodes, _ = _run(records, threshold=2, window=10)
    ep = episodes[0]
    assert ep.meaningful_progress_windowed(2, 10) is True
    assert ep.qualified is True
    assert ep.reclaims[0].cumulative_progress_at_reclaim == 2


def test_progress_outside_the_window_is_not_meaningful():
    """The same shape as the cross-tick test above, but the second
    acquisition arrives long after the window closes -- this is the slow
    incidental-sweep-accretion shape the windowed check exists to reject
    (see the module docstring and Sec 4/6 of the governing report)."""

    records = [
        _seed_tick((V, A)),
        _tick(1, [_diff(0, 1, "A")]),
        _tick(50, [_diff(1, 1, "A")]),
        _tick(51, [_diff(0, 1, "V"), _diff(1, 1, "V")]),
    ]
    episodes, _ = _run(records, threshold=2, window=10)
    ep = episodes[0]
    assert ep.meaningful_progress_windowed(2, 10) is False
    assert ep.qualified is False


def test_same_tick_burst_and_reclaim_still_works():
    """Backward-compatible with Phase 5A's original same-tick shape: the
    attacker's whole burst and the victim's reclaim can both land in one
    tick when the victim's seat acts later in that tick's fixed block
    order."""

    records = [
        _seed_tick((V, A)),
        _tick(1, [_diff(0, 4, "A"), _diff(0, 1, "V")]),
    ]
    episodes, _ = _run(records, threshold=4, window=10)
    ep = episodes[0]
    assert ep.cells_taken == {1, 2, 3}
    assert len(ep.reclaims) == 1
    assert ep.reclaims[0].cumulative_progress_at_reclaim == 4
    assert ep.qualified is True


def test_capture_before_any_reclaim_is_not_qualifying():
    records = [
        _seed_tick((V, A)),
        _tick(1, [_diff(0, 8, "A")], events=(KillDeathEvent(event_type="kill", victim="V", killer="A"),)),
    ]
    episodes, _ = _run(records, threshold=4, window=10)
    ep = episodes[0]
    assert ep.end_reason == "captured"
    assert ep.captured_by == "A"
    assert ep.reclaims == []
    assert ep.qualified is False


def test_a_reclaim_on_the_same_tick_as_capture_does_not_qualify():
    """A reclaim recorded for one episode does not save the victim if a
    *different* concurrent episode's cells still zero out its core this
    tick -- the qualifying check must use the tick's actual capture outcome,
    not just this episode's own remaining cell count."""

    # A takes cell 0, T takes cells 1-7 (zeroing V's core), V reclaims cell
    # 0 back in the same tick before the capture check -- but the capture
    # check still sees 0 owned cells because T's takeover of 1-7 is not
    # reclaimed.
    records = [
        _seed_tick((V, A, T)),
        _tick(
            1,
            [_diff(0, 1, "A"), _diff(1, 7, "T"), _diff(0, 1, "V")],
            events=(KillDeathEvent(event_type="kill", victim="V", killer="T"),),
        ),
    ]
    episodes, _ = _run(records, threshold=1, window=10)
    va = next(ep for ep in episodes if ep.attacker == "A")
    assert va.end_reason == "reclaimed_all"
    assert len(va.reclaims) == 1
    assert va.reclaims[0].qualifying is False  # V was captured this same tick


def test_multiple_reclaim_cycles_within_one_open_episode():
    records = [
        _seed_tick((V, A)),
        _tick(1, [_diff(0, 1, "A"), _diff(1, 1, "A")]),  # A takes cells 0,1
        _tick(2, [_diff(0, 1, "V")]),  # V reclaims cell 0 only; episode stays open (cell 1 still held)
        _tick(3, [_diff(2, 1, "A")]),  # A extends the same still-open episode with a new cell
        _tick(4, [_diff(1, 1, "V"), _diff(2, 1, "V")]),  # V reclaims the rest -> episode closes
    ]
    episodes, _ = _run(records, threshold=1, window=10)
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.end_reason == "reclaimed_all"
    assert ep.end_tick == 4
    assert len(ep.reclaims) == 2
    assert ep.reclaims[0].cells == (0,)
    assert ep.reclaims[1].cells == (1, 2)
    assert ep.cumulative_cells == {0, 1, 2}


def test_wraparound_core_is_handled_via_modular_addressing():
    small_arena = 20
    victim = ("V", 16)  # core window wraps: 16, 17, 18, 19, 0, 1, 2, 3
    attacker = ("A", 8)  # core window: 8..15 -- disjoint from V's
    seed = TickSnapshot(
        tick=0,
        agents=_agents(victim, attacker),
        memory_diffs=(_diff(16, 4, "V"), _diff(0, 4, "V"), _diff(8, 8, "A")),
    )
    # attacker takes wrapped address 17 (the second cell of V's window)
    hostile = _tick(1, [_diff(17, 1, "A")])
    episodes, _ = m.reconstruct_episodes([seed, hostile], arena_size=small_arena, threshold=1, window=10)
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.victim == "V"
    assert ep.cells_taken == {17}


def test_seat_labels_are_generic_not_positionally_assumed():
    """Reconstruction must not assume a fixed seat-name convention -- only
    that ``core_owner_of``/``windows`` are built from whichever agent_ids
    tick 0 actually publishes, in whatever order."""

    z, y, x = ("zulu", 100), ("yankee", 0), ("xray", 50)
    records = [_seed_tick((z, y, x)), _tick(1, [_diff(0, 1, "xray")])]
    episodes, _ = _run(records)
    assert len(episodes) == 1
    assert episodes[0].victim == "yankee"
    assert episodes[0].attacker == "xray"


def test_reconstruction_is_deterministic_across_two_independent_passes():
    records = [
        _seed_tick((V, A, T)),
        _tick(1, [_diff(0, 2, "A")]),
        _tick(2, [_diff(2, 1, "T")]),
        _tick(3, [_diff(0, 1, "V")]),
        _tick(4, [_diff(3, 1, "A")]),
        _tick(5, [_diff(1, 1, "V"), _diff(3, 1, "V")]),
    ]

    def _fingerprint(episodes):
        return sorted(
            (
                ep.victim,
                ep.attacker,
                ep.start_tick,
                ep.end_tick,
                ep.end_reason,
                tuple(sorted(ep.cumulative_cells)),
                tuple((r.tick, r.cells, r.qualifying) for r in ep.reclaims),
            )
            for ep in episodes
        )

    first, _ = _run(list(records), threshold=1, window=10)
    second, _ = _run(list(records), threshold=1, window=10)
    assert _fingerprint(first) == _fingerprint(second)


def test_max_assault_ticks_scales_with_action_budget():
    # ceil(ASSAULT_WINDOW / action_budget) + 1 slack tick, derived from the
    # search agents' own ASSAULT_WINDOW=16 constant, not fitted to a result.
    assert m.max_assault_ticks(2) == 9
    assert m.max_assault_ticks(8) == 3
    assert m.max_assault_ticks(16) == 2
    assert m.max_assault_ticks(32) == 2
    assert m.max_assault_ticks(1) == 17
