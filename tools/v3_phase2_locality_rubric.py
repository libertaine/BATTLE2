"""Score the Beta2 Sec 17 rubric across the v3 Phase 2 locality corpus and
evaluate the predeclared GO/MODIFY/ABANDON gates.

This is the analysis half of Phase 2. ``v3_phase2_locality_corpus.py``
executes the corpus and reduces every condition to measured aggregates;
this script reads that reduction, scores it, compares it against both
controls, and applies the gates exactly as
``v3_phase2_locality_corpus.json`` declared them before any main-stage
result existed.

**Every rubric number for both arms comes from the same code.** The five
criteria, the ranking-perturbation measure, the search/expansion/defense
profile and the saturation profile are ``v3_phase1_ecology_rubric``'s own
functions, imported here rather than reimplemented, with only their
role/roster constants rebound to the locality population. Two consequences
worth stating plainly:

* The Ruleset-v2 control arm is not merely *comparable* to the locality
  arm -- it is scored by literally the same lines, and its numbers are read
  from Phase 1's committed ``phase1_main_rubric.json`` without
  re-execution (Phase 2L Control 1).
* Criterion 2 names its 1v1 pair ids as literals inside the Phase 1
  function. Rather than modify a committed Phase 1 tool, the Phase 2
  buckets alias ``lclaimer_vs_ltracker`` into the slot Phase 1 calls
  ``claimer_vs_coretracker_400``. The second slot
  (``hunter_vs_coretracker_400``) is deliberately left **empty**: Phase 1
  scored criterion 2's first half as a disjunction over two expansion
  agents, and Phase 2's population has exactly one expansion archetype, so
  scoring it on one matchup is strictly stricter than Phase 1's own
  reading, never looser.

Usage, from the repo root with .venv active::

    python tools/v3_phase2_locality_rubric.py --output runs/research_v3_phase2
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase1_ecology_rubric as rubric
import v3_phase2_locality_corpus as corpus

PHASE1_ROOT = REPO / "runs" / "research_v3_phase1"

#: Phase 1's own literal pair-id slot for criterion 2's expansion-versus-search
#: matchup. Phase 2 aliases its single expansion matchup into this slot.
PHASE1_COUNTER_PAIR_SLOT = "claimer_vs_coretracker_400"
PHASE2_COUNTER_PAIR = "lclaimer_vs_ltracker"


@contextlib.contextmanager
def phase2_roles() -> Iterator[None]:
    """Rebind every Phase 1 rubric constant to the Phase 2 population."""

    definition = corpus.corpus_definition()
    roles = definition["roles"]
    saved = (
        rubric.SEARCH_AGENTS,
        rubric.EXPANSION_AGENTS,
        rubric.DEFENSE_AGENTS,
        rubric.NEGATIVE_CONTROL_ROSTER,
        rubric.KINGMAKING_PAIRS,
        rubric.DEFAULT_CONDITION,
    )
    rubric.SEARCH_AGENTS = tuple(roles["search"])
    rubric.EXPANSION_AGENTS = tuple(roles["expansion"])
    rubric.DEFENSE_AGENTS = tuple(roles["defense"])
    rubric.NEGATIVE_CONTROL_ROSTER = roles["negative_control_roster"]
    rubric.KINGMAKING_PAIRS = tuple(tuple(p) for p in definition["kingmaking_pairs"])
    rubric.DEFAULT_CONDITION = definition["stages"]["main"]["reference_condition"]
    try:
        yield
    finally:
        (
            rubric.SEARCH_AGENTS,
            rubric.EXPANSION_AGENTS,
            rubric.DEFENSE_AGENTS,
            rubric.NEGATIVE_CONTROL_ROSTER,
            rubric.KINGMAKING_PAIRS,
            rubric.DEFAULT_CONDITION,
        ) = saved


def build_buckets(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    buckets = rubric.index_by_condition(analysis)
    for bucket in buckets.values():
        pairs = bucket["pairs"]
        if PHASE2_COUNTER_PAIR in pairs:
            pairs[PHASE1_COUNTER_PAIR_SLOT] = pairs[PHASE2_COUNTER_PAIR]
        for row in bucket["rosters"].values():
            bucket.setdefault("arm", row.get("arm"))
            bucket.setdefault("locality_reach", row.get("locality_reach"))
    return buckets


# ---------------------------------------------------------------------------
# locality-specific measurement
# ---------------------------------------------------------------------------


def locality_profile(bucket: dict[str, Any]) -> dict[str, Any]:
    """Aggregate spatial behaviour per strategic role (Phase 2N item 4)."""

    roles = corpus.corpus_definition()["roles"]
    role_of: dict[str, str] = {}
    for role, agents in roles.items():
        if role == "negative_control_roster":
            continue
        for agent in agents:
            role_of[agent] = role

    per_agent: dict[str, dict[str, list[float]]] = {}
    for row in bucket["rosters"].values():
        for agent, stats in row["locality"]["by_agent"].items():
            store = per_agent.setdefault(agent, {})
            for key, value in stats.items():
                if value is not None:
                    store.setdefault(key, []).append(float(value))

    def _mean(values: list[float] | None) -> float | None:
        return (sum(values) / len(values)) if values else None

    agents = {
        agent: {key: _mean(values) for key, values in series.items()}
        for agent, series in per_agent.items()
    }
    by_role: dict[str, dict[str, float | None]] = {}
    for role in ("search", "expansion", "defense", "control"):
        members = [agents[a] for a in roles.get(role, []) if a in agents]
        if not members:
            continue
        by_role[role] = {
            key: _mean([m[key] for m in members if m.get(key) is not None])
            for key in ("move_share", "local_read_share", "local_write_share",
                        "moves", "distinct_loci", "core_distance_max",
                        "encounter_ticks", "opponent_core_reach_ticks", "reach_misses")
        }

    shares = [a["move_share"] for a in agents.values() if a.get("move_share") is not None]
    mobile = [
        (agent, stats["move_share"])
        for agent, stats in agents.items()
        if stats.get("move_share") is not None and stats["move_share"] > 0.0
    ]
    return {
        "condition_id": bucket["condition_id"],
        "by_agent": agents,
        "by_role": by_role,
        "mean_move_share": _mean(shares),
        "max_move_share": max(shares) if shares else None,
        "min_mobile_move_share": min((s for _a, s in mobile), default=None),
        "encounter_roster_coverage": _encounter_coverage(bucket, tuple(roles["search"])),
    }


def _encounter_coverage(bucket: dict[str, Any], search_agents: tuple[str, ...]) -> float | None:
    """Fraction of search-containing rosters with any measured encounter."""

    relevant = [
        row
        for row in bucket["rosters"].values()
        if any(agent in search_agents for agent in row["roster"])
    ]
    if not relevant:
        return None
    with_contact = 0
    for row in relevant:
        values = [
            stats.get("encounter_ticks") or 0.0
            for stats in row["locality"]["by_agent"].values()
        ]
        if any(value > 0 for value in values):
            with_contact += 1
    return with_contact / len(relevant)


def translation_sensitivity(bucket: dict[str, Any]) -> dict[str, Any]:
    """Phase 2J: outcome change under a pure translation of the layout.

    ``spread`` and ``spread-shifted`` have identical seat gaps and differ
    only by a half-gap phase shift, so the win-rate difference between them
    is translation sensitivity with relative geometry held fixed. ``close``
    changes the geometry and is reported separately, never folded in.
    """

    deltas: list[float] = []
    geometry_deltas: list[float] = []
    per_roster: dict[str, dict[str, float]] = {}
    for roster_id, row in bucket["rosters"].items():
        rates = row.get("layout_win_rates") or {}
        row_deltas: dict[str, float] = {}
        for agent, by_layout in rates.items():
            spread = by_layout.get("spread")
            shifted = by_layout.get("spread-shifted")
            close = by_layout.get("close")
            if spread is not None and shifted is not None:
                delta = abs(spread - shifted) * 100.0
                deltas.append(delta)
                row_deltas[agent] = delta
            if spread is not None and close is not None:
                geometry_deltas.append(abs(spread - close) * 100.0)
        if row_deltas:
            per_roster[roster_id] = row_deltas
    return {
        "condition_id": bucket["condition_id"],
        "translation_delta_pp_mean": (sum(deltas) / len(deltas)) if deltas else None,
        "translation_delta_pp_max": max(deltas) if deltas else None,
        "geometry_delta_pp_mean": (
            (sum(geometry_deltas) / len(geometry_deltas)) if geometry_deltas else None
        ),
        "geometry_delta_pp_max": max(geometry_deltas) if geometry_deltas else None,
        "per_roster": per_roster,
    }


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------


def phase1_control() -> tuple[dict[str, Any], dict[str, Any]]:
    """Phase 1's committed analysis and rubric for the Ruleset-v2 arm."""

    analysis_path = PHASE1_ROOT / "main" / "results" / "phase1_main_analysis.json"
    rubric_path = PHASE1_ROOT / "main" / "results" / "phase1_main_rubric.json"
    if not analysis_path.is_file() or not rubric_path.is_file():
        raise SystemExit(
            f"Ruleset-v2 control artifacts not found under {PHASE1_ROOT}. Phase 2L "
            "Control 1 reads Phase 1's committed corpus rather than re-executing it."
        )
    return (
        json.loads(analysis_path.read_text(encoding="utf-8")),
        json.loads(rubric_path.read_text(encoding="utf-8")),
    )


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------


