"""Restricted deterministic runtime for homogeneous Python-agent matches."""

from __future__ import annotations

import hashlib
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from battle_engine.agent_api import (
    AGENT_API_VERSION,
    ActionKind,
    AgentAction,
    AgentValidationError,
    LoadedPythonAgent,
    MatchContext,
    Observation,
    load_python_agent,
    local_source_fingerprint,
)
from battle_engine.agent_trace import (
    DecisionRecord,
    ResetRecord,
    TraceAction,
    TraceDiagnostic,
    TraceObservation,
    TraceWriter,
)
from battle_engine.config import Config
from battle_engine.results import resolve_winner
from battle_engine.scoring import ScoreMap, ScoringPolicy
from battle_engine.statistics import StatisticsCollector, StatisticsMap
from battle_engine.telemetry import ReplayPublisher, ReplaySink
from battle_engine.vm import VM


class TerminationReason(str, Enum):
    """Internal reason that a completed native match stopped."""

    LAST_AGENT_STANDING = "last_agent_standing"
    ALL_AGENTS_DEAD = "all_agents_dead"
    TICK_LIMIT = "tick_limit"


@dataclass(frozen=True)
class RuntimeDiagnostic:
    """Structured failure detail kept separate from winner resolution."""

    code: str
    stage: str
    message: str
    agent_id: str | None = None
    slot: int | None = None
    exception_type: str | None = None
    tick: int | None = None
    action_slot: int | None = None


def _safe_message(value: object, *, limit: int = 240) -> str:
    """Normalize callback text for concise diagnostics and deterministic replay."""

    message = " ".join(str(value).split())
    return message[:limit] if message else "No error message was provided."


