"""v3 Phase 7: focused tests for the disposable offset-tracker control agent
and the confound-isolation analysis tooling
(``tools/v3_phase7_confound_isolation.py``).

Phase 6 (docs/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md Sec
15/20) diagnosed real ``core_tracker``'s un-offset ``expand_cursor`` as one
mechanism behind its own budget-robustness gate failure at
``instr_per_tick=32``. Phase 7 asks whether offsetting that cursor -- and
nothing else -- repairs it. These tests verify (a) the disposable control
agent (``data/v3_phase7_agents/core_tracker_offset``) differs from the real,
frozen ``core_tracker`` reference agent in exactly the one intended way, and
(b) the Phase 7 "reaction opportunity" metric, built on top of the frozen
Phase 6 ``Episode``/``reconstruct_episodes`` machinery, computes correctly
against small hand-built tick sequences -- never against a live match.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import v3_phase6_defense_episode as phase6
import v3_phase7_confound_isolation as m
from battle_engine.agent_api import MatchContext, Observation, load_python_agent
from battle_engine.agents import agent_spec_from_dir
from battle_engine.reference_agents import reference_agent_spec

REPO = Path(__file__).resolve().parents[2]
OFFSET_AGENT_DIR = REPO / "engine" / "src" / "battle_engine" / "data" / "v3_phase7_agents" / "core_tracker_offset"


def _context(seed: int, arena_size: int = 4096, action_budget: int = 32) -> MatchContext:
    return MatchContext(
        agent_id="A",
        seed=seed,
        arena_size=arena_size,
        tick_limit=400,
        action_budget=action_budget,
        rng=random.Random(seed),
        locality_reach=None,
    )


def _observation(pc: int, last_read: int | None = None) -> Observation:
    return Observation(
        tick=0,
        agent_id="A",
        pc=pc,
        register_a=0,
        register_p=0,
        zero_flag=False,
        last_read=last_read,
        alive=True,
    )


def _load_real_tracker():
    return load_python_agent(reference_agent_spec("core_tracker")).instance


def _load_offset_tracker():
    spec = agent_spec_from_dir(OFFSET_AGENT_DIR)
    assert spec is not None
    return load_python_agent(spec).instance


# ---------------------------------------------------------------------------
# The one intended behavioral difference
# ---------------------------------------------------------------------------


def test_offset_tracker_expand_cursor_starts_past_its_own_core():
    real = _load_real_tracker()
    offset = _load_offset_tracker()
    core_start = 1365
    real.reset(_context(seed=1))
    offset.reset(_context(seed=1))

    # The first act() call both initializes expand_cursor AND immediately
    # consumes it as this tick's expand-write address (before advancing it
    # by expand_stride) -- so the *action's own operand* is the initial
    # cursor value, not ``.expand_cursor`` read back afterward.
    real_action = real.act(_observation(pc=core_start))
    offset_action = offset.act(_observation(pc=core_start))

    assert real.own_core_start == core_start
    assert offset.own_core_start == core_start
    # Real core_tracker: no offset at all.
    assert real_action.operand == core_start % real.arena_size
    # Offset control: exactly CORE_SIZE_HINT past its own core, mirroring
    # core_defender's own precedent.
    assert offset_action.operand == (core_start + m.CORE_SIZE_HINT) % offset.arena_size


def test_offset_tracker_first_expand_write_never_lands_in_its_own_core():
    offset = _load_offset_tracker()
    core_start = 1365
    offset.reset(_context(seed=1))
    # actions_taken=1 after this call: 1 % SCAN_EVERY(3) != 0, so this is an
    # "expand" WRITE, not a scan READ -- exactly the action that landed on
    # the real agent's own core_start + 0 in the Phase 6 replay this
    # experiment is diagnosing (see the governing report's Sec 15).
    action = offset.act(_observation(pc=core_start))
    assert action.kind.name == "WRITE"
    offset_from_own_core = (action.operand - core_start) % offset.arena_size
    assert offset_from_own_core >= m.CORE_SIZE_HINT


def test_offset_tracker_is_otherwise_behaviorally_identical_to_real_tracker():
    """Same scan/probe/assault decisions, same RNG draws, same signature --
    only expand-sweep addresses differ, and only by the fixed offset."""

    real = _load_real_tracker()
    offset = _load_offset_tracker()
    core_start = 500
    real.reset(_context(seed=7))
    offset.reset(_context(seed=7))

    # Both agents are driven with an identical, fixed Observation stream (no
    # foreign bytes ever appear), so both stay in "scan" mode throughout and
    # the only degree of freedom is each agent's own internal state.
    obs = _observation(pc=core_start)
    for _ in range(40):
        real_action = real.act(obs)
        offset_action = offset.act(obs)
        assert real_action.kind == offset_action.kind
        assert real_action.value == offset_action.value
        if real_action.kind.name == "WRITE" and real.mode == "scan":
            # An expand write: addresses differ by exactly the fixed offset
            # (mod arena_size); everything else about the decision is the
            # same because both agents drew the same RNG scan anchor and
            # follow the same scan-cadence arithmetic.
            assert offset_action.operand == (real_action.operand + m.CORE_SIZE_HINT) % real.arena_size
        else:
            assert real_action.operand == offset_action.operand


# ---------------------------------------------------------------------------
# Reaction-opportunity metric (built on the frozen Phase 6 Episode type)
# ---------------------------------------------------------------------------


def _episode(*, victim: str, attacker: str, start_tick: int, end_tick: int | None, end_reason: str | None) -> phase6.Episode:
    ep = phase6.Episode(victim=victim, attacker=attacker, start_tick=start_tick)
    ep.end_tick = end_tick
    ep.end_reason = end_reason
    return ep


def test_multi_tick_episode_always_had_a_reaction_opportunity():
    # Spans ticks 1..3: the victim's own action block runs on tick 2 and 3,
    # each strictly before the attacker's same-tick block on the *next*
    # tick, per sequential-quota scheduling -- true regardless of seat order.
    ep = _episode(victim="A", attacker="C", start_tick=1, end_tick=3, end_reason="captured")
    assert m.had_reaction_opportunity(ep) is True


def test_single_tick_episode_victim_scheduled_after_attacker_had_opportunity():
    # Fixed match order is A < B < C; victim C acts after attacker A within
    # the same tick, so it gets one same-tick reaction window before the
    # capture check fires.
    ep = _episode(victim="C", attacker="A", start_tick=5, end_tick=5, end_reason="captured")
    assert m.had_reaction_opportunity(ep) is True


def test_single_tick_episode_victim_scheduled_before_attacker_had_no_opportunity():
    # Victim A already used its tick-5 action block before attacker C ever
    # acted that tick; the whole episode -- hostile acquisition through
    # capture -- completes inside C's own block, so A never gets a chance.
    ep = _episode(victim="A", attacker="C", start_tick=5, end_tick=5, end_reason="captured")
    assert m.had_reaction_opportunity(ep) is False


def test_non_captured_episode_is_trivially_not_denied_a_chance():
    for reason in ("reclaimed_all", "third_party_takeover", "match_end"):
        ep = _episode(victim="A", attacker="C", start_tick=5, end_tick=5, end_reason=reason)
        assert m.had_reaction_opportunity(ep) is True
