"""Score the Beta2 Phase 4 Sec 17 ecology rubric across the v3 Phase 1 grid.

This is the analysis half of Phase 1: ``v3_phase1_arena_action_grid.py``
executes the grid and reduces every condition to measured aggregates; this
script reads that reduction and answers the four questions Phase 1 has to
answer from it.

1. **Sec 17 rubric, verbatim.** The five criteria from
   ``docs/V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md`` Sec 17 are
   reproduced unaltered in ``CRITERIA`` below and each parameter condition
   is scored against them. No replacement rubric is defined; the
   supplementary measurements this file adds are reported alongside the
   five criteria, never in place of one.
2. **Ranking perturbation (Phase 1I).** Absolute win-rate deltas are the
   weak signal; what matters is whether the *relative* strategic ordering
   changes. Every condition's per-roster ordering is compared against the
   default condition's, counting leader changes and pairwise relationship
   reversals, with non-overlapping Wilson intervals as a conservative
   marker for "larger than uncertainty".
3. **Search/offense opportunity cost (Phase 1L).** ``core_seeker`` and
   ``core_tracker`` are tracked against ``claimer`` and the two defenders
   on both raw win rate and capture-caused rate, because Beta2 Sec 17
   itself records that search agents can be the decisive factor in a
   roster without leading it.
4. **Pairwise-versus-group divergence (Phase 1K).** The v2 property that
   1v1 strength does not predict group strength is re-measured at every
   condition; losing it would be a loss of strategic depth even if the
   win rates looked more even.

Nothing here recomputes a match outcome or an aggregate: every number
traces to ``phase1_<stage>_analysis.json``, which in turn comes from the
production ``evaluation_group_analysis`` module.

Usage, from the repo root with .venv active::

    python tools/v3_phase1_ecology_rubric.py --stage main --output runs/research_v3_phase1
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

DEFAULT_CONDITION = "a4096_b8"

# The negative-control roster, declared as such by the Phase 0 corpus
# definition ("negative control: no offense present"). Sec 17 criterion 5
# excludes exactly this roster by construction, so it is named here rather
# than inferred.
NEGATIVE_CONTROL_ROSTER = "claimer_coredefender_reactive"

SEARCH_AGENTS = ("core_seeker", "core_tracker")
EXPANSION_AGENTS = ("claimer", "hunter")
DEFENSE_AGENTS = ("core_defender", "reactive_core_defender")

# Sec 17's kingmaking mechanism check (Phase 0 Sec 9 criterion 4): each
# pair is (roster with a search agent, the same roster with the search
# agent replaced by Hunter). If an actual elimination event is what opens
# the door for the passive third, the third wins ~0% in the search-free
# roster.
KINGMAKING_PAIRS = (
    ("claimer_coretracker_coredefender", "claimer_hunter_coredefender", "core_defender"),
    ("claimer_coretracker_reactive", "claimer_hunter_reactive", "reactive_core_defender"),
)

# Beta2 Phase 4 Sec 17, reproduced verbatim. Used as the rubric text, never
# paraphrased or replaced -- see docs/V3_PHASE0_RESEARCH_BASELINE.md Sec 9
# for the same five criteria applied to the default control.
CRITERIA: tuple[tuple[str, str], ...] = (
    (
        "Multiple viable archetypes",
        (
            "yes. Five of the six agents have the highest raw win rate in at least one "
            "tested roster ... Core Tracker has none outright -- its best result is a "
            "three-way near-tie ... Both search agents are nevertheless the *decisive* "
            "factor (highest `caused` rate) in every roster they join, a form of strategic "
            "value distinct from raw win rate."
        ),
    ),
    (
        "Counter-strategies",
        (
            "yes, one clear one -- dedicated search defeats blind expansion, the central "
            "problem alpha.10/alpha.11 already set out to fix, confirmed still working "
            "under Beta2's own methodology."
        ),
    ),
    (
        "Context-sensitivity",
        (
            "yes, extensively -- seat, layout, and seed all materially affect outcomes, in "
            "roster-specific rather than universal patterns."
        ),
    ),
    (
        "Multi-agent-specific behavior beyond repeated 1v1",
        "yes, clearly (kingmaking, pairwise-vs-group divergence).",
    ),
    (
        "Evidence of a simple universal solution",
        (
            "no single strategy wins broadly across dissimilar rosters at a rate "
            "approaching 90-100% except in the one negative-control roster with zero "
            "offensive pressure present by construction."
        ),
    ),
)


def load_analysis(stage: str, output: Path) -> dict[str, Any]:
    path = output / stage / "results" / f"phase1_{stage}_analysis.json"
    if not path.is_file():
        raise SystemExit(f"{path} not found -- run the grid and its analyze step first")
    return json.loads(path.read_text(encoding="utf-8"))


def index_by_condition(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Group every roster and pair result under its condition id."""

    conditions: dict[str, dict[str, Any]] = {}
    for entry in analysis["group"]:
        bucket = conditions.setdefault(
            entry["condition_id"],
            {
                "condition_id": entry["condition_id"],
                "arena_size": entry["arena_size"],
                "instr_per_tick": entry["instr_per_tick"],
                "rosters": {},
                "pairs": {},
            },
        )
        bucket["rosters"][entry["roster_id"]] = entry
    for entry in analysis["pairwise"]:
        bucket = conditions.setdefault(
            entry["condition_id"],
            {
                "condition_id": entry["condition_id"],
                "arena_size": entry["arena_size"],
                "instr_per_tick": entry["instr_per_tick"],
                "rosters": {},
                "pairs": {},
            },
        )
        bucket["pairs"][entry["pair_id"]] = entry
    return conditions


