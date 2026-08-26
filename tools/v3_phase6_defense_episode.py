"""v3 Phase 6 -- active-defensive-intervention detector (measurement only).

Phase 5A qualified a *same-tick* defensive-success event and found it
measures "was assaulted and survived" rather than "defended": expansion
agents absorb bursts constantly and often survive them, and the event goes
inert whenever ``instr_per_tick`` is too small for an attacker to concentrate
its assault into one tick (``docs/V3_PHASE5A_DEFENSIVE_EVENT_QUALIFICATION.md``
Sec 3, Sec 5 C3). Its own post-hoc Sec 6 found that requiring the victim to
*actively reclaim* a cell restores near-perfect selectivity, but that result
was same-tick only, unvalidated at low action budgets, and explicitly not
load-bearing for its verdict.

This module reconstructs, purely from committed replay artifacts, a
cross-tick **attack episode**: a maximal, uninterrupted sequence of hostile
acquisitions by one attacker against one victim's core. An episode's
*continuity* (when it opens, extends, and closes) is defined entirely by
ownership state transitions -- capture, full reclaim, or full third-party
takeover -- never by a tick-count window, per the governing Phase 6 task's
explicit instruction not to guess one.

A window *is* used, but only to decide whether an episode's progress counts
as "meaningful hostile progress" rather than incidental contact -- seeded by
a pilot-stage finding (this module's own docstring on ``max_assault_ticks``
and Sec 4/6 of the governing report) that an *unbounded* episode is too
permissive: a blind expansion sweeper (``core_defender``'s own outward
sweep is `claimer`-shaped, `hunter`-shaped, and so on) can lap the whole
arena many times over a 400-tick match and slowly accumulate cells from an
undefended victim's core one incidental touch at a time, without ever
mounting a concentrated assault. Bounding how quickly an episode must reach
its threshold is what tells the two apart, and the bound is derived from
``ASSAULT_WINDOW`` -- the search agents' own published burst-width constant
-- and the match's action budget, never from an outcome. No match is
executed and no scoring, Ruleset, weight, agent, or default is touched.

Mechanics this reconstruction depends on (Phase 6A audit; verified against
``engine/src/battle_engine/python_runtime.py`` and ``vm.py``, not assumed):

* Every core-ownership mutation routes through ``VM._wr8``, which always
  records a diff and updates ``vm.writer`` -- an entrant's own write to its
  own core always *claims* the cell; there is no unclaim operation, so an
  entrant cannot lower its own core-owned count by any action available to
  it (Phase 5 Sec 3 point 3, reconfirmed here as the structural basis for
  Phase 6E's self-farming analysis).
* ``vm.tick_diffs`` -- and therefore ``TickSnapshot.memory_diffs`` -- is in
  **true chronological write order** within a tick (``_attribute_core_capture``'s
  own docstring: "entrants act in fixed scheduled order, so diffs are
  appended in the order writes actually happened").
* Scheduling is **sequential-quota per entrant**, not round-robin
  (``scheduler.run_sequential_quota``): within one tick, a seat completes its
  *entire* action quota before the next seat acts at all. This is the
  mechanical reason Phase 5A's same-tick reclaim was seat-order-sensitive --
  only a seat acting *later* in that tick's fixed block order can react to an
  earlier seat's attack within the same tick. A cross-tick episode lets a
  victim seated *earlier* still reclaim, on its own next tick, provided the
  assault has not already zeroed its core that same tick.
* The core-capture check (``apply_core_capture``) runs exactly once per tick,
  after every seat's actions for that tick, comparing against a snapshot
  taken *before* any of that tick's actions ran. Capture attribution
  (``_attribute_core_capture``) and its resulting ``kill``/``death``
  ``TickSnapshot.events`` entries are authoritative and are reused directly
  here rather than re-derived, which also gives Phase 6N an independent
  cross-check: this module's own episode-closure attacker attribution can be
  compared against the engine's own recorded killer for the same tick.
* Core anchors are recovered from each entrant's tick-0 ``pc`` (Phase 4/5A's
  own method, reused unmodified): ``core_start = entrant.start % arena_size``
  and no action has executed by the time tick 0 is published, so tick-0
  ``pc`` equals ``core_start`` for every Python entrant in this corpus.

Usage::

    python tools/v3_phase6_defense_episode.py pilot
    python tools/v3_phase6_defense_episode.py qualify --condition a4096_b8
    python tools/v3_phase6_defense_episode.py qualify --all
    python tools/v3_phase6_defense_episode.py determinism --condition a4096_b8
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.python_runtime import CORE_SIZE
from battle_engine.replay import KillDeathEvent, TickSnapshot, iter_replay

PHASE1 = REPO / "runs" / "research_v3_phase1" / "main" / "results"
GATES_PATH = (
    REPO / "engine" / "src" / "battle_engine" / "data" / "benchmarks" / "v3_phase6_active_defense_gates.json"
)
OUTPUT_ROOT = REPO / "runs" / "research_v3_phase6"

PRIMARY_CONDITION = "a4096_b8"
BUDGET_CONDITIONS = ("a4096_b2", "a4096_b8", "a4096_b32")
PILOT_ROSTERS = (
    "hunter_coretracker_coreseeker",  # two searchers -- Phase 5A's counterevidence roster
    "claimer_coretracker_coredefender",  # search + expansion + defense
    "coredefender_reactive_coreseeker",  # two defenders + one searcher
    "claimer_coreseeker_hunter",  # search + expansion, no defense
)

ROLES = {
    "search": ("core_seeker", "core_tracker"),
    "expansion": ("claimer", "hunter"),
    "defense": ("core_defender", "reactive_core_defender"),
}
ROLE_OF = {agent: role for role, agents in ROLES.items() for agent in agents}


# ---------------------------------------------------------------------------
# Episode reconstruction
# ---------------------------------------------------------------------------


@dataclass
class ReclaimEvent:
    tick: int
    cells: tuple[int, ...]
    cumulative_progress_at_reclaim: int
    victim_survived_tick: bool
    qualifying: bool


@dataclass
class Episode:
    victim: str
    attacker: str
    start_tick: int
    cells_taken: set[int] = field(default_factory=set)
    cumulative_cells: set[int] = field(default_factory=set)
    # Tick at which ``cumulative_cells`` grew to size i+1, for i in
    # range(len(progress_ticks)) -- i.e. progress_ticks[k-1] is the tick the
    # k-th *distinct* cell was first taken from the victim. This is what
    # lets "meaningful progress" require *concentration*, not just eventual
    # total: see ``meaningful_progress_windowed``.
    progress_ticks: list[int] = field(default_factory=list)
    reclaims: list[ReclaimEvent] = field(default_factory=list)
    end_tick: int | None = None
    end_reason: str | None = None  # reclaimed_all | third_party_takeover | captured | match_end
    captured_by: str | None = None

    def meaningful_progress_windowed(self, threshold: int, window: int) -> bool:
        """Did this episode accumulate >= threshold distinct cells within
        ``window`` ticks of its own start? Deliberately *not* just
        ``len(cumulative_cells) >= threshold`` -- an attacker whose blind
        expansion sweep happens to lap back onto an undefended victim's core
        every few ticks can accumulate the same eventual total over hundreds
        of ticks without ever mounting a concentrated assault (Phase 6A's
        pilot finding; see the module docstring and the governing report's
        Sec 4/6). ``window`` is derived from ``ASSAULT_WINDOW`` and the
        match's action budget, not fitted to any outcome."""

        if len(self.progress_ticks) < threshold:
            return False
        return self.progress_ticks[threshold - 1] - self.start_tick <= window

    @property
    def qualified(self) -> bool:
        return any(r.qualifying for r in self.reclaims)

    @property
    def first_qualifying_tick(self) -> int | None:
        for r in self.reclaims:
            if r.qualifying:
                return r.tick
        return None

    def as_dict(
        self, *, names: dict[str, str], threshold: int, window: int, roster: str, cell: str, condition: str
    ) -> dict[str, Any]:
        return {
            "condition": condition,
            "roster": roster,
            "cell": cell,
            "victim_seat": self.victim,
            "victim": names.get(self.victim, self.victim),
            "victim_role": ROLE_OF.get(names.get(self.victim, self.victim), "other"),
            "attacker_seat": self.attacker,
            "attacker": names.get(self.attacker, self.attacker),
            "attacker_role": ROLE_OF.get(names.get(self.attacker, self.attacker), "other"),
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
            "end_reason": self.end_reason,
            "captured_by": names.get(self.captured_by, self.captured_by) if self.captured_by else None,
            "cumulative_cells_taken": len(self.cumulative_cells),
            "meaningful_progress": self.meaningful_progress_windowed(threshold, window),
            "reclaim_count": len(self.reclaims),
            "reclaim_ticks": [r.tick for r in self.reclaims],
            "qualified": self.qualified,
            "first_qualifying_tick": self.first_qualifying_tick,
            "duration_ticks": (self.end_tick - self.start_tick + 1) if self.end_tick is not None else None,
        }


