"""v2.0.0-alpha.4.1 "Winner-Semantics Hardening" -- survivor-eligibility tests.

alpha.4 (docs/V2_0_ALPHA4_MULTI_ENTRANT_FEASIBILITY.md Sec 7) found that
``results.resolve_winner``'s single-survivor override (``len(alive) == 1``)
never fires with two or more entrants alive, so the match fell through to
ordinary score comparison across ALL entrants -- including dead ones. Since
``ScoringPolicy.score_territory`` has no alive gate, a dead entrant's
previously-claimed territory keeps contributing every remaining tick, and in
two real matches from alpha.4's own 12-match exploratory matrix, the engine's
``result.winner`` named the entrant that had just been core-captured.

This file characterizes and locks in the alpha.4.1 fix: a dead entrant is
never eligible to win while any entrant survives, regardless of accumulated
score. Scores, statistics, and everything else remain byte-for-byte
unaffected -- only winner *eligibility* changed (see
``docs/V2_0_ALPHA4_1_WINNER_SEMANTICS.md``).

Two layers are covered:

- Direct ``resolve_winner`` calls against synthetic ``Agent`` fixtures for
  every scenario in the governing task's Phase 7, mirroring the existing
  precedent in ``test_match_services.py::
  test_winner_resolution_preserves_survival_score_fallback_and_ties``.
- One realistic end-to-end 3-entrant core-capture match through
  ``NativeMatchService`` (Phase 8), reusing ``test_v2_alpha4_multi_entrant.
  py``'s established scripted-agent helpers (duplicated rather than
  cross-imported, following that file's own precedent).
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agent_state import Agent
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.python_runtime import core_addresses
from battle_engine.results import resolve_winner
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ALPHA1_ID

ALPHA = BYTEFRAY_RULESET_V2_ALPHA1_ID


# ---------------------------------------------------------------------------
# 1v1 -- must remain byte-for-byte unchanged (Phase 7 "Existing 1v1 behavior")
# ---------------------------------------------------------------------------


def test_1v1_both_alive_score_decides() -> None:
    agents = [Agent("A", 0, alive=True), Agent("B", 1, alive=True)]
    assert resolve_winner(agents, {"A": 10, "B": 1}, "score_fallback") == "A"


def test_1v1_both_alive_score_tie() -> None:
    agents = [Agent("A", 0, alive=True), Agent("B", 1, alive=True)]
    assert resolve_winner(agents, {"A": 10, "B": 10}, "score_fallback") == ""


def test_1v1_one_dead_survivor_wins_regardless_of_score() -> None:
    agents = [Agent("A", 0, alive=True), Agent("B", 1, alive=False)]
    # B is dead but has a wildly higher score -- A must still win, exactly as
    # before this alpha (this branch is untouched: len(alive) == 1 returns
    # immediately, before eligibility filtering is even computed).
    assert resolve_winner(agents, {"A": 0, "B": 99}, "score_fallback") == "A"
    assert resolve_winner(agents, {"A": 0, "B": 99}, "survival") == "A"


def test_1v1_both_dead_falls_back_to_full_score_comparison() -> None:
    agents = [Agent("A", 0, alive=False), Agent("B", 1, alive=False)]
    # Zero survivors: no invented survival winner -- ordinary score
    # comparison across the full (here, entirely dead) entrant set, exactly
    # as pre-alpha.4.1.
    assert resolve_winner(agents, {"A": 5, "B": 9}, "score_fallback") == "B"
    assert resolve_winner(agents, {"A": 5, "B": 5}, "score_fallback") == ""


def test_1v1_survival_mode_never_uses_score_between_two_survivors() -> None:
    agents = [Agent("A", 0, alive=True), Agent("B", 1, alive=True)]
    assert resolve_winner(agents, {"A": 10, "B": 1}, "survival") == ""


# ---------------------------------------------------------------------------
# Three entrants -- the core alpha.4.1 scenarios (Phase 7)
# ---------------------------------------------------------------------------


def test_three_entrants_one_dead_survivor_wins_despite_lower_score() -> None:
    """A alive 100, B alive 90, C dead 1000 -> A. C's dominant score buys it
    nothing once dead; A wins purely because it survived, exactly the
    governing task's headline scenario."""

    agents = [Agent("A", 0, alive=True), Agent("B", 1, alive=True), Agent("C", 2, alive=False)]
    score = {"A": 100, "B": 90, "C": 1000}
    assert resolve_winner(agents, score, "score_fallback") == "A"


