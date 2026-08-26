"""v3 Research Closeout: focused tests for the closeout-only tooling
(``tools/v3_closeout_defensive_timer.py``,
``tools/v3_closeout_capture_boundary.py``, and the disposable
``turtle_core_refresher`` probe agent).

These are hermetic unit tests against synthetic inputs or the real,
deterministic agent classes -- not real match executions. The broader
empirical results (full-corpus D1 blind-timer ratio, the blind-versus-
reactive discriminant, the turtle-probe corpus, and the constant-density
scheduler analysis) are reported in ``docs/V3_RESEARCH_CLOSEOUT.md``,
which this module does not duplicate.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import v3_closeout_capture_boundary as boundary
import v3_closeout_defensive_timer as timer_tool
from battle_engine.agent_api import ActionKind, MatchContext, Observation, load_python_agent
from battle_engine.agents import agent_spec_from_dir
from battle_engine.python_runtime import CORE_SIZE

REPO = Path(__file__).resolve().parents[2]
TURTLE_AGENT_DIR = (
    REPO / "engine" / "src" / "battle_engine" / "data" / "v3_closeout_agents" / "turtle_core_refresher"
)


# ---------------------------------------------------------------------------
# D1 blind-timer schedule
# ---------------------------------------------------------------------------


def test_blind_schedule_matches_core_defenders_known_refresh_cadence():
    # REFRESH_EVERY=4, instr_per_tick=8: two of every eight actions are
    # "defend" writes (actions_taken 4 and 8 within the first tick), hitting
    # defend_index 0 then 1 -- fully derivable in advance, independent of any
    # opponent, since core_defender never reads its own Observation after
    # the first call.
    schedule = timer_tool.blind_core_defender_schedule(
        core_start=100, arena_size=4096, instr_per_tick=8, tick_limit=3
    )
    assert schedule[1] == {100, 101}
    assert schedule[2] == {102, 103}
    assert schedule[3] == {104, 105}


def test_blind_schedule_is_a_pure_function_of_its_inputs():
    a = timer_tool.blind_core_defender_schedule(core_start=0, arena_size=4096, instr_per_tick=8, tick_limit=5)
    b = timer_tool.blind_core_defender_schedule(core_start=0, arena_size=4096, instr_per_tick=8, tick_limit=5)
    assert a == b


def test_blind_schedule_never_predicts_outside_its_own_core_window():
    schedule = timer_tool.blind_core_defender_schedule(
        core_start=4000, arena_size=4096, instr_per_tick=32, tick_limit=10
    )
    core_window = {(4000 + i) % 4096 for i in range(CORE_SIZE)}
    for addresses in schedule.values():
        assert addresses <= core_window


# ---------------------------------------------------------------------------
# Sec 11: one-block-capture theoretical boundary
# ---------------------------------------------------------------------------


def test_budget_equal_to_core_size_captures_in_one_block():
    result = boundary.one_block_capture_probe(budget=CORE_SIZE)
    assert result["victim_owned_after_attacker_block"] == 0
    assert result["captured"] is True


def test_budget_one_below_core_size_does_not_capture():
    result = boundary.one_block_capture_probe(budget=CORE_SIZE - 1)
    assert result["victim_owned_after_attacker_block"] == 1
    assert result["captured"] is False


def test_capture_boundary_is_monotonic_in_budget():
    owned = [boundary.one_block_capture_probe(budget=b)["victim_owned_after_attacker_block"] for b in range(1, CORE_SIZE + 2)]
    assert owned == sorted(owned, reverse=True)
    assert owned[0] == CORE_SIZE - 1  # budget=1 leaves all but one cell owned
    assert owned[-1] == 0  # budget=CORE_SIZE+1 already zeroed it


# ---------------------------------------------------------------------------
# Turtle probe agent: research probe only, not a reference agent
# ---------------------------------------------------------------------------


def _context(seed: int = 1, arena_size: int = 4096, action_budget: int = 8) -> MatchContext:
    return MatchContext(
        agent_id="turtle_core_refresher",
        seed=seed,
        arena_size=arena_size,
        tick_limit=400,
        action_budget=action_budget,
        rng=random.Random(seed),
        locality_reach=None,
    )


def _observation(pc: int) -> Observation:
    return Observation(
        tick=0, agent_id="turtle_core_refresher", pc=pc, register_a=0, register_p=0,
        zero_flag=False, last_read=None, alive=True,
    )


def _load_turtle():
    spec = agent_spec_from_dir(TURTLE_AGENT_DIR)
    assert spec is not None
    return load_python_agent(spec).instance


def test_turtle_probe_writes_only_within_its_own_core_forever():
    agent = _load_turtle()
    core_start = 777
    agent.reset(_context())
    core_window = {(core_start + i) % 4096 for i in range(CORE_SIZE)}
    obs = _observation(pc=core_start)
    for _ in range(100):
        action = agent.act(obs)
        assert action.kind == ActionKind.WRITE
        assert action.operand in core_window


def test_turtle_probe_never_reads_and_cycles_deterministically():
    agent = _load_turtle()
    core_start = 0
    agent.reset(_context())
    obs = _observation(pc=core_start)
    addresses = [agent.act(obs).operand for _ in range(CORE_SIZE * 3)]
    expected_cycle = [(core_start + i) % CORE_SIZE for i in range(CORE_SIZE)]
    assert addresses == expected_cycle * 3
