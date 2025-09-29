# agents.py — expanded agent library (flooder, spiral, seeker)
from typing import Tuple
from core import enc, NOP, MOV, ADD, LOAD, STORE, JMP, JZ, MOVP, ADDP, LOADI, STOREI

SUPPORTED = ("runner", "writer", "bomber", "flooder", "spiral", "seeker")


def assemble_runner(start: int) -> bytes:
    return b"".join([enc(NOP), enc(ADD, 1), enc(JZ, start), enc(JMP, start + 1)])


def assemble_writer(start: int, offset: int = 128, byte_val: int = 0x41) -> bytes:
    return b"".join([enc(MOV, byte_val), enc(STORE, start + offset), enc(JMP, start)])


def assemble_bomber(
    start: int, ptr: int, stride: int = 64, byte_val: int = 0x99
) -> bytes:
    loop = start + 10
    return b"".join(
        [
            enc(MOV, byte_val),
            enc(MOVP, ptr),
            enc(STOREI),
            enc(ADDP, stride),
            enc(JMP, loop),
        ]
    )


def assemble_flooder(
    start: int, ptr: int, byte_val: int = 0x00, writes_per_loop: int = 8
) -> bytes:
    """
    Flooder: unrolled STOREI operations to produce multiple writes per loop.
    With INSTR_PER_TICK=8, writes_per_loop=8 ≈ up to ~8 writes/tick (subject to scheduling).
    """
    seq = [enc(MOV, byte_val), enc(MOVP, ptr)]
    for _ in range(max(1, writes_per_loop)):
        seq += [enc(STOREI), enc(ADDP, 1)]
    seq.append(enc(JMP, start + 10))  # jump to first STOREI
    return b"".join(seq)


def assemble_spiral(
    start: int, ptr: int, step: int = 7, delta: int = 3, byte_val: int = 0xA5
) -> bytes:
    """
    Spiral: stride grows over time → broad coverage without revisiting too soon.
    A register holds 'step'; ADD updates step; ADDP uses current step.
    """
    loop = start + 15  # after MOV/MOVP/MOV step
    return b"".join(
        [
            enc(MOV, byte_val),  # A = byte
            enc(MOVP, ptr),  # P = ptr
            enc(ADD, step),  # A = step (repurpose A temporarily)
            # loop:
            enc(STOREI),  # write byte_val? Wait: we overwrote A with step.
            # So reload byte for store:
            enc(MOV, byte_val),  # A = byte again
            enc(STOREI),  # store byte at P
            enc(ADD, step),  # A = byte + step (we'll overwrite next)
            enc(ADDP, step),  # P += step
            enc(MOV, step),  # A = step (reset A to step)
            enc(ADD, delta),  # step += delta (A := step+delta)
            enc(ADD, 0),  # update Z correctly (no-op for flag consistency)
            enc(JMP, loop),  # repeat
        ]
    )


def assemble_seeker(
    start: int,
    ptr_start: int,
    target_byte: int = 0x00,
    attack_stride: int = 17,
    byte_val: int = 0xFF,
) -> bytes:
    """
    Seeker: scan from ptr_start for a target byte; when found, write 'byte_val' and hop by attack_stride.
    Uses: LOADI; compare by ADD (-target); JZ found; else ADDP 1 and continue.
    """
    lbl_loop = start + 10
    lbl_found = lbl_loop + 10
    return b"".join(
        [
            enc(MOVP, ptr_start),  # set scan pointer
            # loop:
            enc(LOADI),  # A = [P]
            enc(ADD, (-target_byte) & 0xFFFFFFFF),  # A -= target ; Z=1 if match
            enc(JZ, lbl_found),  # if match -> found
            enc(ADDP, 1),  # P++
            enc(JMP, lbl_loop),  # continue
            # found:
            enc(MOV, byte_val),  # A = attack byte
            enc(STOREI),  # [P] = A
            enc(ADDP, attack_stride),  # jump ahead to spread damage
            enc(JMP, lbl_loop),  # continue scanning
        ]
    )


def build_agent(agent_type: str, start: int, **kwargs) -> bytes:
    t = agent_type.lower()
    if t == "runner":
        return assemble_runner(start)
    if t == "writer":
        return assemble_writer(
            start,
            offset=int(kwargs.get("offset", 128)),
            byte_val=int(kwargs.get("byte", 0x41)),
        )
    if t == "bomber":
        return assemble_bomber(
            start,
            ptr=int(kwargs.get("ptr", start + 256)),
            stride=int(kwargs.get("stride", 64)),
            byte_val=int(kwargs.get("byte", 0x99)),
        )
    if t == "flooder":
        return assemble_flooder(
            start,
            ptr=int(kwargs.get("ptr", start + 256)),
            byte_val=int(kwargs.get("byte", 0x00)),
            writes_per_loop=int(kwargs.get("writes", 8)),
        )
    if t == "spiral":
        return assemble_spiral(
            start,
            ptr=int(kwargs.get("ptr", start + 256)),
            step=int(kwargs.get("step", 7)),
            delta=int(kwargs.get("delta", 3)),
            byte_val=int(kwargs.get("byte", 0xA5)),
        )
    if t == "seeker":
        return assemble_seeker(
            start,
            ptr_start=int(kwargs.get("ptr", start + 256)),
            target_byte=int(kwargs.get("target", 0x00)),
            attack_stride=int(kwargs.get("stride", 17)),
            byte_val=int(kwargs.get("byte", 0xFF)),
        )
    raise ValueError(f"unknown agent type: {agent_type}")
