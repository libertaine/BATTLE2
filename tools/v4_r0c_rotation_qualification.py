"""v4 Research Tool: Driver for R0c Starting-Seat Rotation Qualification.

Conducts comprehensive qualification of deterministic starting-seat rotation
over candidate grain K=2 against fixed K=2 scheduling.
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
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V4_ALPHA1_ID


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


def run_r0c_qualification(output: Path, workers: int = 4) -> dict[str, Any]:
    """Execute complete R0c qualification comparing K=2 Fixed vs K=2 Rotating."""
    results_root = output / "r0c_qualification"
    population = load_population()
    stage_population(population, output)

    corpus = get_corpus_def()
    group_def = corpus["group"]
    pairwise_def = corpus["pairwise"]

    seeds = tuple(int(s) for s in group_def["seeds"])
    pair_seeds = tuple(int(s) for s in pairwise_def["seeds"])

    configurations = [
        ("k2_fixed", False),
        ("k2_rotating", True),
    ]

    all_results: dict[str, Any] = {}

    for config_label, rotate_start in configurations:
        print("\n=======================================================")
        print(f"== Running Full 1080-Cell Corpus: {config_label} (rotate_start={rotate_start}) ==")
        print("=======================================================")

        config_data: dict[str, Any] = {
            "config_label": config_label,
            "rotate_start": rotate_start,
            "chunk_size": 2,
            "rosters": {},
            "pairwise": {},
            "timings": {},
            "modulo_n_analysis": {},
        }

        # 1. Group Rosters (11 rosters x 90 cells = 990 cells)
        for entry in group_def["rosters"]:
            roster = entry["roster"]
            r_id = entry["id"]
            target_dir = results_root / config_label / "group" / r_id
            req = EvaluationRequest(
                candidate_id=roster[0],
                opponent_ids=tuple(roster[1:]),
                seeds=seeds,
                output_dir=target_dir,
                ticks=group_def["ticks"],
                data_root=output,
                workers=workers,
                ruleset_id=BYTEFRAY_RULESET_V4_ALPHA1_ID,
                group=True,
                scheduler_chunk_size=2,
                scheduler_rotate_start=rotate_start,
            )
            elapsed, res = _run_eval(req)
            config_data["timings"][f"group/{r_id}"] = elapsed
            print(f"  [Group] {r_id:36s} {elapsed:6.1f}s (cells: {len(res.cells)})")

            refs = [group_cell_ref_from_evaluation_cell(cell) for cell in res.cells if cell.is_group]
            report = analyze_group(roster, refs)

            # Match lengths, termination reasons, and modulo-N distribution
            n_entrants = len(roster)
            ticks_list = []
            term_reasons: dict[str, int] = {}
            mod_n_winners: dict[int, dict[str, int]] = {m: {} for m in range(n_entrants)}

            for cell in res.cells:

                if cell.ticks_run is not None:
                    ticks_list.append(cell.ticks_run)
                    mod_val = cell.ticks_run % n_entrants
                res_path = cell.artifact_dir / "result.json"
                if res_path.is_file():
                    try:
                        rd = json.loads(res_path.read_text(encoding="utf-8"))
                        reason = rd.get("reason", "unknown")
                        term_reasons[reason] = term_reasons.get(reason, 0) + 1
                        winner = rd.get("winner", "none")
                        if cell.ticks_run is not None:
                            mod_n_winners[mod_val][winner] = mod_n_winners[mod_val].get(winner, 0) + 1
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

            seat_rates: dict[str, dict[str, Any]] = {}
            for s_sens in report.seat_sensitivity:
                seat_rates[s_sens.agent_id] = {
                    "winner_rate_range": s_sens.winner_rate_range,
                    "survival_rate_range": s_sens.survival_rate_range,
                    "seat_win_rates": {s.scope_label: s.winner.rate for s in s_sens.by_seat},
                    "seat_survival_rates": {s.scope_label: s.survival.rate for s in s_sens.by_seat},
                }

            config_data["rosters"][r_id] = {
                "roster": roster,
                "entrants": entrants_data,
                "seat_sensitivity": seat_rates,
                "layout_sensitivity": {s.agent_id: s.winner_rate_range for s in report.layout_sensitivity},
                "mean_ticks": sum(ticks_list) / len(ticks_list) if ticks_list else 0.0,
                "termination_reasons": term_reasons,
                "mod_n_winners": mod_n_winners,
            }

        # 2. Pairwise Controls (9 pairwise controls = 450 cells)
        for entry in pairwise_def["pairs"]:
            p_id = entry["id"]
            cand = entry["candidate"]
            opp = entry["opponent"]
            target_dir = results_root / config_label / "pairwise" / p_id
            req = EvaluationRequest(
                candidate_id=cand,
                opponent_ids=(opp,),
                seeds=pair_seeds,
                output_dir=target_dir,
                ticks=entry["ticks"],
                data_root=output,
                workers=workers,
                ruleset_id=BYTEFRAY_RULESET_V4_ALPHA1_ID,
                group=False,
                both_orientations=True,
                scheduler_chunk_size=2,
                scheduler_rotate_start=rotate_start,
            )
            elapsed, res = _run_eval(req)
            config_data["timings"][f"pairwise/{p_id}"] = elapsed
            print(f"  [Pair]  {p_id:36s} {elapsed:6.1f}s (cells: {len(res.cells)})")

            cand_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "all")
            cand_first_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "candidate_first")
            opp_first_agg = next(a for a in res.aggregates if a.subject_role == "candidate" and a.orientation_scope == "opponent_first")
            total = cand_agg.matches_played

            config_data["pairwise"][p_id] = {
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

        all_results[config_label] = config_data

    out_file = results_root / "r0c_qualification_results.json"
    out_file.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\nR0c qualification complete. Structured results written to {out_file}")
    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="v4 Starting-Seat Rotation Qualification Tool")
    parser.add_argument("--output", type=Path, default=REPO / "runs" / "research_v4_r0c")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    run_r0c_qualification(args.output, workers=args.workers)


if __name__ == "__main__":
    main()
