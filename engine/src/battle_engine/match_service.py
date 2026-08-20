"""Application service for resolved native Bytefray matches.

The service owns homogeneous VM/Python routing, execution, and partial-artifact
cleanup. Agent discovery, CLI parsing, pMARS, and external result persistence
remain outside this native boundary.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from battle_engine.agent_trace import TraceHeader, TraceWriter
from battle_engine.config import Config
from battle_engine.core import Kernel
from battle_engine.entrant_identity import EntrantIdentity
from battle_engine.python_runtime import (
    PythonEntrantController,
    PythonEntrantInitializationError,
    PythonRuntimeResult,
    RuntimeDiagnostic,
    TerminationReason,
    derive_agent_seed,
)
from battle_engine.replay import (
    MatchResult as ReplayMatchResult,
)
from battle_engine.replay import (
    ReplayHeader,
    RuntimeKind,
    iter_replay,
    write_replay,
)
from battle_engine.result_model import (
    ReplayReference,
    ResultEnvelope,
    stable_id,
    write_json_atomic,
)
from battle_engine.results import WINNER_TIE_SENTINEL
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import RulesetPolicy, resolve_ruleset_policy
from battle_engine.supervised_runtime import SupervisedPythonEntrantController
from battle_engine.telemetry import JSONLSink, NullSummarySink


@dataclass(frozen=True, init=False)
class MatchEntrant:
    """Explicitly typed resolved entrant for one native execution path.

    Composes the entrant's :class:`~battle_engine.entrant_identity.
    EntrantIdentity` (who) with this match's resolved participation data --
    ``start``/``code``/``kind``/``python_spec`` (how this entrant
    participates in *this* match) -- rather than storing ``agent_id``/
    ``name`` as independent fields. See
    ``docs/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md``. ``agent_id``/
    ``name`` remain read-only compatibility properties so the many call
    sites across the engine, CLI, tournament service, and tests that
    construct or read them are unaffected.
    """

    identity: EntrantIdentity
    start: int
    code: bytes | None
    kind: str = "vm"
    python_spec: Any | None = None

    def __init__(
        self,
        agent_id: str,
        name: str,
        start: int,
        code: bytes | None,
        kind: str = "vm",
        python_spec: Any | None = None,
    ) -> None:
        object.__setattr__(self, "identity", EntrantIdentity(agent_id=agent_id, name=name))
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "python_spec", python_spec)

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    @property
    def name(self) -> str:
        return self.identity.name

    @classmethod
    def python(cls, agent_id: str, name: str, start: int, spec: Any) -> MatchEntrant:
        return cls(agent_id, name, start, None, "python", spec)


@dataclass(frozen=True)
class MatchRequest:
    """Complete input required to execute one homogeneous native match.

    ``trace_path`` and ``agent_call_timeout`` are Agent Lab's two
    independently optional development-time additions
    (``docs/specs/agent_lab.md`` §4). Both default to ``None`` -- the
    "normal match path" (``bytefray run``/tournament) never sets either,
    so it executes the exact unmodified v0.4.0
    :class:`~battle_engine.python_runtime.PythonEntrantController` code
    path. Only Python compositions honor either field; a VM match request
    that happens to set them is a no-op, since VM matches have no Python
    Agent API boundary to trace or supervise.

    ``ruleset_id`` is v2.0.0-alpha.1's one additive selector (see
    ``docs/V2_0_ALPHA_ARCHITECTURE.md`` Sec 6): ``None`` continues to
    resolve to ``BYTEFRAY_RULESET_ID`` exactly as before this field
    existed, so every existing caller is unaffected. Never persisted on
    ``MatchRequest`` itself -- the *resolved* identity (this value, or the
    frozen default) is what gets threaded into the canonical match/result
    identity and the replay/result ``ruleset_id`` fields by
    ``canonical_match_id``/``_finalize_native_artifacts``, so an alpha
    artifact can never masquerade as a Ruleset-v1 one after the fact.
    """

    config: Config
    entrants: tuple[MatchEntrant, ...]
    max_ticks: int
    replay_path: Path
    verbose: bool = True
    trace_path: Path | None = None
    agent_call_timeout: float | None = None
    ruleset_id: str | None = None


@dataclass(frozen=True)
class NativeAgentResult:
    """Persistence-neutral final state and statistics for one entrant."""

    agent_id: str
    name: str
    alive: bool
    score: int | float
    alive_ticks: int
    kills: int
    deaths: int
    cpu_total: int
    mem_writes: int
    territory_last: int
    territory_max: int
    territory_avg: float
    territory_pct_last: float
    territory_pct_max: float
    territory_pct_avg: float
    diagnostic: RuntimeDiagnostic | None = None
    termination_reason: str | None = None
    metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def as_legacy_statistics(self) -> dict[str, object]:
        """Return the v0.2 CLI agent-statistics shape during migration."""

        return {
            "name": self.name,
            "alive": self.alive,
            "score": self.score,
            "alive_ticks": self.alive_ticks,
            "kills": self.kills,
            "deaths": self.deaths,
            "cpu_total": self.cpu_total,
            "mem_writes": self.mem_writes,
            "territory_last": self.territory_last,
            "territory_max": self.territory_max,
            "territory_avg": self.territory_avg,
            "territory_pct_last": self.territory_pct_last,
            "territory_pct_max": self.territory_pct_max,
            "territory_pct_avg": self.territory_pct_avg,
        }


@dataclass(frozen=True)
class NativeMatchResult:
    """Canonical internal result of one native VM or Python match."""

    winner: str
    ticks_run: int
    score: Mapping[str, int | float]
    agents: tuple[NativeAgentResult, ...]
    replay_path: Path
    termination_reason: TerminationReason
    result_id: str = ""
    match_id: str = ""
    replay_sha256: str = ""
    result_path: Path | None = None

    @property
    def agents_by_id(self) -> Mapping[str, NativeAgentResult]:
        return MappingProxyType({agent.agent_id: agent for agent in self.agents})


class UnsupportedMatchCompositionError(ValueError):
    """Native matches must be homogeneous until mixed scheduling is defined."""

    # Preserve the Phase 3a exception attribute for callers while using the
    # normalized Phase 3b diagnostic code internally.
    code = "native_match_composition_unsupported"

    def __init__(self, message: str):
        super().__init__(message)
        self.diagnostic = RuntimeDiagnostic(
            code="unsupported_match_composition",
            stage="configuration",
            message=message,
        )


class PythonMatchExecutionError(RuntimeError):
    """A Python match failed outside an entrant's controlled forfeit path."""

    def __init__(self, diagnostic: RuntimeDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class RulesetRuntimeUnsupportedError(ValueError):
    """A match's entrant runtime kind(s) are not supported by its requested Ruleset.

    Distinct from :class:`UnsupportedMatchCompositionError`: that error
    rejects *heterogeneous* entrant composition (VM mixed with Python)
    regardless of which Ruleset was requested, and is checked first. This
    error rejects an otherwise-homogeneous composition whose single runtime
    kind the *requested Ruleset* itself does not support -- currently only
    ``bytefray-rules-2``, which supports Python entrants only (Beta1
    Phase 2; see ``docs/V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md``). Raised by
    ``NativeMatchService.run`` before any entrant executes and before any
    replay/result artifact is written.
    """

    code = "ruleset_runtime_unsupported"

    def __init__(self, ruleset_id: str, unsupported_kinds: Iterable[str]):
        kinds = ", ".join(sorted(unsupported_kinds))
        message = (
            f"Ruleset {ruleset_id!r} currently supports Python entrants only "
            f"(requested runtime kind(s): {kinds}). Use {BYTEFRAY_RULESET_ID!r} "
            "for VM entrants."
        )
        super().__init__(message)
        self.ruleset_id = ruleset_id
        self.unsupported_kinds = tuple(sorted(unsupported_kinds))
        self.diagnostic = RuntimeDiagnostic(
            code=self.code,
            stage="configuration",
            message=message,
        )


def _resolve_ruleset_id(request: MatchRequest) -> str:
    """Return the Ruleset identity ``request`` actually executes/executed under.

    The one place this resolution is computed -- ``NativeMatchService.run``
    (dispatch), ``canonical_match_id`` (identity hashing), and
    ``_finalize_native_artifacts`` (persisted ``ruleset_id`` fields) all
    call this instead of each independently repeating ``request.ruleset_id
    or BYTEFRAY_RULESET_ID``, so the dispatched, hashed, and persisted
    identity can never drift apart for the same request.
    """

    return request.ruleset_id or BYTEFRAY_RULESET_ID


def _effective_winner(raw_winner: str) -> str:
    """Map ``resolve_winner``'s "no winner" empty string to a display value.

    ``raw_winner`` is always already ``results.resolve_winner``'s own output
    (see ``Kernel.run`` and ``PythonEntrantController.run``), which already
    applies every win-mode-specific rule -- there is nothing left for this
    function to recompute. It exists only to give ``NativeMatchResult`` and
    ``result.json`` a stable, non-empty display value for "no single winner",
    since both currently type ``winner`` as a required string rather than
    ``str | None`` (see ``_finalize_native_artifacts`` for the canonical
    replay's terminal record, which uses ``None`` instead).
    """

    return raw_winner or WINNER_TIE_SENTINEL


def _build_result(
    kernel: Kernel,
    entrants: tuple[MatchEntrant, ...],
    kernel_winner: str,
    replay_path: Path,
    max_ticks: int,
) -> NativeMatchResult:
    ticks_run = int(kernel.tick or 0)
    arena_size = int(kernel.cfg.arena_size or 0)
    names = {entrant.agent_id: entrant.name for entrant in entrants}
    agent_results: list[NativeAgentResult] = []
    for agent in kernel.agents:
        statistics = kernel.stats.get(agent.agent_id, {})
        territory_sum = int(statistics.get("territory_sum", 0) or 0)
        territory_last = int(statistics.get("territory_last", 0) or 0)
        territory_max = int(statistics.get("territory_max", 0) or 0)
        territory_avg = territory_sum / max(1, ticks_run)
        agent_results.append(
            NativeAgentResult(
                agent_id=agent.agent_id,
                name=names.get(agent.agent_id, agent.agent_id),
                alive=bool(agent.alive),
                score=kernel.score.get(agent.agent_id, 0),
                alive_ticks=int(statistics.get("alive_ticks", 0) or 0),
                kills=int(statistics.get("kills", 0) or 0),
                deaths=int(statistics.get("deaths", 0) or 0),
                cpu_total=int(statistics.get("total_cpu", 0) or 0),
                mem_writes=int(statistics.get("total_mem_writes", 0) or 0),
                territory_last=territory_last,
                territory_max=territory_max,
                territory_avg=territory_avg,
                territory_pct_last=(territory_last * 100.0 / arena_size if arena_size else 0.0),
                territory_pct_max=(territory_max * 100.0 / arena_size if arena_size else 0.0),
                territory_pct_avg=(territory_avg * 100.0 / arena_size if arena_size else 0.0),
                metadata=MappingProxyType(
                    {
                        "kind": "vm",
                        "entry": next(
                            (entry.start for entry in entrants if entry.agent_id == agent.agent_id),
                            0,
                        ),
                        "code_sha256": hashlib.sha256(
                            next(
                                entry.code or b""
                                for entry in entrants
                                if entry.agent_id == agent.agent_id
                            )
                        ).hexdigest(),
                    }
                ),
            )
        )
    score = MappingProxyType(dict(kernel.score))
    termination_decision = kernel.ruleset_policy.resolve_termination(
        alive_count=sum(agent.alive for agent in kernel.agents),
        tick=ticks_run,
        max_ticks=max_ticks,
    )
    assert termination_decision.reason is not None
    return NativeMatchResult(
        winner=_effective_winner(kernel_winner),
        ticks_run=ticks_run,
        score=score,
        agents=tuple(agent_results),
        replay_path=replay_path,
        termination_reason=termination_decision.reason,
    )


def _build_python_result(
    runtime: PythonRuntimeResult,
    config: Config,
    replay_path: Path,
) -> NativeMatchResult:
    arena_size = config.arena_size
    results: list[NativeAgentResult] = []
    for state in runtime.states:
        statistics = runtime.statistics[state.agent_id]
        territory_sum = int(statistics.get("territory_sum", 0) or 0)
        territory_last = int(statistics.get("territory_last", 0) or 0)
        territory_max = int(statistics.get("territory_max", 0) or 0)
        territory_avg = territory_sum / max(1, runtime.ticks_run)
        results.append(
            NativeAgentResult(
                agent_id=state.agent_id,
                name=state.name,
                alive=state.alive,
                score=runtime.score.get(state.agent_id, 0),
                alive_ticks=int(statistics.get("alive_ticks", 0) or 0),
                kills=int(statistics.get("kills", 0) or 0),
                deaths=0 if state.alive else 1,
                cpu_total=int(statistics.get("total_cpu", 0) or 0),
                mem_writes=int(statistics.get("total_mem_writes", 0) or 0),
                territory_last=territory_last,
                territory_max=territory_max,
                territory_avg=territory_avg,
                territory_pct_last=(
                    territory_last * 100.0 / arena_size if arena_size else 0.0
                ),
                territory_pct_max=(
                    territory_max * 100.0 / arena_size if arena_size else 0.0
                ),
                territory_pct_avg=(
                    territory_avg * 100.0 / arena_size if arena_size else 0.0
                ),
                diagnostic=state.diagnostic,
                termination_reason=state.entrant_termination,
                metadata=MappingProxyType(
                    {
                        "kind": "python",
                        "slot": state.slot,
                        "derived_seed": state.derived_seed,
                        "source_sha256": state.source_digest,
                        "api_version": state.loaded.metadata.api_version,
                        "agent_version": state.loaded.metadata.version,
                        # B1 (v0.7 closure pass): additive executor-recorded
                        # identity evidence -- the entry point string the
                        # executor actually resolved and imported from, and
                        # a fingerprint of every local .py file under the
                        # agent directory it actually loaded from. Both are
                        # computed once by the executor at load time (see
                        # python_runtime.PythonEntrantController/
                        # supervised_runtime), never re-derived here. Purely
                        # additive to this free-form metadata dict; readers
                        # that only know the older three keys are
                        # unaffected.
                        "entry_point": state.loaded.entry_point,
                        "local_source_fingerprint": state.local_source_fingerprint,
                        # Lazy-import closure pass: a *second* fingerprint,
                        # over the identical scope, computed once the whole
                        # match has finished (every act() call already
                        # happened) -- catches a local helper imported lazily
                        # from inside reset()/act() (rather than at module
                        # load time) that changed after the fingerprint
                        # above was captured but before that lazy import
                        # actually executed. See python_runtime.
                        # PythonEntrantController.run/supervised_runtime.
                        # SupervisedPythonEntrantController.run.
                        "local_source_fingerprint_final": state.local_source_fingerprint_final,
                    }
                ),
            )
        )
    return NativeMatchResult(
        winner=_effective_winner(runtime.winner),
        ticks_run=runtime.ticks_run,
        score=MappingProxyType(dict(runtime.score)),
        agents=tuple(results),
        replay_path=replay_path,
        termination_reason=runtime.termination_reason,
    )


def _remove_python_artifacts(replay_path: Path, summary_path: Path) -> None:
    """Remove outputs that could otherwise be mistaken for this match's success."""

    for path in (replay_path, summary_path, replay_path.with_name("result.json")):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise PythonMatchExecutionError(
                RuntimeDiagnostic(
                    code="artifact_write_failed",
                    stage="artifact",
                    message=f"Could not clear Python match artifact {path.name}: {exc}",
                    exception_type=type(exc).__name__,
                )
            ) from exc


def _open_trace_writer(request: MatchRequest) -> TraceWriter | None:
    if request.trace_path is None:
        return None
    writer = TraceWriter(request.trace_path)
    writer.write_header(
        TraceHeader(
            match_seed=request.config.seed,
            agents={entrant.agent_id: entrant.name for entrant in request.entrants},
            supervised=request.agent_call_timeout is not None,
            agent_call_timeout=request.agent_call_timeout,
        )
    )
    return writer


def _run_python_match(
    request: MatchRequest,
    replay_path: Path,
    summary_path: Path,
    ruleset_policy: RulesetPolicy,
) -> NativeMatchResult:
    _remove_python_artifacts(replay_path, summary_path)
    trace_writer = _open_trace_writer(request)
    try:
        return _run_python_match_traced(
            request, replay_path, summary_path, trace_writer, ruleset_policy
        )
    finally:
        # The trace writer must stay open across both controller
        # construction (reset records) and controller.run() (decision
        # records) -- it is only safe to close once both are done,
        # regardless of success or failure.
        if trace_writer is not None:
            trace_writer.close()


def _run_python_match_traced(
    request: MatchRequest,
    replay_path: Path,
    summary_path: Path,
    trace_writer: TraceWriter | None,
    ruleset_policy: RulesetPolicy,
) -> NativeMatchResult:
    try:
        if request.agent_call_timeout is not None:
            controller: PythonEntrantController | SupervisedPythonEntrantController = (
                SupervisedPythonEntrantController(
                    request.config,
                    request.entrants,
                    request.max_ticks,
                    agent_call_timeout=request.agent_call_timeout,
                    trace_writer=trace_writer,
                    ruleset_policy=ruleset_policy,
                )
            )
        else:
            controller = PythonEntrantController(
                request.config,
                request.entrants,
                request.max_ticks,
                trace_writer=trace_writer,
                ruleset_policy=ruleset_policy,
            )
    except PythonEntrantInitializationError:
        _remove_python_artifacts(replay_path, summary_path)
        raise
    except Exception as exc:
        _remove_python_artifacts(replay_path, summary_path)
        raise PythonMatchExecutionError(
            RuntimeDiagnostic(
                code="engine_failed",
                stage="initialization",
                message=f"Python match initialization failed: {type(exc).__name__}: {exc}",
                exception_type=type(exc).__name__,
            )
        ) from exc

    temporary_path: Path | None = None
    sink: JSONLSink | None = None
    try:
        replay_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{replay_path.name}.", suffix=".tmp", dir=replay_path.parent
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        sink = JSONLSink(str(temporary_path))
        runtime = controller.run(sink, verbose=request.verbose)
        sink = None  # The controller closes the replay publisher.
        recorded_path = temporary_path
        temporary_path = None
        return _build_python_result(runtime, request.config, recorded_path)
    except OSError as exc:
        raise PythonMatchExecutionError(
            RuntimeDiagnostic(
                code="artifact_write_failed",
                stage="artifact",
                message=f"Python replay could not be written: {type(exc).__name__}: {exc}",
                exception_type=type(exc).__name__,
            )
        ) from exc
    except PythonMatchExecutionError:
        raise
    except Exception as exc:
        raise PythonMatchExecutionError(
            RuntimeDiagnostic(
                code="engine_failed",
                stage="execution",
                message=f"Python match engine failed: {type(exc).__name__}: {exc}",
                exception_type=type(exc).__name__,
            )
        ) from exc
    finally:
        if sink is not None:
            try:
                sink.close()
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        if temporary_path is not None or not replay_path.exists():
            try:
                summary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _identity_safe_diagnostic(diagnostic: Any) -> dict[str, Any] | None:
    """Strip human-readable exception text before it enters an identity hash.

    ``message`` is built from ``str(exception)`` (see
    ``python_runtime._safe_message``) and can embed nondeterministic content
    -- a default object ``repr`` carries an ``id()``-based memory address,
    for instance. Two runs of the literal same match (same seed, same
    code) that both hit the same failure could then get different
    ``result_id``s, defeating dedup/index use cases for exactly the matches
    most worth comparing. The full message is unaffected everywhere else:
    it remains in ``result.json``'s and the replay's human-readable
    ``entrants``, only the ``result_id`` hash input excludes it.
    """

    if diagnostic is None:
        return None
    return {key: value for key, value in diagnostic.items() if key != "message"}


def canonical_match_id(request: MatchRequest) -> str:
    """Derive canonical match identity entirely from request inputs.

    Includes ``BYTEFRAY_RULESET_ID`` as a first-class identity axis, sibling
    to ``reproducibility``/``entrants`` (v0.10 Phase 4) -- never folded into
    ``reproducibility``, which is specifically about per-match
    *configuration*, not gameplay identity (see docs/RULES.md's
    "Configuration values are not Ruleset identity"). Two otherwise-identical
    execution inputs must never collide under one ``match_id`` if they ran
    under different declared gameplay semantics.

    This is a deliberate, one-time native-ID transition: because exactly one
    Ruleset has ever existed, adding it to this payload changes the
    `match_id`/`result_id`/`replay_id` a v0.10+ build computes for the same
    logical inputs relative to a pre-v0.10 build -- see
    docs/RESULT_SCHEMA.md's "Identity recipe" and docs/COMPATIBILITY.md for
    the full rationale and the resume-compatibility consequence.
    """

    entrant_identities = []
    for slot, entrant in enumerate(request.entrants):
        if entrant.kind == "vm":
            metadata = {
                "kind": "vm",
                "entry": entrant.start,
                "code_sha256": hashlib.sha256(entrant.code or b"").hexdigest(),
            }
        else:
            spec = entrant.python_spec
            source = getattr(spec, "source_path", None)
            api_version = getattr(spec, "api_version", None) or 1
            metadata = {
                "kind": "python",
                "slot": slot,
                "derived_seed": derive_agent_seed(
                    request.config.seed, slot, entrant.agent_id, api_version
                ),
                "source_sha256": (
                    hashlib.sha256(source.read_bytes()).hexdigest()
                    if isinstance(source, Path) and source.is_file()
                    else ""
                ),
                "api_version": api_version,
                "agent_version": getattr(spec, "version", None),
            }
        entrant_identities.append(
            {"agent_id": entrant.agent_id, "name": entrant.name, "metadata": metadata}
        )
    reproducibility = {
        "seed": request.config.seed,
        "arena_size": request.config.arena_size,
        "tick_limit": request.max_ticks,
        "action_budget": request.config.instr_per_tick,
        "win_mode": request.config.win_mode,
        "weights": asdict(request.config.weights),
        "entrant_order": [entrant.agent_id for entrant in request.entrants],
    }
    return stable_id(
        "match",
        {
            "mode": "b2",
            "ruleset_id": _resolve_ruleset_id(request),
            "reproducibility": reproducibility,
            "entrants": entrant_identities,
        },
    )


def _finalize_native_artifacts(
    request: MatchRequest,
    result: NativeMatchResult,
    *,
    final_replay_path: Path | None = None,
) -> NativeMatchResult:
    source_replay_path = result.replay_path
    publish_path = final_replay_path or source_replay_path
    reproducibility = {
        "seed": request.config.seed,
        "arena_size": request.config.arena_size,
        "tick_limit": request.max_ticks,
        "action_budget": request.config.instr_per_tick,
        "win_mode": request.config.win_mode,
        "weights": asdict(request.config.weights),
        "entrant_order": [entrant.agent_id for entrant in request.entrants],
    }
    entrants = [
        {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "alive": agent.alive,
            "score": agent.score,
            "termination_reason": agent.termination_reason,
            "diagnostic": (
                None if agent.diagnostic is None else asdict(agent.diagnostic)
            ),
            "statistics": agent.as_legacy_statistics(),
            "metadata": dict(agent.metadata),
        }
        for agent in result.agents
    ]
    match_id = canonical_match_id(request)
    result_identity_entrants = [
        {**entrant, "diagnostic": _identity_safe_diagnostic(entrant["diagnostic"])}
        for entrant in entrants
    ]
    result_id = stable_id(
        "result",
        {
            "match_id": match_id,
            "winner": result.winner,
            "termination_reason": result.termination_reason.value,
            "ticks": result.ticks_run,
            "score": dict(result.score),
            "entrants": result_identity_entrants,
        },
    )

    # Every native match is homogeneous by the time it reaches this point
    # (NativeMatchService.run rejects mixed composition before execution),
    # so one discriminator on the header describes every entrant. The cast
    # is safe because that same validation already restricts `kind` to
    # exactly "vm" or "python" before a request can reach this function.
    runtime_kind = cast(RuntimeKind, request.entrants[0].kind)
    resolved_ruleset_id = _resolve_ruleset_id(request)

    header: ReplayHeader | None = None
    ticks: list[Any] = []
    for record in iter_replay(source_replay_path):
        if isinstance(record, ReplayHeader):
            header = replace(
                record,
                replay_id=match_id,
                match_id=match_id,
                result_id=result_id,
                runtime_kind=runtime_kind,
                reproducibility=reproducibility,
                entrants=tuple(entrants),
                ruleset_id=resolved_ruleset_id,
                schema_version=3,
            )
        else:
            ticks.append(replace(record, schema_version=3))
    if header is None:
        raise PythonMatchExecutionError(
            RuntimeDiagnostic(
                code="artifact_write_failed",
                stage="artifact",
                message="Recorded replay is missing its header record.",
            )
        )

    termination_by_agent = {
        agent.agent_id: agent.termination_reason for agent in result.agents
    }
    final_agents = (
        tuple(
            replace(
                agent_state,
                termination_reason=termination_by_agent.get(agent_state.agent_id),
            )
            for agent_state in ticks[-1].agents
        )
        if ticks
        else ()
    )
    replay_winner = None if result.winner == WINNER_TIE_SENTINEL else result.winner
    terminal = ReplayMatchResult(
        winner=replay_winner,
        win_mode=request.config.win_mode,
        ticks=result.ticks_run,
        score=dict(result.score),
        agents=final_agents,
        replay_id=match_id,
        match_id=match_id,
        result_id=result_id,
        termination_reason=result.termination_reason.value,
        entrants=tuple(entrants),
        schema_version=3,
    )

    publish_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{publish_path.name}.", suffix=".canonical.tmp", dir=publish_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    result_path = publish_path.with_name("result.json")
    complete = False
    try:
        write_replay(temporary, [header, *ticks, terminal])
        temporary.replace(publish_path)
        replay_digest = hashlib.sha256(publish_path.read_bytes()).hexdigest()
        envelope = ResultEnvelope(
            result_id=result_id,
            match_id=match_id,
            mode="b2",
            winner=result.winner,
            termination_reason=result.termination_reason.value,
            ticks=result.ticks_run,
            score=result.score,
            entrants=tuple(entrants),
            reproducibility=reproducibility,
            replay=ReplayReference(match_id, replay_digest, publish_path.name),
            ruleset_id=resolved_ruleset_id,
        )
        write_json_atomic(result_path, envelope.as_dict())
        complete = True
        return replace(
            result,
            replay_path=publish_path,
            result_id=result_id,
            match_id=match_id,
            replay_sha256=replay_digest,
            result_path=result_path,
        )
    finally:
        temporary.unlink(missing_ok=True)
        if source_replay_path != publish_path:
            source_replay_path.unlink(missing_ok=True)
        if not complete:
            publish_path.unlink(missing_ok=True)
            result_path.unlink(missing_ok=True)
            publish_path.with_name("summary.json").unlink(missing_ok=True)


def _run_vm_match(
    request: MatchRequest,
    replay_path: Path,
    summary_path: Path,
    ruleset_policy: RulesetPolicy,
) -> NativeMatchResult:
    """Run a VM match, publishing its replay atomically.

    Mirrors ``_run_python_match``'s temp-file-then-rename shape: nothing is
    ever written at ``replay_path`` itself until the run has fully
    succeeded, so a failure at any point -- kernel construction, spawning,
    execution, or the write itself -- can never leave a partial file visible
    at the requested final path.
    """

    # Clear stale artifacts from a previous run at this exact path up front
    # (not only on failure), so a failed attempt here can never leave an old
    # success-shaped replay/summary/result sitting at the requested location
    # looking like this run's output.
    for stale in (replay_path, summary_path, replay_path.with_name("result.json")):
        stale.unlink(missing_ok=True)
    replay_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    sink: JSONLSink | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{replay_path.name}.", suffix=".tmp", dir=replay_path.parent
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        sink = JSONLSink(str(temporary_path))
        kernel = Kernel(
            request.config,
            sink,
            summary_sink=NullSummarySink(),
            ruleset_policy=ruleset_policy,
        )
        for entrant in request.entrants:
            assert entrant.code is not None
            kernel.spawn(
                entrant.agent_id,
                entrant.start % request.config.arena_size,
                entrant.code,
            )
        kernel_winner = kernel.run(max_ticks=request.max_ticks, verbose=request.verbose)
        sink.close()
        sink = None  # Closed successfully; avoid a redundant close in finally.
        recorded_path = temporary_path
        temporary_path = None
        return _build_result(
            kernel, request.entrants, kernel_winner, recorded_path, request.max_ticks
        )
    finally:
        if sink is not None:
            try:
                sink.close()
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


class NativeMatchService:
    """Route homogeneous VM or Python entrants through their native controller."""

    def run(self, request: MatchRequest) -> NativeMatchResult:
        kinds = {entrant.kind for entrant in request.entrants}
        if not request.entrants or not kinds <= {"vm", "python"} or len(kinds) != 1:
            values = ", ".join(sorted(kinds)) or "none"
            raise UnsupportedMatchCompositionError(
                "Native matches must contain either all VM entrants or all Python "
                f"entrants; received: {values}. Mixed VM/Python matches are not supported."
            )
        if "vm" in kinds and any(entrant.code is None for entrant in request.entrants):
            raise UnsupportedMatchCompositionError("Every VM entrant requires bytecode.")
        if "python" in kinds and any(
            entrant.python_spec is None for entrant in request.entrants
        ):
            raise UnsupportedMatchCompositionError(
                "Every Python entrant requires a resolved Python AgentSpec."
            )
        ids = [entrant.agent_id for entrant in request.entrants]
        if len(set(ids)) != len(ids):
            raise UnsupportedMatchCompositionError(
                f"Entrant IDs must be unique; received: {ids}."
            )

        # Resolved once here -- the one boundary where a homogeneous native
        # match's Ruleset execution semantics (entrant scheduling and match
        # termination decision/reason, as of v1.5 Phase 4) are dispatched --
        # and threaded through to whichever runtime executes, rather than
        # each runtime resolving it itself. ``request.ruleset_id`` selects
        # the Ruleset (v2.0.0-alpha.1 additive selector); ``None`` resolves
        # to the frozen ``BYTEFRAY_RULESET_ID`` exactly as every caller from
        # before this field existed still does. ``resolve_ruleset_policy``
        # fails closed for any unrecognized ID instead of silently executing
        # as Ruleset v1.
        ruleset_policy = resolve_ruleset_policy(_resolve_ruleset_id(request))

        # Beta1 Phase 2's authoritative runtime-compatibility boundary:
        # ``kinds`` (already validated as homogeneous above) and
        # ``ruleset_policy`` (just resolved) are both in scope here and
        # nowhere else upstream of a runtime actually executing -- every
        # production caller (``bytefray run``/``agents test``/``tournament``,
        # and anything built on them) inherits this check without
        # duplicating it. Fires before either runtime is invoked and before
        # any replay/result artifact exists at ``replay_path``.
        unsupported_kinds = ruleset_policy.unsupported_runtime_kinds(kinds)
        if unsupported_kinds:
            raise RulesetRuntimeUnsupportedError(ruleset_policy.ruleset_id, unsupported_kinds)

        replay_path = request.replay_path.resolve()
        summary_path = replay_path.with_name("summary.json")
        if "python" in kinds:
            recorded = _run_python_match(request, replay_path, summary_path, ruleset_policy)
            try:
                return _finalize_native_artifacts(
                    request, recorded, final_replay_path=replay_path
                )
            finally:
                recorded.replay_path.unlink(missing_ok=True)
        recorded = _run_vm_match(request, replay_path, summary_path, ruleset_policy)
        try:
            return _finalize_native_artifacts(
                request, recorded, final_replay_path=replay_path
            )
        finally:
            recorded.replay_path.unlink(missing_ok=True)


__all__ = [
    "MatchEntrant",
    "MatchRequest",
    "NativeAgentResult",
    "NativeMatchResult",
    "NativeMatchService",
    "PythonMatchExecutionError",
    "RulesetRuntimeUnsupportedError",
    "RuntimeDiagnostic",
    "UnsupportedMatchCompositionError",
    "canonical_match_id",
]
