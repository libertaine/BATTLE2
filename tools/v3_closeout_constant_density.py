"""v3 Research Closeout -- constant-density scheduler test (Sec 9-10 of the
governing task).

Phase 1 identified a constant-density diagonal at S ~= 0.781 spanning four
arena sizes and a 64x absolute action-budget range:
``a1024_b2``, ``a4096_b8`` (the shipped default), ``a16384_b32``,
``a65536_b128``. Phase 7 measured reaction-opportunity denial only across
``a4096_b2/_b8/_b32`` -- matched *arena*, varying budget, which changes
density (S = 0.195 / 0.781 / 3.125). This tool runs the identical, frozen
Phase 6 episode reconstruction and Phase 7 ``had_reaction_opportunity``
predicate (both imported unmodified) across the genuinely
constant-density diagonal instead, to separate a *density* effect from an
*absolute-quota* effect -- the causal question the governing closeout task
poses in Sec 9.

All four conditions' group corpora are already committed under
``runs/research_v3_phase1/main/results/``, so this analysis executes zero
new matches. No threshold, window, gate, or qualifying rule is changed.

Usage::

    python tools/v3_closeout_constant_density.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase6_defense_episode as phase6
import v3_phase7_confound_isolation as phase7

OUTPUT_ROOT = REPO / "runs" / "research_v3_closeout"

# S ~= 0.781 diagonal (Phase 1 Sec 3.3's own declared main-grid table).
CONSTANT_DENSITY_CONDITIONS = ("a1024_b2", "a4096_b8", "a16384_b32", "a65536_b128")


def analyze_condition(condition: str, *, threshold: int) -> dict[str, Any]:
    paths = phase6._cells_for_condition(condition, "group")

    total_opportunities = 0
    total_had = 0
    by_role_pair: Counter[tuple[str, str]] = Counter()
    by_role_pair_had: Counter[tuple[str, str]] = Counter()
    by_seat: Counter[str] = Counter()
    by_seat_had: Counter[str] = Counter()
    by_roster: Counter[str] = Counter()
    by_roster_had: Counter[str] = Counter()
    outcome_all: Counter[str] = Counter()
    outcome_denied: Counter[str] = Counter()

    episodes_out: list[dict[str, Any]] = []

    for result_path in paths:
        names, arena, action_budget = phase6._cell_metadata(result_path)
        window = phase6.max_assault_ticks(action_budget)
        replay_path = result_path.parent / "replay.jsonl"
        episodes, _ = phase6.reconstruct_episodes(
            list(phase6.iter_replay(replay_path)), arena_size=arena, threshold=threshold, window=window
        )
        roster = result_path.parent.parent.parent.name
        for ep in episodes:
            if not ep.meaningful_progress_windowed(threshold, window):
                continue
            attacker_role = phase6.ROLE_OF.get(names.get(ep.attacker, ep.attacker), "other")
            victim_role = phase6.ROLE_OF.get(names.get(ep.victim, ep.victim), "other")
            had_opp = phase7.had_reaction_opportunity(ep)

            total_opportunities += 1
            by_role_pair[(attacker_role, victim_role)] += 1
            by_seat[ep.victim] += 1
            by_roster[roster] += 1
            outcome_all[ep.end_reason or "open"] += 1
            if had_opp:
                total_had += 1
                by_role_pair_had[(attacker_role, victim_role)] += 1
                by_seat_had[ep.victim] += 1
                by_roster_had[roster] += 1
            else:
                outcome_denied[ep.end_reason or "open"] += 1

            episodes_out.append(
                {
                    "roster": roster,
                    "cell": result_path.parent.name,
                    "attacker": names.get(ep.attacker, ep.attacker),
                    "attacker_role": attacker_role,
                    "victim": names.get(ep.victim, ep.victim),
                    "victim_role": victim_role,
                    "victim_seat": ep.victim,
                    "had_reaction_opportunity": had_opp,
                    "end_reason": ep.end_reason,
                    "qualified": ep.qualified,
                }
            )

    denied = total_opportunities - total_had
    rate = (denied / total_opportunities) if total_opportunities else None

    def _breakdown(counter: Counter, had_counter: Counter) -> dict[str, Any]:
        out = {}
        for key, n in counter.items():
            had = had_counter.get(key, 0)
            out[str(key)] = {
                "opportunities": n,
                "had_reaction_opportunity": had,
                "denied_reaction_opportunity": n - had,
                "denied_rate": (n - had) / n if n else None,
            }
        return out

    return {
        "condition": condition,
        "threshold": threshold,
        "cells_analysed": len(paths),
        "assault_opportunities": total_opportunities,
        "had_reaction_opportunity": total_had,
        "denied_reaction_opportunity": denied,
        "denied_rate": rate,
        "by_attacker_victim_role": _breakdown(by_role_pair, by_role_pair_had),
        "by_victim_seat": _breakdown(by_seat, by_seat_had),
        "by_roster": _breakdown(by_roster, by_roster_had),
        "outcome_distribution_all": dict(outcome_all),
        "outcome_distribution_denied_only": dict(outcome_denied),
        "episodes": episodes_out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", default="a4096_b8")
    parser.add_argument("--all", action="store_true", help="run the full 4-point constant-density diagonal")
    parser.add_argument("--three", action="store_true", help="run only the 3 conditions the closeout task names")
    parser.add_argument("--threshold", type=int, default=None)
    args = parser.parse_args(argv)

    gates = json.loads(phase6.GATES_PATH.read_text(encoding="utf-8"))
    threshold = args.threshold or gates["event_definition"]["episode_threshold"]

    if args.all:
        conditions = list(CONSTANT_DENSITY_CONDITIONS)
    elif args.three:
        conditions = ["a1024_b2", "a4096_b8", "a16384_b32"]
    else:
        conditions = [args.condition]

    report: dict[str, Any] = {"threshold": threshold, "diagonal_S": 0.781, "conditions": {}}
    for condition in conditions:
        result = analyze_condition(condition, threshold=threshold)
        report["conditions"][condition] = result
        print(f"\n=== {condition} (threshold={threshold}) -- constant-density (S~=0.781) reaction-opportunity ===")
        print(
            f"  assault opportunities: {result['assault_opportunities']}  "
            f"had reaction opportunity: {result['had_reaction_opportunity']}  "
            f"denied: {result['denied_reaction_opportunity']}  "
            f"denied rate: {result['denied_rate']}"
        )
        print("  by attacker/victim role:")
        for key, v in result["by_attacker_victim_role"].items():
            print(f"    {key}: {v}")
        print("  by victim seat:")
        for key, v in result["by_victim_seat"].items():
            print(f"    {key}: {v}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    dest = OUTPUT_ROOT / "closeout_constant_density.json"
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
