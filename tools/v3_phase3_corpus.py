"""v3 Phase 3H/3J -- build the rescored corpus and score it against the
predeclared gates.

Phase 3C proved trajectory invariance for the frozen v2-baseline population
under a kill-weight sweep, and Phase 3D validated that offline rescoring
exactly reproduces real production execution for the sampled cells. This
module therefore builds the Phase 3 group-ecology and pairwise-control
corpus by *exact rescoring* of the already-committed Phase 1 default-
condition corpus (``runs/research_v3_phase1/main/results/a4096_b8``) at
each predeclared kill weight, rather than by re-executing 2,592 cells four
times over.

K0 (``w_kill = 5``) is not rescored at all -- it *is* the committed Phase 1
default condition, reused directly, which is what proves K0 reproduces the
Phase 1 control exactly (Phase 3T Sec 10) rather than merely resembling it.

For each of K1/K2/K3, only ``result.json`` (small JSON) is rescored and
written under ``runs/research_v3_phase3/rescored/<K>/``; no replay is
copied or regenerated, per Phase 3S's artifact-discipline instruction.

Usage::

    python tools/v3_phase3_corpus.py build
    python tools/v3_phase3_corpus.py analyze
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase1_arena_action_grid as grid
import v3_phase3_rescore as rescore

PHASE1_RESULTS = REPO / "runs" / "research_v3_phase1" / "main" / "results"
DEFAULT_CONDITION_ID = "a4096_b8"
OUTPUT_ROOT = REPO / "runs" / "research_v3_phase3"
RESCORED_ROOT = OUTPUT_ROOT / "rescored"

GROUP_ROSTERS: tuple[str, ...] = (
    "claimer_coredefender_reactive",
    "claimer_coreseeker_hunter",
    "claimer_coretracker_coredefender",
    "claimer_coretracker_hunter",
    "claimer_coretracker_reactive",
    "claimer_hunter_coredefender",
    "claimer_hunter_reactive",
    "coredefender_reactive_coreseeker",
    "hunter_coretracker_coredefender",
    "hunter_coretracker_coreseeker",
    "reactive_hunter_coreseeker",
)

PAIRWISE_PAIRS: dict[str, tuple[str, str]] = {
    "claimer_vs_coretracker_400": ("claimer", "core_tracker"),
    "claimer_vs_hunter_400": ("claimer", "hunter"),
    "hunter_vs_coretracker_400": ("hunter", "core_tracker"),
}

# Predeclared Phase 3E kill weights, K0 first (the reference/reused condition).
KILL_WEIGHTS: dict[str, float] = {"K0": 5.0, "K1": 400.0, "K2": 1600.0, "K3": 3200.0}

# Phase 3L MODIFY-rule interpolation: at most two new values, both strictly
# inside the bracket the primary sweep identified as ambiguous (G3/G4
# passing only at K2=1600 while G5 fails there and passes at K1=400,
# suggesting the useful region -- if one exists -- lies strictly between
# the two). Declared only after K0-K3 were scored, per Phase 3L; K0-K3
# themselves are never altered. Not part of the primary predeclared sweep.
MODIFY_KILL_WEIGHTS: dict[str, float] = {"M1": 800.0, "M2": 1200.0}
ARENA_SIZE = 4096
INSTR_PER_TICK = 8


def _condition_dict(condition_id: str) -> dict[str, Any]:
    return {"id": condition_id, "arena_size": ARENA_SIZE, "instr_per_tick": INSTR_PER_TICK}


def build_group_condition(label: str, weight: float) -> None:
    for roster in GROUP_ROSTERS:
        src_eval_path = PHASE1_RESULTS / DEFAULT_CONDITION_ID / "group" / roster / "evaluation.json"
        data = json.loads(src_eval_path.read_text(encoding="utf-8"))
        dst_dir = RESCORED_ROOT / label / "group" / roster
        for cell in data["cells"]:
            artifact_dir = cell["artifact_dir"]
            src_result = src_eval_path.parent / artifact_dir / "result.json"
            dst_result = dst_dir / artifact_dir / "result.json"
            rescore.rescore_result_file(src_result, dst_result, weight)
        conditions = data.get("effective_conditions")
        if isinstance(conditions, dict) and isinstance(conditions.get("weights"), dict):
            conditions["weights"]["kill"] = weight
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / "evaluation.json").write_text(json.dumps(data), encoding="utf-8")


def build_pairwise_condition(label: str, weight: float) -> None:
    for pair_id in PAIRWISE_PAIRS:
        src_eval_path = PHASE1_RESULTS / DEFAULT_CONDITION_ID / "pairwise" / pair_id / "evaluation.json"
        data = json.loads(src_eval_path.read_text(encoding="utf-8"))
        new_cells = []
        for cell in data["cells"]:
            cell = dict(cell)
            if cell.get("status") == "completed" and cell.get("outcome") in ("win", "loss", "tie"):
                result_path = src_eval_path.parent / cell["artifact_dir"] / "result.json"
                original = json.loads(result_path.read_text(encoding="utf-8"))
                cell["outcome"] = rescore.rescore_pairwise_outcome(
                    original, weight, subject_id=cell["subject_id"], opponent_id=cell["opponent_id"]
                )
            # `artifact_dir` is left pointing at the ORIGINAL committed match
            # directory (absolute) so `_match_shape` reads the real,
            # trajectory-invariant result.json for cpu/territory/termination
            # stats directly -- only `outcome` (score-derived) is rescored.
            cell["artifact_dir"] = str((src_eval_path.parent / cell["artifact_dir"]).resolve())
            new_cells.append(cell)
        data["cells"] = new_cells
        conditions = data.get("effective_conditions")
        if isinstance(conditions, dict) and isinstance(conditions.get("weights"), dict):
            conditions["weights"]["kill"] = weight
        dst_dir = RESCORED_ROOT / label / "pairwise" / pair_id
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / "evaluation.json").write_text(json.dumps(data), encoding="utf-8")


def all_weights() -> dict[str, float]:
    combined = dict(KILL_WEIGHTS)
    combined.update(MODIFY_KILL_WEIGHTS)
    return combined


def build(weights: dict[str, float] | None = None) -> None:
    for label, weight in (weights or all_weights()).items():
        if weight == rescore.DEFAULT_KILL_WEIGHT:
            continue  # K0 reuses the committed Phase 1 corpus directly.
        build_group_condition(label, weight)
        build_pairwise_condition(label, weight)
        print(f"built rescored corpus for {label} (w_kill={weight})")


def _results_root_for(label: str, weight: float) -> Path:
    return PHASE1_RESULTS if weight == rescore.DEFAULT_KILL_WEIGHT else RESCORED_ROOT


def _condition_id_for(label: str, weight: float) -> str:
    return DEFAULT_CONDITION_ID if weight == rescore.DEFAULT_KILL_WEIGHT else label


def analyze(weights: dict[str, float] | None = None) -> dict[str, Any]:
    weights = weights or all_weights()
    report: dict[str, Any] = {"group": [], "pairwise": []}
    for label, weight in weights.items():
        results_root = _results_root_for(label, weight)
        condition = _condition_dict(_condition_id_for(label, weight))
        for roster in GROUP_ROSTERS:
            roster_agents = roster_agent_ids(roster)
            entry = grid.analyze_roster(roster, roster_agents, condition, results_root)
            if entry is None:
                raise SystemExit(f"missing group analysis for {label}/{roster}")
            entry["condition_id"] = label
            entry["kill_weight"] = weight
            report["group"].append(entry)
        for pair_id, (candidate, opponent) in PAIRWISE_PAIRS.items():
            entry = grid.analyze_pair(
                pair_id, {"candidate": candidate, "opponent": opponent}, condition, results_root
            )
            if entry is None:
                raise SystemExit(f"missing pairwise analysis for {label}/{pair_id}")
            entry["condition_id"] = label
            entry["kill_weight"] = weight
            report["pairwise"].append(entry)
    return report


def roster_agent_ids(roster_id: str) -> list[str]:
    src_eval_path = PHASE1_RESULTS / DEFAULT_CONDITION_ID / "group" / roster_id / "evaluation.json"
    data = json.loads(src_eval_path.read_text(encoding="utf-8"))
    return list(data["roster_agent_ids"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "analyze"))
    args = parser.parse_args(argv)

    if args.command == "build":
        build()
        return 0

    analysis = analyze()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT_ROOT / "phase3_analysis.json"
    destination.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    print(f"wrote {destination}")
    print(f"group entries: {len(analysis['group'])}, pairwise entries: {len(analysis['pairwise'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