# ---------------------------------------------------------------------------
# Sec 17 criteria
# ---------------------------------------------------------------------------


def _leaders(bucket: dict[str, Any]) -> dict[str, list[str]]:
    """agent -> rosters in which it holds the highest raw win rate.

    Ties count as leads for every tied agent, which is how Sec 17 itself
    counts them ("`reactive_hunter_coreseeker` tied at 50.0%").
    """

    leaders: dict[str, list[str]] = {}
    for roster_id, entry in bucket["rosters"].items():
        if "entrants" not in entry:
            continue
        rates = {a: (v["win_rate"] or 0.0) for a, v in entry["entrants"].items()}
        if not rates:
            continue
        best = max(rates.values())
        for agent, rate in rates.items():
            if rate == best:
                leaders.setdefault(agent, []).append(roster_id)
    return leaders


def criterion_1(bucket: dict[str, Any]) -> dict[str, Any]:
    leaders = _leaders(bucket)
    decisive: dict[str, list[str]] = {}
    for roster_id, entry in bucket["rosters"].items():
        if "entrants" not in entry:
            continue
        caused = {a: (v["capture_caused"] or 0.0) for a, v in entry["entrants"].items()}
        if not caused or max(caused.values()) <= 0.0:
            continue
        best = max(caused.values())
        for agent, rate in caused.items():
            if rate == best:
                decisive.setdefault(agent, []).append(roster_id)
    search_rosters = {
        agent: [
            roster_id
            for roster_id, entry in bucket["rosters"].items()
            if agent in entry.get("roster", [])
        ]
        for agent in SEARCH_AGENTS
    }
    search_decisive_everywhere = {
        agent: sorted(search_rosters[agent]) == sorted(decisive.get(agent, []))
        and bool(search_rosters[agent])
        for agent in SEARCH_AGENTS
    }
    return {
        "distinct_leading_agents": len(leaders),
        "leaders": {a: sorted(r) for a, r in sorted(leaders.items())},
        "decisive_by_caused": {a: sorted(r) for a, r in sorted(decisive.items())},
        "search_decisive_in_every_roster_joined": search_decisive_everywhere,
        "pass": len(leaders) >= 2,
    }


