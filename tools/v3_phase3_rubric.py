"""v3 Phase 3J -- score the verbatim Beta2 Sec 17 rubric across K0-K3,
plus the diagnostic 2A/2B split, reusing
``tools/v3_phase1_ecology_rubric.py``'s own functions unmodified (imported,
not reimplemented -- the identical precedent Phase 2 set for its own
locality-versus-control comparison).

Usage::

    python tools/v3_phase3_rubric.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase1_ecology_rubric as rubric
import v3_phase3_corpus as corpus

REFERENCE = "K0"


def diagnostic_2a_2b(bucket: dict[str, Any]) -> dict[str, Any]:
    """Split Sec 17 criterion 2 into its two independently-failable halves.

    2A -- pairwise counter-strategy effectiveness: does dedicated search
    beat blind expansion in the 1v1 controls?
    2B -- group offensive-mechanism effectiveness: does search actually own
    the capture mechanism (highest capture-caused rate) in group play?
    This is a diagnostic split, not a replacement -- criterion_2 itself
    (imported, unmodified) remains the scored gate.
    """

    pair = bucket["pairs"].get("claimer_vs_coretracker_400")
    hunter_pair = bucket["pairs"].get("hunter_vs_coretracker_400")
    claimer_rate = pair["candidate_win_rate"] if pair else None
    hunter_rate = hunter_pair["candidate_win_rate"] if hunter_pair else None
    pairwise_2a = {
        "claimer_vs_core_tracker_1v1": claimer_rate,
        "hunter_vs_core_tracker_1v1": hunter_rate,
        "search_wins_claimer_matchup": claimer_rate is not None and claimer_rate < 0.5,
        "search_wins_hunter_matchup": hunter_rate is not None and hunter_rate < 0.5,
        "pass_2a": bool(
            (claimer_rate is not None and claimer_rate < 0.5)
            or (hunter_rate is not None and hunter_rate < 0.5)
        ),
    }

    search_caused: list[float] = []
    other_caused: list[float] = []
    for entry in bucket["rosters"].values():
        for agent, stats in entry.get("entrants", {}).items():
            rate = stats["capture_caused"]
            if rate is None:
                continue
            (search_caused if agent in rubric.SEARCH_AGENTS else other_caused).append(rate)
    search_max = max(search_caused) if search_caused else None
    other_max = max(other_caused) if other_caused else None
    group_2b = {
        "search_caused_max": search_max,
        "non_search_caused_max": other_max,
        "pass_2b": bool(
            search_max is not None and other_max is not None and search_max > other_max
        ),
    }
    return {"2A_pairwise_counter_strategy": pairwise_2a, "2B_group_offensive_mechanism": group_2b}


def pairwise_negative_control(conditions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Phase 3I: no pairwise outcome may change solely because kill weight changes."""

    reference = conditions[REFERENCE]
    changes: list[dict[str, Any]] = []
    for label, bucket in conditions.items():
        if label == REFERENCE:
            continue
        for pair_id, pair in bucket["pairs"].items():
            ref_pair = reference["pairs"].get(pair_id)
            if ref_pair is None:
                continue
            if pair["candidate_win_rate"] != ref_pair["candidate_win_rate"]:
                changes.append(
                    {
                        "pair_id": pair_id,
                        "condition": label,
                        "reference_rate": ref_pair["candidate_win_rate"],
                        "changed_rate": pair["candidate_win_rate"],
                    }
                )
    return {"pairwise_controls_checked": len(reference["pairs"]) * (len(conditions) - 1), "changes": changes, "pass": not changes}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        nargs="+",
        default=["K0", "K1", "K2", "K3"],
        help="condition labels to score (default: the four predeclared weights)",
    )
    parser.add_argument("--destination-name", default="phase3_rubric.json")
    args = parser.parse_args(argv)

    weights = corpus.all_weights()
    analysis_path = corpus.OUTPUT_ROOT / "phase3_analysis.json"
    if not analysis_path.is_file():
        raise SystemExit(f"{analysis_path} not found -- run tools/v3_phase3_corpus.py build/analyze first")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    conditions = rubric.index_by_condition(analysis)

    report: dict[str, Any] = {
        "reference_condition": REFERENCE,
        "kill_weights": {label: weights[label] for label in args.labels},
        "rubric": [],
        "diagnostic_2a_2b": {},
        "perturbation": [],
        "search": [],
        "pairwise_negative_control": pairwise_negative_control(
            {label: conditions[label] for label in [REFERENCE, *args.labels] if label in conditions}
        ),
    }
    reference_bucket = conditions[REFERENCE]
    for label in args.labels:
        bucket = conditions[label]
        scored = rubric.score_condition(bucket)
        report["rubric"].append(scored)
        report["diagnostic_2a_2b"][label] = diagnostic_2a_2b(bucket)
        report["perturbation"].append(rubric.ranking_perturbation(bucket, reference_bucket))
        report["search"].append(rubric.search_profile(bucket))

    destination = corpus.OUTPUT_ROOT / args.destination_name
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 100)
    print("PHASE 3 -- BETA2 SEC 17 RUBRIC, SCORED PER KILL WEIGHT")
    print("=" * 100)
    for row in report["rubric"]:
        c1 = row["criterion_1_multiple_viable_archetypes"]
        c2 = row["criterion_2_counter_strategies"]
        c3 = row["criterion_3_context_sensitivity"]
        c4 = row["criterion_4_multi_agent_specific"]
        c5 = row["criterion_5_no_universal_solution"]
        mark = lambda v: "PASS" if v["pass"] else "FAIL"
        print(
            f"{row['condition_id']:>4s} (w_kill={weights[row['condition_id']]:>7.1f}): "
            f"C1={mark(c1)}({c1['distinct_leading_agents']}) C2={mark(c2)} C3={mark(c3)} "
            f"C4={mark(c4)} C5={mark(c5)} -> {row['criteria_passed']}/5"
        )

    print("\n" + "=" * 100)
    print("DIAGNOSTIC 2A (pairwise) / 2B (group mechanism) SPLIT")
    print("=" * 100)
    for label, diag in report["diagnostic_2a_2b"].items():
        a = diag["2A_pairwise_counter_strategy"]
        b = diag["2B_group_offensive_mechanism"]
        print(
            f"{label}: 2A={'PASS' if a['pass_2a'] else 'FAIL'} "
            f"(claimer_vs_ct={a['claimer_vs_core_tracker_1v1']}, hunter_vs_ct={a['hunter_vs_core_tracker_1v1']}) "
            f"2B={'PASS' if b['pass_2b'] else 'FAIL'} (search_max={b['search_caused_max']}, other_max={b['non_search_caused_max']})"
        )

    print("\n" + "=" * 100)
    print("SEARCH / EXPANSION / DEFENSE WIN AND CAUSED SHARES")
    print("=" * 100)
    for row in report["search"]:
        print(
            f"{row['condition_id']:>4s}: search_win={row['search_win_rate']}, expand_win={row['expansion_win_rate']}, "
            f"defend_win={row['defense_win_rate']}, search_caused={row['search_caused']}, "
            f"expand_caused={row['expansion_caused']}, defend_caused={row['defense_caused']}"
        )

    print("\n" + "=" * 100)
    print("RANKING PERTURBATION vs K0")
    print("=" * 100)
    for row in report["perturbation"]:
        print(
            f"{row['condition_id']:>4s}: leaders={row['leader_changes']}/{row['rosters_compared']} "
            f"reversals={row['pairwise_reversals']}/{row['pairwise_relationships']} "
            f"strict={row['pairwise_reversals_beyond_intervals']} "
            f"rates_moved={row['rates_changed_beyond_intervals']}/{row['rates_compared']} "
            f"mean_move={row['mean_absolute_rate_move_pp']}"
        )

    print("\n" + "=" * 100)
    print("PAIRWISE NEGATIVE CONTROL (Phase 3I)")
    print("=" * 100)
    npc = report["pairwise_negative_control"]
    print(f"checked {npc['pairwise_controls_checked']} pairwise comparisons; changes: {npc['changes']}")
    print(f"PASS: {npc['pass']}")

    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
