"""v2.0.0-alpha.4 "Multi-Entrant Feasibility" -- focused 3-entrant tests.

Answers the governing task's central architecture question with executable
proof rather than code reading alone: does the existing engine -- built and
tested exclusively against exactly-two-entrant matches through alpha.1-3 --
actually execute correctly with three independent entrants, and does a
3-entrant match let ``alive_ticks``/``kills`` diverge and let an elimination
happen while play continues, the way a 2-entrant match structurally cannot
(see docs/V2_0_ALPHA3_SCORING_SENSITIVITY.md Sec 8/20)?

No production code changes accompany this file: every test below runs
against the unmodified engine. ``MatchEntrant``/``MatchRequest``/
``NativeMatchService``, both Python controllers, the shared scheduler,
scoring, statistics, ``resolve_winner``, and the core-capture mechanic all
already operate over ``tuple[MatchEntrant, ...]``/``list[Agent]`` with no
pair-specific code path -- this file exists to confirm that empirically,
not to add the capability.

Every scripted agent below is a small, fully deterministic Python source
string, mirroring ``test_ruleset_v2_alpha1.py``'s own established pattern,
so each scenario's exact tick-by-tick outcome is knowable in advance and
assertable precisely. Helpers are intentionally duplicated from that file
rather than imported cross-module, following the same precedent
``test_ruleset_v2_alpha1.py``'s own header comment already establishes
relative to ``test_ruleset_v1_equivalence.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.python_runtime import core_addresses
from battle_engine.replay import ReplayHeader, TickSnapshot, iter_replay
from battle_engine.result_model import read_result
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ALPHA1_ID

ALPHA = BYTEFRAY_RULESET_V2_ALPHA1_ID


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


def _python_entrant(root: Path, agent_id: str, source: bytes, *, slot: str, start: int) -> MatchEntrant:
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

HALT_SOURCE = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.HALT)

def create_agent():
    return Agent()
"""


def _scripted_writer_source(addresses: list[int], value: int = 0xAA) -> bytes:
    """Write ``addresses`` in order, one per ``act()``, then NOP forever."""

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


def _writer_then_halt_source(addresses: list[int], value: int = 0xAA) -> bytes:
    """Write ``addresses`` in order, one per ``act()``, then HALT forever."""

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
        "        return AgentAction(ActionKind.HALT)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


# ---------------------------------------------------------------------------
# Execution: three Python entrants load, act, and own territory
# ---------------------------------------------------------------------------


def test_three_entrants_all_load_and_act_and_own_territory(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "alpha_e", _scripted_writer_source([0, 1, 2, 3, 4]), slot="A", start=0),
        _python_entrant(tmp_path, "beta_e", _scripted_writer_source([100, 101, 102, 103, 104]), slot="B", start=100),
        _python_entrant(tmp_path, "gamma_e", _scripted_writer_source([200, 201, 202, 203, 204]), slot="C", start=200),
    )
    request = MatchRequest(
        Config(arena_size=300, instr_per_tick=2),
        entrants,
        max_ticks=3,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
    )
    result = NativeMatchService().run(request)
    assert len(result.agents) == 3
    for slot in ("A", "B", "C"):
        agent = result.agents_by_id[slot]
        assert agent.alive is True
        assert agent.alive_ticks == 3
        assert agent.territory_last == 5


# ---------------------------------------------------------------------------
# Continuation after one elimination -- the critical acceptance test
# ---------------------------------------------------------------------------