def criterion_2(bucket: dict[str, Any]) -> dict[str, Any]:
    """Does dedicated search still defeat blind expansion?

    Two independent readings, both from measured data: the 1v1 control
    (``claimer`` vs ``core_tracker``, where a candidate rate below 50%
    means search wins the matchup) and the group capture evidence (search
    agents' capture-caused rates against everyone else's).
    """

    pair = bucket["pairs"].get("claimer_vs_coretracker_400")
    hunter_pair = bucket["pairs"].get("hunter_vs_coretracker_400")
    search_caused: list[float] = []
    other_caused: list[float] = []
    for entry in bucket["rosters"].values():
        for agent, stats in entry.get("entrants", {}).items():
            rate = stats["capture_caused"]
            if rate is None:
                continue
            (search_caused if agent in SEARCH_AGENTS else other_caused).append(rate)
    claimer_rate = pair["candidate_win_rate"] if pair else None
    hunter_rate = hunter_pair["candidate_win_rate"] if hunter_pair else None
    search_max = max(search_caused) if search_caused else None
    other_max = max(other_caused) if other_caused else None
    beats_1v1 = [r for r in (claimer_rate, hunter_rate) if r is not None and r < 0.5]
    separated = (
        search_max is not None and other_max is not None and search_max > other_max
    )
    return {
        "claimer_vs_core_tracker_1v1": claimer_rate,
        "hunter_vs_core_tracker_1v1": hunter_rate,
        "expansion_matchups_lost_to_search": len(beats_1v1),
        "search_caused_max": search_max,
        "non_search_caused_max": other_max,
        "search_caused_dominates": separated,
        "pass": bool(beats_1v1) and separated,
    }


def criterion_3(bucket: dict[str, Any]) -> dict[str, Any]:
    """Seat/layout/seed sensitivity, and whether it is roster-specific."""

    axes = {"seat": [], "layout": [], "seed": []}
    per_roster: dict[str, dict[str, float]] = {}
    for roster_id, entry in bucket["rosters"].items():
        if "seat_sensitivity" not in entry:
            continue
        row: dict[str, float] = {}
        for axis, key in (
            ("seat", "seat_sensitivity"),
            ("layout", "layout_sensitivity"),
            ("seed", "seed_sensitivity"),
        ):
            values = [v for v in entry[key].values() if v is not None]
            best = max(values) if values else 0.0
            axes[axis].append(best)
            row[axis] = best
        per_roster[roster_id] = row
    maxima = {axis: (max(vals) if vals else 0.0) for axis, vals in axes.items()}
    # "roster-specific rather than universal": the per-roster maxima must
    # not all be the same value on any axis, i.e. some rosters really are
    # more context-sensitive than others.
    roster_specific = {
        axis: len({round(row[axis], 6) for row in per_roster.values()}) > 1 for axis in axes
    }
    return {
        "max_range_pp": {axis: 100.0 * value for axis, value in maxima.items()},
        "per_roster_max_range": {
            r: {a: 100.0 * v for a, v in row.items()} for r, row in per_roster.items()
        },
        "roster_specific": roster_specific,
        "pass": all(value > 0.0 for value in maxima.values()) and any(roster_specific.values()),
    }


