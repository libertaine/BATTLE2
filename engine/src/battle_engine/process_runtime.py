"""Canonical Bytefray v4 spatial-process runtime.

The R0-R6 research harness and the product execution path intentionally share
this implementation.  ``NativeMatchService`` constructs production entrants
through :meth:`ProcessMatchController.from_python_entrants`; focused mechanic
tests may still construct explicit :class:`ProcessEntrantSpec` objects.
"""

from __future__ import annotations

import enum
import hashlib
import math
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

from battle_engine.agent_api import (
    ActionKind,
    ActionKindV2,
    AgentAction,
    AgentV2,
    AgentValidationError,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
    load_python_agent,
    local_source_fingerprint,
)
from battle_engine.agent_worker import AgentWorkerHandle, WorkerCallStatus
from battle_engine.config import Config
from battle_engine.python_runtime import (
    PythonEntrantInitializationError,
    RuntimeDiagnostic,
    apply_core_capture,
    derive_agent_seed,
    diagnose_action_exception,
    diagnose_load_failure,
    diagnose_reset_failure,
)
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1, RulesetPolicy
from battle_engine.scoring import ScoreMap, ScoringPolicy
from battle_engine.statistics import StatisticsCollector, StatisticsMap
from battle_engine.telemetry import ReplayPublisher, ReplaySink
from battle_engine.vm import VM


class ProcessRole(str, enum.Enum):
    DEFENDER = "defender"
    HUNTER = "hunter"
    SCOUT = "scout"
    ATTACKER = "attacker"
    EXPANDER = "expander"
    GENERALIST = "generalist"


@dataclass
class ProcessTelemetry:
    process_id: str
    role: str
    total_actions: int = 0
    total_moves: int = 0
    total_reads: int = 0
    total_writes: int = 0
    total_passes: int = 0
    disruption_hits_received: int = 0
    total_disrupted_ticks: int = 0
    disrupted_match_ticks: set[int] = field(default_factory=set)
    positions_visited: set[int] = field(default_factory=set)
    addresses_read: set[int] = field(default_factory=set)
    addresses_written: set[int] = field(default_factory=set)


class ProcessInstance:
    """A logical process entity owned by an entrant."""

    def __init__(
        self,
        process_id: str,
        role: ProcessRole,
        initial_position: int | None,
        reach: int | None,
        quota_share: int | Fraction,
        logic: Callable[[ObservationV2, dict[str, Any]], AgentAction],
        *,
        executor: Callable[[ObservationV2, int], AgentAction] | None = None,
    ):
        self.process_id = process_id
        self.role = role
        self.position = initial_position
        self.reach = reach
        self.quota_share = quota_share  # Max actions per tick for this process
        self.logic = logic
        self.executor = executor
        self.local_state: dict[str, Any] = {}
        self.telemetry = ProcessTelemetry(process_id=process_id, role=role.value)
        self.disrupted_until_tick = 0
        if initial_position is not None:
            self.telemetry.positions_visited.add(initial_position)

    def is_disrupted(self, tick: int) -> bool:
        return tick < self.disrupted_until_tick

    def reset(self) -> None:
        self.local_state.clear()
        self.disrupted_until_tick = 0
        if self.position is not None:
            self.telemetry.positions_visited.add(self.position)

    def act(self, obs: ObservationV2, action_slot: int = 0) -> AgentAction:
        if self.executor is not None:
            return self.executor(obs, action_slot)
        return self.logic(obs, self.local_state)


@dataclass
class ProcessEntrantSpec:
    """Specification for a multi-process entrant."""
    agent_id: str
    name: str
    processes: list[ProcessInstance]
    allocation_policy: str = "fixed"  # "fixed" (uses quota_share) or "dynamic"
    start: int | None = None
    normalized_shares: bool = False
    api_version: int = 2
    agent_version: str = "0"
    source_path: Path | None = None
    entry_point: str = ""
    derived_seed: int = 0
    source_digest: str = ""
    local_source_fingerprint: str | None = None
    local_source_fingerprint_final: str | None = None
    agent_dir: Path | None = None


@dataclass
class EntrantState:
    agent_id: str
    slot: int
    core_base: int
    core_size: int
    core_cells: tuple[int, ...]
    alive: bool = True
    cpu_used: int = 0
    total_actions: int = 0
    mem_writes: int = 0
    pc: int = 0
    region: tuple[int, int] = (0, 0)
    register_a: int = 0
    register_p: int = 0
    zero_flag: bool = False
    last_read: int | None = None
    diagnostic: RuntimeDiagnostic | None = None
    entrant_termination: str | None = None

    @property
    def core_start(self) -> int:
        return self.core_base


