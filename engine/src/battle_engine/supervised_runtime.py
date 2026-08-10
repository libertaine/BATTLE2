"""Whole-match-lifetime worker-subprocess execution for Python entrants.

Same authoritative match semantics as
:class:`~battle_engine.python_runtime.PythonEntrantController` -- action
execution, tick scheduling, and scoring are the identical engine-owned
code (:func:`battle_engine.python_runtime.apply_action` and this module's
own copy of the tick loop shape). Only *production* -- the ``load``/
``reset``/``act`` calls themselves -- is relocated into one
:class:`~battle_engine.agent_worker.AgentWorkerHandle` subprocess per
entrant, with a per-call timeout. See ``docs/specs/agent_lab.md``
§4/§6/§7 for the full design rationale.

This module is a deliberate, reviewed near-duplicate of
:class:`~battle_engine.python_runtime.PythonEntrantController`'s per-tick
loop rather than a shared-base refactor of that already heavily tested
class -- the two controllers' failure handling differs enough (exception
narrowing vs. timeout/crash/protocol-error handling) that unifying them
risked the unsupervised path's existing coverage for a purely
development-time-only benefit. See the design spec's "strongest argument
against this architecture" section for the full tradeoff discussion.

Development-time hang containment, not a security sandbox -- see
``docs/specs/agent_lab.md`` §17 and :mod:`battle_engine.agent_worker`.
"""

from __future__ import annotations

import hashlib
import random
import time
from pathlib import Path
from types import MappingProxyType
from typing import Any

from battle_engine.agent_api import (
    ActionKind,
    AgentAction,
    AgentMetadata,
    LoadedPythonAgent,
    MatchContext,
    Observation,
    local_source_fingerprint,
)
from battle_engine.agent_trace import (
    DecisionRecord,
    ResetRecord,
    TraceAction,
    TraceObservation,
    TraceWriter,
)
from battle_engine.agent_worker import AgentWorkerHandle, WorkerCallResult, WorkerCallStatus
from battle_engine.config import Config
from battle_engine.python_runtime import (
    InvalidPythonActionError,
    PythonEntrantInitializationError,
    PythonEntrantState,
    PythonRuntimeResult,
    RuntimeDiagnostic,
    TerminationReason,
    _observation,
    _to_trace_diagnostic,
    apply_action,
    derive_agent_seed,
    diagnose_action_timeout,
    diagnose_invalid_action,
    diagnose_load_timeout,
    diagnose_reset_timeout,
    diagnose_worker_exited,
    diagnose_worker_protocol_error,
    forfeit_entrant,
)
from battle_engine.results import resolve_winner
from battle_engine.scoring import ScoreMap, ScoringPolicy
from battle_engine.statistics import StatisticsCollector, StatisticsMap
from battle_engine.telemetry import ReplayPublisher, ReplaySink
from battle_engine.vm import VM


class _NullAgentInstance:
    """Placeholder for ``LoadedPythonAgent.instance`` in supervised mode.

    The real agent instance lives inside the worker subprocess. Nothing in
    this module ever calls through this placeholder; it exists only so
    ``LoadedPythonAgent``/``PythonEntrantState`` keep their existing shape
    for code (``match_service._build_python_result``) that reads
    ``state.loaded.metadata`` uniformly regardless of which controller
    produced the state. Any accidental call fails loudly rather than
    silently misbehaving.
    """

    def reset(self, context: MatchContext) -> None:
        raise RuntimeError("supervised entrant instance is not directly callable")

    def act(self, observation: Observation) -> Any:
        raise RuntimeError("supervised entrant instance is not directly callable")


def _diagnostic_from_payload(payload: dict[str, Any] | None) -> RuntimeDiagnostic:
    data = (payload or {}).get("diagnostic") or {}
    return RuntimeDiagnostic(
        code=data.get("code", "agent_worker_protocol_error"),
        stage=data.get("stage", "internal"),
        message=data.get("message", "Worker reported a failure with no diagnostic detail."),
        agent_id=data.get("agent_id"),
        slot=data.get("slot"),
        exception_type=data.get("exception_type"),
        tick=data.get("tick"),
        action_slot=data.get("action_slot"),
    )