class PythonEntrantInitializationError(ValueError):
    """A Python entrant could not be reset before tick zero."""

    code = "agent_initialization_failed"

    def __init__(self, diagnostic: RuntimeDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class InvalidPythonActionError(ValueError):
    """An ``act`` result is not one valid Phase 3a operation."""


def diagnose_load_failure(
    exc: AgentValidationError, *, agent_id: str, slot: int = 0
) -> RuntimeDiagnostic:
    """Build the stable diagnostic for a load-stage failure.

    Shared by a real match's initialization path and Agent API validation
    (``battle_engine.agent_validation``), so the two report the identical
    code/stage/message for the same underlying ``load_python_agent`` failure.
    """

    return RuntimeDiagnostic(
        code=exc.code,
        stage="load",
        message=_safe_message(exc),
        agent_id=agent_id,
        slot=slot,
        exception_type=type(exc).__name__,
    )


def diagnose_reset_failure(
    exc: Exception, *, agent_id: str, slot: int = 0
) -> RuntimeDiagnostic:
    """Build the stable diagnostic for a reset-stage failure.

    Shared by a real match's initialization path and Agent API validation.
    """

    return RuntimeDiagnostic(
        code="agent_reset_failed",
        stage="reset",
        message=(
            f"Python agent {agent_id} reset failed: "
            f"{type(exc).__name__}: {_safe_message(exc)}"
        ),
        agent_id=agent_id,
        slot=slot,
        exception_type=type(exc).__name__,
    )


def diagnose_action_exception(
    exc: Exception, *, agent_id: str, slot: int = 0, tick: int, action_slot: int
) -> RuntimeDiagnostic:
    """Build the stable diagnostic for an ``act()``-stage exception.

    Shared by a real match's forfeit path and Agent API validation.
    """

    return RuntimeDiagnostic(
        code="agent_action_failed",
        stage="action",
        message=(
            f"Python agent {agent_id} act failed: "
            f"{type(exc).__name__}: {_safe_message(exc)}"
        ),
        agent_id=agent_id,
        slot=slot,
        exception_type=type(exc).__name__,
        tick=tick,
        action_slot=action_slot,
    )


def diagnose_invalid_action(
    exc: InvalidPythonActionError,
    *,
    agent_id: str,
    slot: int = 0,
    tick: int,
    action_slot: int,
) -> RuntimeDiagnostic:
    """Build the stable diagnostic for an ``act()``-stage invalid-action rejection.

    Shared by a real match's forfeit path and Agent API validation.
    """

    return RuntimeDiagnostic(
        code="agent_action_invalid",
        stage="action",
        message=(
            f"Python agent {agent_id} returned an invalid action: {_safe_message(exc)}"
        ),
        agent_id=agent_id,
        slot=slot,
        exception_type=type(exc).__name__,
        tick=tick,
        action_slot=action_slot,
    )


def diagnose_load_timeout(*, agent_id: str, slot: int, timeout: float) -> RuntimeDiagnostic:
    """Build the diagnostic for a supervised worker that did not finish loading in time.

    See ``docs/specs/agent_lab.md`` §7 -- development-time hang
    containment, not a security sandbox.
    """

    return RuntimeDiagnostic(
        code="agent_load_timeout",
        stage="load",
        message=f"Python agent {agent_id} did not finish loading within {timeout:g}s.",
        agent_id=agent_id,
        slot=slot,
    )


def diagnose_reset_timeout(*, agent_id: str, slot: int, timeout: float) -> RuntimeDiagnostic:
    """Build the diagnostic for a supervised worker whose ``reset()`` did not return in time."""

    return RuntimeDiagnostic(
        code="agent_reset_timeout",
        stage="reset",
        message=f"Python agent {agent_id} reset() did not return within {timeout:g}s.",
        agent_id=agent_id,
        slot=slot,
    )


def diagnose_action_timeout(
    *, agent_id: str, slot: int, tick: int, action_slot: int, timeout: float
) -> RuntimeDiagnostic:
    """Build the diagnostic for a supervised worker whose ``act()`` did not return in time."""

    return RuntimeDiagnostic(
        code="agent_action_timeout",
        stage="action",
        message=f"Python agent {agent_id} act() did not return within {timeout:g}s.",
        agent_id=agent_id,
        slot=slot,
        tick=tick,
        action_slot=action_slot,
    )


def diagnose_worker_exited(
    *,
    agent_id: str,
    slot: int,
    stage: str,
    tick: int | None = None,
    action_slot: int | None = None,
    exit_code: int | None = None,
) -> RuntimeDiagnostic:
    """Build the diagnostic for a supervised worker process that exited unexpectedly."""

    suffix = f" (exit code {exit_code})" if exit_code is not None else " (exit code unknown)"
    return RuntimeDiagnostic(
        code="agent_worker_exited",
        stage=stage,
        message=(
            f"Python agent {agent_id}'s supervised worker process exited unexpectedly "
            f"during {stage}{suffix}."
        ),
        agent_id=agent_id,
        slot=slot,
        exception_type="WorkerExited",
        tick=tick,
        action_slot=action_slot,
    )


def diagnose_worker_protocol_error(
    *,
    agent_id: str,
    slot: int,
    stage: str,
    detail: str,
    tick: int | None = None,
    action_slot: int | None = None,
) -> RuntimeDiagnostic:
    """Build the diagnostic for a supervised worker response that could not be parsed."""

    return RuntimeDiagnostic(
        code="agent_worker_protocol_error",
        stage=stage,
        message=(
            f"Python agent {agent_id}'s supervised worker sent an unexpected response "
            f"during {stage}: {detail}"
        ),
        agent_id=agent_id,
        slot=slot,
        exception_type="WorkerProtocolError",
        tick=tick,
        action_slot=action_slot,
    )


def _to_trace_diagnostic(diagnostic: RuntimeDiagnostic | None) -> TraceDiagnostic | None:
    if diagnostic is None:
        return None
    return TraceDiagnostic(
        code=diagnostic.code,
        stage=diagnostic.stage,
        message=diagnostic.message,
        agent_id=diagnostic.agent_id,
        slot=diagnostic.slot,
        exception_type=diagnostic.exception_type,
        tick=diagnostic.tick,
        action_slot=diagnostic.action_slot,
    )


@dataclass
class PythonEntrantState:
    agent_id: str
    name: str
    loaded: LoadedPythonAgent
    rng: random.Random
    slot: int = 0
    derived_seed: int = 0
    source_digest: str = ""
    local_source_fingerprint: str | None = None
    # The agent directory `local_source_fingerprint` was computed from at
    # load time -- retained so a *second*, final fingerprint can be
    # recomputed over the identical deterministic scope once the match
    # finishes (see `local_source_fingerprint_final`), without threading an
    # extra parameter through the whole tick loop.
    agent_dir: Path | None = None
    # A lazy import performed from inside `reset()`/`act()` (a local helper
    # imported only when first needed, rather than at module load time) can
    # change the agent directory's contents *after* the load-time
    # fingerprint above was captured but *before* that lazy import actually
    # executes -- the initial fingerprint alone cannot see this. Computed
    # once, after the match loop has finished (every `act()` call has
    # already happened), over the identical scope as the initial
    # fingerprint. `None` until `PythonEntrantController.run`/
    # `SupervisedPythonEntrantController.run` populates it.
    local_source_fingerprint_final: str | None = None
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
    entrant_termination: str | None = None


@dataclass(frozen=True)
class PythonRuntimeResult:
    winner: str
    ticks_run: int
    score: Mapping[str, int | float]
    states: tuple[PythonEntrantState, ...]
    statistics: StatisticsMap
    termination_reason: TerminationReason


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
    elif action.kind is ActionKind.JUMP or action.kind is ActionKind.JUMP_IF_ZERO and state.zero_flag:
        state.pc = operand & 0xFFFFFFFF


def forfeit_entrant(
    state: PythonEntrantState, diagnostic: RuntimeDiagnostic
) -> dict[str, Any]:
    """Mark one entrant forfeited and build its replay ``forfeit`` event.

    A free function (not a method) so both :class:`PythonEntrantController`
    and :class:`~battle_engine.supervised_runtime.SupervisedPythonEntrantController`
    apply the identical forfeit bookkeeping for an exception, an invalid
    action, or (supervised only) a timeout/worker-crash diagnostic.
    """

    state.alive = False
    state.entrant_termination = "forfeit"
    state.diagnostic = diagnostic
    return {
        "type": "forfeit",
        "victim": state.agent_id,
        "reason": diagnostic.code,
        "stage": diagnostic.stage,
        "tick": diagnostic.tick,
        "action_slot": diagnostic.action_slot,
    }


class PythonEntrantController:
    """Run Python-only entrants with the existing sequential native quota model."""

    def __init__(
        self,
        config: Config,
        entrants: tuple[Any, ...],
        max_ticks: int,
        *,
        trace_writer: TraceWriter | None = None,
    ):
        self.config = config
        self.trace_writer = trace_writer
        if config.arena_size <= 0 or config.instr_per_tick <= 0 or max_ticks <= 0:
            diagnostic = RuntimeDiagnostic(
                code="match_configuration_invalid",
                stage="configuration",
                message="Python matches require positive arena, action budget, and tick limit.",
            )
            raise PythonEntrantInitializationError(diagnostic)
        self.vm = VM(config.arena_size)
        self.max_ticks = max_ticks
        self.states: list[PythonEntrantState] = []
        self.score: ScoreMap = {}
        self.statistics: StatisticsMap = {}
        self.statistics_collector = StatisticsCollector()
        self.scoring = ScoringPolicy(config.weights)

        for slot, entrant in enumerate(entrants):
            try:
                loaded = load_python_agent(entrant.python_spec)
            except AgentValidationError as exc:
                diagnostic = diagnose_load_failure(
                    exc, agent_id=entrant.agent_id, slot=slot
                )
                raise PythonEntrantInitializationError(diagnostic) from exc
            seed = derive_agent_seed(
                config.seed, slot, entrant.agent_id, loaded.metadata.api_version
            )
            state = PythonEntrantState(
                agent_id=entrant.agent_id,
                name=entrant.name,
                loaded=loaded,
                rng=random.Random(seed),
                slot=slot,
                derived_seed=seed,
                source_digest=hashlib.sha256(loaded.source_path.read_bytes()).hexdigest(),
                local_source_fingerprint=local_source_fingerprint(
                    getattr(entrant.python_spec, "dir", None)
                ),
                agent_dir=getattr(entrant.python_spec, "dir", None),
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
            reset_start = time.perf_counter()
            try:
                loaded.instance.reset(context)
            except Exception as exc:
                # Exception, not BaseException: KeyboardInterrupt/SystemExit
                # must propagate and stop the run rather than being reported
                # as an ordinary agent failure (see the matching narrowing
                # in the per-action handler below for the full rationale).
                diagnostic = diagnose_reset_failure(
                    exc, agent_id=entrant.agent_id, slot=slot
                )
                self._trace_reset(entrant.agent_id, reset_start, diagnostic)
                raise PythonEntrantInitializationError(diagnostic) from exc
            self._trace_reset(entrant.agent_id, reset_start, None)
            self.states.append(state)
            self.score[entrant.agent_id] = 0
            self.statistics_collector.initialize_agent(
                self.statistics, entrant.agent_id
            )

    def _trace_reset(
        self, agent_id: str, start: float, diagnostic: RuntimeDiagnostic | None
    ) -> None:
        if self.trace_writer is None:
            return
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.trace_writer.write_reset(
            ResetRecord(
                agent_id=agent_id,
                wall_time_ms=elapsed_ms,
                diagnostic=_to_trace_diagnostic(diagnostic),
            )
        )

    def _trace_decision(
        self,
        state: PythonEntrantState,
        tick: int,
        action_slot: int,
        start: float,
        observation: Observation,
        action: AgentAction | None,
        diagnostic: RuntimeDiagnostic | None,
    ) -> None:
        if self.trace_writer is None:
            return
        elapsed_ms = (time.perf_counter() - start) * 1000
        trace_action = (
            None
            if action is None
            else TraceAction(kind=action.kind.value, operand=action.operand, value=action.value)
        )
        self.trace_writer.write_decision(
            DecisionRecord(
                tick=tick,
                agent_id=state.agent_id,
                action_slot=action_slot,
                wall_time_ms=elapsed_ms,
                observation=TraceObservation(
                    tick=observation.tick,
                    agent_id=observation.agent_id,
                    pc=observation.pc,
                    register_a=observation.register_a,
                    register_p=observation.register_p,
                    zero_flag=observation.zero_flag,
                    last_read=observation.last_read,
                    alive=observation.alive,
                ),
                action=trace_action,
                diagnostic=_to_trace_diagnostic(diagnostic),
            )
        )

    def _forfeit(
        self, state: PythonEntrantState, diagnostic: RuntimeDiagnostic
    ) -> dict[str, Any]:
        return forfeit_entrant(state, diagnostic)

    def run(self, sink: ReplaySink, *, verbose: bool) -> PythonRuntimeResult:
        replay = ReplayPublisher(sink)
        ticks_run = 0
        try:
            replay.publish_header(self.config)
            # Publish initial entrant state as tick 0, before any act()
            # call. Python entrants never populate the arena (source is not
            # loaded into memory), so memory_diffs is empty here, but the
            # per-entrant starting pc/region/registers are still captured --
            # see match.py's MatchRunner.run for the VM-side counterpart.
            replay.publish_tick(
                0, self.states, self.score, self.vm, []  # type: ignore[arg-type]
            )
            for tick in range(1, self.max_ticks + 1):
                ticks_run = tick
                self.vm.clear_tick_diffs()
                events: list[dict[str, Any]] = []
                for state in self.states:
                    state.cpu_used = 0
                for state in self.states:
                    if not state.alive:
                        continue
                    for action_slot in range(self.config.instr_per_tick):
                        if not state.alive:
                            break
                        observation = _observation(tick, state)
                        act_start = time.perf_counter()
                        try:
                            action = state.loaded.instance.act(observation)
                            state.cpu_used += 1
                            state.total_actions += 1
                            self._trace_decision(
                                state, tick, action_slot, act_start, observation, action, None
                            )
                            apply_action(action, state, self.vm)
                            if action.kind is ActionKind.HALT:
                                state.entrant_termination = "normal_halt"
                                events.append({"type": "death", "victim": state.agent_id})
                        except InvalidPythonActionError as exc:
                            diagnostic = diagnose_invalid_action(
                                exc,
                                agent_id=state.agent_id,
                                slot=state.slot,
                                tick=tick,
                                action_slot=action_slot,
                            )
                            self._trace_decision(
                                state, tick, action_slot, act_start, observation, None, diagnostic
                            )
                            events.append(self._forfeit(state, diagnostic))
                        except Exception as exc:
                            # Exception, not BaseException: an operator's
                            # Ctrl-C (KeyboardInterrupt) or an agent's own
                            # sys.exit() (SystemExit) must propagate and
                            # actually stop the match, not be silently
                            # absorbed as a routine agent forfeit -- that
                            # was previously the only way to abort a hung
                            # or runaway Python match short of SIGKILL.
                            state.cpu_used += 1
                            state.total_actions += 1
                            diagnostic = diagnose_action_exception(
                                exc,
                                agent_id=state.agent_id,
                                slot=state.slot,
                                tick=tick,
                                action_slot=action_slot,
                            )
                            self._trace_decision(
                                state, tick, action_slot, act_start, observation, None, diagnostic
                            )
                            events.append(self._forfeit(state, diagnostic))

                self.statistics_collector.record_tick(
                    self.statistics,
                    self.states,  # type: ignore[arg-type]
                    self.vm.ownership_counts,
                )
                self.scoring.score_alive(self.score, self.states)  # type: ignore[arg-type]
                self.scoring.score_territory(
                    self.score,
                    self.states,  # type: ignore[arg-type]
                    self.vm.ownership_counts,
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

        # A lazy import performed from inside reset()/act() can change the
        # agent directory's contents after the load-time fingerprint was
        # captured but before that lazy import actually executes -- so a
        # second, final fingerprint is computed here, now that every
        # act() call for this match has already happened, over the
        # identical deterministic scope as the initial one.
        for state in self.states:
            state.local_source_fingerprint_final = local_source_fingerprint(state.agent_dir)

        alive_count = sum(state.alive for state in self.states)
        if alive_count == 0:
            termination_reason = TerminationReason.ALL_AGENTS_DEAD
        elif alive_count == 1:
            termination_reason = TerminationReason.LAST_AGENT_STANDING
        else:
            termination_reason = TerminationReason.TICK_LIMIT
        winner = resolve_winner(self.states, self.score, self.config.win_mode)
        return PythonRuntimeResult(
            winner=winner,
            ticks_run=ticks_run,
            score=MappingProxyType(dict(self.score)),
            states=tuple(self.states),
            statistics=self.statistics,
            termination_reason=termination_reason,
        )


__all__ = [
    "InvalidPythonActionError",
    "PythonEntrantController",
    "PythonEntrantInitializationError",
    "PythonEntrantState",
    "PythonRuntimeResult",
    "RuntimeDiagnostic",
    "TerminationReason",
    "apply_action",
    "derive_agent_seed",
    "diagnose_action_exception",
    "diagnose_action_timeout",
    "diagnose_invalid_action",
    "diagnose_load_failure",
    "diagnose_load_timeout",
    "diagnose_reset_failure",
    "diagnose_reset_timeout",
    "diagnose_worker_exited",
    "diagnose_worker_protocol_error",
    "forfeit_entrant",
    "validate_action",
]
