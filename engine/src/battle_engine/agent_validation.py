"""``bytefray agents validate <agent-id>`` — Agent API v1 discover/load/dry-run.

Answers "can Bytefray discover, load, initialize, and successfully execute
this agent's Agent API v1 contract?" without running a full match. Reuses
the exact production discovery (:func:`battle_engine.agents.resolve_agent`),
loading (:func:`battle_engine.agent_api.load_python_agent`), and action
validation (:func:`battle_engine.python_runtime.validate_action`) a real
Python-vs-Python match uses, plus four small diagnostic-construction
helpers factored out of :mod:`battle_engine.python_runtime` so a validation
failure and the equivalent real-match failure share one code path, not two
hand-synchronized copies. See ``docs/specs/agent_validation.md``.

Passing validation means only that the agent was discoverable, loadable,
reset successfully, accepted one deterministic observation, and returned
one action the current runtime action contract accepts. It does not mean
the agent is strategically sound, competitive, free of later-tick
failures, safe from hangs/timeouts, sandboxed, or able to complete a real
match.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

from battle_engine.agent_api import (
    ActionKind,
    AgentAction,
    AgentManifestError,
    AgentValidationError,
    MatchContext,
    Observation,
    load_python_agent,
)
from battle_engine.agent_trace import ResetRecord, TraceAction, TraceHeader, TraceObservation, TraceWriter
from battle_engine.agent_worker import AgentWorkerHandle, WorkerCallStatus
from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.paths import get_data_root
from battle_engine.python_runtime import (
    InvalidPythonActionError,
    RuntimeDiagnostic,
    _safe_message,
    _to_trace_diagnostic,
    derive_agent_seed,
    diagnose_action_exception,
    diagnose_invalid_action,
    diagnose_load_failure,
    diagnose_reset_failure,
    validate_action,
)
from battle_engine.supervised_runtime import diagnostic_for_worker_result

# The fixture's synthetic slot identity is deliberately the real slot
# letter a single Python entrant would receive in a real match, not the
# agent's own discovery id and not a validation-only sentinel: cli.py
# builds ``MatchEntrant.python("A", nameA, startA, pythonA)``, so no real
# match ever exposes an agent's own discovery id to its own reset()/act()
# -- only the slot letter. See docs/specs/agent_validation.md §7.
VALIDATION_AGENT_ID = "A"
VALIDATION_SEED = Config().seed
VALIDATION_ARENA_SIZE = Config().arena_size
VALIDATION_SLOT = 0
DEFAULT_AGENT_TIMEOUT = 5.0
MIN_AGENT_TIMEOUT = 0.1
MAX_AGENT_TIMEOUT = 300.0


@dataclass(frozen=True)
class ValidationResult:
    """Successful validation outcome for one Python agent."""

    agent_id: str
    api_version: int
    dry_run_action: AgentAction


class AgentValidationFailedError(RuntimeError):
    """Validation stopped at the first failing stage; see ``.diagnostic``."""

    def __init__(self, diagnostic: RuntimeDiagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def build_validation_context(api_version: int) -> MatchContext:
    """Build the one deterministic ``MatchContext`` used for a dry-run reset.

    Uses the exact production seed-derivation function
    (:func:`battle_engine.python_runtime.derive_agent_seed`) with fixed,
    documented inputs, and a ``tick_limit``/``action_budget`` of ``1`` --
    a dry run makes exactly one ``act()`` call, so the context does not
    overstate what it actually does.
    """

    seed = derive_agent_seed(VALIDATION_SEED, VALIDATION_SLOT, VALIDATION_AGENT_ID, api_version)
    return MatchContext(
        agent_id=VALIDATION_AGENT_ID,
        seed=seed,
        arena_size=VALIDATION_ARENA_SIZE,
        tick_limit=1,
        action_budget=1,
        rng=random.Random(seed),
    )


def build_validation_observation() -> Observation:
    """Build the one deterministic ``Observation`` used for the dry-run ``act()``.

    Field-for-field identical to a fresh entrant's genuine first
    observation in a real match: tick 0 is published before any ``act()``
    call, so the real loop's first ``act()`` happens at ``tick=1``; ``pc``
    starts at the CLI's own ``--a-start`` default of ``0``; every other
    field is ``PythonEntrantState``'s un-mutated dataclass default.
    """

    return Observation(
        tick=1,
        agent_id=VALIDATION_AGENT_ID,
        pc=0,
        register_a=0,
        register_p=0,
        zero_flag=False,
        last_read=None,
        alive=True,
    )


def _display_message(diagnostic: RuntimeDiagnostic, agent_id: str) -> str:
    """Rewrite the shared reset/act diagnostic templates' synthetic 'A'
    identity for CLI display.

    ``diagnose_reset_failure``/``diagnose_action_exception``/
    ``diagnose_invalid_action`` are shared verbatim with a real match's
    forfeit path (see the module docstring), so their message text always
    names the *fixture's* per-tick identity (``VALIDATION_AGENT_ID``,
    "A") -- correct and load-bearing for the equivalence tests, since a
    real match's own diagnostics say the same thing for its slot-A
    entrant. But a person running ``bytefray agents validate
    reset_err_agent`` never sees a second agent or a slot letter; telling
    them "Python agent A reset failed" reads as a different agent than
    the one they just named. Only the printed text is adjusted here --
    the underlying ``RuntimeDiagnostic`` returned by ``validate_agent``
    is untouched.
    """

    if diagnostic.stage in ("reset", "action"):
        return diagnostic.message.replace(
            f"Python agent {VALIDATION_AGENT_ID} ", f"Python agent {agent_id} ", 1
        )
    return diagnostic.message


def _format_dry_run_action(action: AgentAction) -> str:
    parts = [action.kind.name]
    if action.operand is not None:
        parts.append(f"operand={action.operand}")
    if action.value is not None:
        parts.append(f"value={action.value}")
    return " ".join(parts)


def _validate_agent(
    agent_id: str,
    *,
    data_root: Path | None,
    timeout: float | None = None,
    trace_path: Path | None = None,
) -> ValidationResult:
    root = (data_root or get_data_root()).expanduser().resolve()
    # None means "unsupervised" (this function's own default, matching
    # every existing caller/test's v0.4.0 behavior exactly) -- only
    # main() resolves a bare `bytefray agents validate` invocation's
    # implicit timeout to DEFAULT_AGENT_TIMEOUT. See
    # docs/specs/agent_lab.md §7.

    # Stage 1: discovery.
    try:
        spec = resolve_agent(root, agent_id)
    except SystemExit as exc:
        raise AgentValidationFailedError(
            RuntimeDiagnostic(
                code="agent_unknown",
                stage="discovery",
                message=_safe_message(exc),
                agent_id=agent_id,
            )
        ) from exc
    except AgentManifestError as exc:
        # _spec_from_dir can raise this directly, before a kind is even
        # known -- reuse diagnose_load_failure's exact message/code
        # normalization and only relabel the stage, rather than
        # duplicating its logic.
        raise AgentValidationFailedError(
            replace(
                diagnose_load_failure(exc, agent_id=agent_id, slot=VALIDATION_SLOT),
                stage="discovery",
            )
        ) from exc

    # Stage 2: supported-kind check.
    if spec.kind != "python":
        raise AgentValidationFailedError(
            RuntimeDiagnostic(
                code="agent_kind_unsupported",
                stage="discovery",
                message=(
                    f"Agent {agent_id!r} is kind {spec.kind!r}; validation currently "
                    "supports Python agents only."
                ),
                agent_id=agent_id,
            )
        )

    trace_writer = _open_validation_trace_writer(
        trace_path, api_version=spec.api_version, timeout=timeout
    )
    try:
        if timeout is None:
            return _validate_agent_unsupervised(agent_id, spec, trace_writer=trace_writer)
        return _validate_agent_supervised(agent_id, spec, timeout=timeout, trace_writer=trace_writer)
    finally:
        if trace_writer is not None:
            trace_writer.close()


def _open_validation_trace_writer(
    trace_path: Path | None, *, api_version: int | None, timeout: float | None
) -> TraceWriter | None:
    if trace_path is None:
        return None
    writer = TraceWriter(trace_path)
    writer.write_header(
        TraceHeader(
            match_seed=VALIDATION_SEED,
            agents={VALIDATION_AGENT_ID: "validate"},
            supervised=timeout is not None,
            agent_call_timeout=timeout,
        )
    )
    return writer


def _trace_validation_reset(
    trace_writer: TraceWriter | None, start: float, diagnostic: RuntimeDiagnostic | None
) -> None:
    if trace_writer is None:
        return
    trace_writer.write_reset(
        ResetRecord(
            agent_id=VALIDATION_AGENT_ID,
            wall_time_ms=(time.perf_counter() - start) * 1000,
            diagnostic=_to_trace_diagnostic(diagnostic),
        )
    )


def _validate_agent_unsupervised(
    agent_id: str, spec: Any, *, trace_writer: TraceWriter | None
) -> ValidationResult:
    """Stages 3-5, unmodified from v0.4.0: in-process, untimed. See module docstring."""

    # Stage 3: manifest/API version/entry point, import/factory, and
    # contract checking -- one indivisible call to the real production
    # loader. Not split into three CLI-visible sub-stages: doing so would
    # require either duplicating load_python_agent's internal control flow
    # or guessing where inside it a failure occurred.
    try:
        loaded = load_python_agent(spec)
    except AgentValidationError as exc:
        raise AgentValidationFailedError(
            diagnose_load_failure(exc, agent_id=VALIDATION_AGENT_ID, slot=VALIDATION_SLOT)
        ) from exc

    api_version = loaded.metadata.api_version

    # Stage 4: deterministic reset.
    context = build_validation_context(api_version)
    reset_start = time.perf_counter()
    try:
        loaded.instance.reset(context)
    except Exception as exc:
        # Exception, not BaseException: KeyboardInterrupt/SystemExit must
        # propagate rather than being reported as an ordinary validation
        # failure, matching PythonEntrantController's identical narrowing.
        diagnostic = diagnose_reset_failure(exc, agent_id=VALIDATION_AGENT_ID, slot=VALIDATION_SLOT)
        _trace_validation_reset(trace_writer, reset_start, diagnostic)
        raise AgentValidationFailedError(diagnostic) from exc
    _trace_validation_reset(trace_writer, reset_start, None)

    # Stage 5: one deterministic act(), validated by the real action
    # validator -- not a reimplementation.
    observation = build_validation_observation()
    act_start = time.perf_counter()
    try:
        action = loaded.instance.act(observation)
    except Exception as exc:
        diagnostic = diagnose_action_exception(
            exc,
            agent_id=VALIDATION_AGENT_ID,
            slot=VALIDATION_SLOT,
            tick=observation.tick,
            action_slot=0,
        )
        _trace_decision(trace_writer, observation, act_start, None, diagnostic)
        raise AgentValidationFailedError(diagnostic) from exc

    try:
        validated_action = validate_action(action)
    except InvalidPythonActionError as exc:
        diagnostic = diagnose_invalid_action(
            exc,
            agent_id=VALIDATION_AGENT_ID,
            slot=VALIDATION_SLOT,
            tick=observation.tick,
            action_slot=0,
        )
        _trace_decision(trace_writer, observation, act_start, None, diagnostic)
        raise AgentValidationFailedError(diagnostic) from exc

    _trace_decision(
        trace_writer,
        observation,
        act_start,
        TraceAction(kind=validated_action.kind.value, operand=validated_action.operand, value=validated_action.value),
        None,
    )
    return ValidationResult(
        agent_id=agent_id, api_version=api_version, dry_run_action=validated_action
    )


def _trace_decision(
    trace_writer: TraceWriter | None,
    observation: Observation,
    start: float,
    action: TraceAction | None,
    diagnostic: RuntimeDiagnostic | None,
) -> None:
    if trace_writer is None:
        return
    from battle_engine.agent_trace import DecisionRecord

    trace_writer.write_decision(
        DecisionRecord(
            tick=observation.tick,
            agent_id=VALIDATION_AGENT_ID,
            action_slot=0,
            wall_time_ms=(time.perf_counter() - start) * 1000,
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


def _validate_agent_supervised(
    agent_id: str, spec: Any, *, timeout: float, trace_writer: TraceWriter | None
) -> ValidationResult:
    """Stages 3-5 via one whole-dry-run-lifetime worker subprocess, with a timeout.

    Mirrors :class:`battle_engine.supervised_runtime.SupervisedPythonEntrantController`
    at one-call granularity -- see ``docs/specs/agent_lab.md`` §6/§10.
    """

    handle = AgentWorkerHandle(agent_id=VALIDATION_AGENT_ID, slot=VALIDATION_SLOT)
    handle.start()
    try:
        load_result = handle.load(spec, timeout=timeout)
        if load_result.status is not WorkerCallStatus.OK:
            diagnostic = diagnostic_for_worker_result(
                load_result,
                agent_id=VALIDATION_AGENT_ID,
                slot=VALIDATION_SLOT,
                stage="load",
                timeout=timeout,
                exit_code=handle.exit_code,
            )
            raise AgentValidationFailedError(diagnostic)

        assert load_result.payload is not None
        api_version = load_result.payload["metadata"]["api_version"]

        reset_start = time.perf_counter()
        reset_result = handle.reset(
            match_seed=VALIDATION_SEED,
            api_version=api_version,
            arena_size=VALIDATION_ARENA_SIZE,
            tick_limit=1,
            action_budget=1,
            timeout=timeout,
        )
        if reset_result.status is not WorkerCallStatus.OK:
            diagnostic = diagnostic_for_worker_result(
                reset_result,
                agent_id=VALIDATION_AGENT_ID,
                slot=VALIDATION_SLOT,
                stage="reset",
                timeout=timeout,
                exit_code=handle.exit_code,
            )
            _trace_validation_reset(trace_writer, reset_start, diagnostic)
            raise AgentValidationFailedError(diagnostic)
        _trace_validation_reset(trace_writer, reset_start, None)

        observation = build_validation_observation()
        act_start = time.perf_counter()
        act_result = handle.act(observation, action_slot=0, timeout=timeout)
        if act_result.status is not WorkerCallStatus.OK:
            diagnostic = diagnostic_for_worker_result(
                act_result,
                agent_id=VALIDATION_AGENT_ID,
                slot=VALIDATION_SLOT,
                stage="action",
                timeout=timeout,
                exit_code=handle.exit_code,
                tick=observation.tick,
                action_slot=0,
            )
            _trace_decision(trace_writer, observation, act_start, None, diagnostic)
            raise AgentValidationFailedError(diagnostic)

        assert act_result.payload is not None
        action_payload = act_result.payload.get("action")
        if action_payload is None:
            exc = InvalidPythonActionError("act() must return one AgentAction")
            diagnostic = diagnose_invalid_action(
                exc, agent_id=VALIDATION_AGENT_ID, slot=VALIDATION_SLOT, tick=observation.tick, action_slot=0
            )
            _trace_decision(trace_writer, observation, act_start, None, diagnostic)
            raise AgentValidationFailedError(diagnostic)

        validated_action = AgentAction(
            kind=ActionKind(action_payload["kind"]),
            operand=action_payload.get("operand"),
            value=action_payload.get("value"),
        )
        _trace_decision(
            trace_writer,
            observation,
            act_start,
            TraceAction(**action_payload),
            None,
        )
        return ValidationResult(
            agent_id=agent_id, api_version=api_version, dry_run_action=validated_action
        )
    finally:
        handle.close()


def validate_agent(
    agent_id: str,
    *,
    data_root: Path | None = None,
    timeout: float | None = None,
    trace_path: Path | None = None,
) -> ValidationResult:
    """Validate one Python agent's Agent API v1 contract with one dry-run tick.

    ``timeout=None`` (the default) is unsupervised, in-process, and
    untimed -- byte-for-byte the v0.4.0 behavior every existing caller and
    test already depends on. Passing a ``timeout`` runs the same dry run
    through one whole-call-lifetime worker subprocess instead
    (``docs/specs/agent_lab.md`` §6), so a hung ``reset()``/``act()`` is
    reported and recovered rather than hanging this call forever;
    ``bytefray agents validate``'s CLI entry point (:func:`main`) supplies
    a default timeout so the *interactive* default is safe even though
    this function's own default is not.

    Raises :class:`AgentValidationFailedError` at the first failing stage
    (discovery, kind, load, reset, or act); returns a
    :class:`ValidationResult` only if every stage succeeds. Any exception
    not already one of the typed validation failures (a bug in this
    module, not the agent under test) is caught once here and reported as
    a ``validation_internal_error`` diagnostic rather than propagating
    raw, matching every other failure path's no-traceback requirement.
    """

    try:
        return _validate_agent(agent_id, data_root=data_root, timeout=timeout, trace_path=trace_path)
    except AgentValidationFailedError:
        raise
    except Exception as exc:
        raise AgentValidationFailedError(
            RuntimeDiagnostic(
                code="validation_internal_error",
                stage="internal",
                message=_safe_message(exc),
                agent_id=agent_id,
                exception_type=type(exc).__name__,
            )
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray agents validate",
        description=(
            "Discover, load, reset, and dry-run one Agent API v1 Python agent. "
            "Passing validation proves the agent was discoverable, loadable, reset "
            "successfully, and returned one action the current runtime accepts for "
            "one deterministic tick -- it does not prove strategic correctness, "
            "later-tick success, timeout safety, sandboxing, or full-match completion."
        ),
    )
    parser.add_argument("agent_id", help="agent's discovery id to validate")
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
        "--trace-path",
        type=Path,
        default=None,
        help="write a bytefray.agent_trace v1 file for this dry run (default: none)",
    )
    return parser


def _timeout_value(value: str) -> float:
    parsed = float(value)
    if not (MIN_AGENT_TIMEOUT <= parsed <= MAX_AGENT_TIMEOUT):
        raise argparse.ArgumentTypeError(
            f"must be between {MIN_AGENT_TIMEOUT} and {MAX_AGENT_TIMEOUT} seconds"
        )
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    agent_id = args.agent_id
    # The CLI is supervised by default, matching agents test's identical
    # policy (docs/specs/agent_lab.md §7) -- validate_agent()'s own
    # default stays unsupervised for existing library callers/tests.
    effective_timeout = DEFAULT_AGENT_TIMEOUT if args.timeout is None else args.timeout

    try:
        result = validate_agent(
            agent_id, timeout=effective_timeout, trace_path=args.trace_path
        )
    except AgentValidationFailedError as exc:
        diagnostic = exc.diagnostic
        print(f"agent: {agent_id}", file=sys.stderr)
        print("status: invalid", file=sys.stderr)
        print(f"stage: {diagnostic.stage}", file=sys.stderr)
        print(f"code: {diagnostic.code}", file=sys.stderr)
        print(f"error: {_display_message(diagnostic, agent_id)}", file=sys.stderr)
        if diagnostic.exception_type:
            print(f"detail: {diagnostic.exception_type}", file=sys.stderr)
        return 2

    print(f"agent: {agent_id}")
    print("status: valid")
    print(f"api_version: {result.api_version}")
    print(f"dry_run_action: {_format_dry_run_action(result.dry_run_action)}")
    if args.trace_path is not None:
        print(f"trace: {args.trace_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
