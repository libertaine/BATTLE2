"""v3 Research Closeout -- defensive-event line, empirical closure tests.

Implements the governing closeout task's Sec 4/5 (D1 blind-timer prediction
and the blind-versus-reactive discriminant). Read-only re-analysis of the
already-committed Phase 1 replay corpus through the frozen Phase 6 episode
detector (``tools/v3_phase6_defense_episode.py``, imported and never
copied or edited) -- no match is executed, no threshold or window is
changed, and no scoring/Ruleset/default is touched.

D1 -- blind timer prediction (Sec 4 of the closeout task)
-----------------------------------------------------------------------
``core_defender`` (``engine/src/battle_engine/data/reference_agents/
core_defender/agent.py``) reads ``observation.pc`` exactly once, on its
very first ``act()`` call, to learn its own spawn address; every
subsequent call ignores ``observation`` completely and returns whichever
address its own ``actions_taken`` counter and fixed ``REFRESH_EVERY``/
``expand_stride`` constants dictate. Its action stream is therefore fully
computable in advance, with zero knowledge of any opponent, by literally
re-running the same, real, unmodified agent class against a synthetic
observation stream -- which is what :func:`blind_core_defender_schedule`
does. Comparing that blind prediction against every qualifying Phase 6
reclaim where ``core_defender`` is the victim answers the closeout task's
load-bearing question directly: does the event require any concept of
defensive *response*, or does a deterministic, attack-blind timer already
account for it?

Blind-versus-reactive discriminant (Sec 5 of the closeout task)
-----------------------------------------------------------------------
:func:`blind_vs_reactive` reports ``core_defender`` and
``reactive_core_defender`` **separately** (never pooled into one
"defense" role) at every Phase 6 budget condition, on: opportunity-
conditioned qualifying rate, raw event rate, reclaim rate (>=1 reclaim
given an opportunity, regardless of whether the victim survived that
reclaim's tick), eventual survival, and eventual capture.

Usage::

    python tools/v3_closeout_defensive_timer.py timer --all
    python tools/v3_closeout_defensive_timer.py discriminant --all
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase6_defense_episode as phase6
from battle_engine.agent_api import ActionKind, MatchContext, Observation
from battle_engine.data.reference_agents.core_defender.agent import (
    DEFENDED_RADIUS,
    CoreDefenderAgent,
)
from battle_engine.python_runtime import CORE_SIZE
from battle_engine.replay import iter_replay

OUTPUT_ROOT = REPO / "runs" / "research_v3_closeout"
BUDGET_CONDITIONS = ("a4096_b2", "a4096_b8", "a4096_b32")


# ---------------------------------------------------------------------------
# D1: blind-timer prediction
# ---------------------------------------------------------------------------


def blind_core_defender_schedule(
    *, core_start: int, arena_size: int, instr_per_tick: int, tick_limit: int
) -> dict[int, set[int]]:
    """Every address ``core_defender`` writes into its *own* core window,
    by tick, replaying the real agent class against a synthetic
    observation stream that never reflects any opponent action.

    ``observation.pc`` is fixed at ``core_start`` for every call (matching
    the real runtime's contract that Python entrants never move their own
    ``pc``); every other ``Observation`` field is an inert placeholder,
    exactly as this agent's own source guarantees they must be, since it
    reads none of them after its first call.
    """

    agent = CoreDefenderAgent()
    context = MatchContext(
        agent_id="core_defender",
        seed=0,
        arena_size=arena_size,
        tick_limit=tick_limit,
        action_budget=instr_per_tick,
        rng=random.Random(0),
    )
    agent.reset(context)
    core_window = {(core_start + i) % arena_size for i in range(CORE_SIZE)}
    assert DEFENDED_RADIUS == CORE_SIZE, "core_defender's own defended radius must match CORE_SIZE"

    schedule: dict[int, set[int]] = defaultdict(set)
    obs = Observation(
        tick=0, agent_id="core_defender", pc=core_start, register_a=0, register_p=0,
        zero_flag=False, last_read=None, alive=True,
    )
    for tick in range(1, tick_limit + 1):
        for _slot in range(instr_per_tick):
            action = agent.act(obs)
            if action.kind == ActionKind.WRITE and action.operand is not None:
                address = action.operand % arena_size
                if address in core_window:
                    schedule[tick].add(address)
    return dict(schedule)


def _victim_core_start(result_path: Path, victim_seat: str) -> int:
    replay_path = result_path.parent / "replay.jsonl"
    for record in iter_replay(replay_path):
        if isinstance(record, phase6.TickSnapshot) and record.tick == 0:
            for state in record.agents:
                if state.agent_id == victim_seat:
                    return int(state.pc)
    raise ValueError(f"no tick-0 pc for {victim_seat} in {replay_path}")


def blind_timer_prediction(condition: str, *, threshold: int) -> dict[str, Any]:
    """D1 over one budget condition's full default-corpus group cells."""

    total_qualifying_reclaims = 0
    predicted_matches = 0
    unpredicted: list[dict[str, Any]] = []

    for result_path in phase6._cells_for_condition(condition, "group"):
        names, arena, action_budget = phase6._cell_metadata(result_path)
        core_defender_seats = [seat for seat, name in names.items() if name == "core_defender"]
        if not core_defender_seats:
            continue
        window = phase6.max_assault_ticks(action_budget)
        replay_path = result_path.parent / "replay.jsonl"
        episodes, _summary = phase6.reconstruct_episodes(
            list(iter_replay(replay_path)), arena_size=arena, threshold=threshold, window=window
        )
        victim_seat = core_defender_seats[0]
        qualifying_eps = [
            ep for ep in episodes
            if ep.victim == victim_seat and any(r.qualifying for r in ep.reclaims)
        ]
        if not qualifying_eps:
            continue

        repro = json.loads(result_path.read_text(encoding="utf-8"))["reproducibility"]
        tick_limit = int(repro["tick_limit"])
        core_start = _victim_core_start(result_path, victim_seat)
        schedule = blind_core_defender_schedule(
            core_start=core_start, arena_size=arena, instr_per_tick=action_budget, tick_limit=tick_limit
        )

        for ep in qualifying_eps:
            for reclaim in ep.reclaims:
                if not reclaim.qualifying:
                    continue
                total_qualifying_reclaims += 1
                predicted_here = schedule.get(reclaim.tick, set())
                if set(reclaim.cells).issubset(predicted_here):
                    predicted_matches += 1
                else:
                    unpredicted.append(
                        {
                            "cell": str(result_path.parent.relative_to(REPO)),
                            "tick": reclaim.tick,
                            "cells": list(reclaim.cells),
                            "predicted_addresses_that_tick": sorted(predicted_here),
                        }
                    )

    ratio = (predicted_matches / total_qualifying_reclaims) if total_qualifying_reclaims else None
    return {
        "condition": condition,
        "threshold": threshold,
        "observed_qualifying_reclaims": total_qualifying_reclaims,
        "predicted_timer_reclaims": predicted_matches,
        "ratio": ratio,
        "unpredicted_examples": unpredicted[:10],
    }


