#!/usr/bin/env python3
"""
asm_assembler.py
Assemble .asm -> raw bytecode blob for the BATTLE VM (Milestone-5 ISA).

Supports immediates that are:
  - plain decimal: 123
  - hex: 0x7b
  - negative hex: -0x7b
  - label: mylabel
  - label+const or label-const (e.g. start+128, start-4)

Also strips comments that start with '#' or ';'.

Usage:
  python asm_assembler.py input.asm -o agent.bin --entry 128
"""
from __future__ import annotations
import argparse, re, sys
from typing import List, Dict, Tuple

# opcode map matches core.py values
OPMAP = {
    "NOP": 0,
    "MOV": 1,
    "ADD": 2,
    "LOAD": 3,
    "STORE": 4,
    "JMP": 5,
    "JZ": 6,
    "HALT": 7,
    "MOVP": 8,
    "ADDP": 9,
    "LOADI": 10,
    "STOREI": 11,
}
IMM_OPS = {
    "MOV",
    "ADD",
    "LOAD",
    "STORE",
    "JMP",
    "JZ",
    "MOVP",
    "ADDP",
}  # opcodes that take imm32

_label_re = re.compile(r"^\s*([A-Za-z_]\w*):")
# _inst_re tolerates trailing comments; we also strip comments earlier
_inst_re = re.compile(r"^\s*([A-Za-z]+)(?:\s+(.+?))?\s*(?:[#;].*)?$")


def parse_lines(lines: List[str]) -> Tuple[List[Tuple[str, str, int]], Dict[str, int]]:
    """
    First pass: parse and collect labels and instruction footprint.
    Returns list of tuples (op, arg_string, offset_for_inst) and labels->offset.
    """
    cleaned: List[Tuple[str, str, int]] = []
    labels: Dict[str, int] = {}
    offset = 0
    for raw in lines:
        # strip both '#' and ';' comments
        no_hash = raw.split("#", 1)[0]
        line = no_hash.split(";", 1)[0].strip()
        if not line:
            continue
        # label?
        m = _label_re.match(line)
        if m:
            lab = m.group(1)
            if lab in labels:
                raise SyntaxError(f"duplicate label {lab}")
            labels[lab] = offset
            line = line[m.end() :].strip()
            if not line:
                continue
        m = _inst_re.match(line)
        if not m:
            raise SyntaxError(f"bad line: {raw!r}")
        op = m.group(1).upper()
        arg = (m.group(2) or "").strip()
        if op not in OPMAP:
            raise SyntaxError(f"unknown opcode {op} on line: {raw!r}")
        cleaned.append((op, arg, offset))
        offset += 5 if op in IMM_OPS else 1
    return cleaned, labels


def parse_number(tok: str) -> int:
    """
    Parse decimal, hex, or negative hex (e.g., -0xC1).
    """
    tok = tok.strip()
    if not tok:
        raise ValueError("empty numeric token")
    neg = tok.startswith("-")
    core = tok[1:] if neg else tok
    if core.lower().startswith("0x"):
        val = int(core, 16)
    else:
        val = int(core, 10)
    return -val if neg else val


def encode_operand(tok: str, labels: Dict[str, int]) -> int:
    """
    Evaluate token that can be:
      - numeric (dec/hex, incl. negatives like -0xC1)
      - label
      - label+const or label-const
      - expression with a single +/- (no parentheses)
    """
    if not tok:
        raise ValueError("expected immediate or label")
    tok = tok.strip()

    # quick numeric (handles -0x.., 0x.., -NNN, +NNN, NNN)
    if tok[0] in "+-" and tok[1:].lower().startswith("0x"):
        return parse_number(tok)
    if tok.lower().startswith("0x") or tok.lstrip("+-").isdigit():
        return parse_number(tok)

    # handle single +/- operator (label+123 or 123+label or label-0x10)
    # avoid treating a leading 0x... as an expression
    for op in ("+", "-"):
        if op in tok and not tok.lower().startswith("0x"):
            left, right = (part.strip() for part in tok.split(op, 1))

            def eval_part(p: str) -> int:
                if not p:
                    raise ValueError(f"empty operand in expression '{tok}'")
                if p.lower().startswith("0x") or p.lstrip("+-").isdigit():
                    return parse_number(p)
                if p in labels:
                    return labels[p]
                raise ValueError(f"unknown symbol '{p}' in expression '{tok}'")

            lv = eval_part(left)
            rv = eval_part(right)
            return (lv + rv) if op == "+" else (lv - rv)

    # single token: label or numeric
    if tok in labels:
        return labels[tok]
    if tok.lower().startswith("0x") or tok.lstrip("+-").isdigit():
        return parse_number(tok)

    raise ValueError(f"unknown immediate or label: {tok}")


def assemble(cleaned: List[Tuple[str, str, int]], labels: Dict[str, int]) -> bytes:
    out = bytearray()
    for op, arg, off in cleaned:
        opcode = OPMAP[op]
        out.append(opcode)
        if op in IMM_OPS:
            if not arg:
                raise ValueError(f"{op} requires immediate (at offset {off})")
            val = encode_operand(arg, labels) & 0xFFFFFFFF
            out += bytes(
                [val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >> 24) & 0xFF]
            )
    return bytes(out)


def main(argv=None):
    p = argparse.ArgumentParser(prog="asm_assembler.py")
    p.add_argument("src", help="source .asm file")
    p.add_argument("-o", "--out", default="agent.bin", help="output blob")
    p.add_argument(
        "--entry", type=int, default=128, help="declared entry (informational)"
    )
    p.add_argument("--max-size", type=int, default=16 * 1024, help="max blob size")
    args = p.parse_args(argv)

    with open(args.src, "r", encoding="utf-8") as f:
        lines = f.readlines()

    cleaned, labels = parse_lines(lines)
    blob = assemble(cleaned, labels)

    if len(blob) > args.max_size:
        print(f"ERROR: blob {len(blob)} bytes > max {args.max_size}", file=sys.stderr)
        sys.exit(2)

    with open(args.out, "wb") as fo:
        fo.write(blob)

    print(f"WROTE {args.out} {len(blob)} bytes; entry={args.entry}; labels={labels}")


if __name__ == "__main__":
    main()
