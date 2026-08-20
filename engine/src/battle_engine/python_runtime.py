"""Restricted deterministic runtime for homogeneous Python-agent matches."""

from __future__ import annotations

import hashlib
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass
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
from battle_engine.entrant_identity import EntrantIdentity
from battle_engine.results import resolve_winner
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA1_ID,
    BYTEFRAY_RULESET_V2_ALPHA11_ID,
    BYTEFRAY_RULESET_V2_ID,
    RULESET_V1,
    RulesetPolicy,
    TerminationReason,
)
from battle_engine.scoring import ScoreMap, ScoringPolicy
from battle_engine.statistics import StatisticsCollector, StatisticsMap
from battle_engine.telemetry import ReplayPublisher, ReplaySink
from battle_engine.vm import VM

# v2.0.0-alpha.1 "Vulnerable Core" (docs/V2_0_ALPHA_ARCHITECTURE.md Sec 6,
# docs/V2_0_ALPHA1_EVALUATION.md): each Python entrant's core is a
# fixed-size window of ``CORE_SIZE`` bytes anchored at its own original
# spawn address (``entrant.start % arena_size``), using ordinary
# ``pos % arena_size`` wrap -- the same addressing every other arena access
# in this engine already uses (``vm.py``'s ``_rd32``/``_wr8``). Deliberately
# NOT derived from the entrant's program size, write count, or any other
# entrant-controlled property (that would reward padding/footprint
# inflation with survivability -- see the governing task's Phase 3).
#
# 8 was chosen, not computed: Python entrants load no code into the arena
# at all (unlike the VM path, which has a real per-entrant code footprint
# to reason about -- see ``VM.load_code``), so there is no existing
# "footprint" to size a core against in the first place. Against the
# default ``Config.arena_size == 4096``, 8 cells is small enough (0.2% of
# the arena) that a core is a genuine localized target an opponent must
# actually find and fully overwrite -- not a proxy for general territorial
# dominance -- while still being more than one cell, so a single incidental
# write passing through can't trivially end a match by accident. It is a
# fixed module constant, not threaded through ``Config``, per the governing
# task's instruction not to make it configurable for this alpha.
CORE_SIZE = 8

# v2.0.0-alpha.11 "Consistent Core Observability"
# (docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md).
#
# The defect this closes, stated precisely: under
# ``bytefray-rules-2-alpha1``, ``seed_core_ownership`` establishes a core's
# initial ownership by writing the byte value ``0`` -- which is exactly what
# untouched arena already contains (docs/RULES.md: "The arena starts filled
# with byte 0"). Ownership is engine-internal and unreadable by any entrant,
# so *content* is the only channel through which a core can be observed at
# all. The consequence, measured across alpha.10's 976-match corpus: an
# entrant that never writes into its own core is literally invisible to
# every non-privileged searcher (0% capture rate against ``claimer``/
# ``hunter``), while an entrant that *defends* its core becomes detectable
# precisely because it defended (12-28% capture rate against the two
# defenders). Defending was informationally self-punishing and blind
# expansion bought invisibility for free.
#
# ``CORE_BEACON_BYTE`` is the public, fixed constant a core's own cells hold
# instead. It is Ruleset knowledge on exactly the same footing as
# ``CORE_SIZE`` already is (``core_defender``/``reactive_core_defender``/
# ``core_tracker`` all already hardcode ``8`` on that basis) -- not
# privileged information about any specific opponent, and deliberately not
# keyed to any reference agent: no agent needs to recognize this particular
# value to benefit, since every existing content-based searcher keys on
# "non-zero and not my own signature", which any non-zero beacon satisfies.
#
# ``0xCE`` was chosen, not computed: it must be non-zero (a zero beacon is
# the defect itself) and must differ from every signature byte used by any
# bundled starter or reference agent -- ``0x99`` (adaptive), ``0xC1``
# (claimer), ``0xE3`` (hunter), ``0xC2`` (strider), ``0x2C`` (wanderer),
# ``0xD3`` (core_defender), ``0x5E`` (core_seeker), ``0xA5`` (core_tracker),
# ``0xC7`` (reactive_core_defender) -- so that no agent is accidentally
# blinded to beacons by its own ``value != self.signature`` self-filter and
# no agent's ordinary territory is mistaken for a core.
CORE_BEACON_BYTE = 0xCE

# The historical alpha.1 seeding content: ownership without an observable
# footprint. Retained explicitly (rather than as a bare literal) so the
# alpha.1-vs-alpha.11 difference is a named, greppable Ruleset property.
CORE_SEED_BYTE_ALPHA1 = 0x00

