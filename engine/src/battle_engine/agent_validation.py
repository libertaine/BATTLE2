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
from dataclasses import dataclass, replace
from pathlib import Path

from battle_engine.agent_api import (
    AgentAction,
    AgentManifestError,
    AgentValidationError,
    MatchContext,
    Observation,
    load_python_agent,
)
from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.paths import get_data_root
from battle_engine.python_runtime import (
    InvalidPythonActionError,
    RuntimeDiagnostic,
    _safe_message,
    derive_agent_seed,
    diagnose_action_exception,
    diagnose_invalid_action,
    diagnose_load_failure,
    diagnose_reset_failure,
    validate_action,
)

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


def _format_dry_run_action(action: AgentAction) -> str:
    parts = [action.kind.name]
    if action.operand is not None:
        parts.append(f"operand={action.operand}")
    if action.value is not None:
        parts.append(f"value={action.value}")
    return " ".join(parts)


def _validate_agent(agent_id: str, *, data_root: Path | None) -> ValidationResult:
    root = (data_root or get_data_root()).expanduser().resolve()

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
    try:
        loaded.instance.reset(context)
    except Exception as exc:
        # Exception, not BaseException: KeyboardInterrupt/SystemExit must
        # propagate rather than being reported as an ordinary validation
        # failure, matching PythonEntrantController's identical narrowing.
        raise AgentValidationFailedError(
            diagnose_reset_failure(exc, agent_id=VALIDATION_AGENT_ID, slot=VALIDATION_SLOT)
        ) from exc

    # Stage 5: one deterministic act(), validated by the real action
    # validator -- not a reimplementation.
    observation = build_validation_observation()
    try:
        action = loaded.instance.act(observation)
    except Exception as exc:
        raise AgentValidationFailedError(
            diagnose_action_exception(
                exc,
                agent_id=VALIDATION_AGENT_ID,
                slot=VALIDATION_SLOT,
                tick=observation.tick,
                action_slot=0,
            )
        ) from exc

    try:
        validated_action = validate_action(action)
    except InvalidPythonActionError as exc:
        raise AgentValidationFailedError(
            diagnose_invalid_action(
                exc,
                agent_id=VALIDATION_AGENT_ID,
                slot=VALIDATION_SLOT,
                tick=observation.tick,
                action_slot=0,
            )
        ) from exc

    return ValidationResult(
        agent_id=agent_id, api_version=api_version, dry_run_action=validated_action
    )


def validate_agent(agent_id: str, *, data_root: Path | None = None) -> ValidationResult:
    """Validate one Python agent's Agent API v1 contract with one dry-run tick.

    Raises :class:`AgentValidationFailedError` at the first failing stage
    (discovery, kind, load, reset, or act); returns a
    :class:`ValidationResult` only if every stage succeeds. Any exception
    not already one of the typed validation failures (a bug in this
    module, not the agent under test) is caught once here and reported as
    a ``validation_internal_error`` diagnostic rather than propagating
    raw, matching every other failure path's no-traceback requirement.
    """

    try:
        return _validate_agent(agent_id, data_root=data_root)
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    agent_id = args.agent_id

    try:
        result = validate_agent(agent_id)
    except AgentValidationFailedError as exc:
        diagnostic = exc.diagnostic
        print(f"agent: {agent_id}", file=sys.stderr)
        print("status: invalid", file=sys.stderr)
        print(f"stage: {diagnostic.stage}", file=sys.stderr)
        print(f"code: {diagnostic.code}", file=sys.stderr)
        print(f"error: {diagnostic.message}", file=sys.stderr)
        if diagnostic.exception_type:
            print(f"detail: {diagnostic.exception_type}", file=sys.stderr)
        return 2

    print(f"agent: {agent_id}")
    print("status: valid")
    print(f"api_version: {result.api_version}")
    print(f"dry_run_action: {_format_dry_run_action(result.dry_run_action)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
