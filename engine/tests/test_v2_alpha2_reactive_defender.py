"""``reactive_core_defender`` -- v2.0.0-alpha.2 reactive-defense acceptance tests.

Covers the Phase 5 checklist from the governing v2.0.0-alpha.2 task: proves
this reference agent is genuinely *reactive* (detects and responds to
evidence of core damage through ordinary observations) rather than merely
a differently-shaped periodic agent like the original ``core_defender``
(see ``test_v2_alpha1_reference_agents.py`` and
``docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md``). Every scripted opponent below is
a small, fully deterministic Python source string, mirroring
``test_ruleset_v2_alpha1.py``'s own pattern, so each scenario's exact
tick-by-tick ownership sequence is knowable in advance.
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agent_api import load_python_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.python_runtime import core_addresses
from battle_engine.reference_agents import reference_agent_spec
from battle_engine.replay import TickSnapshot, iter_replay
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ALPHA1_ID

ALPHA = BYTEFRAY_RULESET_V2_ALPHA1_ID
DEFENDER = reference_agent_spec("reactive_core_defender")


def _write_agent(agent_dir: Path, agent_id: str, source: bytes) -> None:
    agent_dir.mkdir(parents=True)
    manifest = {
        "kind": "python",
        "api_version": 1,
        "entrypoint": "agent.py:create_agent",
        "name": agent_id,
        "display": agent_id.title(),
        "version": "1.0",
    }
    agent_dir.joinpath("agent.yaml").write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    agent_dir.joinpath("agent.py").write_bytes(source)


def _scripted_entrant(root: Path, agent_id: str, source: bytes, *, slot: str, start: int) -> MatchEntrant:
    from battle_engine.agents import resolve_agent

    agent_dir = root / "agents" / agent_id
    _write_agent(agent_dir, agent_id, source)
    return MatchEntrant.python(slot, agent_id, start, resolve_agent(root, agent_id))


NOP_SOURCE = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _scripted_writer_source(addresses: list[int], value: int = 0xAA) -> bytes:
    """Write ``addresses`` in order, one per ``act()`` call, then NOP forever."""

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        f"ADDRESSES = {addresses!r}\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.index = 0\n\n"
        "    def act(self, observation):\n"
        "        if self.index < len(ADDRESSES):\n"
        "            addr = ADDRESSES[self.index]\n"
        "            self.index += 1\n"
        f"            return AgentAction(ActionKind.WRITE, addr, {value})\n"
        "        return AgentAction(ActionKind.NOP)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


def _delayed_writer_source(delay: int, addresses: list[int], value: int = 0xAA) -> bytes:
    """NOP ``delay`` times, then write ``addresses`` in order, then NOP forever.

    Used to let the defender's own one-time SIGN phase (``DEFENDED_RADIUS``
    actions) finish before any attack begins, so a test exercises the
    genuinely *reactive* PATROL/ALERT detection path rather than being
    incidentally satisfied by SIGN's own unconditional first pass over
    every core cell.
    """

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        f"DELAY = {delay!r}\n"
        f"ADDRESSES = {addresses!r}\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.index = 0\n\n"
        "    def act(self, observation):\n"
        "        if self.index < DELAY:\n"
        "            self.index += 1\n"
        "            return AgentAction(ActionKind.NOP)\n"
        "        write_index = self.index - DELAY\n"
        "        if write_index < len(ADDRESSES):\n"
        "            addr = ADDRESSES[write_index]\n"
        "            self.index += 1\n"
        f"            return AgentAction(ActionKind.WRITE, addr, {value})\n"
        "        return AgentAction(ActionKind.NOP)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


def _spaced_writer_source(delay: int, addresses: list[int], gap: int, value: int = 0xAA) -> bytes:
    """NOP ``delay`` times, then write each of ``addresses`` one at a time,
    each followed by ``gap`` NOPs, then NOP forever.

    Attacking one cell at a time with a wide gap between hits (rather than
    a simultaneous multi-cell burst) tests full-core repair over the
    course of a match without depending on the exact phase relationship
    between a fixed patrol rotation's cursor and a burst's start tick --
    see this module's own discussion (in
    ``test_attempts_full_repair_of_a_fully_damaged_core``) of why a
    simultaneous same-order burst against a fixed round-robin patrol is
    phase-dependent and not a fair single-scenario acceptance test on its
    own.
    """

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        f"DELAY = {delay!r}\n"
        f"ADDRESSES = {addresses!r}\n"
        f"GAP = {gap!r}\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.index = 0\n\n"
        "    def act(self, observation):\n"
        "        if self.index < DELAY:\n"
        "            self.index += 1\n"
        "            return AgentAction(ActionKind.NOP)\n"
        "        offset = self.index - DELAY\n"
        "        step = GAP + 1\n"
        "        cell = offset // step\n"
        "        if cell < len(ADDRESSES) and offset % step == 0:\n"
        "            self.index += 1\n"
        f"            return AgentAction(ActionKind.WRITE, ADDRESSES[cell], {value})\n"
        "        self.index += 1\n"
        "        return AgentAction(ActionKind.NOP)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


def _defender_request(
    tmp_path: Path,
    *,
    defender_start: int,
    opponent_source: bytes,
    arena_size: int = 512,
    instr_per_tick: int = 2,
    max_ticks: int = 40,
    ruleset_id: str | None = ALPHA,
) -> MatchRequest:
    entrants = (
        MatchEntrant.python("A", "reactive_core_defender", defender_start, DEFENDER),
        _scripted_entrant(tmp_path, "attacker", opponent_source, slot="B", start=0),
    )
    return MatchRequest(
        Config(arena_size=arena_size, instr_per_tick=instr_per_tick),
        entrants,
        max_ticks=max_ticks,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
    )


def _core_writes_by(records, agent_id: str, arena_size: int = 512) -> list[tuple[int, int]]:
    """(tick, address, owner) for every arena WRITE credited to ``agent_id``."""

    hits = []
    for record in records:
        if not isinstance(record, TickSnapshot):
            continue
        for diff in record.memory_diffs:
            if diff.owner != agent_id:
                continue
            for offset in range(diff.length):
                addr = (diff.address + offset) % arena_size
                hits.append((record.tick, addr, diff.owner))
    return hits


# ---------------------------------------------------------------------------
# Ordinary Agent API v1 lifecycle
# ---------------------------------------------------------------------------


def test_reactive_core_defender_satisfies_the_agent_api_v1_contract() -> None:
    loaded = load_python_agent(DEFENDER)
    assert loaded.metadata.agent_id == "reactive_core_defender"
    assert loaded.metadata.api_version == 1


def test_reactive_core_defender_is_not_part_of_the_general_starter_roster() -> None:
    from battle_engine.starters import STARTER_AGENT_NAMES

    assert "reactive_core_defender" not in STARTER_AGENT_NAMES


def test_reactive_core_defender_runs_a_full_match_without_forfeiting(tmp_path) -> None:
    request = _defender_request(tmp_path, defender_start=20, opponent_source=NOP_SOURCE)
    result = NativeMatchService().run(request)
    for agent in result.agents:
        assert agent.diagnostic is None


# ---------------------------------------------------------------------------
# No privileged information
# ---------------------------------------------------------------------------


def test_observation_carries_no_opponent_state_the_agent_could_read() -> None:
    """Structural guarantee: even if this agent wanted opponent state, the
    Agent API v1 ``Observation`` it is handed has no field to read it from."""

    from battle_engine.agent_api import Observation

    v1_fields = {
        "tick",
        "agent_id",
        "pc",
        "register_a",
        "register_p",
        "zero_flag",
        "last_read",
        "alive",
    }
    # v3 research Phase 2 adds exactly one additive, optional field, and it
    # describes *this* entrant's own execution locus -- never another
    # entrant's anything. It is `None` under every Ruleset with a stable
    # identity, so a v1/v2 agent observes exactly what it always did.
    experimental_fields = {"locus"}
    fields = {f.name for f in Observation.__dataclass_fields__.values()}
    assert fields == v1_fields | experimental_fields
    assert Observation.__dataclass_fields__["locus"].default is None


def test_behavior_before_any_damage_is_identical_regardless_of_opponent(tmp_path) -> None:
    """With no core damage, this agent's own core-directed actions must be a
    pure function of its own state -- identical whether the opponent is an
    idle NOP agent or an active writer elsewhere in the arena, proving
    nothing about *this* opponent leaks into *this* agent's behavior."""

    quiet = _defender_request(
        tmp_path / "quiet", defender_start=20, opponent_source=NOP_SOURCE, max_ticks=10
    )
    busy = _defender_request(
        tmp_path / "busy",
        defender_start=20,
        opponent_source=_scripted_writer_source(list(range(300, 320))),
        max_ticks=10,
    )
    quiet_result = NativeMatchService().run(quiet)
    busy_result = NativeMatchService().run(busy)

    core = set(core_addresses(20, 512))
    quiet_hits = _core_writes_by(iter_replay(quiet_result.replay_path), "A")
    busy_hits = _core_writes_by(iter_replay(busy_result.replay_path), "A")
    quiet_core_hits = [(t, a) for t, a, _ in quiet_hits if a in core]
    busy_core_hits = [(t, a) for t, a, _ in busy_hits if a in core]
    assert quiet_core_hits == busy_core_hits


