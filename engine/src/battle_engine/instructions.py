"""BATTLE VM instruction definitions and bytecode encoding."""

from __future__ import annotations

NOP, MOV, ADD, LOAD, STORE, JMP, JZ, HALT = range(8)
MOVP, ADDP, LOADI, STOREI = 8, 9, 10, 11


def enc(op: int, imm: int | None = None) -> bytes:
    """Encode one opcode and its optional 32-bit little-endian immediate."""
    if imm is None:
        return bytes([op])
    v = imm & 0xFFFFFFFF
    return bytes([op, v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])
