"""Restricted deterministic runtime for homogeneous Python-agent matches."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from battle_engine.agent_api import (
    AGENT_API_VERSION,
    ActionKind,
    AgentAction,
    LoadedPythonAgent,
    MatchContext,
    Observation,
    load_python_agent,
)
from battle_engine.config import Config
from battle_engine.results import resolve_winner
from battle_engine.scoring import ScoreMap, ScoringPolicy
from battle_engine.statistics import StatisticsCollector, StatisticsMap
from battle_engine.telemetry import ReplayPublisher, ReplaySink
from battle_engine.vm import VM


@dataclass(frozen=True)
class RuntimeDiagnostic:
    code: str
    agent_id: str
    message: str


class PythonEntrantInitializationError(ValueError):
    """A Python entrant could not be reset before tick zero."""

    code = "python_reset_failed"

    def __init__(self, diagnostic: RuntimeDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class InvalidPythonActionError(ValueError):
    """An ``act`` result is not one valid Phase 3a operation."""


@dataclass
class PythonEntrantState:
    agent_id: str
    name: str
    loaded: LoadedPythonAgent
    rng: random.Random
    pc: int = 0
    register_a: int = 0
    register_p: int = 0
    zero_flag: bool = False
    last_read: int | None = None
    alive: bool = True
    cpu_used: int = 0
    total_actions: int = 0
    mem_writes: int = 0
    region: tuple[int, int] = (0, 0)
    diagnostic: RuntimeDiagnostic | None = None


@dataclass(frozen=True)
class PythonRuntimeResult:
    winner: str
    ticks_run: int
    score: Mapping[str, int | float]
    states: tuple[PythonEntrantState, ...]
    statistics: StatisticsMap


def derive_agent_seed(
    match_seed: int, slot: int, agent_id: str, api_version: int = AGENT_API_VERSION
) -> int:
    """Derive one stable independent RNG seed without Python's randomized hash."""

    material = f"battle2-python-v1\0{match_seed}\0{slot}\0{agent_id}\0{api_version}"
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:16], "big")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidPythonActionError(f"{label} must be an integer")
    return value


def validate_action(action: object) -> AgentAction:
    """Validate one action and reject irrelevant or malformed operands."""

    if not isinstance(action, AgentAction):
        raise InvalidPythonActionError("act() must return one AgentAction")
    if not isinstance(action.kind, ActionKind):
        raise InvalidPythonActionError("action kind is unsupported")

    no_operand = {ActionKind.NOP, ActionKind.HALT}
    one_operand = {
        ActionKind.SET_A,
        ActionKind.ADD_A,
        ActionKind.READ,
        ActionKind.SET_P,
        ActionKind.ADD_P,
        ActionKind.JUMP,
        ActionKind.JUMP_IF_ZERO,
    }
    if action.kind in no_operand:
        if action.operand is not None or action.value is not None:
            raise InvalidPythonActionError(f"{action.kind.value} takes no operands")
    elif action.kind in one_operand:
        _integer(action.operand, f"{action.kind.value} operand")
        if action.value is not None:
            raise InvalidPythonActionError(f"{action.kind.value} takes one operand")
    elif action.kind is ActionKind.WRITE:
        _integer(action.operand, "write address")
        _integer(action.value, "write value")
    else:  # Defensive if the enum grows without runtime semantics.
        raise InvalidPythonActionError(f"unsupported action: {action.kind!r}")
    return action


def _observation(tick: int, state: PythonEntrantState) -> Observation:
    return Observation(
        tick=tick,
        agent_id=state.agent_id,
        pc=state.pc,
        register_a=state.register_a,
        register_p=state.register_p,
        zero_flag=state.zero_flag,
        last_read=state.last_read,
        alive=state.alive,
    )


def apply_action(action: AgentAction, state: PythonEntrantState, vm: VM) -> None:
    """Apply one validated action to engine-owned state and the shared arena."""

    action = validate_action(action)
    operand = action.operand
    if action.kind is ActionKind.NOP:
        return
    if action.kind is ActionKind.HALT:
        state.alive = False
        return
    assert operand is not None
    if action.kind is ActionKind.SET_A:
        state.register_a = operand & 0xFFFFFFFF
    elif action.kind is ActionKind.ADD_A:
        state.register_a = (state.register_a + operand) & 0xFFFFFFFF
        state.zero_flag = state.register_a == 0
    elif action.kind is ActionKind.READ:
        value = vm.arena[operand % len(vm.arena)]
        state.last_read = value
        state.register_a = value
        state.zero_flag = value == 0
    elif action.kind is ActionKind.WRITE:
        assert action.value is not None
        vm._wr8(operand, action.value, state.agent_id)
        state.mem_writes += 1
    elif action.kind is ActionKind.SET_P:
        state.register_p = operand & 0xFFFFFFFF
    elif action.kind is ActionKind.ADD_P:
        state.register_p = (state.register_p + operand) & 0xFFFFFFFF
    elif action.kind is ActionKind.JUMP:
        state.pc = operand & 0xFFFFFFFF
    elif action.kind is ActionKind.JUMP_IF_ZERO and state.zero_flag:
        state.pc = operand & 0xFFFFFFFF