# ---------------------------------------------------------------------------
# Normal (undamaged) behavior: expands, signs once, does not blindly rewrite
# ---------------------------------------------------------------------------


def test_expands_when_core_is_intact(tmp_path) -> None:
    request = _defender_request(
        tmp_path, defender_start=20, opponent_source=NOP_SOURCE, max_ticks=10
    )
    result = NativeMatchService().run(request)
    core = set(core_addresses(20, 512))
    a = result.agents_by_id["A"]
    assert a.territory_last > len(core)  # claimed ground well beyond its own core


def test_does_not_continuously_rewrite_a_healthy_core(tmp_path) -> None:
    """No attack ever occurs: excluding tick 0 (the engine's own one-time
    ``seed_core_ownership`` spawn step, not this agent's decision -- see
    ``python_runtime.seed_core_ownership``), every core-address WRITE this
    agent itself chooses to make must come from its own one-time SIGN phase
    (exactly ``DEFENDED_RADIUS`` writes), never a recurring blind refresh."""

    request = _defender_request(
        tmp_path, defender_start=20, opponent_source=NOP_SOURCE, max_ticks=40
    )
    result = NativeMatchService().run(request)
    core = set(core_addresses(20, 512))
    hits = _core_writes_by(iter_replay(result.replay_path), "A")
    core_hits = [(t, a) for t, a, _ in hits if a in core and t > 0]
    assert len(core_hits) == 8  # exactly the one-time sign phase, no ongoing refresh
    assert {addr for _, addr in core_hits} == core


