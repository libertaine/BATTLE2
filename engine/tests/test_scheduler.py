"""Direct unit tests for the shared ``scheduler.run_sequential_quota`` abstraction.

These pin the scheduler's own contract in isolation, independent of any
runtime (VM/Python/supervised) that consumes it -- the runtime-integration
characterization tests (``test_scheduler_characterization.py``,
``test_python_scheduler_characterization.py``) cover the same semantics
through each real call site.
"""

from __future__ import annotations

from dataclasses import dataclass

from battle_engine.scheduler import run_sequential_quota


@dataclass
class _FakeState:
    name: str
    alive: bool = True


def test_sequential_ordering_full_quota() -> None:
    states = [_FakeState("A"), _FakeState("B"), _FakeState("C")]
    calls: list[str] = []

    run_sequential_quota(states, 3, lambda state, slot: calls.append(state.name))

    assert calls == ["A", "A", "A", "B", "B", "B", "C", "C", "C"]


def test_initial_dead_state_is_skipped_entirely() -> None:
    states = [_FakeState("A"), _FakeState("B", alive=False), _FakeState("C")]
    calls: list[str] = []

    run_sequential_quota(states, 3, lambda state, slot: calls.append(state.name))

    assert calls == ["A", "A", "A", "C", "C", "C"]


def test_mid_quota_death_stops_that_states_remaining_slots() -> None:
    states = [_FakeState("A"), _FakeState("B"), _FakeState("C")]
    calls: list[str] = []

    def execute(state: _FakeState, slot: int) -> None:
        calls.append(f"{state.name}{slot}")
        if state.name == "B" and slot == 1:
            state.alive = False

    run_sequential_quota(states, 3, execute)

    assert calls == ["A0", "A1", "A2", "B0", "B1", "C0", "C1", "C2"]


def test_earlier_death_does_not_suppress_later_states() -> None:
    states = [_FakeState("A"), _FakeState("B"), _FakeState("C")]
    calls: list[str] = []

    def execute(state: _FakeState, slot: int) -> None:
        calls.append(state.name)
        if state.name == "A":
            state.alive = False

    run_sequential_quota(states, 3, execute)

    assert calls == ["A", "B", "B", "B", "C", "C", "C"]


def test_quota_one_executes_each_state_once_in_order() -> None:
    states = [_FakeState("A"), _FakeState("B"), _FakeState("C")]
    calls: list[str] = []

    run_sequential_quota(states, 1, lambda state, slot: calls.append(state.name))

    assert calls == ["A", "B", "C"]


def test_non_default_quota_of_five() -> None:
    states = [_FakeState("A"), _FakeState("B")]
    calls: list[str] = []

    run_sequential_quota(states, 5, lambda state, slot: calls.append(state.name))

    assert calls == ["A"] * 5 + ["B"] * 5


def test_slot_index_is_passed_to_the_callback() -> None:
    states = [_FakeState("A"), _FakeState("B")]
    slots: list[int] = []

    run_sequential_quota(states, 3, lambda state, slot: slots.append(slot))

    assert slots == [0, 1, 2, 0, 1, 2]


def test_zero_quota_iterates_states_but_executes_no_slots() -> None:
    states = [_FakeState("A"), _FakeState("B")]
    calls: list[str] = []

    run_sequential_quota(states, 0, lambda state, slot: calls.append(state.name))

    assert calls == []
