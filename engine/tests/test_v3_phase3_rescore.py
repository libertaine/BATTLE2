"""v3 Phase 3D: offline kill-weight rescoring must exactly match what
production scoring/winner-resolution would compute.

``tools/v3_phase3_rescore.py`` rescores an already-executed ``result.json``
at a new ``weights.kill`` without re-executing the match, exploiting Phase
3C's proof that gameplay trajectory (and therefore each entrant's ``alive``
state and ``kills`` count) does not depend on kill weight. These are fast,
hermetic unit tests of that rescoring logic against synthetic payloads; the
broader empirical validation against real production executions for a
representative corpus sample lives in
``tools/v3_phase3_execution_invariance.py``/``tools/v3_phase3_rescore.py``'s
own ``validate_against_real_executions`` (reported in
docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md), which this module does
not duplicate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import v3_phase3_rescore as rescore


def _payload(*, alive, kills, score, names=None, win_mode="score_fallback"):
    names = names or {}
    return {
        "score": dict(score),
        "winner": None,
        "reproducibility": {"win_mode": win_mode, "weights": {"kill": 5.0, "alive": 1.0, "territory": 1.0, "territory_bucket": 64}},
        "entrants": [
            {
                "agent_id": agent_id,
                "name": names.get(agent_id, agent_id.lower()),
                "alive": alive[agent_id],
                "score": score[agent_id],
                "statistics": {"kills": kills.get(agent_id, 0), "score": score[agent_id]},
            }
            for agent_id in score
        ],
    }


def test_rescore_score_map_only_moves_the_kill_term():
    original = {"A": 1000.0, "B": 1200.0}
    kills = {"A": 1}
    rescored = rescore.rescore_score_map(original, kills, new_kill_weight=1600.0, old_kill_weight=5.0)
    assert rescored["A"] == pytest.approx(1000.0 + 1 * (1600.0 - 5.0))
    assert rescored["B"] == 1200.0  # no kills -> untouched


def test_rescore_score_map_is_a_no_op_at_the_default_weight():
    original = {"A": 500.0, "B": 700.0}
    kills = {"A": 2, "B": 1}
    rescored = rescore.rescore_score_map(original, kills, new_kill_weight=5.0, old_kill_weight=5.0)
    assert rescored == original


def test_rescore_result_payload_flips_winner_when_kill_bonus_overtakes_territory_lead():
    """Killer trails on raw territory/alive score but a large kill bonus should
    make it the winner -- mirrors the real double-kill cell Phase 3C sampled."""

    payload = _payload(
        alive={"A": False, "B": False, "C": True},
        kills={"C": 2},
        score={"A": 1657.0, "B": 2.0, "C": 1294.0},
    )
    default = rescore.rescore_result_payload(payload, new_kill_weight=5.0)
    assert default["winner"] == "C"  # sole survivor wins regardless of score
    assert default["score"] == payload["score"]

    boosted = rescore.rescore_result_payload(payload, new_kill_weight=1600.0)
    assert boosted["winner"] == "C"
    assert boosted["score"]["C"] == pytest.approx(1294.0 + 2 * (1600.0 - 5.0))
    assert boosted["score"]["A"] == 1657.0  # untouched: A had zero kills


def test_rescore_result_payload_can_change_winner_among_survivors():
    """Two survivors, one of whom has the sole kill: raising the kill weight
    should be able to overturn a territory-driven default winner."""

    payload = _payload(
        alive={"A": True, "B": True, "C": False},
        kills={"A": 1},
        score={"A": 500.0, "B": 600.0, "C": 300.0},
    )
    default = rescore.rescore_result_payload(payload, new_kill_weight=5.0)
    assert default["winner"] == "B"  # ahead on raw score, both alive

    boosted = rescore.rescore_result_payload(payload, new_kill_weight=1600.0)
    assert boosted["winner"] == "A"  # kill bonus now dominates the 100-point gap
    assert boosted["score"]["A"] == pytest.approx(500.0 + 1 * (1600.0 - 5.0))
    assert boosted["score"]["B"] == 600.0


def test_rescore_result_payload_never_lets_a_dead_entrant_win():
    """Survivor-eligibility must be preserved exactly -- a dead entrant with
    a huge kill bonus still cannot win while any entrant survives."""

    payload = _payload(
        alive={"A": True, "B": False},
        kills={"B": 5},
        score={"A": 100.0, "B": 50.0},
    )
    boosted = rescore.rescore_result_payload(payload, new_kill_weight=3200.0)
    assert boosted["score"]["B"] == pytest.approx(50.0 + 5 * (3200.0 - 5.0))
    assert boosted["winner"] == "A"  # sole survivor wins regardless of score


def test_rescore_result_payload_updates_disclosed_weight_only():
    payload = _payload(
        alive={"A": True, "B": True},
        kills={},
        score={"A": 10.0, "B": 10.0},
    )
    rescored = rescore.rescore_result_payload(payload, new_kill_weight=400.0)
    assert rescored["reproducibility"]["weights"]["kill"] == 400.0
    assert rescored["reproducibility"]["weights"]["alive"] == 1.0
    assert rescored["reproducibility"]["weights"]["territory"] == 1.0
    assert rescored["winner"] == "tie"  # equal score, both alive


def test_rescore_pairwise_outcome_maps_slot_winner_to_agent_name():
    payload = _payload(
        alive={"A": True, "B": False},
        kills={"A": 1},
        score={"A": 100.0, "B": 200.0},
        names={"A": "claimer", "B": "core_tracker"},
    )
    # At the default weight B is ineligible (dead) and A is the sole
    # survivor, so A already wins regardless of kill weight here -- assert
    # the name mapping itself is correct at two different weights.
    assert rescore.rescore_pairwise_outcome(payload, 5.0, subject_id="claimer", opponent_id="core_tracker") == "win"
    assert rescore.rescore_pairwise_outcome(payload, 1600.0, subject_id="claimer", opponent_id="core_tracker") == "win"
    assert rescore.rescore_pairwise_outcome(payload, 5.0, subject_id="core_tracker", opponent_id="claimer") == "loss"
