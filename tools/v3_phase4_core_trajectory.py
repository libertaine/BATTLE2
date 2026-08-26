"""Post-Phase-4 evidence: core-ownership trajectories from committed replays.

Produces every number cited in the dated addendum to
``docs/V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md``, so those claims are
reproducible from the repository rather than resting on a transcript.

This is **measurement only**. It changes no scoring, no Ruleset, and no
default, and it is deliberately *not* the Phase 5A qualification harness
(see ``docs/V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md``, which has not
been implemented): it samples 6 of the 11 committed group rosters at the
default condition, whereas Phase 5A's own gates require the full 594-cell
corpus plus other density conditions.

Two analyses, both reconstructed purely from committed artifacts:

``trajectory``
    Per-tick count of core cells each entrant still owns, replayed from
    ``memory_diffs`` (``address``/``length``/``owner``) starting at tick 0,
    with each entrant's core anchor taken from its tick-0 ``pc`` (published
    before any agent acts, and documented as ``[start, start]`` in
    ``AgentState.region`` for Python entrants). Used to show that generic
    "damaged then recovered" and "reached the brink and survived" are both
    non-selective for defense.

``incursions``
    Per-tick count of *ownership transitions away from* each entrant inside
    its own core window -- i.e. how many of its core cells an opponent took
    that tick. Used to show that concentrated (>= 4 cells in one tick)
    incursions separate committed assault bursts from incidental sweep
    contact, which no sweeper can produce at these strides.

Usage::

    python tools/v3_phase4_core_trajectory.py trajectory
    python tools/v3_phase4_core_trajectory.py incursions
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.python_runtime import CORE_SIZE
from battle_engine.replay import TickSnapshot, iter_replay

PHASE1_DEFAULT = REPO / "runs" / "research_v3_phase1" / "main" / "results" / "a4096_b8" / "group"
ARENA = 4096
DEFENSE_AGENTS = ("core_defender", "reactive_core_defender")

# The two 6-roster samples the addendum reports. They differ deliberately:
# the trajectory sample includes the offense-free negative control (where no
# capture can occur), while the incursion sample swaps it for an
# offense-heavy roster, so the incursion signature is measured where
# assaults actually happen.
TRAJECTORY_ROSTERS = (
    "claimer_coretracker_coredefender",
    "claimer_coretracker_reactive",
    "coredefender_reactive_coreseeker",
    "reactive_hunter_coreseeker",
    "hunter_coretracker_coredefender",
    "claimer_coredefender_reactive",
)
INCURSION_ROSTERS = (
    "claimer_coretracker_coredefender",
    "claimer_coretracker_reactive",
    "coredefender_reactive_coreseeker",
    "reactive_hunter_coreseeker",
    "hunter_coretracker_coredefender",
    "claimer_coreseeker_hunter",
)


def _cells(rosters: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for roster in rosters:
        paths += [Path(p) for p in sorted(glob.glob(str(PHASE1_DEFAULT / roster / "matches" / "*" / "result.json")))]
    return paths


def _anchor(state: Any) -> int:
    """A Python entrant's spawn address from its tick-0 ``pc``.

    ``AgentState.pc`` is typed as a ``Position`` because the reader also
    accepts historical ``[x, y]`` coordinate records; every native
    ``battle2.replay`` v3 record this tool reads carries a plain address,
    so a tuple here means the input is not what this analysis assumes and
    is rejected rather than silently coerced.
    """

    pc = state.pc
    if not isinstance(pc, int):
        raise TypeError(f"expected a scalar arena address for pc, got {pc!r}")
    return pc % ARENA


def _core_windows(replay_path: Path) -> dict[str, list[int]]:
    """Each seat's core address window, from its tick-0 pc (its spawn address)."""

    for record in iter_replay(replay_path):
        if isinstance(record, TickSnapshot) and record.tick == 0:
            return {
                state.agent_id: [(_anchor(state) + offset) % ARENA for offset in range(CORE_SIZE)]
                for state in record.agents
            }
    raise ValueError(f"{replay_path}: no tick-0 record")


def owned_series(replay_path: Path) -> dict[str, list[int]]:
    """Per-tick count of own-core cells still owned, per seat."""

    writer: list[str | None] = [None] * ARENA
    windows = _core_windows(replay_path)
    series: dict[str, list[int]] = {seat: [] for seat in windows}
    for record in iter_replay(replay_path):
        if not isinstance(record, TickSnapshot):
            continue
        for diff in record.memory_diffs:
            for offset in range(diff.length):
                writer[(diff.address + offset) % ARENA] = diff.owner
        for seat, window in windows.items():
            series[seat].append(sum(1 for address in window if writer[address] == seat))
    return series