def criterion_4(bucket: dict[str, Any]) -> dict[str, Any]:
    """Kingmaking and pairwise-vs-group divergence."""

    kingmaking = []
    for search_roster, control_roster, passive in KINGMAKING_PAIRS:
        entry = bucket["rosters"].get(search_roster)
        control = bucket["rosters"].get(control_roster)
        if not entry or "entrants" not in entry:
            continue
        entrants = entry["entrants"]
        worker = max(
            entrants,
            key=lambda a: (entrants[a]["capture_caused"] or 0.0),
        )
        record = {
            "roster": search_roster,
            "worker": worker,
            "worker_caused": entrants[worker]["capture_caused"],
            "worker_win_rate": entrants[worker]["win_rate"],
            "passive": passive,
            "passive_caused": entrants.get(passive, {}).get("capture_caused"),
            "passive_win_rate": entrants.get(passive, {}).get("win_rate"),
            "control_roster": control_roster,
            "passive_win_rate_without_search": (
                control["entrants"].get(passive, {}).get("win_rate")
                if control and "entrants" in control
                else None
            ),
        }
        record["kingmaking"] = bool(
            record["worker_caused"]
            and record["passive_win_rate"] is not None
            and record["worker_win_rate"] is not None
            and record["worker_caused"] > (record["passive_caused"] or 0.0)
            and record["passive_win_rate"] > record["worker_win_rate"]
        )
        kingmaking.append(record)

    divergence = []
    for pair_id, pair in bucket["pairs"].items():
        candidate = pair["candidate"]
        opponent = pair["opponent"]
        for roster_id, entry in bucket["rosters"].items():
            roster = entry.get("roster", [])
            if candidate not in roster or opponent not in roster:
                continue
            group_rate = entry["entrants"][candidate]["win_rate"]
            if group_rate is None or pair["candidate_win_rate"] is None:
                continue
            divergence.append(
                {
                    "pair_id": pair_id,
                    "agent": candidate,
                    "opponent": opponent,
                    "roster": roster_id,
                    "pairwise_win_rate": pair["candidate_win_rate"],
                    "group_win_rate": group_rate,
                    "delta_pp": 100.0 * (group_rate - pair["candidate_win_rate"]),
                }
            )
    max_divergence = max((abs(d["delta_pp"]) for d in divergence), default=0.0)
    return {
        "kingmaking": kingmaking,
        "kingmaking_observed": any(k["kingmaking"] for k in kingmaking),
        "divergence": divergence,
        "max_divergence_pp": max_divergence,
        "pass": any(k["kingmaking"] for k in kingmaking) or max_divergence >= 10.0,
    }


def criterion_5(bucket: dict[str, Any]) -> dict[str, Any]:
    """No simple universal solution outside the negative-control roster."""

    highest: list[dict[str, Any]] = []
    for roster_id, entry in bucket["rosters"].items():
        if "entrants" not in entry or roster_id == NEGATIVE_CONTROL_ROSTER:
            continue
        for agent, stats in entry["entrants"].items():
            if stats["win_rate"] is not None:
                highest.append({"roster": roster_id, "agent": agent, "rate": stats["win_rate"]})
    highest.sort(key=lambda h: -h["rate"])
    negative_control = bucket["rosters"].get(NEGATIVE_CONTROL_ROSTER, {}).get("entrants", {})
    at_or_above_90 = [h for h in highest if h["rate"] >= 0.90]
    # A "simple universal solution" needs one strategy winning broadly
    # across *dissimilar* rosters, so a single agent at >=90% in two or
    # more non-control rosters is the failing shape, not one outlier.
    by_agent: dict[str, int] = {}
    for hit in at_or_above_90:
        by_agent[hit["agent"]] = by_agent.get(hit["agent"], 0) + 1
    universal = {a: n for a, n in by_agent.items() if n >= 2}
    return {
        "highest_non_control_rate": highest[0] if highest else None,
        "rosters_at_or_above_90pct": at_or_above_90,
        "agents_at_or_above_90pct_in_multiple_rosters": universal,
        "negative_control_rates": {
            a: v["win_rate"] for a, v in sorted(negative_control.items())
        },
        "pass": not universal,
    }


