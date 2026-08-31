"""v4 Research Tool: Driver for R0b Scheduler Grain Qualification.

Sweeps K in {quota, 4, 2, 1} across budgets b in {8, 16, 32} to identify the coarsest
deterministic scheduling grain that resolves the seat/reaction problem.

Stage 1: Focused sweep on 4 problem group rosters + 1 pairwise control across budgets.
Stage 2: Full benchmark corpus (1080 cells) on key candidates and rotating-start qualification.
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

from battle_engine.agent_evaluation import (
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


FOCUS_ROSTERS = [
    ("claimer_coretracker_coredefender", ["claimer", "core_tracker", "core_defender"]),
    ("coredefender_reactive_coreseeker", ["core_defender", "reactive_core_defender", "core_seeker"]),
    ("hunter_coretracker_coredefender", ["hunter", "core_tracker", "core_defender"]),
    ("claimer_coredefender_reactive", ["claimer", "core_defender", "reactive_core_defender"]),
]

FOCUS_PAIRWISE = [
    ("claimer_vs_coretracker_400", "claimer", "core_tracker", 400),
]


def _run_eval(request: EvaluationRequest) -> tuple[float, Any]:
    started = time.perf_counter()
    service = EvaluationService()
    result = service.run(request)
    elapsed = time.perf_counter() - started
    return elapsed, result


def run_stage1_sweep(output: Path, budgets: tuple[int, ...] = (8, 16, 32), workers: int = 4) -> dict[str, Any]:
    """Stage 1: Focused Scheduler-Grain Sweep across b in {8, 16, 32} and K in {b, 4, 2, 1}."""
    results_root = output / "stage1_sweep"
    population = load_population()
    stage_population(population, output)

    seeds = (1, 2, 3, 4, 5)
    sweep_results: dict[str, Any] = {}

    for b in budgets:
        grains = [b, 4, 2, 1] if b > 4 else ([b, 2, 1] if b > 2 else [b, 1])
        # Deduplicate while preserving order
        seen_g = set()
        dedup_grains = []
        for g in grains:
            if g not in seen_g:
                seen_g.add(g)
                dedup_grains.append(g)

        for K in dedup_grains:
            label = f"b{b}_K{K}"
            ruleset = BYTEFRAY_RULESET_V2_ID if K == b else BYTEFRAY_RULESET_V4_ALPHA1_ID
            chunk_arg = None if K == b else K
            print("\n=======================================================")
            print(f"== Stage 1 Sweep: Budget b={b}, Grain K={K} (label={label}) ==")
            print("=======================================================")


            condition_data: dict[str, Any] = {
                "budget": b,
                "grain": K,
                "is_sequential": (K == b),
                "rosters": {},
                "pairwise": {},
                "timings": {},
            }

            # 1. Group focus rosters
            for r_id, roster in FOCUS_ROSTERS:
                target_dir = results_root / label / "group" / r_id
                req = EvaluationRequest(
                    candidate_id=roster[0],
                    opponent_ids=tuple(roster[1:]),
                    seeds=seeds,
                    output_dir=target_dir,
                    ticks=400,
                    data_root=output,
                    workers=workers,
                    ruleset_id=ruleset,
                    group=True,
                    instr_per_tick=b,
                    scheduler_chunk_size=chunk_arg,
                )
                elapsed, res = _run_eval(req)
                condition_data["timings"][f"group/{r_id}"] = elapsed
                print(f"  [Group] {r_id:36s} {elapsed:6.1f}s (cells: {len(res.cells)})")

                refs = [group_cell_ref_from_evaluation_cell(cell) for cell in res.cells if cell.is_group]
                report = analyze_group(roster, refs)

                # Collect match length & termination distribution from cells
                ticks_list = []
                term_reasons: dict[str, int] = {}
                for cell in res.cells:
                    if cell.ticks_run is not None:
                        ticks_list.append(cell.ticks_run)
                    res_path = cell.artifact_dir / "result.json"
                    if res_path.is_file():
                        try:
                            rd = json.loads(res_path.read_text(encoding="utf-8"))
                            reason = rd.get("reason", "unknown")
                            term_reasons[reason] = term_reasons.get(reason, 0) + 1
                        except Exception:
                            pass

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

                # Seat sensitivity per entrant
                seat_rates: dict[str, dict[str, Any]] = {}
                for s_sens in report.seat_sensitivity:
                    seat_rates[s_sens.agent_id] = {
                        "winner_rate_range": s_sens.winner_rate_range,
                        "survival_rate_range": s_sens.survival_rate_range,
                        "seat_win_rates": {s.scope_label: s.winner.rate for s in s_sens.by_seat},
                        "seat_survival_rates": {s.scope_label: s.survival.rate for s in s_sens.by_seat},
                    }


                condition_data["rosters"][r_id] = {
                    "roster": roster,
                    "entrants": entrants_data,
                    "seat_sensitivity": seat_rates,
                    "mean_ticks": sum(ticks_list) / len(ticks_list) if ticks_list else 0.0,
                    "termination_reasons": term_reasons,
                }

            # 2. Pairwise control
            for p_id, cand, opp, ticks in FOCUS_PAIRWISE:
                target_dir = results_root / label / "pairwise" / p_id
                req = EvaluationRequest(
                    candidate_id=cand,
                    opponent_ids=(opp,),
                    seeds=seeds,
                    output_dir=target_dir,
                    ticks=ticks,
                    data_root=output,
                    workers=workers,
                    ruleset_id=ruleset,
                    group=False,
                    both_orientations=True,
                    instr_per_tick=b,
                    scheduler_chunk_size=chunk_arg,
                )
                elapsed, res = _run_eval(req)
                condition_data["timings"][f"pairwise/{p_id}"] = elapsed
                print(f"  [Pair]  {p_id:36s} {elapsed:6.1f}s (cells: {len(res.cells)})")

                cand_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "all")
                cand_first_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "candidate_first")
                opp_first_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "opponent_first")
                total = cand_agg.matches_played

                condition_data["pairwise"][p_id] = {
                    "candidate": cand,
                    "opponent": opp,
                    "total_cells": total,
                    "win_rates": {
                        cand: cand_agg.wins / total if total else 0.0,
                        opp: cand_agg.losses / total if total else 0.0,
                        "ties": cand_agg.ties / total if total else 0.0,
                    },
                    "candidate_first_wins": cand_first_agg.wins,
                    "opponent_first_wins": opp_first_agg.wins,
                    "first_mover_advantage": (cand_first_agg.wins - opp_first_agg.wins) / (total / 2) if total else 0.0,
                }

            sweep_results[label] = condition_data

    out_file = results_root / "stage1_sweep_results.json"
    out_file.write_text(json.dumps(sweep_results, indent=2), encoding="utf-8")
    print(f"\nStage 1 sweep complete. Wrote structured results to {out_file}")
    return sweep_results


def run_stage2_corpus(
    output: Path,
    label: str,
    ruleset: str,
    chunk_size: int | None = None,
    rotate_start: bool = False,
    workers: int = 4,
) -> dict[str, Any]:
    """Run full 1080-cell benchmark corpus under specified scheduler configuration."""
    results_dir = output / "stage2" / label
    population = load_population()
    stage_population(population, output)

    corpus = get_corpus_def()
    timings: dict[str, float] = {}

    group = corpus["group"]
    seeds = tuple(int(s) for s in group["seeds"])
    print(f"\n== Stage 2 Corpus: {label} (ruleset={ruleset}, chunk_size={chunk_size}, rotate_start={rotate_start}) ==")
    
    rosters_data: dict[str, Any] = {}
    for entry in group["rosters"]:
        roster = entry["roster"]
        target_dir = results_dir / "group" / entry["id"]
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
            scheduler_chunk_size=chunk_size,
            scheduler_rotate_start=rotate_start,
        )
        elapsed, res = _run_eval(req)
        timings[f"group/{entry['id']}"] = elapsed
        print(f"  [Group] {entry['id']:36s} {elapsed:6.1f}s")

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

        seat_rates: dict[str, dict[str, Any]] = {}
        for s_sens in report.seat_sensitivity:
            seat_rates[s_sens.agent_id] = {
                "winner_rate_range": s_sens.winner_rate_range,
                "survival_rate_range": s_sens.survival_rate_range,
                "seat_win_rates": {s.scope_label: s.winner.rate for s in s_sens.by_seat},
                "seat_survival_rates": {s.scope_label: s.survival.rate for s in s_sens.by_seat},
            }


        rosters_data[entry["id"]] = {
            "roster": roster,
            "entrants": entrants_data,
            "seat_sensitivity": seat_rates,
            "layout_sensitivity": {s.agent_id: s.winner_rate_range for s in report.layout_sensitivity},
        }

    pairwise_data: dict[str, Any] = {}
    pairwise = corpus["pairwise"]
    pair_seeds = tuple(int(s) for s in pairwise["seeds"])
    for entry in pairwise["pairs"]:
        target_dir = results_dir / "pairwise" / entry["id"]
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
            scheduler_chunk_size=chunk_size,
            scheduler_rotate_start=rotate_start,
        )
        elapsed, res = _run_eval(req)
        timings[f"pairwise/{entry['id']}"] = elapsed
        print(f"  [Pair]  {entry['id']:36s} {elapsed:6.1f}s")

        cand_name = entry["candidate"]
        opp_name = entry["opponent"]
        cand_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "all")
        cand_first_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "candidate_first")
        opp_first_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "opponent_first")
        total = cand_agg.matches_played

        pairwise_data[entry["id"]] = {
            "candidate": cand_name,
            "opponent": opp_name,
            "total_cells": total,
            "win_rates": {
                cand_name: cand_agg.wins / total if total else 0.0,
                opp_name: cand_agg.losses / total if total else 0.0,
                "ties": cand_agg.ties / total if total else 0.0,
            },
            "candidate_first_wins": cand_first_agg.wins,
            "opponent_first_wins": opp_first_agg.wins,
        }

    summary = {
        "label": label,
        "ruleset": ruleset,
        "chunk_size": chunk_size,
        "rotate_start": rotate_start,
        "timings": timings,
        "total_time": sum(timings.values()),
        "rosters": rosters_data,
        "pairwise": pairwise_data,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="v4 Scheduler Grain Qualification Tool")
    parser.add_argument("--mode", choices=["stage1", "stage2", "all"], default="stage1")
    parser.add_argument("--output", type=Path, default=REPO / "runs" / "research_v4_r0b")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    if args.mode in ("stage1", "all"):
        run_stage1_sweep(args.output, workers=args.workers)

    if args.mode in ("stage2", "all"):
        # Stage 2: Evaluate K=8 control, K=1 reference, K=2, K=4, and K=2 with rotating start
        run_stage2_corpus(args.output, "k8_sequential_control", BYTEFRAY_RULESET_V2_ID, chunk_size=None, rotate_start=False, workers=args.workers)
        run_stage2_corpus(args.output, "k1_interleaved_ref", BYTEFRAY_RULESET_V4_ALPHA1_ID, chunk_size=1, rotate_start=False, workers=args.workers)
        run_stage2_corpus(args.output, "k2_chunked", BYTEFRAY_RULESET_V4_ALPHA1_ID, chunk_size=2, rotate_start=False, workers=args.workers)
        run_stage2_corpus(args.output, "k4_chunked", BYTEFRAY_RULESET_V4_ALPHA1_ID, chunk_size=4, rotate_start=False, workers=args.workers)
        run_stage2_corpus(args.output, "k2_chunked_rotating", BYTEFRAY_RULESET_V4_ALPHA1_ID, chunk_size=2, rotate_start=True, workers=args.workers)


if __name__ == "__main__":
    main()
