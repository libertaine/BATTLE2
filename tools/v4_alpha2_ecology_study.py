"""Phase 5 alpha1/alpha2 ecology qualification runner (NOT a public Bytefray CLI).

Answers the Phase 5K questions the v4.0.0-alpha2 release decision depends on
by running one paired, controlled study: the same roster, arenas, seeds, and
seat orientations under ``bytefray-rules-4-alpha1`` and
``bytefray-rules-4-alpha2``, so every difference reported between the two
conditions is the Ruleset and nothing else.

**How this differs from the Phase 4 harness it succeeds.** Phase 4 expressed
its experimental conditions as research-only ``MatchRequest`` override fields
(``core_size``, ``reach_cap``, ``process_spread_radius``,
``process_order_overrides``, ``process_selection_mode``) and computed seeded
placement inside the harness. None of those fields exists in the product, and
this module deliberately does not reintroduce them: a condition here is a
Ruleset *identity*, placement comes from
``battle_engine.placement.resolve_direct_match_starts`` -- the same function
``bytefray run`` calls -- and process selection comes from the Ruleset policy.
The harness therefore has no way to construct a match the product cannot, and
no ecology number it reports can come from a code path a user cannot reach.

Execution is one call to ``NativeMatchService.run(MatchRequest)`` per match,
the exact canonical product entry point. This module supplies only the
matrix, the placement resolution every product caller already performs, and
post-hoc replay analysis for the handful of metrics ``NativeMatchResult`` does
not summarise but replay schema 4 already records per tick.

Usage::

    python tools/v4_alpha2_ecology_study.py run \\
        --condition alpha2 --arena-sizes 256 512 1024 --seeds 0-31 \\
        --ticks 1000 --output <research-root>/raw_results

    python tools/v4_alpha2_ecology_study.py summarize \\
        --input <research-root>/raw_results --output <research-root>/summaries

``run`` appends one JSON record per match to ``<condition>.jsonl`` and is
resumable: an already-recorded (condition, pair, arena, seed, orientation)
tuple is skipped.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.placement import resolve_direct_match_starts
from battle_engine.replay import MatchResult, ReplayHeader, TickSnapshot, iter_replay
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
)

# Research probes live outside the product agents/ catalogue on purpose -- see
# each probe's own module docstring for what it isolates and why it is not a
# competitive entrant.
PROBES_ROOT = REPO / "tools" / "v4_alpha2_ecology_agents"
PROBE_AGENTS = ("local_hunter",)

#: Frozen historical controls, unchanged from the Phase 4 roster. Their source
#: is deliberately NOT adapted to alpha2 before their alpha2 results are
#: recorded: "Hydra and Nemesis get weaker" is a fact about agents written for
#: alpha1, and it is not by itself evidence that alpha2 is a better Ruleset.
HISTORICAL_ROSTER = (
    "hydra",
    "Nemesis",
    "viper",
    "v4_claimer",
    "v4_concentrated_attacker",
    "v4_defender_scout",
    "v4_local_defender",
    "v4_scout",
)

#: Agents that know alpha2's rules -- that placement is not closed-form, and
#: that targets must be acquired through the API v2 observation contract.
#: New IDs, never overwrites of the historical agents above.
ADAPTED_ROSTER = ("hydra_alpha2", "nemesis_alpha2")

ROSTER = (*HISTORICAL_ROSTER, *ADAPTED_ROSTER, *PROBE_AGENTS)

CONDITIONS: dict[str, str] = {
    "alpha1": BYTEFRAY_RULESET_V4_ALPHA1_ID,
    "alpha2": BYTEFRAY_RULESET_V4_ALPHA2_ID,
}


def resolve_any_agent(name: str):
    if name in PROBE_AGENTS:
        return resolve_agent(PROBES_ROOT, name)
    return resolve_agent(REPO, name)


# --------------------------------------------------------------------------
# Matrix
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchSpec:
    condition: str
    agent_a: str
    agent_b: str
    arena_size: int
    seed: int
    orientation: str  # "a_first" | "b_first"


def iter_matrix(
    roster: tuple[str, ...],
    arena_sizes: tuple[int, ...],
    seeds: tuple[int, ...],
    condition: str,
) -> list[MatchSpec]:
    return [
        MatchSpec(condition, agent_a, agent_b, arena_size, seed, orientation)
        for agent_a, agent_b in itertools.combinations(roster, 2)
        for arena_size in arena_sizes
        for seed in seeds
        for orientation in ("a_first", "b_first")
    ]


def build_request(spec: MatchSpec, ticks: int, replay_path: Path) -> MatchRequest:
    """One match, built exactly the way ``bytefray run`` builds one.

    Both seats' starts are left omitted and resolved by the production
    placement function against the condition's Ruleset, so alpha1 gets its
    historical opposite pair and alpha2 gets its seed-derived layout without
    this harness computing either itself.
    """

    ruleset_id = CONDITIONS[spec.condition]
    first, second = (
        (spec.agent_a, spec.agent_b)
        if spec.orientation == "a_first"
        else (spec.agent_b, spec.agent_a)
    )
    starts = resolve_direct_match_starts(
        ruleset_id=ruleset_id,
        arena_size=spec.arena_size,
        entrant_count=2,
        supplied_starts=[None, None],
        seed=spec.seed,
    )
    return MatchRequest(
        config=Config(arena_size=spec.arena_size, instr_per_tick=8, seed=spec.seed),
        entrants=(
            MatchEntrant.python("A", first, starts[0], resolve_any_agent(first)),
            MatchEntrant.python("B", second, starts[1], resolve_any_agent(second)),
        ),
        max_ticks=ticks,
        replay_path=replay_path,
        verbose=False,
        ruleset_id=ruleset_id,
    )


# --------------------------------------------------------------------------
# Replay analysis
# --------------------------------------------------------------------------


def _circular_distance(a: int, b: int, arena_size: int) -> int:
    delta = abs(a - b) % arena_size
    return min(delta, arena_size - delta)


def analyze_replay(replay_path: Path) -> dict[str, Any]:
    """One pass over a replay for the spatial metrics results do not carry.

    Movement, dispersion, disruption timing, full-roster lockout, a
    quota-redistribution proxy, and visibility/contact timing -- every one
    reconstructed from schema-4 fields already persisted
    (``ProcessState.anchor/reach/disrupted``), with no new instrumentation and
    no engine change. Carried over from the Phase 4 harness so the two
    studies' numbers mean the same thing, plus two Phase 5 additions:
    ``unique_anchors`` and ``moves`` (the movement question alpha2's search
    behaviour turns on) and ``max_consecutive_lockout_ticks`` (the
    disruption-lock measurement Phase 5J requires).
    """

    header: ReplayHeader | None = None
    anchors_seen: dict[str, set[int]] = defaultdict(set)
    moves: dict[str, int] = defaultdict(int)
    previous_anchor: dict[tuple[str, str], int] = {}
    max_dispersion: dict[str, int] = defaultdict(int)
    first_disruption_tick: dict[str, int | None] = defaultdict(lambda: None)
    full_lockout_ticks: dict[str, int] = defaultdict(int)
    current_lockout_run: dict[str, int] = defaultdict(int)
    max_lockout_run: dict[str, int] = defaultdict(int)
    prev_disrupted: dict[str, frozenset[str]] = {}
    redistribution_events: dict[str, int] = defaultdict(int)
    first_contact_tick: int | None = None
    first_mutual_contact_tick: int | None = None
    contact_ticks = 0
    lost_contact_events = 0
    was_in_contact = False
    # A schema-4 replay ends with a MatchResult record that repeats the final
    # tick's process snapshots. Counting it as well as that tick's own
    # TickSnapshot would inflate every per-tick tally by one on the last tick,
    # which matters most for the consecutive-lockout run length the
    # disruption-lock assessment turns on.
    seen_ticks: set[int] = set()

    for record in iter_replay(replay_path):
        if isinstance(record, ReplayHeader):
            header = record
            continue
        if not isinstance(record, (TickSnapshot, MatchResult)):
            continue
        tick = record.tick if isinstance(record, TickSnapshot) else record.ticks
        if tick in seen_ticks:
            continue
        seen_ticks.add(tick)
        arena_size = header.config.arena_size if header else 1

        by_entrant: dict[str, list] = defaultdict(list)
        for process in record.processes:
            by_entrant[process.entrant_id].append(process)

        for entrant_id, processes in by_entrant.items():
            for process in processes:
                key = (entrant_id, process.process_id)
                anchors_seen[entrant_id].add(process.anchor)
                if key in previous_anchor and previous_anchor[key] != process.anchor:
                    moves[entrant_id] += 1
                previous_anchor[key] = process.anchor

            positions = [process.anchor for process in processes]
            if len(positions) > 1:
                max_dispersion[entrant_id] = max(
                    max_dispersion[entrant_id],
                    max(
                        _circular_distance(a, b, arena_size)
                        for i, a in enumerate(positions)
                        for b in positions[i + 1 :]
                    ),
                )

            disrupted = frozenset(p.process_id for p in processes if p.disrupted)
            if disrupted and first_disruption_tick[entrant_id] is None and tick > 0:
                first_disruption_tick[entrant_id] = tick
            if entrant_id in prev_disrupted and prev_disrupted[entrant_id] != disrupted:
                redistribution_events[entrant_id] += 1
            prev_disrupted[entrant_id] = disrupted

            if processes and len(disrupted) == len(processes):
                full_lockout_ticks[entrant_id] += 1
                current_lockout_run[entrant_id] += 1
                max_lockout_run[entrant_id] = max(
                    max_lockout_run[entrant_id], current_lockout_run[entrant_id]
                )
            else:
                current_lockout_run[entrant_id] = 0

        if isinstance(record, TickSnapshot) and header is not None:
            entrant_ids = list(by_entrant)
            in_contact = {entrant_id: False for entrant_id in entrant_ids}
            for observer_id in entrant_ids:
                for other_id in entrant_ids:
                    if observer_id == other_id:
                        continue
                    for observer in by_entrant[observer_id]:
                        if observer.disrupted:
                            continue
                        for enemy in by_entrant[other_id]:
                            if (
                                _circular_distance(observer.anchor, enemy.anchor, arena_size)
                                <= observer.reach
                            ):
                                in_contact[observer_id] = True
                                break
                        if in_contact[observer_id]:
                            break
            any_contact = any(in_contact.values())
            mutual = len(entrant_ids) >= 2 and all(in_contact.values())
            if any_contact:
                contact_ticks += 1
                if first_contact_tick is None:
                    first_contact_tick = tick
            if mutual and first_mutual_contact_tick is None:
                first_mutual_contact_tick = tick
            if was_in_contact and not any_contact:
                lost_contact_events += 1
            was_in_contact = any_contact

    return {
        "unique_anchors": {k: len(v) for k, v in anchors_seen.items()},
        "moves": dict(moves),
        "max_dispersion": dict(max_dispersion),
        "first_disruption_tick": dict(first_disruption_tick),
        "full_lockout_ticks": dict(full_lockout_ticks),
        "max_consecutive_lockout_ticks": dict(max_lockout_run),
        "redistribution_events": dict(redistribution_events),
        "first_contact_tick": first_contact_tick,
        "first_mutual_contact_tick": first_mutual_contact_tick,
        "contact_ticks": contact_ticks,
        "lost_contact_events": lost_contact_events,
    }


def run_one(spec: MatchSpec, ticks: int, scratch_dir: Path) -> dict[str, Any]:
    replay_path = scratch_dir / (
        f"{spec.condition}_{spec.agent_a}_{spec.agent_b}_"
        f"{spec.arena_size}_{spec.seed}_{spec.orientation}.jsonl"
    )
    request = build_request(spec, ticks, replay_path)
    result = NativeMatchService().run(request)
    replay_metrics = analyze_replay(replay_path)
    try:
        replay_path.unlink(missing_ok=True)
        replay_path.with_name("result.json").unlink(missing_ok=True)
        replay_path.with_name("summary.json").unlink(missing_ok=True)
    except OSError:
        pass

    agents_by_slot = {agent.metadata["slot"]: agent for agent in result.agents}
    slot_to_agent = {
        0: spec.agent_a if spec.orientation == "a_first" else spec.agent_b,
        1: spec.agent_b if spec.orientation == "a_first" else spec.agent_a,
    }
    winner_slot = {"A": 0, "B": 1}.get(result.winner)
    starts = tuple(entrant.start for entrant in request.entrants)

    return {
        "condition": spec.condition,
        "ruleset_id": CONDITIONS[spec.condition],
        "agent_a": spec.agent_a,
        "agent_b": spec.agent_b,
        "arena_size": spec.arena_size,
        "seed": spec.seed,
        "orientation": spec.orientation,
        "starts": starts,
        "separation": _circular_distance(starts[0], starts[1], spec.arena_size),
        "winner_slot": winner_slot,
        "winner_agent": slot_to_agent.get(winner_slot),
        "ticks_run": result.ticks_run,
        "termination_reason": getattr(
            result.termination_reason, "value", str(result.termination_reason)
        ),
        "first": _side(agents_by_slot[0]),
        "second": _side(agents_by_slot[1]),
        "replay_metrics": replay_metrics,
    }


def _side(agent: Any) -> dict[str, Any]:
    return {
        "agent_id": agent.agent_id,
        "alive": agent.alive,
        "score": agent.score,
        "territory_pct_last": agent.territory_pct_last,
        "processes": agent.metadata.get("processes"),
    }


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def run_condition(
    condition: str,
    arena_sizes: tuple[int, ...],
    seeds: tuple[int, ...],
    ticks: int,
    output_dir: Path,
    roster: tuple[str, ...],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    # Per-condition, because a match's transient result.json/summary.json are
    # named by the engine from the replay's own directory, not from the
    # replay's stem. Two conditions sharing one scratch directory therefore
    # race on the same three filenames, and on Windows the loser dies with a
    # WinError 5 mid-study rather than merely overwriting.
    scratch_dir = output_dir / f"_scratch_{condition}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{condition}.jsonl"

    done: set[tuple] = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                done.add(
                    (
                        record["agent_a"],
                        record["agent_b"],
                        record["arena_size"],
                        record["seed"],
                        record["orientation"],
                    )
                )

    specs = iter_matrix(roster, arena_sizes, seeds, condition)
    pending = [
        spec
        for spec in specs
        if (spec.agent_a, spec.agent_b, spec.arena_size, spec.seed, spec.orientation)
        not in done
    ]
    print(
        f"{condition}: {len(specs)} matches in matrix, {len(done)} already recorded, "
        f"{len(pending)} to run",
        flush=True,
    )

    with out_path.open("a", encoding="utf-8") as handle:
        for index, spec in enumerate(pending, start=1):
            handle.write(json.dumps(run_one(spec, ticks, scratch_dir)) + "\n")
            if index % 250 == 0:
                handle.flush()
                print(f"  {index}/{len(pending)}", flush=True)
    print(f"{condition}: wrote {out_path}", flush=True)


# --------------------------------------------------------------------------
# Summaries
# --------------------------------------------------------------------------


def _wilson(successes: int, total: int) -> tuple[float, float]:
    """Wilson 95% interval -- the same interval Phase 4 reported."""

    if total == 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    phat = successes / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = (
        z * ((phat * (1 - phat) / total + z * z / (4 * total * total)) ** 0.5)
    ) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {}

    ticks = [record["ticks_run"] for record in records]
    tick_limited = sum(
        1 for record in records if record["termination_reason"] == "tick_limit"
    )
    draws = sum(1 for record in records if record["winner_agent"] is None)

    played: dict[str, int] = defaultdict(int)
    won: dict[str, int] = defaultdict(int)
    first_seat_played: dict[str, int] = defaultdict(int)
    first_seat_won: dict[str, int] = defaultdict(int)
    moves: dict[str, list[int]] = defaultdict(list)
    anchors: dict[str, list[int]] = defaultdict(list)
    lockout: dict[str, list[int]] = defaultdict(list)
    max_lockout_run: dict[str, list[int]] = defaultdict(list)
    contact_first: list[int] = []
    contacted = 0

    for record in records:
        by_slot = {0: record["first"], 1: record["second"]}
        names = {
            0: record["agent_a"]
            if record["orientation"] == "a_first"
            else record["agent_b"],
            1: record["agent_b"]
            if record["orientation"] == "a_first"
            else record["agent_a"],
        }
        for slot, name in names.items():
            played[name] += 1
            entrant_id = by_slot[slot]["agent_id"]
            metrics = record["replay_metrics"]
            moves[name].append(metrics["moves"].get(entrant_id, 0))
            anchors[name].append(metrics["unique_anchors"].get(entrant_id, 0))
            lockout[name].append(metrics["full_lockout_ticks"].get(entrant_id, 0))
            max_lockout_run[name].append(
                metrics["max_consecutive_lockout_ticks"].get(entrant_id, 0)
            )
            if slot == 0:
                first_seat_played[name] += 1
        winner = record["winner_agent"]
        if winner is not None:
            won[winner] += 1
            if record["winner_slot"] == 0:
                first_seat_won[winner] += 1
        if record["replay_metrics"]["first_contact_tick"] is not None:
            contacted += 1
            contact_first.append(record["replay_metrics"]["first_contact_tick"])

    agents = {}
    for name in sorted(played):
        n = played[name]
        wins = won[name]
        low, high = _wilson(wins, n)
        first_n = first_seat_played[name]
        second_n = n - first_n
        first_rate = first_seat_won[name] / first_n if first_n else 0.0
        second_rate = (wins - first_seat_won[name]) / second_n if second_n else 0.0
        agents[name] = {
            "played": n,
            "wins": wins,
            "win_rate": wins / n,
            "win_rate_ci": [low, high],
            "seat_delta": first_rate - second_rate,
            "mean_moves": statistics.mean(moves[name]) if moves[name] else 0.0,
            "mean_unique_anchors": statistics.mean(anchors[name])
            if anchors[name]
            else 0.0,
            "mean_full_lockout_ticks": statistics.mean(lockout[name])
            if lockout[name]
            else 0.0,
            "max_consecutive_lockout_ticks": max(max_lockout_run[name])
            if max_lockout_run[name]
            else 0,
            "matches_with_long_lockout": sum(
                1 for value in max_lockout_run[name] if value >= 50
            ),
        }

    return {
        "matches": total,
        "median_ticks": statistics.median(ticks),
        "mean_ticks": statistics.mean(ticks),
        "tick_limit_rate": tick_limited / total,
        "draw_rate": draws / total,
        "contact_rate": contacted / total,
        "median_first_contact_tick": statistics.median(contact_first)
        if contact_first
        else None,
        "agents": agents,
    }


def write_summary(condition: str, summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{condition}_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    with (output_dir / f"{condition}_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "agent",
                "played",
                "wins",
                "win_rate",
                "ci_low",
                "ci_high",
                "seat_delta",
                "mean_moves",
                "mean_unique_anchors",
                "mean_full_lockout_ticks",
                "max_consecutive_lockout_ticks",
                "matches_with_long_lockout",
            ]
        )
        for name, row in summary["agents"].items():
            writer.writerow(
                [
                    name,
                    row["played"],
                    row["wins"],
                    f"{row['win_rate']:.4f}",
                    f"{row['win_rate_ci'][0]:.4f}",
                    f"{row['win_rate_ci'][1]:.4f}",
                    f"{row['seat_delta']:+.4f}",
                    f"{row['mean_moves']:.2f}",
                    f"{row['mean_unique_anchors']:.2f}",
                    f"{row['mean_full_lockout_ticks']:.2f}",
                    row["max_consecutive_lockout_ticks"],
                    row["matches_with_long_lockout"],
                ]
            )


def print_summary(condition: str, summary: dict[str, Any]) -> None:
    print(f"\n=== {condition} ({summary['matches']} matches) ===")
    print(
        f"median ticks {summary['median_ticks']:.1f} | "
        f"tick-limit {summary['tick_limit_rate']:.1%} | "
        f"draw {summary['draw_rate']:.1%} | "
        f"contact {summary['contact_rate']:.1%} | "
        f"median first contact {summary['median_first_contact_tick']}"
    )
    print(
        f"{'agent':28} {'win%':>7} {'95% CI':>16} {'seat':>7} "
        f"{'moves':>8} {'anchors':>8} {'lockout':>8} {'maxrun':>7}"
    )
    for name, row in sorted(
        summary["agents"].items(), key=lambda item: -item[1]["win_rate"]
    ):
        low, high = row["win_rate_ci"]
        print(
            f"{name:28} {row['win_rate']:6.1%} "
            f"[{low:5.1%},{high:6.1%}] {row['seat_delta']:+6.1%} "
            f"{row['mean_moves']:8.1f} {row['mean_unique_anchors']:8.1f} "
            f"{row['mean_full_lockout_ticks']:8.1f} "
            f"{row['max_consecutive_lockout_ticks']:7d}"
        )


# --------------------------------------------------------------------------
# Shard merge
# --------------------------------------------------------------------------


def _cell_key(record: dict[str, Any]) -> tuple:
    return (
        record["agent_a"],
        record["agent_b"],
        record["arena_size"],
        record["seed"],
        record["orientation"],
    )


def merge_shards(
    inputs: list[Path], output: Path, expected: int | None
) -> list[dict[str, Any]]:
    """Fold seed-partitioned shard files into one condition file.

    A condition may be executed as concurrent workers over disjoint seed
    ranges when a single-threaded run would take too long. Every worker
    covers the full pair x arena x orientation matrix for its own seeds, so
    no matrix cell is ever split across workers -- but a shard set may still
    overlap an earlier partial run of the same condition, so cells are
    de-duplicated by identity rather than concatenated blindly.

    First occurrence wins, and duplicates are counted and reported. Every
    match is deterministic in its own recorded inputs and shares no state
    with any other, so which worker produced a given cell cannot change it;
    a duplicate that *disagreed* would mean the study was not reproducible,
    so disagreements are reported as errors rather than silently resolved.
    """

    seen: dict[tuple, dict[str, Any]] = {}
    duplicates = 0
    conflicts: list[tuple] = []
    for path in inputs:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            key = _cell_key(record)
            if key in seen:
                duplicates += 1
                previous = seen[key]
                if (
                    previous["winner_agent"],
                    previous["ticks_run"],
                    previous["termination_reason"],
                ) != (
                    record["winner_agent"],
                    record["ticks_run"],
                    record["termination_reason"],
                ):
                    conflicts.append(key)
                continue
            seen[key] = record

    print(
        f"merged {len(inputs)} shard file(s): {len(seen)} unique cells, "
        f"{duplicates} duplicate(s) discarded, {len(conflicts)} conflict(s)"
    )
    if conflicts:
        raise SystemExit(
            f"non-deterministic duplicate cells found: {conflicts[:5]!r} "
            "-- the study is not reproducible and must not be summarised"
        )
    if expected is not None and len(seen) != expected:
        raise SystemExit(
            f"expected {expected} unique cells, merged {len(seen)}; "
            "the matrix is incomplete"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for key in sorted(seen, key=lambda item: tuple(map(str, item))):
            handle.write(json.dumps(seen[key]) + "\n")
    print(f"wrote {output}")
    return list(seen.values())


# --------------------------------------------------------------------------
# Paired alpha1/alpha2 comparison
# --------------------------------------------------------------------------


def compare(summaries: dict[str, dict[str, Any]]) -> None:
    """Print the Phase 5L side-by-side table.

    Deliberately a *paired* comparison over an identical matrix: same roster,
    pairs, arenas, seeds, and both orientations in both conditions, so a
    difference in any row is the Ruleset rather than a difference in what was
    measured.
    """

    alpha1, alpha2 = summaries["alpha1"], summaries["alpha2"]
    rows = [
        ("matches", f"{alpha1['matches']}", f"{alpha2['matches']}"),
        ("median match ticks", f"{alpha1['median_ticks']:.1f}", f"{alpha2['median_ticks']:.1f}"),
        ("mean match ticks", f"{alpha1['mean_ticks']:.1f}", f"{alpha2['mean_ticks']:.1f}"),
        ("tick-limit rate", f"{alpha1['tick_limit_rate']:.1%}", f"{alpha2['tick_limit_rate']:.1%}"),
        ("draw rate", f"{alpha1['draw_rate']:.1%}", f"{alpha2['draw_rate']:.1%}"),
        ("contact rate", f"{alpha1['contact_rate']:.1%}", f"{alpha2['contact_rate']:.1%}"),
        (
            "median first contact tick",
            str(alpha1["median_first_contact_tick"]),
            str(alpha2["median_first_contact_tick"]),
        ),
    ]
    print("\n=== Phase 5L: alpha1 vs alpha2 (paired, identical matrix) ===")
    print(f"{'metric':32} {'alpha1':>14} {'alpha2':>14}")
    for label, a, b in rows:
        print(f"{label:32} {a:>14} {b:>14}")

    def agent_rows(field: str, fmt: str) -> None:
        print(f"\n-- {field} --")
        print(f"{'agent':28} {'alpha1':>12} {'alpha2':>12} {'delta':>12}")
        for name in sorted(set(alpha1["agents"]) | set(alpha2["agents"])):
            a = alpha1["agents"].get(name, {}).get(field)
            b = alpha2["agents"].get(name, {}).get(field)
            if a is None or b is None:
                continue
            print(
                f"{name:28} {format(a, fmt):>12} {format(b, fmt):>12} "
                f"{format(b - a, '+' + fmt):>12}"
            )

    agent_rows("win_rate", ".1%")
    agent_rows("seat_delta", ".1%")
    agent_rows("mean_moves", ".1f")
    agent_rows("mean_unique_anchors", ".1f")
    agent_rows("mean_full_lockout_ticks", ".1f")
    agent_rows("matches_with_long_lockout", "d")


# --------------------------------------------------------------------------
# Disruption-lock assessment
# --------------------------------------------------------------------------

#: An entrant fully disrupted for at least this fraction of the match it was
#: in, in one unbroken run, is treated as *locked* rather than merely
#: pressured. Phase 4's finding was specifically that a pursuer can be
#: disrupted every tick "for the rest of the match" with no way to disengage,
#: so the measure has to be a sustained run relative to match length -- a
#: fixed tick count would call a 40-tick run in a 1000-tick match the same
#: thing as a 40-tick run in a 45-tick one.
LOCK_FRACTION = 0.5

#: Below this many ticks a match is too short for "sustained lockout" to
#: mean anything: an entrant killed on tick 3 was not locked out, it lost.
LOCK_MIN_TICKS = 50


def lockout_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure how often the Phase 4 disruption-lock actually happens.

    Phase 4 (Section E) found that a single-process pursuer which gets close
    enough to detect a reactive opponent, but not close enough to win, can be
    re-disrupted every tick indefinitely -- unable to attack *or* retreat,
    since a disrupted process cannot issue a MOVE either. Phase 5 has to
    classify that as a rare edge case, a meaningful archetype weakness, or a
    dominant ecological failure, so it needs a frequency, not an anecdote.

    For every (match, entrant) pair this reports whether the entrant spent an
    unbroken :data:`LOCK_FRACTION` of the match fully disrupted, and what
    happened to it when it did. The outcome split is the part that decides
    the classification: lockout that reliably precedes a loss is a weakness
    of the locked archetype, while lockout that mostly ends in a draw is the
    stalemate mechanism Phase 4 described.
    """

    per_agent: dict[str, dict[str, int]] = defaultdict(
        lambda: {"played": 0, "locked": 0, "locked_lost": 0, "locked_drew": 0, "locked_won": 0}
    )
    eligible = 0
    locked_matches = 0

    for record in records:
        ticks = record["ticks_run"]
        names = {
            0: record["agent_a"] if record["orientation"] == "a_first" else record["agent_b"],
            1: record["agent_b"] if record["orientation"] == "a_first" else record["agent_a"],
        }
        entrant_ids = {0: record["first"]["agent_id"], 1: record["second"]["agent_id"]}
        runs = record["replay_metrics"]["max_consecutive_lockout_ticks"]
        winner = record["winner_agent"]
        match_counted = False
        for slot, name in names.items():
            per_agent[name]["played"] += 1
            if ticks < LOCK_MIN_TICKS:
                continue
            if slot == 0:
                eligible += 1
            run = runs.get(entrant_ids[slot], 0)
            if run < ticks * LOCK_FRACTION:
                continue
            per_agent[name]["locked"] += 1
            if not match_counted:
                locked_matches += 1
                match_counted = True
            if winner is None:
                per_agent[name]["locked_drew"] += 1
            elif winner == name:
                per_agent[name]["locked_won"] += 1
            else:
                per_agent[name]["locked_lost"] += 1

    return {
        "lock_fraction": LOCK_FRACTION,
        "lock_min_ticks": LOCK_MIN_TICKS,
        "matches": len(records),
        "matches_long_enough_to_assess": eligible,
        "matches_with_a_locked_entrant": locked_matches,
        "agents": {name: dict(row) for name, row in sorted(per_agent.items())},
    }


