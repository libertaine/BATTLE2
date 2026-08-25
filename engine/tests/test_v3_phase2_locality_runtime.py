"""``bytefray-rules-3-alpha1`` -- v3 research Phase 2 bounded-locality tests.

Covers the Phase 2V checklist from the governing task: circular geometry,
reach enforcement across the arena wrap, movement, action accounting, core
behavior, Ruleset isolation in both directions, artifact identity, and
determinism (repeat / serial-vs-parallel / resume).

The governing discipline every test here exists to protect is that the
experimental Ruleset is *additive and isolated*: it must be impossible to
reach locality semantics from a Ruleset-v1/v2 request, impossible to reach
absolute addressing from a locality request, and impossible for either to
change the other's artifacts by a single byte. See
``docs/V3_PHASE2_LOCALITY_FEASIBILITY.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation
from battle_engine.config import Config
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    OverlappingCoreError,
    canonical_match_id,
)
from battle_engine.python_runtime import (
    CORE_BEACON_BYTE,
    CORE_SIZE,
    DEFAULT_LOCALITY_REACH,
    InvalidPythonActionError,
    PythonEntrantState,
    apply_action,
    circular_displacement,
    circular_distance,
    core_addresses,
    has_bounded_locality,
    validate_action,
)
from battle_engine.replay import TickSnapshot, iter_replay
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V3_ALPHA1_ID,
    resolve_ruleset_policy,
)
from battle_engine.vm import VM

LOCALITY = BYTEFRAY_RULESET_V3_ALPHA1_ID
V2 = BYTEFRAY_RULESET_V2_ID


# ---------------------------------------------------------------------------
# Fixtures: scripted agents, written as source strings so each scenario's
# exact action sequence is knowable in advance (the same pattern
# test_ruleset_v2_alpha1.py established).
# ---------------------------------------------------------------------------


def _write_agent(agent_dir: Path, agent_id: str, source: str) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": "python",
        "api_version": 1,
        "entrypoint": "agent.py:create_agent",
        "name": agent_id,
        "display": agent_id.title(),
        "version": "1.0",
    }
    agent_dir.joinpath("agent.yaml").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    agent_dir.joinpath("agent.py").write_text(source, encoding="utf-8")


def _entrant(root: Path, agent_id: str, source: str, *, slot: str, start: int) -> MatchEntrant:
    from battle_engine.agents import resolve_agent

    _write_agent(root / "agents" / agent_id, agent_id, source)
    return MatchEntrant.python(slot, agent_id, start, resolve_agent(root, agent_id))


NOP_SOURCE = """from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _scripted_source(actions: str) -> str:
    """An agent replaying a literal list of ``(kind, operand, value)`` tuples."""

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        f"ACTIONS = {actions}\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.index = 0\n"
        "        self.reach = context.locality_reach\n"
        "        self.arena_size = context.arena_size\n\n"
        "    def act(self, observation):\n"
        "        if self.index >= len(ACTIONS):\n"
        "            return AgentAction(ActionKind.NOP)\n"
        "        kind, operand, value = ACTIONS[self.index]\n"
        "        self.index += 1\n"
        "        if value is None:\n"
        "            return AgentAction(ActionKind(kind), operand)\n"
        "        return AgentAction(ActionKind(kind), operand, value)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    )


LOCAL_SWEEPER_SOURCE = """from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.reach = context.locality_reach
        self.offset = 0

    def act(self, observation):
        if self.offset >= self.reach:
            self.offset = 0
            return AgentAction(ActionKind.MOVE, self.reach)
        offset = self.offset
        self.offset += 1
        return AgentAction(ActionKind.LOCAL_WRITE, offset, 0x77)

def create_agent():
    return Agent()
"""


def _request(
    tmp_path: Path,
    entrants: tuple[MatchEntrant, ...],
    *,
    ruleset_id: str,
    locality_reach: int | None = None,
    arena_size: int = 512,
    instr_per_tick: int = 4,
    max_ticks: int = 20,
    seed: int = 1337,
    run_dir: str = "run",
) -> MatchRequest:
    return MatchRequest(
        Config(arena_size=arena_size, instr_per_tick=instr_per_tick, seed=seed),
        entrants,
        max_ticks=max_ticks,
        replay_path=tmp_path / run_dir / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
        locality_reach=locality_reach,
    )