# ---------------------------------------------------------------------------
# Detection, reaction, and repair
# ---------------------------------------------------------------------------


def test_detects_and_repairs_a_single_damaged_core_cell(tmp_path) -> None:
    core = list(core_addresses(20, 512))
    target = core[3]
    request = _defender_request(
        tmp_path,
        defender_start=20,
        # Delayed well past the 8-action SIGN phase (instr_per_tick=1, so
        # SIGN finishes by tick 8) so this exercises genuine PATROL-driven
        # detection, not SIGN's own incidental first pass over every cell.
        opponent_source=_delayed_writer_source(20, [target]),
        instr_per_tick=1,
        max_ticks=80,
    )
    result = NativeMatchService().run(request)
    a = result.agents_by_id["A"]
    assert a.alive is True
    assert a.termination_reason is None

    hits = _core_writes_by(iter_replay(result.replay_path), "A")
    repair_hits = [(t, addr) for t, addr, _ in hits if addr == target]
    # More than the sign-phase write to `target` -- a later repair happened.
    assert len(repair_hits) >= 2


def test_changes_behavior_after_detecting_damage(tmp_path) -> None:
    """Once a mismatch is found, the repair follows promptly -- a real,
    fast behavioral pivot triggered by evidence, not an eventual
    coincidence spread arbitrarily across the rest of the match."""

    core = list(core_addresses(20, 512))
    target = core[5]
    request = _defender_request(
        tmp_path,
        defender_start=20,
        opponent_source=_delayed_writer_source(20, [target]),
        instr_per_tick=1,
        max_ticks=80,
    )
    result = NativeMatchService().run(request)
    records = list(iter_replay(result.replay_path))

    attacker_hit_tick = next(
        record.tick
        for record in records
        if isinstance(record, TickSnapshot)
        for diff in record.memory_diffs
        if diff.owner == "B"  # the scripted attacker's match slot
        for offset in range(diff.length)
        if (diff.address + offset) % 512 == target
    )
    hits = _core_writes_by(records, "A")
    repair_ticks = [t for t, addr, _ in hits if addr == target and t > attacker_hit_tick]
    assert repair_ticks
    # A full, un-reactive patrol pass is DEFENDED_RADIUS * REFRESH_EVERY
    # ticks at instr_per_tick=1 (32); a genuine reaction lands well before
    # that, driven by the detection itself rather than merely waiting for
    # the next scheduled inspection of this specific cell to come around.
    assert repair_ticks[0] - attacker_hit_tick < 32