def test_match_continues_after_one_of_three_is_eliminated(tmp_path) -> None:
    """B halts on its very first action; A and C (NOP) run the full budget.

    Proves both halves of the alpha.4 hypothesis at once: the match does
    NOT terminate the instant one of three entrants dies (only
    ``alive_count == 1`` forces early termination -- see
    ``ruleset_policy.RulesetPolicy.resolve_termination``), and
    ``alive_ticks`` genuinely diverges (0 for B, 10 for A/C) in ordinary
    result data once it does.
    """

    entrants = (
        _python_entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=0),
        _python_entrant(tmp_path, "b", HALT_SOURCE, slot="B", start=50),
        _python_entrant(tmp_path, "c", NOP_SOURCE, slot="C", start=100),
    )
    request = MatchRequest(
        Config(arena_size=200, instr_per_tick=4),
        entrants,
        max_ticks=10,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
    )
    result = NativeMatchService().run(request)
    assert result.ticks_run == 10
    assert result.termination_reason.value == "tick_limit"

    a, b, c = result.agents_by_id["A"], result.agents_by_id["B"], result.agents_by_id["C"]
    assert a.alive is True and c.alive is True
    assert b.alive is False
    assert b.termination_reason == "normal_halt"

    alive_ticks_by_agent = {"A": a.alive_ticks, "B": b.alive_ticks, "C": c.alive_ticks}
    assert alive_ticks_by_agent == {"A": 10, "B": 0, "C": 10}
    # Genuinely divergent, not just "not identical to a fixed constant":
    assert len(set(alive_ticks_by_agent.values())) > 1


# ---------------------------------------------------------------------------
# 3-way core capture: basic attribution and bystander non-interference
# ---------------------------------------------------------------------------


def test_three_way_core_capture_basic_attribution_and_bystander_unaffected(tmp_path) -> None:
    victim_core = list(core_addresses(40, 200))
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=40),
        _python_entrant(tmp_path, "attacker", _scripted_writer_source(victim_core), slot="B", start=0),
        _python_entrant(tmp_path, "bystander", _scripted_writer_source([150]), slot="C", start=100),
    )
    request = MatchRequest(
        Config(arena_size=200, instr_per_tick=8),
        entrants,
        max_ticks=5,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )
    result = NativeMatchService().run(request)
    # Match continues to the tick limit -- eliminating one of three entrants
    # does not end the match, unlike the 2-entrant case (alpha.3 Sec 8).
    assert result.ticks_run == 5
    assert result.termination_reason.value == "tick_limit"

    victim, attacker, bystander = (
        result.agents_by_id["A"],
        result.agents_by_id["B"],
        result.agents_by_id["C"],
    )
    assert victim.alive is False
    assert victim.termination_reason == "core_captured"
    assert victim.deaths == 1
    assert attacker.kills == 1
    # The bystander is provably unaffected: it acted normally, owns exactly
    # what it wrote (1 cell) plus its own seeded core (8 cells -- under
    # bytefray-rules-2-alpha1, every entrant's own core is seeded at
    # construction, not just a "victim" role's -- see
    # python_runtime.seed_core_ownership), never died, and was neither
    # victim nor killer.
    assert bystander.alive is True
    assert bystander.kills == 0
    assert bystander.deaths == 0
    assert bystander.territory_last == 9


def test_three_way_core_capture_attribution_credits_the_entrant_that_completes_it(tmp_path) -> None:
    """Two independent attackers each damage half of the victim's core in
    the same tick; attribution goes to whichever one's write took the last
    cell, not to whoever contributed the most damage -- a "kill stealing"
    dynamic with no 2-entrant analogue, since a 2-entrant match can only
    ever have one attacker."""

    victim_core = list(core_addresses(40, 200))
    first_half, second_half = victim_core[:4], victim_core[4:]
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=40),
        _python_entrant(tmp_path, "first_attacker", _scripted_writer_source(first_half), slot="B", start=0),
        _python_entrant(tmp_path, "second_attacker", _scripted_writer_source(second_half), slot="C", start=100),
    )
    request = MatchRequest(
        Config(arena_size=200, instr_per_tick=4),
        entrants,
        max_ticks=3,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    first_attacker = result.agents_by_id["B"]
    second_attacker = result.agents_by_id["C"]
    assert victim.alive is False
    assert victim.termination_reason == "core_captured"
    # Scheduler order is entrant order (A, B, C): B's 4 writes replay before
    # C's within the same tick, so C's write is the one that actually
    # zeroes the victim's remaining ownership -- C gets sole kill credit
    # despite B having removed exactly as many cells.
    assert second_attacker.kills == 1
    assert first_attacker.kills == 0


# ---------------------------------------------------------------------------
# Winner logic at 3/2/1 survivors, and ties
# ---------------------------------------------------------------------------


def test_three_alive_at_tick_limit_winner_decided_by_score(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "a", _scripted_writer_source(list(range(10))), slot="A", start=0),
        _python_entrant(tmp_path, "b", _scripted_writer_source(list(range(20, 25))), slot="B", start=20),
        _python_entrant(tmp_path, "c", NOP_SOURCE, slot="C", start=40),
    )
    request = MatchRequest(
        Config(arena_size=64, instr_per_tick=10, weights=Weights(territory_bucket=1)),
        entrants,
        max_ticks=1,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
    )
    result = NativeMatchService().run(request)
    a, b, c = result.agents_by_id["A"], result.agents_by_id["B"], result.agents_by_id["C"]
    assert a.alive and b.alive and c.alive
    # alive_ticks/kills are identical (1, 0) for all three -- only territory
    # (10 vs 5 vs 0 cells, bucket size 1) breaks the tie.
    assert a.territory_last == 10
    assert b.territory_last == 5
    assert c.territory_last == 0
    assert result.winner == "A"
    assert result.termination_reason.value == "tick_limit"