def score_condition(bucket: dict[str, Any]) -> dict[str, Any]:
    scores = {
        "condition_id": bucket["condition_id"],
        "arena_size": bucket["arena_size"],
        "instr_per_tick": bucket["instr_per_tick"],
        "criterion_1_multiple_viable_archetypes": criterion_1(bucket),
        "criterion_2_counter_strategies": criterion_2(bucket),
        "criterion_3_context_sensitivity": criterion_3(bucket),
        "criterion_4_multi_agent_specific": criterion_4(bucket),
        "criterion_5_no_universal_solution": criterion_5(bucket),
    }
    scores["criteria_passed"] = sum(
        1 for key, value in scores.items() if key.startswith("criterion_") and value["pass"]
    )
    return scores


# ---------------------------------------------------------------------------
# Ranking perturbation (Phase 1I)
# ---------------------------------------------------------------------------


def _intervals_disjoint(a: list[float] | None, b: list[float] | None) -> bool:
    if not a or not b:
        return False
    return a[1] < b[0] or b[1] < a[0]


def ranking_perturbation(
    bucket: dict[str, Any], reference: dict[str, Any]
) -> dict[str, Any]:
    """How much of the default condition's strategic ordering survives here.

    Reports leader changes and, more informatively, pairwise relationship
    reversals: for every unordered pair of roster members, whether the sign
    of their win-rate difference flipped relative to the default. A flip
    whose Wilson intervals are also disjoint at *both* conditions is marked
    separately, because Phase 1I explicitly warns against overinterpreting
    differences inside uncertainty intervals.
    """

    rosters = []
    total_pairs = 0
    reversed_pairs = 0
    significant_reversals = 0
    leader_changes = 0

    for roster_id, entry in sorted(bucket["rosters"].items()):
        base = reference["rosters"].get(roster_id)
        if not base or "entrants" not in entry or "entrants" not in base:
            continue
        agents = sorted(set(entry["entrants"]) & set(base["entrants"]))
        pair_records = []
        for i, left in enumerate(agents):
            for right in agents[i + 1 :]:
                here = (entry["entrants"][left]["win_rate"] or 0.0) - (
                    entry["entrants"][right]["win_rate"] or 0.0
                )
                there = (base["entrants"][left]["win_rate"] or 0.0) - (
                    base["entrants"][right]["win_rate"] or 0.0
                )
                total_pairs += 1
                flipped = (here > 0 > there) or (here < 0 < there)
                strong = flipped and _intervals_disjoint(
                    entry["entrants"][left]["interval"], entry["entrants"][right]["interval"]
                ) and _intervals_disjoint(
                    base["entrants"][left]["interval"], base["entrants"][right]["interval"]
                )
                if flipped:
                    reversed_pairs += 1
                if strong:
                    significant_reversals += 1
                pair_records.append(
                    {
                        "left": left,
                        "right": right,
                        "delta_pp_here": 100.0 * here,
                        "delta_pp_default": 100.0 * there,
                        "reversed": flipped,
                        "reversed_beyond_intervals": strong,
                    }
                )
        leader_changed = entry.get("leader") != base.get("leader")
        if leader_changed:
            leader_changes += 1
        rosters.append(
            {
                "roster_id": roster_id,
                "ordering_here": entry.get("ordering"),
                "ordering_default": base.get("ordering"),
                "leader_here": entry.get("leader"),
                "leader_default": base.get("leader"),
                "leader_changed": leader_changed,
                "pairs": pair_records,
            }
        )

    # A relationship reversal is deliberately strict: two agents that were
    # already statistically indistinguishable at the default can swap order
    # without that meaning anything. It would understate the experiment on
    # its own, though -- an agent can move 50 pp without reversing anything,
    # because it was already ahead. So the absolute move of each agent's own
    # rate is counted separately, and "material" means the two Wilson
    # intervals for the same agent in the same roster do not overlap.
    rate_moves: list[dict[str, Any]] = []
    for roster_id, entry in sorted(bucket["rosters"].items()):
        base = reference["rosters"].get(roster_id)
        if not base or "entrants" not in entry or "entrants" not in base:
            continue
        for agent in sorted(set(entry["entrants"]) & set(base["entrants"])):
            here = entry["entrants"][agent]
            there = base["entrants"][agent]
            if here["win_rate"] is None or there["win_rate"] is None:
                continue
            rate_moves.append(
                {
                    "roster_id": roster_id,
                    "agent": agent,
                    "win_rate_here": here["win_rate"],
                    "win_rate_default": there["win_rate"],
                    "delta_pp": 100.0 * (here["win_rate"] - there["win_rate"]),
                    "material": _intervals_disjoint(here["interval"], there["interval"]),
                }
            )
    material = [m for m in rate_moves if m["material"]]
    largest = max(rate_moves, key=lambda m: abs(m["delta_pp"]), default=None)

    return {
        "condition_id": bucket["condition_id"],
        "rosters_compared": len(rosters),
        "leader_changes": leader_changes,
        "pairwise_relationships": total_pairs,
        "pairwise_reversals": reversed_pairs,
        "pairwise_reversals_beyond_intervals": significant_reversals,
        "reversal_fraction": (reversed_pairs / total_pairs) if total_pairs else None,
        "rates_compared": len(rate_moves),
        "rates_changed_beyond_intervals": len(material),
        "largest_rate_move": largest,
        "mean_absolute_rate_move_pp": (
            sum(abs(m["delta_pp"]) for m in rate_moves) / len(rate_moves) if rate_moves else None
        ),
        "detail": rosters,
        "rate_moves": rate_moves,
    }