def test_three_entrants_two_dead_lone_survivor_forced_win() -> None:
    """A alive 1, B dead 1000, C dead 2000 -> A. This is the pre-existing
    single-survivor override (``len(alive) == 1``), unmodified by this
    alpha -- included here to anchor it alongside the new eligibility rule
    it complements."""

    agents = [Agent("A", 0, alive=True), Agent("B", 1, alive=False), Agent("C", 2, alive=False)]
    score = {"A": 1, "B": 1000, "C": 2000}
    assert resolve_winner(agents, score, "score_fallback") == "A"


def test_three_entrants_multiple_survivors_dead_entrant_excluded() -> None:
    """A alive 100, B alive 200, C dead 1000 -> B. Two survivors remain, so
    score decides between them -- but only between them; C's score is never
    consulted despite dwarfing both."""

    agents = [Agent("A", 0, alive=True), Agent("B", 1, alive=True), Agent("C", 2, alive=False)]
    score = {"A": 100, "B": 200, "C": 1000}
    assert resolve_winner(agents, score, "score_fallback") == "B"


def test_three_entrants_surviving_tie_unaffected_by_dead_entrants_score() -> None:
    """A alive 200, B alive 200, C dead 1000 -> tie. The pre-existing tie
    rule (top two scores equal -> "") is preserved exactly, applied to the
    survivor subset only -- C's 1000 neither breaks the tie nor wins."""

    agents = [Agent("A", 0, alive=True), Agent("B", 1, alive=True), Agent("C", 2, alive=False)]
    score = {"A": 200, "B": 200, "C": 1000}
    assert resolve_winner(agents, score, "score_fallback") == ""


def test_three_entrants_zero_survivors_falls_back_to_full_score_comparison() -> None:
    """All three dead: no survivor to prefer, so -- per the governing
    task's explicit instruction not to invent a survival winner here --
    resolution falls back to ordinary score comparison across the full
    (all-dead) entrant set, unchanged from pre-alpha.4.1 behavior. A
    tied variant is included to show the existing tie rule still applies
    identically in this fallback path."""

    agents = [Agent("A", 0, alive=False), Agent("B", 1, alive=False), Agent("C", 2, alive=False)]
    assert resolve_winner(agents, {"A": 100, "B": 300, "C": 200}, "score_fallback") == "B"
    assert resolve_winner(agents, {"A": 100, "B": 300, "C": 300}, "score_fallback") == ""


# ---------------------------------------------------------------------------
# Four entrants -- proves the rule is genuinely N-entrant, not a 3-entrant
# special case (Phase 7)
# ---------------------------------------------------------------------------


def test_four_entrants_two_alive_two_dead_highest_surviving_score_wins() -> None:
    """A alive 50, B alive 80, C dead 500, D dead 300 -> B. Two survivors,
    two dead entrants each individually outscoring both survivors -- the
    highest-scoring survivor still wins, and the eligibility filter scales
    to an entrant count this alpha never hardcodes anywhere."""

    agents = [
        Agent("A", 0, alive=True),
        Agent("B", 1, alive=True),
        Agent("C", 2, alive=False),
        Agent("D", 3, alive=False),
    ]
    score = {"A": 50, "B": 80, "C": 500, "D": 300}
    assert resolve_winner(agents, score, "score_fallback") == "B"