def _wilson_disjoint(a: list[float] | None, b: list[float] | None) -> bool:
    return rubric._intervals_disjoint(a, b)


def evaluate_gates(
    scored: dict[str, dict[str, Any]],
    locality: dict[str, dict[str, Any]],
    translation: dict[str, dict[str, Any]],
    search: dict[str, dict[str, Any]],
    buckets: dict[str, dict[str, Any]],
    v2_rubric: dict[str, Any],
    v2_search: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    definition = corpus.corpus_definition()
    main = definition["stages"]["main"]
    reference = main["reference_condition"]
    control_map = main["ruleset_v2_control"]["condition_map"]
    l_ids = [c["id"] for c in main["conditions"] if c["arm"] == "locality"]
    g_ids = [c["id"] for c in main["conditions"] if c["arm"] == "global_reach_control"]
    density_of = {c["id"]: c["S"] for c in main["conditions"]}
    roles = definition["roles"]

    findings: dict[str, Any] = {}

    # -- G1: criterion 2 across distinct densities -------------------------
    c2_pass = {cid: scored[cid]["criterion_2_counter_strategies"]["pass"] for cid in l_ids}
    c2_densities = sorted({density_of[cid] for cid, ok in c2_pass.items() if ok})
    v2_c2 = main["ruleset_v2_control"]["phase1_criterion_2_result"]
    v2_densities = sorted(
        {
            density_of[l_id]
            for l_id, v_id in control_map.items()
            if v2_c2.get(v_id) == "PASS"
        }
    )
    findings["G1"] = {
        "locality_criterion_2_pass": c2_pass,
        "locality_densities_holding_criterion_2": c2_densities,
        "ruleset_v2_densities_holding_criterion_2": v2_densities,
        "holds": len(c2_densities) >= 2,
    }

    # -- G2: 5/5 conditions ------------------------------------------------
    l_five = [cid for cid in l_ids if scored[cid]["criteria_passed"] == 5]
    v2_scores = main["ruleset_v2_control"]["phase1_rubric_score"]
    v2_five = [v for v, s in v2_scores.items() if s == 5]
    findings["G2"] = {
        "locality_conditions_at_5_of_5": l_five,
        "ruleset_v2_conditions_at_5_of_5": sorted(v2_five),
        "holds": len(l_five) >= 4,
    }

    # -- G3: expansion loses its edge without becoming useless -------------
    expansion_agent = roles["expansion"][0]
    ref_bucket = buckets[reference]
    l_claimer = _role_mean(ref_bucket, (expansion_agent,), "win_rate")
    v2_claimer = _control_agent_rate(v2_search, "a4096_b8", "expansion_win_rate")
    l_expansion = search[reference]["expansion_win_rate"]
    findings["G3"] = {
        "locality_expansion_win_rate": l_claimer,
        "ruleset_v2_expansion_win_rate": v2_claimer,
        "holds": bool(
            l_claimer is not None
            and v2_claimer is not None
            and l_claimer < v2_claimer
            and (l_expansion or 0.0) >= 0.15
        ),
    }

    # -- G4: search competitive through its own mechanism ------------------
    qualifying = []
    for cid in l_ids:
        profile = search[cid]
        win = profile["search_win_rate"] or 0.0
        owns = (profile["search_caused"] or 0.0) > max(
            profile["expansion_caused"] or 0.0, profile["defense_caused"] or 0.0
        )
        if win >= 0.25 and owns:
            qualifying.append(cid)
    findings["G4"] = {
        "conditions_where_search_wins_25pct_and_owns_capture": qualifying,
        "densities": sorted({density_of[c] for c in qualifying}),
        "holds": len({density_of[c] for c in qualifying}) >= 2,
    }

    # -- G5: no universal solution ----------------------------------------
    universal = {
        cid: scored[cid]["criterion_5_no_universal_solution"][
            "agents_at_or_above_90pct_in_multiple_rosters"
        ]
        for cid in l_ids
    }
    findings["G5"] = {
        "agents_at_or_above_90pct_in_multiple_rosters": universal,
        "holds": not any(universal.values()),
    }

    # -- G6: context sensitivity ------------------------------------------
    ranges = {cid: scored[cid]["criterion_3_context_sensitivity"]["max_range_pp"] for cid in l_ids}
    all_nonzero = all(all(v > 0.0 for v in r.values()) for r in ranges.values())
    v2_seed = _control_c3(v2_rubric, "a4096_b8", "seed")
    l_seed = ranges[reference]["seed"]
    findings["G6"] = {
        "max_range_pp": ranges,
        "locality_seed_range_pp_at_reference": l_seed,
        "ruleset_v2_seed_range_pp_at_a4096_b8": v2_seed,
        "holds": bool(all_nonzero and v2_seed is not None and l_seed >= v2_seed),
    }

    # -- G7: pairwise-vs-group divergence ---------------------------------
    divergence = {
        cid: scored[cid]["criterion_4_multi_agent_specific"]["max_divergence_pp"]
        for cid in l_ids
    }
    findings["G7"] = {
        "max_divergence_pp": divergence,
        "holds": all(value >= 10.0 for value in divergence.values()),
    }

    # -- G8: movement/reconnaissance tradeoff ------------------------------
    ref_locality = locality[reference]
    spread_pp = None
    if ref_locality["max_move_share"] is not None and ref_locality["min_mobile_move_share"] is not None:
        spread_pp = 100.0 * (
            ref_locality["max_move_share"] - ref_locality["min_mobile_move_share"]
        )
    mean_share = ref_locality["mean_move_share"]
    findings["G8"] = {
        "mean_move_share": mean_share,
        "max_move_share": ref_locality["max_move_share"],
        "min_mobile_move_share": ref_locality["min_mobile_move_share"],
        "archetype_spread_pp": spread_pp,
        "by_role_move_share": {
            role: stats["move_share"] for role, stats in ref_locality["by_role"].items()
        },
        "holds": bool(
            mean_share is not None
            and 0.0 < mean_share < 0.5
            and spread_pp is not None
            and spread_pp >= 10.0
        ),
    }

    # -- G9: bounded reach itself does the work ----------------------------
    g_reference = "G_a4096_b8"
    moved = []
    if g_reference in buckets:
        for roster_id, row in buckets[reference]["rosters"].items():
            control_row = buckets[g_reference]["rosters"].get(roster_id)
            if not control_row:
                continue
            for agent, stats in row["entrants"].items():
                other = control_row["entrants"].get(agent)
                if not other:
                    continue
                if _wilson_disjoint(stats["interval"], other["interval"]):
                    moved.append(
                        {
                            "roster": roster_id,
                            "agent": agent,
                            "locality_rate": stats["win_rate"],
                            "global_reach_rate": other["win_rate"],
                        }
                    )
    findings["G9"] = {
        "rates_disjoint_from_global_reach_control": moved,
        "count": len(moved),
        "holds": len(moved) >= 4,
    }

    # -- G10: interaction stays frequent -----------------------------------
    coverage = {cid: locality[cid]["encounter_roster_coverage"] for cid in l_ids}
    findings["G10"] = {
        "search_roster_encounter_coverage": coverage,
        "holds": all(v is not None and v >= 0.80 for v in coverage.values()),
    }

    # -- ABANDON -----------------------------------------------------------
    abandon: dict[str, Any] = {}
    abandon["A1"] = {
        "mean_move_share_at_reference": mean_share,
        "holds": bool(mean_share is not None and mean_share >= 0.50),
    }
    abandon["A2"] = {
        "densities_holding_criterion_2": c2_densities,
        "other_go_criteria_met": [
            key for key in ("G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10")
            if findings[key]["holds"]
        ],
        "holds": bool(
            len(c2_densities) <= 1
            and not any(
                findings[key]["holds"]
                for key in ("G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10")
            )
        ),
    }
    tick_limit_no_capture = _tick_limit_without_capture(buckets, l_ids, tuple(roles["search"]))
    abandon["A3"] = {
        "share_of_search_roster_cells_at_tick_limit_without_capture": tick_limit_no_capture,
        "holds": bool(tick_limit_no_capture is not None and tick_limit_no_capture >= 0.50),
    }
    top_expansion = [
        cid
        for cid in l_ids
        if _top_role(search[cid]) == "expansion"
    ]
    search_below_15 = all((search[cid]["search_win_rate"] or 0.0) < 0.15 for cid in l_ids)
    abandon["A4"] = {
        "conditions_where_expansion_is_top_role": top_expansion,
        "search_below_15pct_everywhere": search_below_15,
        "holds": bool(len(top_expansion) >= 5 and search_below_15),
    }
    strictly_worse = []
    for l_id, v_id in control_map.items():
        l_profile = search.get(l_id)
        v_profile = v2_search.get(v_id)
        if not l_profile or not v_profile:
            continue
        worse_win = (l_profile["search_win_rate"] or 0.0) < (v_profile["search_win_rate"] or 0.0)
        worse_caused = (l_profile["search_caused"] or 0.0) < (v_profile["search_caused"] or 0.0)
        strictly_worse.append({"condition": l_id, "control": v_id,
                               "worse_win": worse_win, "worse_caused": worse_caused})
    abandon["A5"] = {
        "per_condition": strictly_worse,
        "holds": bool(strictly_worse) and all(
            row["worse_win"] and row["worse_caused"] for row in strictly_worse
        ),
    }
    camper = roles["control"][0]
    camper_leads = scored[reference]["criterion_1_multiple_viable_archetypes"]["leaders"].get(
        camper, []
    )
    abandon["A6"] = {
        "control_agent": camper,
        "rosters_led_at_reference": camper_leads,
        "holds": len(camper_leads) >= 4,
    }
    pilot_promotion = _pilot_promotion()
    abandon["A7"] = {
        "pilot_reach_star": pilot_promotion.get("reach_star"),
        "pilot_eligible": pilot_promotion.get("eligible"),
        "holds": pilot_promotion.get("reach_star") is None,
    }
    abandon["A8"] = {
        "note": "the complement of G9: bounded reach contributed nothing",
        "holds": not findings["G9"]["holds"],
    }
    v2_c3 = {axis: _control_c3(v2_rubric, "a4096_b8", axis) for axis in ("seat", "layout", "seed")}
    abandon["A9"] = {
        "locality_ranges_pp": ranges[reference],
        "ruleset_v2_ranges_pp": v2_c3,
        "holds": all(
            v2_c3[axis] is not None and ranges[reference][axis] < v2_c3[axis]
            for axis in ("seat", "layout", "seed")
        ),
    }

    go_held = [key for key in sorted(findings) if findings[key]["holds"]]
    abandon_held = [key for key in sorted(abandon) if abandon[key]["holds"]]

    if abandon_held:
        verdict = "LOCALITY NOT VALIDATED - ABANDON CURRENT V3 THESIS"
    elif findings["G1"]["holds"] and len(go_held) >= 6:
        verdict = "LOCALITY VALIDATED - PROCEED TO MULTI-LOCUS RESEARCH"
    else:
        verdict = "LOCALITY PROMISING - MODIFY BEFORE MULTI-LOCUS"

    return {
        "reference_condition": reference,
        "locality_conditions": l_ids,
        "global_reach_conditions": g_ids,
        "go": findings,
        "go_held": go_held,
        "abandon": abandon,
        "abandon_held": abandon_held,
        "decision_rule": definition["gates"]["decision_rule"],
        "verdict": verdict,
    }


def _role_mean(bucket: dict[str, Any], agents: tuple[str, ...], field: str) -> float | None:
    values = [
        row["entrants"][a][field]
        for row in bucket["rosters"].values()
        for a in agents
        if a in row.get("entrants", {}) and row["entrants"][a][field] is not None
    ]
    return (sum(values) / len(values)) if values else None


def _top_role(profile: dict[str, Any]) -> str:
    candidates = {
        "search": profile["search_win_rate"] or 0.0,
        "expansion": profile["expansion_win_rate"] or 0.0,
        "defense": profile["defense_win_rate"] or 0.0,
    }
    return max(candidates, key=lambda key: candidates[key])


def _control_agent_rate(
    v2_search: dict[str, dict[str, Any]], condition: str, field: str
) -> float | None:
    profile = v2_search.get(condition)
    return profile[field] if profile else None


def _control_c3(v2_rubric: dict[str, Any], condition: str, axis: str) -> float | None:
    for row in v2_rubric["rubric"]:
        if row["condition_id"] == condition:
            return row["criterion_3_context_sensitivity"]["max_range_pp"][axis]
    return None


def _tick_limit_without_capture(
    buckets: dict[str, dict[str, Any]], condition_ids: list[str], search_agents: tuple[str, ...]
) -> float | None:
    total = 0
    stalled = 0
    for cid in condition_ids:
        for row in buckets[cid]["rosters"].values():
            if not any(agent in search_agents for agent in row["roster"]):
                continue
            shape = row["match_shape"]
            cells = shape["cells_read"]
            if not cells:
                continue
            total += cells
            reasons = shape["termination_reasons"]
            captured = shape["entrant_termination_reasons"].get("core_captured", 0)
            tick_limited = reasons.get("TerminationReason.TICK_LIMIT", 0) + reasons.get(
                "tick_limit", 0
            )
            # A conservative upper bound: every tick-limited cell in a
            # condition with no captures at all is counted as stalled.
            stalled += tick_limited if captured == 0 else 0
    return (stalled / total) if total else None


def _pilot_promotion() -> dict[str, Any]:
    path = REPO / "runs" / "research_v3_phase2" / "pilot" / "results" / "phase2_pilot_promotion.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# presentation
# ---------------------------------------------------------------------------


def _pct(value: float | None, width: int = 6) -> str:
    return f"{'--':>{width}}" if value is None else f"{100.0 * value:>{width}.1f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=Path("runs/research_v3_phase2"))
    parser.add_argument("--stage", default="main")
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()

    analysis_path = output / args.stage / "results" / f"phase2_{args.stage}_analysis.json"
    if not analysis_path.is_file():
        raise SystemExit(f"{analysis_path} not found -- run the corpus and analyze it first")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    buckets = build_buckets(analysis)

    v2_analysis, v2_rubric = phase1_control()
    v2_buckets = rubric.index_by_condition(v2_analysis)

    definition = corpus.corpus_definition()
    main_stage = definition["stages"]["main"]
    # The gates are always evaluated against the declared main stage. A
    # non-main stage (the post-hoc reach diagnostic) is scored and printed
    # with the identical code but reported separately and never gated.
    reference = definition["stages"][args.stage].get(
        "reference_condition", main_stage["reference_condition"]
    )

    with phase2_roles():
        scored = {cid: rubric.score_condition(b) for cid, b in buckets.items()}
        search = {cid: rubric.search_profile(b) for cid, b in buckets.items()}
        saturation = {cid: rubric.saturation_profile(b) for cid, b in buckets.items()}
        perturbation = {
            cid: rubric.ranking_perturbation(b, buckets[reference])
            for cid, b in buckets.items()
        }
        locality = {cid: locality_profile(b) for cid, b in buckets.items()}
        translation = {cid: translation_sensitivity(b) for cid, b in buckets.items()}
    # The Ruleset-v2 arm keeps Phase 1's own role constants -- it is Phase
    # 1's population and must be profiled as Phase 1 profiled it.
    v2_search = {cid: rubric.search_profile(b) for cid, b in v2_buckets.items()}

    gates = (
        evaluate_gates(scored, locality, translation, search, buckets, v2_rubric, v2_search)
        if args.stage == "main"
        else {
            "verdict": "not evaluated: gates are scored only on the declared main stage",
            "go": {},
            "go_held": [],
            "abandon": {},
            "abandon_held": [],
            "decision_rule": definition["gates"]["decision_rule"],
            "reference_condition": reference,
        }
    )

    report = {
        "stage": args.stage,
        "corpus_id": definition["corpus_id"],
        "ruleset_id": definition["ruleset_id"],
        "reference_condition": reference,
        "reach_star": analysis.get("reach_star"),
        "criteria_text": [{"criterion": name, "text": text} for name, text in rubric.CRITERIA],
        "rubric": [scored[cid] for cid in sorted(scored)],
        "search": [search[cid] for cid in sorted(search)],
        "saturation": [saturation[cid] for cid in sorted(saturation)],
        "perturbation": {cid: perturbation[cid] for cid in sorted(perturbation)},
        "locality": [locality[cid] for cid in sorted(locality)],
        "translation": [translation[cid] for cid in sorted(translation)],
        "ruleset_v2_control": {
            "search": [v2_search[cid] for cid in sorted(main_stage["ruleset_v2_control"]["condition_map"].values())],
            "rubric_scores": main_stage["ruleset_v2_control"]["phase1_rubric_score"],
            "criterion_2": main_stage["ruleset_v2_control"]["phase1_criterion_2_result"],
        },
        "gates": gates,
    }
    path = output / args.stage / "results" / f"phase2_{args.stage}_rubric.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {path}")

    _print(report, buckets, scored, search, locality, translation, gates, main_stage)
    if args.stage != "main":
        print(
            "\n  (post-hoc diagnostic stage: the predeclared gates are evaluated only "
            "on the 'main' stage and are unaffected by anything above)"
        )
    return 0


