"""Match scheduling and tick execution."""

from __future__ import annotations

from typing import Any, Protocol

from battle_engine.agent_state import Agent
from battle_engine.config import Config
from battle_engine.scheduler import run_sequential_quota
from battle_engine.scoring import ScoreMap, ScoringPolicy
from battle_engine.statistics import StatisticsCollector, StatisticsMap
from battle_engine.telemetry import LegacyRendererObserver, ReplayPublisher
from battle_engine.vm import VM


class MatchState(Protocol):
    cfg: Config
    vm: VM
    instr_per_tick: int
    agents: list[Agent]
    tick: int
    score: ScoreMap
    stats: StatisticsMap
    _alive_prev: dict[str, bool]


class MatchRunner:
    def __init__(
        self,
        state: MatchState,
        replay: ReplayPublisher,
        renderer: LegacyRendererObserver,
        scoring: ScoringPolicy,
        statistics: StatisticsCollector,
    ):
        self.state = state
        self.replay = replay
        self.renderer = renderer
        self.scoring = scoring
        self.statistics = statistics

    def run(self, max_ticks: int, verbose: bool) -> None:
        state = self.state
        try:
            self.replay.publish_header(state.cfg)
            self.renderer.start()
            # Publish initial arena/agent state as tick 0, before any agent
            # has acted. Entrants are already spawned (their code is loaded
            # into the arena) by the time ``run`` is called, so
            # ``state.vm.tick_diffs`` currently holds the code-placement
            # diffs from loading -- publishing them now lets a replay
            # consumer reconstruct starting arena content without a
            # separate snapshot mechanism. The tick-1 iteration below clears
            # ``tick_diffs`` before recording its own writes, so this data
            # is not duplicated into tick 1.
            self.replay.publish_tick(0, state.agents, state.score, state.vm, [])
            for tick in range(1, max_ticks + 1):
                state.tick = tick
                state.vm.clear_tick_diffs()
                events: list[dict[str, Any]] = []

                self._execute_agents()
                self.statistics.record_tick(
                    state.stats, state.agents, state.vm.ownership_counts
                )
                self.scoring.score_alive(state.score, state.agents)
                self.scoring.score_territory(
                    state.score, state.agents, state.vm.ownership_counts
                )
                self._attribute_deaths(events)

                snapshot = self.replay.publish_tick(
                    tick, state.agents, state.score, state.vm, events
                )
                self.renderer.publish_tick(tick, snapshot, state.cfg, state.vm)

                if verbose and (tick % 50 == 0 or tick < 10):
                    alive_ids = [agent.agent_id for agent in state.agents if agent.alive]
                    print(f"[T{tick:05d}] alive={alive_ids} score={state.score}")

                for agent in state.agents:
                    state._alive_prev[agent.agent_id] = agent.alive
                if sum(1 for agent in state.agents if agent.alive) <= 1:
                    break
        finally:
            try:
                self.replay.close()
            finally:
                self.renderer.close()

    def _execute_agents(self) -> None:
        state = self.state
        for agent in state.agents:
            agent.cpu_used = 0

        def execute_slot(agent: Agent, slot: int) -> None:
            del slot
            state.vm.step(agent)
            agent.cpu_used += 1

        run_sequential_quota(state.agents, state.instr_per_tick, execute_slot)

    def _attribute_deaths(self, events: list[dict[str, Any]]) -> None:
        state = self.state
        for agent in state.agents:
            was_alive = state._alive_prev.get(agent.agent_id, True)
            if not (was_alive and not agent.alive):
                continue
            killer = state.vm.writer[agent.pc % len(state.vm.arena)]
            if killer and killer != agent.agent_id:
                self.scoring.score_kill(state.score, killer)
                self.statistics.record_death(state.stats, agent.agent_id, killer)
                events.append({"type": "kill", "victim": agent.agent_id, "by": killer})
            else:
                self.statistics.record_death(state.stats, agent.agent_id)
                events.append({"type": "death", "victim": agent.agent_id})
