"""Run and analyze the v3 Phase 2 bounded-locality corpus.

Phase 2 asks one question: *does bounded locality make two strategic axes
viable at the same time, across a wider density band than Ruleset-v2
parameter tuning can produce?* This script is the driver that answers it.

Three deliberate continuities with Phase 1, each of which exists to make
the comparison a measurement rather than an assertion:

1. **The same reduction code.** Every ecology aggregate is computed by
   ``v3_phase1_arena_action_grid``'s own ``analyze_roster``/``analyze_pair``,
   imported here rather than reimplemented, with only its role constants
   rebound to the locality population (see :func:`_phase1_roles`). The
   Ruleset-v2 control arm and the locality arm are therefore reduced by
   literally the same lines.
2. **The same production harness.** Matches execute through
   ``battle_engine.agent_evaluation.EvaluationService`` and aggregates come
   from the production ``evaluation_group_analysis`` module. Unlike Phase 1,
   which shelled out to the ``agents evaluate`` CLI, this driver builds its
   ``EvaluationRequest`` directly: the experimental Ruleset is deliberately
   absent from every product CLI's ``--ruleset`` choices, and putting it
   back to save a subprocess would advertise an unstable identity in a
   shipped command.
3. **The Ruleset-v2 arm is not re-executed.** Phase 1 already measured the
   six matched conditions with the frozen v2 population; its committed
   artifacts under ``runs/research_v3_phase1`` are read as-is (Phase 2L
   Control 1).

What this tool adds that Phase 1 had no need for: the per-entrant locality
telemetry the engine now records in each ``result.json``'s
``entrants[].metadata.locality`` (movement, distinct loci, distance from
own core, encounter frequency, reach misses), and per-layout win rates,
which Phase 2J's translation/placement check needs and which Phase 1's
reduction keeps only as a range.

Usage, from the repo root with .venv active::

    python tools/v3_phase2_locality_corpus.py run     --stage pilot --output runs/research_v3_phase2
    python tools/v3_phase2_locality_corpus.py analyze --stage pilot --output runs/research_v3_phase2

See docs/V3_PHASE2_LOCALITY_FEASIBILITY.md for the measured results.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import v3_phase1_arena_action_grid as phase1
from battle_engine.benchmarks import load_population, stage_population
from battle_engine.paths import get_resource_root

CORPUS_FILENAME = "v3_phase2_locality_corpus.json"
POPULATION_ID = "v3-phase2-locality"


def _resource(filename: str) -> dict:
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


def corpus_definition() -> dict:
    return _resource(CORPUS_FILENAME)


def stage_definition(stage: str) -> dict:
    corpus = corpus_definition()
    try:
        return corpus["stages"][stage]
    except KeyError:
        declared = ", ".join(sorted(corpus["stages"]))
        raise SystemExit(
            f"stage {stage!r} is not declared in {CORPUS_FILENAME}; declared: {declared}"
        ) from None


def rosters_by_id() -> dict[str, dict]:
    return {entry["id"]: entry for entry in corpus_definition()["rosters"]}


def pairs_by_id() -> dict[str, dict]:
    return {entry["id"]: entry for entry in corpus_definition()["pairs"]}


@contextlib.contextmanager
def _phase1_roles() -> Iterator[None]:
    """Rebind the Phase 1 reduction's role constants to this population.

    ``v3_phase1_arena_action_grid`` names its search agents at module scope
    (they feed the ``interaction_starved`` degeneracy flag). Rebinding them
    for the duration of a Phase 2 reduction is deliberate: it is what lets
    both arms be reduced by the identical code path instead of by a
    reimplementation that could quietly diverge. Restored on exit so a
    Ruleset-v2 reduction in the same process is unaffected.
    """

    roles = corpus_definition()["roles"]
    previous = phase1.SEARCH_AGENTS
    phase1.SEARCH_AGENTS = tuple(roles["search"])
    try:
        yield
    finally:
        phase1.SEARCH_AGENTS = previous


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _evaluate(
    *,
    candidate: str,
    opponents: list[str],
    group: bool,
    seeds: list[int],
    ticks: int,
    arena_size: int,
    instr_per_tick: int,
    locality_reach: int,
    out: Path,
    data_root: Path,
    workers: int,
) -> tuple[float, int]:
    """Execute one evaluation in-process through the production service."""

    from battle_engine.agent_evaluation import (
        EvaluationConfigurationError,
        EvaluationRequest,
        EvaluationService,
    )
    from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V3_ALPHA1_ID

    out.parent.mkdir(parents=True, exist_ok=True)
    request = EvaluationRequest(
        candidate_id=candidate,
        opponent_ids=tuple(opponents),
        seeds=tuple(seeds),
        output_dir=out,
        ticks=ticks,
        data_root=data_root,
        workers=workers,
        ruleset_id=BYTEFRAY_RULESET_V3_ALPHA1_ID,
        group=group,
        arena_size=arena_size,
        instr_per_tick=instr_per_tick,
        locality_reach=locality_reach,
    )
    started = time.perf_counter()
    try:
        result = EvaluationService().run(request)
    except EvaluationConfigurationError as exc:
        # Phase 2 deliberately probes reaches and arenas that are *expected*
        # to be rejected, so a refusal is recorded rather than fatal -- but
        # it is always printed.
        print(f"    [rejected] {exc}")
        return time.perf_counter() - started, 2
    elapsed = time.perf_counter() - started
    bad = len(result.failed_cells) + len(result.corrupted_cells) + len(result.drift_cells)
    if bad:
        print(f"    [exit 1] {bad} failed/corrupted/drifted cells")
    return elapsed, (1 if bad else 0)


def cmd_run(stage: str, output: Path, workers: int) -> int:
    definition = stage_definition(stage)
    results = output / stage / "results"

    population = load_population(POPULATION_ID)
    staged = stage_population(population, output)
    print(
        f"staged {len(staged)} files for {len(population.members)} pinned agents "
        f"into {output}"
    )

    roster_defs = rosters_by_id()
    pair_defs = pairs_by_id()
    seeds = list(definition["seeds"])
    ticks = definition["ticks"]
    conditions = list(definition["conditions"])
    roster_ids = list(definition["rosters"])
    pair_ids = list(definition["pairs"])

    reach_star = _resolve_reach_star(stage, output)
    print(
        f"\n== stage {stage}: {len(conditions)} conditions x "
        f"({len(roster_ids)} rosters + {len(pair_ids)} pairs), "
        f"seeds {seeds}, {ticks} ticks =="
    )
    if reach_star is not None:
        print(f"   R* = {reach_star} (from the pilot's promotion rule)")

    records: list[dict[str, Any]] = []
    for condition in conditions:
        arena = condition["arena_size"]
        budget = condition["instr_per_tick"]
        reach = condition["locality_reach"]
        if reach == "R*":
            if reach_star is None:
                raise SystemExit(
                    "condition names R* but no pilot promotion is recorded; run the "
                    "pilot stage and its analyze step first"
                )
            reach = reach_star
        note = condition.get("probe") or condition.get("rationale") or ""
        density = (budget * ticks) / arena
        print(
            f"\n-- {condition['id']}  arena {arena}  budget {budget}  R {reach}  "
            f"(S={density:.3f})  {note[:70]}"
        )
        common = {
            "condition_id": condition["id"],
            "arm": condition.get("arm", "pilot"),
            "arena_size": arena,
            "instr_per_tick": budget,
            "locality_reach": reach,
        }
        for roster_id in roster_ids:
            roster = roster_defs[roster_id]["roster"]
            out = results / condition["id"] / "group" / roster_id
            elapsed, code = _evaluate(
                candidate=roster[0],
                opponents=roster[1:],
                group=True,
                seeds=seeds,
                ticks=ticks,
                arena_size=arena,
                instr_per_tick=budget,
                locality_reach=reach,
                out=out,
                data_root=output,
                workers=workers,
            )
            size = phase1._directory_bytes(out) if out.is_dir() else 0
            records.append(
                {**common, "kind": "group", "id": roster_id, "ticks": ticks,
                 "seconds": elapsed, "exit_code": code, "bytes": size}
            )
            print(f"   {'group ' + roster_id:44s} {elapsed:7.1f}s  {size / 1e6:8.1f} MB")
        for pair_id in pair_ids:
            pair = pair_defs[pair_id]
            out = results / condition["id"] / "pairwise" / pair_id
            elapsed, code = _evaluate(
                candidate=pair["candidate"],
                opponents=[pair["opponent"]],
                group=False,
                seeds=seeds,
                ticks=pair["ticks"],
                arena_size=arena,
                instr_per_tick=budget,
                locality_reach=reach,
                out=out,
                data_root=output,
                workers=workers,
            )
            size = phase1._directory_bytes(out) if out.is_dir() else 0
            records.append(
                {**common, "kind": "pairwise", "id": pair_id, "ticks": pair["ticks"],
                 "seconds": elapsed, "exit_code": code, "bytes": size}
            )
            print(f"   {'pair ' + pair_id:44s} {elapsed:7.1f}s  {size / 1e6:8.1f} MB")

    results.mkdir(parents=True, exist_ok=True)
    (results / "run_records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    total_s = sum(r["seconds"] for r in records)
    total_b = sum(r["bytes"] for r in records)
    print(
        f"\ntotal wall clock: {total_s:.1f}s across {len(records)} evaluations; "
        f"artifacts {total_b / 1e9:.2f} GB"
    )
    return 0


def _resolve_reach_star(stage: str, output: Path) -> int | None:
    if stage != "main":
        return None
    path = output / "pilot" / "results" / "phase2_pilot_promotion.json"
    if not path.is_file():
        return None
    return int(json.loads(path.read_text(encoding="utf-8"))["reach_star"])


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


def _locality_profile(cells: list) -> dict[str, Any]:
    """Aggregate the engine's per-entrant locality telemetry over one evaluation.

    Read straight from each cell's ``result.json``
    ``entrants[].metadata.locality`` -- the deterministic, additive block the
    locality runtime records. Nothing here recomputes a match.
    """

    by_agent: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    action_mix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    read = 0
    for cell in cells:
        result_path = Path(cell.artifact_dir) / "result.json"
        if not result_path.is_file():
            continue
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        read += 1
        for entrant in payload.get("entrants", []):
            name = entrant.get("name") or entrant.get("agent_id")
            locality = (entrant.get("metadata") or {}).get("locality")
            if not locality:
                continue
            stats = entrant.get("statistics") or {}
            cpu = int(stats.get("cpu_total") or 0)
            for key, value in locality.items():
                by_agent[name][key].append(float(value))
            by_agent[name]["cpu_total"].append(float(cpu))
            # Action-mix shares, from counters the engine already keeps. The
            # residual is every non-arena action (NOP/registers/jumps) plus
            # reach misses; the corpus agents emit none of the former, so it
            # is effectively the reach-miss share and is reported as such.
            action_mix[name]["moves"] += int(locality["moves"])
            action_mix[name]["local_reads"] += int(locality["local_reads"])
            action_mix[name]["local_writes"] += int(locality["local_writes"])
            action_mix[name]["reach_misses"] += int(locality["reach_misses"])
            action_mix[name]["cpu_total"] += cpu

    profile: dict[str, Any] = {"cells_read": read, "by_agent": {}}
    for name, series in by_agent.items():
        totals = action_mix[name]
        cpu = totals["cpu_total"] or 1
        profile["by_agent"][name] = {
            **{key: phase1._mean(values) for key, values in series.items()},
            "move_share": totals["moves"] / cpu,
            "local_read_share": totals["local_reads"] / cpu,
            "local_write_share": totals["local_writes"] / cpu,
            "reach_miss_share": totals["reach_misses"] / cpu,
        }
    return profile


def _layout_win_rates(roster: list[str], cells: list) -> dict[str, dict[str, float | None]]:
    """Per-layout win rate for every roster member (Phase 2J).

    ``spread`` and ``spread-shifted`` are the *same* relative geometry --
    identical seat gaps, phase-shifted by half a gap -- so the difference
    between them is a pure translation. ``close`` is a different geometry
    and is reported alongside but never folded into the translation
    measure. Phase 1's reduction keeps only the range across all three,
    which cannot separate translation from geometry.
    """

    from battle_engine.evaluation_group_analysis import (
        analyze_group,
        group_cell_ref_from_evaluation_cell,
    )

    refs = [group_cell_ref_from_evaluation_cell(cell) for cell in cells if cell.is_group]
    if not refs:
        return {}
    analysis = analyze_group(roster, refs)
    rates: dict[str, dict[str, float | None]] = {}
    for view in analysis.layout_sensitivity:
        rates[view.agent_id] = {
            summary.label: summary.winner.rate for summary in view.by_layout
        }
    return rates


def analyze_condition_roster(
    roster_id: str, roster: list[str], condition: dict, results: Path, ticks: int
) -> dict[str, Any] | None:
    evaluation_json = results / condition["id"] / "group" / roster_id / "evaluation.json"
    if not evaluation_json.is_file():
        return None
    with _phase1_roles():
        entry = phase1.analyze_roster(roster_id, roster, condition, results)
    if entry is None:
        return None
    _data, cells = phase1._load_cells(evaluation_json)
    entry["arm"] = condition.get("arm", "pilot")
    entry["locality_reach"] = condition["locality_reach"]
    entry["locality"] = _locality_profile(cells)
    entry["layout_win_rates"] = _layout_win_rates(roster, cells)
    return entry


def analyze_condition_pair(
    pair_id: str, pair: dict, condition: dict, results: Path
) -> dict[str, Any] | None:
    evaluation_json = results / condition["id"] / "pairwise" / pair_id / "evaluation.json"
    if not evaluation_json.is_file():
        return None
    with _phase1_roles():
        entry = phase1.analyze_pair(pair_id, pair, condition, results)
    if entry is None:
        return None
    _data, cells = phase1._load_cells(evaluation_json)
    entry["arm"] = condition.get("arm", "pilot")
    entry["locality_reach"] = condition["locality_reach"]
    entry["locality"] = _locality_profile(cells)
    return entry


def cmd_analyze(stage: str, output: Path) -> int:
    definition = stage_definition(stage)
    results = output / stage / "results"
    roster_defs = rosters_by_id()
    pair_defs = pairs_by_id()
    ticks = definition["ticks"]
    reach_star = _resolve_reach_star(stage, output)

    group_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    for condition in definition["conditions"]:
        resolved = dict(condition)
        if resolved["locality_reach"] == "R*":
            if reach_star is None:
                continue
            resolved["locality_reach"] = reach_star
        for roster_id in definition["rosters"]:
            entry = analyze_condition_roster(
                roster_id, roster_defs[roster_id]["roster"], resolved, results, ticks
            )
            if entry is not None:
                group_rows.append(entry)
        for pair_id in definition["pairs"]:
            entry = analyze_condition_pair(
                pair_id, pair_defs[pair_id], resolved, results
            )
            if entry is not None:
                pair_rows.append(entry)

    with _phase1_roles():
        for row in group_rows:
            row["degeneracy_flags"] = phase1._degeneracy_flags(row)

    analysis = {
        "stage": stage,
        "corpus_id": corpus_definition()["corpus_id"],
        "ruleset_id": corpus_definition()["ruleset_id"],
        "reach_star": reach_star,
        "group": group_rows,
        "pairwise": pair_rows,
    }
    results.mkdir(parents=True, exist_ok=True)
    path = results / f"phase2_{stage}_analysis.json"
    path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    print(f"wrote {path}  ({len(group_rows)} roster rows, {len(pair_rows)} pair rows)")

    if stage == "pilot":
        _print_pilot(analysis, output)
    else:
        _print_main(analysis)
    return 0


# ---------------------------------------------------------------------------
# pilot screening against the predeclared rejection rules
# ---------------------------------------------------------------------------


def _condition_index(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    conditions: dict[str, dict[str, Any]] = {}
    for row in analysis["group"]:
        bucket = conditions.setdefault(
            row["condition_id"],
            {
                "condition_id": row["condition_id"],
                "arena_size": row["arena_size"],
                "instr_per_tick": row["instr_per_tick"],
                "locality_reach": row["locality_reach"],
                "arm": row.get("arm"),
                "rosters": {},
                "pairs": {},
            },
        )
        bucket["rosters"][row["roster_id"]] = row
    for row in analysis["pairwise"]:
        bucket = conditions.setdefault(
            row["condition_id"],
            {
                "condition_id": row["condition_id"],
                "arena_size": row["arena_size"],
                "instr_per_tick": row["instr_per_tick"],
                "locality_reach": row["locality_reach"],
                "arm": row.get("arm"),
                "rosters": {},
                "pairs": {},
            },
        )
        bucket["pairs"][row["pair_id"]] = row
    return conditions


def _mean_move_share(bucket: dict[str, Any]) -> float | None:
    shares = [
        stats["move_share"]
        for row in bucket["rosters"].values()
        for stats in row["locality"]["by_agent"].values()
    ]
    return phase1._mean(shares)


def _captures(bucket: dict[str, Any], search_agents: tuple[str, ...]) -> int:
    total = 0
    for row in bucket["rosters"].values():
        if not any(agent in search_agents for agent in row["roster"]):
            continue
        total += row["match_shape"]["entrant_termination_reasons"].get("core_captured", 0)
    return total


def screen_pilot(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    corpus = corpus_definition()
    rules = corpus["stages"]["pilot"]["rejection_rules"]
    search_agents = tuple(corpus["roles"]["search"])
    rows: list[dict[str, Any]] = []
    for condition_id, bucket in _condition_index(analysis).items():
        arena = bucket["arena_size"]
        reach = bucket["locality_reach"]
        flags: list[str] = []
        if reach < 8:
            flags.append("attack_infeasible")
        if reach >= arena / 4:
            flags.append("reach_collapse")
        captures = _captures(bucket, search_agents)
        if captures == 0:
            flags.append("no_contact")
        move_share = _mean_move_share(bucket)
        if move_share is not None and move_share >= 0.50:
            flags.append("movement_dominated")
        ticks_mean = phase1._mean(
            [row["match_shape"]["ticks_mean"] for row in bucket["rosters"].values()]
        )
        saturation = phase1._mean(
            [row["match_shape"]["saturation_mean_pct"] for row in bucket["rosters"].values()]
        )
        limit = max(row["ticks"] for row in bucket["rosters"].values())
        if (
            ticks_mean is not None
            and saturation is not None
            and ticks_mean >= limit - 0.5
            and saturation < 20.0
        ):
            flags.append("crawl")
        camper_rates = [
            row["entrants"].get("local_camper", {}).get("win_rate")
            for row in bucket["rosters"].values()
            if any(agent in search_agents for agent in row["roster"])
        ]
        if any(rate is not None and rate >= 0.50 for rate in camper_rates):
            flags.append("turtle_dominant")
        misses = sum(
            int(stats["reach_misses"] or 0)
            for row in bucket["rosters"].values()
            for stats in row["locality"]["by_agent"].values()
        )
        forfeits = sum(
            row["match_shape"]["entrant_termination_reasons"].get("forfeit", 0)
            for row in bucket["rosters"].values()
        )
        if misses or forfeits:
            flags.append("runtime_pathology")
        rows.append(
            {
                "condition_id": condition_id,
                "arena_size": arena,
                "instr_per_tick": bucket["instr_per_tick"],
                "locality_reach": reach,
                "captures_in_search_rosters": captures,
                "mean_move_share": move_share,
                "mean_ticks": ticks_mean,
                "mean_saturation_pct": saturation,
                "reach_misses": misses,
                "forfeits": forfeits,
                "rejected_by": flags,
                "surviving": not flags,
                "rules": {flag: rules[flag] for flag in flags},
            }
        )
    rows.sort(key=lambda r: (r["arena_size"], r["instr_per_tick"], r["locality_reach"]))
    return rows


def promote(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the corpus definition's own predeclared promotion rule."""

    definition = corpus_definition()["stages"]["pilot"]
    anchor = [r for r in rows if r["arena_size"] == 4096 and r["instr_per_tick"] == 8]
    eligible = [
        r
        for r in anchor
        if r["captures_in_search_rosters"] > 0
        and r["mean_move_share"] is not None
        and r["mean_move_share"] < 0.50
        and r["locality_reach"] >= 8
        and r["locality_reach"] <= r["arena_size"] // 32
    ]
    eligible.sort(key=lambda r: r["locality_reach"])
    return {
        "rule": definition["promotion_rule"],
        "eligible": [r["condition_id"] for r in eligible],
        "reach_star": eligible[0]["locality_reach"] if eligible else None,
        "reach_star_condition": eligible[0]["condition_id"] if eligible else None,
    }


