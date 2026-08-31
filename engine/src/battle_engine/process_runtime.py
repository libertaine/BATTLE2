"""Bytefray v4 Research Prototype: Multi-Process Entrant Simulation Runtime.

Provides a research-only multi-process execution harness supporting:
- Model A: Independent Action Cursors (global reach)
- Model B: Static Spatial Loci (fixed position, reach R)
- Model C: Movable Spatial Anchors (dynamic position, move cost, reach R)
- Stage 4: Process Disruption (temporary incapacitation on anchor overwrite)
- Stage 5: Research-only enemy-anchor visibility prototypes

Strictly adheres to:
- Entrant-level fairness under chunked scheduler (K=2, rotating start)
- Explicit disrupted-quota policy (lost quota or fair redistribution)
- Pure deterministic execution (no OS threads/processes)
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from battle_engine.agent_api import ActionKind, AgentAction
from battle_engine.config import Config
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1, RulesetPolicy
from battle_engine.scoring import ScoreMap, ScoringPolicy
from battle_engine.statistics import StatisticsCollector, StatisticsMap
from battle_engine.vm import VM


class ProcessModel(str, enum.Enum):
    MODEL_A_CURSOR = "model_a_cursor"  # Global reach, independent cursors
    MODEL_B_STATIC_LOCUS = "model_b_static_locus"  # Fixed position, reach R
    MODEL_C_MOVABLE_ANCHOR = "model_c_movable_anchor"  # Dynamic position, move actions, reach R


class ProcessRole(str, enum.Enum):
    DEFENDER = "defender"
    HUNTER = "hunter"
    SCOUT = "scout"
    ATTACKER = "attacker"
    EXPANDER = "expander"
    GENERALIST = "generalist"


class DisruptedQuotaPolicy(str, enum.Enum):
    """How an entrant's per-tick quota behaves while processes are disrupted."""

    LOST = "lost"
    FAIR_REDISTRIBUTION = "fair_redistribution"


class AnchorVisibilityModel(str, enum.Enum):
    """Research-only enemy-anchor information supplied to processes."""

    HIDDEN = "hidden"
    PUBLIC = "public"
    LOCAL_DETECTION = "local_detection"


@dataclass
class ProcessObservation:
    tick: int
    agent_id: str
    process_id: str
    role: str
    position: int | None
    reach: int | None
    core_base: int
    core_size: int
    arena_size: int
    last_action_kind: ActionKind | None = None
    last_action_operand: int | None = None
    last_action_value: int | None = None
    read_result: int | None = None
    read_owner: str | None = None
    visible_enemy_anchors: tuple[int, ...] = ()
    shared_memory: dict[str, Any] = field(default_factory=dict)


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
        quota_share: int,
        logic: Callable[[ProcessObservation, dict[str, Any]], AgentAction],
    ):
        self.process_id = process_id
        self.role = role
        self.position = initial_position
        self.reach = reach
        self.quota_share = quota_share  # Max actions per tick for this process
        self.logic = logic
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

    def act(self, obs: ProcessObservation) -> AgentAction:
        return self.logic(obs, self.local_state)


@dataclass
class ProcessEntrantSpec:
    """Specification for a multi-process entrant."""
    agent_id: str
    name: str
    processes: list[ProcessInstance]
    allocation_policy: str = "fixed"  # "fixed" (uses quota_share) or "dynamic"


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



