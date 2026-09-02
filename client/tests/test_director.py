"""Phase 7: client-side Director wall-clock runtime and per-mode caching.

The underlying `DirectorPlan`'s *content* (state transitions, significance
mapping, hidden-event non-reaction) is already proven against real matches in
`engine/tests/test_v4_spectator_director.py`. This file tests a different
layer: `PlaybackDirectorRuntime`'s wall-clock hold consumption and
`DirectorManager`'s per-mode caching, using a hand-built `DirectorPlan` (so
hold/rate timing is exactly controlled) and a synthetic replay session (the
same pattern `test_playback_controller.py` already uses for pure
playback-mechanics tests that do not need a real engine trace).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from battle_client.director import BROADCAST_MODE, DirectorManager, PlaybackDirectorRuntime
from battle_client.player import PlaybackController
from battle_client.session import ReplaySession
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.replay import (
    AgentState,
    MatchConfiguration,
    ReplayHeader,
    TickSnapshot,
    write_replay,
)
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1
from battle_engine.spectator_derivation import analyze_pair
from battle_engine.spectator_director import (
    DirectorDecision,
    DirectorMode,
    DirectorPacingState,
    DirectorPlan,
    DirectorReason,
)


class FakeClock:
    """A manually-advanced monotonic clock for deterministic hold tests."""

    def __init__(self, start: float = 100.0) -> None:
        self._now = start

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def __call__(self) -> float:
        return self._now


def _agent(agent_id: str, pc: int = 0) -> AgentState:
    return AgentState(agent_id=agent_id, pc=pc, alive=True, cpu_used=0, mem_writes=0)


def _ten_tick_session(tmp_path: Path) -> ReplaySession:
    header = ReplayHeader(MatchConfiguration(arena_size=8), {"A": "alpha", "B": "beta"}, runtime_kind="vm")
    ticks = tuple(
        TickSnapshot(t, agents=(_agent("A", pc=t), _agent("B", pc=t)), score={"A": t, "B": 0})
        for t in range(10)
    )
    replay_path = tmp_path / "replay.jsonl"
    write_replay(replay_path, [header, *ticks])
    session = ReplaySession()
    session.load(replay_path)
    return session


def _decision(
    tick: int,
    *,
    state: DirectorPacingState = DirectorPacingState.CRUISE,
    rate_tps: float = 10.0,
    hold_ms: int = 0,
    reason: DirectorReason = DirectorReason.NO_SIGNIFICANT_ACTIVITY,
) -> DirectorDecision:
    return DirectorDecision(
        tick=tick,
        state=state,
        rate_tps=rate_tps,
        hold_ms=hold_ms,
        reason=reason,
        source_events=(),
        visibility_basis="broadcast",
        boundary=False,
    )


def _plan_with_hold_at(tick_with_hold: int, *, hold_ms: int = 500, last_tick: int = 9) -> DirectorPlan:
    decisions = tuple(
        _decision(
            t,
            state=DirectorPacingState.IMPACT_HOLD if t == tick_with_hold else DirectorPacingState.CRUISE,
            hold_ms=hold_ms if t == tick_with_hold else 0,
            reason=DirectorReason.MAJOR_EVENT_HOLD if t == tick_with_hold else DirectorReason.NO_SIGNIFICANT_ACTIVITY,
        )
        for t in range(last_tick + 1)
    )
    return DirectorPlan(
        mode=DirectorMode.BROADCAST,
        entrant_id=None,
        visibility_basis="broadcast",
        match_id="synthetic",
        replay_sha256="0" * 64,
        config_fingerprint=(),
        first_tick=0,
        last_tick=last_tick,
        decisions=decisions,
    )


# ---------------------------------------------------------------------------
# PlaybackDirectorRuntime: rate application
# ---------------------------------------------------------------------------


def test_update_applies_the_planned_rate_and_advances(tmp_path: Path) -> None:
    session = _ten_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    plan = _plan_with_hold_at(3)  # tick 0-2 and 4-9 are plain CRUISE @ 10 TPS
    runtime = PlaybackDirectorRuntime(plan, clock=FakeClock())

    assert controller.session.current_tick == 0
    runtime.update(controller, elapsed_seconds=0.15)  # interval is 1/10 = 0.1s
    assert controller.session.current_tick == 1
    assert controller.tick_interval == 0.1


# ---------------------------------------------------------------------------
# PlaybackDirectorRuntime: hold consumption
# ---------------------------------------------------------------------------


def test_hold_blocks_advance_until_the_wall_clock_elapses(tmp_path: Path) -> None:
    session = _ten_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    controller.session.seek(3)
    plan = _plan_with_hold_at(3, hold_ms=500)
    clock = FakeClock()
    runtime = PlaybackDirectorRuntime(plan, clock=clock)

    runtime.update(controller, elapsed_seconds=0.016)
    assert controller.session.current_tick == 3, "hold must block advance immediately"

    clock.advance(0.3)
    runtime.update(controller, elapsed_seconds=0.016)
    assert controller.session.current_tick == 3, "300ms < 500ms hold: must still be holding"
    assert runtime.hold_remaining_ms(3) == pytest.approx(200.0)

    clock.advance(0.25)  # total 550ms >= 500ms: this frame clears the hold and
    # resumes rate-based accumulation, but a 16ms frame alone does not cross a
    # 100ms tick interval -- it takes a normal-sized next frame to actually
    # step forward, exactly as ordinary (non-Director) playback would.
    runtime.update(controller, elapsed_seconds=0.016)
    assert controller.session.current_tick == 3, "hold clears this frame but does not itself advance"
    runtime.update(controller, elapsed_seconds=0.15)
    assert controller.session.current_tick == 4, "next frame advances at the resumed rate"


def test_same_tick_repeated_calls_do_not_restart_or_extend_the_hold(tmp_path: Path) -> None:
    session = _ten_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    controller.session.seek(3)
    plan = _plan_with_hold_at(3, hold_ms=500)
    clock = FakeClock()
    runtime = PlaybackDirectorRuntime(plan, clock=clock)

    runtime.update(controller, elapsed_seconds=0.016)
    clock.advance(0.2)
    for _ in range(10):
        runtime.update(controller, elapsed_seconds=0.016)
        assert controller.session.current_tick == 3
    # Ten repeated same-instant calls must not have restarted the hold timer:
    # exactly 200ms of real time passed, so exactly 300ms should remain.
    assert runtime.hold_remaining_ms(3) == pytest.approx(300.0)


def test_manual_pause_makes_update_a_no_op(tmp_path: Path) -> None:
    session = _ten_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    controller.pause()
    plan = _plan_with_hold_at(3, hold_ms=500)
    runtime = PlaybackDirectorRuntime(plan, clock=FakeClock())

    runtime.update(controller, elapsed_seconds=1.0)
    assert controller.session.current_tick == 0
    assert controller.playing is False
    assert runtime.hold_remaining_ms(3) == 0.0, "a hold must not start ticking while paused"


def test_restart_clears_consumed_holds_so_they_replay(tmp_path: Path) -> None:
    session = _ten_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    controller.session.seek(3)
    plan = _plan_with_hold_at(3, hold_ms=500)
    clock = FakeClock()
    runtime = PlaybackDirectorRuntime(plan, clock=clock)

    runtime.update(controller, elapsed_seconds=0.016)
    clock.advance(0.6)
    runtime.update(controller, elapsed_seconds=0.016)  # clears the hold this frame
    runtime.update(controller, elapsed_seconds=0.15)  # next frame actually advances
    assert controller.session.current_tick == 4  # hold consumed once

    controller.restart()  # PlaybackController.restart() also pauses
    controller.play()
    runtime.restart()
    controller.session.seek(3)
    runtime.update(controller, elapsed_seconds=0.016)
    assert controller.session.current_tick == 3, "after a restart, the same tick's hold must replay"
    clock.advance(0.6)
    runtime.update(controller, elapsed_seconds=0.016)
    runtime.update(controller, elapsed_seconds=0.15)
    assert controller.session.current_tick == 4


def test_leaving_an_unfinished_hold_and_returning_restarts_its_timer(tmp_path: Path) -> None:
    """An interrupted (not-yet-consumed) hold restarts its wait if revisited.

    This is distinct from a *consumed* hold, which never replays without a
    full `restart()` (see the test above) -- the rule is: the plan says a
    hold belongs at this tick; runtime state says only whether *this*
    traversal has already finished waiting it out. Critically, this must
    hold even when the tick visited in between has no hold of its own --
    the abandoned wait must not be measured against the original (now
    irrelevant) start instant just because the tick number happens to
    match again on return.
    """

    session = _ten_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    controller.session.seek(3)
    plan = _plan_with_hold_at(3, hold_ms=500)
    clock = FakeClock()
    runtime = PlaybackDirectorRuntime(plan, clock=clock)

    runtime.update(controller, elapsed_seconds=0.016)
    clock.advance(0.2)  # 200ms into the hold, not yet consumed
    runtime.update(controller, elapsed_seconds=0.016)
    assert runtime.hold_remaining_ms(3) == pytest.approx(300.0)

    # Manual navigation away to an unrelated, hold-free tick, observed by the
    # runtime (a real render loop calls update() every frame regardless of
    # what tick it lands on) -- then back to tick 3, before the hold finished.
    controller.session.seek(1)
    runtime.update(controller, elapsed_seconds=0.001)
    controller.session.seek(3)

    # The very next observation of tick 3 restarts its hold fresh -- full
    # duration remaining again, discarding the abandoned 200ms of progress
    # rather than carrying it forward.
    runtime.update(controller, elapsed_seconds=0.016)
    assert runtime.hold_remaining_ms(3) == pytest.approx(500.0)

    clock.advance(0.2)
    runtime.update(controller, elapsed_seconds=0.016)
    assert controller.session.current_tick == 3, "still holding: only 200ms have passed since the restart"
    assert runtime.hold_remaining_ms(3) == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# DirectorManager: availability and per-mode caching
# ---------------------------------------------------------------------------


def test_manager_is_unavailable_without_a_derivation() -> None:
    manager = DirectorManager(None, unavailable_reason="Director unavailable: no trace supplied.")
    assert manager.available is False
    assert "no trace" in manager.status_message
    assert manager.plan_for(BROADCAST_MODE) is None
    assert manager.runtime_for(BROADCAST_MODE) is None


_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

_HERMIT = _IMPORTS + '''
class Hermit:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="z", reach=1, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, obs.self_anchor)
def create_agent() -> AgentV2:
    return Hermit()
'''


def _write_agent(root: Path, name: str, source: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.py").write_text(source)
    (directory / "agent.yaml").write_text(
        f"name: {name}\ndescription: Phase 7 fixture\nversion: '1.0'\napi_version: 2\n"
    )


def _tiny_derivation(tmp_path: Path):
    _write_agent(tmp_path, "hermit_a", _HERMIT)
    _write_agent(tmp_path, "hermit_b", _HERMIT)
    replay_path = tmp_path / "replay.jsonl"
    trace_path = tmp_path / "trace.jsonl"
    request = MatchRequest(
        config=Config(seed=1, arena_size=32, instr_per_tick=8, win_mode="capture", weights=Weights()),
        entrants=(
            MatchEntrant.python("A", "Entrant A", 0, resolve_agent(tmp_path, "hermit_a")),
            MatchEntrant.python("B", "Entrant B", 16, resolve_agent(tmp_path, "hermit_b")),
        ),
        max_ticks=5,
        replay_path=replay_path,
        trace_path=trace_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    NativeMatchService().run(request)
    return analyze_pair(replay_path, trace_path)


def test_manager_caches_one_plan_and_runtime_per_mode(tmp_path: Path) -> None:
    derivation = _tiny_derivation(tmp_path)
    manager = DirectorManager(derivation)
    assert manager.available is True

    broadcast_plan_1 = manager.plan_for(BROADCAST_MODE)
    broadcast_plan_2 = manager.plan_for(BROADCAST_MODE)
    assert broadcast_plan_1 is broadcast_plan_2, "the same mode must return the cached plan object"

    entrant_plan = manager.plan_for("A")
    assert entrant_plan is not None
    assert entrant_plan is not broadcast_plan_1

    broadcast_runtime_1 = manager.runtime_for(BROADCAST_MODE)
    broadcast_runtime_2 = manager.runtime_for(BROADCAST_MODE)
    assert broadcast_runtime_1 is broadcast_runtime_2
    entrant_runtime = manager.runtime_for("A")
    assert entrant_runtime is not broadcast_runtime_1


def test_manager_restart_clears_every_cached_runtime_independently(tmp_path: Path) -> None:
    derivation = _tiny_derivation(tmp_path)
    manager = DirectorManager(derivation)
    broadcast_runtime = manager.runtime_for(BROADCAST_MODE)
    entrant_runtime = manager.runtime_for("A")
    assert broadcast_runtime is not None and entrant_runtime is not None

    # Poke both runtimes' internal hold bookkeeping directly to prove restart
    # reaches every cached mode, not just the most recently used one.
    broadcast_runtime._consumed_holds.add(1)
    entrant_runtime._consumed_holds.add(1)

    manager.restart()

    assert broadcast_runtime._consumed_holds == set()
    assert entrant_runtime._consumed_holds == set()