class PythonEntrantController:
    """Run Python-only entrants with the existing sequential native quota model."""

    def __init__(self, config: Config, entrants: tuple[Any, ...], max_ticks: int):
        self.config = config
        self.vm = VM(config.arena_size)
        self.max_ticks = max_ticks
        self.states: list[PythonEntrantState] = []
        self.score: ScoreMap = {}
        self.statistics: StatisticsMap = {}
        self.statistics_collector = StatisticsCollector()
        self.scoring = ScoringPolicy(config.weights)

        for slot, entrant in enumerate(entrants):
            loaded = load_python_agent(entrant.python_spec)
            seed = derive_agent_seed(
                config.seed, slot, entrant.agent_id, loaded.metadata.api_version
            )
            state = PythonEntrantState(
                agent_id=entrant.agent_id,
                name=entrant.name,
                loaded=loaded,
                rng=random.Random(seed),
                pc=entrant.start & 0xFFFFFFFF,
                region=(entrant.start % config.arena_size,) * 2,
            )
            context = MatchContext(
                agent_id=entrant.agent_id,
                seed=seed,
                arena_size=config.arena_size,
                tick_limit=max_ticks,
                action_budget=config.instr_per_tick,
                rng=state.rng,
            )
            try:
                loaded.instance.reset(context)
            except BaseException as exc:
                diagnostic = RuntimeDiagnostic(
                    "python_reset_failed",
                    entrant.agent_id,
                    f"Python agent {entrant.agent_id} reset failed: {type(exc).__name__}: {exc}",
                )
                raise PythonEntrantInitializationError(diagnostic) from exc
            self.states.append(state)
            self.score[entrant.agent_id] = 0
            self.statistics_collector.initialize_agent(
                self.statistics, entrant.agent_id
            )

    def _forfeit(
        self, state: PythonEntrantState, code: str, message: str
    ) -> dict[str, str]:
        state.alive = False
        state.diagnostic = RuntimeDiagnostic(code, state.agent_id, message)
        return {"type": "forfeit", "victim": state.agent_id, "reason": code, "message": message}

    def run(self, sink: ReplaySink, *, verbose: bool) -> PythonRuntimeResult:
        replay = ReplayPublisher(sink)
        ticks_run = 0
        try:
            replay.publish_header(self.config)
            for tick in range(1, self.max_ticks + 1):
                ticks_run = tick
                self.vm.clear_tick_diffs()
                events: list[dict[str, Any]] = []
                for state in self.states:
                    state.cpu_used = 0
                for state in self.states:
                    if not state.alive:
                        continue
                    for _ in range(self.config.instr_per_tick):
                        if not state.alive:
                            break
                        try:
                            action = state.loaded.instance.act(_observation(tick, state))
                            state.cpu_used += 1
                            state.total_actions += 1
                            apply_action(action, state, self.vm)
                            if action.kind is ActionKind.HALT:
                                events.append({"type": "death", "victim": state.agent_id})
                        except InvalidPythonActionError as exc:
                            events.append(
                                self._forfeit(
                                    state,
                                    "python_action_invalid",
                                    f"Python agent {state.agent_id} returned an "
                                    f"invalid action: {exc}",
                                )
                            )
                        except BaseException as exc:
                            state.cpu_used += 1
                            state.total_actions += 1
                            events.append(
                                self._forfeit(
                                    state,
                                    "python_act_failed",
                                    f"Python agent {state.agent_id} act failed: "
                                    f"{type(exc).__name__}: {exc}",
                                )
                            )

                self.statistics_collector.record_tick(
                    self.statistics, self.states, self.vm.writer  # type: ignore[arg-type]
                )
                self.scoring.score_alive(self.score, self.states)  # type: ignore[arg-type]
                self.scoring.score_territory(
                    self.score, self.states, self.vm.writer  # type: ignore[arg-type]
                )
                replay.publish_tick(
                    tick,
                    self.states,  # type: ignore[arg-type]
                    self.score,
                    self.vm,
                    events,
                )
                if verbose and (tick % 50 == 0 or tick < 10):
                    alive = [state.agent_id for state in self.states if state.alive]
                    print(f"[T{tick:05d}] alive={alive} score={self.score}")
                if sum(state.alive for state in self.states) <= 1:
                    break
        finally:
            replay.close()

        winner = resolve_winner(  # type: ignore[arg-type]
            self.states, self.score, self.config.win_mode
        )
        return PythonRuntimeResult(
            winner=winner,
            ticks_run=ticks_run,
            score=MappingProxyType(dict(self.score)),
            states=tuple(self.states),
            statistics=self.statistics,
        )


__all__ = [
    "InvalidPythonActionError",
    "PythonEntrantController",
    "PythonEntrantInitializationError",
    "PythonEntrantState",
    "PythonRuntimeResult",
    "RuntimeDiagnostic",
    "apply_action",
    "derive_agent_seed",
    "validate_action",
]
