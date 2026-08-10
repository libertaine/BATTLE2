"""Read-only ``bytefray.evaluation`` v2 -> common history model (Sec 10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from battle_engine.agent_evaluation import (
    IDENTITY_VERSION,
    SCHEMA_NAME,
    aggregate_cells,
    compare_candidate_baseline,
)
from battle_engine.result_model import stable_id

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

# A cell that lacks any of these, or has the wrong type, cannot even be
# safely represented as an `EvaluationCell`/`AdaptedCell` -- H1: this must
# become a typed `ArtifactReadError` (the whole artifact reported
# unreadable, sibling discovery unaffected), never an uncaught exception
# escaping from deep inside dataclass construction.
_REQUIRED_CELL_STRING_FIELDS = ("schedule_id", "subject_role", "subject_id", "opponent_id")
_VALID_SUBJECT_ROLES = ("candidate", "baseline")
_VALID_LIFECYCLE_STATES = ("running", "finished", "aborted")


def _recorded_or_unknown(
    data: dict[str, Any],
    key: str,
    *,
    expected_type: type | tuple[type, ...] | None = None,
    allow_none: bool = False,
) -> ConfidenceValue:
    """A key genuinely absent from the artifact must never read as a
    confidently ``RECORDED(None)`` value (H1) -- only a key that is
    *present*, with a value of the expected type (or legitimately ``None``
    when ``allow_none``), is ``RECORDED``. Anything else is honestly
    ``UNKNOWN``.
    """

    if key not in data:
        return ConfidenceValue.unknown()
    value = data[key]
    if value is None:
        return ConfidenceValue.recorded(None) if allow_none else ConfidenceValue.unknown()
    if expected_type is not None and not isinstance(value, expected_type):
        return ConfidenceValue.unknown()
    return ConfidenceValue.recorded(value)


def _validate_v2_cells(raw_cells: Any, path: Path) -> list[dict[str, Any]]:
    """Structural validation only -- raises for anything that cannot even be
    safely turned into an ``EvaluationCell``. Semantic/soft issues (missing
    coordinates, dangling context references, etc.) are handled separately
    as non-fatal health diagnostics so one malformed *field* never aborts
    the whole artifact the way a missing *structural* field must.
    """

    if not isinstance(raw_cells, list):
        raise ArtifactReadError(
            f"{path}: 'cells' must be a list, got {type(raw_cells).__name__}",
            code=HealthCode.INVALID_REQUIRED_FIELDS,
        )
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_cells):
        if not isinstance(raw, dict):
            raise ArtifactReadError(
                f"{path}: cells[{index}] is not an object", code=HealthCode.INVALID_REQUIRED_FIELDS
            )
        missing = [
            field
            for field in _REQUIRED_CELL_STRING_FIELDS
            if not isinstance(raw.get(field), str) or not raw.get(field)
        ]
        if not isinstance(raw.get("seed"), int) or isinstance(raw.get("seed"), bool):
            missing.append("seed")
        if not isinstance(raw.get("status"), str) or not raw.get("status"):
            missing.append("status")
        if missing:
            raise ArtifactReadError(
                f"{path}: cells[{index}] missing/invalid required field(s): {', '.join(missing)}",
                code=HealthCode.INVALID_REQUIRED_FIELDS,
            )
        if raw.get("subject_role") not in _VALID_SUBJECT_ROLES:
            raise ArtifactReadError(
                f"{path}: cells[{index}] has invalid subject_role {raw.get('subject_role')!r} "
                f"(expected one of {_VALID_SUBJECT_ROLES})",
                code=HealthCode.INVALID_REQUIRED_FIELDS,
            )
        validated.append(raw)
    return validated


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
    type_errors = []
    if not isinstance(data.get("evaluation_id"), str) or not data["evaluation_id"]:
        type_errors.append("evaluation_id must be a non-empty string")
    if not isinstance(data.get("candidate_id"), str) or not data["candidate_id"]:
        type_errors.append("candidate_id must be a non-empty string")
    if not isinstance(data.get("opponent_ids"), list):
        type_errors.append("opponent_ids must be a list")
    if not isinstance(data.get("seeds"), list):
        type_errors.append("seeds must be a list")
    if not isinstance(data.get("ticks"), int) or isinstance(data.get("ticks"), bool):
        type_errors.append("ticks must be an int")
    if type_errors:
        raise ArtifactReadError(
            f"{path}: {'; '.join(type_errors)}", code=HealthCode.INVALID_REQUIRED_FIELDS
        )

    raw_cells = _validate_v2_cells(data.get("cells"), path)

    location = ArtifactLocation(
        evaluation_json_path=path, directory=path.parent, file_modified_at=file_modified_at(path)
    )
    schema = SchemaSupport(schema=SCHEMA_NAME, schema_version=version, supported=True)

    planned_raw = data.get("planned_identities")
    planned: dict[str, Any] = planned_raw if isinstance(planned_raw, dict) else {}
    candidate_identity = (
        ConfidenceValue.recorded(planned["candidate"]) if planned.get("candidate") else ConfidenceValue.unknown()
    )
    baseline_identity = (
        ConfidenceValue.recorded(planned.get("baseline"))
        if "baseline" in planned
        else ConfidenceValue.unknown()
    )
    opponent_identities_raw = planned.get("opponents")
    opponent_identities: list[Any] = (
        opponent_identities_raw if isinstance(opponent_identities_raw, list) else []
    )

    opponent_ids_list_raw = data.get("opponent_ids", [])
    opponent_ids_list: list[Any] = opponent_ids_list_raw if isinstance(opponent_ids_list_raw, list) else []
    cells = []
    schedule_ids: list[str] = []
    execution_context_refs: list[tuple[str, str]] = []  # (schedule_id, context_id)
    for raw in raw_cells:
        opponent_identity = ConfidenceValue.unknown()
        try:
            idx = opponent_ids_list.index(raw.get("opponent_id"))
            if idx < len(opponent_identities):
                opponent_identity = ConfidenceValue.recorded(opponent_identities[idx])
        except ValueError:
            pass
        schedule_ids.append(raw["schedule_id"])
        context_id = raw.get("execution_context_id")
        if isinstance(context_id, str) and context_id:
            execution_context_refs.append((raw["schedule_id"], context_id))
        cells.append(
            AdaptedCell(
                schedule_id=raw["schedule_id"],
                subject_role=raw["subject_role"],
                subject_id=raw["subject_id"],
                opponent_id=raw["opponent_id"],
                seed=raw["seed"],
                status=raw["status"],
                outcome=raw.get("outcome"),
                match_id=raw.get("match_id"),
                artifact_dir=str(raw.get("artifact_dir", "")),
                score_subject=raw.get("score_subject"),
                score_opponent=raw.get("score_opponent"),
                territory_subject=raw.get("territory_subject"),
                territory_opponent=raw.get("territory_opponent"),
                opponent_index=_recorded_or_unknown(raw, "opponent_index", expected_type=int),
                seed_index=_recorded_or_unknown(raw, "seed_index", expected_type=int),
                condition_occurrence_index=_recorded_or_unknown(
                    raw, "condition_occurrence_index", expected_type=int
                ),
                condition_fingerprint=_recorded_or_unknown(
                    raw, "condition_fingerprint", expected_type=str
                ),
                opponent_identity=opponent_identity,
                execution_context_id=_recorded_or_unknown(
                    raw, "execution_context_id", expected_type=str, allow_none=True
                ),
            )
        )

    lifecycle_state_raw = data.get("lifecycle_state")
    codes: list[HealthCode] = []
    detail: list[str] = []
    if lifecycle_state_raw == "aborted" and data.get("abort_reason") == "source_drift":
        codes.append(HealthCode.SOURCE_DRIFT_ABORTED)
        detail.append(str(data.get("abort_detail")))
    elif lifecycle_state_raw != "finished":
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

    if lifecycle_state_raw not in _VALID_LIFECYCLE_STATES:
        detail.append(f"lifecycle_state {lifecycle_state_raw!r} is not one of {_VALID_LIFECYCLE_STATES}")

    matrix_size = data.get("matrix_size")
    if (
        lifecycle_state_raw == "finished"
        and isinstance(matrix_size, int)
        and len(cells) < matrix_size
    ):
        codes.append(HealthCode.FINISHED_MATRIX_SHORT)
        detail.append(
            f"lifecycle_state is 'finished' but only {len(cells)}/{matrix_size} cells are recorded"
        )

    if len(schedule_ids) != len(set(schedule_ids)):
        codes.append(HealthCode.DUPLICATE_SCHEDULE_ID)
        detail.append("duplicate schedule_id values across cells")

    known_context_ids = {
        item.get("context_id")
        for item in data.get("execution_contexts", ())
        if isinstance(item, dict)
    }
    dangling = sorted(
        {schedule_id for schedule_id, context_id in execution_context_refs if context_id not in known_context_ids}
    )
    if dangling:
        codes.append(HealthCode.DANGLING_EXECUTION_CONTEXT)
        detail.append(
            f"{len(dangling)} cell(s) reference an execution_context_id absent from "
            f"execution_contexts: {', '.join(dangling[:5])}"
            + ("..." if len(dangling) > 5 else "")
        )

    if any(Path(str(raw.get("artifact_dir", ""))).is_absolute() for raw in raw_cells):
        codes.append(HealthCode.NON_PORTABLE_ABSOLUTE_PATH)
        detail.append("one or more cell artifact_dir entries are absolute paths")

    # Self-consistency: the persisted planned_identities payload must
    # rehash to the artifact's own evaluation_id (B1's invariant) --
    # detectable here too, for an artifact written by a version of this
    # module that predates the B1 fix, or corrupted after the fact.
    rules_id = data.get("rules_compatibility_id")
    effective_conditions = data.get("effective_conditions")
    seeds = data.get("seeds")
    ticks = data.get("ticks")
    if (
        planned.get("candidate")
        and isinstance(rules_id, str)
        and isinstance(effective_conditions, dict)
        and isinstance(seeds, list)
        and isinstance(ticks, int)
    ):
        recomputed_payload = {
            "identity_version": IDENTITY_VERSION,
            "candidate": planned.get("candidate"),
            "baseline": planned.get("baseline"),
            "opponents": opponent_identities,
            "seeds": seeds,
            "ticks": ticks,
            "effective_conditions": effective_conditions,
            "rules_compatibility_id": rules_id,
        }
        recomputed_id = stable_id("evaluation-v2", recomputed_payload)
        if recomputed_id != data.get("evaluation_id"):
            codes.append(HealthCode.PLANNED_IDENTITY_INCONSISTENT)
            detail.append(
                "planned_identities/effective_conditions/rules_compatibility_id do not "
                "rehash to the recorded evaluation_id"
            )

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
        opponent_ids=tuple(opponent_ids_list),
        seeds=tuple(data.get("seeds", ())),
        ticks=data.get("ticks", 0),
        matrix_size=data.get("matrix_size", len(cells)),
        lifecycle_state=_recorded_or_unknown(data, "lifecycle_state", expected_type=str),
        created_at=_recorded_or_unknown(data, "created_at", expected_type=str),
        finished_at=_recorded_or_unknown(data, "finished_at", expected_type=str, allow_none=True),
        rules_compatibility_id=_recorded_or_unknown(data, "rules_compatibility_id", expected_type=str),
        candidate_identity=candidate_identity,
        baseline_identity=baseline_identity,
        effective_conditions=_recorded_or_unknown(data, "effective_conditions", expected_type=dict),
        cells=tuple(cells),
        health=HealthReport(codes=tuple(codes), detail=tuple(detail), verified=False),
        aggregates_recomputed=tuple(aggregates),
        comparison_recomputed=tuple(comparison),
        execution_contexts=tuple(
            item for item in data.get("execution_contexts", ()) if isinstance(item, dict)
        ),
    )


__all__ = ["adapt_v2"]
