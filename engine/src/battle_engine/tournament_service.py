"""Headless deterministic tournament orchestration over ``NativeMatchService``."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.result_model import ResultEnvelope, read_result, stable_id, write_json_atomic

SCHEMA_NAME = "battle2.tournament"
SCHEMA_VERSION = 1


class TournamentConfigurationError(ValueError):
    code = "tournament_configuration_invalid"


@dataclass(frozen=True)
class TournamentRequest:
    entrants: tuple[MatchEntrant, ...]
    config: Config
    rounds: int
    max_ticks: int
    output_dir: Path
    seed: int = 1337
    resume: bool = True
    retry_failures: bool = False
    verbose: bool = False


@dataclass(frozen=True)
class Standing:
    agent_id: str
    played: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    score_total: float = 0.0


@dataclass(frozen=True)
class TournamentMatch:
    schedule_id: str
    round_number: int
    entrant_ids: tuple[str, str]
    seed: int
    artifact_dir: Path
    status: str
    match_id: str | None = None
    result_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class TournamentResult:
    tournament_id: str
    division: str
    standings: tuple[Standing, ...]
    matches: tuple[TournamentMatch, ...]
    state_path: Path

    @property
    def standings_by_id(self) -> Mapping[str, Standing]:
        return MappingProxyType({standing.agent_id: standing for standing in self.standings})


def derive_match_seed(seed: int, round_number: int, first: str, second: str) -> int:
    material = f"battle2-tournament-v1\0{seed}\0{round_number}\0{first}\0{second}"
    return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")


def _entrant_identity(entrant: MatchEntrant) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "agent_id": entrant.agent_id,
        "name": entrant.name,
        "kind": entrant.kind,
        "start": entrant.start,
    }
    if entrant.kind == "vm":
        identity["code_sha256"] = hashlib.sha256(entrant.code or b"").hexdigest()
    else:
        spec = entrant.python_spec
        identity.update(
            api_version=getattr(spec, "api_version", None),
            agent_version=getattr(spec, "version", None),
            entry_point=getattr(spec, "entry_point", None),
        )
        source = getattr(spec, "source_path", None)
        if isinstance(source, Path) and source.is_file():
            identity["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    return identity


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "entrant"


class TournamentService:
    def __init__(self, match_service: NativeMatchService | None = None):
        self.match_service = match_service or NativeMatchService()

    def run(self, request: TournamentRequest) -> TournamentResult:
        division = self._validate(request)
        identities = [_entrant_identity(entrant) for entrant in request.entrants]
        tournament_id = stable_id(
            "tournament",
            {
                "seed": request.seed,
                "rounds": request.rounds,
                "max_ticks": request.max_ticks,
                "config": asdict(request.config),
                "entrants": identities,
            },
        )
        state_path = request.output_dir / "tournament.json"
        prior = self._load_state(state_path, tournament_id) if request.resume else {}
        prior_matches = {
            item["schedule_id"]: item for item in prior.get("matches", ())
        }
        scheduled = self._schedule(request, tournament_id)
        completed: list[TournamentMatch] = []
        canonical_results: list[ResultEnvelope] = []

        for item, entrants in scheduled:
            previous = prior_matches.get(item.schedule_id)
            result_path = item.artifact_dir / "result.json"
            if previous and previous.get("status") == "completed" and result_path.is_file():
                envelope = read_result(result_path)
                canonical_results.append(envelope)
                completed.append(
                    replace(
                        item,
                        status="completed",
                        match_id=envelope.match_id,
                        result_id=envelope.result_id,
                    )
                )
                continue
            if (
                previous
                and previous.get("status") in {"failed", "rejected"}
                and not request.retry_failures
            ):
                completed.append(
                    replace(
                        item,
                        status=previous["status"],
                        error_code=previous.get("error_code"),
                        error_message=previous.get("error_message"),
                    )
                )
                continue
            try:
                native = self.match_service.run(
                    MatchRequest(
                        config=replace(request.config, seed=item.seed),
                        entrants=entrants,
                        max_ticks=request.max_ticks,
                        replay_path=item.artifact_dir / "replay.jsonl",
                        verbose=request.verbose,
                    )
                )
                envelope = read_result(native.result_path)
                canonical_results.append(envelope)
                completed.append(
                    replace(
                        item,
                        status="completed",
                        match_id=envelope.match_id,
                        result_id=envelope.result_id,
                    )
                )
            except Exception as exc:
                code = getattr(
                    getattr(exc, "diagnostic", None), "code", None
                ) or getattr(exc, "code", "match_failed")
                rejected_markers = (
                    "configuration",
                    "composition",
                    "initial",
                    "contract",
                    "reset",
                )
                status = (
                    "rejected"
                    if any(marker in code for marker in rejected_markers)
                    else "failed"
                )
                completed.append(
                    replace(
                        item,
                        status=status,
                        error_code=code,
                        error_message=" ".join(str(exc).split())[:240],
                    )
                )
            self._write_state(state_path, tournament_id, division, completed)

        standings = self._standings(request.entrants, canonical_results)
        self._write_state(state_path, tournament_id, division, completed, standings)
        return TournamentResult(tournament_id, division, standings, tuple(completed), state_path)

    def _validate(self, request: TournamentRequest) -> str:
        if len(request.entrants) < 2 or request.rounds < 1 or request.max_ticks < 1:
            raise TournamentConfigurationError(
                "Tournament requires 2+ entrants, positive rounds, and a positive tick limit."
            )
        ids = [entrant.agent_id for entrant in request.entrants]
        if len(set(ids)) != len(ids):
            raise TournamentConfigurationError("Tournament entrant IDs must be unique.")
        kinds = {entrant.kind for entrant in request.entrants}
        if len(kinds) != 1 or not kinds <= {"vm", "python"}:
            raise TournamentConfigurationError(
                "Tournament divisions must be all VM or all Python; "
                "mixed groups are unsupported."
            )
        return next(iter(kinds))

    def _schedule(self, request: TournamentRequest, tournament_id: str):
        scheduled = []
        ordinal = 0
        for round_number in range(1, request.rounds + 1):
            for first_index in range(len(request.entrants) - 1):
                for second_index in range(first_index + 1, len(request.entrants)):
                    ordinal += 1
                    first = request.entrants[first_index]
                    second = request.entrants[second_index]
                    seed = derive_match_seed(
                        request.seed, round_number, first.agent_id, second.agent_id
                    )
                    schedule_id = stable_id(
                        "scheduled",
                        {
                            "tournament_id": tournament_id,
                            "round": round_number,
                            "first": first.agent_id,
                            "second": second.agent_id,
                        },
                    )
                    label = (
                        f"{ordinal:06d}-r{round_number}-{_safe_name(first.agent_id)}"
                        f"-vs-{_safe_name(second.agent_id)}"
                    )
                    directory = request.output_dir / "matches" / label
                    match = TournamentMatch(
                        schedule_id,
                        round_number,
                        (first.agent_id, second.agent_id),
                        seed,
                        directory,
                        "pending",
                    )
                    scheduled.append((match, (first, second)))
        return scheduled

    def _standings(self, entrants, results):
        rows = {entrant.agent_id: Standing(entrant.agent_id) for entrant in entrants}
        for result in results:
            ids = [str(item["agent_id"]) for item in result.entrants]
            if len(ids) != 2:
                continue
            for agent_id in ids:
                row = rows[agent_id]
                rows[agent_id] = replace(
                    row,
                    played=row.played + 1,
                    score_total=row.score_total + float(result.score.get(agent_id, 0)),
                )
            if result.winner in ids:
                loser = ids[1] if result.winner == ids[0] else ids[0]
                winner = rows[result.winner]
                rows[result.winner] = replace(winner, wins=winner.wins + 1)
                rows[loser] = replace(rows[loser], losses=rows[loser].losses + 1)
            else:
                for agent_id in ids:
                    rows[agent_id] = replace(rows[agent_id], ties=rows[agent_id].ties + 1)
        return tuple(
            sorted(
                rows.values(),
                key=lambda row: (-row.wins, -row.score_total, row.agent_id),
            )
        )

    def _load_state(self, path: Path, tournament_id: str) -> dict[str, Any]:
        if not path.is_file():
            return {}
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            data.get("schema") != SCHEMA_NAME
            or data.get("schema_version") != SCHEMA_VERSION
            or data.get("tournament_id") != tournament_id
        ):
            raise TournamentConfigurationError(
                "Existing tournament state does not match this request."
            )
        return data

    def _write_state(self, path, tournament_id, division, matches, standings=()):
        write_json_atomic(
            path,
            {
                "schema": SCHEMA_NAME,
                "schema_version": SCHEMA_VERSION,
                "tournament_id": tournament_id,
                "division": division,
                "matches": [
                    {
                        **asdict(item),
                        "artifact_dir": str(item.artifact_dir.relative_to(path.parent)),
                    }
                    for item in matches
                ],
                "standings": [asdict(row) for row in standings],
            },
        )