# ---------------------------------------------------------------------------
# Blind-versus-reactive discriminant
# ---------------------------------------------------------------------------


def blind_vs_reactive(condition: str, *, threshold: int) -> dict[str, Any]:
    cells = phase6.collect(condition, "group", threshold=threshold)
    stats: dict[str, dict[str, Any]] = {
        agent: {
            "appearances": 0,
            "opportunity_appearances": 0,
            "qualifying_appearances": 0,
            "reclaim_appearances": 0,
            "survived_to_end": 0,
            "captured": 0,
        }
        for agent in ("core_defender", "reactive_core_defender")
    }

    for cell in cells:
        names = cell["names"]
        by_seat_episodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ep in cell["episodes"]:
            by_seat_episodes[ep["victim_seat"]].append(ep)

        for seat, name in names.items():
            if name not in stats:
                continue
            s = stats[name]
            s["appearances"] += 1
            eps = by_seat_episodes.get(seat, [])
            opp_eps = [ep for ep in eps if ep["meaningful_progress"]]
            if opp_eps:
                s["opportunity_appearances"] += 1
                if any(ep["qualified"] for ep in opp_eps):
                    s["qualifying_appearances"] += 1
                if any(ep["reclaim_count"] > 0 for ep in opp_eps):
                    s["reclaim_appearances"] += 1
            summary = cell["summary"].get(name)
            if summary is not None:
                if summary["alive_at_end"]:
                    s["survived_to_end"] += 1
                if summary["captured_tick"] is not None:
                    s["captured"] += 1

    report: dict[str, Any] = {"condition": condition, "threshold": threshold, "by_agent": {}}
    for agent, s in stats.items():
        n = s["appearances"]
        n_opp = s["opportunity_appearances"]
        report["by_agent"][agent] = {
            "appearances": n,
            "opportunity_appearances": n_opp,
            "raw_event_rate": (s["qualifying_appearances"] / n) if n else None,
            "opportunity_conditioned_qualifying_rate": (s["qualifying_appearances"] / n_opp) if n_opp else None,
            "reclaim_rate_given_opportunity": (s["reclaim_appearances"] / n_opp) if n_opp else None,
            "eventual_survival_rate": (s["survived_to_end"] / n) if n else None,
            "eventual_capture_rate": (s["captured"] / n) if n else None,
        }

    cd = report["by_agent"]["core_defender"]
    rcd = report["by_agent"]["reactive_core_defender"]
    diffs = {}
    for metric in (
        "raw_event_rate",
        "opportunity_conditioned_qualifying_rate",
        "reclaim_rate_given_opportunity",
        "eventual_survival_rate",
        "eventual_capture_rate",
    ):
        a, b = rcd[metric], cd[metric]
        diffs[metric] = {
            "reactive_minus_blind": (a - b) if (a is not None and b is not None) else None,
            "reactive_outperforms_blind": (a > b) if (a is not None and b is not None) else None,
        }
    report["reactive_vs_blind"] = diffs
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_timer = sub.add_parser("timer")
    p_timer.add_argument("--condition", default="a4096_b8")
    p_timer.add_argument("--all", action="store_true")

    p_disc = sub.add_parser("discriminant")
    p_disc.add_argument("--condition", default="a4096_b8")
    p_disc.add_argument("--all", action="store_true")

    args = parser.parse_args(argv)
    gates = json.loads(phase6.GATES_PATH.read_text(encoding="utf-8"))
    threshold = gates["event_definition"]["episode_threshold"]
    conditions = list(BUDGET_CONDITIONS) if args.all else [args.condition]

    if args.cmd == "timer":
        report = {"threshold": threshold, "conditions": {}}
        for condition in conditions:
            result = blind_timer_prediction(condition, threshold=threshold)
            report["conditions"][condition] = result
            print(f"\n=== {condition} -- D1 blind-timer prediction ===")
            print(
                f"  observed qualifying reclaims: {result['observed_qualifying_reclaims']}  "
                f"predicted by blind timer: {result['predicted_timer_reclaims']}  "
                f"ratio: {result['ratio']}"
            )
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        dest = OUTPUT_ROOT / "closeout_d1_blind_timer.json"
        dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {dest}")
        return 0

    # discriminant
    report = {"threshold": threshold, "conditions": {}}
    for condition in conditions:
        result = blind_vs_reactive(condition, threshold=threshold)
        report["conditions"][condition] = result
        print(f"\n=== {condition} -- blind (core_defender) vs reactive (reactive_core_defender) ===")
        for agent, v in result["by_agent"].items():
            print(f"  {agent}: {v}")
        print(f"  reactive - blind: {result['reactive_vs_blind']}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    dest = OUTPUT_ROOT / "closeout_blind_vs_reactive.json"
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