# ---------------------------------------------------------------------------
# Search / offense (Phase 1L)
# ---------------------------------------------------------------------------


def search_profile(bucket: dict[str, Any]) -> dict[str, Any]:
    def _agent_mean(agents: tuple[str, ...], field: str) -> float | None:
        values = [
            entry["entrants"][a][field]
            for entry in bucket["rosters"].values()
            for a in agents
            if a in entry.get("entrants", {}) and entry["entrants"][a][field] is not None
        ]
        return (sum(values) / len(values)) if values else None

    return {
        "condition_id": bucket["condition_id"],
        "arena_size": bucket["arena_size"],
        "instr_per_tick": bucket["instr_per_tick"],
        "search_win_rate": _agent_mean(SEARCH_AGENTS, "win_rate"),
        "expansion_win_rate": _agent_mean(EXPANSION_AGENTS, "win_rate"),
        "defense_win_rate": _agent_mean(DEFENSE_AGENTS, "win_rate"),
        "search_caused": _agent_mean(SEARCH_AGENTS, "capture_caused"),
        "expansion_caused": _agent_mean(EXPANSION_AGENTS, "capture_caused"),
        "defense_caused": _agent_mean(DEFENSE_AGENTS, "capture_caused"),
        "search_territory_pct": _agent_mean(SEARCH_AGENTS, "territory_last_pct"),
        "expansion_territory_pct": _agent_mean(EXPANSION_AGENTS, "territory_last_pct"),
    }


def saturation_profile(bucket: dict[str, Any]) -> dict[str, Any]:
    shapes = [
        entry["match_shape"] for entry in bucket["rosters"].values() if "match_shape" in entry
    ]
    densities = [entry["density"] for entry in bucket["rosters"].values() if "density" in entry]
    if not shapes:
        return {"condition_id": bucket["condition_id"]}
    captured = sum(s["entrant_termination_reasons"].get("core_captured", 0) for s in shapes)
    entrant_slots = sum(s["cells_read"] * 3 for s in shapes)
    return {
        "condition_id": bucket["condition_id"],
        "arena_size": bucket["arena_size"],
        "instr_per_tick": bucket["instr_per_tick"],
        "configured_sweeps": densities[0]["configured_sweeps_per_entrant"] if densities else None,
        "configured_pressure": (
            densities[0]["configured_aggregate_pressure"] if densities else None
        ),
        "realized_actions_per_cell": (
            sum(d["realized_aggregate_actions_per_cell"] for d in densities) / len(densities)
            if densities
            else None
        ),
        "saturation_mean_pct": sum(s["saturation_mean_pct"] or 0.0 for s in shapes) / len(shapes),
        "saturation_min_pct": min(s["saturation_min_pct"] or 0.0 for s in shapes),
        "saturation_max_pct": max(s["saturation_max_pct"] or 0.0 for s in shapes),
        "ticks_mean": sum(s["ticks_mean"] or 0.0 for s in shapes) / len(shapes),
        "capture_rate_per_entrant_slot": (captured / entrant_slots) if entrant_slots else None,
        "replay_bytes_mean": sum(s["replay_bytes_mean"] or 0.0 for s in shapes) / len(shapes),
    }


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------


