"""Qt-free adapters between Designer controls and supported Bytefray workflows."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from battle_engine.agent_evaluation import (
    EvaluationConfigurationError,
    parse_opponents,
    parse_seed_list,
    parse_seed_range,
    read_evaluation,
    rerun_command,
)
from battle_engine.launchers import build_agents_command, build_tournament_command
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
    corrupted: int
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
    counts = {"completed": 0, "failed": 0, "rejected": 0, "corrupted": 0}
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
        corrupted=counts["corrupted"],
        standings=tuple(data.get("standings", ())),
    )


# ---------------------------------------------------------------------------
# Agent Evaluation (v0.6) -- see docs/specs/agent_evaluation.md Sec 13
# ---------------------------------------------------------------------------


def build_designer_evaluate_command(
    *,
    candidate_id: str,
    baseline_id: str | None,
    opponent_ids: Iterable[str],
    seeds_text: str,
    seed_range_text: str,
    ticks: int,
    output_dir: Path,
) -> list[str]:
    """Build the ``bytefray agents evaluate`` argument list for one Designer run.

    Reuses ``battle_engine.agent_evaluation``'s own opponent/seed parsers
    rather than a second, Designer-specific implementation (Sec 13's
    explicit "share the CLI's parser" requirement) -- a
    :class:`~battle_engine.agent_evaluation.EvaluationConfigurationError`
    from either parser is re-raised as :class:`DesignerValidationError` so
    the dialog can present it the same way every other Designer validation
    error already is.
    """

    candidate = candidate_id.strip()
    if not candidate:
        raise DesignerValidationError("Candidate is required.")
    baseline = baseline_id.strip() if baseline_id else None
    if baseline == candidate:
        raise DesignerValidationError("Candidate and baseline must be different agents.")
    opponents = tuple(opponent_ids)
    if not opponents:
        raise DesignerValidationError("Select at least one opponent.")
    if seeds_text.strip() and seed_range_text.strip():
        raise DesignerValidationError("Use either explicit seeds or a seed range, not both.")
    if ticks < 1:
        raise DesignerValidationError("Ticks must be greater than zero.")
    output = output_dir.expanduser().resolve()
    if output.exists() and not output.is_dir():
        raise DesignerValidationError("Evaluation output must be a directory.")

    try:
        parse_opponents(",".join(opponents))
        if seeds_text.strip():
            parse_seed_list(seeds_text)
        elif seed_range_text.strip():
            parse_seed_range(seed_range_text)
    except EvaluationConfigurationError as exc:
        raise DesignerValidationError(str(exc)) from exc

    arguments = [candidate, "--opponents", ",".join(opponents)]
    if baseline:
        arguments.extend(("--baseline", baseline))
    if seeds_text.strip():
        arguments.extend(("--seeds", seeds_text.strip()))
    elif seed_range_text.strip():
        arguments.extend(("--seed-range", seed_range_text.strip()))
    arguments.extend(("--ticks", str(ticks), "--output", str(output)))
    return build_agents_command("evaluate", arguments)


@dataclass(frozen=True)
class EvaluationCellPresentation:
    subject_role: str
    subject_id: str
    opponent_id: str
    seed: int
    status: str
    outcome: str | None
    artifact_dir: Path
    score_subject: float | None
    score_opponent: float | None


@dataclass(frozen=True)
class EvaluationAggregatePresentation:
    subject_role: str
    subject_id: str
    matches_played: int
    wins: int
    losses: int
    ties: int


@dataclass(frozen=True)
class EvaluationComparisonPresentation:
    opponent_id: str
    seed: int
    classification: str
    candidate_outcome: str | None
    baseline_outcome: str | None
    rerun_candidate: str
    rerun_baseline: str | None


@dataclass(frozen=True)
class EvaluationPresentation:
    evaluation_id: str
    candidate_id: str
    baseline_id: str | None
    ticks: int
    state_path: Path
    cells: tuple[EvaluationCellPresentation, ...]
    aggregates: tuple[EvaluationAggregatePresentation, ...]
    comparison: tuple[EvaluationComparisonPresentation, ...]


def read_evaluation_presentation(state_path: Path) -> EvaluationPresentation:
    """Read a canonical ``evaluation.json`` into a typed, Qt-free presentation.

    Reads the artifact itself, never CLI stdout -- the same "authoritative
    source is the canonical artifact" precedent
    ``read_match_presentation``/``read_tournament_presentation`` already
    established (Sec 13).
    """

    path = state_path.expanduser().resolve()
    try:
        data = read_evaluation(path)
    except EvaluationConfigurationError as exc:
        raise DesignerValidationError(str(exc)) from exc

    candidate_id = str(data.get("candidate_id", ""))
    baseline_id = data.get("baseline_id")
    ticks = int(data.get("ticks", 0))
    base_dir = path.parent

    cells = tuple(
        EvaluationCellPresentation(
            subject_role=str(cell.get("subject_role", "")),
            subject_id=str(cell.get("subject_id", "")),
            opponent_id=str(cell.get("opponent_id", "")),
            seed=int(cell.get("seed", 0)),
            status=str(cell.get("status", "")),
            outcome=cell.get("outcome"),
            artifact_dir=(base_dir / str(cell.get("artifact_dir", ""))),
            score_subject=cell.get("score_subject"),
            score_opponent=cell.get("score_opponent"),
        )
        for cell in data.get("cells", ())
    )
    aggregates = tuple(
        EvaluationAggregatePresentation(
            subject_role=str(row.get("subject_role", "")),
            subject_id=str(row.get("subject_id", "")),
            matches_played=int(row.get("matches_played", 0)),
            wins=int(row.get("wins", 0)),
            losses=int(row.get("losses", 0)),
            ties=int(row.get("ties", 0)),
        )
        for row in data.get("aggregates", ())
    )
    comparison = tuple(
        EvaluationComparisonPresentation(
            opponent_id=str(row.get("opponent_id", "")),
            seed=int(row.get("seed", 0)),
            classification=str(row.get("classification", "")),
            candidate_outcome=row.get("candidate_outcome"),
            baseline_outcome=row.get("baseline_outcome"),
            rerun_candidate=rerun_command(candidate_id, str(row.get("opponent_id", "")), int(row.get("seed", 0)), ticks),
            rerun_baseline=(
                rerun_command(str(baseline_id), str(row.get("opponent_id", "")), int(row.get("seed", 0)), ticks)
                if baseline_id
                else None
            ),
        )
        for row in data.get("comparison", ())
    )
    return EvaluationPresentation(
        evaluation_id=str(data.get("evaluation_id", "")),
        candidate_id=candidate_id,
        baseline_id=baseline_id,
        ticks=ticks,
        state_path=path,
        cells=cells,
        aggregates=aggregates,
        comparison=comparison,
    )
