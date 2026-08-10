"""Read-only ``bytefray.evaluation`` v1 -> common history model (Sec 10).

Never mutates the v1 artifact and never treats current agent discovery as
historical evidence. Verified directly against v0.6.1 canonical artifacts:
``result.json``'s ``entrants`` list (``agent_id``/``name``/``alive``/
``score``/``termination_reason``/``diagnostic``/``statistics``/``metadata``)
and its ``reproducibility`` block (``seed``/``arena_size``/``tick_limit``/
``action_budget``/``win_mode``/``weights``/``entrant_order``) never actually
persist ``api_version``/``agent_version``/``source_sha256`` anywhere --
those fields are hashed transiently into ``match_id`` by
``match_service._match_identity_payload`` and then discarded, not written
out. This means genuine executable-identity recovery for v1 evaluations is
**not possible** from canonical artifacts alone; this adapter reports
candidate/baseline/opponent identity as ``UNKNOWN`` rather than fabricating
it, and effective conditions are recovered only as far as ``reproducibility``
actually allows (seed/arena/ticks/budget/win_mode/weights -- no rules
compatibility identifier, which v1 never had).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from battle_engine.agent_evaluation import aggregate_cells, compare_candidate_baseline
from battle_engine.result_model import read_result

from .models import (
    AdaptedCell,
    ArtifactLocation,
    ArtifactPathEscapeError,
    ArtifactReadError,
    ConfidenceValue,
    EvaluationSummary,
    HealthCode,
    HealthReport,
    SchemaSupport,
    evaluation_cells_from_raw,
    file_modified_at,
    resolve_contained_path,
)

V1_SCHEMA_NAME = "bytefray.evaluation"
SUPPORTED_V1_VERSIONS = (1,)


def _recover_effective_conditions(raw_cells: list[dict[str, Any]], base_dir: Path) -> ConfidenceValue:
    for raw in raw_cells:
        if raw.get("status") != "completed" or raw.get("outcome") not in ("win", "loss", "tie"):
            continue
        try:
            artifact_dir = resolve_contained_path(base_dir, str(raw.get("artifact_dir", ".")))
        except ArtifactPathEscapeError:
            # M4: never attribute a path outside the evaluation directory to
            # this evaluation, even for best-effort v1 recovery.
            continue
        result_path = artifact_dir / "result.json"
        if not result_path.is_file():
            continue
        try:
            envelope = read_result(result_path)
        except (OSError, ValueError, KeyError):
            continue
        repro = dict(envelope.reproducibility)
        if not repro:
            continue
        return ConfidenceValue.recovered(
            {
                "tick_limit": repro.get("tick_limit"),
                "arena_size": repro.get("arena_size"),
                "action_budget": repro.get("action_budget"),
                "win_mode": repro.get("win_mode"),
                "weights": repro.get("weights"),
            }
        )
    return ConfidenceValue.unknown()


def _condition_occurrence_indices(raw_cells: list[dict[str, Any]]) -> list[int]:
    """Deterministic, always-recoverable from file order alone (Sec 8/10)."""

    counts: dict[tuple[Any, Any, Any], int] = {}
    indices = []
    for raw in raw_cells:
        key = (raw.get("subject_role"), raw.get("opponent_id"), raw.get("seed"))
        indices.append(counts.get(key, 0))
        counts[key] = counts.get(key, 0) + 1
    return indices


def adapt_v1(path: Path) -> EvaluationSummary:
    path = Path(path).resolve()
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactReadError(f"{path}: could not be read: {exc}", code=HealthCode.MALFORMED_JSON) from exc
    try:
        data: dict[str, Any] = json.loads(raw_text)
    except ValueError as exc:
        raise ArtifactReadError(f"{path}: malformed JSON: {exc}", code=HealthCode.MALFORMED_JSON) from exc

    if data.get("schema") != V1_SCHEMA_NAME:
        raise ArtifactReadError(
            f"{path}: schema {data.get('schema')!r} is not {V1_SCHEMA_NAME!r}",
            code=HealthCode.WRONG_SCHEMA,
        )
    version = data.get("schema_version")
    if version not in SUPPORTED_V1_VERSIONS:
        raise ArtifactReadError(
            f"{path}: unsupported schema_version {version!r}", code=HealthCode.UNSUPPORTED_VERSION
        )
    required = ("evaluation_id", "candidate_id", "opponent_ids", "seeds", "ticks", "cells")
    missing = [key for key in required if key not in data]
    if missing:
        raise ArtifactReadError(
            f"{path}: missing required field(s): {', '.join(missing)}",
            code=HealthCode.INVALID_REQUIRED_FIELDS,
        )

    location = ArtifactLocation(
        evaluation_json_path=path, directory=path.parent, file_modified_at=file_modified_at(path)
    )
    schema = SchemaSupport(schema=V1_SCHEMA_NAME, schema_version=version, supported=True)

    opponent_ids = list(data.get("opponent_ids", ()))
    seeds = list(data.get("seeds", ()))
    opponent_ids_unique = len(opponent_ids) == len(set(opponent_ids))
    seeds_unique = len(seeds) == len(set(seeds))

    raw_cells = data.get("cells", [])
    occurrence_indices = _condition_occurrence_indices(raw_cells)
    schedule_ids = [raw.get("schedule_id") for raw in raw_cells]
    duplicate_schedule_ids = len(schedule_ids) != len(set(schedule_ids))

    cells = []
    for raw, occurrence_index in zip(raw_cells, occurrence_indices):
        opponent_index = ConfidenceValue.unknown()
        if opponent_ids_unique:
            try:
                opponent_index = ConfidenceValue.recovered(opponent_ids.index(raw.get("opponent_id")))
            except ValueError:
                pass
        seed_index = ConfidenceValue.unknown()
        if seeds_unique:
            try:
                seed_index = ConfidenceValue.recovered(seeds.index(raw.get("seed")))
            except ValueError:
                pass
        cells.append(
            AdaptedCell(
                schedule_id=raw.get("schedule_id", ""),
                subject_role=raw.get("subject_role", ""),
                subject_id=raw.get("subject_id", ""),
                opponent_id=raw.get("opponent_id", ""),
                seed=raw.get("seed", 0),
                status=raw.get("status", "pending"),
                outcome=raw.get("outcome"),
                match_id=raw.get("match_id"),
                artifact_dir=str(raw.get("artifact_dir", "")),
                score_subject=raw.get("score_subject"),
                score_opponent=raw.get("score_opponent"),
                territory_subject=raw.get("territory_subject"),
                territory_opponent=raw.get("territory_opponent"),
                opponent_index=opponent_index,
                seed_index=seed_index,
                condition_occurrence_index=(
                    ConfidenceValue.unknown()
                    if duplicate_schedule_ids
                    else ConfidenceValue.recovered(occurrence_index)
                ),
                condition_fingerprint=ConfidenceValue.unknown(),
                opponent_identity=ConfidenceValue.unknown(),
            )
        )

    codes: list[HealthCode] = []
    detail: list[str] = []
    if duplicate_schedule_ids:
        codes.append(HealthCode.UNKNOWN_LEGACY_CONDITION)
        detail.append("duplicate schedule_id values; duplicate alignment evidence is ambiguous")
    if any(Path(str(raw.get("artifact_dir", ""))).is_absolute() for raw in raw_cells):
        codes.append(HealthCode.NON_PORTABLE_ABSOLUTE_PATH)
        detail.append("one or more cell artifact_dir entries are absolute paths")

    complete = bool(data.get("complete"))
    if complete:
        failed = sum(1 for c in cells if c.status == "failed")
        corrupted = sum(1 for c in cells if c.status == "corrupted")
        init_failed = sum(1 for c in cells if c.outcome in ("subject_init_failed", "opponent_init_failed"))
        if failed:
            codes.append(HealthCode.FINISHED_WITH_FAILED_CELLS)
            detail.append(f"{failed} failed cell(s)")
        if corrupted:
            codes.append(HealthCode.FINISHED_WITH_CORRUPTED_CELLS)
            detail.append(f"{corrupted} corrupted cell(s)")
        if init_failed:
            codes.append(HealthCode.FINISHED_WITH_INIT_FAILURES)
            detail.append(f"{init_failed} initialization-failure cell(s)")
        if not any(
            c in (HealthCode.FINISHED_WITH_FAILED_CELLS, HealthCode.FINISHED_WITH_CORRUPTED_CELLS, HealthCode.FINISHED_WITH_INIT_FAILURES)
            for c in codes
        ):
            codes.append(HealthCode.HEALTHY)
    else:
        codes.append(HealthCode.UNFINISHED)

    real_cells = evaluation_cells_from_raw(raw_cells, path.parent)
    candidate_id = data["candidate_id"]
    baseline_id = data.get("baseline_id")
    aggregates = [aggregate_cells("candidate", candidate_id, real_cells)]
    if baseline_id is not None:
        aggregates.append(aggregate_cells("baseline", baseline_id, real_cells))
    comparison = compare_candidate_baseline(real_cells) if baseline_id is not None else ()

    return EvaluationSummary(
        location=location,
        schema=schema,
        evaluation_id=data["evaluation_id"],
        candidate_id=candidate_id,
        baseline_id=baseline_id,
        opponent_ids=tuple(opponent_ids),
        seeds=tuple(seeds),
        ticks=data.get("ticks", 0),
        matrix_size=data.get("matrix_size", len(cells)),
        lifecycle_state=ConfidenceValue.recovered("finished" if complete else "unfinished"),
        created_at=ConfidenceValue.unknown(),
        finished_at=ConfidenceValue.unknown(),
        rules_compatibility_id=ConfidenceValue.unknown(),
        candidate_identity=ConfidenceValue.unknown(),
        baseline_identity=ConfidenceValue.unknown(),
        effective_conditions=_recover_effective_conditions(raw_cells, path.parent),
        cells=tuple(cells),
        health=HealthReport(codes=tuple(codes), detail=tuple(detail), verified=False),
        aggregates_recomputed=tuple(aggregates),
        comparison_recomputed=tuple(comparison),
    )


__all__ = ["adapt_v1"]