def _fmt(value: float | None, width: int = 6, scale: float = 100.0, suffix: str = "%") -> str:
    if value is None:
        return f"{'--':>{width}}"
    return f"{value * scale:{width - len(suffix)}.1f}{suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="v3_phase1_ecology_rubric", description=__doc__)
    parser.add_argument("--stage", default="main")
    parser.add_argument("--output", type=Path, default=REPO / "runs" / "research_v3_phase1")
    parser.add_argument("--reference", default=DEFAULT_CONDITION)
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()

    analysis = load_analysis(args.stage, output)
    conditions = index_by_condition(analysis)
    if args.reference not in conditions:
        raise SystemExit(f"reference condition {args.reference!r} missing from the analysis")
    reference = conditions[args.reference]

    report: dict[str, Any] = {
        "stage": args.stage,
        "reference_condition": args.reference,
        "criteria_text": [{"name": n, "text": t} for n, t in CRITERIA],
        "rubric": [],
        "perturbation": [],
        "search": [],
        "saturation": [],
    }
    for condition_id in sorted(conditions, key=lambda c: (conditions[c]["arena_size"], conditions[c]["instr_per_tick"])):
        bucket = conditions[condition_id]
        report["rubric"].append(score_condition(bucket))
        report["perturbation"].append(ranking_perturbation(bucket, reference))
        report["search"].append(search_profile(bucket))
        report["saturation"].append(saturation_profile(bucket))

    _print_saturation(report)
    _print_rubric(report)
    _print_perturbation(report, args.reference)
    _print_search(report)

    destination = output / args.stage / "results" / f"phase1_{args.stage}_rubric.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {destination}")
    return 0


def _print_saturation(report: dict[str, Any]) -> None:
    print("=" * 118)
    print("ARENA SATURATION AND MATCH SHAPE (Phase 1M)")
    print("=" * 118)
    print(
        f"{'condition':>14s} {'arena':>7s} {'budget':>7s} {'S':>8s} {'P':>7s} "
        f"{'realized':>9s} {'sat%':>7s} {'ticks':>7s} {'capture/slot':>13s} {'replayKB':>9s}"
    )
    for row in report["saturation"]:
        if "saturation_mean_pct" not in row:
            continue
        print(
            f"{row['condition_id']:>14s} {row['arena_size']:>7d} {row['instr_per_tick']:>7d} "
            f"{row['configured_sweeps']:8.3f} {row['configured_pressure']:7.2f} "
            f"{row['realized_actions_per_cell']:9.3f} {row['saturation_mean_pct']:7.1f} "
            f"{row['ticks_mean']:7.0f} {_fmt(row['capture_rate_per_entrant_slot'], 13):>13s} "
            f"{row['replay_bytes_mean'] / 1000:9.0f}"
        )
    print("\nS = configured sweeps per entrant; P = entrants x S; realized = mean summed cpu_total / arena_size")


