"""v3 Research Closeout -- one-block-capture theoretical boundary (Sec 11
of the governing task).

Tests a Ruleset-*capability* question, not a claim about what any real
Agent API v1 entrant can currently discover: can a perfectly informed
attacker -- one that already knows a victim's core addresses, which this
probe is allowed to hard-code because it is testing what the scheduler
and capture rule permit, not what a real agent can learn through
``READ`` -- capture an earlier-scheduled victim within its own single
per-tick action block, at ``instr_per_tick = CORE_SIZE`` (8, the shipped
default) versus ``instr_per_tick = CORE_SIZE - 1`` (7)?

This uses the two real, unmodified engine primitives the theorem in the
closeout report's Sec 8 depends on -- ``battle_engine.scheduler.
run_sequential_quota`` (the actual per-tick scheduling shape) and
``battle_engine.vm.VM._wr8`` (the actual, sole ownership-mutation path,
identical to what every runtime action ultimately calls) -- rather than a
reimplementation or a full match execution. Capture is evaluated with the
identical rule ``apply_core_capture`` uses: a victim is captured
if-and-only-if it owns zero of its own ``CORE_SIZE`` addresses after the
tick's actions have run. No scoring, statistics, or replay machinery is
exercised, because none of it bears on this specific question.

Never added to any benchmark. Disposable, deterministic, and reproducible
by re-running this module directly.

Usage::

    python tools/v3_closeout_capture_boundary.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.python_runtime import CORE_SIZE, core_addresses
from battle_engine.scheduler import run_sequential_quota
from battle_engine.vm import VM


def one_block_capture_probe(*, budget: int, arena_size: int = 4096) -> dict[str, Any]:
    """Can attacker 'A', scheduled after victim 'V', zero V's core-owned
    count within its own single per-tick action block of size ``budget``?

    V is scheduled first (mirrors the closeout theorem's "victim scheduled
    before that attacker") and takes no action touching its own core this
    tick -- modelling the theorem's claim precisely: the Ruleset provides
    no *guaranteed* response window, so the probe does not grant V one.
    A is "perfectly informed": it already holds V's core addresses (not
    discovered via any Agent API v1 action) and spends its own block
    writing them in address order, capped at ``budget`` writes.
    """

    vm = VM(arena_size)
    victim_core_start = 0
    attacker_core_start = 1000  # arbitrary, disjoint from the victim's window
    victim_addrs = core_addresses(victim_core_start, arena_size)
    attacker_addrs = core_addresses(attacker_core_start, arena_size)

    # Seed initial ownership exactly as `seed_core_ownership` does (routed
    # through the same `VM._wr8` ownership-mutation path; content value 0
    # matches that function's own `CORE_SEED_BYTE_ALPHA1` default).
    for address in victim_addrs:
        vm._wr8(address, 0, "V")
    for address in attacker_addrs:
        vm._wr8(address, 0, "A")

    victim_state = types.SimpleNamespace(agent_id="V", alive=True)
    attacker_state = types.SimpleNamespace(agent_id="A", alive=True)

    def victim_slot(_state: Any, _slot: int) -> None:
        # V's own action block completes -- untouched by this probe --
        # entirely before A's block begins, per sequential-quota order.
        return

    attacker_targets = list(victim_addrs)

    def attacker_slot(_state: Any, slot: int) -> None:
        if slot < len(attacker_targets):
            vm._wr8(attacker_targets[slot], 0xFF, "A")

    # One tick: V's full block, then A's full block -- the exact shape
    # `PythonRuntimeController.run`'s per-tick loop drives via the same
    # `run_sequential_quota` call, restricted to the two seats in play.
    run_sequential_quota([victim_state], budget, victim_slot)
    run_sequential_quota([attacker_state], budget, attacker_slot)

    owned_now = sum(1 for address in victim_addrs if vm.writer[address] == "V")
    captured = owned_now == 0
    return {
        "budget": budget,
        "core_size": CORE_SIZE,
        "victim_owned_after_attacker_block": owned_now,
        "captured": captured,
    }


def main() -> int:
    print(f"CORE_SIZE = {CORE_SIZE}\n")
    results = [one_block_capture_probe(budget=b) for b in (5, 6, 7, 8, 9)]
    for r in results:
        print(
            f"  budget={r['budget']:>2d}  victim_owned_after_attacker_block={r['victim_owned_after_attacker_block']}"
            f"  captured={r['captured']}"
        )

    by_budget = {r["budget"]: r for r in results}
    assert by_budget[7]["captured"] is False, "budget 7 (CORE_SIZE - 1) must NOT capture in one block"
    assert by_budget[8]["captured"] is True, "budget 8 (CORE_SIZE) must capture in one block"
    print("\nboundary confirmed: instr_per_tick >= CORE_SIZE is necessary and sufficient here for a")
    print("perfectly-informed attacker to capture an earlier-scheduled, non-reacting victim in one block.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
