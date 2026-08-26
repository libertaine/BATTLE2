"""v3 Phase 4 -- measure defense's economic cost and strategic benefit
*before* selecting a compensating scoring lever, at Phase 3's accepted
offense payoff (w_kill = 1600) held fixed.

1. **Action-opportunity cost**: both defense archetypes' own source commits
   them to a fixed 1-in-4 (`REFRESH_EVERY = 4`) non-claiming action, by
   construction -- confirmed here against real committed replay/result
   data, not merely cited from source.
2. **Denial benefit**: the score an attacker forgoes when a core it
   attacks is successfully defended is, by the scoring formula itself,
   exactly the kill bonus it would otherwise have earned -- quantified
   here at the fixed w_kill=1600 payoff, the mirror image of Phase 3's own
   opportunity-cost measurement.
3. **Structural sanity check**: alpha.5's closed-form proof that
   `alive_ticks` cannot differentiate survivors in a tick-limit-resolved
   multi-entrant match is independent of `w_kill`'s value and of which
   Ruleset-v2 population is used -- reconfirmed directly against this
   phase's own K2 corpus rather than merely cited.
4. **Territory share**: whether defense actually holds less territory
   than the archetypes it competes against, which is the only remaining
   candidate mechanism by which raising `weights.territory` could help it.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.replay import iter_replay

PHASE1_DEFAULT = REPO / "runs" / "research_v3_phase1" / "main" / "results" / "a4096_b8"
PHASE3_ANALYSIS = REPO / "runs" / "research_v3_phase3" / "phase3_analysis.json"

DEFENSE_AGENTS = ("core_defender", "reactive_core_defender")
ALL_AGENTS = ("claimer", "hunter", "core_seeker", "core_tracker", *DEFENSE_AGENTS)


def measure_realized_action_cost() -> dict[str, Any]:
    """Count, from a real committed replay, exactly which of a defender's
    actions were core-directed (WRITE/READ at one of its own DEFENDED_RADIUS
    addresses) versus outward-claiming, for one representative undisturbed
    match of each defense archetype."""

    roster = "coredefender_reactive_coreseeker"
    base = PHASE1_DEFAULT / "group" / roster
    data = json.loads((base / "evaluation.json").read_text(encoding="utf-8"))
    cell = data["cells"][0]
    replay_path = base / cell["artifact_dir"] / "replay.jsonl"
    result_path = base / cell["artifact_dir"] / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))

    core_start_by_seat: dict[str, int] = {}
    seat_agent = {e["agent_id"]: e["name"] for e in result["entrants"]}
    for record in iter_replay(replay_path):
        if getattr(record, "record_type", None) == "header":
            for entrant in record.entrants:
                seat = entrant.get("agent_id") or entrant.get("slot")
                if seat and "start" in entrant.get("metadata", entrant):
                    pass
            break

    # Core anchors are each entrant's own spawn address; recover them from
    # the first tick's agent states (pc, before any JUMP -- see
    # core_defender/agent.py's own documented technique for the identical
    # recovery this agent performs on itself).
    first_tick = None
    for record in iter_replay(replay_path):
        if getattr(record, "record_type", None) == "tick" and record.tick == 0:
            first_tick = record
            break
    assert first_tick is not None
    for agent_state in first_tick.agents:
        core_start_by_seat[agent_state.agent_id] = agent_state.pc

    DEFENDED_RADIUS = 8
    core_cells_by_seat = {
        seat: {(start + offset) % 4096 for offset in range(DEFENDED_RADIUS)}
        for seat, start in core_start_by_seat.items()
    }

    action_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"core_directed": 0, "expansion": 0})
    for record in iter_replay(replay_path):
        if getattr(record, "record_type", None) != "tick":
            continue
        for diff in record.memory_diffs:
            owner = diff.owner
            if owner is None or owner not in core_cells_by_seat:
                continue
            for offset in range(diff.length):
                address = (diff.address + offset) % 4096
                if address in core_cells_by_seat[owner]:
                    action_counts[owner]["core_directed"] += 1
                else:
                    action_counts[owner]["expansion"] += 1

    report = {}
    for seat, counts in action_counts.items():
        agent_name = seat_agent.get(seat, seat)
        total_writes = counts["core_directed"] + counts["expansion"]
        entrant = next(e for e in result["entrants"] if e["agent_id"] == seat)
        cpu_total = entrant["statistics"]["cpu_total"]
        mem_writes = entrant["statistics"]["mem_writes"]
        non_write_actions = cpu_total - mem_writes
        report[agent_name] = {
            # Correct for core_defender (every action is a WRITE, so
            # address-classifying writes captures its whole defensive
            # cost). Undercounts reactive_core_defender, whose patrol
            # check is a cheap READ -- replay's memory_diffs only records
            # writes, so a READ leaves no per-address trace to classify.
            "core_directed_writes": counts["core_directed"],
            "expansion_writes": counts["expansion"],
            "total_writes": total_writes,
            "core_directed_fraction_of_writes": counts["core_directed"] / total_writes if total_writes else None,
            # Correct for reactive_core_defender (its only non-WRITE
            # action is a defensive READ, so this residual *is* its
            # defensive cost exactly). Meaningless for core_defender
            # (always 0, since it never reads).
            "cpu_total": cpu_total,
            "mem_writes": mem_writes,
            "non_write_actions": non_write_actions,
            "non_write_fraction_of_actions": non_write_actions / cpu_total if cpu_total else None,
        }
    return {"sample_cell": cell["artifact_dir"], "by_agent": report}


def measure_denial_benefit(w_kill: float = 1600.0) -> dict[str, Any]:
    """The score an attacker forgoes per successfully-defended attack is,
    by construction, exactly one kill's worth of bonus at the fixed
    payoff -- the mirror image of Phase 3's own opportunity-cost framing.
    Also reports how many attempted-but-failed-to-capture encounters exist
    in the committed corpus (search agent present, defender survives)."""

    analysis = json.loads(PHASE3_ANALYSIS.read_text(encoding="utf-8"))
    k0 = [e for e in analysis["group"] if e["condition_id"] == "K0"]
    defended_survivals = 0
    defended_captures = 0
    for entry in k0:
        for agent, stats in entry["entrants"].items():
            if agent not in DEFENSE_AGENTS:
                continue
            trials = stats.get("trials") or 0
            suffered = stats.get("capture_suffered") or 0.0
            defended_captures += round(suffered * trials)
            defended_survivals += trials - round(suffered * trials)
    return {
        "w_kill_fixed": w_kill,
        "denial_benefit_per_successful_defense": w_kill,
        "defended_survivals_in_K0_corpus": defended_survivals,
        "defended_captures_in_K0_corpus": defended_captures,
        "total_defense_appearances": defended_survivals + defended_captures,
        "note": (
            "Each successfully-repelled attack denies the attacker exactly "
            "w_kill points it would otherwise have earned; this is a "
            "structural consequence of the scoring formula (score_kill is "
            "the only term keyed to a capture event), not a separate "
            "empirical measurement."
        ),
    }


def verify_alive_ticks_tied_among_survivors() -> dict[str, Any]:
    """Alpha.5 Sec 15's closed-form proof, reconfirmed directly against
    this phase's own K2 corpus: whenever 2+ entrants are alive at
    resolution, their alive_ticks must be identical, because
    resolve_termination only force-stops at 0 or 1 alive."""

    base = REPO / "runs" / "research_v3_phase3" / "rescored" / "K2" / "group"
    mismatches = []
    checked = 0
    for roster_dir in sorted(base.iterdir()):
        data = json.loads((roster_dir / "evaluation.json").read_text(encoding="utf-8"))
        for cell in data["cells"]:
            result_path = roster_dir / cell["artifact_dir"] / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            alive_entrants = [e for e in result["entrants"] if e["alive"]]
            if len(alive_entrants) < 2:
                continue
            checked += 1
            ticks = {e["statistics"]["alive_ticks"] for e in alive_entrants}
            if len(ticks) != 1:
                mismatches.append({"cell": cell["artifact_dir"], "roster": roster_dir.name, "ticks": list(ticks)})
    return {"cells_with_2plus_survivors_checked": checked, "mismatches": mismatches, "proof_holds": not mismatches}


def measure_territory_shares() -> dict[str, float]:
    analysis = json.loads(PHASE3_ANALYSIS.read_text(encoding="utf-8"))
    by_agent: dict[str, list[float]] = defaultdict(list)
    for entry in analysis["group"]:
        if entry["condition_id"] != "K2":
            continue
        for agent, stats in entry["entrants"].items():
            if stats.get("territory_last_pct") is not None:
                by_agent[agent].append(stats["territory_last_pct"])
    return {agent: sum(v) / len(v) for agent, v in by_agent.items() if v}


def main() -> int:
    report = {
        "realized_action_cost": measure_realized_action_cost(),
        "denial_benefit": measure_denial_benefit(),
        "alive_ticks_tied_among_survivors": verify_alive_ticks_tied_among_survivors(),
        "territory_share_at_K2": measure_territory_shares(),
    }
    destination = REPO / "runs" / "research_v3_phase4" / "phase4_economics.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
