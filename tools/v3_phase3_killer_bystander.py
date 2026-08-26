"""v3 Phase 3J item 3/4 -- killer-vs-bystander conversion and capture attribution.

For every group cell in the Phase 3 corpus (K0-K3) that produces an
unambiguous single-death core capture (Tier-2 attribution -- see
``evaluation_group_analysis``'s own conservative single-death restriction),
measures:

* ``P(killer ultimately wins | killer lands the decisive capture)``
* ``P(bystander wins | another entrant lands the decisive capture)``
  (per bystander *slot*, not per cell -- a 3-entrant capture cell has
  exactly one bystander slot)

and tallies capture attribution by strategic role (search/expansion/
defense), reusing ``tools/v3_phase1_ecology_rubric.py``'s own
``SEARCH_AGENTS``/``EXPANSION_AGENTS``/``DEFENSE_AGENTS`` constants rather
than redefining the taxonomy.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase1_ecology_rubric as rubric
import v3_phase3_corpus as corpus
from battle_engine.evaluation_group_analysis import (
    GroupCellRef,
    load_group_cell_records,
)


def _refs_for_roster(label: str, weight: float, roster: str) -> list[GroupCellRef]:
    results_root = corpus._results_root_for(label, weight)
    condition_id = corpus._condition_id_for(label, weight)
    evaluation_json = results_root / condition_id / "group" / roster / "evaluation.json"
    data = json.loads(evaluation_json.read_text(encoding="utf-8"))
    refs = []
    for payload in data["cells"]:
        artifact_dir = (evaluation_json.parent / Path(payload["artifact_dir"])).resolve()
        refs.append(
            GroupCellRef(
                schedule_id=payload["schedule_id"],
                roster_agent_ids=tuple(data["roster_agent_ids"]),
                seat_agent_ids=tuple(payload["seat_agent_ids"]),
                layout_id=payload["layout_id"],
                seed=payload["seed"],
                result_path=artifact_dir / "result.json",
            )
        )
    return refs


def _role(agent_id: str) -> str:
    if agent_id in rubric.SEARCH_AGENTS:
        return "search"
    if agent_id in rubric.EXPANSION_AGENTS:
        return "expansion"
    if agent_id in rubric.DEFENSE_AGENTS:
        return "defense"
    return "other"


def analyze_condition(label: str, weight: float) -> dict[str, Any]:
    killer_wins = 0
    killer_total = 0
    bystander_wins = 0
    bystander_total = 0
    attribution_by_role: dict[str, int] = defaultdict(int)
    attribution_total = 0
    unattributed = 0
    cells_with_capture = 0
    examples: list[dict[str, Any]] = []

    for roster in corpus.GROUP_ROSTERS:
        refs = _refs_for_roster(label, weight, roster)
        for ref in refs:
            records = load_group_cell_records(ref)
            if not records or not any(r.available for r in records):
                continue
            any_death = any(r.alive is False for r in records if r.available)
            if not any_death:
                continue
            killers = [r for r in records if r.captor_of]
            if not killers:
                # A death occurred but Tier-2 attribution could not name a
                # unique captor (multi-death cell) -- disclosed, not guessed.
                if any(r.available and r.alive is False for r in records):
                    unattributed += 1
                continue
            cells_with_capture += 1
            for killer in killers:
                attribution_total += 1
                attribution_by_role[_role(killer.agent_id)] += 1
                killer_total += 1
                killer_won = killer.outcome is not None and killer.outcome.value == "winner"
                if killer_won:
                    killer_wins += 1
                victims = set(killer.captor_of)
                for other in records:
                    if other.agent_id == killer.agent_id or other.agent_id in victims:
                        continue
                    bystander_total += 1
                    other_won = other.outcome is not None and other.outcome.value == "winner"
                    if other_won:
                        bystander_wins += 1
                if len(examples) < 5:
                    examples.append(
                        {
                            "roster": roster,
                            "schedule_id": ref.schedule_id,
                            "killer": killer.agent_id,
                            "killer_role": _role(killer.agent_id),
                            "killer_won": killer_won,
                            "victims": sorted(victims),
                        }
                    )

    return {
        "condition_id": label,
        "cells_with_attributed_capture": cells_with_capture,
        "cells_with_unattributed_capture": unattributed,
        "killer_win_rate": (killer_wins / killer_total) if killer_total else None,
        "killer_wins": killer_wins,
        "killer_total": killer_total,
        "bystander_win_rate": (bystander_wins / bystander_total) if bystander_total else None,
        "bystander_wins": bystander_wins,
        "bystander_total": bystander_total,
        "attribution_by_role": dict(attribution_by_role),
        "attribution_total": attribution_total,
        "examples": examples,
    }


def main() -> int:
    weights = corpus.all_weights()
    report = {label: analyze_condition(label, weight) for label, weight in weights.items()}
    destination = corpus.OUTPUT_ROOT / "phase3_killer_bystander.json"
    corpus.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for label, entry in report.items():
        print(
            f"{label} (w_kill={weights[label]}): "
            f"killer_win_rate={entry['killer_win_rate']}, "
            f"bystander_win_rate={entry['bystander_win_rate']}, "
            f"attributed_captures={entry['cells_with_attributed_capture']}, "
            f"unattributed={entry['cells_with_unattributed_capture']}, "
            f"attribution_by_role={entry['attribution_by_role']}"
        )
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