# Which Ruleset identities carry which Python-only mechanic. Finite,
# explicit sets -- never a prefix or naming-convention check, for the same
# fail-closed reason ``ruleset_policy._RULESET_POLICIES`` is finite.
#
# ``BYTEFRAY_RULESET_V2_ID`` ("bytefray-rules-2", v2.0.0-beta1's permanent
# identity) carries both mechanics, identically to
# ``BYTEFRAY_RULESET_V2_ALPHA11_ID``: beta1 promotes alpha.11's
# evidence-backed candidate semantics as-is (see
# docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md Sec 25-26 and
# docs/V2_0_BETA1_PLAN.md), sharing this exact implementation rather than
# duplicating it -- the two identities are distinguished by registration and
# persistence (``ruleset_policy.py``), not by behavior.
VULNERABLE_CORE_RULESET_IDS: frozenset[str] = frozenset(
    {BYTEFRAY_RULESET_V2_ALPHA1_ID, BYTEFRAY_RULESET_V2_ALPHA11_ID, BYTEFRAY_RULESET_V2_ID}
)
OBSERVABLE_CORE_RULESET_IDS: frozenset[str] = frozenset(
    {BYTEFRAY_RULESET_V2_ALPHA11_ID, BYTEFRAY_RULESET_V2_ID}
)


def has_vulnerable_core(ruleset_id: str) -> bool:
    """Whether ``ruleset_id``'s Python semantics include core capture."""

    return ruleset_id in VULNERABLE_CORE_RULESET_IDS


def has_observable_core(ruleset_id: str) -> bool:
    """Whether ``ruleset_id``'s Python semantics include the core beacon.

    Strictly narrower than :func:`has_vulnerable_core`:
    ``bytefray-rules-2-alpha1`` has a vulnerable core with *no* observable
    footprint, and must keep behaving exactly that way forever.
    """

    return ruleset_id in OBSERVABLE_CORE_RULESET_IDS


def core_seed_byte(ruleset_id: str) -> int:
    """The byte value ``ruleset_id`` seeds core cells with at match start."""

    return CORE_BEACON_BYTE if has_observable_core(ruleset_id) else CORE_SEED_BYTE_ALPHA1


def core_addresses(core_start: int, arena_size: int) -> tuple[int, ...]:
    """Every address in one entrant's core region, using ordinary arena wrap."""

    start = core_start % arena_size
    return tuple((start + offset) % arena_size for offset in range(CORE_SIZE))


def _snapshot_core_owners(
    states: list[PythonEntrantState], vm: VM
) -> dict[str, tuple[str | None, ...]]:
    """Per-living-entrant core ownership *before* this tick's actions run.

    Captured once at the start of each tick (before ``run_scheduler``
    executes any action this tick) so :func:`apply_core_capture` can later
    tell, for an entrant that ends the tick core-captured, whether that
    capture happened *during* this tick (attributable to a specific write --
    see :func:`_attribute_core_capture`) or was already true before any of
    this tick's actions ran (unattributable, e.g. two entrants spawned with
    overlapping cores).
    """

    return {
        state.agent_id: tuple(
            vm.writer[address] for address in core_addresses(state.core_start, len(vm.arena))
        )
        for state in states
        if state.alive
    }


def seed_core_ownership(
    state: PythonEntrantState, vm: VM, *, beacon: int = CORE_SEED_BYTE_ALPHA1
) -> None:
    """Establish an entrant's initial ownership of its own core region.

    ``beacon`` is the byte value written into every core cell. It defaults to
    ``CORE_SEED_BYTE_ALPHA1`` (``0``) so ``bytefray-rules-2-alpha1`` and every
    existing caller keep byte-identical historical behavior; alpha.11 passes
    ``CORE_BEACON_BYTE`` instead (see ``core_seed_byte``). Only the *content*
    differs -- the ownership this establishes, and therefore every ownership
    count, territory score, and capture decision downstream of it, is
    identical under both Rulesets.

    Python entrants never place code in the arena (unlike the VM path,
    where ``Kernel.spawn``/``VM.load_code`` establish initial ownership
    over an entrant's code footprint as a side effect of loading it) --
    without this, "owns zero cells of its own core" would already be
    vacuously true before tick one, since nothing has written there yet,
    and the mechanic would capture every entrant on its very first check.
    This is the Python-runtime-only equivalent spawn-time step: routed
    through ``VM._wr8`` exactly like any other write (so it appears in
    tick zero's replay diffs precisely as ``load_code`` already does for
    the VM), establishing this entrant as the sole owner of every cell in
    its own core before any ``act()`` call happens. Only called under
    ``bytefray-rules-2-alpha1``; Ruleset v1 Python matches never call this,
    so their tick-zero ``memory_diffs`` stay empty exactly as before.
    """

    for address in core_addresses(state.core_start, len(vm.arena)):
        vm._wr8(address, beacon, state.agent_id)


