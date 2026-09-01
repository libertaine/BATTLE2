from __future__ import annotations

"""v4 alpha2 qualification: round-robin intra-entrant process selection.

Covers the scheduler half of the alpha2 Ruleset delta
(``docs/V4_ALPHA2_DESIGN.md``). Two layers:

* direct unit coverage of ``ProcessMatchController._select_active_process``,
  which is where the whole semantic lives -- initial cursor, advancement,
  disruption, quota exhaustion, redistribution, and the deliberate absence of
  a tick reset -- driven slot by slot so each documented clause is asserted
  on its own rather than inferred from a match outcome;
* end-to-end match coverage proving the entrant-level K=2 scheduler, the
  quota allocator, and alpha1's own frozen selection are all untouched.
"""

from typing import Any

import pytest
from battle_engine.agent_api import ActionKindV2, AgentAction, ObservationV2
from battle_engine.config import Config
from battle_engine.process_runtime import (
    ProcessEntrantSpec,
    ProcessInstance,
    ProcessMatchController,
    ProcessRole,
)
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1, RULESET_V4_ALPHA2

QUOTA = 8
ARENA = 512


def _noop(_observation: ObservationV2, _state: dict[str, Any]) -> AgentAction:
    return AgentAction(ActionKindV2.MOVE, 0)


def _process(process_id: str, share: int, position: int = 0) -> ProcessInstance:
    return ProcessInstance(
        process_id,
        ProcessRole.GENERALIST,
        initial_position=position,
        reach=8,
        quota_share=share,
        logic=_noop,
    )


def _entrant(agent_id: str, shares: dict[str, int], start: int) -> ProcessEntrantSpec:
    return ProcessEntrantSpec(
        agent_id=agent_id,
        name=agent_id,
        processes=[
            _process(process_id, share, start) for process_id, share in shares.items()
        ],
        start=start,
    )