# ---------------------------------------------------------------------------
# Realistic 3-entrant core-capture integration test (Phase 8)
# ---------------------------------------------------------------------------


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


def _delayed_core_capture_source(nop_count: int, addresses: list[int], value: int = 0xAA) -> bytes:
    """NOP for ``nop_count`` actions (letting the victim build up territory
    first), then write ``addresses`` (the victim's core) one per ``act()``,
    then NOP forever. Models an attacker that only moves in once the victim
    already has something worth taking -- the realistic "late capture" shape
    both of alpha.4's real dead-winner matches actually had (captures at
    tick ~160/200 of a 200-tick budget, not immediately)."""

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        f"ADDRESSES = {addresses!r}\n"
        f"NOP_COUNT = {nop_count}\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.index = 0\n\n"
        "    def act(self, observation):\n"
        "        if self.index < NOP_COUNT:\n"
        "            self.index += 1\n"
        "            return AgentAction(ActionKind.NOP)\n"
        "        addr_index = self.index - NOP_COUNT\n"
        "        if addr_index < len(ADDRESSES):\n"
        "            self.index += 1\n"
        "            addr = ADDRESSES[addr_index]\n"
        f"            return AgentAction(ActionKind.WRITE, addr, {value})\n"
        "        return AgentAction(ActionKind.NOP)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


def test_realistic_three_way_core_capture_dead_victim_with_highest_score_does_not_win(tmp_path) -> None:
    """The exact alpha.4 failure mode, reproduced directly: a victim claims
    substantial territory, is then core-captured by an attacker while a
    bystander plays on, the victim's score keeps growing after death (no
    alive gate on territory scoring) and ends up the highest of the three --
    and yet the match winner must come from the two survivors, never the
    dead victim.
    """

    victim_core = list(core_addresses(40, 200))
    # Territory the victim claims for itself, away from any entrant's core
    # (attacker@[0,8), victim's own core@[40,48), bystander@[100,108)).
    victim_extra_territory = list(range(60, 100))  # 40 cells, 5 ticks to write

    entrants = (
        _python_entrant(tmp_path, "victim", _scripted_writer_source(victim_extra_territory), slot="A", start=40),
        _python_entrant(
            tmp_path,
            "attacker",
            _delayed_core_capture_source(len(victim_extra_territory), victim_core),
            slot="B",
            start=0,
        ),
        _python_entrant(tmp_path, "bystander", NOP_SOURCE, slot="C", start=100),
    )
    request = MatchRequest(
        Config(arena_size=200, instr_per_tick=8, weights=Weights(territory_bucket=1)),
        entrants,
        max_ticks=20,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    attacker = result.agents_by_id["B"]
    bystander = result.agents_by_id["C"]

    # 1. The victim was actually core-captured (not merely halted).
    assert victim.alive is False
    assert victim.termination_reason == "core_captured"
    assert victim.deaths == 1
    assert attacker.kills == 1

    # 2/4. B and C remain alive; the match reaches its normal termination
    # rather than ending the instant the victim dies.
    assert attacker.alive is True
    assert bystander.alive is True
    assert result.ticks_run == 20
    assert result.termination_reason.value == "tick_limit"

    # 3. The dead victim genuinely has the highest raw, preserved score --
    # this is not a contrived near-tie; its accumulated territory (40 cells
    # claimed before death, still "owned" and still scoring every tick
    # after) dwarfs either survivor's.
    assert victim.score > attacker.score
    assert victim.score > bystander.score
    assert victim.score > 0

    # 5. The dead victim must not be the winner -- winner comes only from
    # the surviving subset {attacker, bystander}. The attacker additionally
    # dominates the bystander here (same alive_ticks, plus the captured
    # core's territory, plus the kill bonus), so it is the deterministic
    # winner -- but the decisive assertion is simply that it is not "A".
    assert result.winner != "A"
    assert result.winner == "B"
