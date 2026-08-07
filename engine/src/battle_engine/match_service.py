"""Application service for resolved native BATTLE2 matches.

The service owns homogeneous VM/Python routing, execution, and partial-artifact
cleanup. Agent discovery, CLI parsing, pMARS, and external result persistence
remain outside this native boundary.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, Mapping

from battle_engine.config import Config
from battle_engine.core import Kernel
from battle_engine.python_runtime import (
    PythonEntrantController,
    PythonEntrantInitializationError,
    PythonRuntimeResult,
    RuntimeDiagnostic,
    TerminationReason,
)
from battle_engine.scoring import ScoreMap
from battle_engine.replay import iter_replay, record_to_dict
from battle_engine.result_model import (
    ReplayReference,
    ResultEnvelope,
    stable_id,
    write_json_atomic,
)
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


def _effective_winner(kernel_winner: str | None, score: ScoreMap, win_mode: str) -> str:
    if kernel_winner:
        return kernel_winner
    if win_mode in ("score", "score_fallback"):
        ranked = sorted(score.items(), key=lambda item: (-item[1], item[0]))
        if not ranked:
            return "tie"
        if len(ranked) == 1:
            return ranked[0][0]
        if ranked[0][1] > ranked[1][1]:
            return ranked[0][0]
    return "tie"


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
        winner=_effective_winner(kernel_winner, dict(score), kernel.cfg.win_mode),
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
        winner=_effective_winner(runtime.winner, dict(runtime.score), config.win_mode),
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
    result_id = stable_id(
        "result",
        {
            "match_id": match_id,
            "winner": result.winner,
            "termination_reason": result.termination_reason.value,
            "ticks": result.ticks_run,
            "score": dict(result.score),
            "entrants": entrants,
        },
    )

    records = list(iter_replay(result.replay_path))
    canonical: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        data = record_to_dict(record)
        data["schema_version"] = 3
        if index == 0:
            data.update(
                replay_id=match_id,
                match_id=match_id,
                result_id=result_id,
                reproducibility=reproducibility,
                entrants=[
                    {"agent_id": item["agent_id"], "name": item["name"], **item["metadata"]}
                    for item in entrants
                ],
            )
        canonical.append(data)
    canonical.append(
        {
            "schema": "battle2.replay",
            "schema_version": 3,
            "record_type": "result",
            "replay_id": match_id,
            "match_id": match_id,
            "result_id": result_id,
            "winner": result.winner,
            "win_mode": request.config.win_mode,
            "termination_reason": result.termination_reason.value,
            "ticks": result.ticks_run,
            "score": dict(result.score),
            "entrants": entrants,
            "agents": [],
        }
    )
    temporary = result.replay_path.with_name(f".{result.replay_path.name}.canonical.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for record in canonical:
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
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