def _print_pilot(analysis: dict[str, Any], output: Path) -> None:
    rows = screen_pilot(analysis)
    print("\n== pilot screening against the predeclared rejection rules ==")
    header = (
        f"{'condition':<16}{'arena':>7}{'budget':>7}{'R':>7}{'caps':>6}"
        f"{'move%':>8}{'ticks':>7}{'sat%':>7}  flags"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        move = f"{row['mean_move_share'] * 100:.1f}" if row["mean_move_share"] is not None else "-"
        ticks = f"{row['mean_ticks']:.0f}" if row["mean_ticks"] is not None else "-"
        sat = f"{row['mean_saturation_pct']:.1f}" if row["mean_saturation_pct"] is not None else "-"
        print(
            f"{row['condition_id']:<16}{row['arena_size']:>7}{row['instr_per_tick']:>7}"
            f"{row['locality_reach']:>7}{row['captures_in_search_rosters']:>6}"
            f"{move:>8}{ticks:>7}{sat:>7}  "
            + (", ".join(row["rejected_by"]) or "-")
        )
    decision = promote(rows)
    print(f"\neligible for promotion: {decision['eligible'] or 'none'}")
    print(f"R* = {decision['reach_star']}")
    results = output / "pilot" / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / "phase2_pilot_screening.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    (results / "phase2_pilot_promotion.json").write_text(
        json.dumps(decision, indent=2), encoding="utf-8"
    )
    print(f"wrote {results / 'phase2_pilot_screening.json'}")
    print(f"wrote {results / 'phase2_pilot_promotion.json'}")