def _result_json(request: MatchRequest) -> dict:
    return json.loads(request.replay_path.with_name("result.json").read_text())


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "arena", "expected"),
    [
        (0, 0, 256, 0),
        (0, 5, 256, 5),
        (5, 0, 256, 5),
        (0, 128, 256, 128),
        # The arena wraps: 3 and 253 are six cells apart the short way, not 250.
        (3, 253, 256, 6),
        (253, 3, 256, 6),
        (255, 0, 256, 1),
    ],
)
def test_circular_distance_is_the_short_way_around(a, b, arena, expected) -> None:
    assert circular_distance(a, b, arena) == expected


@pytest.mark.parametrize(
    ("displacement", "arena", "expected"),
    [
        (0, 256, 0),
        (5, 256, 5),
        (-5, 256, 5),
        (128, 256, 128),
        (129, 256, 127),
        (-129, 256, 127),
        # +arena_size - 1 and -1 name the identical one-cell step.
        (255, 256, 1),
        (512, 256, 0),
    ],
)
def test_circular_displacement_normalizes_both_sign_conventions(
    displacement, arena, expected
) -> None:
    assert circular_displacement(displacement, arena) == expected


def _bare_state(locus: int) -> PythonEntrantState:
    import random
    from types import SimpleNamespace

    loaded = SimpleNamespace(
        metadata=SimpleNamespace(api_version=1, version="0"), entry_point="x"
    )
    return PythonEntrantState(
        agent_id="a",
        name="a",
        loaded=loaded,  # type: ignore[arg-type]
        rng=random.Random(0),
        core_start=locus,
        locus=locus,
    )


def test_local_write_in_range_lands_at_locus_plus_displacement() -> None:
    vm = VM(256)
    state = _bare_state(100)
    apply_action(AgentAction(ActionKind.LOCAL_WRITE, 8, 0x42), state, vm, locality_reach=16)
    assert vm.arena[108] == 0x42
    assert vm.writer[108] == "a"
    assert state.locality_local_writes == 1
    assert state.locality_reach_misses == 0
    assert state.mem_writes == 1


def test_local_write_out_of_range_is_a_no_op_that_still_cost_its_action() -> None:
    vm = VM(256)
    state = _bare_state(100)
    apply_action(AgentAction(ActionKind.LOCAL_WRITE, 17, 0x42), state, vm, locality_reach=16)
    assert vm.arena[117] == 0  # untouched
    assert vm.writer[117] is None
    assert state.locality_reach_misses == 1
    assert state.locality_local_writes == 0
    assert state.mem_writes == 0
    # Nothing agent-visible changed either -- a reach miss can never be
    # mistaken for a successful read/write of an empty cell.
    assert state.last_read is None


def test_local_read_in_range_updates_register_and_flag() -> None:
    vm = VM(256)
    vm._wr8(95, 0xCE, "other")
    state = _bare_state(100)
    apply_action(AgentAction(ActionKind.LOCAL_READ, -5), state, vm, locality_reach=16)
    assert state.last_read == 0xCE
    assert state.register_a == 0xCE
    assert state.zero_flag is False
    assert state.locality_local_reads == 1


def test_local_read_out_of_range_leaves_every_agent_visible_field_untouched() -> None:
    vm = VM(256)
    state = _bare_state(100)
    state.last_read = 0x11
    state.register_a = 0x11
    apply_action(AgentAction(ActionKind.LOCAL_READ, -20), state, vm, locality_reach=16)
    assert state.last_read == 0x11
    assert state.register_a == 0x11
    assert state.locality_reach_misses == 1
    assert state.locality_local_reads == 0


def test_reach_is_measured_across_the_arena_wrap_not_linearly() -> None:
    """An entrant at address 2 reaches address 254 in a 256-cell arena: the
    two are four cells apart the short way. A linear ``abs(a - b)`` would
    call that 252 and refuse."""

    vm = VM(256)
    state = _bare_state(2)
    apply_action(AgentAction(ActionKind.LOCAL_WRITE, -4, 0x42), state, vm, locality_reach=8)
    assert vm.arena[254] == 0x42
    assert state.locality_reach_misses == 0


