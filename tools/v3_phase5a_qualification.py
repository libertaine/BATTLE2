"""v3 Phase 5A -- defensive-event qualification harness (measurement only).

Evaluates the candidate defensive-success event against the gates declared
in ``engine/src/battle_engine/data/benchmarks/v3_phase5a_defensive_event_gates.json``,
which were committed **before** this harness ran against anything beyond
the 324-cell sample already reported in the Phase 4 addendum.

The event, per that declaration:

    An entrant loses at least THRESHOLD (=4) of its own core cells to
    opponent writes within a single tick, and still owns at least 1 core
    cell at that tick's capture check.

Everything is reconstructed from committed artifacts -- no match is
executed, no score, weight, Ruleset or default is touched. Per tick, for
each victim, the harness attributes *which opponent* took *how many* of
that victim's core cells, which is what makes the burst-versus-coincidence
classification (gate Q4) deterministic rather than inferred:

    burst        := some single opponent took >= 2 of the victim's core
                    cells that tick (impossible for a sweeper, whose stride
                    exceeds CORE_SIZE, so it lands at most one write per
                    core per tick)
    coincidence  := every contributing opponent took exactly 1

Usage::

    python tools/v3_phase5a_qualification.py --condition a4096_b8
    python tools/v3_phase5a_qualification.py --all
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.python_runtime import CORE_SIZE
from battle_engine.replay import TickSnapshot, iter_replay

PHASE1 = REPO / "runs" / "research_v3_phase1" / "main" / "results"
GATES_PATH = REPO / "engine" / "src" / "battle_engine" / "data" / "benchmarks" / "v3_phase5a_defensive_event_gates.json"
OUTPUT_ROOT = REPO / "runs" / "research_v3_phase5a"

PRIMARY_CONDITION = "a4096_b8"
DENSITY_CONDITIONS = ("a1024_b2", "a4096_b2", "a4096_b32", "a16384_b32", "a65536_b32")
THRESHOLDS = (2, 3, 4, 5, 6)

GATES = json.loads(GATES_PATH.read_text(encoding="utf-8"))
THRESHOLD = GATES["event_definition"]["threshold"]
ROLES = GATES["population"]["roles"]
ROLE_OF = {agent: role for role, agents in ROLES.items() for agent in agents}


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


def _anchor(state: Any) -> int:
    pc = state.pc
    if not isinstance(pc, int):
        raise TypeError(f"expected a scalar arena address for pc, got {pc!r}")
    return pc


def analyse_cell(result_path: Path) -> list[dict[str, Any]]:
    """One cell -> one record per (victim seat, tick) that had any incursion.

    Each record carries the total cells the victim lost that tick, the
    per-opponent breakdown, whether the victim still owned >=1 core cell at
    the tick's capture check, and the victim's seat -- everything the gates
    need, with no thresholding applied yet so C1's sensitivity sweep can
    reuse the same pass.
    """

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    repro = payload.get("reproducibility") or {}
    arena = int(repro["arena_size"])
    names = {e["agent_id"]: e["name"] for e in payload["entrants"]}
    entrant_count = len(payload["entrants"])

    replay_path = result_path.parent / "replay.jsonl"
    windows: dict[str, list[int]] = {}
    core_owner_of: dict[int, str] = {}
    writer: list[str | None] = [None] * arena
    records: list[dict[str, Any]] = []

    for record in iter_replay(replay_path):
        if not isinstance(record, TickSnapshot):
            continue
        if record.tick == 0:
            for state in record.agents:
                seat = state.agent_id
                window = [(_anchor(state) + off) % arena for off in range(CORE_SIZE)]
                windows[seat] = window
                for address in window:
                    if address in core_owner_of:
                        raise ValueError(
                            f"{result_path}: overlapping cores at {address} "
                            f"({core_owner_of[address]} and {seat}) -- this analysis assumes disjoint cores"
                        )
                    core_owner_of[address] = seat

        taken: dict[str, Counter[str]] = defaultdict(Counter)
        for diff in record.memory_diffs:
            for offset in range(diff.length):
                address = (diff.address + offset) % arena
                victim = core_owner_of.get(address)
                if victim is not None and writer[address] == victim and diff.owner != victim:
                    taken[victim][str(diff.owner)] += 1
                writer[address] = diff.owner

        if not taken:
            continue
        for victim, by_attacker in taken.items():
            owned_after = sum(1 for a in windows[victim] if writer[a] == victim)
            records.append(
                {
                    "cell": result_path.parent.name,
                    "seat": victim,
                    "agent": names.get(victim, victim),
                    "role": ROLE_OF.get(names.get(victim, victim), "other"),
                    "tick": record.tick,
                    "total_taken": sum(by_attacker.values()),
                    "max_by_one_attacker": max(by_attacker.values()),
                    "attackers": {names.get(k, k): v for k, v in by_attacker.items()},
                    "survived_tick": owned_after >= 1,
                    "entrant_count": entrant_count,
                }
            )
    return records


def collect(condition: str, kind: str = "group") -> tuple[list[dict[str, Any]], Counter[str], Counter[tuple[str, str]]]:
    """All incursion records for a condition, plus per-agent and per-(agent,seat) appearance counts."""

    root = PHASE1 / condition / kind
    if not root.is_dir():
        raise SystemExit(f"missing corpus: {root}")
    records: list[dict[str, Any]] = []
    appearances: Counter[str] = Counter()
    seat_appearances: Counter[tuple[str, str]] = Counter()
    for result_path in sorted(root.glob("*/matches/*/result.json")):
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        for entrant in payload["entrants"]:
            appearances[entrant["name"]] += 1
            seat_appearances[(entrant["name"], entrant["agent_id"])] += 1
        records.extend(analyse_cell(result_path))
    return records, appearances, seat_appearances


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


def _events(records: list[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    return [r for r in records if r["total_taken"] >= threshold and r["survived_tick"]]


def _event_bearing_cells(events: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: Counter[tuple[str, str]] = Counter()
    for e in events:
        counts[(e["cell"], e["agent"])] += 1
    return dict(counts)


def rates_by_agent(records, appearances, threshold) -> dict[str, dict[str, Any]]:
    events = _events(records, threshold)
    bearing = _event_bearing_cells(events)
    per_agent_cells: Counter[str] = Counter()
    for (_cell, agent) in bearing:
        per_agent_cells[agent] += 1
    worst: dict[str, int] = defaultdict(int)
    for r in records:
        worst[r["agent"]] = max(worst[r["agent"]], r["total_taken"])
    out = {}
    for agent, n in sorted(appearances.items()):
        out[agent] = {
            "role": ROLE_OF.get(agent, "other"),
            "appearances": n,
            "event_bearing_cells": per_agent_cells.get(agent, 0),
            "rate": per_agent_cells.get(agent, 0) / n if n else None,
            "max_single_tick_loss": worst.get(agent, 0),
        }
    return out


def evaluate_gates(records, appearances, seat_appearances) -> dict[str, Any]:
    by_agent = rates_by_agent(records, appearances, THRESHOLD)
    events = _events(records, THRESHOLD)

    search_rates = [v["rate"] for k, v in by_agent.items() if v["role"] == "search"]
    defense_rates = [v["rate"] for k, v in by_agent.items() if v["role"] == "defense"]
    search_max_loss = max((v["max_single_tick_loss"] for v in by_agent.values() if v["role"] == "search"), default=0)

    defense_events = [e for e in events if e["role"] == "defense"]
    burst = [e for e in defense_events if e["max_by_one_attacker"] >= 2]
    burst_share = len(burst) / len(defense_events) if defense_events else None

    bearing = _event_bearing_cells([e for e in events if e["role"] == "defense"])
    per_cell_counts = sorted(bearing.values())
    median_per_cell = statistics.median(per_cell_counts) if per_cell_counts else 0
    p95 = (
        sorted(per_cell_counts)[min(len(per_cell_counts) - 1, int(0.95 * len(per_cell_counts)))]
        if per_cell_counts
        else 0
    )

    # Mechanical ceiling: pure sweeping can cost at most (entrant_count - 1).
    ceiling_violations = [
        r for r in records if r["total_taken"] > (r["entrant_count"] - 1) and r["max_by_one_attacker"] < 2
    ]

    q1 = max(search_rates, default=0.0) <= GATES["qualification_gates"]["Q1_selectivity_search"]["bound"]
    q2 = min(defense_rates, default=0.0) >= GATES["qualification_gates"]["Q2_selectivity_defense"]["bound"]
    q3 = search_max_loss <= GATES["qualification_gates"]["Q3_threshold_margin"]["bound"]
    q4 = (burst_share is not None) and burst_share >= GATES["qualification_gates"]["Q4_burst_attribution"]["bound"]
    q5 = median_per_cell <= GATES["qualification_gates"]["Q5_frequency_discipline"]["bound"]

    return {
        "by_agent": by_agent,
        "Q1_selectivity_search": {"pass": q1, "max_search_rate": max(search_rates, default=0.0)},
        "Q2_selectivity_defense": {"pass": q2, "min_defense_rate": min(defense_rates, default=0.0)},
        "Q3_threshold_margin": {"pass": q3, "max_search_single_tick_loss": search_max_loss},
        "Q4_burst_attribution": {
            "pass": q4,
            "burst_share": burst_share,
            "defense_events": len(defense_events),
            "burst_events": len(burst),
            "coincidence_events": len(defense_events) - len(burst),
        },
        "Q5_frequency_discipline": {
            "pass": q5,
            "median_events_per_bearing_cell": median_per_cell,
            "p95": p95,
            "max": max(per_cell_counts, default=0),
            "cap_required": p95 > GATES["qualification_gates"]["Q5_frequency_discipline"]["cap_trigger"]["bound"],
        },
        "mechanical_ceiling": {
            "holds": not ceiling_violations,
            "violations": len(ceiling_violations),
            "examples": ceiling_violations[:3],
        },
    }


def threshold_sensitivity(records, appearances) -> dict[str, Any]:
    out = {}
    for t in THRESHOLDS:
        by_agent = rates_by_agent(records, appearances, t)
        search = max((v["rate"] for v in by_agent.values() if v["role"] == "search"), default=0.0)
        defense = min((v["rate"] for v in by_agent.values() if v["role"] == "defense"), default=0.0)
        expansion = max((v["rate"] for v in by_agent.values() if v["role"] == "expansion"), default=0.0)
        ev = _events(records, t)
        bursts = sum(1 for e in ev if e["max_by_one_attacker"] >= 2)
        out[str(t)] = {
            "max_search_rate": search,
            "min_defense_rate": defense,
            "max_expansion_rate": expansion,
            "events": len(ev),
            "burst_share": bursts / len(ev) if ev else None,
        }
    return out


def seat_decomposition(records, seat_appearances) -> dict[str, Any]:
    """C2: separate event CREATION (was a qualifying incursion inflicted?)
    from event SURVIVAL (given one, did the victim survive that tick?)."""

    created: Counter[tuple[str, str]] = Counter()
    survived: Counter[tuple[str, str]] = Counter()
    for r in records:
        if r["role"] != "defense" or r["total_taken"] < THRESHOLD:
            continue
        key = (r["agent"], r["seat"])
        created[key] += 1
        if r["survived_tick"]:
            survived[key] += 1

    by_seat: dict[str, dict[str, Any]] = {}
    for seat in sorted({s for (_a, s) in seat_appearances}):
        appear = sum(n for (a, s), n in seat_appearances.items() if s == seat and ROLE_OF.get(a) == "defense")
        c = sum(n for (a, s), n in created.items() if s == seat)
        v = sum(n for (a, s), n in survived.items() if s == seat)
        by_seat[seat] = {
            "defense_appearances": appear,
            "qualifying_incursions_created": c,
            "creation_per_appearance": c / appear if appear else None,
            "survived_given_incursion": v / c if c else None,
        }
    survival_values = [d["survived_given_incursion"] for d in by_seat.values() if d["survived_given_incursion"] is not None]
    spread_pp = (max(survival_values) - min(survival_values)) * 100 if survival_values else 0.0
    return {
        "by_seat": by_seat,
        "survival_spread_pp": spread_pp,
        "scheduler_artifact_disclosure_triggered": spread_pp > 25.0,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def run_condition(condition: str, kind: str = "group") -> dict[str, Any]:
    records, appearances, seat_appearances = collect(condition, kind)
    result: dict[str, Any] = {
        "condition": condition,
        "kind": kind,
        "incursion_records": len(records),
        "gates": evaluate_gates(records, appearances, seat_appearances),
        "threshold_sensitivity": threshold_sensitivity(records, appearances),
    }
    if kind == "group":
        result["seat_decomposition"] = seat_decomposition(records, seat_appearances)
    return result


def _print_condition(report: dict[str, Any]) -> None:
    g = report["gates"]
    print(f"\n=== {report['condition']} ({report['kind']}) ===")
    print(f"{'agent':<24s}{'role':>10s}{'appear':>8s}{'events':>8s}{'rate':>8s}{'maxloss':>9s}")
    for agent, v in g["by_agent"].items():
        print(
            f"{agent:<24s}{v['role']:>10s}{v['appearances']:>8d}{v['event_bearing_cells']:>8d}"
            f"{100.0 * (v['rate'] or 0):>7.1f}%{v['max_single_tick_loss']:>9d}"
        )
    mark = lambda ok: "PASS" if ok else "FAIL"
    print(
        f"  Q1 search<=2%      {mark(g['Q1_selectivity_search']['pass'])}  "
        f"(max {100 * g['Q1_selectivity_search']['max_search_rate']:.2f}%)"
    )
    print(
        f"  Q2 defense>=25%    {mark(g['Q2_selectivity_defense']['pass'])}  "
        f"(min {100 * g['Q2_selectivity_defense']['min_defense_rate']:.1f}%)"
    )
    print(
        f"  Q3 margin<=2       {mark(g['Q3_threshold_margin']['pass'])}  "
        f"(search max single-tick loss {g['Q3_threshold_margin']['max_search_single_tick_loss']})"
    )
    q4 = g["Q4_burst_attribution"]
    print(
        f"  Q4 burst>=90%      {mark(q4['pass'])}  "
        f"({100 * (q4['burst_share'] or 0):.1f}% of {q4['defense_events']} defense events; "
        f"{q4['coincidence_events']} coincidence)"
    )
    q5 = g["Q5_frequency_discipline"]
    print(
        f"  Q5 median<=3       {mark(q5['pass'])}  "
        f"(median {q5['median_events_per_bearing_cell']}, p95 {q5['p95']}, max {q5['max']}, "
        f"cap_required={q5['cap_required']})"
    )
    mc = g["mechanical_ceiling"]
    print(f"  mechanical ceiling {mark(mc['holds'])}  ({mc['violations']} violations)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", default=PRIMARY_CONDITION)
    parser.add_argument("--all", action="store_true", help="primary + density conditions + pairwise")
    args = parser.parse_args(argv)

    report: dict[str, Any] = {
        "gates_declared_at": str(GATES_PATH.relative_to(REPO)),
        "threshold": THRESHOLD,
        "conditions": {},
    }

    primary = run_condition(args.condition, "group")
    _print_condition(primary)
    report["conditions"][args.condition] = primary

    if args.all:
        pair = run_condition(PRIMARY_CONDITION, "pairwise")
        _print_condition(pair)
        report["conditions"][f"{PRIMARY_CONDITION}:pairwise"] = pair
        for condition in DENSITY_CONDITIONS:
            density = run_condition(condition, "group")
            _print_condition(density)
            report["conditions"][condition] = density

    print("\n--- threshold sensitivity (primary condition) ---")
    print(f"{'thr':>4s}{'search':>10s}{'defense':>10s}{'expansion':>11s}{'events':>9s}{'burst%':>9s}")
    for t, v in primary["threshold_sensitivity"].items():
        print(
            f"{t:>4s}{100 * v['max_search_rate']:>9.2f}%{100 * v['min_defense_rate']:>9.1f}%"
            f"{100 * v['max_expansion_rate']:>10.1f}%{v['events']:>9d}"
            f"{100 * (v['burst_share'] or 0):>8.1f}%"
        )

    if "seat_decomposition" in primary:
        sd = primary["seat_decomposition"]
        print("\n--- C2 seat decomposition: creation vs survival (defense agents) ---")
        print(f"{'seat':>5s}{'appear':>8s}{'created':>9s}{'create/app':>12s}{'survive|inc':>13s}")
        for seat, v in sd["by_seat"].items():
            print(
                f"{seat:>5s}{v['defense_appearances']:>8d}{v['qualifying_incursions_created']:>9d}"
                f"{v['creation_per_appearance'] or 0:>12.3f}"
                f"{100 * (v['survived_given_incursion'] or 0):>12.1f}%"
            )
        print(
            f"  survival spread across seats: {sd['survival_spread_pp']:.1f} pp  "
            f"(disclosure trigger at >25pp: {sd['scheduler_artifact_disclosure_triggered']})"
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT_ROOT / "phase5a_qualification.json"
    destination.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
