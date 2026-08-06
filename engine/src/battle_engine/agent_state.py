"""Mutable runtime state for an agent executing in the BATTLE VM."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Agent:
    agent_id: str
    pc: int
    alive: bool = True
    regs: dict[str, int] = field(default_factory=lambda: {"A": 0, "Z": 0, "P": 0})
    cpu_used: int = 0
    mem_writes: int = 0
    region: tuple[int, int] = (0, 0)