def test_move_wraps_the_arena_and_records_distance_travelled() -> None:
    vm = VM(256)
    state = _bare_state(2)
    apply_action(AgentAction(ActionKind.MOVE, -8), state, vm, locality_reach=8)
    assert state.locus == 250
    assert state.locality_moves == 1
    assert state.locality_move_cells == 8
    assert state.locality_visited == {2, 250}


def test_move_beyond_reach_does_not_move_and_costs_its_action() -> None:
    vm = VM(256)
    state = _bare_state(100)
    apply_action(AgentAction(ActionKind.MOVE, 9), state, vm, locality_reach=8)
    assert state.locus == 100
    assert state.locality_moves == 0
    assert state.locality_reach_misses == 1


def test_a_zero_cell_move_is_legal_and_travels_nothing() -> None:
    vm = VM(256)
    state = _bare_state(100)
    apply_action(AgentAction(ActionKind.MOVE, 0), state, vm, locality_reach=8)
    assert state.locus == 100
    assert state.locality_moves == 1
    assert state.locality_move_cells == 0
    assert state.locality_reach_misses == 0


def test_the_reachable_window_is_exactly_two_r_plus_one_cells() -> None:
    reach = 6
    vm = VM(256)
    for displacement in range(-reach - 2, reach + 3):
        state = _bare_state(100)
        apply_action(
            AgentAction(ActionKind.LOCAL_WRITE, displacement, 0x42),
            state,
            vm,
            locality_reach=reach,
        )
        expected_hit = abs(displacement) <= reach
        assert (state.locality_reach_misses == 0) is expected_hit, displacement
    owned = sum(1 for owner in vm.writer if owner == "a")
    assert owned == 2 * reach + 1


# ---------------------------------------------------------------------------
# Ruleset isolation -- the vocabularies are disjoint, in both directions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action",
    [
        AgentAction(ActionKind.MOVE, 1),
        AgentAction(ActionKind.LOCAL_READ, 1),
        AgentAction(ActionKind.LOCAL_WRITE, 1, 0x42),
    ],
)
def test_locality_actions_are_invalid_under_absolute_addressing(action) -> None:
    with pytest.raises(InvalidPythonActionError):
        validate_action(action)


@pytest.mark.parametrize(
    "action",
    [
        AgentAction(ActionKind.READ, 100),
        AgentAction(ActionKind.WRITE, 100, 0x42),
    ],
)
def test_absolute_actions_are_invalid_under_bounded_locality(action) -> None:
    with pytest.raises(InvalidPythonActionError, match="bounded-locality"):
        validate_action(action, locality=True)


@pytest.mark.parametrize(
    "action",
    [
        AgentAction(ActionKind.NOP),
        AgentAction(ActionKind.HALT),
        AgentAction(ActionKind.SET_A, 5),
        AgentAction(ActionKind.ADD_A, 5),
        AgentAction(ActionKind.SET_P, 5),
        AgentAction(ActionKind.ADD_P, 5),
        AgentAction(ActionKind.JUMP, 5),
        AgentAction(ActionKind.JUMP_IF_ZERO, 5),
    ],
)
def test_every_non_addressing_action_is_identical_under_both_vocabularies(action) -> None:
    assert validate_action(action) == action
    assert validate_action(action, locality=True) == action


def test_local_write_requires_both_a_displacement_and_a_value() -> None:
    with pytest.raises(InvalidPythonActionError):
        validate_action(AgentAction(ActionKind.LOCAL_WRITE, 1), locality=True)
    with pytest.raises(InvalidPythonActionError):
        validate_action(AgentAction(ActionKind.LOCAL_WRITE, None, 5), locality=True)


def test_move_and_local_read_reject_a_second_operand() -> None:
    with pytest.raises(InvalidPythonActionError):
        validate_action(AgentAction(ActionKind.MOVE, 1, 2), locality=True)
    with pytest.raises(InvalidPythonActionError):
        validate_action(AgentAction(ActionKind.LOCAL_READ, 1, 2), locality=True)


def test_only_the_experimental_identity_carries_bounded_locality() -> None:
    assert has_bounded_locality(LOCALITY)
    for other in (BYTEFRAY_RULESET_ID, V2, "bytefray-rules-2-alpha1", "bytefray-rules-2-alpha11"):
        assert not has_bounded_locality(other)


