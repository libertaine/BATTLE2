"""Run and analyze the v3 Phase 0 Ruleset-v2 control corpus.

The corpus definition itself is committed package data
(``battle_engine/data/benchmarks/v2_baseline_corpus.json``) and its
population is pinned by ``battle_engine/data/benchmarks/v2_baseline.json``,
so "rerun the Phase-0 control corpus" is reproducible from the repository
alone -- this script is only the driver.

It calls the *production* ``battle_engine.agent_evaluation`` CLI for every
roster/pair (the same tool ``bytefray agents evaluate`` invokes) and the
production ``evaluation_group_analysis`` module for every aggregate, exactly
as ``runs/research_v2_beta2_phase4/`` did. No match-execution or aggregation
logic lives here beyond table formatting, because this corpus characterizes
the production harness rather than a private reimplementation of it.

Usage, from the repo root with .venv active::

    python tools/v3_phase0_baseline_corpus.py run      --output runs/research_v3_phase0
    python tools/v3_phase0_baseline_corpus.py analyze  --output runs/research_v3_phase0

``run`` stages the frozen population into ``--output`` (which doubles as the
``BYTEFRAY_ROOT`` the evaluations discover agents from) and writes one
evaluation artifact per roster/pair under ``<output>/results/``. ``analyze``
reads those artifacts and prints the Phase-0-vs-Beta2 comparison, writing
``<output>/results/phase0_baseline.json``.

See docs/V3_PHASE0_RESEARCH_BASELINE.md for the measured results.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.benchmarks import load_population, stage_population
from battle_engine.paths import get_resource_root


def corpus_definition() -> dict:
    """Load the committed corpus definition from package resources."""

    root = get_resource_root()
    for directory in (
        root / "battle_engine" / "data" / "benchmarks",
        root / "engine" / "src" / "battle_engine" / "data" / "benchmarks",
        REPO / "engine" / "src" / "battle_engine" / "data" / "benchmarks",
    ):
        path = directory / "v2_baseline_corpus.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise SystemExit("v2_baseline_corpus.json not found in package resources")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _evaluate(args: list[str], output: Path, data_root: Path) -> float:
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "battle_engine.agent_evaluation",
            *args,
            "--output",
            str(output),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": str(REPO / "engine" / "src"),
            "BYTEFRAY_ROOT": str(data_root),
        },
    )
    elapsed = time.perf_counter() - started
    # Exit 1 means a cell failed/drifted and must be surfaced, never ignored;
    # exit 2 is a configuration error.
    if completed.returncode != 0:
        print(f"    !! exit {completed.returncode}: {completed.stderr.strip()[-400:]}")
    return elapsed


def cmd_run(output: Path, workers: str) -> int:
    results = output / "results"
    population = load_population()
    staged = stage_population(population, output)
    print(f"staged {len(staged)} files for {len(population.members)} pinned agents into {output}")

    corpus = corpus_definition()
    ruleset = corpus["ruleset_id"]
    timings: dict[str, float] = {}

    group = corpus["group"]
    seeds = ",".join(str(seed) for seed in group["seeds"])
    print(f"\n== group rosters ({len(group['rosters'])} x {group['cells_per_roster']} cells) ==")
    for entry in group["rosters"]:
        roster = entry["roster"]
        elapsed = _evaluate(
            [
                roster[0],
                "--opponents",
                ",".join(roster[1:]),
                "--ruleset",
                ruleset,
                "--group",
                "--seeds",
                seeds,
                "--ticks",
                str(group["ticks"]),
                "--workers",
                workers,
            ],
            results / "group" / entry["id"],
            output,
        )
        timings[f"group/{entry['id']}"] = elapsed
        print(f"  {entry['id']:36s} {elapsed:7.1f}s")

    pairwise = corpus["pairwise"]
    pair_seeds = ",".join(str(seed) for seed in pairwise["seeds"])
    print(f"\n== pairwise controls ({len(pairwise['pairs'])} x {pairwise['cells_per_pair']} cells) ==")
    for entry in pairwise["pairs"]:
        elapsed = _evaluate(
            [
                entry["candidate"],
                "--opponents",
                entry["opponent"],
                "--ruleset",
                ruleset,
                "--seeds",
                pair_seeds,
                "--ticks",
                str(entry["ticks"]),
                "--workers",
                workers,
            ],
            results / "pairwise" / entry["id"],
            output,
        )
        timings[f"pairwise/{entry['id']}"] = elapsed
        print(f"  {entry['id']:36s} {elapsed:7.1f}s")

    results.mkdir(parents=True, exist_ok=True)
    (results / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"\ntotal wall clock: {sum(timings.values()):.1f}s across {len(timings)} evaluations")
    return 0


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


def _load_cells(evaluation_json: Path):
    """Rebuild EvaluationCell objects from a persisted evaluation artifact.

    ``artifact_dir`` is persisted *relative* to the evaluation directory, so
    it is re-anchored here against that directory. This corpus is our own
    freshly written output, hence the direct join; code reading arbitrary
    untrusted historical artifacts must use ``evaluation_history.
    group_adapter``'s containment-checked resolution instead (see
    ``GroupCellRef``'s docstring).
    """

    from battle_engine.agent_evaluation import EvaluationCell

    base = evaluation_json.parent
    data = json.loads(evaluation_json.read_text(encoding="utf-8"))
    cells = []
    for payload in data["cells"]:
        payload = dict(payload)
        payload["artifact_dir"] = (base / Path(payload["artifact_dir"])).resolve()
        cells.append(EvaluationCell(**payload))
    return data, cells


def analyze_roster(entry: dict, results: Path) -> dict:
    from battle_engine.evaluation_group_analysis import (
        analyze_group,
        group_cell_ref_from_evaluation_cell,
    )

    data, cells = _load_cells(results / "group" / entry["id"] / "evaluation.json")
    refs = [group_cell_ref_from_evaluation_cell(cell) for cell in cells if cell.is_group]
    analysis = analyze_group(entry["roster"], refs)
    out: dict = {
        "id": entry["id"],
        "roster": entry["roster"],
        "evaluation_id": data["evaluation_id"],
        "cells_analyzed": analysis.cells_analyzed,
        "available_cells": analysis.available_cells,
        "effective_conditions": data["effective_conditions"],
        "entrants": {},
    }
    for summary in analysis.entrant_summaries:
        interval = summary.winner.interval
        out["entrants"][summary.agent_id] = {
            "win_rate": summary.winner.rate,
            "wins": summary.winner.successes,
            "trials": summary.winner.trials,
            "interval": [interval.lower, interval.upper] if interval else None,
            "survival": summary.survival.rate,
            "capture_caused": summary.capture_caused.rate,
            "capture_suffered": summary.capture_suffered.rate,
            "territory_last_pct": summary.territory_last_pct.mean,
        }
    out["seat_sensitivity"] = {s.agent_id: s.winner_rate_range for s in analysis.seat_sensitivity}
    out["layout_sensitivity"] = {
        s.agent_id: s.winner_rate_range for s in analysis.layout_sensitivity
    }
    out["seed_sensitivity"] = {s.agent_id: s.winner_rate_range for s in analysis.seed_summary}
    return out


def analyze_pair(entry: dict, results: Path) -> dict:
    data = json.loads(
        (results / "pairwise" / entry["id"] / "evaluation.json").read_text(encoding="utf-8")
    )
    cells = [c for c in data["cells"] if c.get("subject_role") == "candidate"]
    played = [c for c in cells if c.get("outcome") in ("win", "loss", "tie")]
    wins = sum(1 for c in played if c["outcome"] == "win")
    return {
        "id": entry["id"],
        "candidate": entry["candidate"],
        "opponent": entry["opponent"],
        "ticks": entry["ticks"],
        "evaluation_id": data["evaluation_id"],
        "effective_conditions": data["effective_conditions"],
        "cells": len(played),
        "wins": wins,
        "losses": sum(1 for c in played if c["outcome"] == "loss"),
        "ties": sum(1 for c in played if c["outcome"] == "tie"),
        "candidate_win_rate": wins / len(played) if played else None,
    }


def _pct(value) -> str:
    return "  --  " if value is None else f"{value * 100:5.1f}%"


def cmd_analyze(output: Path) -> int:
    results = output / "results"
    corpus = corpus_definition()
    report: dict = {"corpus_id": corpus["corpus_id"], "group": [], "pairwise": []}

    print("=" * 88)
    print("GROUP ROSTERS -- Phase 0 vs Beta2 Phase 4 win rates")
    print("=" * 88)
    for entry in corpus["group"]["rosters"]:
        result = analyze_roster(entry, results)
        report["group"].append(result)
        expected = entry.get("beta2_win_rates", {})
        print(f"\n{entry['id']}  (cells {result['cells_analyzed']}/{result['available_cells']})")
        print(f"  {'agent':26s} {'phase0':>8s} {'beta2':>8s} {'delta':>8s}  95% interval    caused")
        for agent_id, stats in result["entrants"].items():
            exp = expected.get(agent_id)
            delta = (
                f"{(stats['win_rate'] - exp) * 100:+6.1f}pp"
                if exp is not None and stats["win_rate"] is not None
                else "     --"
            )
            iv = stats["interval"]
            iv_txt = f"[{iv[0] * 100:4.1f},{iv[1] * 100:5.1f}]" if iv else "     --     "
            print(
                f"  {agent_id:26s} {_pct(stats['win_rate'])} {_pct(exp):>8s} {delta:>8s}  "
                f"{iv_txt}  {_pct(stats['capture_caused'])}"
            )

    print("\n" + "=" * 88)
    print("PAIRWISE CONTROLS -- Phase 0 vs Beta2 Phase 4 win rates")
    print("=" * 88)
    print(f"  {'pair':32s} {'cells':>5s} {'phase0':>8s} {'beta2':>8s} {'delta':>9s}")
    for entry in corpus["pairwise"]["pairs"]:
        result = analyze_pair(entry, results)
        report["pairwise"].append(result)
        exp = entry["beta2_win_rates"].get(entry["candidate"])
        delta = (
            f"{(result['candidate_win_rate'] - exp) * 100:+6.1f}pp"
            if exp is not None and result["candidate_win_rate"] is not None
            else "      --"
        )
        print(
            f"  {entry['id']:32s} {result['cells']:5d} "
            f"{_pct(result['candidate_win_rate'])} {_pct(exp):>8s} {delta:>9s}"
        )

    results.mkdir(parents=True, exist_ok=True)
    (results / "phase0_baseline.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {results / 'phase0_baseline.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="v3_phase0_baseline_corpus", description=__doc__)
    parser.add_argument("command", choices=("run", "analyze"))
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / "runs" / "research_v3_phase0",
        help="corpus working directory (also the BYTEFRAY_ROOT agents are staged into)",
    )
    parser.add_argument(
        "--workers", default="4", help="evaluation worker subprocesses per evaluation"
    )
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    if args.command == "run":
        return cmd_run(output, args.workers)
    return cmd_analyze(output)


if __name__ == "__main__":
    raise SystemExit(main())
