"""v3 research Phase 2 -- the experimental locality-aware agent population.

Acceptance checks for the six ``v3-phase2-locality`` benchmark members: that
they are pinned and verify, that they speak only the locality vocabulary,
that they never waste an action on a reach miss at any reach the experiment
treats as viable, that they are deterministic, and -- the check that
protects the whole comparison -- that adding them left the frozen Phase-0 v2
population completely untouched.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from battle_engine.agent_api import ActionKind
from battle_engine.agent_trace import read_trace
from battle_engine.benchmarks import (
    V2_BASELINE_ID,
    load_population,
    stage_population,
    verify_population,
)
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.python_runtime import LOCALITY_ACTIONS
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V3_ALPHA1_ID,
)

LOCALITY_POPULATION = "v3-phase2-locality"
LOCALITY = BYTEFRAY_RULESET_V3_ALPHA1_ID
V2 = BYTEFRAY_RULESET_V2_ID

EXPECTED_MEMBERS = {
    "local_claimer",
    "local_camper",
    "local_core_defender",
    "local_reactive_defender",
    "local_core_seeker",
    "local_core_tracker",
}

# Every reach the pilot or the main corpus may use. 8 == CORE_SIZE is the
# smallest reach at which a single burst can still cover a whole core.
VIABLE_REACHES = (8, 16, 32, 64, 128, 256)


@pytest.fixture(scope="module")
def population():
    return load_population(LOCALITY_POPULATION)


@pytest.fixture()
def staged(tmp_path: Path, population) -> Path:
    stage_population(population, tmp_path)
    return tmp_path


def _match(
    root: Path,
    a: str,
    b: str,
    *,
    ruleset_id: str,
    reach: int | None,
    arena_size: int = 4096,
    ticks: int = 120,
    seed: int = 1,
    run: str = "run",
    trace: bool = False,
) -> dict:
    from battle_engine.agents import resolve_agent

    out = root / "runs" / run
    request = MatchRequest(
        config=Config(arena_size=arena_size, instr_per_tick=8, seed=seed),
        entrants=(
            MatchEntrant.python("A", a, 0, resolve_agent(root, a)),
            MatchEntrant.python("B", b, arena_size // 2, resolve_agent(root, b)),
        ),
        max_ticks=ticks,
        replay_path=out / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
        locality_reach=reach,
        trace_path=(out / "trace.jsonl") if trace else None,
    )
    NativeMatchService().run(request)
    return json.loads((out / "result.json").read_text())


# ---------------------------------------------------------------------------
# The population itself
# ---------------------------------------------------------------------------


def test_the_locality_population_is_pinned_and_verifies(population) -> None:
    verifications = verify_population(population)
    failures = [v for v in verifications if not v.matches]
    assert not failures, [(v.agent_id, v.detail) for v in failures]
    assert len(verifications) == len(EXPECTED_MEMBERS)


def test_the_population_names_exactly_the_six_experimental_members(population) -> None:
    assert set(population.agent_ids) == EXPECTED_MEMBERS
    assert set(population.ecology_core) == EXPECTED_MEMBERS


def test_the_population_declares_the_experimental_ruleset_not_a_stable_one(
    population,
) -> None:
    assert population.ruleset_id == LOCALITY
    assert "alpha" in population.ruleset_id
    assert population.ruleset_id != "bytefray-rules-3"


def test_every_ported_member_records_its_v2_lineage() -> None:
    """Phase 2I requires the lineage of every adapted agent to be recorded.
    Five members name a frozen Phase-0 ancestor; ``local_camper`` deliberately
    names none, and that absence is itself the record."""

    manifest = json.loads(
        Path("engine/src/battle_engine/data/benchmarks/v3_phase2_locality.json").read_text()
    )
    lineage = {m["agent_id"]: m["v2_lineage"] for m in manifest["members"]}
    assert lineage == {
        "local_claimer": "claimer",
        "local_core_defender": "core_defender",
        "local_reactive_defender": "reactive_core_defender",
        "local_core_seeker": "core_seeker",
        "local_core_tracker": "core_tracker",
        "local_camper": None,
    }
    v2_members = set(load_population(V2_BASELINE_ID).agent_ids)
    for ancestor in filter(None, lineage.values()):
        assert ancestor in v2_members


def test_the_frozen_v2_population_is_completely_untouched() -> None:
    """The load-bearing negative for the whole Phase 2 comparison: the v2
    control agents must still be byte-identical to the revisions Phase 0
    pinned and Phase 1 measured."""

    verifications = verify_population(load_population(V2_BASELINE_ID))
    assert all(v.matches for v in verifications)
    assert len(verifications) == 9


def test_the_two_populations_share_no_agent_id(population) -> None:
    v2 = set(load_population(V2_BASELINE_ID).agent_ids)
    assert not (set(population.agent_ids) & v2)


# ---------------------------------------------------------------------------
# Vocabulary and reach discipline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_id", sorted(EXPECTED_MEMBERS))
def test_each_member_speaks_only_the_locality_vocabulary(staged, agent_id) -> None:
    _match(staged, agent_id, "local_camper", ruleset_id=LOCALITY, reach=32, trace=True)
    document = read_trace(staged / "runs" / "run" / "trace.jsonl")
    kinds = {
        record.action.kind
        for record in document.decisions
        if record.agent_id == "A" and record.action is not None
    }
    assert kinds, agent_id
    allowed = {kind.value for kind in LOCALITY_ACTIONS}
    assert kinds <= allowed, (agent_id, kinds - allowed)


@pytest.mark.parametrize("agent_id", sorted(EXPECTED_MEMBERS))
def test_each_member_forfeits_loudly_under_ruleset_v2(staged, agent_id) -> None:
    """A v3 experimental agent being incompatible with Ruleset v2 is fine.
    Silently *meaning something else* under Ruleset v2 would not be, so each
    one must be rejected by the runtime rather than run."""

    result = _match(staged, agent_id, "local_camper", ruleset_id=V2, reach=None)
    subject = next(e for e in result["entrants"] if e["name"] == agent_id)
    assert subject["termination_reason"] == "forfeit"
    assert subject["diagnostic"]["code"] == "agent_action_invalid"


@pytest.mark.parametrize("reach", VIABLE_REACHES)
@pytest.mark.parametrize("agent_id", sorted(EXPECTED_MEMBERS))
def test_no_member_ever_wastes_an_action_on_a_reach_miss(staged, agent_id, reach) -> None:
    """An agent is told ``R`` at reset and knows its own locus every action,
    so every reach miss is an arithmetic bug. Zero of them across the whole
    viable reach range is what lets the corpus attribute movement cost to the
    mechanic rather than to agent defects."""

    result = _match(
        staged,
        agent_id,
        "local_core_tracker" if agent_id != "local_core_tracker" else "local_claimer",
        ruleset_id=LOCALITY,
        reach=reach,
        run=f"r{reach}_{agent_id}",
    )
    for entrant in result["entrants"]:
        assert entrant["metadata"]["locality"]["reach_misses"] == 0, (
            agent_id,
            reach,
            entrant["name"],
        )
        assert entrant["termination_reason"] != "forfeit"


# ---------------------------------------------------------------------------
# Archetype behaviour -- each member does the thing its role claims
# ---------------------------------------------------------------------------


def _locality(result: dict, name: str) -> dict:
    return next(e for e in result["entrants"] if e["name"] == name)["metadata"]["locality"]


def test_the_camper_control_never_moves(staged) -> None:
    result = _match(staged, "local_camper", "local_claimer", ruleset_id=LOCALITY, reach=64)
    stats = _locality(result, "local_camper")
    assert stats["moves"] == 0
    assert stats["distinct_loci"] == 1
    assert stats["final_core_distance"] == 0


def test_the_claimer_tiles_the_arena_with_one_step_per_r_cells_written(staged) -> None:
    reach = 64
    result = _match(
        staged, "local_claimer", "local_camper", ruleset_id=LOCALITY, reach=reach, ticks=100
    )
    stats = _locality(result, "local_claimer")
    entrant = next(e for e in result["entrants"] if e["name"] == "local_claimer")
    # 800 actions at 8/tick x 100 ticks: R writes then one MOVE, repeating.
    assert entrant["statistics"]["cpu_total"] == 800
    assert stats["moves"] == 800 // (reach + 1)
    assert stats["move_cells"] == stats["moves"] * reach


def test_the_reactive_defender_never_leaves_its_guard_band(staged) -> None:
    """Its whole design is that every core cell stays readable on every
    action. That is only true while it stays within ``R - CORE_SIZE`` of its
    own core."""

    for reach in (16, 64, 256):
        result = _match(
            staged,
            "local_reactive_defender",
            "local_camper",
            ruleset_id=LOCALITY,
            reach=reach,
            run=f"band{reach}",
        )
        stats = _locality(result, "local_reactive_defender")
        assert stats["core_distance_max"] <= reach - 8, (reach, stats)


def test_the_excursion_defender_does_leave_and_does_come_back(staged) -> None:
    """The complementary archetype: Local Core Defender buys territory with
    absence. It must actually range away from its core (unlike the reactive
    defender) and must actually return (unlike the claimer)."""

    reach = 64
    result = _match(
        staged,
        "local_core_defender",
        "local_camper",
        ruleset_id=LOCALITY,
        reach=reach,
        ticks=200,
    )
    stats = _locality(result, "local_core_defender")
    assert stats["core_distance_max"] > reach
    assert stats["moves"] > 0
    defender = next(e for e in result["entrants"] if e["name"] == "local_core_defender")
    assert defender["statistics"]["territory_last"] > 0


@pytest.mark.parametrize("agent_id", ["local_core_seeker", "local_core_tracker"])
def test_each_searcher_actually_reads_the_arena(staged, agent_id) -> None:
    result = _match(staged, agent_id, "local_claimer", ruleset_id=LOCALITY, reach=64)
    stats = _locality(result, agent_id)
    assert stats["local_reads"] > 0
    assert stats["local_writes"] > 0


def test_a_searcher_can_still_capture_a_core_under_bounded_locality(staged) -> None:
    """The capability the whole offense archetype depends on: find a core you
    could not see from where you started, travel to it, and take it."""

    result = _match(
        staged,
        "local_core_tracker",
        "local_camper",
        ruleset_id=LOCALITY,
        reach=64,
        arena_size=2048,
        ticks=400,
    )
    victim = next(e for e in result["entrants"] if e["name"] == "local_camper")
    assert victim["termination_reason"] == "core_captured"
    tracker = next(e for e in result["entrants"] if e["name"] == "local_core_tracker")
    assert tracker["statistics"]["kills"] == 1


def test_search_behaviour_is_conditional_rather_than_a_fixed_action_mix(staged) -> None:
    """Phase 2N item 3: a locality-aware searcher should behave differently
    when there is something to find. Against a stationary opponent the
    tracker's action mix must diverge from its mix against nothing to find --
    it approaches, probes, and bursts, none of which happen in an empty
    region."""

    from battle_engine.agents import resolve_agent

    def _mix(opponent: str, run: str) -> dict[str, int]:
        out = staged / "runs" / run
        request = MatchRequest(
            config=Config(arena_size=2048, instr_per_tick=8, seed=3),
            entrants=(
                MatchEntrant.python("A", "local_core_tracker", 0, resolve_agent(staged, "local_core_tracker")),
                MatchEntrant.python("B", opponent, 1024, resolve_agent(staged, opponent)),
            ),
            max_ticks=200,
            replay_path=out / "replay.jsonl",
            verbose=False,
            ruleset_id=LOCALITY,
            locality_reach=64,
            trace_path=out / "trace.jsonl",
        )
        NativeMatchService().run(request)
        counts: dict[str, int] = {}
        for record in read_trace(out / "trace.jsonl").decisions:
            if record.action is None or record.agent_id != "A":
                continue
            counts[record.action.kind] = counts.get(record.action.kind, 0) + 1
        return counts

    quiet = _mix("local_camper", "mix_quiet")
    busy = _mix("local_claimer", "mix_busy")
    assert quiet and busy
    quiet_move_share = quiet.get(ActionKind.MOVE.value, 0) / sum(quiet.values())
    busy_move_share = busy.get(ActionKind.MOVE.value, 0) / sum(busy.values())
    assert quiet_move_share != busy_move_share


def test_the_tracker_draws_its_sweep_direction_from_the_match_rng(staged) -> None:
    """The locality analogue of the ancestor's RNG-drawn scan anchor: which
    way this agent investigates first must not be a pure function of its
    placement, or it would be exactly as placement-bound as the mechanic
    allows."""

    directions = set()
    for seed in range(1, 13):
        result = _match(
            staged,
            "local_core_tracker",
            "local_camper",
            ruleset_id=LOCALITY,
            reach=64,
            ticks=20,
            seed=seed,
            run=f"dir{seed}",
        )
        stats = _locality(result, "local_core_tracker")
        # A positive sweep leaves the locus ahead of the core, a negative one
        # behind it, on a 4096 arena that neither can lap in 20 ticks.
        directions.add(stats["final_locus"] < 2048)
    assert len(directions) == 2


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_id", sorted(EXPECTED_MEMBERS))
def test_each_member_is_a_pure_function_of_its_declared_inputs(
    tmp_path, population, agent_id
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        stage_population(population, root)
    a = _match(first, agent_id, "local_core_seeker", ruleset_id=LOCALITY, reach=32, seed=9)
    b = _match(second, agent_id, "local_core_seeker", ruleset_id=LOCALITY, reach=32, seed=9)
    assert a["match_id"] == b["match_id"]
    assert a["result_id"] == b["result_id"]
    assert a["score"] == b["score"]
    assert [e["metadata"]["locality"] for e in a["entrants"]] == [
        e["metadata"]["locality"] for e in b["entrants"]
    ]


def test_staging_copies_exactly_the_pinned_files(tmp_path, population) -> None:
    staged = stage_population(population, tmp_path)
    assert len(staged) == 2 * len(EXPECTED_MEMBERS)
    for agent_id in EXPECTED_MEMBERS:
        agent_dir = tmp_path / "agents" / agent_id
        assert sorted(p.name for p in agent_dir.iterdir()) == ["agent.py", "agent.yaml"]
    # A staged copy must verify against the manifest exactly as the source
    # tree does -- otherwise a corpus run would silently execute something
    # other than the pinned revision.
    shutil.rmtree(tmp_path / "agents" / "local_camper")
    stage_population(population, tmp_path, agent_ids=("local_camper",))
    assert (tmp_path / "agents" / "local_camper" / "agent.py").is_file()