def test_the_experimental_identity_resolves_and_is_python_only() -> None:
    policy = resolve_ruleset_policy(LOCALITY)
    assert policy.ruleset_id == LOCALITY
    assert policy.unsupported_runtime_kinds(["python"]) == frozenset()
    assert policy.unsupported_runtime_kinds(["vm"]) == frozenset({"vm"})


def test_a_v2_agent_forfeits_loudly_under_locality_rather_than_meaning_something_else(
    tmp_path,
) -> None:
    """A Ruleset-v2 agent emits absolute ``WRITE``. Under locality that is
    rejected as an invalid action, so the agent forfeits visibly instead of
    silently having its addresses reinterpreted as displacements."""

    absolute_writer = _scripted_source("[('write', 300, 0x42)]")
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "absolute", absolute_writer, slot="A", start=0),
            _entrant(tmp_path, "quiet", NOP_SOURCE, slot="B", start=256),
        ),
        ruleset_id=LOCALITY,
        locality_reach=16,
    )
    NativeMatchService().run(request)
    entrants = {e["name"]: e for e in _result_json(request)["entrants"]}
    assert entrants["absolute"]["termination_reason"] == "forfeit"
    assert entrants["absolute"]["diagnostic"]["code"] == "agent_action_invalid"


def test_a_locality_agent_forfeits_loudly_under_ruleset_v2(tmp_path) -> None:
    local_writer = _scripted_source("[('local_write', 1, 0x42)]")
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "local", local_writer, slot="A", start=0),
            _entrant(tmp_path, "quiet", NOP_SOURCE, slot="B", start=256),
        ),
        ruleset_id=V2,
    )
    NativeMatchService().run(request)
    entrants = {e["name"]: e for e in _result_json(request)["entrants"]}
    assert entrants["local"]["termination_reason"] == "forfeit"
    assert entrants["local"]["diagnostic"]["code"] == "agent_action_invalid"


# ---------------------------------------------------------------------------
# Ruleset-v1/v2 artifacts are untouched
# ---------------------------------------------------------------------------


def test_a_ruleset_v2_match_carries_no_locality_field_anywhere(tmp_path) -> None:
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=0),
            _entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=256),
        ),
        ruleset_id=V2,
    )
    NativeMatchService().run(request)
    result = _result_json(request)
    assert "locality_reach" not in result["reproducibility"]
    for entrant in result["entrants"]:
        assert "locality" not in entrant["metadata"]
    assert "locus" not in request.replay_path.read_text()


def test_a_stray_reach_on_a_non_locality_request_is_completely_inert(tmp_path) -> None:
    """Setting ``locality_reach`` without the locality Ruleset must not switch
    on locality semantics, must not appear in any artifact, and must not
    change identity -- otherwise a misconfigured research run could silently
    produce Ruleset-v2 results under a different id."""

    entrants = (
        _entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=0),
        _entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=256),
    )
    plain = _request(tmp_path, entrants, ruleset_id=V2, run_dir="plain")
    stray = _request(
        tmp_path, entrants, ruleset_id=V2, locality_reach=999, run_dir="stray"
    )
    assert canonical_match_id(plain) == canonical_match_id(stray)
    NativeMatchService().run(plain)
    NativeMatchService().run(stray)
    assert _result_json(plain)["result_id"] == _result_json(stray)["result_id"]


# ---------------------------------------------------------------------------
# Artifact identity
# ---------------------------------------------------------------------------


def _identity_request(tmp_path, reach, ruleset_id=LOCALITY, run_dir="run") -> MatchRequest:
    return _request(
        tmp_path,
        (
            _entrant(tmp_path, "a", LOCAL_SWEEPER_SOURCE, slot="A", start=0),
            _entrant(tmp_path, "b", LOCAL_SWEEPER_SOURCE, slot="B", start=256),
        ),
        ruleset_id=ruleset_id,
        locality_reach=reach,
        run_dir=run_dir,
    )


