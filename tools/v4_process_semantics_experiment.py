"""v4 Research Experiment Driver: Process Semantics Investigation (R1).

Executes systematic experimental sweeps across:
- Stage 1: Model A (Independent Action Cursors, 1-4 processes, equal vs weighted allocation)
- Stage 2: Model B (Static Spatial Loci, reach R in {256, 512, 1024})
- Stage 3: Model C (Movable Spatial Anchors, movement cost, reach R in {256, 512})
- Stage 4: Process Disruption (indestructible vs disabled on anchor overwrite)
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
    make_dual_process_defender_hunter,
    make_dual_process_dual_sweeper,
    make_movable_dual_scout_hunter,
    make_quad_process_quad_sweeper,
    make_single_process_claimer,
    make_single_process_defender,
    make_single_process_hunter,
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
    reach: int | None = None,
    disruption_duration: int = 0,
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
                disruption_duration=disruption_duration,
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
                        "moves": 0,
                        "reads": 0,
                        "writes": 0,
                        "passes": 0,
                        "disrupted_ticks": 0,
                        "positions_visited": 0,
                    }
                proc_metrics[key]["actions"] += pdata["actions"]
                proc_metrics[key]["moves"] += pdata["moves"]
                proc_metrics[key]["reads"] += pdata["reads"]
                proc_metrics[key]["writes"] += pdata["writes"]
                proc_metrics[key]["passes"] += pdata["passes"]
                proc_metrics[key]["disrupted_ticks"] += pdata["disrupted_ticks"]
                proc_metrics[key]["positions_visited"] += pdata["positions_count"]

    summary = {
        "total_matches": total_matches,
        "win_rates": {name: agent_wins.get(name, 0) / total_matches for name, _ in roster_factories},
        "survival_rates": {name: agent_survivals.get(name, 0) / total_matches for name, _ in roster_factories},
        "mean_scores": {name: sum(agent_scores.get(name, [0])) / total_matches for name, _ in roster_factories},
        "mean_territory": {name: sum(agent_territory.get(name, [0])) / total_matches for name, _ in roster_factories},
        "process_averages": {
            k: {metric: val / total_matches for metric, val in v.items()}
            for k, v in proc_metrics.items()
        },
    }
    return summary


def run_stage1_model_a(output_dir: Path) -> dict[str, Any]:
    """Stage 1: Model A (Independent Action Cursors, 1-4 processes)."""
    print("\n" + "="*80)
    print("STAGE 1: MODEL A (INDEPENDENT ACTION CURSORS vs SINGLE PROCESS)")
    print("="*80)

    stage1_results = {}

    # Matchup 1: Single Defender vs Dual Process (Defender + Hunter 4/4) vs Single Claimer
    print("  Running Matchup 1: Single Defender vs Dual (Def+Hunt 4/4) vs Single Claimer...")
    r1 = [
        ("single_defender", lambda aid: make_single_process_defender(aid)),
        ("dual_def_hunt_4_4", lambda aid: make_dual_process_defender_hunter(aid, alloc=(4, 4))),
        ("single_claimer", lambda aid: make_single_process_claimer(aid)),
    ]
    t0 = time.perf_counter()
    res1 = run_match_matrix(r1, model=ProcessModel.MODEL_A_CURSOR, num_seeds=20)
    dt1 = time.perf_counter() - t0
    stage1_results["matchup_1_def_vs_dual_vs_claim"] = res1
    print(f"    Completed in {dt1:.2f}s | Win rates: {res1['win_rates']}")

    # Matchup 2: Single Hunter vs Dual Process (Defender + Hunter 4/4) vs Single Claimer
    print("  Running Matchup 2: Single Hunter vs Dual (Def+Hunt 4/4) vs Single Claimer...")
    r2 = [
        ("single_hunter", lambda aid: make_single_process_hunter(aid)),
        ("dual_def_hunt_4_4", lambda aid: make_dual_process_defender_hunter(aid, alloc=(4, 4))),
        ("single_claimer", lambda aid: make_single_process_claimer(aid)),
    ]
    t0 = time.perf_counter()
    res2 = run_match_matrix(r2, model=ProcessModel.MODEL_A_CURSOR, num_seeds=20)
    dt2 = time.perf_counter() - t0
    stage1_results["matchup_2_hunt_vs_dual_vs_claim"] = res2
    print(f"    Completed in {dt2:.2f}s | Win rates: {res2['win_rates']}")

    # Matchup 3: Single Claimer vs Dual Sweeper (4/4) vs Quad Sweeper (2/2/2/2)
    print("  Running Matchup 3: Single Claimer vs Dual Sweeper (4/4) vs Quad Sweeper (2/2/2/2)...")
    r3 = [
        ("single_claimer", lambda aid: make_single_process_claimer(aid)),
        ("dual_sweeper_4_4", lambda aid: make_dual_process_dual_sweeper(aid, alloc=(4, 4))),
        ("quad_sweeper_2_2_2_2", lambda aid: make_quad_process_quad_sweeper(aid, alloc=(2, 2, 2, 2))),
    ]
    t0 = time.perf_counter()
    res3 = run_match_matrix(r3, model=ProcessModel.MODEL_A_CURSOR, num_seeds=20)
    dt3 = time.perf_counter() - t0
    stage1_results["matchup_3_sweep_expansion_comparison"] = res3
    print(f"    Completed in {dt3:.2f}s | Win rates: {res3['win_rates']}")

    # Matchup 4: Allocation Comparison (Equal 4/4 vs Asymmetric 6/2 vs Triple 4/2/2)
    print("  Running Matchup 4: Allocation Comparison (Dual 4/4 vs Dual 6/2 vs Triple 4/2/2)...")
    r4 = [
        ("dual_def_hunt_4_4", lambda aid: make_dual_process_defender_hunter(aid, alloc=(4, 4))),
        ("dual_def_hunt_6_2", lambda aid: make_dual_process_defender_hunter(aid, alloc=(6, 2))),
        ("triple_def_scout_atk_4_2_2", lambda aid: make_triple_process_def_scout_atk(aid, alloc=(4, 2, 2))),
    ]
    t0 = time.perf_counter()
    res4 = run_match_matrix(r4, model=ProcessModel.MODEL_A_CURSOR, num_seeds=20)
    dt4 = time.perf_counter() - t0
    stage1_results["matchup_4_allocation_comparison"] = res4
    print(f"    Completed in {dt4:.2f}s | Win rates: {res4['win_rates']}")

    return stage1_results


def run_stage2_model_b(output_dir: Path) -> dict[str, Any]:
    """Stage 2: Model B (Static Spatial Loci, reach R in {256, 512, 1024})."""
    print("\n" + "="*80)
    print("STAGE 2: MODEL B (STATIC SPATIAL LOCI)")
    print("="*80)

    stage2_results = {}

    for reach in [256, 512, 1024]:
        print(f"\n  --- Testing Reach R = {reach} ---")
        r = [
            ("single_claimer", lambda aid, r_val=reach: make_single_process_claimer(aid, reach=r_val)),
            ("dual_def_hunt", lambda aid, r_val=reach: make_dual_process_defender_hunter(aid, alloc=(4, 4), reach=r_val)),
            ("triple_def_scout_atk", lambda aid, r_val=reach: make_triple_process_def_scout_atk(aid, alloc=(4, 2, 2), reach=r_val)),
        ]
        t0 = time.perf_counter()
        res = run_match_matrix(r, model=ProcessModel.MODEL_B_STATIC_LOCUS, reach=reach, num_seeds=20)
        dt = time.perf_counter() - t0
        stage2_results[f"reach_{reach}"] = res
        print(f"    R={reach} in {dt:.2f}s | Win rates: {res['win_rates']} | Survivals: {res['survival_rates']}")

    return stage2_results


def run_stage3_model_c(output_dir: Path) -> dict[str, Any]:
    """Stage 3: Model C (Movable Spatial Anchors, movement cost)."""
    print("\n" + "="*80)
    print("STAGE 3: MODEL C (MOVABLE SPATIAL ANCHORS)")
    print("="*80)

    stage3_results = {}

    for reach in [256, 512]:
        print(f"\n  --- Testing Movable Anchor with Reach R = {reach} ---")
        r = [
            ("movable_dual_scout_hunt", lambda aid, r_val=reach: make_movable_dual_scout_hunter(aid, alloc=(4, 4), reach=r_val)),
            ("dual_def_hunt_static", lambda aid, r_val=reach: make_dual_process_defender_hunter(aid, alloc=(4, 4), reach=r_val)),
            ("single_claimer", lambda aid, r_val=reach: make_single_process_claimer(aid, reach=r_val)),
        ]
        t0 = time.perf_counter()
        res = run_match_matrix(r, model=ProcessModel.MODEL_C_MOVABLE_ANCHOR, reach=reach, num_seeds=20)
        dt = time.perf_counter() - t0
        stage3_results[f"reach_{reach}"] = res
        print(f"    R={reach} in {dt:.2f}s | Win rates: {res['win_rates']} | Survivals: {res['survival_rates']}")
        print(f"    Process Averages: {res['process_averages']}")

    return stage3_results



def run_stage4_disruption(output_dir: Path) -> dict[str, Any]:
    """Stage 4: Process Disruption Test (Indestructible vs Disrupted on anchor overwrite)."""
    print("\n" + "="*80)
    print("STAGE 4: PROCESS DISRUPTION (INDESTRUCTIBLE vs DISRUPTED D=4 TICKS)")
    print("="*80)

    stage4_results = {}

    for disruption in [0, 4]:
        label = "indestructible" if disruption == 0 else "disrupted_d4"
        print(f"\n  --- Testing Disruption Mode: {label} ---")
        r = [
            ("dual_def_hunt", lambda aid: make_dual_process_defender_hunter(aid, alloc=(4, 4), reach=512)),
            ("triple_def_scout_atk", lambda aid: make_triple_process_def_scout_atk(aid, alloc=(4, 2, 2), reach=512)),
            ("single_claimer", lambda aid: make_single_process_claimer(aid, reach=512)),
        ]
        t0 = time.perf_counter()
        res = run_match_matrix(r, model=ProcessModel.MODEL_B_STATIC_LOCUS, reach=512, disruption_duration=disruption, num_seeds=20)
        dt = time.perf_counter() - t0
        stage4_results[label] = res
        print(f"    {label} in {dt:.2f}s | Win rates: {res['win_rates']} | Survivals: {res['survival_rates']}")

    return stage4_results


def main() -> None:
    parser = argparse.ArgumentParser(description="v4 Research Tool: R1 Process Semantics Investigation")
    parser.add_argument("--output", type=Path, default=REPO / "runs" / "research_v4_r1")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    all_stage_results = {}

    all_stage_results["stage1"] = run_stage1_model_a(args.output)
    all_stage_results["stage2"] = run_stage2_model_b(args.output)
    all_stage_results["stage3"] = run_stage3_model_c(args.output)
    all_stage_results["stage4"] = run_stage4_disruption(args.output)

    out_file = args.output / "r1_process_semantics_results.json"
    out_file.write_text(json.dumps(all_stage_results, indent=2), encoding="utf-8")
    print(f"\nR1 Process Semantics Investigation Complete! Structured results written to {out_file}")


if __name__ == "__main__":
    main()
