"""v3 Phase 3C -- execution-invariance check for the kill-weight lever.

Determines whether changing ``Weights.kill`` can affect the *trajectory* of
a frozen match before final score/winner resolution, for a representative
sample of real cells drawn from the committed Phase 1 default-condition
corpus (``runs/research_v3_phase1/main/results/a4096_b8``).

For each sampled cell, re-executes the identical match (same agents, source
revisions, seed, arena, action budget, tick limit, entrant order,
placements/layout) at every predeclared kill weight
(docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md Sec Phase 3E: 5, 400,
1600, 3200) and diffs everything *except* score-derived fields:

* per-tick agent states (pc, alive, cpu_used, mem_writes, region,
  register_a, register_p, zero_flag, last_read, termination_reason);
* memory diffs (address, length, owner, values);
* engine events (kill/death attribution);
* tick count / termination reason / winner;
* final per-entrant statistics excluding ``score``.

If every non-score field is identical across all four weights for every
sampled cell, the frozen benchmark's trajectories are proven invariant to
this lever, and a kill-weight sweep over the *already committed* Phase 1
replay/result corpus is a pure scoring intervention -- Phase 3D's offline
rescoring path is then legitimate broad evidence, validated against these
same representative real executions.

Usage::

    python tools/v3_phase3_execution_invariance.py \\
        --output runs/research_v3_phase3/execution_invariance
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine" / "src"))

from battle_engine import benchmarks
from battle_engine.agent_test import GroupEntrantSpec, test_agent, test_agents
from battle_engine.replay import iter_replay
from battle_engine.result_model import read_result

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE1_DEFAULT = REPO_ROOT / "runs" / "research_v3_phase1" / "main" / "results" / "a4096_b8"

KILL_WEIGHTS = (5.0, 400.0, 1600.0, 3200.0)

RULESET_V2 = "bytefray-rules-2"

# Curated, representative sample: one capture cell and one non-capture cell
# per group roster where both exist (claimer_coredefender_reactive never
# captures -- Phase 0/1's own negative control; hunter_coretracker_coreseeker
# captures in every sampled cell -- an offense-heavy roster), plus one cell
# from each of the three pairwise controls. Selected by
# ``tools/v3_phase3_execution_invariance.py --rescan`` against the committed
# corpus; pinned here for a stable, auditable sample.
GROUP_CELLS: tuple[dict[str, Any], ...] = (
    {"roster": "claimer_coredefender_reactive", "seat_agent_ids": ["claimer", "core_defender", "reactive_core_defender"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "claimer_coreseeker_hunter", "seat_agent_ids": ["claimer", "core_seeker", "hunter"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "capture"},
    {"roster": "claimer_coreseeker_hunter", "seat_agent_ids": ["hunter", "claimer", "core_seeker"], "seat_starts": [0, 682, 1364], "seed": 1, "tag": "no_capture"},
    {"roster": "claimer_coretracker_coredefender", "seat_agent_ids": ["claimer", "core_defender", "core_tracker"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "capture"},
    {"roster": "claimer_coretracker_coredefender", "seat_agent_ids": ["claimer", "core_tracker", "core_defender"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "claimer_coretracker_hunter", "seat_agent_ids": ["claimer", "hunter", "core_tracker"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "capture"},
    {"roster": "claimer_coretracker_hunter", "seat_agent_ids": ["claimer", "core_tracker", "hunter"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "claimer_coretracker_reactive", "seat_agent_ids": ["claimer", "reactive_core_defender", "core_tracker"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "capture"},
    {"roster": "claimer_coretracker_reactive", "seat_agent_ids": ["claimer", "core_tracker", "reactive_core_defender"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "claimer_hunter_coredefender", "seat_agent_ids": ["hunter", "core_defender", "claimer"], "seat_starts": [0, 682, 1364], "seed": 1, "tag": "capture"},
    {"roster": "claimer_hunter_coredefender", "seat_agent_ids": ["claimer", "hunter", "core_defender"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "claimer_hunter_reactive", "seat_agent_ids": ["hunter", "reactive_core_defender", "claimer"], "seat_starts": [0, 682, 1364], "seed": 1, "tag": "capture"},
    {"roster": "claimer_hunter_reactive", "seat_agent_ids": ["claimer", "hunter", "reactive_core_defender"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "coredefender_reactive_coreseeker", "seat_agent_ids": ["core_defender", "core_seeker", "reactive_core_defender"], "seat_starts": [682, 2047, 3412], "seed": 1, "tag": "capture"},
    {"roster": "coredefender_reactive_coreseeker", "seat_agent_ids": ["core_defender", "reactive_core_defender", "core_seeker"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "hunter_coretracker_coredefender", "seat_agent_ids": ["hunter", "core_tracker", "core_defender"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "capture"},
    {"roster": "hunter_coretracker_coredefender", "seat_agent_ids": ["core_tracker", "hunter", "core_defender"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "hunter_coretracker_coreseeker", "seat_agent_ids": ["hunter", "core_tracker", "core_seeker"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "capture"},
    {"roster": "reactive_hunter_coreseeker", "seat_agent_ids": ["reactive_core_defender", "hunter", "core_seeker"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "capture"},
    {"roster": "reactive_hunter_coreseeker", "seat_agent_ids": ["reactive_core_defender", "core_seeker", "hunter"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
)

PAIRWISE_CELLS: tuple[dict[str, Any], ...] = (
    {"pair": "claimer_vs_coretracker_400", "subject_id": "claimer", "opponent_id": "core_tracker", "subject_start": 0, "opponent_start": 2048, "seed": 1},
    {"pair": "claimer_vs_hunter_400", "subject_id": "claimer", "opponent_id": "hunter", "subject_start": 0, "opponent_start": 2048, "seed": 1},
    {"pair": "hunter_vs_coretracker_400", "subject_id": "hunter", "opponent_id": "core_tracker", "subject_start": 0, "opponent_start": 2048, "seed": 1},
)

TICKS = 400
ARENA_SIZE = 4096
INSTR_PER_TICK = 8

# Fields legitimately allowed to differ across kill weights: `score` is
# score-derived (the very thing under test); `weights`, `match_id`,
# `result_id`, and `replay_id` are legitimately identity-bearing (Phase 3B
# deliberately makes weights vary canonical identity, exactly like
# arena_size/instr_per_tick before it) -- their divergence is proof the
# plumbing works, not evidence against trajectory invariance, which this
# script checks over everything else: actions' effects (writes/memory
# diffs), captures, death timing, tick count, and raw statistics.
EXCLUDED_FIELDS = {
    "score",
    "weights",
    "match_id",
    "result_id",
    "replay_id",
    # `result.json`'s `replay.sha256` is a digest of the *whole replay
    # file's bytes*, which legitimately differ because the replay header's
    # `reproducibility`/`config.weights` and terminal result record's
    # `score` legitimately differ -- this key is a stand-in for "the
    # artifact differs", not "the trajectory differs".
    "sha256",
    # Phase 3C explicitly permits winner resolution to differ -- it is
    # downstream of score, and a weight-driven winner flip on a captured
    # match is the causal effect this whole phase is testing for, not a
    # trajectory violation. Tracked separately as `winner_changed` below,
    # never folded into `trajectory_invariant`.
    "winner",
    "outcome",
}


def _strip_scores(record: Any) -> Any:
    """Recursively drop every score- or identity-bearing field named above."""

    if is_dataclass(record) and not isinstance(record, type):
        record = asdict(record)
    if isinstance(record, dict):
        return {
            key: _strip_scores(value)
            for key, value in record.items()
            if key not in EXCLUDED_FIELDS
        }
    if isinstance(record, (list, tuple)):
        return [_strip_scores(item) for item in record]
    return record


def _replay_trajectory(replay_path: Path) -> list[Any]:
    return [_strip_scores(record) for record in iter_replay(replay_path)]


def _result_trajectory(result_path: Path) -> dict[str, Any]:
    envelope = read_result(result_path)
    payload = asdict(envelope) if is_dataclass(envelope) else envelope.as_dict()
    payload.pop("result_id", None)
    payload.pop("match_id", None)
    return _strip_scores(payload)


def _run_group_cell(cell: dict[str, Any], kill_weight: float, out_dir: Path, data_root: Path) -> Path:
    entrants = [
        GroupEntrantSpec(seat=chr(ord("A") + i), agent_id=agent_id, start=start)
        for i, (agent_id, start) in enumerate(
            zip(cell["seat_agent_ids"], cell["seat_starts"], strict=True)
        )
    ]
    run_dir = out_dir / f"group-{cell['roster']}-{cell['tag']}-k{kill_weight:g}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    test_agents(
        entrants,
        seed=cell["seed"],
        ticks=TICKS,
        trace=False,
        run_dir=run_dir,
        data_root=data_root,
        ruleset_id=RULESET_V2,
        arena_size=ARENA_SIZE,
        instr_per_tick=INSTR_PER_TICK,
        kill_weight=kill_weight,
    )
    return run_dir


def _run_pairwise_cell(cell: dict[str, Any], kill_weight: float, out_dir: Path, data_root: Path) -> Path:
    run_dir = out_dir / f"pairwise-{cell['pair']}-k{kill_weight:g}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    test_agent(
        cell["subject_id"],
        opponent=cell["opponent_id"],
        seed=cell["seed"],
        ticks=TICKS,
        trace=False,
        run_dir=run_dir,
        data_root=data_root,
        ruleset_id=RULESET_V2,
        agent_start=cell["subject_start"],
        opponent_start=cell["opponent_start"],
        arena_size=ARENA_SIZE,
        instr_per_tick=INSTR_PER_TICK,
        kill_weight=kill_weight,
    )
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "runs" / "research_v3_phase3" / "execution_invariance")
    args = parser.parse_args()

    data_root = args.output / "_agents"
    data_root.mkdir(parents=True, exist_ok=True)
    population = benchmarks.load_population(benchmarks.V2_BASELINE_ID)
    benchmarks.stage_population(population, data_root)

    report: dict[str, Any] = {"cells": [], "summary": {}}
    invariant_cells = 0
    divergent_cells: list[str] = []
    score_changed_cells = 0
    winner_changed_cells: list[str] = []

    all_cells: list[tuple[str, dict[str, Any], Any]] = [
        (f"group:{c['roster']}:{c['tag']}", c, _run_group_cell) for c in GROUP_CELLS
    ] + [(f"pairwise:{c['pair']}", c, _run_pairwise_cell) for c in PAIRWISE_CELLS]

    for label, cell, runner in all_cells:
        run_dirs: dict[float, Path] = {}
        for weight in KILL_WEIGHTS:
            run_dirs[weight] = runner(cell, weight, data_root.parent, data_root)

        baseline_weight = KILL_WEIGHTS[0]
        baseline_replay = _replay_trajectory(run_dirs[baseline_weight] / "replay.jsonl")
        baseline_result = _result_trajectory(run_dirs[baseline_weight] / "result.json")

        cell_record: dict[str, Any] = {"label": label, "kill_weights": {}}
        cell_invariant = True
        cell_score_changed = False
        cell_winner_changed = False
        raw_baseline = json.loads((run_dirs[baseline_weight] / "result.json").read_text(encoding="utf-8"))
        for weight in KILL_WEIGHTS[1:]:
            replay = _replay_trajectory(run_dirs[weight] / "replay.jsonl")
            result = _result_trajectory(run_dirs[weight] / "result.json")
            replay_match = replay == baseline_replay
            result_match = result == baseline_result
            if not (replay_match and result_match):
                cell_invariant = False
            raw_current = json.loads((run_dirs[weight] / "result.json").read_text(encoding="utf-8"))
            if raw_baseline.get("score") != raw_current.get("score"):
                cell_score_changed = True
            if raw_baseline.get("winner") != raw_current.get("winner"):
                cell_winner_changed = True
            cell_record["kill_weights"][weight] = {
                "trajectory_identical_to_k0": replay_match and result_match,
                "score_map": raw_current.get("score"),
                "winner": raw_current.get("winner"),
            }
        cell_record["kill_weights"][baseline_weight] = {
            "trajectory_identical_to_k0": True,
            "score_map": raw_baseline.get("score"),
            "winner": raw_baseline.get("winner"),
        }
        cell_record["trajectory_invariant"] = cell_invariant
        cell_record["score_changed_by_weight"] = cell_score_changed
        cell_record["winner_changed_by_weight"] = cell_winner_changed
        report["cells"].append(cell_record)
        if cell_invariant:
            invariant_cells += 1
        else:
            divergent_cells.append(label)
        if cell_score_changed:
            score_changed_cells += 1
        if cell_winner_changed:
            winner_changed_cells.append(label)

    report["summary"] = {
        "total_cells": len(all_cells),
        "trajectory_invariant_cells": invariant_cells,
        "divergent_cells": divergent_cells,
        "score_changed_cells": score_changed_cells,
        "winner_changed_cells": winner_changed_cells,
        "kill_weights_tested": list(KILL_WEIGHTS),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "execution_invariance_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )

    print(f"cells tested: {report['summary']['total_cells']}")
    print(f"trajectory-invariant cells: {invariant_cells}/{len(all_cells)}")
    print(f"cells whose score changed with kill weight: {score_changed_cells}/{len(all_cells)}")
    print(f"cells whose winner changed with kill weight: {len(winner_changed_cells)}/{len(all_cells)}")
    if winner_changed_cells:
        print("WINNER-CHANGED CELLS (expected causal signal, not a defect):")
        for label in winner_changed_cells:
            print(f"  - {label}")
    if divergent_cells:
        print("DIVERGENT CELLS (trajectory changed with kill weight):")
        for label in divergent_cells:
            print(f"  - {label}")
        return 1
    print("VERDICT: trajectory invariant across all sampled cells and kill weights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
