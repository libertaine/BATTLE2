"""v3 Phase 4 -- build the defense-payoff corpus at Phase 3's fixed offense
payoff (w_kill = 1600), sweeping w_territory, by exact rescoring of the
committed Phase 1 default-condition corpus.

T0 (w_territory=1.0) is exactly Phase 3's own K2 condition -- reused
directly from `runs/research_v3_phase3/rescored/K2`, not rebuilt, for the
identical reason K0 reused the Phase 1 corpus directly in Phase 3.

Usage::

    python tools/v3_phase4_corpus.py build
    python tools/v3_phase4_corpus.py analyze
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
import v3_phase3_corpus as p3corpus
import v3_phase4_rescore as rescore

PHASE1_RESULTS = REPO / "runs" / "research_v3_phase1" / "main" / "results"
DEFAULT_CONDITION_ID = "a4096_b8"
PHASE3_K2_ROOT = REPO / "runs" / "research_v3_phase3" / "rescored"
OUTPUT_ROOT = REPO / "runs" / "research_v3_phase4"
RESCORED_ROOT = OUTPUT_ROOT / "rescored"

GROUP_ROSTERS = p3corpus.GROUP_ROSTERS
PAIRWISE_PAIRS = p3corpus.PAIRWISE_PAIRS
ARENA_SIZE = p3corpus.ARENA_SIZE
INSTR_PER_TICK = p3corpus.INSTR_PER_TICK

FIXED_KILL_WEIGHT = rescore.FIXED_KILL_WEIGHT  # 1600.0, Phase 3's accepted offense payoff

# Predeclared Phase 4 territory weights. T0 is Phase 3's own K2 (w_territory
# at its shipped default, 1.0) -- the reference condition, reused not
# rebuilt. T1/T2 are derived from the measured economics
# (docs/V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md Sec 3): defense's
# realized territory deficit against the leading archetype is small
# (2-7pp at K2), so a moderate (5x) and a large/saturating (20x) multiplier
# bracket whether *any* magnitude of this lever can compensate it without
# re-diluting the Phase 3 kill payoff.
TERRITORY_WEIGHTS: dict[str, float] = {"T0": 1.0, "T1": 5.0, "T2": 20.0}


def _condition_dict(condition_id: str) -> dict[str, Any]:
    return {"id": condition_id, "arena_size": ARENA_SIZE, "instr_per_tick": INSTR_PER_TICK}


def _results_root_for(label: str, weight: float) -> Path:
    if weight == 1.0:
        return PHASE3_K2_ROOT
    return RESCORED_ROOT


def _condition_id_for(label: str, weight: float) -> str:
    return "K2" if weight == 1.0 else label


def build_group_condition(label: str, w_territory: float) -> None:
    for roster in GROUP_ROSTERS:
        src_eval_path = PHASE1_RESULTS / DEFAULT_CONDITION_ID / "group" / roster / "evaluation.json"
        data = json.loads(src_eval_path.read_text(encoding="utf-8"))
        dst_dir = RESCORED_ROOT / label / "group" / roster
        for cell in data["cells"]:
            artifact_dir = cell["artifact_dir"]
            src_result = src_eval_path.parent / artifact_dir / "result.json"
            dst_result = dst_dir / artifact_dir / "result.json"
            rescore.rescore_result_file_general(
                src_result, dst_result, w_alive=1.0, w_kill=FIXED_KILL_WEIGHT, w_territory=w_territory
            )
        conditions = data.get("effective_conditions")
        if isinstance(conditions, dict) and isinstance(conditions.get("weights"), dict):
            conditions["weights"]["kill"] = FIXED_KILL_WEIGHT
            conditions["weights"]["territory"] = w_territory
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / "evaluation.json").write_text(json.dumps(data), encoding="utf-8")


def build_pairwise_condition(label: str, w_territory: float) -> None:
    for pair_id in PAIRWISE_PAIRS:
        src_eval_path = PHASE1_RESULTS / DEFAULT_CONDITION_ID / "pairwise" / pair_id / "evaluation.json"
        data = json.loads(src_eval_path.read_text(encoding="utf-8"))
        new_cells = []
        for cell in data["cells"]:
            cell = dict(cell)
            if cell.get("status") == "completed" and cell.get("outcome") in ("win", "loss", "tie"):
                result_path = src_eval_path.parent / cell["artifact_dir"] / "result.json"
                original = json.loads(result_path.read_text(encoding="utf-8"))
                cell["outcome"] = rescore.rescore_pairwise_outcome_general(
                    original,
                    w_alive=1.0,
                    w_kill=FIXED_KILL_WEIGHT,
                    w_territory=w_territory,
                    subject_id=cell["subject_id"],
                    opponent_id=cell["opponent_id"],
                )
            cell["artifact_dir"] = str((src_eval_path.parent / cell["artifact_dir"]).resolve())
            new_cells.append(cell)
        data["cells"] = new_cells
        conditions = data.get("effective_conditions")
        if isinstance(conditions, dict) and isinstance(conditions.get("weights"), dict):
            conditions["weights"]["kill"] = FIXED_KILL_WEIGHT
            conditions["weights"]["territory"] = w_territory
        dst_dir = RESCORED_ROOT / label / "pairwise" / pair_id
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / "evaluation.json").write_text(json.dumps(data), encoding="utf-8")


def build() -> None:
    for label, weight in TERRITORY_WEIGHTS.items():
        if weight == 1.0:
            continue  # T0 reuses Phase 3's own K2 directly.
        build_group_condition(label, weight)
        build_pairwise_condition(label, weight)
        print(f"built rescored corpus for {label} (w_territory={weight}, w_kill fixed at {FIXED_KILL_WEIGHT})")


def analyze() -> dict[str, Any]:
    report: dict[str, Any] = {"group": [], "pairwise": []}
    for label, weight in TERRITORY_WEIGHTS.items():
        results_root = _results_root_for(label, weight)
        condition = _condition_dict(_condition_id_for(label, weight))
        for roster in GROUP_ROSTERS:
            roster_agents = p3corpus.roster_agent_ids(roster)
            entry = grid.analyze_roster(roster, roster_agents, condition, results_root)
            if entry is None:
                raise SystemExit(f"missing group analysis for {label}/{roster}")
            entry["condition_id"] = label
            entry["territory_weight"] = weight
            report["group"].append(entry)
        for pair_id, (candidate, opponent) in PAIRWISE_PAIRS.items():
            entry = grid.analyze_pair(
                pair_id, {"candidate": candidate, "opponent": opponent}, condition, results_root
            )
            if entry is None:
                raise SystemExit(f"missing pairwise analysis for {label}/{pair_id}")
            entry["condition_id"] = label
            entry["territory_weight"] = weight
            report["pairwise"].append(entry)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "analyze"))
    args = parser.parse_args(argv)

    if args.command == "build":
        build()
        return 0

    analysis = analyze()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT_ROOT / "phase4_analysis.json"
    destination.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    print(f"wrote {destination}")
    print(f"group entries: {len(analysis['group'])}, pairwise entries: {len(analysis['pairwise'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
