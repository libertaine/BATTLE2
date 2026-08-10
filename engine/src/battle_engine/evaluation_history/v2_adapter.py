"""Read-only ``bytefray.evaluation`` v2 -> common history model (Sec 10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from battle_engine.agent_evaluation import (
    SCHEMA_NAME,
    aggregate_cells,
    compare_candidate_baseline,
)

from .models import (
    AdaptedCell,
    ArtifactLocation,
    ArtifactReadError,
    ConfidenceValue,
    EvaluationSummary,
    HealthCode,
    HealthReport,
    SchemaSupport,
    evaluation_cells_from_raw,
    file_modified_at,
)

SUPPORTED_V2_VERSIONS = (2,)


def adapt_v2(path: Path) -> EvaluationSummary:
    path = Path(path).resolve()
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactReadError(f"{path}: could not be read: {exc}", code=HealthCode.MALFORMED_JSON) from exc
    try:
        data: dict[str, Any] = json.loads(raw_text)
    except ValueError as exc:
        raise ArtifactReadError(f"{path}: malformed JSON: {exc}", code=HealthCode.MALFORMED_JSON) from exc

    if data.get("schema") != SCHEMA_NAME:
        raise ArtifactReadError(
            f"{path}: schema {data.get('schema')!r} is not {SCHEMA_NAME!r}",
            code=HealthCode.WRONG_SCHEMA,
        )
    version = data.get("schema_version")
    if version not in SUPPORTED_V2_VERSIONS:
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
    schema = SchemaSupport(schema=SCHEMA_NAME, schema_version=version, supported=True)

    planned = data.get("planned_identities") or {}
    candidate_identity = (
        ConfidenceValue.recorded(planned["candidate"]) if planned.get("candidate") else ConfidenceValue.unknown()
    )
    baseline_identity = (
        ConfidenceValue.recorded(planned.get("baseline"))
        if "baseline" in planned
        else ConfidenceValue.unknown()
    )
    opponent_identities = planned.get("opponents") or []

    raw_cells = data.get("cells", [])
    cells = []
    for raw in raw_cells:
        opponent_identity = ConfidenceValue.unknown()
        try:
            idx = data.get("opponent_ids", []).index(raw.get("opponent_id"))
            if idx < len(opponent_identities):
                opponent_identity = ConfidenceValue.recorded(opponent_identities[idx])
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
                opponent_index=ConfidenceValue.recorded(raw.get("opponent_index")),
                seed_index=ConfidenceValue.recorded(raw.get("seed_index")),
                condition_occurrence_index=ConfidenceValue.recorded(
                    raw.get("condition_occurrence_index")
                ),
                condition_fingerprint=ConfidenceValue.recorded(raw.get("condition_fingerprint")),
                opponent_identity=opponent_identity,
            )
        )

    lifecycle_state = data.get("lifecycle_state")
    codes: list[HealthCode] = []
    detail: list[str] = []
    if lifecycle_state == "aborted" and data.get("abort_reason") == "source_drift":
        codes.append(HealthCode.SOURCE_DRIFT_ABORTED)
        detail.append(str(data.get("abort_detail")))
    elif lifecycle_state != "finished":
        codes.append(HealthCode.UNFINISHED)
    else:
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
        if not codes:
            codes.append(HealthCode.HEALTHY)

    if any(Path(str(raw.get("artifact_dir", ""))).is_absolute() for raw in raw_cells):
        codes.append(HealthCode.NON_PORTABLE_ABSOLUTE_PATH)
        detail.append("one or more cell artifact_dir entries are absolute paths")

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
        opponent_ids=tuple(data.get("opponent_ids", ())),
        seeds=tuple(data.get("seeds", ())),
        ticks=data.get("ticks", 0),
        matrix_size=data.get("matrix_size", len(cells)),
        lifecycle_state=ConfidenceValue.recorded(lifecycle_state),
        created_at=ConfidenceValue.recorded(data.get("created_at")),
        finished_at=ConfidenceValue.recorded(data.get("finished_at")),
        rules_compatibility_id=ConfidenceValue.recorded(data.get("rules_compatibility_id")),
        candidate_identity=candidate_identity,
        baseline_identity=baseline_identity,
        effective_conditions=ConfidenceValue.recorded(data.get("effective_conditions")),
        cells=tuple(cells),
        health=HealthReport(codes=tuple(codes), detail=tuple(detail), verified=False),
        aggregates_recomputed=tuple(aggregates),
        comparison_recomputed=tuple(comparison),
    )


__all__ = ["adapt_v2"]
