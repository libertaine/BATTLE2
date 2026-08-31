"""v4 Research Tool: Driver for Scheduler Experiments & Comparisons.

Executes:
1. Authoritative baseline reproduction (sequential scheduler, Ruleset v2, 1080 cells).
2. Interleaved scheduler experiment (Ruleset v4-alpha1, 1080 cells).
3. Budget sensitivity sweep (instr_per_tick = 8, 16, 32) under sequential vs interleaved.
4. Comparative ecological analysis (win rates, survival, seat bias, high-budget reaction).
5. Performance and throughput benchmarking.

Outputs results under runs/research_v4_scheduler/ and generates data for V4_SCHEDULER_RESEARCH.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.agent_evaluation import (
    EvaluationCell,
    EvaluationRequest,
    EvaluationService,
)
from battle_engine.benchmarks import load_population, stage_population
from battle_engine.evaluation_group_analysis import (
    analyze_group,
    group_cell_ref_from_evaluation_cell,
)
from battle_engine.paths import get_resource_root
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
)


def get_corpus_def() -> dict:
    root = get_resource_root()
    for directory in (
        root / "battle_engine" / "data" / "benchmarks",
        root / "engine" / "src" / "battle_engine" / "data" / "benchmarks",
        REPO / "engine" / "src" / "battle_engine" / "data" / "benchmarks",
    ):
        path = directory / "v2_baseline_corpus.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise SystemExit("v2_baseline_corpus.json not found in package resources")


def _run_eval(request: EvaluationRequest) -> tuple[float, Any]:
    started = time.perf_counter()
    service = EvaluationService()
    result = service.run(request)
    elapsed = time.perf_counter() - started
    return elapsed, result


def run_full_corpus(output: Path, ruleset: str, workers: int = 4) -> dict[str, float]:
    results = output / "results"
    population = load_population()
    staged = stage_population(population, output)
    print(f"Staged {len(staged)} files for {len(population.members)} pinned agents into {output}")

    corpus = get_corpus_def()
    timings: dict[str, float] = {}

    group = corpus["group"]
    seeds = tuple(int(s) for s in group["seeds"])
    print(f"\n== Group rosters ({len(group['rosters'])} x {group['cells_per_roster']} cells) [ruleset={ruleset}] ==")
    for entry in group["rosters"]:
        roster = entry["roster"]
        target_dir = results / "group" / entry["id"]
        req = EvaluationRequest(
            candidate_id=roster[0],
            opponent_ids=tuple(roster[1:]),
            seeds=seeds,
            output_dir=target_dir,
            ticks=group["ticks"],
            data_root=output,
            workers=workers,
            ruleset_id=ruleset,
            group=True,
        )
        elapsed, res = _run_eval(req)
        timings[f"group/{entry['id']}"] = elapsed
        print(f"  {entry['id']:36s} {elapsed:7.1f}s (cells: {len(res.cells)})")

    pairwise = corpus["pairwise"]
    pair_seeds = tuple(int(s) for s in pairwise["seeds"])
    print(f"\n== Pairwise controls ({len(pairwise['pairs'])} x {pairwise['cells_per_pair']} cells) [ruleset={ruleset}] ==")
    for entry in pairwise["pairs"]:
        target_dir = results / "pairwise" / entry["id"]
        req = EvaluationRequest(
            candidate_id=entry["candidate"],
            opponent_ids=(entry["opponent"],),
            seeds=pair_seeds,
            output_dir=target_dir,
            ticks=entry["ticks"],
            data_root=output,
            workers=workers,
            ruleset_id=ruleset,
            group=False,
            both_orientations=True,
        )
        elapsed, res = _run_eval(req)
        timings[f"pairwise/{entry['id']}"] = elapsed
        print(f"  {entry['id']:36s} {elapsed:7.1f}s (cells: {len(res.cells)})")

    results.mkdir(parents=True, exist_ok=True)
    (results / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"\nTotal wall clock: {sum(timings.values()):.1f}s across {len(timings)} evaluations")
    return timings


def analyze_corpus(results_dir: Path) -> dict[str, Any]:
    corpus = get_corpus_def()
    group = corpus["group"]
    analysis: dict[str, Any] = {"rosters": {}, "pairwise": {}}

    for entry in group["rosters"]:
        eval_path = results_dir / "group" / entry["id"] / "evaluation.json"
        data = json.loads(eval_path.read_text(encoding="utf-8"))
        base = eval_path.parent
        cells = []
        for payload in data["cells"]:
            p = dict(payload)
            p["artifact_dir"] = (base / Path(p["artifact_dir"])).resolve()
            cells.append(EvaluationCell(**p))
        refs = [group_cell_ref_from_evaluation_cell(cell) for cell in cells if cell.is_group]
        report = analyze_group(entry["roster"], refs)
        
        entrants_data = {}
        for s in report.entrant_summaries:
            entrants_data[s.agent_id] = {
                "win_rate": s.winner.rate,
                "wins": s.winner.successes,
                "survival": s.survival.rate,
                "score_mean": s.score.mean,
                "capture_caused": s.capture_caused.rate,
                "capture_suffered": s.capture_suffered.rate,
                "territory_last_pct": s.territory_last_pct.mean,
            }
            
        analysis["rosters"][entry["id"]] = {
            "roster": entry["roster"],
            "entrants": entrants_data,
            "seat_sensitivity": {s.agent_id: s.winner_rate_range for s in report.seat_sensitivity},
            "layout_sensitivity": {s.agent_id: s.winner_rate_range for s in report.layout_sensitivity},
            "seed_summary": {s.agent_id: s.winner_rate_range for s in report.seed_summary},
        }

    for entry in corpus["pairwise"]["pairs"]:
        eval_path = results_dir / "pairwise" / entry["id"] / "evaluation.json"
        data = json.loads(eval_path.read_text(encoding="utf-8"))
        cand_name = entry["candidate"]
        opp_name = entry["opponent"]
        cand_agg = next(a for a in data["aggregates"] if a["subject_role"] == "candidate" and a["orientation_scope"] == "all")
        cand_wins = cand_agg["wins"]
        opp_wins = cand_agg["losses"]
        ties = cand_agg["ties"]
        total = cand_agg["matches_played"]
        analysis["pairwise"][entry["id"]] = {
            "candidate": cand_name,
            "opponent": opp_name,
            "total_cells": total,
            "win_rates": {
                cand_name: cand_wins / total if total else 0.0,
                opp_name: opp_wins / total if total else 0.0,
                "ties": ties / total if total else 0.0,
            },
            "candidate_first_wins": next((a["wins"] for a in data["aggregates"] if a["subject_role"] == "candidate" and a["orientation_scope"] == "candidate_first"), None),
            "opponent_first_wins": next((a["wins"] for a in data["aggregates"] if a["subject_role"] == "candidate" and a["orientation_scope"] == "opponent_first"), None),
        }


    return analysis


def run_budget_sweep(output: Path, budgets: tuple[int, ...] = (8, 16, 32), workers: int = 4) -> dict[str, Any]:
    results_root = output / "budget_sweep"
    population = load_population()
    stage_population(population, output)

    rosters = [
        ("hunter_coretracker_coreseeker", ["hunter", "core_tracker", "core_seeker"]),
        ("claimer_coretracker_coredefender", ["claimer", "core_tracker", "core_defender"]),
        ("claimer_coredefender_reactive", ["claimer", "core_defender", "reactive_core_defender"]),
        ("coredefender_reactive_coreseeker", ["core_defender", "reactive_core_defender", "core_seeker"]),
    ]

    seeds = (1, 2, 3, 4, 5)
    rulesets = [
        ("seq", BYTEFRAY_RULESET_V2_ID),
        ("inter", BYTEFRAY_RULESET_V4_ALPHA1_ID),
    ]

    sweep_results: dict[str, Any] = {}

    for b in budgets:
        for r_name, r_id in rulesets:
            print(f"\n== Budget Sweep: budget={b}, ruleset={r_name} ({r_id}) ==")
            for r_id_str, roster in rosters:
                target_dir = results_root / f"b{b}_{r_name}" / r_id_str
                req = EvaluationRequest(
                    candidate_id=roster[0],
                    opponent_ids=tuple(roster[1:]),
                    seeds=seeds,
                    output_dir=target_dir,
                    ticks=400,
                    data_root=output,
                    workers=workers,
                    ruleset_id=r_id,
                    group=True,
                    instr_per_tick=b,
                )
                elapsed, res = _run_eval(req)
                print(f"  b{b}_{r_name}/{r_id_str:36s} {elapsed:7.1f}s")

                refs = [group_cell_ref_from_evaluation_cell(cell) for cell in res.cells if cell.is_group]
                report = analyze_group(roster, refs)
                
                entrants_data = {}
                for s in report.entrant_summaries:
                    entrants_data[s.agent_id] = {
                        "win_rate": s.winner.rate,
                        "wins": s.winner.successes,
                        "survival": s.survival.rate,
                        "score_mean": s.score.mean,
                        "capture_caused": s.capture_caused.rate,
                        "capture_suffered": s.capture_suffered.rate,
                        "territory_last_pct": s.territory_last_pct.mean,
                    }

                sweep_results[f"b{b}_{r_name}_{r_id_str}"] = {
                    "budget": b,
                    "ruleset": r_name,
                    "roster_id": r_id_str,
                    "entrants": entrants_data,
                    "seat_sensitivity": {s.agent_id: s.winner_rate_range for s in report.seat_sensitivity},
                    "layout_sensitivity": {s.agent_id: s.winner_rate_range for s in report.layout_sensitivity},
                }

    (results_root / "sweep_analysis.json").write_text(json.dumps(sweep_results, indent=2), encoding="utf-8")
    return sweep_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V4 Scheduler Experiment Driver")
    parser.add_argument("mode", choices=["all", "baseline", "interleaved", "sweep", "analyze", "benchmark"])
    parser.add_argument("--output", type=Path, default=REPO / "runs" / "research_v4_scheduler")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    args = parser.parse_args()

    if args.mode == "baseline":
        run_full_corpus(args.output / "baseline_seq", BYTEFRAY_RULESET_V2_ID, args.workers)
    elif args.mode == "interleaved":
        run_full_corpus(args.output / "candidate_inter", BYTEFRAY_RULESET_V4_ALPHA1_ID, args.workers)
    elif args.mode == "sweep":
        run_budget_sweep(args.output, workers=args.workers)
    elif args.mode == "analyze":
        base_analysis = analyze_corpus(args.output / "baseline_seq" / "results")
        inter_analysis = analyze_corpus(args.output / "candidate_inter" / "results")
        sweep_data = json.loads((args.output / "budget_sweep" / "sweep_analysis.json").read_text(encoding="utf-8")) if (args.output / "budget_sweep" / "sweep_analysis.json").is_file() else {}
        (args.output / "comparison.json").write_text(
            json.dumps({"baseline_seq": base_analysis, "candidate_inter": inter_analysis, "budget_sweep": sweep_data}, indent=2),
            encoding="utf-8",
        )
        print("Wrote comparison.json")
    elif args.mode == "all":
        print("=== 1. Running Baseline (Sequential) ===")
        # If baseline already ran, avoid re-running if desired, or run fresh
        if not (args.output / "baseline_seq" / "results" / "timings.json").is_file():
            run_full_corpus(args.output / "baseline_seq", BYTEFRAY_RULESET_V2_ID, args.workers)
        else:
            print("Baseline already completed, skipping to interleaved/sweep.")
            
        print("=== 2. Running Interleaved ===")
        if not (args.output / "candidate_inter" / "results" / "timings.json").is_file():
            run_full_corpus(args.output / "candidate_inter", BYTEFRAY_RULESET_V4_ALPHA1_ID, args.workers)
        else:
            print("Interleaved corpus already completed, skipping to sweep.")

        print("=== 3. Running Budget Sweep ===")
        sweep_data = run_budget_sweep(args.output, workers=args.workers)

        print("=== 4. Analyzing Corpora ===")
        base_analysis = analyze_corpus(args.output / "baseline_seq" / "results")
        inter_analysis = analyze_corpus(args.output / "candidate_inter" / "results")
        (args.output / "comparison.json").write_text(
            json.dumps({"baseline_seq": base_analysis, "candidate_inter": inter_analysis, "budget_sweep": sweep_data}, indent=2),
            encoding="utf-8",
        )
        print("Completed all experimental phases and wrote comparison.json")