ASSAULT_WINDOW = 16  # core_seeker/core_tracker's own burst-width constant


def max_assault_ticks(action_budget: int, *, assault_window: int = ASSAULT_WINDOW, slack: int = 1) -> int:
    """Mechanically-derived episode-progress window.

    A genuine assault burst is ``assault_window`` consecutive WRITE actions
    (``core_seeker``/``core_tracker``'s own ``ASSAULT_WINDOW``/
    ``ASSAULT_ACTIONS`` constant), which spans at most
    ``ceil(assault_window / action_budget)`` ticks at a given
    ``action_budget`` (``instr_per_tick``), since an attacker cannot exceed
    its own per-tick action quota. One tick of slack is added because a
    burst that starts mid-quota (the attacker had already spent some of that
    tick's actions before locking on) can spill into one additional tick
    beyond the pure ceiling. This is derived from the agents' own published
    burst-width constant, not fitted to any corpus outcome.
    """

    return -(-assault_window // action_budget) + slack


def _anchor(state: Any) -> int:
    pc = state.pc
    if not isinstance(pc, int):
        raise TypeError(f"expected a scalar arena address for pc, got {pc!r}")
    return pc


def reconstruct_episodes(
    records: Iterable[TickSnapshot],
    *,
    arena_size: int,
    threshold: int,
    window: int,
) -> tuple[list[Episode], dict[str, dict[str, Any]]]:
    """Walk a match's tick stream once and return every episode observed.

    ``threshold``/``window`` only affect the final ``qualifying`` pass, not
    reconstruction itself -- every episode and every reclaim is recorded
    regardless, so a caller can re-derive rates at a different threshold or
    window from the same reconstruction (used by the threshold-sensitivity
    and window-sensitivity pilots).

    Returns ``(episodes, per_victim_summary)`` where ``per_victim_summary``
    carries each seat's final alive/captured state, used by callers to
    compute appearance-level (not episode-level) denominators.
    """

    writer: list[str | None] = [None] * arena_size
    windows: dict[str, tuple[int, ...]] = {}
    core_owner_of: dict[int, str] = {}
    open_episodes: dict[tuple[str, str], Episode] = {}
    closed_episodes: list[Episode] = []
    alive: dict[str, bool] = {}
    captured_tick: dict[str, int] = {}
    captured_by: dict[str, str | None] = {}
    # Independent capture attribution, derived purely from this module's own
    # ownership bookkeeping rather than reused from the engine's kill/death
    # events -- Phase 6N's auditability equivalence check compares this
    # against ``captured_by`` (which *is* sourced from the engine events).
    # Mirrors ``_attribute_core_capture``'s own rule: the write that brings a
    # victim's self-owned core-cell count from one to zero is the killer.
    owned_count: dict[str, int] = {}
    derived_killer: dict[str, str | None] = {}

    def _close(ep: Episode, *, tick: int, reason: str, captor: str | None = None) -> None:
        ep.end_tick = tick
        ep.end_reason = reason
        ep.captured_by = captor
        closed_episodes.append(ep)
        del open_episodes[(ep.victim, ep.attacker)]

    def _open_or_extend(victim: str, attacker: str, address: int, tick: int) -> None:
        key = (victim, attacker)
        ep = open_episodes.get(key)
        if ep is None:
            ep = Episode(victim=victim, attacker=attacker, start_tick=tick)
            open_episodes[key] = ep
        ep.cells_taken.add(address)
        if address not in ep.cumulative_cells:
            ep.cumulative_cells.add(address)
            ep.progress_ticks.append(tick)

    def _third_party_take(victim: str, holder: str, address: int, tick: int) -> None:
        """A cell held by ``holder`` as part of an open (victim, holder)
        episode changed owner to a third entrant. No reclaim event -- the
        victim did not act -- but the episode loses continuity over this
        cell and closes if that was its last one."""

        key = (victim, holder)
        ep = open_episodes.get(key)
        if ep is None or address not in ep.cells_taken:
            return
        ep.cells_taken.discard(address)
        if not ep.cells_taken:
            _close(ep, tick=tick, reason="third_party_takeover")

    def _reclaim(victim: str, attacker: str, address: int, tick: int) -> None:
        """The victim wrote back a cell held by ``attacker``. Closes the
        episode if that was the attacker's last held cell. The caller
        captures the episode reference *before* calling this (see the main
        loop), because this call may remove the episode from
        ``open_episodes`` entirely."""

        key = (victim, attacker)
        ep = open_episodes.get(key)
        if ep is None or address not in ep.cells_taken:
            return
        ep.cells_taken.discard(address)
        if not ep.cells_taken:
            _close(ep, tick=tick, reason="reclaimed_all")

    for record in records:
        if not isinstance(record, TickSnapshot):
            continue
        tick = record.tick

        if tick == 0:
            for state in record.agents:
                seat = state.agent_id
                core_window = tuple((_anchor(state) + off) % arena_size for off in range(CORE_SIZE))
                windows[seat] = core_window
                alive[seat] = True
                owned_count[seat] = 0
                derived_killer[seat] = None
                for address in core_window:
                    if address in core_owner_of:
                        raise ValueError(f"overlapping cores at {address} -- disjoint-core assumption violated")
                    core_owner_of[address] = seat

        # Episode references captured at the moment of reclaim, keyed by
        # (victim, attacker); safe to key by pair alone within one tick
        # because sequential-quota scheduling gives each entrant exactly one
        # contiguous action block per tick, so a given (victim, attacker)
        # pair cannot close and reopen an episode within the same tick --
        # closing one requires the victim's block, reopening requires the
        # same attacker's block, and each entrant acts at most once per tick.
        reclaim_refs: dict[tuple[str, str], Episode] = {}
        reclaim_cells: dict[tuple[str, str], list[int]] = defaultdict(list)

        for diff in record.memory_diffs:
            for offset in range(diff.length):
                address = (diff.address + offset) % arena_size
                previous = writer[address]
                new_owner = diff.owner
                victim_home = core_owner_of.get(address)
                if victim_home is not None and new_owner != previous:
                    if new_owner == victim_home:
                        if previous != victim_home:
                            owned_count[victim_home] = owned_count.get(victim_home, 0) + 1
                        if previous is not None and previous != victim_home:
                            key = (victim_home, previous)
                            ep = open_episodes.get(key)
                            if ep is not None and address in ep.cells_taken:
                                reclaim_refs[key] = ep
                                reclaim_cells[key].append(address)
                            _reclaim(victim_home, previous, address, tick)
                    elif new_owner is not None:
                        if previous == victim_home:
                            owned_count[victim_home] = owned_count.get(victim_home, 0) - 1
                            if owned_count[victim_home] == 0:
                                derived_killer[victim_home] = new_owner
                        if previous is not None and previous != victim_home and previous != new_owner:
                            _third_party_take(victim_home, previous, address, tick)
                        _open_or_extend(victim_home, new_owner, address, tick)
                writer[address] = new_owner

        # One ReclaimEvent per (victim, attacker) per tick, covering every
        # cell reclaimed from that attacker this tick. Progress is measured
        # at the moment of reclaim (cumulative_cells never shrinks, so this
        # equals the episode's full progress-to-date either way).
        for key, ep in reclaim_refs.items():
            ep.reclaims.append(
                ReclaimEvent(
                    tick=tick,
                    cells=tuple(reclaim_cells[key]),
                    cumulative_progress_at_reclaim=len(ep.cumulative_cells),
                    victim_survived_tick=True,  # corrected in the final pass below
                    qualifying=False,
                )
            )

        captured_this_tick = {
            e.victim: e.killer
            for e in record.events
            if isinstance(e, KillDeathEvent) and e.event_type in ("kill", "death")
        }
        for victim, killer in captured_this_tick.items():
            alive[victim] = False
            captured_tick[victim] = tick
            captured_by[victim] = killer
            for (v, a), ep in list(open_episodes.items()):
                if v == victim:
                    _close(ep, tick=tick, reason="captured", captor=killer)

    # A reclaim's survived_tick/qualifying cannot be finalized inline: a
    # capture is only known once every diff *and* event for that tick has
    # been processed, and a reclaim can be recorded before its own tick's
    # capture check resolves. Recompute both in one dedicated pass using the
    # now-complete captured_tick map (a victim's reclaim tick is unsurvived
    # if and only if capture happened on that exact tick).
    all_episodes = closed_episodes + list(open_episodes.values())
    for ep in all_episodes:
        if ep.end_tick is None:
            ep.end_reason = "match_end"
        windowed_ok = ep.meaningful_progress_windowed(threshold, window)
        for r in ep.reclaims:
            captured_at = captured_tick.get(ep.victim)
            r.victim_survived_tick = captured_at != r.tick
            r.qualifying = windowed_ok and r.cumulative_progress_at_reclaim >= threshold and r.victim_survived_tick

    per_victim_summary = {
        seat: {
            "alive_at_end": alive.get(seat, True),
            "captured_tick": captured_tick.get(seat),
            "captured_by": captured_by.get(seat),
            "derived_captured_by": derived_killer.get(seat),
            "attribution_agrees": captured_by.get(seat) == derived_killer.get(seat),
        }
        for seat in windows
    }
    return all_episodes, per_victim_summary


# ---------------------------------------------------------------------------
# Corpus-level analysis
# ---------------------------------------------------------------------------


def _cell_metadata(result_path: Path) -> tuple[dict[str, str], int, int]:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    names = {e["agent_id"]: e["name"] for e in payload["entrants"]}
    repro = payload.get("reproducibility") or {}
    return names, int(repro["arena_size"]), int(repro["action_budget"])


def analyse_cell(result_path: Path, *, threshold: int) -> dict[str, Any]:
    names, arena, action_budget = _cell_metadata(result_path)
    window = max_assault_ticks(action_budget)
    replay_path = result_path.parent / "replay.jsonl"
    episodes, summary = reconstruct_episodes(
        iter_replay(replay_path), arena_size=arena, threshold=threshold, window=window
    )
    roster = result_path.parent.parent.parent.name
    cell = result_path.parent.name
    condition = result_path.parent.parent.parent.parent.parent.name
    return {
        "roster": roster,
        "cell": cell,
        "condition": condition,
        "action_budget": action_budget,
        "window": window,
        "names": names,
        "episodes": [
            ep.as_dict(names=names, threshold=threshold, window=window, roster=roster, cell=cell, condition=condition)
            for ep in episodes
        ],
        "summary": {names.get(seat, seat): v for seat, v in summary.items()},
    }


def _cells_for_condition(condition: str, kind: str, rosters: tuple[str, ...] | None = None) -> list[Path]:
    root = PHASE1 / condition / kind
    if not root.is_dir():
        raise SystemExit(f"missing corpus: {root}")
    paths: list[Path] = []
    roster_dirs = [root / r for r in rosters] if rosters else sorted(root.iterdir())
    for roster_dir in roster_dirs:
        if not roster_dir.is_dir():
            continue
        paths += sorted(roster_dir.glob("matches/*/result.json"))
    return paths


def collect(condition: str, kind: str, *, threshold: int, rosters: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    return [analyse_cell(p, threshold=threshold) for p in _cells_for_condition(condition, kind, rosters)]


# ---------------------------------------------------------------------------
# Pilot: episode-size (cumulative_cells) distribution by attacker role
# ---------------------------------------------------------------------------


def pilot_episode_sizes(rosters: tuple[str, ...] = PILOT_ROSTERS, condition: str = PRIMARY_CONDITION) -> dict[str, Any]:
    """Distribution of cumulative distinct cells taken per episode, by
    attacker role -- measured with threshold=1 (no filtering) so the raw
    shape is visible before any threshold is chosen."""

    cells = collect(condition, "group", threshold=1, rosters=rosters)
    by_role: dict[str, Counter[int]] = defaultdict(Counter)
    reclaimed_by_role: dict[str, Counter[int]] = defaultdict(Counter)
    for cell in cells:
        for ep in cell["episodes"]:
            role = ep["attacker_role"]
            size = ep["cumulative_cells_taken"]
            by_role[role][size] += 1
            if ep["reclaim_count"] > 0:
                reclaimed_by_role[role][size] += 1

    print(f"pilot rosters: {rosters}\ncells analysed: {len(cells)}\n")
    print("episode cumulative-cell-count distribution, by attacker role (all episodes):")
    print(f"{'role':<10s}" + "".join(f"{k:>6d}" for k in range(1, CORE_SIZE + 1)) + "   total")
    for role in ("search", "expansion", "defense"):
        row = by_role[role]
        total = sum(row.values())
        print(f"{role:<10s}" + "".join(f"{row.get(k, 0):>6d}" for k in range(1, CORE_SIZE + 1)) + f"   {total}")
    print("\nsame distribution, restricted to episodes with >=1 victim reclaim:")
    print(f"{'role':<10s}" + "".join(f"{k:>6d}" for k in range(1, CORE_SIZE + 1)) + "   total")
    for role in ("search", "expansion", "defense"):
        row = reclaimed_by_role[role]
        total = sum(row.values())
        print(f"{role:<10s}" + "".join(f"{row.get(k, 0):>6d}" for k in range(1, CORE_SIZE + 1)) + f"   {total}")

    return {
        "rosters": list(rosters),
        "condition": condition,
        "by_role": {r: dict(c) for r, c in by_role.items()},
        "reclaimed_by_role": {r: dict(c) for r, c in reclaimed_by_role.items()},
    }


# ---------------------------------------------------------------------------
# Gate evaluation (post-declaration)
# ---------------------------------------------------------------------------


def _appearances(condition: str, kind: str, rosters: tuple[str, ...] | None = None) -> Counter[str]:
    appearances: Counter[str] = Counter()
    for result_path in _cells_for_condition(condition, kind, rosters):
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        for entrant in payload["entrants"]:
            appearances[entrant["name"]] += 1
    return appearances


def qualify_condition(condition: str, kind: str, *, threshold: int) -> dict[str, Any]:
    cells = collect(condition, kind, threshold=threshold)
    appearances = _appearances(condition, kind)

    all_episodes: list[dict[str, Any]] = [ep for cell in cells for ep in cell["episodes"]]
    opportunities = [ep for ep in all_episodes if ep["meaningful_progress"]]
    qualifying = [ep for ep in opportunities if ep["qualified"]]

    # Opportunity/qualification are per victim-appearance (a cell), not per
    # episode -- an appearance with >=1 opportunity episode is one
    # "opportunity appearance", counted once even if several episodes
    # occurred in that match.
    opp_appearances: dict[str, set[tuple[str, str]]] = defaultdict(set)
    qual_appearances: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for ep in opportunities:
        opp_appearances[ep["victim"]].add((ep["condition"], ep["cell"]))
    for ep in qualifying:
        qual_appearances[ep["victim"]].add((ep["condition"], ep["cell"]))

    by_agent: dict[str, dict[str, Any]] = {}
    for agent, n in sorted(appearances.items()):
        role = ROLE_OF.get(agent, "other")
        n_opp = len(opp_appearances.get(agent, ()))
        n_qual = len(qual_appearances.get(agent, ()))
        by_agent[agent] = {
            "role": role,
            "appearances": n,
            "opportunity_appearances": n_opp,
            "qualifying_appearances": n_qual,
            "raw_rate": n_qual / n if n else None,
            "opportunity_conditioned_rate": (n_qual / n_opp) if n_opp else None,
        }

    search_raw = [v["raw_rate"] for v in by_agent.values() if v["role"] == "search"]
    defense_opp_rate = [
        v["opportunity_conditioned_rate"] for v in by_agent.values() if v["role"] == "defense" and v["opportunity_conditioned_rate"] is not None
    ]
    search_opp_rate = [
        v["opportunity_conditioned_rate"] for v in by_agent.values() if v["role"] == "search" and v["opportunity_conditioned_rate"] is not None
    ]
    expansion_opp_rate = [
        v["opportunity_conditioned_rate"] for v in by_agent.values() if v["role"] == "expansion" and v["opportunity_conditioned_rate"] is not None
    ]

    # Self-farming (Q2): every qualifying episode's attacker must differ from
    # its victim by construction; verified directly rather than assumed.
    self_farm_violations = [ep for ep in qualifying if ep["attacker_seat"] == ep["victim_seat"]]

    # Sweep false positives (Q4): qualifying episodes whose attacker role is
    # not "search" (the only archetypes with a deliberate-assault mechanism
    # per Phase 5's stride analysis).
    non_search_qualifying = [ep for ep in qualifying if ep["attacker_role"] != "search"]

    per_cell_qual: Counter[tuple[str, str]] = Counter()
    for ep in qualifying:
        per_cell_qual[(ep["condition"], ep["cell"], ep["victim"])] += 1
    counts = sorted(per_cell_qual.values())
    median_repeat = statistics.median(counts) if counts else 0
    p95_repeat = sorted(counts)[min(len(counts) - 1, int(0.95 * len(counts)))] if counts else 0

    return {
        "condition": condition,
        "kind": kind,
        "threshold": threshold,
        "cells_analysed": len(cells),
        "total_episodes": len(all_episodes),
        "opportunity_episodes": len(opportunities),
        "qualifying_episodes": len(qualifying),
        "by_agent": by_agent,
        "max_search_raw_rate": max(search_raw, default=0.0),
        "min_defense_opportunity_rate": min(defense_opp_rate, default=None),
        "max_search_opportunity_rate": max(search_opp_rate, default=0.0),
        "max_expansion_opportunity_rate": max(expansion_opp_rate, default=0.0),
        "self_farm_violations": len(self_farm_violations),
        "non_search_qualifying_share": (len(non_search_qualifying) / len(qualifying)) if qualifying else None,
        "median_qualifying_per_appearance": median_repeat,
        "p95_qualifying_per_appearance": p95_repeat,
        "max_qualifying_per_appearance": max(counts, default=0),
    }


def digest_episodes(cells: list[dict[str, Any]]) -> str:
    """Stable digest over every qualifying episode's identifying fields, for
    the Q6-equivalent determinism check: two independent reconstruction
    passes over the same committed replays must agree bit-for-bit."""

    payload = []
    for cell in cells:
        for ep in sorted(cell["episodes"], key=lambda e: (e["cell"], e["victim_seat"], e["attacker_seat"], e["start_tick"])):
            payload.append(
                (
                    ep["cell"],
                    ep["victim_seat"],
                    ep["attacker_seat"],
                    ep["start_tick"],
                    ep["end_tick"],
                    ep["end_reason"],
                    ep["cumulative_cells_taken"],
                    tuple(ep["reclaim_ticks"]),
                    ep["qualified"],
                )
            )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pilot = sub.add_parser("pilot")
    p_pilot.add_argument("--condition", default=PRIMARY_CONDITION)

    p_qual = sub.add_parser("qualify")
    p_qual.add_argument("--condition", default=PRIMARY_CONDITION)
    p_qual.add_argument("--all", action="store_true")

    p_det = sub.add_parser("determinism")
    p_det.add_argument("--condition", default=PRIMARY_CONDITION)

    args = parser.parse_args(argv)

    if args.cmd == "pilot":
        result = pilot_episode_sizes(condition=args.condition)
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        (OUTPUT_ROOT / "phase6_pilot_episode_sizes.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0

    if args.cmd == "determinism":
        gates = json.loads(GATES_PATH.read_text(encoding="utf-8"))
        threshold = gates["event_definition"]["episode_threshold"]
        pass1 = collect(args.condition, "group", threshold=threshold)
        pass2 = collect(args.condition, "group", threshold=threshold)
        d1, d2 = digest_episodes(pass1), digest_episodes(pass2)
        print(f"pass 1 digest: {d1}\npass 2 digest: {d2}\nidentical: {d1 == d2}")
        return 0 if d1 == d2 else 1

    # qualify
    gates = json.loads(GATES_PATH.read_text(encoding="utf-8"))
    threshold = gates["event_definition"]["episode_threshold"]
    report: dict[str, Any] = {"gates_declared_at": str(GATES_PATH.relative_to(REPO)), "threshold": threshold, "conditions": {}}
    conditions = list(BUDGET_CONDITIONS) if args.all else [args.condition]
    for condition in conditions:
        result = qualify_condition(condition, "group", threshold=threshold)
        report["conditions"][condition] = result
        print(f"\n=== {condition} (group, threshold={threshold}) ===")
        print(f"episodes: {result['total_episodes']}  opportunities: {result['opportunity_episodes']}  qualifying: {result['qualifying_episodes']}")
        print(f"{'agent':<24s}{'role':>10s}{'appear':>8s}{'opp':>6s}{'qual':>6s}{'raw%':>8s}{'opp%':>8s}")
        for agent, v in result["by_agent"].items():
            print(
                f"{agent:<24s}{v['role']:>10s}{v['appearances']:>8d}{v['opportunity_appearances']:>6d}"
                f"{v['qualifying_appearances']:>6d}{100*(v['raw_rate'] or 0):>7.1f}%"
                f"{100*(v['opportunity_conditioned_rate'] or 0):>7.1f}%"
            )
        if args.all:
            report["conditions"][f"{condition}:pairwise"] = qualify_condition(condition, "pairwise", threshold=threshold)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT_ROOT / "phase6_qualification.json"
    destination.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