def _print_rubric(report: dict[str, Any]) -> None:
    print("\n" + "=" * 118)
    print("BETA2 PHASE 4 SEC 17 ECOLOGY RUBRIC, SCORED PER CONDITION")
    print("=" * 118)
    print(
        f"{'condition':>14s} {'C1 archetypes':>14s} {'C2 counter':>11s} {'C3 context':>11s} "
        f"{'C4 multi':>9s} {'C5 no-universal':>16s} {'passed':>7s}"
    )
    for row in report["rubric"]:
        c1 = row["criterion_1_multiple_viable_archetypes"]
        c2 = row["criterion_2_counter_strategies"]
        c3 = row["criterion_3_context_sensitivity"]
        c4 = row["criterion_4_multi_agent_specific"]
        c5 = row["criterion_5_no_universal_solution"]

        def _mark(value: dict[str, Any]) -> str:
            return "PASS" if value["pass"] else "FAIL"

        print(
            f"{row['condition_id']:>14s} "
            f"{_mark(c1) + ' (' + str(c1['distinct_leading_agents']) + ')':>14s} "
            f"{_mark(c2):>11s} {_mark(c3):>11s} {_mark(c4):>9s} {_mark(c5):>16s} "
            f"{row['criteria_passed']:>5d}/5"
        )


def _print_perturbation(report: dict[str, Any], reference: str) -> None:
    print("\n" + "=" * 118)
    print(f"RANKING PERTURBATION versus {reference} (Phase 1I)")
    print("=" * 118)
    print(
        f"{'condition':>14s} {'leaders':>8s} {'pair reversals':>15s} {'strict':>7s} "
        f"{'rates moved':>12s} {'mean |move|':>12s} {'largest move':>34s}"
    )
    for row in report["perturbation"]:
        largest = row["largest_rate_move"]
        largest_text = (
            f"{largest['agent']} in {largest['roster_id']} {largest['delta_pp']:+.0f}pp"
            if largest
            else "--"
        )
        print(
            f"{row['condition_id']:>14s} "
            f"{str(row['leader_changes']) + '/' + str(row['rosters_compared']):>8s} "
            f"{str(row['pairwise_reversals']) + '/' + str(row['pairwise_relationships']):>15s} "
            f"{row['pairwise_reversals_beyond_intervals']:>7d} "
            f"{str(row['rates_changed_beyond_intervals']) + '/' + str(row['rates_compared']):>12s} "
            f"{(row['mean_absolute_rate_move_pp'] or 0.0):>10.1f}pp "
            f"{largest_text:>34s}"
        )
    print()
    print(
        "'strict' counts pairwise reversals whose Wilson intervals are disjoint at BOTH "
        "conditions;"
    )
    print(
        "'rates moved' counts single-agent rates whose own interval is disjoint from its "
        "default interval."
    )


def _print_search(report: dict[str, Any]) -> None:
    print("\n" + "=" * 118)
    print("SEARCH / OFFENSE VERSUS EXPANSION AND DEFENSE (Phase 1L)")
    print("=" * 118)
    print(
        f"{'condition':>14s} {'search win':>11s} {'expand win':>11s} {'defend win':>11s} "
        f"{'search caused':>14s} {'other caused':>13s} {'search terr':>12s} {'expand terr':>12s}"
    )
    for row in report["search"]:
        other_caused = max(
            (row["expansion_caused"] or 0.0), (row["defense_caused"] or 0.0)
        )
        print(
            f"{row['condition_id']:>14s} {_fmt(row['search_win_rate'], 11):>11s} "
            f"{_fmt(row['expansion_win_rate'], 11):>11s} {_fmt(row['defense_win_rate'], 11):>11s} "
            f"{_fmt(row['search_caused'], 14):>14s} {_fmt(other_caused, 13):>13s} "
            f"{_fmt(row['search_territory_pct'], 12, scale=1.0):>12s} "
            f"{_fmt(row['expansion_territory_pct'], 12, scale=1.0):>12s}"
        )
    print("\nterritory columns are already percentages of the arena, so they compare across arena sizes")


if __name__ == "__main__":
    raise SystemExit(main())
