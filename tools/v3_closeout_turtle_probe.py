"""v3 Research Closeout -- E8 turtle-control probe (Sec 6 of the governing task).

The Phase 5 design proposal declared, but never ran, an "E8 turtle
control" gate: "A deliberately passive/immobile probe agent (analogous to
Phase 2's ``local_camper``) must not become competitive at any tested
``w_defense``" (``docs/V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md``
Sec 5B.3). Phase 5B -- the scoring experiment E8 was declared for -- never
ran, because Phase 5A itself failed qualification first. There is no
``w_defense`` scoring Ruleset to test "competitiveness" against.

This tool instantiates the *behavior* E8 declared (a maximally passive,
own-core-only writer, "analogous to ... local_camper") and measures it
against the mechanism that *is* implemented and still live at this point
in the research program: Phase 6's active-defense event
(``tools/v3_phase6_defense_episode.py``, imported and never edited). The
probe agent
(``engine/src/battle_engine/data/v3_closeout_agents/turtle_core_refresher``)
is disposable research tooling only -- never registered in any
``BenchmarkPopulation`` manifest, never added to ``v2_baseline_corpus.json``,
and no production agent is touched.

Design: substitute the probe for ``core_defender`` in the
``coredefender_reactive_coreseeker`` roster shape, keeping the real,
untouched ``reactive_core_defender`` and ``core_seeker`` in the same
match, at Phase 6's own three budget conditions and Phase 1's own
seed/layout/permutation methodology (3 seeds x 3 layouts x 6 seat
permutations = 54 cells/condition). This lets the probe be compared,
cell-for-cell-comparable, against the real ``reactive_core_defender`` in
the same matches, and against Phase 6's own published rate for real
``core_defender`` in the *same* roster shape (recomputed here, restricted
to that one roster, for a fair matched comparison rather than the
full-corpus aggregate).

Usage::

    python tools/v3_closeout_turtle_probe.py run --workers 4
    python tools/v3_closeout_turtle_probe.py analyze --all
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
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase1_arena_action_grid as phase1
import v3_phase6_defense_episode as phase6

PROBE_AGENT_DIR = REPO / "engine" / "src" / "battle_engine" / "data" / "v3_closeout_agents" / "turtle_core_refresher"
ORIGINAL_ROSTER = "coredefender_reactive_coreseeker"
PROBE_ROSTER_ID = "turtle_reactive_coreseeker_probe"
OUTPUT_ROOT = REPO / "runs" / "research_v3_closeout"
BUDGET_CONDITIONS = ("a4096_b2", "a4096_b8", "a4096_b32")
ARENA_SIZE = 4096
TICKS = 400
SEEDS = "1,2,3"


def _stage_probe_agent(data_root: Path) -> Path:
    """Plain file copy into the run's disposable ``agents/`` directory --
    never routed through ``stage_population``/``BenchmarkPopulation``, so
    this probe never becomes part of any frozen manifest."""

    dest = data_root / "agents" / "turtle_core_refresher"
    dest.mkdir(parents=True, exist_ok=True)
    for filename in ("agent.py", "agent.yaml"):
        (dest / filename).write_bytes((PROBE_AGENT_DIR / filename).read_bytes())
    return dest


def cmd_run(output: Path, workers: str) -> int:
    from battle_engine.benchmarks import load_population, stage_population

    population = load_population()
    stage_population(population, output)
    _stage_probe_agent(output)

    ruleset = phase1.grid_definition()["ruleset_id"]
    roster = ["turtle_core_refresher", "reactive_core_defender", "core_seeker"]
    results = output / "results"

    for condition_id, budget in (("a4096_b2", 2), ("a4096_b8", 8), ("a4096_b32", 32)):
        out = results / condition_id / "group" / PROBE_ROSTER_ID
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


def _agent_rate(paths: list[Path], *, threshold: int, agent_name: str) -> dict[str, Any]:
    appearances = 0
    opp_appearances: set[tuple[str, str]] = set()
    qual_appearances: set[tuple[str, str]] = set()
    reclaim_appearances: set[tuple[str, str]] = set()
    survived = 0
    captured = 0

    for result_path in paths:
        names, arena, action_budget = phase6._cell_metadata(result_path)
        if agent_name not in names.values():
            continue
        appearances += 1
        cell_key = (result_path.parent.parent.parent.parent.parent.name, result_path.parent.name)
        window = phase6.max_assault_ticks(action_budget)
        replay_path = result_path.parent / "replay.jsonl"
        episodes, summary = phase6.reconstruct_episodes(
            list(phase6.iter_replay(replay_path)), arena_size=arena, threshold=threshold, window=window
        )
        seat = next(s for s, n in names.items() if n == agent_name)
        for ep in episodes:
            if ep.victim != seat or not ep.meaningful_progress_windowed(threshold, window):
                continue
            opp_appearances.add(cell_key)
            if any(r.qualifying for r in ep.reclaims):
                qual_appearances.add(cell_key)
            if ep.reclaims:
                reclaim_appearances.add(cell_key)
        s = summary.get(seat)
        if s is not None:
            if s["alive_at_end"]:
                survived += 1
            if s["captured_tick"] is not None:
                captured += 1

    n = appearances
    n_opp = len(opp_appearances)
    return {
        "agent": agent_name,
        "appearances": n,
        "opportunity_appearances": n_opp,
        "qualifying_appearances": len(qual_appearances),
        "raw_event_rate": (len(qual_appearances) / n) if n else None,
        "opportunity_conditioned_qualifying_rate": (len(qual_appearances) / n_opp) if n_opp else None,
        "reclaim_rate_given_opportunity": (len(reclaim_appearances) / n_opp) if n_opp else None,
        "eventual_survival_rate": (survived / n) if n else None,
        "eventual_capture_rate": (captured / n) if n else None,
    }


def analyze_condition(condition: str, *, threshold: int) -> dict[str, Any]:
    original_paths = phase6._cells_for_condition(condition, "group", rosters=(ORIGINAL_ROSTER,))
    probe_paths = [
        p for p in (OUTPUT_ROOT / "results" / condition / "group" / PROBE_ROSTER_ID).glob("matches/*/result.json")
    ]

    return {
        "condition": condition,
        "threshold": threshold,
        "matched_roster_shape": ORIGINAL_ROSTER,
        "real_core_defender_in_matched_roster": _agent_rate(original_paths, threshold=threshold, agent_name="core_defender"),
        "real_reactive_core_defender_in_matched_roster": _agent_rate(
            original_paths, threshold=threshold, agent_name="reactive_core_defender"
        ),
        "turtle_probe": _agent_rate(probe_paths, threshold=threshold, agent_name="turtle_core_refresher"),
        "real_reactive_core_defender_alongside_turtle": _agent_rate(
            probe_paths, threshold=threshold, agent_name="reactive_core_defender"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run")
    p_run.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    p_run.add_argument("--workers", default="4")

    p_an = sub.add_parser("analyze")
    p_an.add_argument("--condition", default="a4096_b8")
    p_an.add_argument("--all", action="store_true")
    p_an.add_argument("--threshold", type=int, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "run":
        return cmd_run(args.output.expanduser().resolve(), args.workers)

    gates = json.loads(phase6.GATES_PATH.read_text(encoding="utf-8"))
    threshold = args.threshold or gates["event_definition"]["episode_threshold"]
    conditions = list(BUDGET_CONDITIONS) if args.all else [args.condition]
    report = {"threshold": threshold, "conditions": {}}
    for condition in conditions:
        result = analyze_condition(condition, threshold=threshold)
        report["conditions"][condition] = result
        print(f"\n=== {condition} (threshold={threshold}) -- turtle probe vs matched roster ===")
        for key in (
            "real_core_defender_in_matched_roster",
            "real_reactive_core_defender_in_matched_roster",
            "turtle_probe",
            "real_reactive_core_defender_alongside_turtle",
        ):
            print(f"  {key}: {result[key]}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    dest = OUTPUT_ROOT / "closeout_turtle_probe.json"
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