def _print_main(analysis: dict[str, Any]) -> None:
    print("\n== main conditions ==")
    header = (
        f"{'condition':<16}{'arm':<22}{'arena':>7}{'budget':>7}{'R':>6}{'S':>8}"
        f"{'sat%':>7}{'ticks':>7}{'caps%':>7}{'move%':>7}  flags"
    )
    print(header)
    print("-" * len(header))
    for condition_id, bucket in _condition_index(analysis).items():
        rosters = list(bucket["rosters"].values())
        if not rosters:
            continue
        arena = bucket["arena_size"]
        budget = bucket["instr_per_tick"]
        ticks = rosters[0]["ticks"]
        density = (budget * ticks) / arena
        sat = phase1._mean([r["match_shape"]["saturation_mean_pct"] for r in rosters])
        tk = phase1._mean([r["match_shape"]["ticks_mean"] for r in rosters])
        slots = sum(sum(r["match_shape"]["entrant_termination_reasons"].values()) for r in rosters)
        caps = sum(
            r["match_shape"]["entrant_termination_reasons"].get("core_captured", 0)
            for r in rosters
        )
        move = _mean_move_share(bucket)
        flags = sorted({flag for r in rosters for flag in r.get("degeneracy_flags", [])})
        print(
            f"{condition_id:<16}{bucket['arm'] or '':<22}{arena:>7}{budget:>7}"
            f"{bucket['locality_reach']:>6}{density:>8.3f}"
            f"{(sat or 0):>7.1f}{(tk or 0):>7.0f}"
            f"{(100.0 * caps / slots if slots else 0):>7.1f}"
            f"{(100.0 * move if move is not None else 0):>7.1f}  "
            + (", ".join(flags) or "-")
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["run", "analyze"])
    parser.add_argument("--stage", default="pilot", help="pilot or main")
    parser.add_argument(
        "--output", type=Path, default=Path("runs/research_v3_phase2"), help="corpus root"
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    if args.command == "run":
        return cmd_run(args.stage, output, args.workers)
    return cmd_analyze(args.stage, output)


if __name__ == "__main__":
    raise SystemExit(main())