class ProcessMatchController:
    """Executes a match between multi-process and/or single-process entrants."""

    def __init__(
        self,
        config: Config,
        entrant_specs: list[ProcessEntrantSpec],
        max_ticks: int,
        model: ProcessModel = ProcessModel.MODEL_A_CURSOR,
        ruleset_policy: RulesetPolicy | None = None,
        disruption_duration: int = 0,  # 0 = disabled (indestructible)
        disrupted_quota_policy: DisruptedQuotaPolicy = DisruptedQuotaPolicy.FAIR_REDISTRIBUTION,
        anchor_visibility_model: AnchorVisibilityModel = AnchorVisibilityModel.HIDDEN,
        detection_radius: int | None = None,
        max_move_delta: int = 64,
    ):
        self.config = config
        self.entrant_specs = entrant_specs
        self.max_ticks = max_ticks
        self.model = model
        self.ruleset_policy = ruleset_policy or RULESET_V4_ALPHA1
        self.disruption_duration = disruption_duration
        self.disrupted_quota_policy = DisruptedQuotaPolicy(disrupted_quota_policy)
        self.anchor_visibility_model = AnchorVisibilityModel(anchor_visibility_model)
        if detection_radius is not None and detection_radius < 0:
            raise ValueError("detection_radius must be non-negative")
        self.detection_radius = detection_radius
        self.max_move_delta = max_move_delta

        for spec in entrant_specs:
            if not spec.processes:
                raise ValueError(f"entrant {spec.agent_id!r} must define at least one process")
            if any(p.quota_share < 0 for p in spec.processes):
                raise ValueError(f"entrant {spec.agent_id!r} has a negative process quota share")
            declared_quota = sum(p.quota_share for p in spec.processes)
            if declared_quota != config.instr_per_tick:
                raise ValueError(
                    f"entrant {spec.agent_id!r} process quota shares total {declared_quota}; "
                    f"expected {config.instr_per_tick}"
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
            start = slot * spacing
            core_cells = tuple((start + i) % config.arena_size for i in range(8))
            st = EntrantState(
                agent_id=spec.agent_id,
                slot=slot,
                core_base=start,
                core_size=8,
                core_cells=core_cells,
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

        if self.anchor_visibility_model == AnchorVisibilityModel.HIDDEN:
            return ()

        enemy_positions = {
            process.position
            for spec in self.entrant_specs
            if spec.agent_id != observer_spec.agent_id
            and self._states_by_agent_id[spec.agent_id].alive
            for process in spec.processes
            if process.position is not None
        }
        if self.anchor_visibility_model == AnchorVisibilityModel.PUBLIC:
            return tuple(sorted(enemy_positions))

        observers = [
            process
            for process in observer_spec.processes
            if process.position is not None and not process.is_disrupted(tick)
        ]
        visible: set[int] = set()
        for enemy_position in enemy_positions:
            for observer in observers:
                observer_position = observer.position
                radius = (
                    self.detection_radius
                    if self.detection_radius is not None
                    else observer.reach
                )
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
        if self.disrupted_quota_policy == DisruptedQuotaPolicy.LOST:
            return preserve_aliased_id_limits({p: p.quota_share for p in eligible})
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

    def run(self) -> dict[str, Any]:
        """Execute the match to completion."""
        ticks_run = 0
        last_obs_results: dict[str, dict[str, Any]] = {
            spec.agent_id: {p.process_id: {} for p in spec.processes}
            for spec in self.entrant_specs
        }

        for tick in range(1, self.max_ticks + 1):
            ticks_run = tick
            self.vm.clear_tick_diffs()

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
            ) -> None:
                if not st.alive:
                    return
                spec = next(s for s in self.entrant_specs if s.agent_id == st.agent_id)

                # Select the next process within its explicit effective quota.
                active_proc: ProcessInstance | None = None
                effective_quotas = self._effective_process_quotas(spec, _tick)
                for p in spec.processes:
                    if _proc_actions[st.agent_id][p.process_id] < effective_quotas.get(p, 0):
                        active_proc = p
                        break

                if active_proc is None:
                    return

                # Build Observation
                last_res = last_obs_results[st.agent_id][active_proc.process_id]
                obs = ProcessObservation(
                    tick=_tick,
                    agent_id=st.agent_id,
                    process_id=active_proc.process_id,
                    role=active_proc.role.value,
                    position=active_proc.position,
                    reach=active_proc.reach,
                    core_base=st.core_base,
                    core_size=st.core_size,
                    arena_size=self.config.arena_size,
                    last_action_kind=last_res.get("action_kind"),
                    last_action_operand=last_res.get("operand"),
                    last_action_value=last_res.get("value"),
                    read_result=last_res.get("read_val"),
                    read_owner=last_res.get("read_owner"),
                    visible_enemy_anchors=self._visible_enemy_anchors(spec, _tick),
                    shared_memory=self.shared_contexts[st.agent_id],
                )

                action = active_proc.act(obs)
                _proc_actions[st.agent_id][active_proc.process_id] += 1
                st.cpu_used += 1
                st.total_actions += 1
                active_proc.telemetry.total_actions += 1

                # Execute action based on model
                res_info: dict[str, Any] = {
                    "action_kind": action.kind,
                    "operand": action.operand,
                    "value": action.value,
                }

                if action.kind == ActionKind.NOP:
                    active_proc.telemetry.total_passes += 1

                elif action.kind == ActionKind.MOVE:
                    # Model C: Movement
                    if self.model == ProcessModel.MODEL_C_MOVABLE_ANCHOR and active_proc.position is not None:
                        op = action.operand if action.operand is not None else 0
                        delta = max(-self.max_move_delta, min(op, self.max_move_delta))
                        new_pos = (active_proc.position + delta) % self.config.arena_size
                        active_proc.position = new_pos
                        active_proc.telemetry.total_moves += 1
                        active_proc.telemetry.positions_visited.add(new_pos)

                elif action.kind == ActionKind.READ:
                    target_addr = (action.operand if action.operand is not None else 0) % self.config.arena_size
                    # Check reach under Model B / C
                    if (
                        self.model in (ProcessModel.MODEL_B_STATIC_LOCUS, ProcessModel.MODEL_C_MOVABLE_ANCHOR)
                        and active_proc.reach is not None
                        and active_proc.position is not None
                        and self._circular_dist(target_addr, active_proc.position) > active_proc.reach
                    ):
                        # Out of reach: read fails
                        res_info["read_val"] = 0
                        res_info["read_owner"] = None
                        last_obs_results[st.agent_id][active_proc.process_id] = res_info
                        return

                    val = self.vm.arena[target_addr]
                    owner = self.vm.writer[target_addr]
                    res_info["read_val"] = val
                    res_info["read_owner"] = owner
                    active_proc.telemetry.total_reads += 1
                    active_proc.telemetry.addresses_read.add(target_addr)

                elif action.kind == ActionKind.WRITE:
                    target_addr = (action.operand if action.operand is not None else 0) % self.config.arena_size
                    # Check reach under Model B / C
                    if (
                        self.model in (ProcessModel.MODEL_B_STATIC_LOCUS, ProcessModel.MODEL_C_MOVABLE_ANCHOR)
                        and active_proc.reach is not None
                        and active_proc.position is not None
                        and self._circular_dist(target_addr, active_proc.position) > active_proc.reach
                    ):
                        # Out of reach: write discarded
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

            # Core capture check (8-cell vulnerable core)
            for st in self.states:
                if not st.alive:
                    continue
                # If all 8 core cells are no longer owned by st.agent_id, entrant dies
                owned_cells = sum(1 for c in st.core_cells if self.vm.writer[c] == st.agent_id)
                if owned_cells == 0:
                    st.alive = False

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

            alive_count = sum(1 for st in self.states if st.alive)
            if alive_count <= 1:
                break

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