def maintain_core_beacons(states: list[PythonEntrantState], vm: VM) -> None:
    """bytefray-rules-2-alpha11: a self-owned core cell is never blank.

    The whole of the alpha.11 observability invariant, and deliberately no
    more than that. For every *living* entrant, any cell of its own core that
    **it still owns** and whose content has become ``0x00`` is rewritten to
    :data:`CORE_BEACON_BYTE`, attributed to that same owner.

    Three properties this rule is carefully scoped to preserve, each of which
    a broader "restore the marker" rule would have broken:

    * **Observability does not equal invulnerability.** Only cells the owner
      *already owns* are touched, so an attacker's write is never reverted,
      no ownership is ever restored, ``vm.ownership_counts`` never changes,
      and the capture rule (:func:`apply_core_capture`) is not affected in
      any way. A core is exactly as killable as it was under alpha.1.
    * **The owner's own content is left alone.** Only ``0x00`` is repaired,
      never a non-zero byte, so ``core_defender``'s ``0xD3`` and
      ``reactive_core_defender``'s ``0xC7`` core signatures survive intact
      and their ``READ``-then-compare repair logic keeps working exactly as
      designed. A rule that normalized *all* self-owned core content to the
      beacon would make every reactive patrol read look like damage and
      drive that agent into permanent false repair -- silently redesigning a
      reference defender.
    * **The owner cannot hide.** Writing ``0`` over its own core is the only
      way an entrant could restore alpha.1's invisibility while keeping
      ownership, and that is precisely what this repairs.

    Called once per tick after :func:`apply_core_capture` (so a core captured
    this tick belongs to a dead entrant and is no longer maintained) and
    before statistics/scoring/replay publication (so any maintenance write
    lands in this tick's ``memory_diffs`` and replays reconstruct exactly).
    Routed through ``VM._wr8`` like every other write in this engine.
    """

    for state in states:
        if not state.alive:
            continue
        for address in core_addresses(state.core_start, len(vm.arena)):
            if vm.writer[address] == state.agent_id and vm.arena[address] == 0:
                vm._wr8(address, CORE_BEACON_BYTE, state.agent_id)


def _attribute_core_capture(
    state: PythonEntrantState,
    core_addrs: tuple[int, ...],
    before_owners: tuple[str | None, ...],
    vm: VM,
) -> str | None:
    """Find which entrant's write caused ``state`` to lose its last core cell.

    Replays this tick's ``vm.tick_diffs`` (already in true execution order --
    entrants act in fixed scheduled order, so diffs are appended in the
    order writes actually happened) restricted to addresses inside
    ``core_addrs``, starting from ``before_owners`` (this entrant's core
    ownership before any of this tick's actions ran). Returns the ``owner``
    of the one diff that makes ``state``'s core-owned count drop from one
    to zero -- unambiguous by construction, since only one write can be
    "the write that took the last cell" once diffs are replayed in their
    real order. Returns ``None`` if ``state`` already owned zero core cells
    before this tick's actions ran (an edge case with no single attributable
    cause this tick -- see ``seed_core_ownership``'s docstring for how an
    overlapping-core spawn could produce this).
    """

    core_set = set(core_addrs)
    local_owner: dict[int, str | None] = dict(zip(core_addrs, before_owners, strict=True))
    remaining = sum(1 for owner in local_owner.values() if owner == state.agent_id)
    if remaining == 0:
        return None
    for start, length, owner, _values in vm.tick_diffs:
        for offset in range(length):
            address = (start + offset) % len(vm.arena)
            if address not in core_set:
                continue
            previous = local_owner[address]
            if previous == owner:
                continue
            local_owner[address] = owner
            if previous == state.agent_id:
                remaining -= 1
                if remaining == 0:
                    return owner
    return None  # pragma: no cover - unreachable given the caller's own invariant


