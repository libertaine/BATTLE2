"""v4 Research Experiment Driver: Process Equivalence Challenge (R1b).

Adversarial validation of the R1 multi-process conclusion.
Tests whether a monolithic Python control loop time-slicing its 8 actions
can faithfully replicate the strategic capability of a true multi-process entrant
under the exact same K=2 chunked scheduler.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.config import Config, Weights
from battle_engine.process_agents import (
    make_monolithic_triple_sim,
    make_single_process_claimer,
    make_single_process_defender,
    make_triple_process_def_scout_atk,
)
from battle_engine.process_runtime import (
    ProcessMatchController,
    ProcessModel,
)


def run_match_matrix(
    roster_factories: list[tuple[str, Any]],
    model: ProcessModel,
    num_seeds: int = 20,
    ticks: int = 400,
) -> dict[str, Any]:
    """Runs all pairwise and 3-way matches across the provided roster factories."""
    config = Config(
        arena_size=4096,
        instr_per_tick=8,
        seed=42,
        win_mode="score_fallback",
        weights=Weights(alive=1.0, kill=5.0, territory=1.0, territory_bucket=64),
    )

    n_entrants = len(roster_factories)
    results: list[dict[str, Any]] = []

    for s_idx in range(num_seeds):
        # Permute seats to eliminate seat bias
        for perm in range(n_entrants):
            permuted_factories = roster_factories[perm:] + roster_factories[:perm]
            entrant_specs = []
            slot_letters = ["A", "B", "C", "D"]
            for idx, (name, factory) in enumerate(permuted_factories):
                slot_id = slot_letters[idx]
                spec = factory(slot_id)
                entrant_specs.append(spec)

            match_config = Config(
                arena_size=4096,
                instr_per_tick=8,
                seed=s_idx * 100 + perm,
                win_mode="score_fallback",
                weights=config.weights,
            )

            controller = ProcessMatchController(
                config=match_config,
                entrant_specs=entrant_specs,
                max_ticks=ticks,
                model=model,
            )
            res = controller.run()
            results.append(res)

    # Aggregate metrics
    agent_wins: dict[str, int] = {}
    agent_survivals: dict[str, int] = {}
    agent_scores: dict[str, list[float]] = {}
    agent_territory: dict[str, list[int]] = {}
    proc_metrics: dict[str, dict[str, Any]] = {}
    total_matches = len(results)

    for res in results:
        winner = res["winner"]
        if winner != "tie":
            w_name = res["entrants"][winner]["name"]
            agent_wins[w_name] = agent_wins.get(w_name, 0) + 1

        for edata in res["entrants"].values():
            name = edata["name"]
            if edata["alive"]:
                agent_survivals[name] = agent_survivals.get(name, 0) + 1
            agent_scores.setdefault(name, []).append(edata["score"])
            agent_territory.setdefault(name, []).append(edata["territory"])

            for pid, pdata in edata["processes"].items():
                key = f"{name}/{pid}_{pdata['role']}"
                if key not in proc_metrics:
                    proc_metrics[key] = {
                        "actions": 0,
                        "reads": 0,
                        "writes": 0,
                        "passes": 0,
                    }
                proc_metrics[key]["actions"] += pdata["actions"]
                proc_metrics[key]["reads"] += pdata["reads"]
                proc_metrics[key]["writes"] += pdata["writes"]
                proc_metrics[key]["passes"] += pdata["passes"]

    summary = {
        "total_matches": total_matches,
        "win_rates": {spec_name: agent_wins.get(spec_name, 0) / total_matches for spec_name in agent_scores.keys()},
        "survival_rates": {spec_name: agent_survivals.get(spec_name, 0) / total_matches for spec_name in agent_survivals.keys()},
        "mean_scores": {spec_name: sum(agent_scores.get(spec_name, [0])) / total_matches for spec_name in agent_scores.keys()},
        "mean_territory": {spec_name: sum(agent_territory.get(spec_name, [0])) / total_matches for spec_name in agent_territory.keys()},
        "process_averages": {
            k: {metric: val / total_matches for metric, val in v.items()}
            for k, v in proc_metrics.items()
        },
    }
    return summary


def run_equivalence_experiments(output_dir: Path) -> dict[str, Any]:
    print("\n" + "="*80)
    print("R1b: MULTI-PROCESS vs MONOLITHIC EQUIVALENCE CHALLENGE")
    print("="*80)

    results = {}

    # Matchup 1: Multi-Process Triple vs Baseline Ecologies
    print("\n  --- Experiment 1: Multi-Process Triple vs Single Claimer vs Single Defender ---")
    r1 = [
        ("triple_def_scout_atk", lambda aid: make_triple_process_def_scout_atk(aid, alloc=(4, 2, 2))),
        ("single_claimer", lambda aid: make_single_process_claimer(aid)),
        ("single_defender", lambda aid: make_single_process_defender(aid)),
    ]
    t0 = time.perf_counter()
    res1 = run_match_matrix(r1, model=ProcessModel.MODEL_A_CURSOR, num_seeds=20)
    dt1 = time.perf_counter() - t0
    results["multi_process_vs_baseline"] = res1
    print(f"    Completed in {dt1:.2f}s | Win rates: {res1['win_rates']}")
    
    # Matchup 2: Monolithic Triple vs Baseline Ecologies
    print("\n  --- Experiment 2: Monolithic Triple vs Single Claimer vs Single Defender ---")
    r2 = [
        ("monolithic_triple_sim", lambda aid: make_monolithic_triple_sim(aid)),
        ("single_claimer", lambda aid: make_single_process_claimer(aid)),
        ("single_defender", lambda aid: make_single_process_defender(aid)),
    ]
    t0 = time.perf_counter()
    res2 = run_match_matrix(r2, model=ProcessModel.MODEL_A_CURSOR, num_seeds=20)
    dt2 = time.perf_counter() - t0
    results["monolithic_vs_baseline"] = res2
    print(f"    Completed in {dt2:.2f}s | Win rates: {res2['win_rates']}")

    # Matchup 3: Head-to-Head (Multi-Process vs Monolithic)
    print("\n  --- Experiment 3: Head-to-Head (Multi-Process Triple vs Monolithic Triple) ---")
    r3 = [
        ("triple_def_scout_atk", lambda aid: make_triple_process_def_scout_atk(aid, alloc=(4, 2, 2))),
        ("monolithic_triple_sim", lambda aid: make_monolithic_triple_sim(aid)),
    ]
    t0 = time.perf_counter()
    res3 = run_match_matrix(r3, model=ProcessModel.MODEL_A_CURSOR, num_seeds=30)
    dt3 = time.perf_counter() - t0
    results["head_to_head"] = res3
    print(f"    Completed in {dt3:.2f}s | Win rates: {res3['win_rates']}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="v4 Research Tool: R1b Equivalence Challenge")
    parser.add_argument("--output", type=Path, default=REPO / "runs" / "research_v4_r1b")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    results = run_equivalence_experiments(args.output)

    out_file = args.output / "r1b_equivalence_results.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nR1b Challenge Complete! Results written to {out_file}")


if __name__ == "__main__":
    main()