def test_the_resolved_reach_is_recorded_in_canonical_reproducibility(tmp_path) -> None:
    request = _identity_request(tmp_path, 24)
    NativeMatchService().run(request)
    result = _result_json(request)
    assert result["ruleset_id"] == LOCALITY
    assert result["reproducibility"]["locality_reach"] == 24


def test_an_omitted_reach_resolves_to_the_documented_default_and_is_disclosed(
    tmp_path,
) -> None:
    request = _identity_request(tmp_path, None)
    NativeMatchService().run(request)
    assert _result_json(request)["reproducibility"]["locality_reach"] == DEFAULT_LOCALITY_REACH


def test_changing_reach_changes_the_canonical_match_identity(tmp_path) -> None:
    assert canonical_match_id(_identity_request(tmp_path, 16)) != canonical_match_id(
        _identity_request(tmp_path, 32)
    )


def test_an_explicit_default_reach_and_an_omitted_one_share_one_identity(tmp_path) -> None:
    assert canonical_match_id(
        _identity_request(tmp_path, DEFAULT_LOCALITY_REACH)
    ) == canonical_match_id(_identity_request(tmp_path, None))


def test_the_locality_identity_never_collides_with_the_ruleset_v2_one(tmp_path) -> None:
    assert canonical_match_id(_identity_request(tmp_path, 16)) != canonical_match_id(
        _identity_request(tmp_path, 16, ruleset_id=V2)
    )


def test_per_entrant_locality_telemetry_is_persisted_for_a_locality_match(tmp_path) -> None:
    request = _identity_request(tmp_path, 16)
    NativeMatchService().run(request)
    for entrant in _result_json(request)["entrants"]:
        locality = entrant["metadata"]["locality"]
        assert locality["moves"] > 0
        assert locality["local_writes"] > 0
        assert locality["reach_misses"] == 0
        assert locality["distinct_loci"] == locality["moves"] + 1
        assert set(locality) == {
            "final_locus",
            "moves",
            "move_cells",
            "distinct_loci",
            "reach_misses",
            "local_reads",
            "local_writes",
            "core_distance_max",
            "core_distance_sum",
            "encounter_ticks",
            "opponent_core_reach_ticks",
            "final_core_distance",
        }


def test_the_replay_records_each_entrants_locus_every_tick(tmp_path) -> None:
    request = _identity_request(tmp_path, 16)
    NativeMatchService().run(request)
    ticks = [r for r in iter_replay(request.replay_path) if isinstance(r, TickSnapshot)]
    assert ticks
    for snapshot in ticks:
        for agent in snapshot.agents:
            assert agent.locus is not None
    # The locus actually moves over the match rather than being a constant.
    first = {a.agent_id: a.locus for a in ticks[0].agents}
    last = {a.agent_id: a.locus for a in ticks[-1].agents}
    assert first != last


# ---------------------------------------------------------------------------
# Action accounting -- locality adds no throughput
# ---------------------------------------------------------------------------


def test_move_consumes_exactly_one_action_like_every_other_operation(tmp_path) -> None:
    """Two entrants at the same budget, one spending every action on MOVE and
    one on NOP, must record the identical ``cpu_total``: movement is charged
    from the ordinary per-tick quota, never in addition to it."""

    mover = _scripted_source("[('move', 1, None)] * 1000")
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "mover", mover, slot="A", start=0),
            _entrant(tmp_path, "idle", NOP_SOURCE, slot="B", start=256),
        ),
        ruleset_id=LOCALITY,
        locality_reach=8,
        instr_per_tick=4,
        max_ticks=10,
    )
    NativeMatchService().run(request)
    entrants = {e["name"]: e for e in _result_json(request)["entrants"]}
    assert entrants["mover"]["statistics"]["cpu_total"] == 40
    assert entrants["idle"]["statistics"]["cpu_total"] == 40
    assert entrants["mover"]["metadata"]["locality"]["moves"] == 40


def test_a_reach_miss_costs_the_same_action_a_successful_operation_would(
    tmp_path,
) -> None:
    misser = _scripted_source("[('local_write', 999, 0x42)] * 1000")
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "misser", misser, slot="A", start=0),
            _entrant(tmp_path, "idle", NOP_SOURCE, slot="B", start=256),
        ),
        ruleset_id=LOCALITY,
        locality_reach=8,
        instr_per_tick=4,
        max_ticks=10,
    )
    NativeMatchService().run(request)
    entrants = {e["name"]: e for e in _result_json(request)["entrants"]}
    assert entrants["misser"]["statistics"]["cpu_total"] == 40
    assert entrants["misser"]["metadata"]["locality"]["reach_misses"] == 40
    assert entrants["misser"]["statistics"]["mem_writes"] == 0


