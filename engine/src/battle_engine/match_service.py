"""Application service for resolved native BATTLE2 matches.

The service owns homogeneous VM/Python routing, execution, and partial-artifact
cleanup. Agent discovery, CLI parsing, pMARS, and external result persistence
remain outside this native boundary.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
import hashlib
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, Mapping, cast

from battle_engine.config import Config
from battle_engine.core import Kernel
from battle_engine.python_runtime import (
    PythonEntrantController,
    PythonEntrantInitializationError,
    PythonRuntimeResult,
    RuntimeDiagnostic,
    TerminationReason,
)
from battle_engine.replay import (
    MatchResult as ReplayMatchResult,
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
from battle_engine.telemetry import JSONLSink, NullSummarySink


@dataclass(frozen=True)
class MatchEntrant:
    """Explicitly typed resolved entrant for one native execution path."""

    agent_id: str
    name: str
    start: int
    code: bytes | None
    kind: str = "vm"
    python_spec: Any | None = None

    @classmethod
    def python(cls, agent_id: str, name: str, start: int, spec: Any) -> "MatchEntrant":
        return cls(agent_id, name, start, None, "python", spec)


@dataclass(frozen=True)
class MatchRequest:
    """Complete input required to execute one homogeneous native match."""

    config: Config
    entrants: tuple[MatchEntrant, ...]
    max_ticks: int
    replay_path: Path
    verbose: bool = True


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
    return NativeMatchResult(
        winner=_effective_winner(kernel_winner),
        ticks_run=ticks_run,
        score=score,
        agents=tuple(agent_results),
        replay_path=replay_path,
        termination_reason=(
            TerminationReason.ALL_AGENTS_DEAD
            if not any(agent.alive for agent in kernel.agents)
            else TerminationReason.LAST_AGENT_STANDING
            if sum(agent.alive for agent in kernel.agents) == 1
            else TerminationReason.TICK_LIMIT
        ),
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


def _run_python_match(
    request: MatchRequest, replay_path: Path, summary_path: Path
) -> NativeMatchResult:
    _remove_python_artifacts(replay_path, summary_path)
    try:
        controller = PythonEntrantController(
            request.config, request.entrants, request.max_ticks
        )
    except PythonEntrantInitializationError:
        _remove_python_artifacts(replay_path, summary_path)
        raise
    except BaseException as exc:
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
        temporary_path.replace(replay_path)
        temporary_path = None
        return _build_python_result(runtime, request.config, replay_path)
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
    except BaseException as exc:
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


def _finalize_native_artifacts(
    request: MatchRequest, result: NativeMatchResult
) -> NativeMatchResult:
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
    identity = {
        "mode": "b2",
        "reproducibility": reproducibility,
        "entrants": [
            {
                "agent_id": entrant["agent_id"],
                "name": entrant["name"],
                "metadata": entrant["metadata"],
            }
            for entrant in entrants
        ],
    }
    match_id = stable_id("match", identity)
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

    header: ReplayHeader | None = None
    ticks: list[Any] = []
    for record in iter_replay(result.replay_path):
        if isinstance(record, ReplayHeader):
            header = replace(
                record,
                replay_id=match_id,
                match_id=match_id,
                result_id=result_id,
                runtime_kind=runtime_kind,
                reproducibility=reproducibility,
                entrants=tuple(entrants),
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

    temporary = result.replay_path.with_name(f".{result.replay_path.name}.canonical.tmp")
    try:
        write_replay(temporary, [header, *ticks, terminal])
        temporary.replace(result.replay_path)
    finally:
        temporary.unlink(missing_ok=True)
    replay_digest = hashlib.sha256(result.replay_path.read_bytes()).hexdigest()
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
        replay=ReplayReference(match_id, replay_digest, result.replay_path.name),
    )
    result_path = result.replay_path.with_name("result.json")
    write_json_atomic(result_path, envelope.as_dict())
    return replace(
        result,
        result_id=result_id,
        match_id=match_id,
        replay_sha256=replay_digest,
        result_path=result_path,
    )


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

        replay_path = request.replay_path.resolve()
        summary_path = replay_path.with_name("summary.json")
        if "python" in kinds:
            return _finalize_native_artifacts(
                request, _run_python_match(request, replay_path, summary_path)
            )
        replay_path.with_name("result.json").unlink(missing_ok=True)
        replay_path.parent.mkdir(parents=True, exist_ok=True)
        sink = JSONLSink(str(replay_path))
        try:
            kernel = Kernel(request.config, sink, summary_sink=NullSummarySink())
            for entrant in request.entrants:
                assert entrant.code is not None
                kernel.spawn(
                    entrant.agent_id,
                    entrant.start % request.config.arena_size,
                    entrant.code,
                )
            kernel_winner = kernel.run(max_ticks=request.max_ticks, verbose=request.verbose)
        except BaseException:
            sink.close()
            replay_path.unlink(missing_ok=True)
            summary_path.unlink(missing_ok=True)
            replay_path.with_name("result.json").unlink(missing_ok=True)
            raise
        finally:
            sink.close()
        return _finalize_native_artifacts(
            request, _build_result(kernel, request.entrants, kernel_winner, replay_path)
        )


__all__ = [
    "MatchEntrant",
    "MatchRequest",
    "NativeAgentResult",
    "NativeMatchResult",
    "NativeMatchService",
    "PythonMatchExecutionError",
    "RuntimeDiagnostic",
    "UnsupportedMatchCompositionError",
]