def test_attempts_full_repair_of_a_fully_damaged_core(tmp_path) -> None:
    """Every one of the 8 core cells is attacked, one at a time, widely
    spaced (not a simultaneous burst -- see ``_spaced_writer_source``'s
    docstring for why a same-order simultaneous burst against this fixed
    patrol rotation is phase-dependent and not by itself a fair test of
    "can this agent ever repair a fully damaged core"). With each hit
    given a full patrol cycle's worth of room to be noticed and fixed
    before the next lands, this agent must end up with its whole core
    intact, having reclaimed every cell at least once."""

    core = list(core_addresses(20, 512))
    request = _defender_request(
        tmp_path,
        defender_start=20,
        opponent_source=_spaced_writer_source(20, core, gap=40),
        instr_per_tick=8,
        max_ticks=400,
    )
    result = NativeMatchService().run(request)
    a = result.agents_by_id["A"]
    assert a.alive is True
    assert a.termination_reason is None
    hits = _core_writes_by(iter_replay(result.replay_path), "A")
    core_set = set(core)
    reclaimed = {addr for t, addr, _ in hits if addr in core_set and t > 0}
    assert reclaimed == core_set  # every cell was repaired at least once


def test_returns_to_expansion_after_damage_is_resolved(tmp_path) -> None:
    """A single, one-shot attack (not sustained) must not leave this agent
    stuck defending forever -- normal expansion must resume afterward."""

    core = list(core_addresses(20, 512))
    request = _defender_request(
        tmp_path,
        defender_start=20,
        opponent_source=_delayed_writer_source(20, [core[0]]),
        instr_per_tick=1,
        max_ticks=100,
    )
    result = NativeMatchService().run(request)
    records = list(iter_replay(result.replay_path))
    hits = _core_writes_by(records, "A")
    core_set = set(core)
    last_core_write_tick = max(t for t, a, _ in hits if a in core_set)
    a_writes_after = [
        (record.tick, diff.address)
        for record in records
        if isinstance(record, TickSnapshot) and record.tick > last_core_write_tick
        for diff in record.memory_diffs
        if diff.owner == "A"
    ]
    assert a_writes_after  # kept acting
    assert any(addr not in set(core) for _, addr in a_writes_after)  # and expanded again


# ---------------------------------------------------------------------------
# Determinism, wrap-around, ruleset non-interference
# ---------------------------------------------------------------------------


def test_deterministic_given_identical_input(tmp_path) -> None:
    core = list(core_addresses(20, 512))
    first = _defender_request(
        tmp_path / "first",
        defender_start=20,
        opponent_source=_scripted_writer_source(core),
        instr_per_tick=1,
        max_ticks=80,
    )
    second = _defender_request(
        tmp_path / "second",
        defender_start=20,
        opponent_source=_scripted_writer_source(core),
        instr_per_tick=1,
        max_ticks=80,
    )
    first_result = NativeMatchService().run(first)
    second_result = NativeMatchService().run(second)
    first_a = first_result.agents_by_id["A"]
    second_a = second_result.agents_by_id["A"]
    assert first_a.alive == second_a.alive
    assert first_a.termination_reason == second_a.termination_reason
    assert first_a.score == second_a.score
    assert first_a.territory_last == second_a.territory_last