def _print(report, buckets, scored, search, locality, translation, gates, main_stage) -> None:
    control_map = main_stage["ruleset_v2_control"]["condition_map"]
    v2_c2 = main_stage["ruleset_v2_control"]["phase1_criterion_2_result"]
    v2_score = main_stage["ruleset_v2_control"]["phase1_rubric_score"]
    density = {c["id"]: c["S"] for c in main_stage["conditions"]}

    print("\n== Beta2 Sec 17 rubric: locality arm vs Ruleset-v2 control ==")
    header = (
        f"{'condition':<15}{'S':>7}  C1  C2  C3  C4  C5  {'score':>6}   "
        f"{'v2 C2':>6}{'v2 score':>9}"
    )
    print(header)
    print("-" * len(header))
    for cid in sorted(scored):
        row = scored[cid]
        marks = []
        for key in (
            "criterion_1_multiple_viable_archetypes",
            "criterion_2_counter_strategies",
            "criterion_3_context_sensitivity",
            "criterion_4_multi_agent_specific",
            "criterion_5_no_universal_solution",
        ):
            marks.append(" P" if row[key]["pass"] else " F")
        control = control_map.get(cid)
        print(
            f"{cid:<15}{density.get(cid, 0):>7.3f}  " + "  ".join(marks)
            + f"  {row['criteria_passed']:>4}/5   "
            + (f"{v2_c2.get(control, '--'):>6}{v2_score.get(control, '--'):>7}/5" if control else f"{'--':>6}{'--':>9}")
        )

    print("\n== search / expansion / defense ==")
    header = (
        f"{'condition':<15}{'srch win':>9}{'expd win':>9}{'def win':>9}"
        f"{'srch cau':>9}{'expd cau':>9}{'def cau':>9}"
    )
    print(header)
    print("-" * len(header))
    for cid in sorted(search):
        p = search[cid]
        print(
            f"{cid:<15}{_pct(p['search_win_rate'], 9)}{_pct(p['expansion_win_rate'], 9)}"
            f"{_pct(p['defense_win_rate'], 9)}{_pct(p['search_caused'], 9)}"
            f"{_pct(p['expansion_caused'], 9)}{_pct(p['defense_caused'], 9)}"
        )

    print("\n== spatial behaviour (share of actions, by strategic role) ==")
    header = f"{'condition':<15}{'role':<12}{'move%':>8}{'read%':>8}{'write%':>8}{'moves':>8}{'loci':>8}{'enc':>8}"
    print(header)
    print("-" * len(header))
    for cid in sorted(locality):
        for role, stats in sorted(locality[cid]["by_role"].items()):
            print(
                f"{cid:<15}{role:<12}"
                f"{(100 * (stats['move_share'] or 0)):>8.1f}"
                f"{(100 * (stats['local_read_share'] or 0)):>8.1f}"
                f"{(100 * (stats['local_write_share'] or 0)):>8.1f}"
                f"{(stats['moves'] or 0):>8.0f}"
                f"{(stats['distinct_loci'] or 0):>8.0f}"
                f"{(stats['encounter_ticks'] or 0):>8.1f}"
            )

    print("\n== translation sensitivity (spread vs spread-shifted, same geometry) ==")
    header = f"{'condition':<15}{'transl mean':>13}{'transl max':>12}{'geom mean':>11}{'geom max':>10}"
    print(header)
    print("-" * len(header))
    for cid in sorted(translation):
        t = translation[cid]
        def _f(v, w):
            return f"{'--':>{w}}" if v is None else f"{v:>{w}.1f}"
        print(f"{cid:<15}{_f(t['translation_delta_pp_mean'], 13)}{_f(t['translation_delta_pp_max'], 12)}"
              f"{_f(t['geometry_delta_pp_mean'], 11)}{_f(t['geometry_delta_pp_max'], 10)}")

    if not gates["go"]:
        return
    print("\n== predeclared gates ==")
    for key in sorted(gates["go"]):
        print(f"  {key}  {'HOLDS ' if gates['go'][key]['holds'] else 'fails '}")
    print(f"  GO criteria held: {len(gates['go_held'])}/10  {gates['go_held']}")
    print("  ABANDON:")
    for key in sorted(gates["abandon"]):
        state = "HOLDS" if gates["abandon"][key]["holds"] else "fails"
        print(f"    {key}  {state}")
    print(f"\n  VERDICT: {gates['verdict']}")


if __name__ == "__main__":
    raise SystemExit(main())