def incursion_series(replay_path: Path) -> dict[str, list[int]]:
    """Per-tick count of own-core cells taken *by an opponent*, per seat."""

    writer: list[str | None] = [None] * ARENA
    windows = _core_windows(replay_path)
    series: dict[str, list[int]] = {seat: [] for seat in windows}
    for record in iter_replay(replay_path):
        if not isinstance(record, TickSnapshot):
            continue
        taken: Counter[str] = Counter()
        for diff in record.memory_diffs:
            for offset in range(diff.length):
                address = (diff.address + offset) % ARENA
                previous, new = writer[address], diff.owner
                if new != previous:
                    for seat, window in windows.items():
                        if seat != new and previous == seat and address in window:
                            taken[seat] += 1
                writer[address] = new
        for seat in windows:
            series[seat].append(taken.get(seat, 0))
    return series


def _seat_names(result_path: Path) -> tuple[dict[str, str], set[str]]:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    names = {e["agent_id"]: e["name"] for e in payload["entrants"]}
    captured = {
        e["agent_id"] for e in payload["entrants"] if e.get("termination_reason") == "core_captured"
    }
    return names, captured


def report_trajectory() -> dict[str, Any]:
    per_agent: dict[str, Counter[str]] = defaultdict(Counter)
    cells = _cells(TRAJECTORY_ROSTERS)
    for result_path in cells:
        names, captured = _seat_names(result_path)
        for seat, series in owned_series(result_path.parent / "replay.jsonl").items():
            record = per_agent[names.get(seat, seat)]
            record["appearances"] += 1
            if not series:
                continue
            low = min(series)
            if seat in captured:
                record["captured"] += 1
                continue
            record["survived"] += 1
            if low < CORE_SIZE:
                record["damaged_and_survived"] += 1
            if low <= 1:
                record["brink_and_survived"] += 1
            armed, cycles = False, 0
            for value in series:
                if value < CORE_SIZE:
                    armed = True
                elif armed:
                    cycles += 1
                    armed = False
            record["full_recovery_cycles"] += cycles

    print(f"cells analysed: {len(cells)}  rosters: {len(TRAJECTORY_ROSTERS)}\n")
    header = f"{'agent':<24s}{'appear':>7s}{'surv':>6s}{'capt':>6s}{'dmg&surv':>10s}{'brink&surv':>11s}{'cycles':>8s}"
    print(header)
    for name in sorted(per_agent):
        r = per_agent[name]
        print(
            f"{name:<24s}{r['appearances']:>7d}{r['survived']:>6d}{r['captured']:>6d}"
            f"{r['damaged_and_survived']:>10d}{r['brink_and_survived']:>11d}{r['full_recovery_cycles']:>8d}"
        )
    return {name: dict(counter) for name, counter in per_agent.items()}


def report_incursions(threshold: int = 4) -> dict[str, Any]:
    distribution: dict[str, Counter[int]] = defaultdict(Counter)
    peak: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    events: dict[str, Counter[str]] = defaultdict(Counter)
    cells = _cells(INCURSION_ROSTERS)
    for result_path in cells:
        names, captured = _seat_names(result_path)
        for seat, series in incursion_series(result_path.parent / "replay.jsonl").items():
            name = names.get(seat, seat)
            for value in series:
                if value:
                    distribution[name][value] += 1
            highest = max(series) if series else 0
            outcome = "CAPTURED" if seat in captured else "survived"
            peak[(name, outcome)][highest] += 1
            events[name]["appearances"] += 1
            if outcome == "survived" and highest >= threshold:
                events[name]["events"] += 1

    print(f"cells analysed: {len(cells)}  rosters: {len(INCURSION_ROSTERS)}\n")
    print("own-core cells lost to an opponent within ONE tick (nonzero ticks only):")
    print(f"{'agent':<24s}" + "".join(f"{k:>7d}" for k in range(1, CORE_SIZE + 1)))
    for name in sorted(distribution):
        print(f"{name:<24s}" + "".join(f"{distribution[name].get(k, 0):>7d}" for k in range(1, CORE_SIZE + 1)))

    print(f"\ncandidate event (>= {threshold} lost in one tick, survived the capture check):")
    print(f"{'agent':<24s}{'appear':>8s}{'events':>8s}{'rate':>8s}{'max loss':>10s}")
    for name in sorted(events):
        appearances = events[name]["appearances"]
        fired = events[name]["events"]
        worst = max(distribution[name]) if distribution[name] else 0
        print(f"{name:<24s}{appearances:>8d}{fired:>8d}{100.0 * fired / appearances:>7.1f}%{worst:>10d}")
    return {
        "distribution": {n: dict(c) for n, c in distribution.items()},
        "events": {n: dict(c) for n, c in events.items()},
        "peak": {f"{n}/{o}": dict(c) for (n, o), c in peak.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", choices=("trajectory", "incursions"))
    parser.add_argument("--threshold", type=int, default=4)
    args = parser.parse_args(argv)
    if args.analysis == "trajectory":
        report_trajectory()
    else:
        report_incursions(args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
