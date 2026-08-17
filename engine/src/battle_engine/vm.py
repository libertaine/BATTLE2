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
        # Authoritative aggregate of ``writer``. Every ownership mutation,
        # including wrapped/overlapping initial loads and Python Agent API
        # writes, converges through ``_wr8`` and updates this map in O(1).
        self.ownership_counts: dict[str, int] = {}
        # (start_address, length, owner, values) -- ``values`` holds the
        # actual byte written at each address in the run, in order, so a
        # replay consumer can reconstruct arena content, not just ownership.
        self.tick_diffs: list[tuple[int, int, str | None, list[int]]] = []

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
        byte_value = val & 0xFF
        previous_owner = self.writer[i]
        if previous_owner != owner:
            if previous_owner is not None:
                previous_count = self.ownership_counts[previous_owner] - 1
                if previous_count:
                    self.ownership_counts[previous_owner] = previous_count
                else:
                    del self.ownership_counts[previous_owner]
            if owner is not None:
                self.ownership_counts[owner] = self.ownership_counts.get(owner, 0) + 1
        self.arena[i] = byte_value
        self.writer[i] = owner
        if (
            self.tick_diffs
            and self.tick_diffs[-1][0] + self.tick_diffs[-1][1] == i
            and self.tick_diffs[-1][2] == owner
        ):
            a, length, previous_owner, values = self.tick_diffs[-1]
            values.append(byte_value)
            self.tick_diffs[-1] = (a, length + 1, previous_owner, values)
        else:
            self.tick_diffs.append((i, 1, owner, [byte_value]))

    def load_code(
        self, start: int, code: bytes, owner: str | None
    ) -> tuple[int, int]:
        """Place initial agent bytecode, recorded as ordinary write diffs.

        Routing through ``_wr8`` (rather than writing ``self.arena``
        directly) means initial code placement appears in ``tick_diffs``
        exactly like any other write, so a caller that publishes those
        diffs as a tick-zero replay record can reconstruct starting arena
        content without a separate snapshot mechanism.
        """
        m = len(self.arena)
        s = start % m
        for i, byte in enumerate(code):
            self._wr8(s + i, byte, owner)
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
