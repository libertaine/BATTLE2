"""``bytefray agents evaluate <candidate-id>`` — a deterministic evaluation matrix.

Runs a candidate agent (and, optionally, a baseline agent for comparison)
against an explicit, author-chosen opponent/seed matrix, reusing
``agent_test.test_agent`` as the exact per-cell executor so every
evaluation cell is byte-for-byte reproducible via a plain ``bytefray
agents test`` invocation. Produces an additive, independently versioned
``bytefray.evaluation`` v1 artifact that references (never duplicates) the
canonical ``replay.jsonl``/``result.json`` each cell's real match already
writes. See ``docs/specs/agent_evaluation.md`` for the full design
rationale.

This module is Qt-free and headless: it executes agent code only via
``agent_test.test_agent`` (the same production execution boundary
``agents test`` itself uses), never independently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from battle_engine.agent_api import AgentValidationError
from battle_engine.agent_test import (
    DEFAULT_TICKS,
    OPPONENT_SLOT,
    TESTED_AGENT_SLOT,
    AgentTestError,
    InitializationFailureOutcome,
    test_agent,
)
from battle_engine.agents import AgentSpec, resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchResult,
    canonical_match_id,
)
from battle_engine.paths import get_data_root
from battle_engine.project_info import get_project_info
from battle_engine.replay import ReplayHeader, iter_replay
from battle_engine.result_model import (
    ReplayIntegrityError,
    ResultEnvelope,
    read_result,
    stable_id,
    verify_replay_digest,
    write_json_atomic,
)
from battle_engine.results import WINNER_TIE_SENTINEL

SCHEMA_NAME = "bytefray.evaluation"
SCHEMA_VERSION = 1

CANDIDATE = "candidate"
BASELINE = "baseline"

_OUTCOME_RANK = {"loss": 0, "tie": 1, "win": 2}
_REAL_OUTCOMES = frozenset(_OUTCOME_RANK)


class EvaluationConfigurationError(ValueError):
    """An invalid evaluation request or incompatible existing artifact state."""

    code = "evaluation_configuration_invalid"


# ---------------------------------------------------------------------------
# Identity (docs/specs/agent_evaluation.md Sec 8)
# ---------------------------------------------------------------------------


def source_digest(source_path: Path | None) -> str | None:
    """Hash an entry-point source file's bytes, or ``None`` if unavailable.

    The one primitive genuinely shared with ``tournament_service.
    _entrant_identity``/``match_service.canonical_match_id`` -- each of
    those builds its own differently shaped identity dict for its own
    purpose and is left untouched (see Sec 8/Sec 2 finding 8 of the spec
    for why unifying the dict shapes themselves would be a premature
    abstraction).
    """

    if source_path is None or not source_path.is_file():
        return None
    return hashlib.sha256(source_path.read_bytes()).hexdigest()


def agent_identity(spec: AgentSpec) -> dict[str, Any]:
    """A stable, hashable identity fingerprint for one resolved Python agent."""

    return {
        "agent_id": spec.name,
        "kind": spec.kind,
        "api_version": spec.api_version,
        "agent_version": spec.version,
        "entry_point": spec.entry_point,
        "source_sha256": source_digest(spec.source_path),
    }


def _resolve_python_agent(root: Path, agent_id: str) -> AgentSpec:
    try:
        spec = resolve_agent(root, agent_id)
    except SystemExit as exc:
        raise EvaluationConfigurationError(f"Unknown agent {agent_id!r}: {exc}") from exc
    except AgentValidationError as exc:
        raise EvaluationConfigurationError(
            f"Agent {agent_id!r} manifest is invalid: {exc}"
        ) from exc
    if spec.kind != "python":
        raise EvaluationConfigurationError(
            f"Agent {agent_id!r} is kind {spec.kind!r}; evaluation requires Python "
            "agents only (see docs/specs/agent_evaluation.md Sec 17)."
        )
    return spec


def _expected_cell_match_id(
    subject_spec: AgentSpec,
    subject_id: str,
    opponent_spec: AgentSpec,
    opponent_id: str,
    seed: int,
    ticks: int,
) -> str:
    """Recompute the ``match_id`` a fresh cell run would produce.

    Mirrors ``agent_test._test_agent``'s own ``MatchRequest`` construction
    exactly (same ``Config(seed=...)``, same fixed A/B slot entrants) so a
    resumed cell's recorded ``match_id`` can be verified against what this
    exact (subject, opponent, seed) combination would compute today --
    catching a source-content change the way ``tournament_service``'s
    resume verification already does (docs/specs/agent_evaluation.md
    Sec 14).
    """

    request = MatchRequest(
        config=Config(seed=seed),
        entrants=(
            MatchEntrant.python(TESTED_AGENT_SLOT, subject_id, 0, subject_spec),
            MatchEntrant.python(OPPONENT_SLOT, opponent_id, 0, opponent_spec),
        ),
        max_ticks=ticks,
        replay_path=Path("."),
    )
    return canonical_match_id(request)


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationRequest:
    candidate_id: str
    opponent_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    output_dir: Path
    baseline_id: str | None = None
    ticks: int = DEFAULT_TICKS
    resume: bool = True
    retry_failures: bool = False


@dataclass(frozen=True)
class EvaluationCell:
    schedule_id: str
    subject_role: str
    subject_id: str
    opponent_id: str
    seed: int
    artifact_dir: Path
    status: str = "pending"
    outcome: str | None = None
    match_id: str | None = None
    result_id: str | None = None
    ticks_run: int | None = None
    score_subject: float | None = None
    score_opponent: float | None = None
    territory_subject: float | None = None
    territory_opponent: float | None = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def is_scored(self) -> bool:
        return self.status == "completed" and self.outcome in _REAL_OUTCOMES


@dataclass(frozen=True)
class SubjectAggregate:
    subject_role: str
    subject_id: str
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    subject_init_failures: int = 0
    opponent_init_failures: int = 0
    failed: int = 0
    score_total: float = 0.0
    score_avg: float = 0.0
    score_differential_avg: float = 0.0
    ticks_avg: float = 0.0
    territory_avg: float = 0.0
    territory_differential_avg: float = 0.0

    @property
    def win_rate_display(self) -> str:
        if self.matches_played == 0:
            return "0/0 (n/a)"
        pct = 100.0 * self.wins / self.matches_played
        return f"{self.wins}/{self.matches_played} ({pct:.0f}%)"


@dataclass(frozen=True)
class ComparisonEntry:
    opponent_id: str
    seed: int
    classification: str  # "improved" | "regressed" | "unchanged" | "inconclusive"
    candidate_outcome: str | None = None
    baseline_outcome: str | None = None
    candidate_score: float | None = None
    baseline_score: float | None = None
    candidate_score_differential: float | None = None
    baseline_score_differential: float | None = None
    candidate_territory: float | None = None
    baseline_territory: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    evaluation_id: str
    request: EvaluationRequest
    cells: tuple[EvaluationCell, ...]
    aggregates: tuple[SubjectAggregate, ...]
    comparison: tuple[ComparisonEntry, ...]
    state_path: Path

    @property
    def failed_cells(self) -> tuple[EvaluationCell, ...]:
        return tuple(cell for cell in self.cells if cell.status == "failed")

    @property
    def corrupted_cells(self) -> tuple[EvaluationCell, ...]:
        return tuple(cell for cell in self.cells if cell.status == "corrupted")


def _safe_path_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "entrant"


def build_matrix(request: EvaluationRequest, evaluation_id: str) -> tuple[EvaluationCell, ...]:
    """Build the deterministic subject x opponent x seed matrix.

    Iteration order is candidate, then baseline (if present); opponents
    and seeds in exact request order, never re-sorted or deduplicated
    (docs/specs/agent_evaluation.md Sec 7).
    """

    subjects: list[tuple[str, str]] = [(CANDIDATE, request.candidate_id)]
    if request.baseline_id is not None:
        subjects.append((BASELINE, request.baseline_id))

    cells: list[EvaluationCell] = []
    ordinal = 0
    for role, subject_id in subjects:
        for opponent_id in request.opponent_ids:
            for seed in request.seeds:
                ordinal += 1
                schedule_id = stable_id(
                    "evaluation-cell",
                    {
                        "evaluation_id": evaluation_id,
                        "role": role,
                        "subject_id": subject_id,
                        "opponent_id": opponent_id,
                        "seed": seed,
                    },
                )
                label = (
                    f"{ordinal:04d}-{role}-{_safe_path_segment(subject_id)}"
                    f"-vs-{_safe_path_segment(opponent_id)}-seed{seed}"
                )
                cells.append(
                    EvaluationCell(
                        schedule_id=schedule_id,
                        subject_role=role,
                        subject_id=subject_id,
                        opponent_id=opponent_id,
                        seed=seed,
                        artifact_dir=request.output_dir / "matches" / label,
                    )
                )
    return tuple(cells)


# ---------------------------------------------------------------------------
# Aggregation and comparison (Sec 11)
# ---------------------------------------------------------------------------


def aggregate_cells(
    subject_role: str, subject_id: str, cells: Sequence[EvaluationCell]
) -> SubjectAggregate:
    own = [
        cell
        for cell in cells
        if cell.subject_role == subject_role and cell.subject_id == subject_id
    ]
    scored = [cell for cell in own if cell.is_scored]
    played = len(scored)
    wins = sum(1 for cell in scored if cell.outcome == "win")
    losses = sum(1 for cell in scored if cell.outcome == "loss")
    ties = sum(1 for cell in scored if cell.outcome == "tie")
    subject_init_failures = sum(1 for cell in own if cell.outcome == "subject_init_failed")
    opponent_init_failures = sum(1 for cell in own if cell.outcome == "opponent_init_failed")
    failed = sum(1 for cell in own if cell.status == "failed")

    score_total = sum(cell.score_subject or 0.0 for cell in scored)
    score_diff_total = sum(
        (cell.score_subject or 0.0) - (cell.score_opponent or 0.0) for cell in scored
    )
    ticks_total = sum(cell.ticks_run or 0 for cell in scored)
    territory_total = sum(cell.territory_subject or 0.0 for cell in scored)
    territory_diff_total = sum(
        (cell.territory_subject or 0.0) - (cell.territory_opponent or 0.0) for cell in scored
    )

    return SubjectAggregate(
        subject_role=subject_role,
        subject_id=subject_id,
        matches_played=played,
        wins=wins,
        losses=losses,
        ties=ties,
        subject_init_failures=subject_init_failures,
        opponent_init_failures=opponent_init_failures,
        failed=failed,
        score_total=score_total,
        score_avg=(score_total / played) if played else 0.0,
        score_differential_avg=(score_diff_total / played) if played else 0.0,
        ticks_avg=(ticks_total / played) if played else 0.0,
        territory_avg=(territory_total / played) if played else 0.0,
        territory_differential_avg=(territory_diff_total / played) if played else 0.0,
    )


def classify(candidate_outcome: str, baseline_outcome: str) -> str:
    """Deterministic outcome-rank comparator (Sec 11). ``win > tie > loss`` only."""

    delta = _OUTCOME_RANK[candidate_outcome] - _OUTCOME_RANK[baseline_outcome]
    if delta > 0:
        return "improved"
    if delta < 0:
        return "regressed"
    return "unchanged"


def compare_candidate_baseline(
    cells: Sequence[EvaluationCell],
) -> tuple[ComparisonEntry, ...]:
    candidate_cells = {
        (cell.opponent_id, cell.seed): cell for cell in cells if cell.subject_role == CANDIDATE
    }
    baseline_cells = {
        (cell.opponent_id, cell.seed): cell for cell in cells if cell.subject_role == BASELINE
    }
    keys = sorted(set(candidate_cells) | set(baseline_cells))

    entries: list[ComparisonEntry] = []
    for opponent_id, seed in keys:
        candidate_cell = candidate_cells.get((opponent_id, seed))
        baseline_cell = baseline_cells.get((opponent_id, seed))
        if candidate_cell is None or baseline_cell is None:
            entries.append(
                ComparisonEntry(
                    opponent_id=opponent_id,
                    seed=seed,
                    classification="inconclusive",
                    candidate_outcome=candidate_cell.outcome if candidate_cell else None,
                    baseline_outcome=baseline_cell.outcome if baseline_cell else None,
                    reason="cell missing on one side",
                )
            )
            continue
        if not candidate_cell.is_scored or not baseline_cell.is_scored:
            entries.append(
                ComparisonEntry(
                    opponent_id=opponent_id,
                    seed=seed,
                    classification="inconclusive",
                    candidate_outcome=candidate_cell.outcome,
                    baseline_outcome=baseline_cell.outcome,
                    reason=(
                        f"candidate={candidate_cell.status}/{candidate_cell.outcome} "
                        f"baseline={baseline_cell.status}/{baseline_cell.outcome}"
                    ),
                )
            )
            continue
        assert candidate_cell.outcome is not None and baseline_cell.outcome is not None
        classification = classify(candidate_cell.outcome, baseline_cell.outcome)
        candidate_score_diff = (
            None
            if candidate_cell.score_subject is None or candidate_cell.score_opponent is None
            else candidate_cell.score_subject - candidate_cell.score_opponent
        )
        baseline_score_diff = (
            None
            if baseline_cell.score_subject is None or baseline_cell.score_opponent is None
            else baseline_cell.score_subject - baseline_cell.score_opponent
        )
        entries.append(
            ComparisonEntry(
                opponent_id=opponent_id,
                seed=seed,
                classification=classification,
                candidate_outcome=candidate_cell.outcome,
                baseline_outcome=baseline_cell.outcome,
                candidate_score=candidate_cell.score_subject,
                baseline_score=baseline_cell.score_subject,
                candidate_score_differential=candidate_score_diff,
                baseline_score_differential=baseline_score_diff,
                candidate_territory=candidate_cell.territory_subject,
                baseline_territory=baseline_cell.territory_subject,
            )
        )
    return tuple(entries)


def rerun_command(subject_id: str, opponent_id: str, seed: int, ticks: int) -> str:
    """The exact ``agents test`` invocation that reproduces one cell (Sec 8/10)."""

    return f"bytefray agents test {subject_id} --opponent {opponent_id} --seed {seed} --ticks {ticks}"


# ---------------------------------------------------------------------------
# Seed/opponent parsing shared by the CLI and Designer (Sec 12/13)
# ---------------------------------------------------------------------------


def parse_opponents(text: str) -> tuple[str, ...]:
    opponents = tuple(chunk.strip() for chunk in text.split(",") if chunk.strip())
    if not opponents:
        raise EvaluationConfigurationError("--opponents requires at least one agent id.")
    return opponents


def parse_seed_list(text: str) -> tuple[int, ...]:
    seeds: list[int] = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            seeds.append(int(chunk))
        except ValueError as exc:
            raise EvaluationConfigurationError(f"Invalid seed value {chunk!r}.") from exc
    if not seeds:
        raise EvaluationConfigurationError("--seeds requires at least one seed.")
    return tuple(seeds)


def parse_seed_range(text: str) -> tuple[int, ...]:
    start_text, sep, end_text = text.partition(":")
    if not sep:
        raise EvaluationConfigurationError(
            f"--seed-range must be START:END, got {text!r}."
        )
    try:
        start, end = int(start_text.strip()), int(end_text.strip())
    except ValueError as exc:
        raise EvaluationConfigurationError(
            f"--seed-range values must be integers, got {text!r}."
        ) from exc
    if end < start:
        raise EvaluationConfigurationError(
            f"--seed-range end must be >= start, got {text!r}."
        )
    return tuple(range(start, end + 1))


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _cell_from_match_result(cell: EvaluationCell, match_result: NativeMatchResult) -> EvaluationCell:
    winner = match_result.winner
    outcome = (
        "tie"
        if winner == WINNER_TIE_SENTINEL
        else "win"
        if winner == TESTED_AGENT_SLOT
        else "loss"
    )
    agents_by_id = match_result.agents_by_id
    subject_agent = agents_by_id.get(TESTED_AGENT_SLOT)
    opponent_agent = agents_by_id.get(OPPONENT_SLOT)
    return replace(
        cell,
        status="completed",
        outcome=outcome,
        match_id=match_result.match_id,
        result_id=match_result.result_id,
        ticks_run=match_result.ticks_run,
        score_subject=float(match_result.score.get(TESTED_AGENT_SLOT, 0)),
        score_opponent=float(match_result.score.get(OPPONENT_SLOT, 0)),
        territory_subject=(subject_agent.territory_pct_last if subject_agent else None),
        territory_opponent=(opponent_agent.territory_pct_last if opponent_agent else None),
        error_code=None,
        error_message=None,
    )


def _cell_from_envelope(cell: EvaluationCell, envelope: ResultEnvelope) -> EvaluationCell:
    winner = envelope.winner
    outcome = (
        "tie"
        if winner == WINNER_TIE_SENTINEL
        else "win"
        if winner == TESTED_AGENT_SLOT
        else "loss"
    )
    subject_entrant = next(
        (entry for entry in envelope.entrants if entry.get("agent_id") == TESTED_AGENT_SLOT), {}
    )
    opponent_entrant = next(
        (entry for entry in envelope.entrants if entry.get("agent_id") == OPPONENT_SLOT), {}
    )
    subject_stats = subject_entrant.get("statistics", {}) or {}
    opponent_stats = opponent_entrant.get("statistics", {}) or {}
    return replace(
        cell,
        status="completed",
        outcome=outcome,
        match_id=envelope.match_id,
        result_id=envelope.result_id,
        ticks_run=envelope.ticks,
        score_subject=float(envelope.score.get(TESTED_AGENT_SLOT, 0)),
        score_opponent=float(envelope.score.get(OPPONENT_SLOT, 0)),
        territory_subject=subject_stats.get("territory_pct_last"),
        territory_opponent=opponent_stats.get("territory_pct_last"),
        error_code=None,
        error_message=None,
    )


def _cell_from_state(cell: EvaluationCell, previous: Mapping[str, Any]) -> EvaluationCell:
    return replace(
        cell,
        status=previous.get("status", cell.status),
        outcome=previous.get("outcome"),
        match_id=previous.get("match_id"),
        result_id=previous.get("result_id"),
        ticks_run=previous.get("ticks_run"),
        score_subject=previous.get("score_subject"),
        score_opponent=previous.get("score_opponent"),
        territory_subject=previous.get("territory_subject"),
        territory_opponent=previous.get("territory_opponent"),
        error_code=previous.get("error_code"),
        error_message=previous.get("error_message"),
    )


def _resumed_cell_mismatch(
    envelope: ResultEnvelope, cell: EvaluationCell, expected_match_id: str
) -> str | None:
    """Sec 14: adapted from ``tournament_service._resumed_result_mismatch``."""

    entrant_order = tuple(str(entry.get("agent_id")) for entry in envelope.entrants)
    expected_order = (TESTED_AGENT_SLOT, OPPONENT_SLOT)
    if entrant_order != expected_order:
        return f"entrant order {entrant_order} does not match expected {expected_order}"
    actual_seed = envelope.reproducibility.get("seed")
    if actual_seed != cell.seed:
        return f"seed {actual_seed!r} does not match the scheduled cell's {cell.seed!r}"
    if envelope.match_id != expected_match_id:
        return (
            f"match ID {envelope.match_id!r} does not match the scheduled cell's "
            f"expected ID {expected_match_id!r}"
        )
    if envelope.replay is None:
        return "result has no replay reference, but a native Python match result always has one"
    replay_path = cell.artifact_dir / envelope.replay.filename
    try:
        verify_replay_digest(envelope, replay_path)
        header = next(
            (record for record in iter_replay(replay_path) if isinstance(record, ReplayHeader)),
            None,
        )
    except ReplayIntegrityError as exc:
        return f"replay verification failed ({exc.code}): {exc}"
    except (OSError, ValueError) as exc:
        return f"replay header could not be read: {exc}"
    if header is None:
        return "replay has no header"
    if header.match_id != envelope.match_id:
        return "replay header match ID does not match result envelope"
    if header.result_id != envelope.result_id:
        return "replay header result ID does not match result envelope"
    return None


class EvaluationService:
    """Headless orchestrator: schedules and executes an evaluation matrix.

    Sibling to ``TournamentService``, not a wrapper around it -- both sit
    over ``NativeMatchService`` (here, via ``agent_test.test_agent``) but
    schedule fundamentally different experiment shapes (see
    docs/specs/agent_evaluation.md Sec 3/Sec 4).
    """

    def preflight(
        self,
        *,
        candidate_id: str,
        opponent_ids: tuple[str, ...],
        seeds: tuple[int, ...],
        baseline_id: str | None = None,
        ticks: int = DEFAULT_TICKS,
    ) -> tuple[dict[str, AgentSpec], str]:
        """Validate a request's agent/seed/tick shape and resolve its evaluation id.

        Independent of ``output_dir`` (unlike :class:`EvaluationRequest`
        itself), so a caller -- the CLI in particular -- can compute a
        default ``--output`` directory from the resolved ``evaluation_id``
        before constructing the full request. Called both by the CLI and
        by :meth:`run` itself, so there is exactly one implementation of
        "resolve and validate the matrix inputs," not one for callers that
        already know their output directory and a second for ones that
        don't.
        """

        request = EvaluationRequest(
            candidate_id=candidate_id,
            opponent_ids=opponent_ids,
            seeds=seeds,
            output_dir=Path("."),
            baseline_id=baseline_id,
            ticks=ticks,
        )
        specs = self._validate(request)
        evaluation_id = self._evaluation_id(request, specs)
        return specs, evaluation_id

    def run(self, request: EvaluationRequest) -> EvaluationResult:
        specs = self._validate(request)
        evaluation_id = self._evaluation_id(request, specs)
        state_path = request.output_dir / "evaluation.json"
        prior = self._load_state(state_path, evaluation_id) if request.resume else {}
        prior_cells = {item["schedule_id"]: item for item in prior.get("cells", ())}
        matrix = build_matrix(request, evaluation_id)

        completed: list[EvaluationCell] = []
        for cell in matrix:
            previous = prior_cells.get(cell.schedule_id)
            resolved: EvaluationCell | None = None
            if previous is not None:
                resolved = self._resolve_from_state(cell, previous, specs, request)
                if (
                    resolved is not None
                    and resolved.status in ("failed", "corrupted")
                    and request.retry_failures
                ):
                    resolved = None
            if resolved is None:
                resolved = self._execute_cell(cell, request)
            completed.append(resolved)
            self._write_state(state_path, evaluation_id, request, completed, matrix)

        aggregates = self._all_aggregates(request, completed)
        comparison = (
            compare_candidate_baseline(completed) if request.baseline_id is not None else ()
        )
        self._write_state(
            state_path,
            evaluation_id,
            request,
            completed,
            matrix,
            aggregates=aggregates,
            comparison=comparison,
        )
        return EvaluationResult(
            evaluation_id=evaluation_id,
            request=request,
            cells=tuple(completed),
            aggregates=aggregates,
            comparison=comparison,
            state_path=state_path,
        )

    # -- validation -----------------------------------------------------

    def _validate(self, request: EvaluationRequest) -> dict[str, AgentSpec]:
        if not request.opponent_ids:
            raise EvaluationConfigurationError("Evaluation requires at least one opponent.")
        if not request.seeds:
            raise EvaluationConfigurationError("Evaluation requires at least one seed.")
        if request.ticks < 1:
            raise EvaluationConfigurationError("Evaluation requires a positive tick limit.")
        if request.baseline_id is not None and request.baseline_id == request.candidate_id:
            raise EvaluationConfigurationError(
                "Candidate and baseline must be different agents."
            )
        subject_ids = [request.candidate_id]
        if request.baseline_id is not None:
            subject_ids.append(request.baseline_id)
        all_ids = sorted(set(subject_ids) | set(request.opponent_ids))
        root = get_data_root()
        return {agent_id: _resolve_python_agent(root, agent_id) for agent_id in all_ids}

    def _evaluation_id(self, request: EvaluationRequest, specs: dict[str, AgentSpec]) -> str:
        project = get_project_info()
        payload = {
            "candidate": agent_identity(specs[request.candidate_id]),
            "baseline": (
                agent_identity(specs[request.baseline_id])
                if request.baseline_id is not None
                else None
            ),
            "opponents": [agent_identity(specs[opponent_id]) for opponent_id in request.opponent_ids],
            "seeds": list(request.seeds),
            "ticks": request.ticks,
            "agent_api_version": project.agent_api_version,
        }
        return stable_id("evaluation", payload)

    # -- resume -----------------------------------------------------------

    def _resolve_from_state(
        self,
        cell: EvaluationCell,
        previous: Mapping[str, Any],
        specs: dict[str, AgentSpec],
        request: EvaluationRequest,
    ) -> EvaluationCell | None:
        status = previous.get("status")
        if status not in ("completed", "failed", "corrupted"):
            return None
        if status != "completed":
            return _cell_from_state(cell, previous)

        outcome = previous.get("outcome")
        if outcome in ("subject_init_failed", "opponent_init_failed"):
            return _cell_from_state(cell, previous)

        result_path = cell.artifact_dir / "result.json"
        if not result_path.is_file():
            return replace(
                _cell_from_state(cell, previous),
                status="corrupted",
                error_code="resumed_result_missing",
                error_message="Recorded completed cell has no result.json to verify.",
            )
        try:
            envelope = read_result(result_path)
        except (OSError, ValueError, KeyError) as exc:
            return replace(
                _cell_from_state(cell, previous),
                status="corrupted",
                error_code="resumed_result_unreadable",
                error_message=f"result.json could not be read: {exc}"[:240],
            )

        expected_match_id = _expected_cell_match_id(
            specs[cell.subject_id],
            cell.subject_id,
            specs[cell.opponent_id],
            cell.opponent_id,
            cell.seed,
            request.ticks,
        )
        mismatch = _resumed_cell_mismatch(envelope, cell, expected_match_id)
        if mismatch is not None:
            return replace(
                _cell_from_state(cell, previous),
                status="corrupted",
                error_code="resumed_result_mismatch",
                error_message=mismatch[:240],
            )
        return _cell_from_envelope(cell, envelope)

    # -- execution --------------------------------------------------------

    def _execute_cell(self, cell: EvaluationCell, request: EvaluationRequest) -> EvaluationCell:
        try:
            outcome = test_agent(
                cell.subject_id,
                opponent=cell.opponent_id,
                seed=cell.seed,
                ticks=request.ticks,
                timeout=None,
                trace=False,
                run_dir=cell.artifact_dir,
            )
        except AgentTestError as exc:
            return replace(
                cell,
                status="failed",
                outcome=None,
                error_code=exc.diagnostic.code,
                error_message=" ".join(str(exc).split())[:240],
            )
        if isinstance(outcome, InitializationFailureOutcome):
            failed_slot = outcome.diagnostic.agent_id
            result_outcome = (
                "subject_init_failed" if failed_slot == TESTED_AGENT_SLOT else "opponent_init_failed"
            )
            return replace(
                cell,
                status="completed",
                outcome=result_outcome,
                error_code=outcome.diagnostic.code,
                error_message=" ".join(outcome.diagnostic.message.split())[:240],
            )
        return _cell_from_match_result(cell, outcome.match_result)

    # -- aggregation --------------------------------------------------------

    def _all_aggregates(
        self, request: EvaluationRequest, cells: Sequence[EvaluationCell]
    ) -> tuple[SubjectAggregate, ...]:
        aggregates = [aggregate_cells(CANDIDATE, request.candidate_id, cells)]
        if request.baseline_id is not None:
            aggregates.append(aggregate_cells(BASELINE, request.baseline_id, cells))
        return tuple(aggregates)

    # -- persistence --------------------------------------------------------

    def _load_state(self, path: Path, evaluation_id: str) -> dict[str, Any]:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA_NAME:
            raise EvaluationConfigurationError(
                f"Existing evaluation state at {path} uses an unrecognized schema."
            )
        if data.get("schema_version") != SCHEMA_VERSION:
            raise EvaluationConfigurationError(
                f"Existing evaluation state at {path} uses unsupported schema version "
                f"{data.get('schema_version')!r} (expected {SCHEMA_VERSION})."
            )
        if data.get("evaluation_id") != evaluation_id:
            raise EvaluationConfigurationError(
                "Existing evaluation state does not match this request."
            )
        return data

    def _write_state(
        self,
        path: Path,
        evaluation_id: str,
        request: EvaluationRequest,
        cells: Sequence[EvaluationCell],
        matrix: Sequence[EvaluationCell],
        *,
        aggregates: Sequence[SubjectAggregate] = (),
        comparison: Sequence[ComparisonEntry] = (),
    ) -> None:
        project = get_project_info()
        write_json_atomic(
            path,
            {
                "schema": SCHEMA_NAME,
                "schema_version": SCHEMA_VERSION,
                "evaluation_id": evaluation_id,
                "candidate_id": request.candidate_id,
                "baseline_id": request.baseline_id,
                "opponent_ids": list(request.opponent_ids),
                "seeds": list(request.seeds),
                "ticks": request.ticks,
                "matrix_size": len(matrix),
                "project": asdict(project),
                "cells": [_cell_to_dict(cell, path.parent) for cell in cells],
                "aggregates": [asdict(row) for row in aggregates],
                "comparison": [asdict(row) for row in comparison],
                "complete": len(cells) >= len(matrix),
            },
        )


def _cell_to_dict(cell: EvaluationCell, base: Path) -> dict[str, Any]:
    data = asdict(cell)
    try:
        data["artifact_dir"] = str(cell.artifact_dir.relative_to(base))
    except ValueError:
        data["artifact_dir"] = str(cell.artifact_dir)
    return data


def read_evaluation(path: Path) -> dict[str, Any]:
    """Read a persisted ``evaluation.json`` verbatim (dict form).

    A thin, schema-checked read used by the CLI's ``--dry-run``-adjacent
    presentation code and by the Designer (Sec 13); the richer typed
    ``EvaluationResult`` is only produced by ``EvaluationService.run``
    itself, since that is the only place with the resolved
    ``EvaluationCell``/``SubjectAggregate`` objects to reconstruct.
    """

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA_NAME:
        raise EvaluationConfigurationError(f"{path}: not a {SCHEMA_NAME} artifact.")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise EvaluationConfigurationError(
            f"{path}: unsupported schema version {data.get('schema_version')!r} "
            f"(expected {SCHEMA_VERSION})."
        )
    return data


def _default_output_dir(root: Path, evaluation_id: str) -> Path:
    return root / "runs" / "evaluations" / evaluation_id


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray agents evaluate",
        description=(
            "Run a deterministic Python-agent evaluation matrix: a candidate "
            "(and optional baseline) against explicit opponents and seeds, "
            "through the exact 'bytefray agents test' execution boundary. "
            "See docs/specs/agent_evaluation.md."
        ),
    )
    parser.add_argument("candidate_id", help="candidate agent's discovery id")
    parser.add_argument(
        "--baseline", default=None, help="baseline agent's discovery id to compare against"
    )
    parser.add_argument(
        "--opponents", required=True, help="comma-separated opponent discovery ids"
    )
    seed_group = parser.add_mutually_exclusive_group()
    seed_group.add_argument("--seeds", default=None, help="comma-separated explicit seeds")
    seed_group.add_argument(
        "--seed-range", default=None, help="inclusive seed range START:END"
    )
    parser.add_argument(
        "--ticks", type=_positive_int, default=DEFAULT_TICKS, help=f"tick budget per cell (default: {DEFAULT_TICKS})"
    )
    parser.add_argument("--output", type=Path, default=None, help="evaluation artifact directory")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the matrix and exit without running anything"
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def _resolve_seeds(args: argparse.Namespace) -> tuple[int, ...]:
    if args.seeds is not None:
        return parse_seed_list(args.seeds)
    if args.seed_range is not None:
        return parse_seed_range(args.seed_range)
    return (Config().seed,)


def _print_matrix(request: EvaluationRequest, matrix: Sequence[EvaluationCell]) -> None:
    subjects = [request.candidate_id] + ([request.baseline_id] if request.baseline_id else [])
    print(f"candidate: {request.candidate_id}")
    print(f"baseline: {request.baseline_id if request.baseline_id else 'none'}")
    print(f"opponents: {', '.join(request.opponent_ids)}")
    print(f"seeds: {', '.join(str(seed) for seed in request.seeds)}")
    print(f"ticks: {request.ticks}")
    print(f"subjects: {len(subjects)}  opponents: {len(request.opponent_ids)}  seeds: {len(request.seeds)}")
    print(f"matches: {len(matrix)}")


def _print_aggregate(aggregate: SubjectAggregate) -> None:
    print(f"[{aggregate.subject_role}] {aggregate.subject_id}")
    print(f"  win rate: {aggregate.win_rate_display}")
    print(
        f"  wins={aggregate.wins} losses={aggregate.losses} ties={aggregate.ties} "
        f"played={aggregate.matches_played}"
    )
    print(
        f"  score_avg={aggregate.score_avg:g} score_differential_avg={aggregate.score_differential_avg:g} "
        f"ticks_avg={aggregate.ticks_avg:g}"
    )
    print(
        f"  territory_avg={aggregate.territory_avg:.2f}% "
        f"territory_differential_avg={aggregate.territory_differential_avg:.2f}%"
    )
    if aggregate.subject_init_failures or aggregate.opponent_init_failures or aggregate.failed:
        print(
            f"  subject_init_failed={aggregate.subject_init_failures} "
            f"opponent_init_failed={aggregate.opponent_init_failures} failed={aggregate.failed}"
        )


def _print_comparison_entry(entry: ComparisonEntry, ticks: int) -> None:
    print(f"  opponent={entry.opponent_id} seed={entry.seed}")
    print(f"    candidate: {entry.candidate_outcome}  baseline: {entry.baseline_outcome}")
    if entry.reason:
        print(f"    reason: {entry.reason}")
    if entry.candidate_score is not None and entry.baseline_score is not None:
        print(f"    score: candidate={entry.candidate_score:g} baseline={entry.baseline_score:g}")
    print(f"    rerun candidate: {rerun_command('<candidate>', entry.opponent_id, entry.seed, ticks)}")
    if entry.baseline_outcome is not None:
        print(f"    rerun baseline:  {rerun_command('<baseline>', entry.opponent_id, entry.seed, ticks)}")


def _print_result(result: EvaluationResult, request: EvaluationRequest) -> None:
    print(f"evaluation: {result.evaluation_id}")
    for aggregate in result.aggregates:
        _print_aggregate(aggregate)
    if request.baseline_id is not None:
        regressed = [entry for entry in result.comparison if entry.classification == "regressed"]
        improved = [entry for entry in result.comparison if entry.classification == "improved"]
        unchanged = [entry for entry in result.comparison if entry.classification == "unchanged"]
        inconclusive = [entry for entry in result.comparison if entry.classification == "inconclusive"]
        print(
            f"comparison: {len(improved)} improved, {len(regressed)} regressed, "
            f"{len(unchanged)} unchanged, {len(inconclusive)} inconclusive "
            f"(of {len(result.comparison)} matched cells)"
        )
        if regressed:
            print("regressions:")
            for entry in regressed:
                _print_comparison_entry(entry, request.ticks)
        if inconclusive:
            print("inconclusive:")
            for entry in inconclusive:
                _print_comparison_entry(entry, request.ticks)
    failed = result.failed_cells
    corrupted = result.corrupted_cells
    if failed:
        print("failed cells:")
        for cell in failed:
            print(
                f"  {cell.subject_role}={cell.subject_id} opponent={cell.opponent_id} "
                f"seed={cell.seed} code={cell.error_code} error={cell.error_message}"
            )
    if corrupted:
        print("corrupted cells (rerun with --retry-failed to reconcile):")
        for cell in corrupted:
            print(
                f"  {cell.subject_role}={cell.subject_id} opponent={cell.opponent_id} "
                f"seed={cell.seed} code={cell.error_code} error={cell.error_message}"
            )
    print(f"evaluation artifact: {result.state_path}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        opponent_ids = parse_opponents(args.opponents)
        seeds = _resolve_seeds(args)
    except EvaluationConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    service = EvaluationService()
    try:
        _specs, evaluation_id = service.preflight(
            candidate_id=args.candidate_id,
            opponent_ids=opponent_ids,
            seeds=seeds,
            baseline_id=args.baseline,
            ticks=args.ticks,
        )
    except EvaluationConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    root = get_data_root()
    output_dir = (
        args.output.expanduser().resolve()
        if args.output is not None
        else _default_output_dir(root, evaluation_id).resolve()
    )
    request = EvaluationRequest(
        candidate_id=args.candidate_id,
        opponent_ids=opponent_ids,
        seeds=seeds,
        output_dir=output_dir,
        baseline_id=args.baseline,
        ticks=args.ticks,
        retry_failures=args.retry_failed,
    )
    matrix = build_matrix(request, evaluation_id)
    if not args.quiet or args.dry_run:
        _print_matrix(request, matrix)
    if args.dry_run:
        return 0

    try:
        result = service.run(request)
    except EvaluationConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        _print_result(result, request)
    return 1 if (result.failed_cells or result.corrupted_cells) else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASELINE",
    "CANDIDATE",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "ComparisonEntry",
    "EvaluationCell",
    "EvaluationConfigurationError",
    "EvaluationRequest",
    "EvaluationResult",
    "EvaluationService",
    "SubjectAggregate",
    "agent_identity",
    "aggregate_cells",
    "build_matrix",
    "classify",
    "compare_candidate_baseline",
    "main",
    "parse_opponents",
    "parse_seed_list",
    "parse_seed_range",
    "read_evaluation",
    "rerun_command",
    "source_digest",
]