class ProcessAgentCallError(RuntimeError):
    """A supervised API-v2 callback failed with a stable diagnostic."""

    def __init__(self, diagnostic: RuntimeDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic



class ProcessMatchController:
    """Executes a match between multi-process and/or single-process entrants."""

    @staticmethod
    def _initialization_error(
        *,
        code: str,
        message: str,
        agent_id: str | None = None,
        slot: int | None = None,
        stage: str = "declaration",
        exception_type: str | None = None,
    ) -> PythonEntrantInitializationError:
        return PythonEntrantInitializationError(
            RuntimeDiagnostic(
                code=code,
                stage=stage,
                message=message,
                agent_id=agent_id,
                slot=slot,
                exception_type=exception_type,
            )
        )

    @classmethod
    def _validate_declarations(
        cls,
        declarations: object,
        *,
        agent_id: str,
        slot: int,
        arena_size: int,
    ) -> list[ProcessDeclaration]:
        if not isinstance(declarations, list) or not declarations:
            raise cls._initialization_error(
                code="agent_process_declaration_invalid",
                message=(
                    f"Python agent {agent_id} must declare a non-empty list of "
                    "ProcessDeclaration values."
                ),
                agent_id=agent_id,
                slot=slot,
            )
        if not all(isinstance(item, ProcessDeclaration) for item in declarations):
            raise cls._initialization_error(
                code="agent_process_declaration_invalid",
                message=(
                    f"Python agent {agent_id} declare_processes() must return only "
                    "ProcessDeclaration values."
                ),
                agent_id=agent_id,
                slot=slot,
            )

        typed = list(declarations)
        ids = [item.id for item in typed]
        if any(not isinstance(process_id, str) or not process_id for process_id in ids):
            raise cls._initialization_error(
                code="agent_process_declaration_invalid",
                message=f"Python agent {agent_id} declared an empty process ID.",
                agent_id=agent_id,
                slot=slot,
            )
        duplicate_ids = sorted(
            process_id for process_id in set(ids) if ids.count(process_id) > 1
        )
        if duplicate_ids:
            raise cls._initialization_error(
                code="agent_process_declaration_invalid",
                message=(
                    f"Python agent {agent_id} declared duplicate process IDs: "
                    f"{duplicate_ids}."
                ),
                agent_id=agent_id,
                slot=slot,
            )

        for declaration in typed:
            if (
                isinstance(declaration.reach, bool)
                or not isinstance(declaration.reach, int)
                or declaration.reach <= 0
                or declaration.reach >= arena_size
            ):
                raise cls._initialization_error(
                    code="agent_process_declaration_invalid",
                    message=(
                        f"Python agent {agent_id} process {declaration.id!r} must "
                        f"declare integer reach in [1, {arena_size - 1}]."
                    ),
                    agent_id=agent_id,
                    slot=slot,
                )
            if (
                isinstance(declaration.share, bool)
                or not isinstance(declaration.share, (int, float))
                or not math.isfinite(float(declaration.share))
                or declaration.share < 0
            ):
                raise cls._initialization_error(
                    code="agent_process_declaration_invalid",
                    message=(
                        f"Python agent {agent_id} process {declaration.id!r} has "
                        "an invalid quota share."
                    ),
                    agent_id=agent_id,
                    slot=slot,
                )
        total_share = math.fsum(float(item.share) for item in typed)
        if not math.isclose(total_share, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise cls._initialization_error(
                code="agent_process_declaration_invalid",
                message=(
                    f"Python agent {agent_id} process shares total {total_share:g}; "
                    "expected 1."
                ),
                agent_id=agent_id,
                slot=slot,
            )
        if not any(item.share > 0 for item in typed):
            raise cls._initialization_error(
                code="agent_process_declaration_invalid",
                message=f"Python agent {agent_id} must declare a positive process share.",
                agent_id=agent_id,
                slot=slot,
            )
        return typed

    @classmethod
    def from_python_entrants(
        cls,
        config: Config,
        entrants: tuple[Any, ...],
        max_ticks: int,
        *,
        ruleset_policy: RulesetPolicy = RULESET_V4_ALPHA1,
        agent_call_timeout: float | None = None,
    ) -> ProcessMatchController:
        """Load API-v2 entrants and consume their declarations before tick zero."""

        if config.instr_per_tick != 8:
            raise cls._initialization_error(
                code="match_configuration_invalid",
                stage="configuration",
                message=(
                    "Bytefray Ruleset v4 alpha1 fixes the entrant action quota at Q=8; "
                    f"received {config.instr_per_tick}."
                ),
            )
        if config.arena_size <= 1 or max_ticks <= 0:
            raise cls._initialization_error(
                code="match_configuration_invalid",
                stage="configuration",
                message="V4 matches require arena_size > 1 and a positive tick limit.",
            )

        worker_handles: list[AgentWorkerHandle] = []
        specs: list[ProcessEntrantSpec] = []
        try:
            for slot, entrant in enumerate(entrants):
                executor: Callable[[ObservationV2, int], AgentAction]
                declared_api = getattr(entrant.python_spec, "api_version", None)
                if declared_api != 2:
                    raise cls._initialization_error(
                        code="agent_api_version_unsupported",
                        stage="load",
                        message=(
                            f"Ruleset {ruleset_policy.ruleset_id!r} requires Agent API v2; "
                            f"entrant {entrant.agent_id!r} declares {declared_api!r}."
                        ),
                        agent_id=entrant.agent_id,
                        slot=slot,
                    )

                seed = derive_agent_seed(config.seed, slot, entrant.agent_id, 2)
                agent_dir = getattr(entrant.python_spec, "dir", None)
                entry_point = getattr(entrant.python_spec, "entry_point", "") or ""
                initial_fingerprint = local_source_fingerprint(agent_dir)

                if agent_call_timeout is None:
                    try:
                        loaded = load_python_agent(entrant.python_spec)
                    except AgentValidationError as exc:
                        raise PythonEntrantInitializationError(
                            diagnose_load_failure(exc, agent_id=entrant.agent_id, slot=slot)
                        ) from exc
                    context = MatchContextV2(
                        agent_id=entrant.agent_id,
                        seed=seed,
                        arena_size=config.arena_size,
                        tick_limit=max_ticks,
                        rng=random.Random(seed),
                    )
                    instance = cast(AgentV2, loaded.instance)
                    try:
                        instance.reset(context)
                    except Exception as exc:
                        raise PythonEntrantInitializationError(
                            diagnose_reset_failure(exc, agent_id=entrant.agent_id, slot=slot)
                        ) from exc
                    try:
                        declarations: object = instance.declare_processes()
                    except Exception as exc:
                        raise cls._initialization_error(
                            code="agent_process_declaration_failed",
                            message=(
                                f"Python agent {entrant.agent_id} process declaration failed: "
                                f"{type(exc).__name__}: {exc}"
                            ),
                            agent_id=entrant.agent_id,
                            slot=slot,
                            exception_type=type(exc).__name__,
                        ) from exc

                    def direct_execute(
                        observation: ObservationV2,
                        action_slot: int,
                        *,
                        current_instance: AgentV2 = instance,
                    ) -> AgentAction:
                        del action_slot
                        return current_instance.act(observation)

                    executor = direct_execute

                    source_path = loaded.source_path
                    agent_version = loaded.metadata.version
                else:
                    from battle_engine.supervised_runtime import diagnostic_for_worker_result

                    handle = AgentWorkerHandle(agent_id=entrant.agent_id, slot=slot)
                    handle.start()
                    worker_handles.append(handle)
                    load_result = handle.load(
                        entrant.python_spec, timeout=agent_call_timeout
                    )
                    if load_result.status is not WorkerCallStatus.OK:
                        raise PythonEntrantInitializationError(
                            diagnostic_for_worker_result(
                                load_result,
                                agent_id=entrant.agent_id,
                                slot=slot,
                                stage="load",
                                timeout=agent_call_timeout,
                                exit_code=handle.exit_code,
                            )
                        )
                    assert load_result.payload is not None
                    metadata = load_result.payload["metadata"]
                    source_path = Path(load_result.payload["source_path"])
                    agent_version = str(metadata["version"])
                    reset_result = handle.reset(
                        match_seed=config.seed,
                        api_version=2,
                        arena_size=config.arena_size,
                        tick_limit=max_ticks,
                        action_budget=config.instr_per_tick,
                        timeout=agent_call_timeout,
                    )
                    if reset_result.status is not WorkerCallStatus.OK:
                        raise PythonEntrantInitializationError(
                            diagnostic_for_worker_result(
                                reset_result,
                                agent_id=entrant.agent_id,
                                slot=slot,
                                stage="reset",
                                timeout=agent_call_timeout,
                                exit_code=handle.exit_code,
                            )
                        )
                    declaration_result = handle.declare_processes(
                        timeout=agent_call_timeout
                    )
                    if declaration_result.status is not WorkerCallStatus.OK:
                        raise PythonEntrantInitializationError(
                            diagnostic_for_worker_result(
                                declaration_result,
                                agent_id=entrant.agent_id,
                                slot=slot,
                                stage="declaration",
                                timeout=agent_call_timeout,
                                exit_code=handle.exit_code,
                            )
                        )
                    assert declaration_result.payload is not None
                    declaration_payload = declaration_result.payload.get("declarations")
                    declarations = (
                        [ProcessDeclaration(**item) for item in declaration_payload]
                        if isinstance(declaration_payload, list)
                        else declaration_payload
                    )

                    def worker_execute(
                        observation: ObservationV2,
                        action_slot: int,
                        *,
                        worker: AgentWorkerHandle = handle,
                        current_agent_id: str = entrant.agent_id,
                        current_slot: int = slot,
                    ) -> AgentAction:
                        call = worker.act(
                            observation,
                            action_slot=action_slot,
                            timeout=agent_call_timeout,
                        )
                        if call.status is not WorkerCallStatus.OK:
                            raise ProcessAgentCallError(
                                diagnostic_for_worker_result(
                                    call,
                                    agent_id=current_agent_id,
                                    slot=current_slot,
                                    stage="action",
                                    timeout=agent_call_timeout,
                                    exit_code=worker.exit_code,
                                    tick=observation.current_tick,
                                    action_slot=action_slot,
                                )
                            )
                        assert call.payload is not None
                        action_payload = call.payload.get("action")
                        if not isinstance(action_payload, Mapping):
                            raise ValueError("act() must return one AgentAction")
                        return AgentAction(
                            ActionKindV2(action_payload["kind"]),
                            action_payload.get("operand"),
                            action_payload.get("value"),
                        )

                    executor = worker_execute

                validated = cls._validate_declarations(
                    declarations,
                    agent_id=entrant.agent_id,
                    slot=slot,
                    arena_size=config.arena_size,
                )
                processes = [
                    ProcessInstance(
                        declaration.id,
                        ProcessRole.GENERALIST,
                        None,
                        declaration.reach,
                        Fraction(str(declaration.share)),
                        lambda _observation, _state: AgentAction(
                            ActionKindV2.MOVE, 0
                        ),
                        executor=executor,
                    )
                    for declaration in validated
                ]
                try:
                    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
                except OSError as exc:
                    raise cls._initialization_error(
                        code="agent_source_invalid",
                        stage="load",
                        message=f"Could not read loaded Python agent source {source_path}: {exc}",
                        agent_id=entrant.agent_id,
                        slot=slot,
                        exception_type=type(exc).__name__,
                    ) from exc
                specs.append(
                    ProcessEntrantSpec(
                        entrant.agent_id,
                        entrant.name,
                        processes,
                        start=entrant.start,
                        normalized_shares=True,
                        api_version=2,
                        agent_version=agent_version,
                        source_path=source_path,
                        entry_point=entry_point,
                        derived_seed=seed,
                        source_digest=source_digest,
                        local_source_fingerprint=initial_fingerprint,
                        agent_dir=agent_dir,
                    )
                )
            controller = cls(
                config,
                specs,
                max_ticks,
                ruleset_policy=ruleset_policy,
            )
            controller._worker_handles = worker_handles
            return controller
        except BaseException:
            for handle in worker_handles:
                handle.close()
            raise

    def __init__(
        self,
        config: Config,
        entrant_specs: list[ProcessEntrantSpec],
        max_ticks: int,
        ruleset_policy: RulesetPolicy | None = None,
        max_move_delta: int = 64,
        **kwargs
    ):
        self.config = config
        self.entrant_specs = entrant_specs
        self.max_ticks = max_ticks
        self.ruleset_policy = ruleset_policy or RULESET_V4_ALPHA1
        self.disruption_duration = 1
        self.max_move_delta = max_move_delta
        # v4 alpha2's round-robin process-selection cursor: for each entrant,
        # the index its next intra-entrant selection scan starts from. Alpha1
        # (``process_selection == "priority"``) never reads it. See
        # :meth:`_select_active_process` for the full contract.
        self._process_cursor: dict[str, int] = {
            spec.agent_id: 0 for spec in entrant_specs
        }
        self._worker_handles: list[AgentWorkerHandle] = []

        if config.instr_per_tick <= 0 or config.arena_size <= 1 or max_ticks <= 0:
            raise ValueError("process matches require positive arena, quota, and tick limit")

        for spec in entrant_specs:
            if not spec.processes:
                raise ValueError(f"entrant {spec.agent_id!r} must define at least one process")
            if any(p.quota_share < 0 for p in spec.processes):
                raise ValueError(f"entrant {spec.agent_id!r} has a negative process quota share")
            process_ids = [process.process_id for process in spec.processes]
            if len(set(process_ids)) != len(process_ids):
                raise ValueError(
                    f"entrant {spec.agent_id!r} process IDs must be unique; "
                    f"received {process_ids}"
                )
            declared_quota = sum(p.quota_share for p in spec.processes)
            expected_total: int | Fraction = (
                Fraction(1) if spec.normalized_shares else config.instr_per_tick
            )
            if declared_quota != expected_total:
                raise ValueError(
                    f"entrant {spec.agent_id!r} process quota shares total {declared_quota}; "
                    f"expected {expected_total}"
                )

        self.vm = VM(config.arena_size)
        self.scoring = ScoringPolicy(config.weights)
        self.statistics_collector = StatisticsCollector()
        self.score: ScoreMap = {}
        self.statistics: StatisticsMap = {}

        # Shared entrant context per agent_id
        self.shared_contexts: dict[str, dict[str, Any]] = {
            spec.agent_id: {} for spec in entrant_specs
        }

        # Initialize entrant states and cores
        self.states: list[EntrantState] = []
        n_entrants = len(entrant_specs)
        spacing = config.arena_size // max(1, n_entrants)

        for slot, spec in enumerate(entrant_specs):
            start = (
                slot * spacing
                if spec.start is None
                else spec.start % config.arena_size
            )
            core_cells = tuple((start + i) % config.arena_size for i in range(8))
            st = EntrantState(
                agent_id=spec.agent_id,
                slot=slot,
                core_base=start,
                core_size=8,
                core_cells=core_cells,
                pc=start,
                region=(start, start),
            )
            self.states.append(st)
            self.score[spec.agent_id] = 0
            self.statistics_collector.initialize_agent(self.statistics, spec.agent_id)

            # Seed core ownership (0xCE beacon)
            for cell in core_cells:
                self.vm._wr8(cell, 0xCE, owner=spec.agent_id)

            # Reset processes
            for p in spec.processes:
                p.reset()
                if p.position is None:
                    p.position = start
                else:
                    unnormalized_position = p.position
                    p.position %= config.arena_size
                    if unnormalized_position != p.position:
                        p.telemetry.positions_visited.discard(unnormalized_position)
                p.telemetry.positions_visited.add(p.position)

        self._states_by_agent_id = {st.agent_id: st for st in self.states}

    def _circular_dist(self, a: int, b: int) -> int:
        d = abs(a - b)
        return min(d, self.config.arena_size - d)

    def _visible_enemy_anchors(
        self,
        observer_spec: ProcessEntrantSpec,
        tick: int,
    ) -> tuple[int, ...]:
        """Return current enemy occupancy visible to an entire entrant.

        Visibility is evaluated immediately before each callback. Local
        detection uses every currently eligible friendly process as a sensor,
        making the resulting spatial fact entrant-wide without exposing which
        sensor observed it. Co-located enemies collapse to one occupied
        address; identities and structural metadata remain private.
        """

        enemy_positions = {
            process.position
            for spec in self.entrant_specs
            if spec.agent_id != observer_spec.agent_id
            and self._states_by_agent_id[spec.agent_id].alive
            for process in spec.processes
            if process.position is not None
        }

        observers = [
            process
            for process in observer_spec.processes
            if process.position is not None and not process.is_disrupted(tick)
        ]
        visible: set[int] = set()
        for enemy_position in enemy_positions:
            for observer in observers:
                observer_position = observer.position
                radius = observer.reach
                if (
                    observer_position is not None
                    and radius is not None
                    and self._circular_dist(observer_position, enemy_position) <= radius
                ):
                    visible.add(enemy_position)
                    break
        return tuple(sorted(visible))

    def _effective_process_quotas(
        self,
        spec: ProcessEntrantSpec,
        tick: int,
    ) -> dict[ProcessInstance, int]:
        """Return explicit per-process limits for this tick's current eligibility.

        Fair redistribution uses proportional largest remainders. Equal
        remainders are resolved by stable ``process_id`` rather than process
        list position, so permuting a valid entrant specification does not
        alter the effective allocation.
        """

        def preserve_aliased_id_limits(
            allocations: dict[ProcessInstance, int],
        ) -> dict[ProcessInstance, int]:
            limits_by_id: dict[str, int] = {}
            for process, limit in allocations.items():
                limits_by_id[process.process_id] = limits_by_id.get(process.process_id, 0) + limit
            return {process: limits_by_id[process.process_id] for process in allocations}

        eligible = [p for p in spec.processes if not p.is_disrupted(tick)]
        if not eligible:
            return {}

        total_weight = sum(p.quota_share for p in eligible)
        if total_weight <= 0:
            return {}

        quota = self.config.instr_per_tick
        allocations = {p: (quota * p.quota_share) // total_weight for p in eligible}
        remainder_slots = quota - sum(allocations.values())
        remainder_order = sorted(
            eligible,
            key=lambda p: (-(quota * p.quota_share % total_weight), p.process_id),
        )
        for p in remainder_order[:remainder_slots]:
            allocations[p] += 1
        return preserve_aliased_id_limits(allocations)

    def _select_active_process(
        self,
        spec: ProcessEntrantSpec,
        effective_quotas: dict[ProcessInstance, int],
        actions_this_tick: dict[str, int],
    ) -> ProcessInstance | None:
        """Choose which of one entrant's processes takes this action slot.

        Reads ``self.ruleset_policy.process_selection``, so *which* process
        acts next is a semantic the Ruleset states rather than a runtime
        detail. Both modes select only from processes that are eligible this
        tick and still under their :meth:`_effective_process_quotas`
        allocation, and neither mode can change how large that allocation is:
        quota allocation, quota redistribution after a disruption, and
        disruption eligibility itself are computed entirely in
        ``_effective_process_quotas`` and are identical under both.
        Returning ``None`` means the entrant has no process able to act and
        forfeits the remainder of this slot -- unchanged in both modes, and
        what an all-disrupted entrant does every slot of the tick.

        ``"priority"`` (v4 alpha1, frozen): scan the declared process list
        from index 0 every time. Any quota freed up mid-tick is therefore
        always offered to the earliest-declared eligible process, which makes
        declaration order an undocumented priority ranking distinct from the
        ``share`` each process actually declares. Phase 4 measured that
        accidental lever at up to ~14 percentage points of win rate
        (docs/V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md Section G1).

        ``"round_robin"`` (v4 alpha2): scan from ``self._process_cursor``
        instead, and advance the cursor to just past whichever process was
        selected. Precisely:

        * **Initial cursor** -- 0 for every entrant, set once at controller
          construction, so an entrant's first action of the match still goes
          to its first declared process and a single-process entrant is
          bit-for-bit unaffected by this mode.
        * **Advancement** -- only on a successful selection, to
          ``(selected_index + 1) % process_count``. A slot that selects
          nothing (every process disrupted or quota-exhausted) leaves the
          cursor untouched, so a wasted slot never silently skips a process's
          turn.
        * **Disruption** -- a disrupted process is absent from
          ``effective_quotas`` entirely, so it is passed over without
          consuming its turn, and the scan continues to the next candidate
          in rotation. It rejoins the rotation at its own list position once
          it is eligible again.
        * **Quota exhaustion** -- identical treatment: a process at its
          allocation is simply not a candidate. When no process has quota
          left the scan completes without selecting, exactly as
          ``"priority"`` does.
        * **Redistribution** -- handled entirely upstream. When a sibling
          becomes disrupted its share is reallocated among the eligible
          processes by ``_effective_process_quotas``; this method only sees
          the resulting larger allocations, and hands the extra slots out in
          rotation rather than all to the earliest-declared process.
        * **Tick boundary** -- the cursor deliberately does **not** reset.
          It is match-scoped, so rotation continues across ticks and no
          process gets a systematic first-slot advantage every tick merely
          by being declared first. This is exactly the behavior Phase 4
          measured (Section G2); resetting per tick would reintroduce a
          weaker form of the same declaration-order bias.

        The cursor is keyed by ``agent_id`` and advanced by integer index
        into ``spec.processes``, never by dict or set iteration order, so
        rotation is reproducible across platforms and Python versions.
        """

        processes = spec.processes
        if not processes:
            return None

        if self.ruleset_policy.process_selection == "round_robin":
            cursor = self._process_cursor[spec.agent_id]
            count = len(processes)
            for offset in range(count):
                index = (cursor + offset) % count
                candidate = processes[index]
                if actions_this_tick[candidate.process_id] < effective_quotas.get(
                    candidate, 0
                ):
                    self._process_cursor[spec.agent_id] = (index + 1) % count
                    return candidate
            return None

        for process in processes:
            if actions_this_tick[process.process_id] < effective_quotas.get(process, 0):
                return process
        return None

    @staticmethod
    def _validate_v2_action(action: object) -> AgentAction:
        if not isinstance(action, AgentAction):
            raise ValueError("act() must return one AgentAction")
        if not isinstance(action.kind, ActionKindV2):
            raise ValueError("Agent API v2 supports READ, WRITE, and MOVE only")
        if isinstance(action.operand, bool) or not isinstance(action.operand, int):
            raise ValueError(f"{action.kind.value} requires one integer operand")
        if action.kind is ActionKindV2.WRITE:
            if isinstance(action.value, bool) or not isinstance(action.value, int):
                raise ValueError("write requires one integer value")
        elif action.value is not None:
            raise ValueError(f"{action.kind.value} does not accept a value")
        return action

    def _process_snapshots(self, tick: int) -> list[dict[str, Any]]:
        return [
            {
                "process_id": process.process_id,
                "entrant_id": spec.agent_id,
                "anchor": process.position if process.position is not None else 0,
                "disrupted": process.is_disrupted(tick),
                "reach": process.reach if process.reach is not None else 0,
            }
            for spec in self.entrant_specs
            for process in spec.processes
        ]

    def close(self) -> None:
        for handle in self._worker_handles:
            handle.close()
        self._worker_handles.clear()

    def run(
        self, sink: ReplaySink | None = None, *, verbose: bool = False
    ) -> dict[str, Any]:
        """Execute the match to completion."""
        replay = ReplayPublisher(sink) if sink is not None else None
        ticks_run = 0
        last_obs_results: dict[str, dict[str, Any]] = {
            spec.agent_id: {p.process_id: {} for p in spec.processes}
            for spec in self.entrant_specs
        }

        if replay is not None:
            replay.publish_header(self.config)
            replay.publish_tick(
                0,
                self.states,  # type: ignore[arg-type]
                self.score,
                self.vm,
                [],
                self._process_snapshots(0),
            )

        for tick in range(1, self.max_ticks + 1):
            ticks_run = tick
            self.vm.clear_tick_diffs()
            events: list[dict[str, Any]] = []
            pre_tick_core_owners = {
                state.agent_id: tuple(
                    self.vm.writer[address] for address in state.core_cells
                )
                for state in self.states
                if state.alive
            }

            for st in self.states:
                st.cpu_used = 0

            for spec in self.entrant_specs:
                if not self._states_by_agent_id[spec.agent_id].alive:
                    continue
                for p in spec.processes:
                    if p.is_disrupted(tick):
                        p.telemetry.disrupted_match_ticks.add(tick)

            # Per-tick process turn tracking
            proc_actions_this_tick: dict[str, dict[str, int]] = {
                spec.agent_id: {p.process_id: 0 for p in spec.processes}
                for spec in self.entrant_specs
            }

            # Entrant-level process scheduling inside chunked slots
            def execute_entrant_slot(
                st: EntrantState,
                slot: int,
                _tick: int = tick,
                _proc_actions: dict[str, dict[str, int]] = proc_actions_this_tick,
                _events: list[dict[str, Any]] = events,
            ) -> None:
                if not st.alive:
                    return
                spec = next(s for s in self.entrant_specs if s.agent_id == st.agent_id)

                # Select the next process within its explicit effective quota.
                effective_quotas = self._effective_process_quotas(spec, _tick)
                active_proc = self._select_active_process(
                    spec, effective_quotas, _proc_actions[st.agent_id]
                )

                if active_proc is None:
                    return

                # Build Observation
                last_res = last_obs_results[st.agent_id][active_proc.process_id]
                obs = ObservationV2(
                    current_tick=_tick,
                    last_callback_tick=last_res.get("tick", 0),
                    previous_action_tick=last_res.get("tick", 0),
                    self_process_id=active_proc.process_id,
                    self_anchor=active_proc.position or 0,
                    self_reach=active_proc.reach or 0,
                    own_core_base=st.core_base,
                    own_core_size=st.core_size,
                    visible_enemy_anchor_addresses=self._visible_enemy_anchors(spec, _tick),
                    previous_action_applied=last_res.get("applied", False),
                    previous_read_value=last_res.get("read_val"),
                    previous_read_owner=last_res.get("read_owner"),
                )

                try:
                    action = active_proc.act(obs, slot)
                    if spec.normalized_shares:
                        action = self._validate_v2_action(action)
                except ProcessAgentCallError as exc:
                    _proc_actions[st.agent_id][active_proc.process_id] += 1
                    st.cpu_used += 1
                    st.total_actions += 1
                    active_proc.telemetry.total_actions += 1
                    st.alive = False
                    st.entrant_termination = "forfeit"
                    st.diagnostic = exc.diagnostic
                    _events.append(
                        {
                            "type": "forfeit",
                            "victim": st.agent_id,
                            "reason": exc.diagnostic.code,
                            "stage": exc.diagnostic.stage,
                            "tick": _tick,
                            "action_slot": slot,
                        }
                    )
                    return
                except ValueError as exc:
                    _proc_actions[st.agent_id][active_proc.process_id] += 1
                    st.cpu_used += 1
                    st.total_actions += 1
                    active_proc.telemetry.total_actions += 1
                    diagnostic = RuntimeDiagnostic(
                        code="agent_action_invalid",
                        stage="action",
                        message=(
                            f"Python agent {st.agent_id} returned an invalid action: {exc}"
                        ),
                        agent_id=st.agent_id,
                        slot=st.slot,
                        exception_type=type(exc).__name__,
                        tick=_tick,
                        action_slot=slot,
                    )
                    st.alive = False
                    st.entrant_termination = "forfeit"
                    st.diagnostic = diagnostic
                    _events.append(
                        {
                            "type": "forfeit",
                            "victim": st.agent_id,
                            "reason": diagnostic.code,
                            "stage": diagnostic.stage,
                            "tick": _tick,
                            "action_slot": slot,
                        }
                    )
                    return
                except Exception as exc:
                    _proc_actions[st.agent_id][active_proc.process_id] += 1
                    st.cpu_used += 1
                    st.total_actions += 1
                    active_proc.telemetry.total_actions += 1
                    diagnostic = diagnose_action_exception(
                        exc,
                        agent_id=st.agent_id,
                        slot=st.slot,
                        tick=_tick,
                        action_slot=slot,
                    )
                    st.alive = False
                    st.entrant_termination = "forfeit"
                    st.diagnostic = diagnostic
                    _events.append(
                        {
                            "type": "forfeit",
                            "victim": st.agent_id,
                            "reason": diagnostic.code,
                            "stage": diagnostic.stage,
                            "tick": _tick,
                            "action_slot": slot,
                        }
                    )
                    return
                _proc_actions[st.agent_id][active_proc.process_id] += 1
                st.cpu_used += 1
                st.total_actions += 1
                active_proc.telemetry.total_actions += 1

                # Execute action based on model
                res_info: dict[str, Any] = {
                    "action_kind": action.kind,
                    "operand": action.operand,
                    "value": action.value,
                    "applied": True,
                    "tick": _tick,
                }

                if action.kind == ActionKind.NOP:
                    active_proc.telemetry.total_passes += 1

                elif action.kind in (ActionKind.MOVE, ActionKindV2.MOVE):
                    if active_proc.position is not None:
                        op = action.operand if action.operand is not None else 0
                        delta = max(-self.max_move_delta, min(op, self.max_move_delta))
                        new_pos = (active_proc.position + delta) % self.config.arena_size
                        active_proc.position = new_pos
                        active_proc.telemetry.total_moves += 1
                        active_proc.telemetry.positions_visited.add(new_pos)

                elif action.kind in (ActionKind.READ, ActionKindV2.READ):
                    target_addr = (action.operand if action.operand is not None else 0) % self.config.arena_size
                    # Check reach
                    if (
                        active_proc.reach is not None
                        and active_proc.position is not None
                        and self._circular_dist(target_addr, active_proc.position) > active_proc.reach
                    ):
                        # Out of reach: read fails
                        res_info["read_val"] = None
                        res_info["read_owner"] = None
                        res_info["applied"] = False
                        last_obs_results[st.agent_id][active_proc.process_id] = res_info
                        return

                    val = self.vm.arena[target_addr]
                    owner = self.vm.writer[target_addr]
                    res_info["read_val"] = val
                    res_info["read_owner"] = owner
                    active_proc.telemetry.total_reads += 1
                    active_proc.telemetry.addresses_read.add(target_addr)

                elif action.kind in (ActionKind.WRITE, ActionKindV2.WRITE):
                    target_addr = (action.operand if action.operand is not None else 0) % self.config.arena_size
                    # Check reach
                    if (
                        active_proc.reach is not None
                        and active_proc.position is not None
                        and self._circular_dist(target_addr, active_proc.position) > active_proc.reach
                    ):
                        # Out of reach: write discarded
                        res_info["applied"] = False
                        last_obs_results[st.agent_id][active_proc.process_id] = res_info
                        return

                    val = (action.value if action.value is not None else 0) & 0xFF
                    self.vm._wr8(target_addr, val, owner=st.agent_id)
                    st.mem_writes += 1
                    active_proc.telemetry.total_writes += 1
                    active_proc.telemetry.addresses_written.add(target_addr)


                    # R4b shared-location blast: every live enemy process whose
                    # current anchor occupies this cell is disrupted. Friendly
                    # processes are immune even when co-located.
                    if self.disruption_duration > 0:
                        for other_spec in self.entrant_specs:
                            if other_spec.agent_id == st.agent_id:
                                continue
                            if not self._states_by_agent_id[other_spec.agent_id].alive:
                                continue
                            for other_p in other_spec.processes:
                                if other_p.position is not None and other_p.position == target_addr:
                                    other_p.disrupted_until_tick = _tick + self.disruption_duration
                                    other_p.telemetry.disruption_hits_received += 1
                                    other_p.telemetry.total_disrupted_ticks += self.disruption_duration
                                    other_p.telemetry.disrupted_match_ticks.add(_tick)

                last_obs_results[st.agent_id][active_proc.process_id] = res_info


            # Execute tick via ruleset policy scheduler
            self.ruleset_policy.run_scheduler(
                self.states, self.config.instr_per_tick, execute_entrant_slot, tick=tick
            )

            apply_core_capture(
                self.states,  # type: ignore[arg-type]
                self.vm,
                pre_tick_core_owners,
                self.scoring,
                self.score,
                self.statistics_collector,
                self.statistics,
                events,
            )

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

            if replay is not None:
                replay.publish_tick(
                    tick,
                    self.states,  # type: ignore[arg-type]
                    self.score,
                    self.vm,
                    events,
                    self._process_snapshots(tick),
                )
            if verbose and (tick % 50 == 0 or tick < 10):
                alive = [state.agent_id for state in self.states if state.alive]
                print(f"[T{tick:05d}] alive={alive} score={self.score}")

            if self.ruleset_policy.resolve_termination(
                alive_count=sum(1 for st in self.states if st.alive),
                tick=tick,
                max_ticks=self.max_ticks,
            ).terminated:
                break

        if replay is not None:
            replay.close()

        for spec in self.entrant_specs:
            spec.local_source_fingerprint_final = local_source_fingerprint(spec.agent_dir)

        # Calculate results
        living = [st for st in self.states if st.alive]
        if len(living) == 1:
            winner = living[0].agent_id
            reason = "last_agent_standing"
        elif len(living) == 0:
            winner = "tie"
            reason = "all_agents_dead"
        else:
            # Score fallback
            scores = {st.agent_id: self.score[st.agent_id] for st in living}
            max_score = max(scores.values())
            top_agents = [aid for aid, sc in scores.items() if sc == max_score]
            winner = top_agents[0] if len(top_agents) == 1 else "tie"
            reason = "tick_limit"

        # Entrant summaries
        entrants_summary = {}
        for st in self.states:
            spec = next(s for s in self.entrant_specs if s.agent_id == st.agent_id)
            proc_stats = {}
            for p in spec.processes:
                proc_stats[p.process_id] = {
                    "role": p.role.value,
                    "actions": p.telemetry.total_actions,
                    "moves": p.telemetry.total_moves,
                    "reads": p.telemetry.total_reads,
                    "writes": p.telemetry.total_writes,
                    "passes": p.telemetry.total_passes,
                    "disruption_hits_received": p.telemetry.disruption_hits_received,
                    "disrupted_ticks": p.telemetry.total_disrupted_ticks,
                    "distinct_disrupted_ticks": len(p.telemetry.disrupted_match_ticks),
                    "positions_count": len(p.telemetry.positions_visited),
                    "reads_count": len(p.telemetry.addresses_read),
                    "writes_count": len(p.telemetry.addresses_written),
                }
            entrants_summary[st.agent_id] = {
                "name": spec.name,
                "alive": st.alive,
                "score": self.score[st.agent_id],
                "territory": self.vm.ownership_counts.get(st.agent_id, 0),
                "processes": proc_stats,
            }

        return {
            "winner": winner,
            "reason": reason,
            "ticks_run": ticks_run,
            "entrants": entrants_summary,
        }
