"""Qt-free adapters between Designer controls and supported BATTLE2 workflows."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from battle_engine.launchers import build_tournament_command
from battle_engine.result_model import read_result

from app.services.agent_catalog import AgentRow


class DesignerValidationError(ValueError):
    """A concise validation error suitable for presentation in the Designer."""


@dataclass(frozen=True)
class MatchPresentation:
    winner: str
    termination_reason: str
    result_path: Path
    replay_path: Path | None


@dataclass(frozen=True)
class TournamentPresentation:
    state_path: Path
    tournament_id: str
    division: str
    completed: int
    failed: int
    rejected: int
    standings: tuple[dict[str, object], ...]


def agent_identifier(row: AgentRow) -> str:
    value = row.meta.get("name") if isinstance(row.meta, dict) else None
    return str(value or Path(row.path).name or row.name)


def agent_kind(row: AgentRow) -> str:
    value = row.meta.get("kind") if isinstance(row.meta, dict) else None
    return "python" if value == "python" else "vm"


def validate_homogeneous(rows: Iterable[AgentRow], *, minimum: int = 2) -> str:
    selected = tuple(rows)
    if len(selected) < minimum:
        raise DesignerValidationError(f"Select at least {minimum} agents.")
    kinds = {agent_kind(row) for row in selected}
    if len(kinds) != 1:
        raise DesignerValidationError(
            "Mixed VM/Python execution is unsupported; select agents of one runtime kind."
        )
    return next(iter(kinds))


def match_artifact_paths(replay_path: Path) -> tuple[Path, Path]:
    replay = replay_path.expanduser().resolve()
    return replay.with_name("result.json"), replay


def new_match_run_directory(battle_root: Path) -> Path:
    """A fresh, collision-free artifact directory for one Designer match run.

    Each call returns a distinct path (UTC timestamp plus a short random
    suffix), so two runs -- launched in immediate succession, or by a stale
    process racing a new one -- can never share result/replay/summary files.
    This is filesystem organization only: the returned path is never an
    input to canonical match/result identity (``match_service.stable_id``
    hashes match content, never a filesystem location), so it is safe to
    change this naming scheme at any time without affecting `match_id`.
    """

    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    label = f"{stamp}-{uuid.uuid4().hex[:8]}"
    return battle_root.expanduser().resolve() / "runs" / "_designer" / label


def read_match_presentation(result_path: Path) -> MatchPresentation:
    path = result_path.expanduser().resolve()
    result = read_result(path)
    replay = None
    if result.replay is not None:
        candidate = Path(result.replay.filename)
        replay = candidate if candidate.is_absolute() else path.parent / candidate
        replay = replay.resolve()
    return MatchPresentation(
        winner=result.winner,
        termination_reason=result.termination_reason,
        result_path=path,
        replay_path=replay,
    )


def build_designer_tournament_command(
    rows: Iterable[AgentRow], *, rounds: int, seed: int, output_dir: Path
) -> list[str]:
    selected = tuple(rows)
    validate_homogeneous(selected)
    if rounds < 1:
        raise DesignerValidationError("Rounds must be greater than zero.")
    if seed < 0:
        raise DesignerValidationError("Tournament seed cannot be negative.")
    output = output_dir.expanduser().resolve()
    if output.exists() and not output.is_dir():
        raise DesignerValidationError("Tournament output must be a directory.")
    identifiers = [agent_identifier(row) for row in selected]
    if len(set(identifiers)) != len(identifiers):
        raise DesignerValidationError("Tournament agent names must be unique.")
    return build_tournament_command(
        [*identifiers, "--rounds", str(rounds), "--seed", str(seed), "--output", str(output)]
    )


def read_tournament_presentation(state_path: Path) -> TournamentPresentation:
    path = state_path.expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "battle2.tournament" or data.get("schema_version") != 1:
        raise DesignerValidationError("Unsupported tournament state format.")
    matches = data.get("matches", ())
    counts = {"completed": 0, "failed": 0, "rejected": 0}
    for match in matches:
        status = match.get("status")
        if status in counts:
            counts[status] += 1
    return TournamentPresentation(
        state_path=path,
        tournament_id=str(data.get("tournament_id", "")),
        division=str(data.get("division", "")),
        completed=counts["completed"],
        failed=counts["failed"],
        rejected=counts["rejected"],
        standings=tuple(data.get("standings", ())),
    )
