"""v3 Phase 3D -- deterministic offline rescoring of committed match results.

Given Phase 3C's proof that a kill-weight sweep does not perturb gameplay
trajectory, this module rescores an already-executed ``result.json`` at any
requested ``weights.kill`` without re-executing anything. Because Phase 3
holds ``weights.alive``/``weights.territory`` fixed at their shipped
defaults and only varies ``weights.kill``, the general alpha.3-style
``bucket_sum`` decomposition is unnecessary: the kill term is the only one
that moves, so the exact rescored score is

    new_score = old_score + kills * (new_kill_weight - old_kill_weight)

using each entrant's already-persisted, exact ``statistics.kills`` count.
The new winner is then resolved with the real, unmodified
``battle_engine.results.resolve_winner`` -- the same production function
that decided the original match -- applied to the rescored score map and
each entrant's already-recorded ``alive``/``termination_reason``, which
Phase 3C proved does not change with kill weight.
"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.results import resolve_winner

DEFAULT_KILL_WEIGHT = 5.0


@dataclass(frozen=True)
class _EntrantIdentity:
    agent_id: str
    alive: bool


def rescore_score_map(
    original_score: dict[str, float],
    kills_by_agent: dict[str, int],
    new_kill_weight: float,
    old_kill_weight: float = DEFAULT_KILL_WEIGHT,
) -> dict[str, float]:
    delta = new_kill_weight - old_kill_weight
    return {
        agent_id: value + kills_by_agent.get(agent_id, 0) * delta
        for agent_id, value in original_score.items()
    }


def rescore_result_payload(
    original: dict[str, Any],
    new_kill_weight: float,
    old_kill_weight: float = DEFAULT_KILL_WEIGHT,
) -> dict[str, Any]:
    """Return a deep-copied ``result.json`` payload rescored at ``new_kill_weight``.

    Only score-derived fields (``score``, ``entrants[].score``,
    ``entrants[].statistics.score``, ``winner``) and the disclosed
    ``reproducibility.weights.kill``/``config.weights.kill`` change.
    Everything else -- alive, termination_reason, statistics.kills,
    territory, cpu_total, metadata -- is copied verbatim, since Phase 3C
    proved those fields do not depend on kill weight.
    """

    payload = copy.deepcopy(original)
    entrants = payload["entrants"]
    kills_by_agent = {e["agent_id"]: int(e.get("statistics", {}).get("kills", 0)) for e in entrants}
    rescored_score = rescore_score_map(payload["score"], kills_by_agent, new_kill_weight, old_kill_weight)
    payload["score"] = rescored_score
    for entrant in entrants:
        agent_id = entrant["agent_id"]
        entrant["score"] = rescored_score[agent_id]
        if "statistics" in entrant and entrant["statistics"] is not None:
            entrant["statistics"]["score"] = rescored_score[agent_id]

    identities = [_EntrantIdentity(agent_id=e["agent_id"], alive=bool(e["alive"])) for e in entrants]
    win_mode = payload.get("reproducibility", {}).get("win_mode", "score_fallback")
    # `HasAgentIdentity.agent_id` is declared as a read-only property (so
    # runtime state classes exposing it as such still satisfy the
    # Protocol -- see that Protocol's own docstring); a plain dataclass
    # field structurally provides the same read access at runtime but
    # mypy's Protocol matching does not consider them interchangeable.
    winner = resolve_winner(identities, rescored_score, win_mode)  # type: ignore[arg-type]
    payload["winner"] = winner if winner else "tie"

    reproducibility = payload.get("reproducibility")
    if isinstance(reproducibility, dict) and isinstance(reproducibility.get("weights"), dict):
        reproducibility["weights"]["kill"] = new_kill_weight
    return payload


def rescore_result_file(source_path: Path, destination_path: Path, new_kill_weight: float) -> dict[str, Any]:
    original = json.loads(source_path.read_text(encoding="utf-8"))
    rescored = rescore_result_payload(original, new_kill_weight)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text(json.dumps(rescored, indent=2), encoding="utf-8")
    return rescored


def rescore_pairwise_outcome(
    original_result: dict[str, Any],
    new_kill_weight: float,
    subject_id: str,
    opponent_id: str,
) -> str:
    """Recompute the ``win``/``loss``/``tie`` outcome (candidate perspective)
    a rescored pairwise cell would report, mirroring
    ``tools/v3_phase1_arena_action_grid.py``'s ``analyze_pair`` reading of
    ``evaluation.json``'s stored ``outcome`` field, but recomputed at the
    requested weight instead of read verbatim.

    ``result.json``'s ``winner`` is a physical slot id (``"A"``/``"B"``),
    not an agent name, so it is mapped back through this same result's own
    ``entrants[].name`` before comparing against ``subject_id``/
    ``opponent_id`` (agent names) -- this sidesteps needing to know
    orientation separately, and works identically for either orientation.
    """

    rescored = rescore_result_payload(original_result, new_kill_weight)
    winner_slot = rescored["winner"]
    name_by_slot = {e["agent_id"]: e.get("name") for e in rescored["entrants"]}
    winner_name = name_by_slot.get(winner_slot)
    if winner_name == subject_id:
        return "win"
    if winner_name == opponent_id:
        return "loss"
    return "tie"


# ---------------------------------------------------------------------------
# Validation against real production executions (Phase 3D)
# ---------------------------------------------------------------------------


def validate_against_real_executions(invariance_report_path: Path, execution_root: Path) -> dict[str, Any]:
    """Compare offline-rescored K1/K2/K3 outcomes against the real executions
    Phase 3C already produced for the same sampled cells, at K0=5 as the
    rescoring base. Requires exact agreement on score map, winner, and the
    per-entrant `kills`/territory ingredients the rescoring assumed fixed.
    """

    report = json.loads(invariance_report_path.read_text(encoding="utf-8"))
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for cell in report["cells"]:
        label = cell["label"]
        if label.startswith("group:"):
            _, roster, tag = label.split(":", 2)
            dir_prefix = f"group-{roster}-{tag}"
        else:
            _, pair = label.split(":", 1)
            dir_prefix = f"pairwise-{pair}"
        k0_path = execution_root / f"{dir_prefix}-k5" / "result.json"
        if not k0_path.is_file():
            continue
        original = json.loads(k0_path.read_text(encoding="utf-8"))
        for weight_str in cell["kill_weights"]:
            weight = float(weight_str)
            if weight == DEFAULT_KILL_WEIGHT:
                continue
            real_path = execution_root / f"{dir_prefix}-k{weight:g}" / "result.json"
            if not real_path.is_file():
                continue
            real = json.loads(real_path.read_text(encoding="utf-8"))
            rescored = rescore_result_payload(original, weight)
            checked += 1
            if rescored["score"] != real["score"] or rescored["winner"] != real["winner"]:
                mismatches.append(
                    {
                        "label": label,
                        "weight": weight,
                        "rescored_score": rescored["score"],
                        "real_score": real["score"],
                        "rescored_winner": rescored["winner"],
                        "real_winner": real["winner"],
                    }
                )
    return {"cells_checked": checked, "mismatches": mismatches, "exact_agreement": not mismatches}


def main() -> int:
    execution_root = REPO / "runs" / "research_v3_phase3" / "execution_invariance"
    report_path = execution_root / "execution_invariance_report.json"
    result = validate_against_real_executions(report_path, execution_root)
    print(json.dumps(result, indent=2))
    return 0 if result["exact_agreement"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