def apply_core_capture(
    states: list[PythonEntrantState],
    vm: VM,
    pre_tick_core_owners: Mapping[str, tuple[str | None, ...]],
    scoring: ScoringPolicy,
    score: ScoreMap,
    statistics_collector: StatisticsCollector,
    statistics: StatisticsMap,
    events: list[dict[str, Any]],
) -> None:
    """bytefray-rules-2-alpha1: kill any living entrant now core-captured.

    An entrant is core-captured when it owns zero cells of its own fixed
    ``CORE_SIZE`` core region (Phase 4's semantic definition -- deliberately
    "owns zero", not "one opponent owns all of it", so the rule stays
    well-defined if Bytefray ever supports more than two entrants). Checked
    once per tick, after all of this tick's actions have executed and
    before scoring/termination -- so a captured entrant receives no
    alive/territory score for the tick it dies on, exactly like an
    ordinary Python ``HALT``, and no hidden extra turn. Kill credit goes to
    whichever entrant's ``WRITE`` caused the final defender-owned core cell
    to change owner this tick, when :func:`_attribute_core_capture` can
    determine it unambiguously; otherwise this is recorded as an
    unattributed death, exactly like an ordinary unattributed Python
    forfeit/halt.
    """

    for state in states:
        if not state.alive:
            continue
        addrs = core_addresses(state.core_start, len(vm.arena))
        owned_now = sum(1 for address in addrs if vm.writer[address] == state.agent_id)
        if owned_now > 0:
            continue
        before = pre_tick_core_owners.get(state.agent_id, ())
        # ``before`` is only ever absent-or-mis-sized if this entrant somehow
        # reached this point without a pre-tick snapshot (an invariant
        # violation, not a real match state -- every state alive at tick
        # start is snapshotted before any of that tick's actions run); guard
        # defensively rather than let ``_attribute_core_capture``'s
        # ``zip(..., strict=True)`` raise on a length mismatch.
        killer = (
            _attribute_core_capture(state, addrs, before, vm)
            if len(before) == len(addrs)
            else None
        )
        state.alive = False
        state.entrant_termination = "core_captured"
        if killer is not None and killer != state.agent_id:
            scoring.score_kill(score, killer)
            statistics_collector.record_death(statistics, state.agent_id, killer)
            events.append({"type": "kill", "victim": state.agent_id, "by": killer})
        else:
            statistics_collector.record_death(statistics, state.agent_id)
            events.append({"type": "death", "victim": state.agent_id})


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