def test_a_locality_entrant_gets_the_same_total_actions_as_a_ruleset_v2_one(
    tmp_path,
) -> None:
    """The whole action economy is unchanged: ``instr_per_tick x ticks`` is
    the budget under both Rulesets, and locality spends from it rather than
    extending it."""

    v2_request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=0),
            _entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=256),
        ),
        ruleset_id=V2,
        instr_per_tick=6,
        max_ticks=12,
        run_dir="v2",
    )
    locality_request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=0),
            _entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=256),
        ),
        ruleset_id=LOCALITY,
        locality_reach=16,
        instr_per_tick=6,
        max_ticks=12,
        run_dir="locality",
    )
    NativeMatchService().run(v2_request)
    NativeMatchService().run(locality_request)
    v2_cpu = {e["name"]: e["statistics"]["cpu_total"] for e in _result_json(v2_request)["entrants"]}
    loc_cpu = {
        e["name"]: e["statistics"]["cpu_total"]
        for e in _result_json(locality_request)["entrants"]
    }
    assert v2_cpu == loc_cpu == {"a": 72, "b": 72}


# ---------------------------------------------------------------------------
# Core behavior -- inherited from Ruleset v2, unchanged
# ---------------------------------------------------------------------------


def test_an_entrant_begins_standing_on_its_own_core(tmp_path) -> None:
    """Phase 2G: the initial locus is the entrant's own spawn address, which
    is also its core anchor -- so defending the core is possible from action
    one and no entrant is undefendable by construction."""

    prober = _scripted_source("[('local_read', 0, None)]")
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "prober", prober, slot="A", start=64),
            _entrant(tmp_path, "quiet", NOP_SOURCE, slot="B", start=320),
        ),
        ruleset_id=LOCALITY,
        locality_reach=8,
        max_ticks=2,
    )
    NativeMatchService().run(request)
    ticks = [r for r in iter_replay(request.replay_path) if isinstance(r, TickSnapshot)]
    first = {a.agent_id: a for a in ticks[0].agents}
    assert first["A"].locus == 64
    # It read its own core cell and found the beacon there.
    after = next(a for a in ticks[1].agents if a.agent_id == "A")
    assert after.last_read == CORE_BEACON_BYTE


def test_own_core_cells_are_within_reach_from_the_initial_locus(tmp_path) -> None:
    vm = VM(512)
    state = _bare_state(64)
    for offset in range(CORE_SIZE):
        apply_action(
            AgentAction(ActionKind.LOCAL_WRITE, offset, 0xD3), state, vm, locality_reach=8
        )
    assert state.locality_reach_misses == 0
    assert all(vm.arena[address] == 0xD3 for address in core_addresses(64, 512))


def test_a_local_write_burst_still_captures_an_opponent_core(tmp_path) -> None:
    """Capture semantics are inherited from Ruleset v2 verbatim: whoever owns
    every cell of a living entrant's core kills it, whether the writes came
    from an absolute ``WRITE`` or a bounded ``LOCAL_WRITE``."""

    # The attacker spawns 16 cells from the victim, walks to it, and
    # overwrites all eight core cells.
    attacker = _scripted_source(
        "[('move', -8, None), ('move', -8, None)] + [('local_write', i, 0xAA) for i in range(8)]"
    )
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=100),
            _entrant(tmp_path, "attacker", attacker, slot="B", start=116),
        ),
        ruleset_id=LOCALITY,
        locality_reach=8,
        instr_per_tick=4,
        max_ticks=10,
    )
    NativeMatchService().run(request)
    result = _result_json(request)
    entrants = {e["name"]: e for e in result["entrants"]}
    assert entrants["victim"]["termination_reason"] == "core_captured"
    assert entrants["attacker"]["statistics"]["kills"] == 1
    assert result["winner"] == "B"  # slot label of the attacker entrant