def _controller(policy, shares: dict[str, int]) -> ProcessMatchController:
    """A two-entrant controller whose seat A carries ``shares``.

    Seat B is a single passive process: the selection rule under test is
    entrant-local, and a lone opponent keeps the match legal without adding
    a second multi-process entrant whose own rotation would have to be
    reasoned about alongside seat A's.
    """

    return ProcessMatchController(
        Config(arena_size=ARENA, instr_per_tick=QUOTA, seed=1),
        [
            _entrant("A", shares, start=0),
            _entrant("B", {"solo": QUOTA}, start=ARENA // 2),
        ],
        max_ticks=4,
        ruleset_policy=policy,
    )


def _drive_one_tick(
    controller: ProcessMatchController,
    *,
    disrupt_after: dict[int, set[str]] | None = None,
) -> list[str]:
    """Hand seat A ``QUOTA`` action slots and record who takes each one.

    ``disrupt_after`` maps a slot index to the process IDs that become
    ineligible *from that slot onward*, which is exactly the mid-tick
    condition a sibling being disrupted by an enemy write creates: the
    allocator is re-run every slot, so the freed quota is redistributed and
    then handed out by the selection rule under test.
    """

    spec = controller.entrant_specs[0]
    disrupt_after = disrupt_after or {}
    ineligible: set[str] = set()
    actions = {process.process_id: 0 for process in spec.processes}
    order: list[str] = []
    for slot in range(QUOTA):
        ineligible |= disrupt_after.get(slot, set())
        eligible = [p for p in spec.processes if p.process_id not in ineligible]
        quotas = _allocate(controller, eligible)
        selected = controller._select_active_process(spec, quotas, actions)
        if selected is None:
            order.append("-")
            continue
        actions[selected.process_id] += 1
        order.append(selected.process_id)
    return order


def _allocate(
    controller: ProcessMatchController, eligible: list[ProcessInstance]
) -> dict[ProcessInstance, int]:
    """Reuse the production allocator against an explicit eligible set.

    Calls ``_effective_process_quotas`` on a spec containing only the
    eligible processes, so the numbers under test are the real allocation
    and redistribution arithmetic, never a reimplementation of it.
    """

    if not eligible:
        return {}
    stand_in = ProcessEntrantSpec(agent_id="A", name="A", processes=eligible)
    return controller._effective_process_quotas(stand_in, tick=1)


# ---------------------------------------------------------------------------
# The selection rule, clause by clause
# ---------------------------------------------------------------------------


def test_alpha1_priority_scan_always_restarts_at_the_first_declared_process() -> None:
    """Alpha1's frozen rule, asserted so alpha2 cannot silently redefine it."""

    controller = _controller(RULESET_V4_ALPHA1, {"p1": 4, "p2": 4})
    assert _drive_one_tick(controller) == ["p1"] * 4 + ["p2"] * 4


def test_alpha2_rotates_between_an_entrants_processes() -> None:
    controller = _controller(RULESET_V4_ALPHA2, {"p1": 4, "p2": 4})
    assert _drive_one_tick(controller) == ["p1", "p2"] * 4


def test_alpha2_initial_cursor_is_the_first_declared_process() -> None:
    """Rotation must start somewhere stable and obvious, not mid-list."""

    controller = _controller(RULESET_V4_ALPHA2, {"first": 2, "second": 3, "third": 3})
    assert controller._process_cursor == {"A": 0, "B": 0}
    assert _drive_one_tick(controller)[0] == "first"


def test_a_single_process_entrant_is_unaffected_by_the_selection_rule() -> None:
    """One process has nothing to rotate with, so both Rulesets must agree.

    This is why the Phase 4 study saw single-process agents' own scheduling
    move not at all under round-robin: the rule is a no-op for them.
    """

    alpha1 = _drive_one_tick(_controller(RULESET_V4_ALPHA1, {"solo": QUOTA}))
    alpha2 = _drive_one_tick(_controller(RULESET_V4_ALPHA2, {"solo": QUOTA}))
    assert alpha1 == alpha2 == ["solo"] * QUOTA


def test_total_slots_stay_at_q_under_both_rulesets_when_work_is_available() -> None:
    """Round-robin changes who acts, never how much the entrant acts."""

    for policy in (RULESET_V4_ALPHA1, RULESET_V4_ALPHA2):
        order = _drive_one_tick(_controller(policy, {"p1": 3, "p2": 3, "p3": 2}))
        assert len(order) == QUOTA
        assert "-" not in order


def test_quota_allocation_is_identical_under_both_rulesets() -> None:
    """The allocation is the allocator's business and must not move.

    Same shares, same eligibility, same numbers -- the only difference alpha2
    introduces is the order the allocated slots are handed out in.
    """

    shares = {"p1": 3, "p2": 3, "p3": 2}
    counts = []
    for policy in (RULESET_V4_ALPHA1, RULESET_V4_ALPHA2):
        order = _drive_one_tick(_controller(policy, shares))
        counts.append({pid: order.count(pid) for pid in shares})
    assert counts[0] == counts[1] == {"p1": 3, "p2": 3, "p3": 2}


def test_a_disrupted_process_is_skipped_without_consuming_its_turn() -> None:
    """Rotation passes over an ineligible process and continues, rather than
    spending a slot on it or stalling the entrant."""

    controller = _controller(RULESET_V4_ALPHA2, {"p1": 3, "p2": 3, "p3": 2})
    order = _drive_one_tick(controller, disrupt_after={0: {"p2"}})
    assert "p2" not in order[1:]
    assert len(order) == QUOTA
    assert "-" not in order


def test_freed_quota_is_redistributed_and_then_rotated_not_hoarded() -> None:
    """The accidental lever Phase 4 measured, and its removal.

    A sibling becoming ineligible mid-tick frees its allocation. Alpha1
    always offers the freed slots to the earliest-declared eligible process,
    so ``p1`` absorbs the lot. Alpha2 redistributes the same quota (identical
    totals) and hands the slots out in rotation instead.
    """

    shares = {"p1": 4, "p2": 4}
    alpha1 = _drive_one_tick(
        _controller(RULESET_V4_ALPHA1, shares), disrupt_after={2: {"p2"}}
    )
    alpha2 = _drive_one_tick(
        _controller(RULESET_V4_ALPHA2, shares), disrupt_after={2: {"p2"}}
    )
    assert len(alpha1) == len(alpha2) == QUOTA
    assert "-" not in alpha1 and "-" not in alpha2
    # p2 was eligible and owed quota for the first two slots of the tick.
    # Under alpha1 it got neither of them -- the scan restarts at p1 every
    # slot -- and then lost its allocation to the redistribution, so it acts
    # zero times despite never having exhausted its own share. Under alpha2
    # the rotation gave it its turn before it became ineligible.
    assert alpha1 == ["p1"] * QUOTA
    assert alpha1.count("p2") == 0
    assert alpha2.count("p2") == 1
    assert alpha2[:2] == ["p1", "p2"]
    # Identical totals either way: redistribution is the allocator's, and is
    # unchanged.
    assert alpha1.count("p1") + alpha1.count("p2") == QUOTA
    assert alpha2.count("p1") + alpha2.count("p2") == QUOTA


def test_an_entrant_with_every_process_disrupted_receives_no_actions() -> None:
    controller = _controller(RULESET_V4_ALPHA2, {"p1": 4, "p2": 4})
    assert _drive_one_tick(controller, disrupt_after={0: {"p1", "p2"}}) == ["-"] * QUOTA


def test_the_cursor_does_not_advance_on_a_slot_that_selects_nothing() -> None:
    """A wasted slot must not silently cost a process its next turn."""

    controller = _controller(RULESET_V4_ALPHA2, {"p1": 4, "p2": 4})
    spec = controller.entrant_specs[0]
    before = controller._process_cursor["A"]
    assert controller._select_active_process(spec, {}, {"p1": 0, "p2": 0}) is None
    assert controller._process_cursor["A"] == before


def test_the_cursor_is_match_scoped_and_never_resets_at_a_tick_boundary() -> None:
    """Rotation continues across ticks, by design.

    Resetting per tick would hand the first-declared process the opening slot
    of every single tick -- a weaker form of exactly the declaration-order
    bias alpha2 exists to remove. Shares of 3/3/2 leave the cursor mid-list
    at the end of a tick, which is what makes the carry-over observable.
    """

    controller = _controller(RULESET_V4_ALPHA2, {"p1": 3, "p2": 3, "p3": 2})
    first = _drive_one_tick(controller)
    carried = controller._process_cursor["A"]
    second = _drive_one_tick(controller)
    assert carried != 0
    assert second[0] == controller.entrant_specs[0].processes[carried].process_id
    assert first != second


@pytest.mark.parametrize(
    "order", [("p1", "p2", "p3"), ("p3", "p2", "p1"), ("p2", "p3", "p1")]
)
def test_declaration_permutation_no_longer_changes_how_much_each_process_acts(
    order: tuple[str, ...],
) -> None:
    """The Phase 4 Section G finding, closed.

    Under alpha1 a permuted declaration list changes which process absorbs
    freed mid-tick quota. Under alpha2 every permutation of the same shares
    gives every process the same number of slots; only the phase of the
    rotation moves, which no agent can exploit as a priority ranking.
    """

    shares = {"p1": 3, "p2": 3, "p3": 2}
    permuted = {pid: shares[pid] for pid in order}
    result = _drive_one_tick(
        _controller(RULESET_V4_ALPHA2, permuted), disrupt_after={2: {"p2"}}
    )
    counts = {pid: result.count(pid) for pid in shares}
    assert sum(counts.values()) == QUOTA
    assert counts["p2"] <= 1
    # p1 and p3 split the redistributed quota evenly rather than the
    # earliest-declared one taking all of it.
    assert abs(counts["p1"] - counts["p3"]) <= 1


# ---------------------------------------------------------------------------
# End to end: the entrant-level scheduler and alpha1's sequence are untouched
# ---------------------------------------------------------------------------


def _record_match(policy) -> list[tuple[int, str]]:
    """Run a real match and return seat A's (tick, process_id) call order."""

    calls: list[tuple[int, str]] = []

    def logic(observation: ObservationV2, _state: dict[str, Any]) -> AgentAction:
        calls.append((observation.current_tick, observation.self_process_id))
        return AgentAction(ActionKindV2.MOVE, 0)

    processes = [
        ProcessInstance(pid, ProcessRole.GENERALIST, 0, 8, share, logic)
        for pid, share in (("p1", 3), ("p2", 3), ("p3", 2))
    ]
    controller = ProcessMatchController(
        Config(arena_size=ARENA, instr_per_tick=QUOTA, seed=5),
        [
            ProcessEntrantSpec("A", "A", processes, start=0),
            _entrant("B", {"solo": QUOTA}, start=ARENA // 2),
        ],
        max_ticks=3,
        ruleset_policy=policy,
    )
    controller.run()
    return calls


def test_alpha1_end_to_end_process_call_order_is_unchanged() -> None:
    """The alpha1 firewall at match level: its per-tick sequence is frozen."""

    calls = _record_match(RULESET_V4_ALPHA1)
    per_tick = [pid for tick, pid in calls if tick == 1]
    assert per_tick == ["p1", "p1", "p1", "p2", "p2", "p2", "p3", "p3"]


def test_alpha2_end_to_end_rotates_and_still_spends_the_full_quota() -> None:
    calls = _record_match(RULESET_V4_ALPHA2)
    for tick in (1, 2, 3):
        per_tick = [pid for t, pid in calls if t == tick]
        assert len(per_tick) == QUOTA
        assert sorted(per_tick) == sorted(["p1"] * 3 + ["p2"] * 3 + ["p3"] * 2)
    tick_one = [pid for t, pid in calls if t == 1]
    assert tick_one != ["p1", "p1", "p1", "p2", "p2", "p2", "p3", "p3"]


def test_both_rulesets_remain_bit_for_bit_deterministic() -> None:
    for policy in (RULESET_V4_ALPHA1, RULESET_V4_ALPHA2):
        assert _record_match(policy) == _record_match(policy)


def test_the_entrant_level_k2_rotating_scheduler_is_shared_unchanged() -> None:
    """Alpha2 changes selection *within* an entrant only.

    Both v4 alphas must keep the identical K=2 chunked, rotating-start
    entrant scheduler; a divergence here would be a second, unmeasured
    gameplay change riding along with the intended one.
    """

    assert (
        RULESET_V4_ALPHA1.scheduler_mode,
        RULESET_V4_ALPHA1.scheduler_chunk_size,
        RULESET_V4_ALPHA1.scheduler_rotate_start,
    ) == (
        RULESET_V4_ALPHA2.scheduler_mode,
        RULESET_V4_ALPHA2.scheduler_chunk_size,
        RULESET_V4_ALPHA2.scheduler_rotate_start,
    )