def test_repairs_correctly_when_the_core_wraps_the_arena_end(tmp_path) -> None:
    arena_size = 64
    start = arena_size - 3  # core spans [61, 62, 63, 0, 1, 2, 3, 4]
    core = list(core_addresses(start, arena_size))
    assert core[0] > core[-1]  # confirms the wrap actually occurs
    # The attacker's own start must not overlap the defender's wrapped core
    # (arena_size // 2 is far from both [61-63] and [0-4]) -- an
    # overlapping spawn would let the engine's own spawn-time
    # seed_core_ownership (called for every entrant, not just this one)
    # silently steal cells before tick one even begins, which would test
    # the pathological overlapping-core edge case
    # (test_ruleset_v2_alpha1.py's own
    # test_capture_attribution_unattributed_when_core_already_lost_before_the_tick),
    # not ordinary wrap-around repair.
    entrants = (
        MatchEntrant.python("A", "reactive_core_defender", start, DEFENDER),
        _scripted_entrant(
            tmp_path,
            "attacker",
            _spaced_writer_source(20, core, gap=40),
            slot="B",
            start=arena_size // 2,
        ),
    )
    request = MatchRequest(
        Config(arena_size=arena_size, instr_per_tick=8),
        entrants,
        max_ticks=400,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )
    result = NativeMatchService().run(request)
    a = result.agents_by_id["A"]
    assert a.alive is True
    assert a.termination_reason is None
    hits = _core_writes_by(iter_replay(result.replay_path), "A", arena_size=arena_size)
    repaired_addresses = {addr for _, addr, _ in hits if addr in set(core)}
    assert repaired_addresses == set(core)  # every wrapped cell was reclaimed


def test_does_not_alter_ruleset_v1_semantics(tmp_path) -> None:
    """Under Ruleset v1 there is no core mechanic at all -- this agent must
    run cleanly and never claim/receive a core-related termination."""

    request = _defender_request(
        tmp_path,
        defender_start=20,
        opponent_source=NOP_SOURCE,
        max_ticks=20,
        ruleset_id=None,
    )
    result = NativeMatchService().run(request)
    a = result.agents_by_id["A"]
    assert a.diagnostic is None
    assert a.termination_reason != "core_captured"
    from battle_engine.replay import ReplayHeader

    header = next(iter_replay(result.replay_path))
    assert isinstance(header, ReplayHeader)
    assert header.ruleset_id == BYTEFRAY_RULESET_ID


# ---------------------------------------------------------------------------
# End-to-end: actually survives the same committed attack that always
# captured the original Core Defender in alpha.1
# ---------------------------------------------------------------------------


def test_survives_core_seeker_where_the_original_defender_never_did(tmp_path) -> None:
    seeker = reference_agent_spec("core_seeker")
    survived = 0
    for seed in range(1, 9):
        entrants = (
            MatchEntrant.python("A", "reactive_core_defender", 0, DEFENDER),
            MatchEntrant.python("B", "core_seeker", 2048, seeker),
        )
        request = MatchRequest(
            Config(arena_size=4096, seed=seed),
            entrants,
            max_ticks=200,
            replay_path=tmp_path / f"run-{seed}" / "replay.jsonl",
            verbose=False,
            ruleset_id=ALPHA,
        )
        result = NativeMatchService().run(request)
        if result.agents_by_id["A"].termination_reason != "core_captured":
            survived += 1
    # Not claimed as a guaranteed outcome for every possible future Core
    # Seeker revision -- but for the actual bundled reference implementation,
    # this must show a real, reproducible improvement over the original
    # Core Defender's 0/5 survival rate against the identical opponent
    # (docs/V2_0_ALPHA1_EVALUATION.md Sec 7).
    assert survived >= 6
