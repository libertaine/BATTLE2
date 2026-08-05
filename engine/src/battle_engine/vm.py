"""Circular byte-addressed virtual machine extracted from the v0.1 core."""

from __future__ import annotations

from battle_engine.agent_state import Agent
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
)


class VM:
    def __init__(self, arena_size: int):
        self.arena = bytearray([NOP] * arena_size)
        self.writer: list[str | None] = [None] * arena_size
        self.tick_diffs: list[tuple[int, int, str | None]] = []

    def clear_tick_diffs(self) -> None:
        self.tick_diffs.clear()

    def _rd32(self, pos: int) -> int:
        m = len(self.arena)
        p = pos % m
        return (
            self.arena[p]
            | (self.arena[(p + 1) % m] << 8)
            | (self.arena[(p + 2) % m] << 16)
            | (self.arena[(p + 3) % m] << 24)
        )

    def _wr8(self, pos: int, val: int, owner: str | None) -> None:
        m = len(self.arena)
        i = pos % m
        self.arena[i] = val & 0xFF
        self.writer[i] = owner
        if (
            self.tick_diffs
            and self.tick_diffs[-1][0] + self.tick_diffs[-1][1] == i
            and self.tick_diffs[-1][2] == owner
        ):
            a, length, previous_owner = self.tick_diffs[-1]
            self.tick_diffs[-1] = (a, length + 1, previous_owner)
        else:
            self.tick_diffs.append((i, 1, owner))

    def load_code(
        self, start: int, code: bytes, owner: str | None
    ) -> tuple[int, int]:
        m = len(self.arena)
        s = start % m
        for i, byte in enumerate(code):
            self.arena[(s + i) % m] = byte
            self.writer[(s + i) % m] = owner
        e = (s + max(1, len(code)) - 1) % m
        return s, e

    def step(self, agent: Agent) -> None:
        if not agent.alive:
            return
        m = len(self.arena)
        ip = agent.pc % m
        op = self.arena[ip]
        rd32 = self._rd32
        registers = agent.regs
        if op == NOP:
            agent.pc = (ip + 1) % m
        elif op == HALT:
            agent.alive = False
        elif op == MOV:
            registers["A"] = rd32(ip + 1) & 0xFFFFFFFF
            agent.pc = (ip + 5) % m
        elif op == ADD:
            registers["A"] = (
                registers["A"] + (rd32(ip + 1) & 0xFFFFFFFF)
            ) & 0xFFFFFFFF
            registers["Z"] = 1 if registers["A"] == 0 else 0
            agent.pc = (ip + 5) % m
        elif op == LOAD:
            addr = rd32(ip + 1) % m
            registers["A"] = self.arena[addr]
            registers["Z"] = 1 if registers["A"] == 0 else 0
            agent.pc = (ip + 5) % m
        elif op == STORE:
            addr = rd32(ip + 1) % m
            self._wr8(addr, registers["A"], owner=agent.agent_id)
            agent.mem_writes += 1
            agent.pc = (ip + 5) % m
        elif op == JMP:
            agent.pc = rd32(ip + 1) % m
        elif op == JZ:
            addr = rd32(ip + 1) % m
            agent.pc = addr if registers.get("Z", 0) == 1 else (ip + 5) % m
        elif op == MOVP:
            registers["P"] = rd32(ip + 1) & 0xFFFFFFFF
            agent.pc = (ip + 5) % m
        elif op == ADDP:
            registers["P"] = (
                registers["P"] + (rd32(ip + 1) & 0xFFFFFFFF)
            ) & 0xFFFFFFFF
            agent.pc = (ip + 5) % m
        elif op == LOADI:
            addr = registers["P"] % m
            registers["A"] = self.arena[addr]
            registers["Z"] = 1 if registers["A"] == 0 else 0
            agent.pc = (ip + 1) % m
        elif op == STOREI:
            addr = registers["P"] % m
            self._wr8(addr, registers["A"], owner=agent.agent_id)
            agent.mem_writes += 1
            agent.pc = (ip + 1) % m
        else:
            agent.alive = False