def test_two_alive_at_tick_limit_dead_entrant_cannot_win_by_score(tmp_path) -> None:
    """With exactly two of three entrants alive at the tick limit,
    ``resolve_winner``'s single-survivor override (``len(alive) == 1``)
    never fires, so pre-alpha.4.1 the match fell through to ordinary score
    comparison across ALL entrants -- including the dead one. Territory
    score has no "alive" gate (``ScoringPolicy.score_territory``), so a
    dead entrant's previously-claimed cells kept contributing every
    remaining tick, letting it outscore -- and win against -- both live
    survivors (this was alpha.4's central finding, docs/
    V2_0_ALPHA4_MULTI_ENTRANT_FEASIBILITY.md Sec 7).

    As of alpha.4.1's survivor-eligibility rule
    (docs/V2_0_ALPHA4_1_WINNER_SEMANTICS.md), a dead entrant is no longer
    eligible while any entrant survives: A's dominant score (276) is
    excluded entirely, and the two survivors B/C -- both plain NOP agents
    that never claimed any territory -- are left exactly tied on their
    alive-tick score alone (10 each). The dead entrant's score is neither
    erased nor consulted; it simply can no longer buy a win, and it does
    not skew the survivors' own tie either.
    """

    entrants = (
        _python_entrant(tmp_path, "a", _writer_then_halt_source(list(range(32))), slot="A", start=0),
        _python_entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=40),
        _python_entrant(tmp_path, "c", NOP_SOURCE, slot="C", start=50),
    )
    request = MatchRequest(
        Config(arena_size=64, instr_per_tick=8, weights=Weights(territory_bucket=1)),
        entrants,
        max_ticks=10,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
    )
    result = NativeMatchService().run(request)
    a, b, c = result.agents_by_id["A"], result.agents_by_id["B"], result.agents_by_id["C"]

    assert a.alive is False
    assert a.termination_reason == "normal_halt"
    assert b.alive is True and c.alive is True
    # A: 4 alive ticks (halts entering tick 5) + territory accrued every
    # tick from 32 owned cells, including the 6 ticks after its own death.
    # Its score is preserved untouched by winner-eligibility filtering.
    assert a.alive_ticks == 4
    assert a.score == 276
    assert b.score == 10
    assert c.score == 10
    assert result.termination_reason.value == "tick_limit"
    # Dead A is excluded from eligibility despite the highest score; B/C
    # are left tied on their own merits -- not "A wins", not "B wins by
    # default", but a genuine tie among the survivors.
    assert result.winner == "tie"


