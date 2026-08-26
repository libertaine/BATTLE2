"""v3 Phase 4 -- general 3-term offline rescoring, fixing the Phase 3 offense
payoff (`w_kill = 1600`) and varying `w_territory`.

Phase 3's single-term shortcut (`new_score = old_score + kills * delta`)
only worked because exactly one weight moved. Phase 4 varies
``weights.territory`` while holding ``weights.kill`` fixed at Phase 3's
K2, so the general alpha.3 decomposition is needed:

    score = alive_ticks * w_alive + kills * w_kill + bucket_sum * w_territory

Every committed Phase 1 ``result.json`` already carries ``alive_ticks``
and ``kills`` exactly (``statistics``), and was scored under the *known*
shipped defaults (``w_alive=1.0``, ``w_kill=5.0``, ``w_territory=1.0``), so
``bucket_sum`` is the unique solution of one linear equation in one
unknown -- recovered once, per entrant, directly from the original
committed artifact (never from a Phase-3-rescored copy, to avoid
compounding rescoring error). Two independent checks validate the
decomposition exactly as alpha.3 (docs/V2_0_ALPHA3_SCORING_SENSITIVITY.md
Sec 6) did: integrality (a correct decomposition yields an exact
non-negative integer bucket_sum) and reconstruction (recomputing score at
the *original* weights must reproduce the recorded score exactly).
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

ORIGINAL_WEIGHTS = {"alive": 1.0, "kill": 5.0, "territory": 1.0, "territory_bucket": 64}

# Phase 3's own accepted offense payoff -- held fixed throughout Phase 4.
FIXED_KILL_WEIGHT = 1600.0


@dataclass(frozen=True)
class _EntrantIdentity:
    agent_id: str
    alive: bool


def decompose_bucket_sum(entrant: dict[str, Any]) -> int:
    """Recover the exact, integer territory-bucket sum an entrant earned,
    by algebraic inversion against the *original* K0 (shipped-default)
    score -- alpha.3's method, generalized from 1v1 to this engine's
    ordinary per-entrant statistics, which already carry everything
    needed."""

    stats = entrant.get("statistics") or {}
    alive_ticks = stats.get("alive_ticks")
    kills = stats.get("kills")
    score = entrant.get("score")
    if alive_ticks is None or kills is None or score is None:
        raise ValueError(f"entrant {entrant.get('agent_id')!r} missing alive_ticks/kills/score")
    raw = (score - alive_ticks * ORIGINAL_WEIGHTS["alive"] - kills * ORIGINAL_WEIGHTS["kill"]) / ORIGINAL_WEIGHTS["territory"]
    bucket_sum = round(raw)
    if abs(raw - bucket_sum) > 1e-6 or bucket_sum < 0:
        raise ValueError(
            f"entrant {entrant.get('agent_id')!r}: non-integer or negative bucket_sum "
            f"decomposition ({raw!r}) -- decomposition assumption violated"
        )
    return bucket_sum


def rescore_result_payload_general(
    original: dict[str, Any],
    *,
    w_alive: float = 1.0,
    w_kill: float = FIXED_KILL_WEIGHT,
    w_territory: float = 1.0,
) -> dict[str, Any]:
    """Return a deep-copied ``result.json`` payload rescored at an arbitrary
    ``(w_alive, w_kill, w_territory)`` triple, decomposed from the
    *original* (K0, shipped-default) payload passed in."""

    payload = copy.deepcopy(original)
    entrants = payload["entrants"]
    rescored_score: dict[str, float] = {}
    for entrant in entrants:
        stats = entrant.get("statistics") or {}
        alive_ticks = stats["alive_ticks"]
        kills = stats["kills"]
        bucket_sum = decompose_bucket_sum(entrant)
        new_score = alive_ticks * w_alive + kills * w_kill + bucket_sum * w_territory
        rescored_score[entrant["agent_id"]] = new_score

    payload["score"] = rescored_score
    for entrant in entrants:
        agent_id = entrant["agent_id"]
        entrant["score"] = rescored_score[agent_id]
        if "statistics" in entrant and entrant["statistics"] is not None:
            entrant["statistics"]["score"] = rescored_score[agent_id]

    identities = [_EntrantIdentity(agent_id=e["agent_id"], alive=bool(e["alive"])) for e in entrants]
    win_mode = payload.get("reproducibility", {}).get("win_mode", "score_fallback")
    winner = resolve_winner(identities, rescored_score, win_mode)  # type: ignore[arg-type]
    payload["winner"] = winner if winner else "tie"

    reproducibility = payload.get("reproducibility")
    if isinstance(reproducibility, dict) and isinstance(reproducibility.get("weights"), dict):
        reproducibility["weights"]["alive"] = w_alive
        reproducibility["weights"]["kill"] = w_kill
        reproducibility["weights"]["territory"] = w_territory
    return payload


def rescore_result_file_general(
    source_path: Path, destination_path: Path, *, w_alive: float, w_kill: float, w_territory: float
) -> dict[str, Any]:
    original = json.loads(source_path.read_text(encoding="utf-8"))
    rescored = rescore_result_payload_general(original, w_alive=w_alive, w_kill=w_kill, w_territory=w_territory)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text(json.dumps(rescored, indent=2), encoding="utf-8")
    return rescored


def rescore_pairwise_outcome_general(
    original_result: dict[str, Any],
    *,
    w_alive: float,
    w_kill: float,
    w_territory: float,
    subject_id: str,
    opponent_id: str,
) -> str:
    rescored = rescore_result_payload_general(
        original_result, w_alive=w_alive, w_kill=w_kill, w_territory=w_territory
    )
    winner_slot = rescored["winner"]
    name_by_slot = {e["agent_id"]: e.get("name") for e in rescored["entrants"]}
    winner_name = name_by_slot.get(winner_slot)
    if winner_name == subject_id:
        return "win"
    if winner_name == opponent_id:
        return "loss"
    return "tie"


def validate_decomposition(sample_paths: list[Path]) -> dict[str, Any]:
    """Alpha.3's own two checks, run against a sample of real committed
    K0 result.json files: integrality, and exact reconstruction at the
    original weights."""

    checked = 0
    failures: list[str] = []
    for path in sample_paths:
        original = json.loads(path.read_text(encoding="utf-8"))
        for entrant in original["entrants"]:
            checked += 1
            try:
                bucket_sum = decompose_bucket_sum(entrant)
            except ValueError as exc:
                failures.append(f"{path}: {exc}")
                continue
            stats = entrant["statistics"]
            reconstructed = (
                stats["alive_ticks"] * ORIGINAL_WEIGHTS["alive"]
                + stats["kills"] * ORIGINAL_WEIGHTS["kill"]
                + bucket_sum * ORIGINAL_WEIGHTS["territory"]
            )
            if abs(reconstructed - entrant["score"]) > 1e-6:
                failures.append(
                    f"{path}: reconstruction mismatch for {entrant['agent_id']} "
                    f"({reconstructed} != {entrant['score']})"
                )
    return {"entrants_checked": checked, "failures": failures, "all_passed": not failures}


if __name__ == "__main__":
    import glob

    sample = [Path(p) for p in glob.glob(
        "runs/research_v3_phase1/main/results/a4096_b8/group/*/matches/*/result.json"
    )]
    result = validate_decomposition(sample)
    print(json.dumps({"entrants_checked": result["entrants_checked"], "all_passed": result["all_passed"], "failures": result["failures"][:5]}, indent=2))
