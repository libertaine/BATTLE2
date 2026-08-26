"""v3 Phase 4 -- execution-invariance check for the territory-weight lever,
with `w_kill` fixed at Phase 3's accepted offense payoff (1600).

Smaller than Phase 3's 23-cell sweep by design: the architectural argument
is identical (`scoring.ScoringPolicy.score_territory` only ever writes
into the score map, exactly like `score_kill` did -- see
docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md Sec 4 item 9, which
already covers all three `Weights` fields collectively), so this exists to
confirm that argument empirically for the one axis Phase 3 never
exercised, not to re-establish it from zero. A representative sample
(captures and non-captures, one defense-containing roster and the
negative control) is sufficient for that purpose.
"""

from __future__ import annotations

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
RULESET_V2 = "bytefray-rules-2"
FIXED_KILL_WEIGHT = 1600.0
TERRITORY_WEIGHTS = (1.0, 5.0, 20.0)  # T0 (=K2), T1, T2

GROUP_CELLS: tuple[dict[str, Any], ...] = (
    {"roster": "claimer_coredefender_reactive", "seat_agent_ids": ["claimer", "core_defender", "reactive_core_defender"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "claimer_coretracker_coredefender", "seat_agent_ids": ["claimer", "core_defender", "core_tracker"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "capture"},
    {"roster": "coredefender_reactive_coreseeker", "seat_agent_ids": ["core_defender", "reactive_core_defender", "core_seeker"], "seat_starts": [0, 1365, 2730], "seed": 1, "tag": "no_capture"},
    {"roster": "coredefender_reactive_coreseeker", "seat_agent_ids": ["core_defender", "core_seeker", "reactive_core_defender"], "seat_starts": [682, 2047, 3412], "seed": 1, "tag": "capture"},
)
PAIRWISE_CELLS: tuple[dict[str, Any], ...] = (
    {"pair": "claimer_vs_coretracker_400", "subject_id": "claimer", "opponent_id": "core_tracker", "subject_start": 0, "opponent_start": 2048, "seed": 1},
    {"pair": "hunter_vs_coretracker_400", "subject_id": "hunter", "opponent_id": "core_tracker", "subject_start": 0, "opponent_start": 2048, "seed": 1},
)

TICKS = 400
ARENA_SIZE = 4096
INSTR_PER_TICK = 8

EXCLUDED_FIELDS = {"score", "weights", "match_id", "result_id", "replay_id", "sha256", "winner", "outcome"}


def _strip(record: Any) -> Any:
    if is_dataclass(record) and not isinstance(record, type):
        record = asdict(record)
    if isinstance(record, dict):
        return {k: _strip(v) for k, v in record.items() if k not in EXCLUDED_FIELDS}
    if isinstance(record, (list, tuple)):
        return [_strip(item) for item in record]
    return record


def _replay_trajectory(path: Path) -> list[Any]:
    return [_strip(record) for record in iter_replay(path)]


def _result_trajectory(path: Path) -> dict[str, Any]:
    envelope = read_result(path)
    payload = envelope.as_dict()
    payload.pop("result_id", None)
    payload.pop("match_id", None)
    return _strip(payload)


def main() -> int:
    output = REPO_ROOT / "runs" / "research_v3_phase4" / "execution_invariance"
    data_root = output / "_agents"
    data_root.mkdir(parents=True, exist_ok=True)
    population = benchmarks.load_population(benchmarks.V2_BASELINE_ID)
    benchmarks.stage_population(population, data_root)

    invariant = 0
    divergent: list[str] = []
    winner_changed: list[str] = []
    total = 0

    for cell in GROUP_CELLS:
        entrants = [
            GroupEntrantSpec(seat=chr(ord("A") + i), agent_id=agent_id, start=start)
            for i, (agent_id, start) in enumerate(zip(cell["seat_agent_ids"], cell["seat_starts"], strict=True))
        ]
        label = f"group:{cell['roster']}:{cell['tag']}"
        run_dirs = {}
        for tw in TERRITORY_WEIGHTS:
            run_dir = output / f"group-{cell['roster']}-{cell['tag']}-t{tw:g}"
            if run_dir.exists():
                shutil.rmtree(run_dir)
            test_agents(
                entrants, seed=cell["seed"], ticks=TICKS, trace=False, run_dir=run_dir,
                data_root=data_root, ruleset_id=RULESET_V2, arena_size=ARENA_SIZE,
                instr_per_tick=INSTR_PER_TICK, kill_weight=FIXED_KILL_WEIGHT, territory_weight=tw,
            )
            run_dirs[tw] = run_dir
        total += 1
        baseline_replay = _replay_trajectory(run_dirs[1.0] / "replay.jsonl")
        baseline_result = _result_trajectory(run_dirs[1.0] / "result.json")
        cell_ok = True
        for tw in TERRITORY_WEIGHTS[1:]:
            replay_match = _replay_trajectory(run_dirs[tw] / "replay.jsonl") == baseline_replay
            result_match = _result_trajectory(run_dirs[tw] / "result.json") == baseline_result
            if not (replay_match and result_match):
                cell_ok = False
            base_raw = json.loads((run_dirs[1.0] / "result.json").read_text(encoding="utf-8"))
            cur_raw = json.loads((run_dirs[tw] / "result.json").read_text(encoding="utf-8"))
            if base_raw["winner"] != cur_raw["winner"] and label not in winner_changed:
                winner_changed.append(label)
        if cell_ok:
            invariant += 1
        else:
            divergent.append(label)

    for cell in PAIRWISE_CELLS:
        label = f"pairwise:{cell['pair']}"
        run_dirs = {}
        for tw in TERRITORY_WEIGHTS:
            run_dir = output / f"pairwise-{cell['pair']}-t{tw:g}"
            if run_dir.exists():
                shutil.rmtree(run_dir)
            test_agent(
                cell["subject_id"], opponent=cell["opponent_id"], seed=cell["seed"], ticks=TICKS,
                trace=False, run_dir=run_dir, data_root=data_root, ruleset_id=RULESET_V2,
                agent_start=cell["subject_start"], opponent_start=cell["opponent_start"],
                arena_size=ARENA_SIZE, instr_per_tick=INSTR_PER_TICK,
                kill_weight=FIXED_KILL_WEIGHT, territory_weight=tw,
            )
            run_dirs[tw] = run_dir
        total += 1
        baseline_replay = _replay_trajectory(run_dirs[1.0] / "replay.jsonl")
        baseline_result = _result_trajectory(run_dirs[1.0] / "result.json")
        cell_ok = True
        for tw in TERRITORY_WEIGHTS[1:]:
            replay_match = _replay_trajectory(run_dirs[tw] / "replay.jsonl") == baseline_replay
            result_match = _result_trajectory(run_dirs[tw] / "result.json") == baseline_result
            if not (replay_match and result_match):
                cell_ok = False
            base_raw = json.loads((run_dirs[1.0] / "result.json").read_text(encoding="utf-8"))
            cur_raw = json.loads((run_dirs[tw] / "result.json").read_text(encoding="utf-8"))
            if base_raw["winner"] != cur_raw["winner"] and label not in winner_changed:
                winner_changed.append(label)
        if cell_ok:
            invariant += 1
        else:
            divergent.append(label)

    print(f"cells tested: {total}")
    print(f"trajectory-invariant: {invariant}/{total}")
    print(f"winner changed: {winner_changed}")
    if divergent:
        print("DIVERGENT:", divergent)
        return 1
    print("VERDICT: trajectory invariant across all sampled cells at every tested territory weight.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