def print_lockout(condition: str, report: dict[str, Any]) -> None:
    print(
        f"\n=== disruption lock, {condition} "
        f"(locked = fully disrupted for an unbroken "
        f"{report['lock_fraction']:.0%} of a match of >= "
        f"{report['lock_min_ticks']} ticks) ==="
    )
    assessable = report["matches_long_enough_to_assess"]
    share = report["matches_with_a_locked_entrant"] / assessable if assessable else 0.0
    print(
        f"{report['matches_with_a_locked_entrant']} of {assessable} assessable "
        f"matches had a locked entrant ({share:.1%})"
    )
    print(f"{'agent':28} {'played':>7} {'locked':>7} {'rate':>7} {'lost':>6} {'drew':>6} {'won':>5}")
    for name, row in sorted(report["agents"].items(), key=lambda item: -item[1]["locked"]):
        rate = row["locked"] / row["played"] if row["played"] else 0.0
        print(
            f"{name:28} {row['played']:7} {row['locked']:7} {rate:6.1%} "
            f"{row['locked_lost']:6} {row['locked_drew']:6} {row['locked_won']:5}"
        )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_seeds(text: str) -> tuple[int, ...]:
    if "-" in text:
        low, high = text.split("-", 1)
        return tuple(range(int(low), int(high) + 1))
    return tuple(int(part) for part in text.split(","))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    runner = sub.add_parser("run")
    runner.add_argument("--condition", choices=sorted(CONDITIONS), required=True)
    runner.add_argument("--arena-sizes", type=int, nargs="+", default=[256, 512, 1024])
    runner.add_argument("--seeds", default="0-31")
    runner.add_argument("--ticks", type=int, default=1000)
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--roster", nargs="*", default=None)

    summarizer = sub.add_parser("summarize")
    summarizer.add_argument("--input", type=Path, required=True)
    summarizer.add_argument("--output", type=Path, required=True)
    summarizer.add_argument("--compare", action="store_true")

    merger = sub.add_parser("merge")
    merger.add_argument("--inputs", type=Path, nargs="+", required=True)
    merger.add_argument("--output", type=Path, required=True)
    merger.add_argument("--expect", type=int, default=None)

    args = parser.parse_args(argv)

    if args.command == "merge":
        merge_shards(list(args.inputs), args.output, args.expect)
        return 0

    if args.command == "run":
        run_condition(
            args.condition,
            tuple(args.arena_sizes),
            parse_seeds(args.seeds),
            args.ticks,
            args.output,
            tuple(args.roster) if args.roster else ROSTER,
        )
        return 0

    summaries: dict[str, dict[str, Any]] = {}
    for path in sorted(args.input.glob("*.jsonl")):
        records = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
        summary = summarize(records)
        if not summary:
            continue
        summaries[path.stem] = summary
        write_summary(path.stem, summary, args.output)
        print_summary(path.stem, summary)
        report = lockout_report(records)
        (args.output / f"{path.stem}_lockout.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        print_lockout(path.stem, report)
    if args.compare and {"alpha1", "alpha2"} <= set(summaries):
        compare(summaries)
        (args.output / "alpha1_vs_alpha2.json").write_text(
            json.dumps(summaries, indent=2, sort_keys=True), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