def test_the_core_beacon_invariant_is_preserved_under_locality(tmp_path) -> None:
    """A living entrant's own core cell is never blank -- alpha.11's
    observability rule, inherited unchanged, so a locality searcher has the
    same thing to find that a Ruleset-v2 searcher does."""

    blanker = _scripted_source("[('local_write', i, 0x00) for i in range(8)]")
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "blanker", blanker, slot="A", start=100),
            _entrant(tmp_path, "quiet", NOP_SOURCE, slot="B", start=356),
        ),
        ruleset_id=LOCALITY,
        locality_reach=8,
        instr_per_tick=4,
        max_ticks=6,
    )
    NativeMatchService().run(request)
    ticks = [r for r in iter_replay(request.replay_path) if isinstance(r, TickSnapshot)]
    arena = bytearray(512)
    for snapshot in ticks:
        for diff in snapshot.memory_diffs:
            for offset, value in enumerate(diff.values):
                arena[(diff.address + offset) % 512] = value
    assert all(arena[address] == CORE_BEACON_BYTE for address in core_addresses(100, 512))


def test_overlapping_cores_are_rejected_before_execution_under_locality(tmp_path) -> None:
    entrants = (
        _entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=100),
        _entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=104),
    )
    with pytest.raises(OverlappingCoreError):
        NativeMatchService().run(
            _request(tmp_path, entrants, ruleset_id=LOCALITY, locality_reach=8)
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_identical_inputs_reproduce_an_identical_match_replay_and_result(
    tmp_path,
) -> None:
    first = _identity_request(tmp_path, 20, run_dir="first")
    second = _identity_request(tmp_path, 20, run_dir="second")
    NativeMatchService().run(first)
    NativeMatchService().run(second)
    a, b = _result_json(first), _result_json(second)
    assert a["match_id"] == b["match_id"]
    assert a["result_id"] == b["result_id"]
    assert a["winner"] == b["winner"]
    assert a["score"] == b["score"]
    assert first.replay_path.read_bytes() == second.replay_path.read_bytes()


def test_a_locality_match_is_a_pure_function_of_its_declared_inputs(tmp_path) -> None:
    """Nothing about a locality match depends on wall time, iteration order of
    a set, or any other non-declared input: three runs agree exactly."""

    digests = []
    for index in range(3):
        request = _identity_request(tmp_path, 12, run_dir=f"run{index}")
        NativeMatchService().run(request)
        digests.append(_result_json(request)["replay"]["sha256"])
    assert len(set(digests)) == 1


def test_context_exposes_the_reach_so_an_agent_need_never_guess_it(tmp_path) -> None:
    """``MatchContext.locality_reach`` is the only channel through which an
    agent learns ``R``. Without it, an agent could only discover its bound by
    burning actions on reach misses, which would make the corpus measure
    probing overhead rather than strategy."""

    recorder = (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.reach = context.locality_reach\n\n"
        "    def act(self, observation):\n"
        "        if self.reach is None:\n"
        "            return AgentAction(ActionKind.HALT)\n"
        "        return AgentAction(ActionKind.LOCAL_WRITE, self.reach, 0x99)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    )
    request = _request(
        tmp_path,
        (
            _entrant(tmp_path, "recorder", recorder, slot="A", start=0),
            _entrant(tmp_path, "quiet", NOP_SOURCE, slot="B", start=256),
        ),
        ruleset_id=LOCALITY,
        locality_reach=11,
        max_ticks=3,
    )
    NativeMatchService().run(request)
    entrants = {e["name"]: e for e in _result_json(request)["entrants"]}
    assert entrants["recorder"]["alive"] is True
    # It wrote at exactly +R every action: in range, never a miss.
    assert entrants["recorder"]["metadata"]["locality"]["reach_misses"] == 0


def test_context_reach_is_none_under_every_stable_ruleset() -> None:
    context = MatchContext(
        agent_id="a", seed=1, arena_size=256, tick_limit=10, action_budget=4, rng=None  # type: ignore[arg-type]
    )
    assert context.locality_reach is None
    assert Observation(
        tick=1,
        agent_id="a",
        pc=0,
        register_a=0,
        register_p=0,
        zero_flag=False,
        last_read=None,
        alive=True,
    ).locus is None