def test_one_survivor_forces_win_regardless_of_score(tmp_path) -> None:
    """Two of three entrants must die (not just one) before the
    single-survivor override forces a winner in a 3-entrant match -- the
    direct N=3 analogue of the 2-entrant rule, requiring one extra death
    to reach the same forced-win condition. The sole survivor wins even
    though a now-dead entrant had by far the higher score at the moment it
    died, proving survival still overrides score once it actually applies.
    """

    entrants = (
        _python_entrant(tmp_path, "a", _writer_then_halt_source(list(range(8))), slot="A", start=0),
        _python_entrant(tmp_path, "b", HALT_SOURCE, slot="B", start=40),
        _python_entrant(tmp_path, "c", NOP_SOURCE, slot="C", start=50),
    )
    request = MatchRequest(
        Config(arena_size=64, instr_per_tick=8, weights=Weights(territory_bucket=1)),
        entrants,
        max_ticks=20,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
    )
    result = NativeMatchService().run(request)
    a, b, c = result.agents_by_id["A"], result.agents_by_id["B"], result.agents_by_id["C"]
    assert b.alive is False and a.alive is False
    assert c.alive is True
    # A accrued real (nonzero) score from its 8 written cells before
    # halting -- it is not "obviously" the weakest entrant on points.
    assert a.score > 0
    assert result.ticks_run == 2  # A halts entering tick 2, dropping alive_count to 1
    assert result.termination_reason.value == "last_agent_standing"
    assert result.winner == "C"


def test_three_way_tie_when_all_scores_equal(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=0),
        _python_entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=50),
        _python_entrant(tmp_path, "c", NOP_SOURCE, slot="C", start=100),
    )
    request = MatchRequest(
        Config(arena_size=200, instr_per_tick=4),
        entrants,
        max_ticks=3,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
    )
    result = NativeMatchService().run(request)
    assert result.winner == "tie"
    assert result.termination_reason.value == "tick_limit"
    for slot in ("A", "B", "C"):
        assert result.agents_by_id[slot].alive is True


# ---------------------------------------------------------------------------
# Artifacts and Ruleset v1 compatibility
# ---------------------------------------------------------------------------


def test_replay_and_result_artifacts_represent_all_three_entrants(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=0),
        _python_entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=50),
        _python_entrant(tmp_path, "c", NOP_SOURCE, slot="C", start=100),
    )
    request = MatchRequest(
        Config(arena_size=200, instr_per_tick=4),
        entrants,
        max_ticks=2,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )
    result = NativeMatchService().run(request)
    assert result.result_path is not None
    envelope = read_result(result.result_path)
    assert envelope.ruleset_id == ALPHA
    assert {entrant["agent_id"] for entrant in envelope.entrants} == {"A", "B", "C"}

    records = list(iter_replay(result.replay_path))
    header = records[0]
    assert isinstance(header, ReplayHeader)
    assert header.ruleset_id == ALPHA
    assert {entrant["agent_id"] for entrant in header.entrants} == {"A", "B", "C"}
    tick_zero = next(r for r in records if isinstance(r, TickSnapshot) and r.tick == 0)
    assert {agent.agent_id for agent in tick_zero.agents} == {"A", "B", "C"}


def test_three_entrant_match_runs_under_ruleset_v1_unchanged(tmp_path) -> None:
    """N-entrant support is a general engine property, not something gated
    on the experimental Ruleset -- a 3-entrant match under the frozen
    ``bytefray-rules-1`` (no ``ruleset_id`` passed) must execute correctly
    too, with no core mechanic involved at all."""

    entrants = (
        _python_entrant(tmp_path, "a", NOP_SOURCE, slot="A", start=0),
        _python_entrant(tmp_path, "b", NOP_SOURCE, slot="B", start=50),
        _python_entrant(tmp_path, "c", NOP_SOURCE, slot="C", start=100),
    )
    request = MatchRequest(
        Config(arena_size=200, instr_per_tick=4),
        entrants,
        max_ticks=3,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        # ruleset_id left at its default (None) -> resolves to v1.
    )
    result = NativeMatchService().run(request)
    assert result.result_path is not None
    envelope = read_result(result.result_path)
    assert envelope.ruleset_id == BYTEFRAY_RULESET_ID
    assert len(result.agents) == 3
    for slot in ("A", "B", "C"):
        assert result.agents_by_id[slot].alive is True
    assert result.termination_reason.value == "tick_limit"
