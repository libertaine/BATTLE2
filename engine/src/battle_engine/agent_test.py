"""``bytefray agents test <agent-id>`` — a short, real development match.

Runs the agent under test against either the internal reference Python
opponent (built from the Phase 1 scaffold template resource) or another
discovered Python agent, through the exact production execution boundary
(:class:`battle_engine.match_service.NativeMatchService`). Produces the
same canonical ``replay.jsonl``/``result.json``/``summary.json`` artifacts
any other native match produces, under a dedicated location beneath the
writable data root.

``agents validate`` answers "can the agent satisfy one Agent API lifecycle
call?" ``agents test`` answers a different question: "can the agent
execute through real Bytefray match semantics for a useful short
development run, and what happened?" Bytefray exits ``0`` whenever it
successfully evaluated user-agent behavior -- even when that behavior
prevented a match from starting. That covers the tested agent's own
forfeit, death, loss, or pre-tick-zero initialization failure, *and* an
explicitly selected ``--opponent``'s initialization failure (the opponent
is user-provided agent code too, being evaluated by the same development
test). Only a problem that is not a fact about evaluated user code --
an unknown agent/opponent, a non-Python opponent, or the internal
bundled ``reference`` opponent failing to initialize (Bytefray-owned
infrastructure, never the user's own code) -- is a tool failure
(exit ``2``). See ``docs/specs/agent_test.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from battle_engine.agent_api import AgentValidationError
from battle_engine.agent_scaffold import template_resource_dir
from battle_engine.agents import AgentSpec, resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchResult,
    NativeMatchService,
    PythonMatchExecutionError,
    RulesetRuntimeUnsupportedError,
    UnsupportedMatchCompositionError,
)
from battle_engine.paths import get_data_root, get_resource_root
from battle_engine.placement import resolve_direct_match_starts
from battle_engine.python_runtime import (
    PythonEntrantInitializationError,
    RuntimeDiagnostic,
)
from battle_engine.results import WINNER_TIE_SENTINEL
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID, resolve_omitted_ruleset_id

REFERENCE_OPPONENT_NAME = "reference"
DEFAULT_TICKS = 200
TESTED_AGENT_SLOT = "A"
OPPONENT_SLOT = "B"
DEFAULT_AGENT_TIMEOUT = 5.0
MIN_AGENT_TIMEOUT = 0.1
MAX_AGENT_TIMEOUT = 300.0


class AgentTestError(RuntimeError):
    """A tool/infrastructure failure that prevented a development test from running.

    Distinct from a fact about the tested agent's own behavior (§10.3 of
    ``docs/specs/agent_test.md``): every instance of this error means exit
    code ``2``, never the exit-``0`` "test completed" contract a real
    match -- including one where the tested agent forfeits, dies, or loses
    -- always uses.
    """

    def __init__(self, diagnostic: RuntimeDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def _tool_error(*, stage: str, code: str, message: str) -> AgentTestError:
    return AgentTestError(RuntimeDiagnostic(code=code, stage=stage, message=message))


def _positive_int(value: str) -> int:
    """Validate a positive ``--ticks`` value.

    A small independent copy of ``cli._positive_int`` rather than an
    import of a leading-underscore name across modules -- see
    docs/specs/agent_test.md §7/§14 item 6.
    """

    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _timeout_value(value: str) -> float:
    """Validate ``--timeout``: development-loop bounds, see docs/specs/agent_lab.md §7."""

    parsed = float(value)
    if not (MIN_AGENT_TIMEOUT <= parsed <= MAX_AGENT_TIMEOUT):
        raise argparse.ArgumentTypeError(
            f"must be between {MIN_AGENT_TIMEOUT} and {MAX_AGENT_TIMEOUT} seconds"
        )
    return parsed


def _reference_opponent_spec(resource_root: Path | None = None) -> AgentSpec:
    """Build an ``AgentSpec`` for the internal reference opponent.

    Loaded directly from the bundled ``agent_template`` package resource --
    the same static files ``bytefray agents create`` copies -- never
    copied into the user's writable ``agents/`` catalog and never
    discoverable via ``resolve_agent``/``discover_agents``.
    """

    template_dir = template_resource_dir(resource_root or get_resource_root())
    return AgentSpec(
        name=REFERENCE_OPPONENT_NAME,
        display="Bytefray reference agent",
        dir=template_dir,
        blob=None,
        defaults={},
        kind="python",
        api_version=1,
        version="0.1.0",
        source_path=(template_dir / "agent.py").resolve(),
        entry_point="agent.py:create_agent",
        manifest={
            "kind": "python",
            "api_version": 1,
            "entrypoint": "agent.py:create_agent",
            "version": "0.1.0",
        },
    )


def _resolve_python_entrant(
    agent_id: str, *, data_root: Path, role: str
) -> AgentSpec:
    """Resolve ``agent_id`` and require it to be a Python agent.

    ``role`` is only used for message text ("test agent"/"opponent"); both
    positions apply the identical unknown/non-Python checks, before the
    match is ever attempted.
    """

    try:
        spec = resolve_agent(data_root, agent_id)
    except SystemExit as exc:
        raise _tool_error(
            stage="discovery",
            code="agent_unknown",
            message=str(exc),
        ) from exc
    except AgentValidationError as exc:
        raise _tool_error(
            stage="discovery",
            code="agent_manifest_invalid",
            message=str(exc),
        ) from exc

    if spec.kind != "python":
        raise _tool_error(
            stage="discovery",
            code="agent_kind_unsupported",
            message=(
                f"{role.capitalize()} {agent_id!r} is kind {spec.kind!r}; "
                "agents test requires Python agents only."
            ),
        )
    return spec


def _run_label(opponent_name: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    tiebreaker = uuid.uuid4().hex[:8]
    safe_opponent = _safe_path_segment(opponent_name)
    return f"{timestamp}-{tiebreaker}-vs-{safe_opponent}"


def _safe_path_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "entrant"


@dataclass(frozen=True)
class DevelopmentTestOutcome:
    """Everything the CLI needs to report a completed development test."""

    agent_id: str
    opponent_name: str
    seed: int
    ticks_requested: int
    match_result: NativeMatchResult
    summary_path: Path
    ruleset_id: str = BYTEFRAY_RULESET_ID
    trace_path: Path | None = None


@dataclass(frozen=True)
class InitializationFailureOutcome:
    """A pre-tick-zero failure of evaluated user agent code (still exit 0).

    Covers two distinct cases, both exit ``0`` because both are facts
    about *user-provided* agent code the development test successfully
    evaluated: the tested agent itself (``opponent_name is None``), or an
    explicitly selected ``--opponent`` (``opponent_name`` is that
    opponent's own discovery id). The internal bundled ``reference``
    opponent is never represented by this type -- its own initialization
    failure is Bytefray-owned infrastructure breaking, not a fact about
    user code, and is reported as an :class:`AgentTestError` (exit ``2``)
    instead.
    """

    agent_id: str
    diagnostic: RuntimeDiagnostic
    opponent_name: str | None = None
    trace_path: Path | None = None


def _resolved_weights(
    defaults: Config,
    *,
    kill_weight: float | None,
    alive_weight: float | None = None,
    territory_weight: float | None = None,
) -> Weights:
    """Apply only the explicitly-requested weight overrides on top of
    ``defaults.weights`` -- v3 Phase 4 generalizes Phase 3's single-lever
    `kill_weight` contract to the other two `Weights` fields research
    might independently vary, one experiment at a time. `None` (every
    field's default) reproduces `defaults.weights` unchanged, byte for
    byte, exactly as `kill_weight=None` alone already did.
    """

    if kill_weight is None and alive_weight is None and territory_weight is None:
        return defaults.weights
    weights = defaults.weights
    if kill_weight is not None:
        weights = replace(weights, kill=kill_weight)
    if alive_weight is not None:
        weights = replace(weights, alive=alive_weight)
    if territory_weight is not None:
        weights = replace(weights, territory=territory_weight)
    return weights


def test_agent(
    agent_id: str,
    *,
    opponent: str | None = None,
    seed: int | None = None,
    ticks: int | None = None,
    timeout: float | None = None,
    trace: bool = True,
    data_root: Path | None = None,
    resource_root: Path | None = None,
    run_dir: Path | None = None,
    ruleset_id: str | None = None,
    agent_start: int | None = None,
    opponent_start: int | None = None,
    arena_size: int | None = None,
    instr_per_tick: int | None = None,
    locality_reach: int | None = None,
    kill_weight: float | None = None,
    alive_weight: float | None = None,
    territory_weight: float | None = None,
) -> DevelopmentTestOutcome | InitializationFailureOutcome:
    """Run one short, real development match for ``agent_id``.

    ``ruleset_id``/``agent_start``/``opponent_start`` are v2.0.0-alpha.1's
    additive selectors (see ``docs/V2_0_ALPHA_ARCHITECTURE.md`` Sec 6):
    ``ruleset_id`` defaults to ``None`` (``MatchRequest``'s own default,
    resolving to the frozen Ruleset v1 identity). Both start addresses
    default to ``None`` (omitted), resolved via
    :func:`battle_engine.placement.resolve_direct_match_starts` exactly as
    ``bytefray run``'s own CLI resolves omitted ``--a-start``/``--b-start``
    (v2.0.0-rc2; see that function's docstring): under Ruleset v1 an
    omitted start still resolves to ``0`` -- the exact literal value every
    existing caller already saw via the historical hardcoded
    ``MatchEntrant.python(..., 0, ...)`` construction this replaces, so
    every caller that leaves both at their defaults under Ruleset v1 sees
    byte-for-byte unchanged behavior. Under the permanent Ruleset v2
    identity, an omitted start instead resolves to a deterministic,
    non-overlapping two-seat spread layout -- v2.0.0-rc1 shipped this
    function with a same-address ``0``/``0`` default that collapsed both
    entrants' vulnerable cores onto one window under Ruleset v2, exactly
    the release-blocking defect ``bytefray run`` had; this is that same fix
    applied to this function's own independent default. This module's own
    evaluation tooling (``battle_engine.agent_evaluation``) always passes
    explicit, already-non-overlapping start values for both parameters and
    is unaffected either way.

    Returns a :class:`DevelopmentTestOutcome` for any completed match
    (win/loss/tie/forfeit/death/tick-limit -- all exit ``0`` at the CLI
    layer) or an :class:`InitializationFailureOutcome` when the tested
    agent, or an explicitly selected ``--opponent``, fails to initialize
    before tick zero (also exit ``0``: both are user-provided agent code,
    and the evaluation still succeeded -- it just found nothing to run).
    Raises :class:`AgentTestError` for every tool/infrastructure failure
    (exit ``2``) -- an unknown/non-Python test agent or opponent, the
    internal bundled ``reference`` opponent failing to initialize, or any
    other failure that is not a fact about evaluated user code. Any
    exception not already one of the typed failures above (a bug in this
    module, not the agent under test) is caught once here and reported as
    an ``agent_test_internal_error`` diagnostic, mirroring
    ``agent_validation.validate_agent``'s identical top-level catch-all.

    ``run_dir``, when given, is used verbatim as the run's artifact
    directory (created with ``exist_ok=True`` -- the caller owns its
    lifecycle) instead of this function's own default
    ``<data_root>/runs/agents_test/<agent_id>/<run_label>/`` (created with
    ``exist_ok=False``). Every existing caller leaves this ``None`` and
    sees byte-for-byte unchanged behavior; only
    ``battle_engine.agent_evaluation`` passes it, to place each evaluation
    cell's artifacts under its own ``matches/`` tree while reusing this
    function as the per-cell executor (see ``docs/specs/agent_evaluation.md``
    Sec 6).
    """

    try:
        return _test_agent(
            agent_id,
            opponent=opponent,
            seed=seed,
            ticks=ticks,
            timeout=timeout,
            trace=trace,
            data_root=data_root,
            resource_root=resource_root,
            run_dir=run_dir,
            ruleset_id=ruleset_id,
            agent_start=agent_start,
            opponent_start=opponent_start,
            arena_size=arena_size,
            instr_per_tick=instr_per_tick,
            locality_reach=locality_reach,
            kill_weight=kill_weight,
            alive_weight=alive_weight,
            territory_weight=territory_weight,
        )
    except AgentTestError:
        raise
    except Exception as exc:
        raise AgentTestError(
            RuntimeDiagnostic(
                code="agent_test_internal_error",
                stage="internal",
                message=f"{type(exc).__name__}: {exc}",
                exception_type=type(exc).__name__,
            )
        ) from exc


def _test_agent(
    agent_id: str,
    *,
    opponent: str | None,
    seed: int | None,
    ticks: int | None,
    timeout: float | None,
    trace: bool,
    data_root: Path | None,
    resource_root: Path | None,
    run_dir: Path | None = None,
    ruleset_id: str | None = None,
    agent_start: int | None = None,
    opponent_start: int | None = None,
    arena_size: int | None = None,
    instr_per_tick: int | None = None,
    locality_reach: int | None = None,
    kill_weight: float | None = None,
    alive_weight: float | None = None,
    territory_weight: float | None = None,
) -> DevelopmentTestOutcome | InitializationFailureOutcome:
    root = (data_root or get_data_root()).expanduser().resolve()
    resources = resource_root or get_resource_root()
    effective_seed = Config().seed if seed is None else seed
    effective_ticks = DEFAULT_TICKS if ticks is None else ticks
    # Unlike --seed/--ticks, None here means "unsupervised" (this
    # function's own default, matching every existing caller/test's
    # v0.4.0 behavior exactly), not "apply the CLI's 5s default" -- only
    # main() resolves a bare `bytefray agents test` invocation's implicit
    # timeout to DEFAULT_AGENT_TIMEOUT. See docs/specs/agent_lab.md §7.
    effective_timeout = timeout

    tested_spec = _resolve_python_entrant(agent_id, data_root=root, role="test agent")

    if opponent is None:
        try:
            opponent_spec = _reference_opponent_spec(resources)
        except FileNotFoundError as exc:
            raise _tool_error(
                stage="internal",
                code="agent_test_internal_error",
                message=(
                    "Internal reference opponent resource is missing or "
                    f"broken: {exc}"
                ),
            ) from exc
        opponent_name = REFERENCE_OPPONENT_NAME
    else:
        opponent_spec = _resolve_python_entrant(
            opponent, data_root=root, role="opponent"
        )
        opponent_name = opponent

    if run_dir is None:
        run_label = _run_label(opponent_name)
        effective_run_dir = root / "runs" / "agents_test" / agent_id / run_label
        exist_ok = False
    else:
        effective_run_dir = run_dir
        exist_ok = True
    try:
        effective_run_dir.mkdir(parents=True, exist_ok=exist_ok)
    except OSError as exc:
        raise _tool_error(
            stage="artifact",
            code="output_directory_failed",
            message=f"Could not create development-test output directory: {exc}",
        ) from exc
    run_dir = effective_run_dir

    replay_path = run_dir / "replay.jsonl"
    trace_path = (run_dir / "trace.jsonl") if trace else None
    # v3 Phase 0D: `None` means "this executor's historical default"
    # (`Config()`'s own field default), exactly like `seed`/`ticks` above --
    # so every existing caller that omits these two builds a byte-identical
    # `Config` and therefore a byte-identical `canonical_match_id`. Only an
    # explicit value from a controlled arena/action-budget experiment
    # (docs/V3_PHASE0_RESEARCH_BASELINE.md) ever changes it. Deliberately
    # NOT a Ruleset-semantics change: `arena_size`/`instr_per_tick` are
    # per-match *configuration*, which docs/RULES.md's "Configuration values
    # are not Ruleset identity" already separates from gameplay identity.
    # v3 Phase 3 extends this to `weights.kill` by the identical contract:
    # `None` reproduces `Config()`'s own default `Weights` unchanged; only
    # an explicit value from the payoff-characterization experiment
    # (docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md) ever changes it.
    _config_defaults = Config()
    match_config = Config(
        seed=effective_seed,
        arena_size=_config_defaults.arena_size if arena_size is None else arena_size,
        instr_per_tick=(
            _config_defaults.instr_per_tick if instr_per_tick is None else instr_per_tick
        ),
        weights=_resolved_weights(
            _config_defaults,
            kill_weight=kill_weight,
            alive_weight=alive_weight,
            territory_weight=territory_weight,
        ),
    )
    effective_agent_start, effective_opponent_start = resolve_direct_match_starts(
        ruleset_id=ruleset_id,
        arena_size=match_config.arena_size,
        entrant_count=2,
        supplied_starts=[agent_start, opponent_start],
    )
    request = MatchRequest(
        config=match_config,
        entrants=(
            MatchEntrant.python(
                TESTED_AGENT_SLOT, agent_id, effective_agent_start, tested_spec
            ),
            MatchEntrant.python(
                OPPONENT_SLOT, opponent_name, effective_opponent_start, opponent_spec
            ),
        ),
        max_ticks=effective_ticks,
        replay_path=replay_path,
        verbose=False,
        trace_path=trace_path,
        agent_call_timeout=effective_timeout,
        ruleset_id=ruleset_id,
        locality_reach=locality_reach,
    )

    try:
        match_result = NativeMatchService().run(request)
    except PythonEntrantInitializationError as exc:
        diagnostic = exc.diagnostic
        outcome_trace_path = trace_path if trace_path is not None and trace_path.exists() else None
        if diagnostic.agent_id == TESTED_AGENT_SLOT:
            return InitializationFailureOutcome(
                agent_id=agent_id, diagnostic=diagnostic, trace_path=outcome_trace_path
            )
        if diagnostic.agent_id == OPPONENT_SLOT:
            if opponent is not None:
                # An explicitly selected opponent is user-provided agent
                # code being evaluated by this development test, exactly
                # like the tested agent itself -- its initialization
                # failure is a test result (exit 0), not a tool failure.
                return InitializationFailureOutcome(
                    agent_id=agent_id,
                    diagnostic=diagnostic,
                    opponent_name=opponent_name,
                    trace_path=outcome_trace_path,
                )
            # The internal reference opponent is Bytefray-owned
            # infrastructure, not user code under evaluation; its failure
            # to initialize means the tool/reference fixture is broken.
            raise _tool_error(
                stage="internal",
                code="agent_test_internal_error",
                message=(
                    "Internal reference opponent failed to initialize; this is a "
                    f"Bytefray/tool problem, not a result about {agent_id!r}: "
                    f"{diagnostic.message}"
                ),
            ) from exc
        raise _tool_error(
            stage=diagnostic.stage,
            code="agent_test_internal_error",
            message=f"Python match initialization failed: {diagnostic.message}",
        ) from exc
    except UnsupportedMatchCompositionError as exc:
        raise _tool_error(
            stage=exc.diagnostic.stage,
            code=exc.diagnostic.code,
            message=exc.diagnostic.message,
        ) from exc
    except RulesetRuntimeUnsupportedError as exc:
        # Unreachable via this module's own entrants today -- both slots are
        # always resolved through ``_resolve_python_entrant``, which already
        # rejects any non-Python agent regardless of Ruleset (see its own
        # ``agent_kind_unsupported`` check above). Handled anyway so a future
        # change here fails closed with a clear tool error instead of an
        # unwrapped internal one.
        raise _tool_error(
            stage=exc.diagnostic.stage,
            code=exc.diagnostic.code,
            message=exc.diagnostic.message,
        ) from exc
    except PythonMatchExecutionError as exc:
        raise _tool_error(
            stage=exc.diagnostic.stage,
            code=exc.diagnostic.code,
            message=exc.diagnostic.message,
        ) from exc

    summary_path = run_dir / "summary.json"
    _write_summary(summary_path, agent_id, opponent_name, effective_seed, match_result)

    return DevelopmentTestOutcome(
        agent_id=agent_id,
        opponent_name=opponent_name,
        seed=effective_seed,
        ticks_requested=effective_ticks,
        match_result=match_result,
        summary_path=summary_path,
        ruleset_id=ruleset_id or BYTEFRAY_RULESET_ID,
        trace_path=trace_path if trace_path is not None and trace_path.exists() else None,
    )


# ---------------------------------------------------------------------------
# Multi-entrant (N >= 2) development test (v2.0.0-beta2 Phase 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupEntrantSpec:
    """One seat's assignment for a multi-entrant development-test match.

    ``seat`` is the physical match-identity slot (mirrors ``TESTED_AGENT_
    SLOT``/``OPPONENT_SLOT``'s own convention, generalized: ``"A"``,
    ``"B"``, ``"C"``, ...) -- also the entrant's position in scheduler/
    execution order: ``battle_engine.scheduler.run_sequential_quota``
    executes states in exactly the order it is given, with no separate
    "seat" concept at the engine level, so seat order *is* scheduler
    order (see ``docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md``).
    """

    seat: str
    agent_id: str
    start: int = 0


@dataclass(frozen=True)
class GroupTestOutcome:
    """Everything a multi-entrant evaluation cell needs from one completed match."""

    seats: tuple[str, ...]
    agent_ids: tuple[str, ...]
    seed: int
    ticks_requested: int
    match_result: NativeMatchResult
    ruleset_id: str
    trace_path: Path | None = None


@dataclass(frozen=True)
class GroupInitializationFailureOutcome:
    """A pre-tick-zero failure of one seat's user-provided agent code.

    Every seat in a multi-entrant match is user-provided agent code under
    evaluation -- there is no internal reference-opponent seat here, unlike
    :func:`test_agent`'s default single-opponent path (a multi-entrant
    roster is always fully explicit) -- so, mirroring
    :class:`InitializationFailureOutcome`'s own "exit 0, this is a test
    result about user code" contract, this is never wrapped as an
    :class:`AgentTestError`.
    """

    seat: str
    agent_id: str
    diagnostic: RuntimeDiagnostic
    trace_path: Path | None = None


def test_agents(
    entrants: Sequence[GroupEntrantSpec],
    *,
    seed: int | None = None,
    ticks: int | None = None,
    timeout: float | None = None,
    trace: bool = True,
    data_root: Path | None = None,
    run_dir: Path | None = None,
    ruleset_id: str | None = None,
    arena_size: int | None = None,
    instr_per_tick: int | None = None,
    locality_reach: int | None = None,
    kill_weight: float | None = None,
    alive_weight: float | None = None,
    territory_weight: float | None = None,
) -> GroupTestOutcome | GroupInitializationFailureOutcome:
    """Run one short, real N-entrant (N >= 2) development match.

    The N-entrant generalization of :func:`test_agent`, added for
    v2.0.0-beta2 Phase 2's multi-entrant evaluation methodology.
    :func:`test_agent`/:func:`_test_agent` are completely unmodified by
    this addition -- not even refactored to share an internal helper, so
    the extremely well-tested 1v1 path carries zero risk from this new
    code. Executes through the identical ``NativeMatchService`` production
    boundary every other native match uses.

    Raises :class:`AgentTestError` for tool/infrastructure failures (fewer
    than two entrants, a duplicate seat label, an unknown/non-Python
    entrant). Any exception not already one of the typed failures above is
    caught once here and reported as an ``agent_test_internal_error``
    diagnostic, mirroring :func:`test_agent`'s identical top-level
    catch-all.
    """

    try:
        return _test_agents(
            entrants,
            seed=seed,
            ticks=ticks,
            timeout=timeout,
            trace=trace,
            data_root=data_root,
            run_dir=run_dir,
            ruleset_id=ruleset_id,
            arena_size=arena_size,
            instr_per_tick=instr_per_tick,
            locality_reach=locality_reach,
            kill_weight=kill_weight,
            alive_weight=alive_weight,
            territory_weight=territory_weight,
        )
    except AgentTestError:
        raise
    except Exception as exc:
        raise AgentTestError(
            RuntimeDiagnostic(
                code="agent_test_internal_error",
                stage="internal",
                message=f"{type(exc).__name__}: {exc}",
                exception_type=type(exc).__name__,
            )
        ) from exc


def _test_agents(
    entrants: Sequence[GroupEntrantSpec],
    *,
    seed: int | None,
    ticks: int | None,
    timeout: float | None,
    trace: bool,
    data_root: Path | None,
    run_dir: Path | None = None,
    ruleset_id: str | None = None,
    arena_size: int | None = None,
    instr_per_tick: int | None = None,
    locality_reach: int | None = None,
    kill_weight: float | None = None,
    alive_weight: float | None = None,
    territory_weight: float | None = None,
) -> GroupTestOutcome | GroupInitializationFailureOutcome:
    if len(entrants) < 2:
        raise _tool_error(
            stage="discovery",
            code="agent_test_internal_error",
            message="A multi-entrant test requires at least two entrants.",
        )
    seats = [entrant.seat for entrant in entrants]
    if len(set(seats)) != len(seats):
        raise _tool_error(
            stage="discovery",
            code="agent_test_internal_error",
            message=f"Duplicate seat labels in entrant list: {seats!r}.",
        )

    root = (data_root or get_data_root()).expanduser().resolve()
    effective_seed = Config().seed if seed is None else seed
    effective_ticks = DEFAULT_TICKS if ticks is None else ticks
    effective_timeout = timeout

    specs = [
        _resolve_python_entrant(entrant.agent_id, data_root=root, role=f"entrant {entrant.seat}")
        for entrant in entrants
    ]

    if run_dir is None:
        run_label = _run_label("group")
        effective_run_dir = root / "runs" / "agents_test" / entrants[0].agent_id / run_label
        exist_ok = False
    else:
        effective_run_dir = run_dir
        exist_ok = True
    try:
        effective_run_dir.mkdir(parents=True, exist_ok=exist_ok)
    except OSError as exc:
        raise _tool_error(
            stage="artifact",
            code="output_directory_failed",
            message=f"Could not create development-test output directory: {exc}",
        ) from exc
    run_dir = effective_run_dir

    replay_path = run_dir / "replay.jsonl"
    trace_path = (run_dir / "trace.jsonl") if trace else None
    _config_defaults = Config()
    request = MatchRequest(
        # v3 Phase 0D: identical `None` == "historical default" contract as
        # `_test_agent`'s own `match_config` above -- see that comment.
        # v3 Phase 3 extends this to `weights.kill` identically.
        config=Config(
            seed=effective_seed,
            arena_size=_config_defaults.arena_size if arena_size is None else arena_size,
            instr_per_tick=(
                _config_defaults.instr_per_tick if instr_per_tick is None else instr_per_tick
            ),
            weights=_resolved_weights(
                _config_defaults,
                kill_weight=kill_weight,
                alive_weight=alive_weight,
                territory_weight=territory_weight,
            ),
        ),
        entrants=tuple(
            MatchEntrant.python(entrant.seat, entrant.agent_id, entrant.start, spec)
            for entrant, spec in zip(entrants, specs, strict=True)
        ),
        max_ticks=effective_ticks,
        replay_path=replay_path,
        verbose=False,
        trace_path=trace_path,
        agent_call_timeout=effective_timeout,
        ruleset_id=ruleset_id,
        locality_reach=locality_reach,
    )

    try:
        match_result = NativeMatchService().run(request)
    except PythonEntrantInitializationError as exc:
        diagnostic = exc.diagnostic
        outcome_trace_path = trace_path if trace_path is not None and trace_path.exists() else None
        failed_seat = diagnostic.agent_id or ""
        failed_agent_id = next(
            (entrant.agent_id for entrant in entrants if entrant.seat == failed_seat), failed_seat
        )
        return GroupInitializationFailureOutcome(
            seat=failed_seat,
            agent_id=failed_agent_id,
            diagnostic=diagnostic,
            trace_path=outcome_trace_path,
        )
    except UnsupportedMatchCompositionError as exc:
        raise _tool_error(
            stage=exc.diagnostic.stage, code=exc.diagnostic.code, message=exc.diagnostic.message
        ) from exc
    except RulesetRuntimeUnsupportedError as exc:
        raise _tool_error(
            stage=exc.diagnostic.stage, code=exc.diagnostic.code, message=exc.diagnostic.message
        ) from exc
    except PythonMatchExecutionError as exc:
        raise _tool_error(
            stage=exc.diagnostic.stage, code=exc.diagnostic.code, message=exc.diagnostic.message
        ) from exc

    return GroupTestOutcome(
        seats=tuple(seats),
        agent_ids=tuple(entrant.agent_id for entrant in entrants),
        seed=effective_seed,
        ticks_requested=effective_ticks,
        match_result=match_result,
        ruleset_id=ruleset_id or BYTEFRAY_RULESET_ID,
        trace_path=trace_path if trace_path is not None and trace_path.exists() else None,
    )


def _write_summary(
    summary_path: Path,
    agent_id: str,
    opponent_name: str,
    seed: int,
    match_result: NativeMatchResult,
) -> None:
    """Write the compatibility ``summary.json`` sibling.

    ``NativeMatchService``/``_finalize_native_artifacts`` publish
    ``replay.jsonl``/``result.json`` but never ``summary.json`` --
    mirroring ``cli.py``'s own division of responsibility (see
    docs/specs/agent_test.md §2/§9).
    """

    score_map = dict(match_result.score)
    agent_stats = {
        agent.agent_id: agent.as_legacy_statistics() for agent in match_result.agents
    }
    summary = {
        "version": 2,
        "mode": "b2",
        "seed": seed,
        "ticks": match_result.ticks_run,
        "winner": match_result.winner,
        "A_score": score_map.get(TESTED_AGENT_SLOT, 0),
        "B_score": score_map.get(OPPONENT_SLOT, 0),
        "A_alive_ticks": agent_stats.get(TESTED_AGENT_SLOT, {}).get("alive_ticks", 0),
        "B_alive_ticks": agent_stats.get(OPPONENT_SLOT, {}).get("alive_ticks", 0),
        "A_territory": agent_stats.get(TESTED_AGENT_SLOT, {}).get("territory_last", 0),
        "B_territory": agent_stats.get(OPPONENT_SLOT, {}).get("territory_last", 0),
        "params": {
            "ticks_run": match_result.ticks_run,
        },
        "agents": {"A": agent_id, "B": opponent_name},
        "score": score_map,
        "agent_stats": agent_stats,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _winner_display(match_result: NativeMatchResult, agent_id: str, opponent_name: str) -> str:
    if match_result.winner == WINNER_TIE_SENTINEL:
        return WINNER_TIE_SENTINEL
    name_by_slot = {TESTED_AGENT_SLOT: agent_id, OPPONENT_SLOT: opponent_name}
    return name_by_slot.get(match_result.winner, match_result.winner)


def _display_diagnostic_message(diagnostic: RuntimeDiagnostic, display_name: str) -> str:
    """Rewrite a shared reset/act diagnostic's synthetic slot identity for display.

    Mirrors ``agent_validation._display_message``'s already-implemented,
    already-tested pattern: only the printed text is adjusted, never the
    underlying ``RuntimeDiagnostic``.
    """

    if diagnostic.stage not in ("reset", "action") or diagnostic.agent_id is None:
        return diagnostic.message
    return diagnostic.message.replace(
        f"Python agent {diagnostic.agent_id} ", f"Python agent {display_name} ", 1
    )


def _print_completed_match(outcome: DevelopmentTestOutcome) -> None:
    match_result = outcome.match_result
    winner = _winner_display(match_result, outcome.agent_id, outcome.opponent_name)
    print(f"agent: {outcome.agent_id}")
    print(f"opponent: {outcome.opponent_name}")
    print(f"ruleset: {outcome.ruleset_id}")
    print(f"seed: {outcome.seed}")
    print(f"ticks: {match_result.ticks_run}/{outcome.ticks_requested}")
    print(f"winner: {winner}")
    print(f"termination: {match_result.termination_reason.value}")

    name_by_slot = {TESTED_AGENT_SLOT: outcome.agent_id, OPPONENT_SLOT: outcome.opponent_name}
    for agent in match_result.agents:
        if agent.diagnostic is None:
            continue
        display_name = name_by_slot.get(agent.agent_id, agent.name)
        print(
            f"forfeit: {display_name} stage={agent.diagnostic.stage} "
            f"code={agent.diagnostic.code}"
        )

    print(f"result: {match_result.result_path}")
    print(f"replay: {match_result.replay_path}")
    print(f"summary: {outcome.summary_path}")
    print(f"trace: {outcome.trace_path if outcome.trace_path is not None else 'none'}")
    print()
    print(f"Run 'bytefray replay --replay {match_result.replay_path}' to inspect it.")
    if outcome.trace_path is not None:
        print(f"Run 'bytefray agents inspect {outcome.trace_path.parent}' to inspect decisions.")


def _print_initialization_failure(outcome: InitializationFailureOutcome) -> None:
    diagnostic = outcome.diagnostic
    print(f"agent: {outcome.agent_id}")
    if outcome.opponent_name is not None:
        # The explicit opponent -- not the tested agent -- is the entrant
        # that failed to initialize; name it by its own discovery id so
        # the failing side is unambiguous.
        print(f"opponent: {outcome.opponent_name}")
    print("status: initialization_failed")
    print(f"stage: {diagnostic.stage}")
    print(f"code: {diagnostic.code}")
    display_name = outcome.opponent_name if outcome.opponent_name is not None else outcome.agent_id
    print(f"error: {_display_diagnostic_message(diagnostic, display_name)}")
    if diagnostic.exception_type:
        print(f"detail: {diagnostic.exception_type}")
    print("result: none")
    print("replay: none")
    print(f"trace: {outcome.trace_path if outcome.trace_path is not None else 'none'}")


def _print_tool_error(agent_id: str, exc: AgentTestError) -> None:
    diagnostic = exc.diagnostic
    print(f"agent: {agent_id}", file=sys.stderr)
    print("status: error", file=sys.stderr)
    print(f"stage: {diagnostic.stage}", file=sys.stderr)
    print(f"code: {diagnostic.code}", file=sys.stderr)
    print(f"error: {diagnostic.message}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray agents test",
        description=(
            "Run a short, real Bytefray development match for one Python agent "
            "against a reference opponent or another discovered Python agent. "
            "Bytefray exits 0 whenever it successfully evaluated user-agent "
            "behavior: the tested agent's own forfeit, death, loss, or "
            "pre-tick-zero initialization failure, and an explicit --opponent's "
            "initialization failure, are all successfully executed development "
            "tests. Only a problem that is not a fact about evaluated user code "
            "-- an unknown or non-Python agent/opponent, or the internal "
            "bundled reference opponent failing to initialize -- is a tool "
            "failure (exit 2)."
        ),
    )
    parser.add_argument("agent_id", help="agent's discovery id to test")
    parser.add_argument(
        "--opponent",
        default=None,
        help="discovery id of another Python agent (default: internal reference)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="match seed (default: Config().seed)"
    )
    parser.add_argument(
        "--ticks", type=_positive_int, default=None, help="tick budget (default: 200)"
    )
    parser.add_argument(
        "--timeout",
        type=_timeout_value,
        default=None,
        help=(
            f"per-call load/reset/act timeout in seconds for supervised worker "
            f"execution (default: {DEFAULT_AGENT_TIMEOUT:g}; range "
            f"{MIN_AGENT_TIMEOUT:g}-{MAX_AGENT_TIMEOUT:g}). Development-time hang "
            "containment only -- not a security sandbox."
        ),
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_false",
        default=True,
        help="do not write the trace.jsonl development-trace artifact",
    )
    parser.add_argument(
        "--ruleset",
        choices=[BYTEFRAY_RULESET_ID, BYTEFRAY_RULESET_V2_ID],
        default=None,
        help=(
            f"gameplay Ruleset identity. If omitted, defaults to "
            f"{BYTEFRAY_RULESET_V2_ID} -- agents test entrants are always "
            f"Python. {BYTEFRAY_RULESET_V2_ID} supports Python entrants only. "
            "Affects gameplay semantics and is recorded in the match's "
            "result/replay artifacts."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # The CLI (and anything shelling out to it, e.g. the Designer) is
    # supervised by default -- an interactive/end-user entry point should
    # not hang forever even when the caller never thought to pass
    # --timeout. Direct library callers (existing tests, other tooling)
    # keep test_agent()'s own unsupervised default unless they opt in.
    effective_timeout = DEFAULT_AGENT_TIMEOUT if args.timeout is None else args.timeout
    # RC1 default-Ruleset-defect fix: `agents test` entrants (the tested
    # agent and its opponent) are always Python -- _resolve_python_entrant
    # rejects anything else -- so an omitted --ruleset resolves to current
    # Python gameplay here, matching `bytefray run`'s own Python-only
    # resolution. test_agent()'s own `ruleset_id=None` default (used by
    # every direct library/test caller that never goes through this CLI)
    # is untouched -- only this CLI boundary resolves the omission.
    resolved_ruleset_id = resolve_omitted_ruleset_id(args.ruleset, {"python"})

    try:
        outcome = test_agent(
            args.agent_id,
            opponent=args.opponent,
            seed=args.seed,
            ticks=args.ticks,
            timeout=effective_timeout,
            trace=args.trace,
            ruleset_id=resolved_ruleset_id,
        )
    except AgentTestError as exc:
        _print_tool_error(args.agent_id, exc)
        return 2

    if isinstance(outcome, InitializationFailureOutcome):
        _print_initialization_failure(outcome)
        return 0

    _print_completed_match(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