def diagnostic_for_worker_result(
    result: WorkerCallResult,
    *,
    agent_id: str,
    slot: int,
    stage: str,
    timeout: float,
    exit_code: int | None,
    tick: int | None = None,
    action_slot: int | None = None,
) -> RuntimeDiagnostic:
    """Map one non-OK :class:`WorkerCallResult` to the matching diagnostic.

    Shared by :class:`SupervisedPythonEntrantController` (a whole
    development match) and :mod:`battle_engine.agent_validation` (a single
    supervised dry-run call), so both report identical codes/messages for
    the same underlying worker failure -- the same "reuse-enabling
    extraction" pattern ``diagnose_load_failure``/``diagnose_reset_failure``
    already established for the unsupervised path (see
    ``docs/specs/agent_validation.md`` §2).
    """

    if result.status is WorkerCallStatus.FAILED:
        return _diagnostic_from_payload(result.payload)
    if result.status is WorkerCallStatus.TIMEOUT:
        if stage == "load":
            return diagnose_load_timeout(agent_id=agent_id, slot=slot, timeout=timeout)
        if stage == "reset":
            return diagnose_reset_timeout(agent_id=agent_id, slot=slot, timeout=timeout)
        return diagnose_action_timeout(
            agent_id=agent_id, slot=slot, tick=tick or 0, action_slot=action_slot or 0, timeout=timeout
        )
    if result.status is WorkerCallStatus.EXITED:
        return diagnose_worker_exited(
            agent_id=agent_id, slot=slot, stage=stage, tick=tick, action_slot=action_slot,
            exit_code=exit_code,
        )
    detail = str((result.payload or {}).get("raw", "unparseable response"))
    return diagnose_worker_protocol_error(
        agent_id=agent_id, slot=slot, stage=stage, detail=detail, tick=tick, action_slot=action_slot
    )


