from __future__ import annotations

from battle_engine.agent_state import Agent
from battle_engine.builtins.registry import (
    assemble_bomber,
    assemble_flooder,
    assemble_runner,
    assemble_seeker,
    assemble_spiral,
    assemble_writer,
)
from battle_engine.vm import VM


def _step(vm: VM, agent: Agent, count: int) -> None:
    for _ in range(count):
        vm.step(agent)


def test_seeker_branches_to_scan_loop_and_attack_instructions():
    vm = VM(256)
    vm.load_code(0, assemble_seeker(0, ptr_start=200, byte_val=0xFE), "A")
    agent = Agent("A", 0)

    pcs = []
    for _ in range(6):
        vm.step(agent)
        pcs.append(agent.pc)

    assert pcs == [5, 6, 11, 26, 31, 32]
    assert agent.alive
    assert agent.mem_writes == 1
    assert vm.arena[200] == 0xFE


def test_seeker_nonmatch_path_stays_on_instruction_boundaries():
    vm = VM(256)
    vm.load_code(0, assemble_seeker(0, ptr_start=200, target_byte=0xAA), "A")
    agent = Agent("A", 0)
    instruction_boundaries = {0, 5, 6, 11, 16, 21, 26, 31, 32, 37}

    for _ in range(16):
        vm.step(agent)
        assert agent.pc in instruction_boundaries
        assert agent.alive

    assert agent.regs["P"] == 203
    assert agent.mem_writes == 0


def test_flooder_default_write_cadence_after_setup():
    vm = VM(512)
    vm.load_code(0, assemble_flooder(0, ptr=300), "A")
    agent = Agent("A", 0)

    _step(vm, agent, 2)
    assert agent.mem_writes == 0
    _step(vm, agent, 8)
    assert agent.mem_writes == 4
    _step(vm, agent, 8)
    assert agent.mem_writes == 8
    assert agent.regs["P"] == 308


def test_spiral_uses_fixed_pointer_step_and_two_writes_per_loop():
    vm = VM(512)
    vm.load_code(0, assemble_spiral(0, ptr=300, step=7, delta=3, byte_val=0xA5), "A")
    agent = Agent("A", 0)

    _step(vm, agent, 3 + 18)

    assert agent.mem_writes == 4
    assert agent.regs["P"] == 314
    assert vm.arena[300] == 0xA5
    assert vm.arena[307] == 0xA5


def test_runner_never_writes_and_remains_in_its_loop():
    vm = VM(128)
    vm.load_code(0, assemble_runner(0), "A")
    agent = Agent("A", 0)

    _step(vm, agent, 20)

    assert agent.alive
    assert agent.mem_writes == 0
    assert agent.pc in {1, 6, 11}


def test_writer_repeats_one_direct_write_every_three_instructions():
    vm = VM(128)
    vm.load_code(0, assemble_writer(0, offset=96, byte_val=0x7E), "A")
    agent = Agent("A", 0)

    _step(vm, agent, 6)

    assert agent.mem_writes == 2
    assert vm.arena[96] == 0x7E
    assert agent.pc == 0


def test_bomber_advances_through_fixed_stride_targets():
    vm = VM(256)
    vm.load_code(0, assemble_bomber(0, ptr=128, stride=17, byte_val=0xCC), "A")
    agent = Agent("A", 0)

    _step(vm, agent, 8)

    assert agent.mem_writes == 2
    assert vm.arena[128] == 0xCC
    assert vm.arena[145] == 0xCC
    assert agent.regs["P"] == 162