@dataclass(init=False)
class PythonEntrantState:
    """Python execution state for one entrant.

    References the entrant's :class:`~battle_engine.entrant_identity.
    EntrantIdentity` rather than storing ``agent_id``/``name`` as
    independent fields -- see
    ``docs/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md``. Both remain
    available as read-only compatibility properties: the identity itself
    never mutates once construction finishes, matching every other field
    below that genuinely does (``pc``, ``alive``, RNG-consumed state,
    accounting counters, diagnostics).
    """

    identity: EntrantIdentity
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
    # v2.0.0-alpha.1: this entrant's own core-region anchor
    # (``entrant.start % arena_size``), fixed at construction and never
    # moved by ``JUMP`` or anything else -- unlike ``pc``, which the
    # entrant's own actions can relocate. Always populated (harmless and
    # unused under Ruleset v1); only ``apply_core_capture`` reads it, and
    # only under ``bytefray-rules-2-alpha1``.
    core_start: int = 0

    def __init__(
        self,
        agent_id: str,
        name: str,
        loaded: LoadedPythonAgent,
        rng: random.Random,
        slot: int = 0,
        derived_seed: int = 0,
        source_digest: str = "",
        local_source_fingerprint: str | None = None,
        agent_dir: Path | None = None,
        local_source_fingerprint_final: str | None = None,
        pc: int = 0,
        register_a: int = 0,
        register_p: int = 0,
        zero_flag: bool = False,
        last_read: int | None = None,
        alive: bool = True,
        cpu_used: int = 0,
        total_actions: int = 0,
        mem_writes: int = 0,
        region: tuple[int, int] = (0, 0),
        diagnostic: RuntimeDiagnostic | None = None,
        entrant_termination: str | None = None,
        core_start: int = 0,
    ) -> None:
        self.identity = EntrantIdentity(agent_id=agent_id, name=name)
        self.loaded = loaded
        self.rng = rng
        self.slot = slot
        self.derived_seed = derived_seed
        self.source_digest = source_digest
        self.local_source_fingerprint = local_source_fingerprint
        self.agent_dir = agent_dir
        self.local_source_fingerprint_final = local_source_fingerprint_final
        self.pc = pc
        self.register_a = register_a
        self.register_p = register_p
        self.zero_flag = zero_flag
        self.last_read = last_read
        self.alive = alive
        self.cpu_used = cpu_used
        self.total_actions = total_actions
        self.mem_writes = mem_writes
        self.region = region
        self.diagnostic = diagnostic
        self.entrant_termination = entrant_termination
        self.core_start = core_start

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    @property
    def name(self) -> str:
        return self.identity.name


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
        ruleset_policy: RulesetPolicy = RULESET_V1,
    ):
        self.config = config
        self.trace_writer = trace_writer
        self.ruleset_policy = ruleset_policy
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
                core_start=entrant.start % config.arena_size,
            )
            if has_vulnerable_core(self.ruleset_policy.ruleset_id):
                seed_core_ownership(
                    state, self.vm, beacon=core_seed_byte(self.ruleset_policy.ruleset_id)
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

    def _execute_action_slot(
        self,
        state: PythonEntrantState,
        action_slot: int,
        tick: int,
        events: list[dict[str, Any]],
    ) -> None:
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
            # Exception, not BaseException: an operator's Ctrl-C
            # (KeyboardInterrupt) or an agent's own sys.exit() (SystemExit)
            # must propagate and actually stop the match, not be silently
            # absorbed as a routine agent forfeit -- that was previously
            # the only way to abort a hung or runaway Python match short
            # of SIGKILL.
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

    def run(self, sink: ReplaySink, *, verbose: bool) -> PythonRuntimeResult:
        replay = ReplayPublisher(sink)
        ticks_run = 0
        try:
            replay.publish_header(self.config)
            # Publish initial entrant state as tick 0, before any act()
            # call. Python entrants never populate the arena (source is not
            # loaded into memory), so memory_diffs is empty here under
            # Ruleset v1 -- but not under bytefray-rules-2-alpha1, whose
            # __init__ already seeded each entrant's own core ownership
            # (see seed_core_ownership) before this call, exactly mirroring
            # how match.py's MatchRunner.run publishes the VM's own
            # spawn-time load_code diffs as tick zero.
            replay.publish_tick(
                0, self.states, self.score, self.vm, []  # type: ignore[arg-type]
            )
            is_vulnerable_core = has_vulnerable_core(self.ruleset_policy.ruleset_id)
            is_observable_core = has_observable_core(self.ruleset_policy.ruleset_id)
            for tick in range(1, self.max_ticks + 1):
                ticks_run = tick
                self.vm.clear_tick_diffs()
                events: list[dict[str, Any]] = []
                for state in self.states:
                    state.cpu_used = 0
                pre_tick_core_owners = (
                    _snapshot_core_owners(self.states, self.vm) if is_vulnerable_core else {}
                )

                def execute_slot(
                    state: PythonEntrantState,
                    action_slot: int,
                    *,
                    _tick: int = tick,
                    _events: list[dict[str, Any]] = events,
                ) -> None:
                    self._execute_action_slot(state, action_slot, _tick, _events)

                self.ruleset_policy.run_scheduler(
                    self.states, self.config.instr_per_tick, execute_slot
                )

                if is_vulnerable_core:
                    apply_core_capture(
                        self.states,
                        self.vm,
                        pre_tick_core_owners,
                        self.scoring,
                        self.score,
                        self.statistics_collector,
                        self.statistics,
                        events,
                    )
                if is_observable_core:
                    maintain_core_beacons(self.states, self.vm)

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
                if self.ruleset_policy.resolve_termination(
                    alive_count=sum(state.alive for state in self.states),
                    tick=tick,
                    max_ticks=self.max_ticks,
                ).terminated:
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

        termination_decision = self.ruleset_policy.resolve_termination(
            alive_count=sum(state.alive for state in self.states),
            tick=ticks_run,
            max_ticks=self.max_ticks,
        )
        assert termination_decision.reason is not None
        termination_reason = termination_decision.reason
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
    "CORE_BEACON_BYTE",
    "CORE_SEED_BYTE_ALPHA1",
    "CORE_SIZE",
    "OBSERVABLE_CORE_RULESET_IDS",
    "VULNERABLE_CORE_RULESET_IDS",
    "InvalidPythonActionError",
    "PythonEntrantController",
    "PythonEntrantInitializationError",
    "PythonEntrantState",
    "PythonRuntimeResult",
    "RuntimeDiagnostic",
    "TerminationReason",
    "apply_action",
    "apply_core_capture",
    "core_addresses",
    "core_seed_byte",
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
    "has_observable_core",
    "has_vulnerable_core",
    "maintain_core_beacons",
    "seed_core_ownership",
    "validate_action",
]
