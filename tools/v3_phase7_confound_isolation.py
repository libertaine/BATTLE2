"""v3 Phase 7 -- high-budget defensive-event confound isolation.

Phase 6 (docs/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md)
qualified a cross-tick "attack episode" event and found it fails two
blocking gates (Q6 budget-robustness margin, Q7 seat robustness) at
``instr_per_tick=32`` only, through two independently diagnosed mechanisms:
(1) ``core_tracker``'s own ``expand_cursor`` starts with no offset from its
own core, so a same-tick assault's first "reclaim" is often just that
agent's routine first expansion write landing on its own core_start --
zero defensive intent -- inflating its opportunity-conditioned qualifying
rate to 50.0% and eating Q6's margin; (2) at high action budgets a genuine
assault can complete within a single tick, which -- under Bytefray's
sequential-quota scheduler -- denies an earlier-seated victim any chance to
react before the capture check fires that same tick, producing Q7's
64.9pp seat spread.

Phase 7 asks one causal question, stated precisely in the governing task:
is the high-budget failure an *agent confound* (H1: fix core_tracker's
cursor, selectivity/seat gates recover) or an *unavoidable scheduler
consequence* (H2: a one-block assault mechanically removes the victim's
chance to react, no matter which agent is holding the core)?

Two parts, corresponding to the two hypotheses, deliberately asymmetric in
whether they need new matches:

* **Part A** (``opportunity`` command) needs no new execution at all -- it
  is a pure re-analysis of the same committed Phase 1 replay artifacts
  Phase 6 already used, decomposed by a new derived predicate,
  :func:`had_reaction_opportunity`, built entirely on top of the frozen
  Phase 6 ``Episode``/``reconstruct_episodes`` machinery (imported, never
  copied or modified). This directly tests H2 without touching
  ``core_tracker`` at all: even holding the agent population fixed, does
  Bytefray's own scheduler mechanically deny a victim any chance to react
  once an assault completes within one tick?
* **Part B** (``run`` / ``compare`` commands) tests H1. It stages a
  disposable control agent, ``core_tracker_offset``
  (``engine/src/battle_engine/data/v3_phase7_agents/core_tracker_offset``)
  -- a byte-for-byte copy of the real, frozen ``core_tracker`` reference
  agent with exactly one line changed (``expand_cursor`` offset past its
  own core, mirroring ``core_defender``'s own precedent) -- and re-executes
  *only* the one roster where ``core_tracker`` is ever the victim of a
  genuine search-role assault (``hunter_coretracker_coreseeker``; every
  other ``core_tracker``-containing roster/pair has no second search agent
  to attack it, so the artifact cannot manifest there). Nothing about the
  frozen ``v2-baseline`` population, ``v2_baseline_corpus.json``, or any
  Phase 0-6 committed artifact is touched; the offset agent is staged
  directly into a disposable run directory and is never registered in any
  ``BenchmarkPopulation`` manifest.

The frozen Phase 6 detector (threshold, window formula, episode
open/extend/close rules) is reused completely unmodified throughout --
Phase 7 changes no threshold, no window, and no qualifying rule.

Usage, from the repo root with .venv active::

    python tools/v3_phase7_confound_isolation.py opportunity --all
    python tools/v3_phase7_confound_isolation.py run --workers 4
    python tools/v3_phase7_confound_isolation.py compare --all

See docs/V3_PHASE7_HIGH_BUDGET_CONFOUND_ISOLATION.md for the measured
results.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase1_arena_action_grid as phase1
import v3_phase6_defense_episode as phase6
from battle_engine.replay import iter_replay

OFFSET_AGENT_DIR = (
    REPO / "engine" / "src" / "battle_engine" / "data" / "v3_phase7_agents" / "core_tracker_offset"
)
CORE_SIZE_HINT = 8  # mirrors core_tracker's own public-knowledge constant

# The only group roster in the whole 11-roster v2-baseline corpus where
# core_tracker is ever the *victim* of a genuine search-role assault: every
# other core_tracker-containing roster/pair pairs it only with
# expansion/defense agents, and Q4 (Phase 6 Sec 13) measured 100%
# attacker-side purity for "meaningful progress" episodes at every budget --
# only a search-role agent (core_seeker or core_tracker) ever produces one.
DIAGNOSTIC_ROSTER = "hunter_coretracker_coreseeker"
PHASE7_ROSTER_ID = "hunter_coretracker_coreseeker_offset_control"
PHASE7_OUTPUT = REPO / "runs" / "research_v3_phase7"
BUDGET_CONDITIONS = ("a4096_b2", "a4096_b8", "a4096_b32")
ARENA_SIZE = 4096
TICKS = 400
SEEDS = "1,2,3"


# ---------------------------------------------------------------------------
# Staging + execution (Part B only)
# ---------------------------------------------------------------------------


def _stage_offset_agent(data_root: Path) -> Path:
    """Copy the disposable control agent into ``data_root/agents``.

    Deliberately not routed through ``stage_population``/``BenchmarkPopulation``
    -- this agent is not part of, and never becomes part of, any frozen
    benchmark manifest. A plain file copy is the whole staging step.
    """

    dest = data_root / "agents" / "core_tracker_offset"
    dest.mkdir(parents=True, exist_ok=True)
    for filename in ("agent.py", "agent.yaml"):
        (dest / filename).write_bytes((OFFSET_AGENT_DIR / filename).read_bytes())
    return dest


def cmd_run(output: Path, workers: str) -> int:
    from battle_engine.benchmarks import load_population, stage_population

    population = load_population()
    staged = stage_population(population, output)
    _stage_offset_agent(output)
    print(f"staged {len(staged)} frozen agents + 1 disposable control agent into {output}")

    ruleset = phase1.grid_definition()["ruleset_id"]
    roster = ["hunter", "core_tracker_offset", "core_seeker"]
    results = output / "results"

    for condition_id, budget in (("a4096_b2", 2), ("a4096_b8", 8), ("a4096_b32", 32)):
        out = results / condition_id / "group" / PHASE7_ROSTER_ID
        print(f"\n-- {condition_id}  arena {ARENA_SIZE}  budget {budget}  roster {roster}")
        elapsed, code = phase1._evaluate(
            [
                roster[0],
                "--opponents",
                ",".join(roster[1:]),
                "--ruleset",
                ruleset,
                "--group",
                "--seeds",
                SEEDS,
                "--ticks",
                str(TICKS),
                "--arena-size",
                str(ARENA_SIZE),
                "--instr-per-tick",
                str(budget),
                "--workers",
                workers,
            ],
            out,
            output,
        )
        print(f"   {condition_id:12s} {elapsed:7.1f}s  exit {code}")
        if code != 0:
            return code
    return 0


# ---------------------------------------------------------------------------
# Reaction-opportunity predicate (Part A)
# ---------------------------------------------------------------------------


def had_reaction_opportunity(ep: phase6.Episode) -> bool:
    """Did the victim have any scheduling chance to react before capture?

    Grounded directly in Phase 6's own mechanics audit (its report Sec 4,
    reconfirmed by ``engine/src/battle_engine/scheduler.py``'s
    ``run_sequential_quota``): every alive seat gets its full action quota,
    once per tick, in fixed match order (seat labels 'A' < 'B' < 'C' *are*
    that order -- confirmed against a committed result.json's own
    ``reproducibility.entrant_order``), and ``apply_core_capture`` runs once
    per tick, after every seat's actions that tick.

    An episode that does not end in capture trivially was never denied a
    chance (it was not captured at all). An episode spanning more than one
    tick always gives the victim at least one action block, on some
    intervening tick, that runs before the attacker's *next* tick's block --
    true regardless of seat order, which is exactly the cross-tick
    advantage Phase 6's whole design exists to provide. Only a *single-tick*
    episode (the entire hostile-acquisition-through-capture sequence
    completes within the attacker's own one action block) can deny the
    victim any chance at all, and only when the victim's seat is scheduled
    *before* the attacker's that tick -- it already used its own action
    block earlier in the tick, before the attacker had even acted, and gets
    no second chance because the capture check fires before its next tick
    arrives.
    """

    if ep.end_reason != "captured":
        return True
    if ep.start_tick is None or ep.end_tick is None:
        return True
    if ep.end_tick > ep.start_tick:
        return True
    return ep.victim > ep.attacker


# ---------------------------------------------------------------------------
# Shared cell/episode loading (parametrized over which results root)
# ---------------------------------------------------------------------------


def _cells_under(results_root: Path, condition: str, kind: str, rosters: tuple[str, ...] | None = None) -> list[Path]:
    root = results_root / condition / kind
    if not root.is_dir():
        raise SystemExit(f"missing corpus: {root}")
    paths: list[Path] = []
    roster_dirs = [root / r for r in rosters] if rosters else sorted(root.iterdir())
    for roster_dir in roster_dirs:
        if not roster_dir.is_dir():
            continue
        paths += sorted(roster_dir.glob("matches/*/result.json"))
    return paths


def _episodes_for_cell(result_path: Path, *, threshold: int) -> tuple[dict[str, str], int, int, list[Any]]:
    """Reconstruct one cell's episodes using the frozen Phase 6 reconstructor.

    Returns ``(names, arena_size, action_budget, episodes)``.
    """

    names, arena, action_budget = phase6._cell_metadata(result_path)
    window = phase6.max_assault_ticks(action_budget)
    replay_path = result_path.parent / "replay.jsonl"
    episodes, _ = phase6.reconstruct_episodes(
        iter_replay(replay_path), arena_size=arena, threshold=threshold, window=window
    )
    return names, arena, action_budget, episodes


# ---------------------------------------------------------------------------
# Part A: reaction-opportunity report (no new matches)
# ---------------------------------------------------------------------------


def reaction_opportunity_report(condition: str, *, threshold: int, results_root: Path = phase6.PHASE1) -> dict[str, Any]:
    paths = _cells_under(results_root, condition, "group")

    role_opp: Counter[str] = Counter()
    role_had_opp: Counter[str] = Counter()
    role_qual_given_opp: Counter[str] = Counter()
    role_qual_given_no_opp: Counter[str] = Counter()

    seat_opp: Counter[str] = Counter()
    seat_captured: Counter[str] = Counter()
    pair_captured: Counter[tuple[str, str]] = Counter()  # (attacker_seat, victim_seat)

    defense_seat_opp: Counter[str] = Counter()
    defense_seat_had_opp: Counter[str] = Counter()
    defense_seat_qual: Counter[str] = Counter()
    defense_seat_qual_given_opp_to_act: Counter[str] = Counter()

    for result_path in paths:
        names, _arena, action_budget, episodes = _episodes_for_cell(result_path, threshold=threshold)
        window = phase6.max_assault_ticks(action_budget)
        for ep in episodes:
            if not ep.meaningful_progress_windowed(threshold, window):
                continue
            victim_name = names.get(ep.victim, ep.victim)
            role = phase6.ROLE_OF.get(victim_name, "other")
            had_opp = had_reaction_opportunity(ep)

            role_opp[role] += 1
            if had_opp:
                role_had_opp[role] += 1
                if ep.qualified:
                    role_qual_given_opp[role] += 1
            else:
                if ep.qualified:
                    role_qual_given_no_opp[role] += 1  # sanity: should be ~0

            seat_opp[ep.victim] += 1
            if ep.end_reason == "captured":
                seat_captured[ep.victim] += 1
                pair_captured[(ep.attacker, ep.victim)] += 1

            if role == "defense":
                defense_seat_opp[ep.victim] += 1
                if had_opp:
                    defense_seat_had_opp[ep.victim] += 1
                if ep.qualified:
                    defense_seat_qual[ep.victim] += 1
                    if had_opp:
                        defense_seat_qual_given_opp_to_act[ep.victim] += 1

    def _rate(numer: Counter, denom: Counter, key: str) -> float | None:
        n = denom.get(key, 0)
        return (numer.get(key, 0) / n) if n else None

    by_role = {
        role: {
            "opportunities": role_opp[role],
            "had_reaction_opportunity": role_had_opp[role],
            "p_had_reaction_opportunity": (role_had_opp[role] / role_opp[role]) if role_opp[role] else None,
            "qualified_given_had_opportunity": role_qual_given_opp[role],
            "event_rate_given_opportunity_to_act": (
                (role_qual_given_opp[role] / role_had_opp[role]) if role_had_opp[role] else None
            ),
            "qualified_with_no_opportunity_to_act": role_qual_given_no_opp[role],
        }
        for role in sorted(role_opp)
    }

    defense_seats = sorted(defense_seat_opp)
    defense_seat_rates = {
        seat: {
            "opportunities": defense_seat_opp[seat],
            "p_had_reaction_opportunity": _rate(defense_seat_had_opp, defense_seat_opp, seat),
            "qualifying_rate_unconditional": _rate(defense_seat_qual, defense_seat_opp, seat),
            "qualifying_rate_given_opportunity_to_act": _rate(
                defense_seat_qual_given_opp_to_act, defense_seat_had_opp, seat
            ),
        }
        for seat in defense_seats
    }
    unconditional_values = [v["qualifying_rate_unconditional"] for v in defense_seat_rates.values() if v["qualifying_rate_unconditional"] is not None]
    conditional_values = [v["qualifying_rate_given_opportunity_to_act"] for v in defense_seat_rates.values() if v["qualifying_rate_given_opportunity_to_act"] is not None]

    return {
        "condition": condition,
        "threshold": threshold,
        "cells_analysed": len(paths),
        "by_role": by_role,
        "capture_rate_by_victim_seat": {
            seat: (seat_captured[seat] / seat_opp[seat]) if seat_opp[seat] else None for seat in sorted(seat_opp)
        },
        "capture_counts_by_attacker_victim_seat_pair": {f"{a}->{v}": n for (a, v), n in sorted(pair_captured.items())},
        "defense_seat_breakdown": defense_seat_rates,
        "defense_seat_spread_unconditional": (max(unconditional_values) - min(unconditional_values)) if unconditional_values else None,
        "defense_seat_spread_given_opportunity_to_act": (max(conditional_values) - min(conditional_values)) if conditional_values else None,
    }


# ---------------------------------------------------------------------------
# Part B: original vs offset tracker (needs the new Phase 7 corpus)
# ---------------------------------------------------------------------------


def _agent_opportunity_rate(paths: list[Path], *, threshold: int, agent_name: str) -> dict[str, Any]:
    """Opportunity-conditioned qualifying rate for one agent name, restricted
    to the given cells -- mirrors ``phase6.qualify_condition``'s per-agent
    computation but scoped to an arbitrary cell set (one roster/one corpus)."""

    appearances = 0
    opp_appearances: set[tuple[str, str]] = set()
    qual_appearances: set[tuple[str, str]] = set()
    self_reclaim_own_core_first_action = 0

    for result_path in paths:
        names, _arena, action_budget, episodes = _episodes_for_cell(result_path, threshold=threshold)
        window = phase6.max_assault_ticks(action_budget)
        if agent_name not in names.values():
            continue
        appearances += 1
        cell_key = (result_path.parent.parent.parent.parent.parent.name, result_path.parent.name)
        for ep in episodes:
            victim_name = names.get(ep.victim, ep.victim)
            if victim_name != agent_name:
                continue
            if not ep.meaningful_progress_windowed(threshold, window):
                continue
            opp_appearances.add(cell_key)
            if ep.qualified:
                qual_appearances.add(cell_key)
                # Phase 6 Sec 15's specific diagnosed artifact: the
                # qualifying reclaim is the victim's very own first action,
                # on the same tick the episode opened, at exactly its own
                # core_start + 0. Counted here so Part B can report directly
                # whether this specific artifact -- not just the aggregate
                # rate -- actually stops occurring under the offset control.
                first_reclaim = ep.reclaims[0] if ep.reclaims else None
                if first_reclaim is not None and first_reclaim.tick == ep.start_tick:
                    self_reclaim_own_core_first_action += 1

    n_opp = len(opp_appearances)
    n_qual = len(qual_appearances)
    return {
        "agent": agent_name,
        "appearances": appearances,
        "opportunity_appearances": n_opp,
        "qualifying_appearances": n_qual,
        "opportunity_conditioned_rate": (n_qual / n_opp) if n_opp else None,
        "same_tick_own_first_action_reclaims": self_reclaim_own_core_first_action,
    }


def compare_condition(condition: str, *, threshold: int) -> dict[str, Any]:
    original_paths = _cells_under(phase6.PHASE1, condition, "group", rosters=(DIAGNOSTIC_ROSTER,))
    offset_paths = _cells_under(PHASE7_OUTPUT / "results", condition, "group", rosters=(PHASE7_ROSTER_ID,))

    original = _agent_opportunity_rate(original_paths, threshold=threshold, agent_name="core_tracker")
    offset = _agent_opportunity_rate(offset_paths, threshold=threshold, agent_name="core_tracker_offset")

    # Corpus-wide Q6-equivalent margin, recomputed with the offset agent's
    # rate substituted for core_tracker's own rate as the search-role
    # candidate -- every other roster/agent held at its original Phase 1
    # value. This isolates exactly how much of Q6's own margin loss at this
    # budget is attributable to core_tracker specifically.
    full = phase6.qualify_condition(condition, "group", threshold=threshold)
    non_defense_rates = [
        v["opportunity_conditioned_rate"]
        for agent, v in full["by_agent"].items()
        if v["role"] in ("search", "expansion") and agent != "core_tracker" and v["opportunity_conditioned_rate"] is not None
    ]
    if offset["opportunity_conditioned_rate"] is not None:
        non_defense_rates.append(offset["opportunity_conditioned_rate"])
    corrected_max_non_defense = max(non_defense_rates, default=0.0)
    corrected_margin = (
        (full["min_defense_opportunity_rate"] - corrected_max_non_defense)
        if full["min_defense_opportunity_rate"] is not None
        else None
    )

    return {
        "condition": condition,
        "threshold": threshold,
        "core_tracker_original": original,
        "core_tracker_offset": offset,
        "full_corpus_q6_margin_original": (
            (full["min_defense_opportunity_rate"] - max(full["max_search_opportunity_rate"], full["max_expansion_opportunity_rate"]))
            if full["min_defense_opportunity_rate"] is not None
            else None
        ),
        "full_corpus_q6_margin_with_offset_tracker_substituted": corrected_margin,
        "q7_defense_seat_spread_original": full["seat_spread_defense"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_opp = sub.add_parser("opportunity", help="Part A: reaction-opportunity report, no new matches")
    p_opp.add_argument("--condition", default="a4096_b8")
    p_opp.add_argument("--all", action="store_true")
    p_opp.add_argument("--threshold", type=int, default=None, help="defaults to the Phase 6 gates value")

    p_run = sub.add_parser("run", help="Part B: execute the disposable offset-tracker corpus")
    p_run.add_argument("--output", type=Path, default=PHASE7_OUTPUT)
    p_run.add_argument("--workers", default="4")

    p_cmp = sub.add_parser("compare", help="Part B: original vs offset tracker")
    p_cmp.add_argument("--condition", default="a4096_b8")
    p_cmp.add_argument("--all", action="store_true")
    p_cmp.add_argument("--threshold", type=int, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "run":
        return cmd_run(args.output.expanduser().resolve(), args.workers)

    gates = json.loads(phase6.GATES_PATH.read_text(encoding="utf-8"))
    default_threshold = gates["event_definition"]["episode_threshold"]

    if args.cmd == "opportunity":
        threshold = args.threshold or default_threshold
        conditions = list(BUDGET_CONDITIONS) if args.all else [args.condition]
        report = {"threshold": threshold, "conditions": {}}
        for condition in conditions:
            result = reaction_opportunity_report(condition, threshold=threshold)
            report["conditions"][condition] = result
            print(f"\n=== {condition} (threshold={threshold}) -- reaction-opportunity report ===")
            for role, v in result["by_role"].items():
                print(
                    f"  {role:<10s} opp={v['opportunities']:4d} "
                    f"P(had_opportunity)={v['p_had_reaction_opportunity']}"
                    f"  event_rate|opportunity_to_act={v['event_rate_given_opportunity_to_act']}"
                )
            print(f"  defense seat spread, unconditional:            {result['defense_seat_spread_unconditional']}")
            print(f"  defense seat spread, given opportunity to act:  {result['defense_seat_spread_given_opportunity_to_act']}")
        PHASE7_OUTPUT.mkdir(parents=True, exist_ok=True)
        dest = PHASE7_OUTPUT / "phase7_opportunity_report.json"
        dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {dest}")
        return 0

    # compare
    threshold = args.threshold or default_threshold
    conditions = list(BUDGET_CONDITIONS) if args.all else [args.condition]
    report = {"threshold": threshold, "conditions": {}}
    for condition in conditions:
        result = compare_condition(condition, threshold=threshold)
        report["conditions"][condition] = result
        print(f"\n=== {condition} (threshold={threshold}) -- core_tracker vs core_tracker_offset ===")
        print(f"  original: {result['core_tracker_original']}")
        print(f"  offset:   {result['core_tracker_offset']}")
        print(f"  Q6 margin original:            {result['full_corpus_q6_margin_original']}")
        print(f"  Q6 margin, offset substituted:  {result['full_corpus_q6_margin_with_offset_tracker_substituted']}")
        print(f"  Q7 defense seat spread (unaffected by tracker identity): {result['q7_defense_seat_spread_original']}")
    PHASE7_OUTPUT.mkdir(parents=True, exist_ok=True)
    dest = PHASE7_OUTPUT / "phase7_compare_report.json"
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
