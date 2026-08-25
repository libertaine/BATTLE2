"""Run and analyze the v3 Phase 1 arena-size x action-budget parameter grid.

Phase 1 asks one question: *is the residual Ruleset-v2 strategic ecology
materially dependent on arena/action density, or is its structure robust
across reasonable parameter regions?* This script is the driver that
answers it; it introduces no gameplay, no new agent information and no new
engine instrumentation.

Like ``tools/v3_phase0_baseline_corpus.py``, which it deliberately mirrors,
every match is executed through the *production*
``battle_engine.agent_evaluation`` CLI and every ecology aggregate is
computed by the production ``evaluation_group_analysis`` module. The one
thing this tool reads for itself is each cell's ``result.json``
``statistics.cpu_total``/``termination_reason`` -- Phase 1F requires
*realized* action opportunity alongside the configured budget, and
``EntrantCellRecord`` does not carry ``cpu_total``. That is read here, in
research tooling, rather than by widening a production analysis record and
its persisted ``show --json`` shape for one experiment's benefit.

What varies, and what does not: the rosters, pairs, population, Ruleset,
scoring, agent sources and evaluation methodology are exactly the Phase 0
control's. Only ``--arena-size`` and ``--instr-per-tick`` change, both of
which Phase 0 established as controlled, identity-bearing, persisted
conditions. A Phase 1 cell therefore differs from its Phase 0 control cell
in those two values and in nothing else.

Usage, from the repo root with .venv active::

    python tools/v3_phase1_arena_action_grid.py run     --stage pilot --output runs/research_v3_phase1
    python tools/v3_phase1_arena_action_grid.py analyze --stage pilot --output runs/research_v3_phase1

See docs/V3_PHASE1_ARENA_ACTION_DENSITY.md for the measured results.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.benchmarks import load_population, stage_population
from battle_engine.config import Config
from battle_engine.paths import get_resource_root

GRID_FILENAME = "v3_phase1_arena_action_grid.json"
CORPUS_FILENAME = "v2_baseline_corpus.json"

# Both search agents spend exactly one action in every SCAN_EVERY on a
# READ (core_seeker/agent.py and core_tracker/agent.py both declare
# SCAN_EVERY = 3, deliberately equal so the two stay cost-comparable), so
# a condition's configured scan coverage is a third of its configured
# sweeps. Mirrored here as a derived reporting quantity only -- nothing in
# this tool changes, or depends on being able to change, either agent.
SCAN_EVERY = 3

# The corpus's two genuine search/offense agents. Hunter is deliberately
# NOT here: docs/V3_PHASE0_RESEARCH_BASELINE.md Sec 10.3 records that
# Beta2's own archetype table mislabelled it, and the shipped agent is a
# disperser with no search behaviour at all.
SEARCH_AGENTS = ("core_seeker", "core_tracker")


def _resource(filename: str) -> dict:
    """Load a committed benchmark resource, wherever the package resolves to."""

    root = get_resource_root()
    for directory in (
        root / "battle_engine" / "data" / "benchmarks",
        root / "engine" / "src" / "battle_engine" / "data" / "benchmarks",
        REPO / "engine" / "src" / "battle_engine" / "data" / "benchmarks",
    ):
        path = directory / filename
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise SystemExit(f"{filename} not found in package resources")


def grid_definition() -> dict:
    return _resource(GRID_FILENAME)


def corpus_definition() -> dict:
    return _resource(CORPUS_FILENAME)


def stage_definition(stage: str) -> dict:
    grid = grid_definition()
    try:
        return grid["stages"][stage]
    except KeyError:
        declared = ", ".join(sorted(grid["stages"]))
        raise SystemExit(
            f"stage {stage!r} is not declared in {GRID_FILENAME}; declared stages: {declared}"
        ) from None


def rosters_by_id() -> dict[str, dict]:
    return {entry["id"]: entry for entry in corpus_definition()["group"]["rosters"]}


def pairs_by_id() -> dict[str, dict]:
    return {entry["id"]: entry for entry in corpus_definition()["pairwise"]["pairs"]}


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _evaluate(args: list[str], output: Path, data_root: Path) -> tuple[float, int]:
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
    # Exit 1 means a cell failed/drifted and must be surfaced, never
    # ignored; exit 2 is a configuration error. Phase 1 deliberately probes
    # parameter values that are *expected* to be rejected (an arena too
    # small for its roster), so a non-zero exit is recorded rather than
    # fatal -- but it is always printed.
    if completed.returncode != 0:
        print(f"    [exit {completed.returncode}] {completed.stderr.strip()[-300:]}")
    return elapsed, completed.returncode


def _directory_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _run_one(
    *,
    args: list[str],
    out: Path,
    output: Path,
    record: dict[str, Any],
    records: list[dict[str, Any]],
    label: str,
) -> None:
    elapsed, code = _evaluate(args, out, output)
    size = _directory_bytes(out) if out.is_dir() else 0
    records.append({**record, "seconds": elapsed, "exit_code": code, "bytes": size})
    print(f"   {label:40s} {elapsed:7.1f}s  {size / 1e6:8.1f} MB")


def cmd_run(stage: str, output: Path, workers: str) -> int:
    definition = stage_definition(stage)
    ruleset = grid_definition()["ruleset_id"]
    results = output / stage / "results"

    population = load_population()
    staged = stage_population(population, output)
    print(f"staged {len(staged)} files for {len(population.members)} pinned agents into {output}")

    roster_defs = rosters_by_id()
    pair_defs = pairs_by_id()
    seeds = ",".join(str(seed) for seed in definition["seeds"])
    ticks = definition["ticks"]
    conditions = definition["conditions"]
    roster_ids = definition["rosters"]
    pair_ids = definition["pairs"]

    print(
        f"\n== stage {stage}: {len(conditions)} conditions x "
        f"({len(roster_ids)} rosters + {len(pair_ids)} pairs), "
        f"seeds {seeds}, {ticks} ticks =="
    )

    records: list[dict[str, Any]] = []
    for condition in conditions:
        arena = condition["arena_size"]
        budget = condition["instr_per_tick"]
        # The pilot stage labels each condition with the degeneracy it is
        # probing for; the main stage carries per-axis rationale instead.
        note = condition.get("probe") or (
            f"S={(budget * ticks) / arena:.3f}" + (" DEFAULT" if condition.get("is_default") else "")
        )
        print(f"\n-- {condition['id']}  arena {arena}  budget {budget}  ({note})")
        common = {
            "condition_id": condition["id"],
            "arena_size": arena,
            "instr_per_tick": budget,
        }
        for roster_id in roster_ids:
            roster = roster_defs[roster_id]["roster"]
            _run_one(
                args=[
                    roster[0],
                    "--opponents",
                    ",".join(roster[1:]),
                    "--ruleset",
                    ruleset,
                    "--group",
                    "--seeds",
                    seeds,
                    "--ticks",
                    str(ticks),
                    "--arena-size",
                    str(arena),
                    "--instr-per-tick",
                    str(budget),
                    "--workers",
                    workers,
                ],
                out=results / condition["id"] / "group" / roster_id,
                output=output,
                record={**common, "kind": "group", "id": roster_id, "ticks": ticks},
                records=records,
                label=f"group {roster_id}",
            )
        for pair_id in pair_ids:
            pair = pair_defs[pair_id]
            _run_one(
                args=[
                    pair["candidate"],
                    "--opponents",
                    pair["opponent"],
                    "--ruleset",
                    ruleset,
                    "--seeds",
                    seeds,
                    "--ticks",
                    str(pair["ticks"]),
                    "--arena-size",
                    str(arena),
                    "--instr-per-tick",
                    str(budget),
                    "--workers",
                    workers,
                ],
                out=results / condition["id"] / "pairwise" / pair_id,
                output=output,
                record={**common, "kind": "pairwise", "id": pair_id, "ticks": pair["ticks"]},
                records=records,
                label=f"pair {pair_id}",
            )

    results.mkdir(parents=True, exist_ok=True)
    (results / "run_records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    total_s = sum(r["seconds"] for r in records)
    total_b = sum(r["bytes"] for r in records)
    print(
        f"\ntotal wall clock: {total_s:.1f}s across {len(records)} evaluations; "
        f"artifacts {total_b / 1e9:.2f} GB"
    )
    return 0


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


def _load_cells(evaluation_json: Path) -> tuple[dict, list]:
    """Rebuild EvaluationCell objects from a persisted evaluation artifact.

    ``artifact_dir`` is persisted relative to the evaluation directory and
    re-anchored against it here, exactly as the Phase 0 corpus driver does
    (this is our own freshly written output; code reading arbitrary
    untrusted historical artifacts must use ``evaluation_history.
    group_adapter``'s containment-checked resolution instead).
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


def _mean(values: list[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


def _match_shape(cells: list) -> dict[str, Any]:
    """Realized match shape for one evaluation, read straight from result.json.

    Phase 1F's "realized action opportunity": a match can terminate before
    its tick limit, so the configured ``instr_per_tick x ticks`` product is
    only an upper bound on what an entrant actually got to do.
    ``cpu_total`` is the measured figure, and it is already recorded per
    entrant in every result -- no new instrumentation is needed or added.
    """

    ticks: list[int] = []
    cpu_by_agent: dict[str, list[int]] = defaultdict(list)
    writes_by_agent: dict[str, list[int]] = defaultdict(list)
    territory_by_agent: dict[str, list[float]] = defaultdict(list)
    saturation: list[float] = []
    terminations: dict[str, int] = defaultdict(int)
    entrant_terminations: dict[str, int] = defaultdict(int)
    replay_bytes: list[int] = []
    read = 0

    for cell in cells:
        result_path = Path(cell.artifact_dir) / "result.json"
        if not result_path.is_file():
            continue
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        read += 1
        ticks.append(int(payload.get("ticks") or 0))
        terminations[str(payload.get("termination_reason"))] += 1
        claimed = 0.0
        for entrant in payload.get("entrants", []):
            name = entrant.get("name") or entrant.get("agent_id")
            stats = entrant.get("statistics") or {}
            cpu_by_agent[name].append(int(stats.get("cpu_total") or 0))
            writes_by_agent[name].append(int(stats.get("mem_writes") or 0))
            pct = float(stats.get("territory_pct_last") or 0.0)
            territory_by_agent[name].append(pct)
            claimed += pct
            entrant_terminations[str(entrant.get("termination_reason"))] += 1
        saturation.append(claimed)
        replay = Path(cell.artifact_dir) / "replay.jsonl"
        if replay.is_file():
            replay_bytes.append(replay.stat().st_size)

    return {
        "cells_read": read,
        "ticks_mean": _mean([float(t) for t in ticks]),
        "ticks_min": min(ticks) if ticks else None,
        "ticks_max": max(ticks) if ticks else None,
        "saturation_mean_pct": _mean(saturation),
        "saturation_min_pct": min(saturation) if saturation else None,
        "saturation_max_pct": max(saturation) if saturation else None,
        "cpu_total_mean_by_agent": {
            a: _mean([float(v) for v in vs]) for a, vs in cpu_by_agent.items()
        },
        "mem_writes_mean_by_agent": {
            a: _mean([float(v) for v in vs]) for a, vs in writes_by_agent.items()
        },
        "territory_last_pct_mean_by_agent": {a: _mean(vs) for a, vs in territory_by_agent.items()},
        "termination_reasons": dict(terminations),
        "entrant_termination_reasons": dict(entrant_terminations),
        "replay_bytes_mean": _mean([float(b) for b in replay_bytes]),
        "replay_bytes_max": max(replay_bytes) if replay_bytes else None,
    }


def analyze_roster(
    roster_id: str, roster: list[str], condition: dict, results: Path
) -> dict[str, Any] | None:
    from battle_engine.evaluation_group_analysis import (
        analyze_group,
        group_cell_ref_from_evaluation_cell,
    )

    evaluation_json = results / condition["id"] / "group" / roster_id / "evaluation.json"
    if not evaluation_json.is_file():
        return None
    data, cells = _load_cells(evaluation_json)
    refs = [group_cell_ref_from_evaluation_cell(cell) for cell in cells if cell.is_group]
    analysis = analyze_group(roster, refs)

    entrants: dict[str, Any] = {}
    for summary in analysis.entrant_summaries:
        interval = summary.winner.interval
        entrants[summary.agent_id] = {
            "win_rate": summary.winner.rate,
            "wins": summary.winner.successes,
            "trials": summary.winner.trials,
            "interval": [interval.lower, interval.upper] if interval else None,
            "survival": summary.survival.rate,
            "elimination": summary.elimination.rate,
            "capture_caused": summary.capture_caused.rate,
            "capture_suffered": summary.capture_suffered.rate,
            "territory_last_pct": summary.territory_last_pct.mean,
            "territory_max_pct": summary.territory_max_pct.mean,
            "territory_retention": summary.territory_retention.mean,
            "score_mean": summary.score.mean,
        }

    # Ties are real and common in this corpus, so the ordering is by win
    # rate with the agent id as a deterministic tiebreak; `leader_tied_with`
    # records who else shares the top rate so a "leader" is never silently
    # asserted over an exact tie (Beta2 Sec 17 criterion 1 counts ties as
    # leads, and Phase 0 Sec 10.1 shows what reading a tie carelessly costs).
    ordering = sorted(entrants, key=lambda a: (-(entrants[a]["win_rate"] or 0.0), a))
    leader = ordering[0] if ordering else None
    leader_rate = entrants[leader]["win_rate"] if leader else None
    tied = [a for a in ordering if a != leader and entrants[a]["win_rate"] == leader_rate]

    arena = condition["arena_size"]
    budget = condition["instr_per_tick"]
    shape = _match_shape(cells)
    configured_sweeps = (budget * data["ticks"]) / arena
    realized = shape["cpu_total_mean_by_agent"]
    realized_total = sum(v or 0.0 for v in realized.values())

    return {
        "condition_id": condition["id"],
        "roster_id": roster_id,
        "roster": roster,
        "arena_size": arena,
        "instr_per_tick": budget,
        "ticks": data["ticks"],
        "evaluation_id": data["evaluation_id"],
        "effective_conditions": data["effective_conditions"],
        "cells_analyzed": analysis.cells_analyzed,
        "available_cells": analysis.available_cells,
        "entrants": entrants,
        "ordering": ordering,
        "leader": leader,
        "leader_win_rate": leader_rate,
        "leader_tied_with": tied,
        "seat_sensitivity": {s.agent_id: s.winner_rate_range for s in analysis.seat_sensitivity},
        "layout_sensitivity": {
            s.agent_id: s.winner_rate_range for s in analysis.layout_sensitivity
        },
        "seed_sensitivity": {s.agent_id: s.winner_rate_range for s in analysis.seed_summary},
        "interaction_matrix": analysis.interaction_matrix.to_json(),
        "match_shape": shape,
        "density": {
            "configured_sweeps_per_entrant": configured_sweeps,
            "configured_aggregate_pressure": len(roster) * configured_sweeps,
            "configured_scan_coverage": configured_sweeps / SCAN_EVERY,
            "realized_actions_per_cell_by_agent": {
                a: (v / arena if v is not None else None) for a, v in realized.items()
            },
            "realized_aggregate_actions_per_cell": realized_total / arena,
        },
    }


def analyze_pair(pair_id: str, pair: dict, condition: dict, results: Path) -> dict[str, Any] | None:
    evaluation_json = results / condition["id"] / "pairwise" / pair_id / "evaluation.json"
    if not evaluation_json.is_file():
        return None
    data, cells = _load_cells(evaluation_json)
    scored = [c for c in data["cells"] if c.get("subject_role") == "candidate"]
    played = [c for c in scored if c.get("outcome") in ("win", "loss", "tie")]
    wins = sum(1 for c in played if c["outcome"] == "win")
    arena = condition["arena_size"]
    return {
        "condition_id": condition["id"],
        "pair_id": pair_id,
        "candidate": pair["candidate"],
        "opponent": pair["opponent"],
        "arena_size": arena,
        "instr_per_tick": condition["instr_per_tick"],
        "ticks": data["ticks"],
        "evaluation_id": data["evaluation_id"],
        "cells": len(played),
        "wins": wins,
        "losses": sum(1 for c in played if c["outcome"] == "loss"),
        "ties": sum(1 for c in played if c["outcome"] == "tie"),
        "candidate_win_rate": (wins / len(played)) if played else None,
        "configured_sweeps_per_entrant": (condition["instr_per_tick"] * data["ticks"]) / arena,
        "match_shape": _match_shape(cells),
    }


# Descriptive screening flags for Phase 1D/1O-C. Each names a way a
# parameter region can look different without being strategically
# meaningful; they are reported, never treated as a verdict on their own.
DEGENERACY_RULES: dict[str, str] = {
    "evaluation_rejected": "the evaluation produced no artifact (configuration refused)",
    "no_scored_cells": "an artifact exists but no cell produced a usable result",
    "saturation_ceiling": "mean final arena occupancy >= 99%: every strategy fills the arena",
    "interaction_starved": (
        "a roster that contains a dedicated search agent still produced no core capture "
        "in any cell -- entrants coexisted without ever contesting a core. A roster with "
        "no search agent is not flagged: zero captures there is the design, not a defect."
    ),
    "collision_regime": "captures occur and the mean match ends within a tenth of the tick budget",
    "budget_starved": "mean final arena occupancy < 5%: almost nothing was claimed at all",
    "undecided": (
        "over half the cells produced no winner at all -- with territory scored in whole "
        "64-cell buckets, a small arena offers so few buckets that surviving entrants tie "
        "exactly and `resolve_winner` declines to pick one"
    ),
}


def _degeneracy_flags(entry: dict[str, Any]) -> list[str]:
    shape = entry["match_shape"]
    if entry["cells_analyzed"] == 0 or shape["cells_read"] == 0:
        return ["no_scored_cells"]
    flags: list[str] = []
    saturation = shape["saturation_mean_pct"]
    captured = shape["entrant_termination_reasons"].get("core_captured", 0)
    ticks_mean = shape["ticks_mean"]
    if saturation is not None and saturation >= 99.0:
        flags.append("saturation_ceiling")
    if captured == 0 and any(agent in SEARCH_AGENTS for agent in entry["roster"]):
        flags.append("interaction_starved")
    if captured > 0 and ticks_mean is not None and ticks_mean <= entry["ticks"] / 10.0:
        flags.append("collision_regime")
    if saturation is not None and saturation < 5.0:
        flags.append("budget_starved")
    # Every cell has at most one winner, so the wins summed over entrants
    # is exactly the number of decided cells.
    decided = sum(stats["wins"] for stats in entry["entrants"].values())
    if entry["cells_analyzed"] and decided < entry["cells_analyzed"] / 2:
        flags.append("undecided")
    return flags


def _pct(value: float | None, width: int = 6) -> str:
    return f"{'--':>{width}}" if value is None else f"{value * 100:{width}.1f}%"


# ---------------------------------------------------------------------------
# validate (Phase 1T)
# ---------------------------------------------------------------------------


def _cell_fingerprint(evaluation_json: Path) -> tuple[str, list[tuple[Any, ...]]]:
    """An evaluation's identity plus every cell's own executed identity.

    Two runs that agree here agree on what was executed and what happened,
    not merely on how it was summarized.
    """

    data = json.loads(evaluation_json.read_text(encoding="utf-8"))
    cells = sorted(
        (
            cell["schedule_id"],
            cell.get("match_id"),
            cell.get("result_id"),
            cell.get("outcome"),
            cell.get("score_subject"),
            cell.get("score_opponent"),
            cell.get("layout_id"),
            cell.get("seed"),
        )
        for cell in data["cells"]
    )
    return data["evaluation_id"], cells


def _control_anchor_check(stage: str, output: Path, control: Path) -> tuple[bool, str]:
    """Is the grid's default condition literally the Phase 0 control?

    The grid runs three seeds where the Phase 0 control corpus runs five,
    so the two evaluations legitimately carry different ``evaluation_id``s
    -- the seed set is identity-bearing. What must hold is stronger and
    more specific: every default-condition cell the grid *did* run must be
    the same executed match as the control's corresponding cell, down to
    ``match_id``, outcome and both scores. If that holds, the seed
    reduction is a strict subset of the control rather than a different
    experiment, and every non-default condition is being compared against
    the real published baseline.
    """

    definition = stage_definition(stage)
    results = output / stage / "results"
    default = next((c for c in definition["conditions"] if c.get("is_default")), None)
    if default is None:
        return False, "the grid declares no default condition to anchor against"

    def _cells(path: Path) -> dict[tuple[Any, ...], tuple[Any, ...]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            (cell["seed"], cell["layout_id"], tuple(cell["seat_agent_ids"])): (
                cell.get("match_id"),
                cell.get("outcome"),
                cell.get("score_subject"),
                cell.get("score_opponent"),
            )
            for cell in data["cells"]
        }

    compared = identical = 0
    missing: list[str] = []
    for roster_id in definition["rosters"]:
        here = results / default["id"] / "group" / roster_id / "evaluation.json"
        there = control / "results" / "group" / roster_id / "evaluation.json"
        if not here.is_file() or not there.is_file():
            missing.append(roster_id)
            continue
        grid_cells = _cells(here)
        control_cells = _cells(there)
        shared = set(grid_cells) & set(control_cells)
        if len(shared) != len(grid_cells):
            missing.append(f"{roster_id} (grid cell absent from control)")
        compared += len(shared)
        identical += sum(1 for key in shared if grid_cells[key] == control_cells[key])
    if missing:
        return False, f"could not compare: {', '.join(missing)}"
    return identical == compared and compared > 0, (
        f"{identical}/{compared} default-condition cells identical to the Phase 0 control corpus"
    )


def cmd_validate(stage: str, output: Path, workers: str, control: Path | None) -> int:
    """Phase 1T: re-verify the identity guarantees Phase 0 established, at
    a real Phase 1 grid condition rather than at a synthetic one."""

    from battle_engine.agent_evaluation import BYTEFRAY_RULESET_V2_ID, EvaluationService

    definition = stage_definition(stage)
    ruleset = grid_definition()["ruleset_id"]
    root = output / f"{stage}_validation"
    roster_defs = rosters_by_id()
    population = load_population()
    stage_population(population, output)

    # The most extreme condition in the grid that is still non-degenerate:
    # if identity, determinism and worker-independence hold at 16x default
    # arena and 16x default budget, they hold everywhere milder.
    condition = next(
        (c for c in definition["conditions"] if c["id"] == "a65536_b128"),
        definition["conditions"][-1],
    )
    roster_id = definition["rosters"][3]
    roster = roster_defs[roster_id]["roster"]
    seeds = ",".join(str(s) for s in definition["seeds"][:2])
    print(
        f"validating at {condition['id']} (arena {condition['arena_size']}, "
        f"budget {condition['instr_per_tick']}) with roster {roster_id}, seeds {seeds}"
    )

    def _run(name: str, worker_count: str) -> Path:
        out = root / name
        _evaluate(
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
                str(definition["ticks"]),
                "--arena-size",
                str(condition["arena_size"]),
                "--instr-per-tick",
                str(condition["instr_per_tick"]),
                "--workers",
                worker_count,
            ],
            out,
            output,
        )
        return out / "evaluation.json"

    checks: list[tuple[str, bool, str]] = []

    first = _cell_fingerprint(_run("repeat_a", workers))
    second = _cell_fingerprint(_run("repeat_b", workers))
    checks.append(
        (
            "repeated identical conditions reproduce deterministically",
            first == second,
            f"evaluation_id {first[0][:24]}..., {len(first[1])} cells compared",
        )
    )

    serial = _cell_fingerprint(_run("serial", "1"))
    checks.append(
        (
            "serial and parallel execution agree",
            serial == first,
            f"--workers 1 versus --workers {workers}",
        )
    )

    # Resume: rerun into an already-complete directory. Every cell resolves
    # from persisted state and must verify against a rebuilt Config, which
    # is exactly where a non-default arena/budget would go wrong if the
    # resume path did not carry them (Phase 0 Sec 4).
    resumed = _cell_fingerprint(_run("repeat_a", workers))
    checks.append(
        (
            "resume over a completed non-default evaluation changes nothing",
            resumed == first,
            "re-ran into the existing repeat_a directory",
        )
    )

    service = EvaluationService()
    common = {
        "candidate_id": roster[0],
        "opponent_ids": tuple(roster[1:]),
        "seeds": tuple(definition["seeds"][:2]),
        "ticks": definition["ticks"],
        "data_root": output,
        "ruleset_id": BYTEFRAY_RULESET_V2_ID,
        "group": True,
    }
    _, omitted_id = service.preflight(**common)
    _, explicit_id = service.preflight(
        **common, arena_size=Config().arena_size, instr_per_tick=Config().instr_per_tick
    )
    checks.append(
        (
            "explicit defaults are identical to omitting the parameters",
            omitted_id == explicit_id,
            f"both resolve to {omitted_id[:24]}...",
        )
    )

    identities: dict[str, str] = {}
    for entry in definition["conditions"]:
        _, evaluation_id = service.preflight(
            **common,
            arena_size=entry["arena_size"],
            instr_per_tick=entry["instr_per_tick"],
        )
        identities[entry["id"]] = evaluation_id
    checks.append(
        (
            "every grid condition has a distinct evaluation identity",
            len(set(identities.values())) == len(identities),
            f"{len(identities)} conditions, {len(set(identities.values()))} distinct ids",
        )
    )
    checks.append(
        (
            "the default grid condition matches the omitted-parameter identity",
            identities.get("a4096_b8") == omitted_id,
            "the Phase 0 control anchor is not a separate methodology",
        )
    )

    if control is not None:
        passed, detail = _control_anchor_check(stage, output, control)
        checks.append(
            ("the grid's default condition reproduces the Phase 0 control corpus", passed, detail)
        )

    print()
    ok = True
    for label, passed, detail in checks:
        ok = ok and passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}\n         {detail}")

    (root / "validation.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "validation.json").write_text(
        json.dumps(
            {
                "condition": condition,
                "roster_id": roster_id,
                "seeds": definition["seeds"][:2],
                "checks": [
                    {"check": label, "passed": passed, "detail": detail}
                    for label, passed, detail in checks
                ],
                "condition_evaluation_ids": identities,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {root / 'validation.json'}")
    return 0 if ok else 1


def cmd_analyze(stage: str, output: Path) -> int:
    definition = stage_definition(stage)
    results = output / stage / "results"
    roster_defs = rosters_by_id()
    pair_defs = pairs_by_id()

    report: dict[str, Any] = {
        "grid_id": grid_definition()["grid_id"],
        "stage": stage,
        "ticks": definition["ticks"],
        "seeds": definition["seeds"],
        "degeneracy_rules": DEGENERACY_RULES,
        "group": [],
        "pairwise": [],
    }

    for condition in definition["conditions"]:
        for roster_id in definition["rosters"]:
            entry = analyze_roster(roster_id, roster_defs[roster_id]["roster"], condition, results)
            if entry is None:
                report["group"].append(
                    {
                        "condition_id": condition["id"],
                        "roster_id": roster_id,
                        "arena_size": condition["arena_size"],
                        "instr_per_tick": condition["instr_per_tick"],
                        "degeneracy_flags": ["evaluation_rejected"],
                    }
                )
                continue
            entry["degeneracy_flags"] = _degeneracy_flags(entry)
            report["group"].append(entry)
        for pair_id in definition["pairs"]:
            pair_entry = analyze_pair(pair_id, pair_defs[pair_id], condition, results)
            if pair_entry is not None:
                report["pairwise"].append(pair_entry)

    _print_group_table(report)
    if report["pairwise"]:
        _print_pairwise_table(report)

    results.mkdir(parents=True, exist_ok=True)
    destination = results / f"phase1_{stage}_analysis.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {destination}")
    return 0


def _print_group_table(report: dict[str, Any]) -> None:
    print("=" * 124)
    print(f"PHASE 1 {report['stage'].upper()} -- group rosters by arena x action budget")
    print("=" * 124)
    print(
        f"{'condition':>14s} {'roster':>32s} {'S':>7s} {'P':>7s} {'sat%':>6s} "
        f"{'ticks':>6s} {'cap':>4s} {'leader':>22s} {'win':>7s}  flags"
    )
    for entry in report["group"]:
        if "match_shape" not in entry:
            print(
                f"{entry['condition_id']:>14s} {entry['roster_id']:>32s}   "
                f"{','.join(entry['degeneracy_flags'])}"
            )
            continue
        shape = entry["match_shape"]
        density = entry["density"]
        captured = shape["entrant_termination_reasons"].get("core_captured", 0)
        leader = str(entry["leader"])
        if entry["leader_tied_with"]:
            leader = f"{leader}(tie)"
        print(
            f"{entry['condition_id']:>14s} {entry['roster_id']:>32s} "
            f"{density['configured_sweeps_per_entrant']:7.3f} "
            f"{density['configured_aggregate_pressure']:7.2f} "
            f"{(shape['saturation_mean_pct'] or 0.0):6.1f} "
            f"{(shape['ticks_mean'] or 0.0):6.0f} "
            f"{captured:4d} {leader:>22s} {_pct(entry['leader_win_rate'])}  "
            f"{','.join(entry['degeneracy_flags']) or '-'}"
        )
    print("\nS = configured sweeps per entrant = (instr_per_tick x ticks) / arena_size")
    print("P = configured aggregate pressure  = entrants x S")
    print("sat% = mean summed final territory across all seats; cap = entrant core-captures")


def _print_pairwise_table(report: dict[str, Any]) -> None:
    print("\n" + "=" * 108)
    print(f"PHASE 1 {report['stage'].upper()} -- pairwise controls")
    print("=" * 108)
    for entry in report["pairwise"]:
        shape = entry["match_shape"]
        print(
            f"{entry['condition_id']:>14s} {entry['pair_id']:>32s} "
            f"S {entry['configured_sweeps_per_entrant']:7.3f}  cells {entry['cells']:3d}  "
            f"candidate {_pct(entry['candidate_win_rate'])}  "
            f"ticks {(shape['ticks_mean'] or 0.0):5.0f}  "
            f"sat {(shape['saturation_mean_pct'] or 0.0):5.1f}%"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="v3_phase1_arena_action_grid", description=__doc__)
    parser.add_argument("command", choices=("run", "analyze", "validate"))
    parser.add_argument(
        "--stage", default="pilot", help="grid stage declared in the grid definition"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / "runs" / "research_v3_phase1",
        help="working directory (also the BYTEFRAY_ROOT agents are staged into)",
    )
    parser.add_argument("--workers", default="4", help="evaluation worker subprocesses")
    parser.add_argument(
        "--control",
        type=Path,
        default=None,
        help=(
            "validate only: a directory produced by tools/v3_phase0_baseline_corpus.py, "
            "against which the grid's default condition is compared cell for cell"
        ),
    )
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    if args.command == "run":
        return cmd_run(args.stage, output, args.workers)
    if args.command == "validate":
        control = args.control.expanduser().resolve() if args.control else None
        return cmd_validate(args.stage, output, args.workers, control)
    return cmd_analyze(args.stage, output)


if __name__ == "__main__":
    raise SystemExit(main())
