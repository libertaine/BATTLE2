"""Authoritative incremental VM ownership-count invariants."""

from __future__ import annotations

from collections import Counter

from battle_engine.agent_api import ActionKind, AgentAction
from battle_engine.instructions import NOP
from battle_engine.python_runtime import PythonEntrantState, apply_action
from battle_engine.vm import VM


def _recomputed(vm: VM) -> dict[str, int]:
    return dict(Counter(owner for owner in vm.writer if owner is not None))


def _assert_consistent(vm: VM) -> None:
    assert vm.ownership_counts == _recomputed(vm)
    assert sum(vm.ownership_counts.values()) == sum(owner is not None for owner in vm.writer)


def test_wrapped_writes_overwrites_same_owner_and_unowned_transitions():
    vm = VM(4)
    assert vm.ownership_counts == {}

    vm._wr8(4, 1, "A")
    _assert_consistent(vm)
    assert vm.ownership_counts == {"A": 1}

    vm._wr8(0, 2, "A")
    _assert_consistent(vm)
    assert vm.ownership_counts == {"A": 1}

    vm._wr8(-4, 3, "B")
    _assert_consistent(vm)
    assert vm.ownership_counts == {"B": 1}

    vm._wr8(0, 4, None)
    _assert_consistent(vm)
    assert vm.ownership_counts == {}


def test_wrapped_and_overlapping_code_loads_keep_counts_exact():
    vm = VM(5)
    vm.load_code(3, bytes((1, 2, 3, 4)), "A")
    _assert_consistent(vm)
    assert vm.ownership_counts == {"A": 4}

    vm.load_code(0, bytes((8, 9, 10)), "B")
    _assert_consistent(vm)
    assert vm.ownership_counts == {"A": 2, "B": 3}

    vm.load_code(4, bytes((NOP,) * 7), "C")
    _assert_consistent(vm)
    assert vm.ownership_counts == {"C": 5}


def test_every_mutation_in_sequence_matches_full_recomputation():
    vm = VM(17)
    operations = [
        (-1, "A"),
        (0, "A"),
        (17, "B"),
        (34, "B"),
        (5, "C"),
        (5, "C"),
        (16, None),
        (22, "A"),
        (-12, "B"),
    ]
    for value, (address, owner) in enumerate(operations):
        vm._wr8(address, value, owner)
        _assert_consistent(vm)


def test_python_agent_api_write_uses_the_same_authoritative_boundary():
    vm = VM(8)
    state = PythonEntrantState("A", "Alpha", loaded=None, rng=None)  # type: ignore[arg-type]
    apply_action(AgentAction(ActionKind.WRITE, -1, 0xAB), state, vm)
    _assert_consistent(vm)
    assert vm.writer[7] == "A"
    assert vm.ownership_counts == {"A": 1}
