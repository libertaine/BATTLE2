from __future__ import annotations

import pytest
from battle_engine import core
from battle_engine.agent_state import Agent
from battle_engine.config import Config, Weights
from battle_engine.instructions import (
    ADD,
    ADDP,
    HALT,
    JMP,
    JZ,
    LOAD,
    LOADI,
    MOV,
    MOVP,
    NOP,
    STORE,
    STOREI,
    enc,
)
from battle_engine.vm import VM


def test_core_reexports_extracted_objects_by_identity():
    assert core.Config is Config
    assert core.Weights is Weights
    assert core.Agent is Agent
    assert core.VM is VM
    assert core.enc is enc
    for name, value in {
        "NOP": NOP,
        "MOV": MOV,
        "ADD": ADD,
        "LOAD": LOAD,
        "STORE": STORE,
        "JMP": JMP,
        "JZ": JZ,
        "HALT": HALT,
        "MOVP": MOVP,
        "ADDP": ADDP,
        "LOADI": LOADI,
        "STOREI": STOREI,
    }.items():
        assert getattr(core, name) == value


def test_configuration_defaults_and_from_dict_are_preserved():
    assert Config() == Config(
        arena_size=4096,
        instr_per_tick=8,
        seed=1337,
        win_mode="score_fallback",
        weights=Weights(1.0, 5.0, 1.0, 64),
    )
    assert Config.from_dict(
        {
            "arena_size": "32",
            "instr_per_tick": "3",
            "seed": "9",
            "win_mode": "survival",
            "weights": {
                "alive": "2.5",
                "kill": "7",
                "territory": "0.5",
                "territory_bucket": "4",
            },
        }
    ) == Config(32, 3, 9, "survival", Weights(2.5, 7.0, 0.5, 4))


@pytest.mark.parametrize(
    ("opcode", "expected"),
    [
        (NOP, b"\x00"),
        (HALT, b"\x07"),
        (STOREI, b"\x0b"),
    ],
)
def test_opcode_values_and_single_byte_encoding(opcode, expected):
    assert enc(opcode) == expected


def test_immediate_encoding_is_32_bit_little_endian_with_wrapping():
    assert enc(MOV, 0x12345678) == b"\x01\x78\x56\x34\x12"
    assert enc(ADD, -1) == b"\x02\xff\xff\xff\xff"
    assert enc(JMP, 0x1_0000_0001) == b"\x05\x01\x00\x00\x00"


def test_vm_code_loading_wraps_and_preserves_ownership():
    vm = VM(4)
    assert vm.load_code(3, b"\x01\x02\x03", "A") == (3, 1)
    assert bytes(vm.arena) == b"\x02\x03\x00\x01"
    assert vm.writer == ["A", "A", None, "A"]


def test_vm_groups_adjacent_writes_by_owner_only():
    vm = VM(8)
    vm._wr8(1, 0xAA, "A")
    vm._wr8(2, 0xBB, "A")
    vm._wr8(3, 0xCC, "B")
    assert vm.tick_diffs == [(1, 2, "A", [0xAA, 0xBB]), (3, 1, "B", [0xCC])]
    assert bytes(vm.arena[1:4]) == b"\xaa\xbb\xcc"


def test_halt_and_invalid_opcode_leave_pc_and_stop_agent():
    halt_vm = VM(8)
    halt_vm.arena[2] = HALT
    halted = Agent("A", 2)
    halt_vm.step(halted)
    assert not halted.alive
    assert halted.pc == 2

    invalid_vm = VM(8)
    invalid_vm.arena[3] = 0xFF
    invalid = Agent("B", 3)
    invalid_vm.step(invalid)
    assert not invalid.alive
    assert invalid.pc == 3


def test_indirect_register_and_memory_behavior_is_preserved():
    vm = VM(32)
    vm.load_code(
        0,
        b"".join([enc(MOV, 0x1FF), enc(MOVP, 31), enc(STOREI), enc(ADDP, 2), enc(LOADI)]),
        "A",
    )
    agent = Agent("A", 0)
    for _ in range(5):
        vm.step(agent)
    assert vm.arena[31] == 0xFF
    assert vm.writer[31] == "A"
    assert agent.regs == {"A": 0xFF, "Z": 0, "P": 33}
    assert agent.mem_writes == 1