class SupervisedPythonEntrantController:
    """Run Python-only entrants through one worker subprocess each, with a timeout."""

    def __init__(
        self,
        config: Config,
        entrants: tuple[Any, ...],
        max_ticks: int,
        *,
        agent_call_timeout: float,
        trace_writer: TraceWriter | None = None,
    ) -> None:
        self.config = config
        self.trace_writer = trace_writer
        self.agent_call_timeout = agent_call_timeout
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
        self.handles: dict[str, AgentWorkerHandle] = {}
        self.score: ScoreMap = {}
        self.statistics: StatisticsMap = {}
        self.statistics_collector = StatisticsCollector()
        self.scoring = ScoringPolicy(config.weights)

        try:
            for slot, entrant in enumerate(entrants):
                self._initialize_entrant(slot, entrant)
        except BaseException:
            self._close_all_handles()
            raise

    def _initialize_entrant(self, slot: int, entrant: Any) -> None:
        handle = AgentWorkerHandle(agent_id=entrant.agent_id, slot=slot)
        handle.start()
        self.handles[entrant.agent_id] = handle

        load_result = handle.load(entrant.python_spec, timeout=self.agent_call_timeout)
        if load_result.status is not WorkerCallStatus.OK:
            diagnostic = self._diagnostic_for_failure(
                load_result, agent_id=entrant.agent_id, slot=slot, stage="load"
            )
            handle.kill()
            raise PythonEntrantInitializationError(diagnostic)

        assert load_result.payload is not None
        metadata_payload = load_result.payload["metadata"]
        source_path = Path(load_result.payload["source_path"])
        try:
            source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        except OSError as exc:
            diagnostic = RuntimeDiagnostic(
                code="agent_source_invalid",
                stage="load",
                message=f"Could not read loaded Python agent source {source_path}: {exc}",
                agent_id=entrant.agent_id,
                slot=slot,
            )
            handle.kill()
            raise PythonEntrantInitializationError(diagnostic) from exc

        api_version = metadata_payload["api_version"]
        seed = derive_agent_seed(self.config.seed, slot, entrant.agent_id, api_version)
        loaded_stub = LoadedPythonAgent(
            metadata=AgentMetadata(
                agent_id=entrant.agent_id,
                name=metadata_payload["name"],
                version=metadata_payload["version"],
                api_version=api_version,
            ),
            instance=_NullAgentInstance(),
            source_path=source_path,
            entry_point=getattr(entrant.python_spec, "entry_point", "") or "",
        )
        state = PythonEntrantState(
            agent_id=entrant.agent_id,
            name=entrant.name,
            loaded=loaded_stub,
            rng=random.Random(seed),
            slot=slot,
            derived_seed=seed,
            source_digest=source_digest,
            local_source_fingerprint=local_source_fingerprint(
                getattr(entrant.python_spec, "dir", None)
            ),
            agent_dir=getattr(entrant.python_spec, "dir", None),
            pc=entrant.start & 0xFFFFFFFF,
            region=(entrant.start % self.config.arena_size,) * 2,
        )

        reset_start = time.perf_counter()
        reset_result = handle.reset(
            match_seed=self.config.seed,
            api_version=api_version,
            arena_size=self.config.arena_size,
            tick_limit=self.max_ticks,
            action_budget=self.config.instr_per_tick,
            timeout=self.agent_call_timeout,
        )
        if reset_result.status is not WorkerCallStatus.OK:
            diagnostic = self._diagnostic_for_failure(
                reset_result, agent_id=entrant.agent_id, slot=slot, stage="reset"
            )
            self._trace_reset(entrant.agent_id, reset_start, diagnostic)
            handle.kill()
            raise PythonEntrantInitializationError(diagnostic)
        self._trace_reset(entrant.agent_id, reset_start, None)

        self.states.append(state)
        self.score[entrant.agent_id] = 0
        self.statistics_collector.initialize_agent(self.statistics, entrant.agent_id)

    def _diagnostic_for_failure(
        self,
        result: WorkerCallResult,
        *,
        agent_id: str,
        slot: int,
        stage: str,
        tick: int | None = None,
        action_slot: int | None = None,
    ) -> RuntimeDiagnostic:
        return diagnostic_for_worker_result(
            result,
            agent_id=agent_id,
            slot=slot,
            stage=stage,
            timeout=self.agent_call_timeout,
            exit_code=self.handles[agent_id].exit_code,
            tick=tick,
            action_slot=action_slot,
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
        action: TraceAction | None,
        diagnostic: RuntimeDiagnostic | None,
    ) -> None:
        if self.trace_writer is None:
            return
        elapsed_ms = (time.perf_counter() - start) * 1000
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
                action=action,
                diagnostic=_to_trace_diagnostic(diagnostic),
            )
        )

    def _close_all_handles(self) -> None:
        for handle in self.handles.values():
            handle.close()

    def run(self, sink: ReplaySink, *, verbose: bool) -> PythonRuntimeResult:
        replay = ReplayPublisher(sink)
        ticks_run = 0
        try:
            replay.publish_header(self.config)
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
                    handle = self.handles[state.agent_id]
                    for action_slot in range(self.config.instr_per_tick):
                        if not state.alive:
                            break
                        self._run_one_action(handle, state, tick, action_slot, events)

                self.statistics_collector.record_tick(
                    self.statistics, self.states, self.vm.writer  # type: ignore[arg-type]
                )
                self.scoring.score_alive(self.score, self.states)  # type: ignore[arg-type]
                self.scoring.score_territory(
                    self.score, self.states, self.vm.writer  # type: ignore[arg-type]
                )
                replay.publish_tick(
                    tick, self.states, self.score, self.vm, events  # type: ignore[arg-type]
                )
                if verbose and (tick % 50 == 0 or tick < 10):
                    alive = [state.agent_id for state in self.states if state.alive]
                    print(f"[T{tick:05d}] alive={alive} score={self.score}")
                if sum(state.alive for state in self.states) <= 1:
                    break
        finally:
            replay.close()
            self._close_all_handles()

        # See python_runtime.PythonEntrantController.run's identical
        # comment: a lazy import from inside reset()/act() (executed in the
        # worker subprocess, but sharing this process's filesystem view)
        # can change the agent directory's contents after the load-time
        # fingerprint was captured but before that lazy import actually
        # executes -- recomputed here, over the identical scope, now that
        # every act() call for this match has already happened.
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

    def _run_one_action(
        self,
        handle: AgentWorkerHandle,
        state: PythonEntrantState,
        tick: int,
        action_slot: int,
        events: list[dict[str, Any]],
    ) -> None:
        observation = _observation(tick, state)
        act_start = time.perf_counter()
        act_result = handle.act(observation, action_slot=action_slot, timeout=self.agent_call_timeout)
        state.cpu_used += 1
        state.total_actions += 1

        if act_result.status is not WorkerCallStatus.OK:
            diagnostic = self._diagnostic_for_failure(
                act_result, agent_id=state.agent_id, slot=state.slot, stage="action",
                tick=tick, action_slot=action_slot,
            )
            self._trace_decision(state, tick, action_slot, act_start, observation, None, diagnostic)
            events.append(forfeit_entrant(state, diagnostic))
            handle.kill()
            return

        assert act_result.payload is not None
        action_payload = act_result.payload.get("action")
        if action_payload is None:
            # The worker reported "not a valid AgentAction shape" -- reproduce
            # the exact validate_action rejection an in-process call would
            # hit for the same malformed return value.
            exc = InvalidPythonActionError("act() must return one AgentAction")
            diagnostic = diagnose_invalid_action(
                exc, agent_id=state.agent_id, slot=state.slot, tick=tick, action_slot=action_slot
            )
            self._trace_decision(state, tick, action_slot, act_start, observation, None, diagnostic)
            events.append(forfeit_entrant(state, diagnostic))
            return

        action = AgentAction(
            kind=ActionKind(action_payload["kind"]),
            operand=action_payload.get("operand"),
            value=action_payload.get("value"),
        )
        trace_action = TraceAction(
            kind=action_payload["kind"],
            operand=action_payload.get("operand"),
            value=action_payload.get("value"),
        )
        try:
            apply_action(action, state, self.vm)
        except InvalidPythonActionError as exc:
            diagnostic = diagnose_invalid_action(
                exc, agent_id=state.agent_id, slot=state.slot, tick=tick, action_slot=action_slot
            )
            self._trace_decision(state, tick, action_slot, act_start, observation, trace_action, diagnostic)
            events.append(forfeit_entrant(state, diagnostic))
            return

        self._trace_decision(state, tick, action_slot, act_start, observation, trace_action, None)
        if action.kind is ActionKind.HALT:
            state.entrant_termination = "normal_halt"
            events.append({"type": "death", "victim": state.agent_id})


__all__ = ["SupervisedPythonEntrantController", "diagnostic_for_worker_result"]
