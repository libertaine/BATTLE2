"""Read-only ``bytefray.evaluation`` v2 -> common history model (Sec 10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from battle_engine.agent_evaluation import (
    SCHEMA_NAME,
    all_subject_aggregates,
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
    execution_context_is_valid,
    file_modified_at,
)

# v3 (docs/specs/agent_revision.md Sec 5.3) added one additive top-level
# "agent_revisions" sibling field to "planned_identities" and otherwise
# changed nothing about the v2 wire shape this adapter reads -- accepting
# it here is a narrow compatibility fix (nothing below reads or exposes
# "agent_revisions" yet; that is deferred, along with any other revision-
# aware evaluation_history/CLI work, to a later phase), not a scope
# expansion: without this, every fresh v3 evaluation would be reported
# HealthCode.UNSUPPORTED_VERSION by `list`/`show`/`compare`, a regression
# in the already-shipped v0.7 evaluation_history feature that a "Phase 3
# has no history changes" reading of the plan did not anticipate.
#
# v4 (v0.9 Phase 6, Phase 5 spec Sec J.1/AA.4.8) added per-cell
# "orientation"/"orientation_index" and evaluation-wide "orientation_mode"/
# "arena_alignment_mode" -- also additive over v3's wire shape, so it joins
# this same adapter rather than a new module, following the identical
# precedent this comment already documents for v2->v3. Field extraction
# below is version-conditional: schema_version 4 reads the new fields as
# RECORDED; schema_version 2/3 (which never had this concept) recover them
# as certain historical facts (Sec L.2/AA.4.6), never UNKNOWN.
SUPPORTED_V2_VERSIONS = (2, 3, 4)
_ORIENTATION_AWARE_VERSIONS = (4,)

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


def _agent_revision_field(raw_entry: Any, key: str, *, allow_none: bool = False) -> ConfidenceValue:
    """One field of one role's ``agent_revisions`` entry (docs/specs/agent_revision.md
    Sec 5.1), treated as untrusted persisted input: anything other than a
    present, correctly-typed value is honestly ``UNKNOWN`` -- never a
    guessed or substituted value, and never an exception that would
    destroy the rest of an otherwise-readable artifact (a malformed
    ``agent_revisions`` entry for one role/opponent must not affect any
    other role/opponent's fields).
    """

    if not isinstance(raw_entry, dict):
        return ConfidenceValue.unknown()
    return _recorded_or_unknown(raw_entry, key, expected_type=str, allow_none=allow_none)


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
    return adapt_v2_data(data, path)


def adapt_v2_data(data: dict[str, Any], path: Path) -> EvaluationSummary:
    """Same as :func:`adapt_v2`, but for an already-parsed JSON object.

    ``path`` must already be resolved (as ``adapt_v2`` itself resolves it)
    -- used by ``discovery.adapt_any``, which has already read and parsed
    the file once to peek its schema/version, so the whole artifact is
    never read and JSON-parsed from disk a second time just to dispatch to
    the right adapter.
    """

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

    # docs/specs/agent_revision.md Sec 5.1/5.3: "agent_revisions" is a
    # wholly separate, additive top-level sibling of "planned_identities"
    # (schema v3) -- absent entirely on v1/v2 artifacts and on any v3
    # artifact whose evaluation had nothing to record. Read the same
    # defensive way as "planned_identities" above: never assumed to be the
    # right shape, never allowed to raise out of this function.
    agent_revisions_raw = data.get("agent_revisions")
    agent_revisions: dict[str, Any] = agent_revisions_raw if isinstance(agent_revisions_raw, dict) else {}
    candidate_revision_entry = agent_revisions.get("candidate")
    candidate_agent_revision_id = _agent_revision_field(candidate_revision_entry, "agent_revision_id")
    candidate_agent_revision_error = _agent_revision_field(
        candidate_revision_entry, "agent_revision_error", allow_none=True
    )
    baseline_revision_entry = agent_revisions.get("baseline")
    baseline_agent_revision_id = _agent_revision_field(baseline_revision_entry, "agent_revision_id")
    baseline_agent_revision_error = _agent_revision_field(
        baseline_revision_entry, "agent_revision_error", allow_none=True
    )
    opponent_revisions_raw = agent_revisions.get("opponents")
    opponent_revisions: list[Any] = opponent_revisions_raw if isinstance(opponent_revisions_raw, list) else []

    opponent_ids_list_raw = data.get("opponent_ids", [])
    opponent_ids_list: list[Any] = opponent_ids_list_raw if isinstance(opponent_ids_list_raw, list) else []
    cells = []
    schedule_ids: list[str] = []
    execution_context_refs: list[tuple[str, str]] = []  # (schedule_id, context_id)
    for raw in raw_cells:
        opponent_identity = ConfidenceValue.unknown()
        opponent_agent_revision_id = ConfidenceValue.unknown()
        opponent_agent_revision_error = ConfidenceValue.unknown()
        try:
            # Same ordered-list, first-occurrence-position correlation
            # "opponent_identity" already uses -- safe for duplicate/self-
            # play opponent occurrences because every position for the same
            # opponent_id was populated from the identical, once-per-agent-
            # id dict (agent_evaluation._resolve_revision_results resolves
            # one _RevisionPlanEntry per distinct agent_id, exactly as
            # agent_identity() does for planned_identities).
            idx = opponent_ids_list.index(raw.get("opponent_id"))
            if idx < len(opponent_identities):
                opponent_identity = ConfidenceValue.recorded(opponent_identities[idx])
            if idx < len(opponent_revisions):
                opponent_revision_entry = opponent_revisions[idx]
                opponent_agent_revision_id = _agent_revision_field(
                    opponent_revision_entry, "agent_revision_id"
                )
                opponent_agent_revision_error = _agent_revision_field(
                    opponent_revision_entry, "agent_revision_error", allow_none=True
                )
        except ValueError:
            pass
        schedule_ids.append(raw["schedule_id"])
        context_id = raw.get("execution_context_id")
        if isinstance(context_id, str) and context_id:
            execution_context_refs.append((raw["schedule_id"], context_id))
        # v0.9 Phase 6 (Sec L.2): schema < 4 never recorded orientation --
        # recovered as the certain historical fact, never UNKNOWN.
        orientation = (
            _recorded_or_unknown(raw, "orientation", expected_type=str)
            if version in _ORIENTATION_AWARE_VERSIONS
            else ConfidenceValue.recovered("candidate_first")
        )
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
                result_id=raw.get("result_id"),
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
                opponent_agent_revision_id=opponent_agent_revision_id,
                opponent_agent_revision_error=opponent_agent_revision_error,
                orientation=orientation,
            )
        )

    # H2 (v0.7 closure pass): every semantic/structural check below appends
    # to this one running `codes`/`detail` pair -- `HEALTHY` is appended
    # only once, at the very end, and only if nothing else was ever
    # appended (see the bottom of this function). Previously `HEALTHY` was
    # appended as soon as the lifecycle-state branch alone looked clean,
    # *before* the structural checks further down ran, so an artifact could
    # end up flagged both `HEALTHY` and (say) `FINISHED_MATRIX_SHORT` at
    # once -- a `HealthReport` must never claim both.
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

    # Second closure pass ("execution-context validation must fail
    # safely"): normalize and validate the `execution_contexts` container
    # itself before any iteration touches it. `execution_contexts: null`
    # (valid JSON, wrong container type) previously reached a bare
    # `for item in data.get("execution_contexts", ())` -- since the key is
    # *present* with value `None`, `.get(..., ())` returns `None` itself
    # (the default only applies when the key is absent), so iterating it
    # raised an uncaught `TypeError` that aborted discovery of every
    # sibling in the same scan. `execution_contexts` absent entirely is
    # legitimate (a v2 artifact with no recorded runtime provenance yet);
    # present with any other, non-list value is malformed and diagnosed,
    # never crashed on or silently coerced.
    execution_contexts_raw = data.get("execution_contexts")
    if "execution_contexts" not in data:
        execution_contexts_list: list[Any] = []
    elif isinstance(execution_contexts_raw, list):
        execution_contexts_list = execution_contexts_raw
    else:
        execution_contexts_list = []
        codes.append(HealthCode.INVALID_EXECUTION_CONTEXTS_CONTAINER)
        detail.append(
            "execution_contexts must be a list, got "
            f"{'null' if execution_contexts_raw is None else type(execution_contexts_raw).__name__}"
        )

    known_context_ids = {
        item.get("context_id") for item in execution_contexts_list if isinstance(item, dict)
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

    # H2/second closure pass: an execution_contexts entry is usable -- for
    # both HEALTHY classification here and direct-comparison eligibility in
    # comparison.py -- only if it passes the full structural+semantic
    # validity check (right type, every runtime-compatibility field
    # present with the expected type, and context_id itself consistent
    # with those fields). A context missing every field but context_id
    # (e.g. a hand-edited `{"context_id": "..."}`) fails this and is
    # diagnosed, never silently treated as complete just because a
    # shallower check only looked at context_id's presence.
    valid_execution_contexts = [
        item for item in execution_contexts_list if execution_context_is_valid(item)
    ]
    invalid_context_entries = len(execution_contexts_list) - len(valid_execution_contexts)
    if invalid_context_entries:
        codes.append(HealthCode.INVALID_EXECUTION_CONTEXT_ENTRY)
        detail.append(f"{invalid_context_entries} execution_contexts entrie(s) are malformed")

    if any(Path(str(raw.get("artifact_dir", ""))).is_absolute() for raw in raw_cells):
        codes.append(HealthCode.NON_PORTABLE_ABSOLUTE_PATH)
        detail.append("one or more cell artifact_dir entries are absolute paths")

    # H2: a cell's (subject_role, subject_id, opponent_id, seed,
    # condition_occurrence_index, orientation) coordinate is supposed to be
    # unique -- `condition_occurrence_index` exists specifically to
    # disambiguate otherwise-identical duplicates. More than one cell
    # sharing the exact same coordinate means that uniqueness invariant is
    # already broken; comparison.py's strict alignment independently
    # refuses to pair such cells positionally (H4), but this is flagged
    # here too as a structural diagnostic on the artifact itself.
    #
    # v0.9 Phase 6 (Sec 9/W.1-2): `orientation` joins the coordinate for
    # schema >= 4 artifacts -- a `candidate_first` and an `opponent_first`
    # cell for the identical (opponent, seed) share the same
    # `condition_occurrence_index` by design (Sec I.3: orientation, not
    # occurrence, is what distinguishes them) and must never be reported as
    # a duplicate-coordinate structural problem. Pre-Phase-6 artifacts have
    # no `orientation` field at all, so every cell's absent-field value
    # (`None`) is identical and contributes nothing to disambiguation --
    # exactly the historical (single-orientation) behavior this check
    # already had, unchanged.
    coordinate_counts: dict[tuple[Any, ...], list[str]] = {}
    for raw in raw_cells:
        occurrence = raw.get("condition_occurrence_index")
        if not isinstance(occurrence, int) or isinstance(occurrence, bool):
            continue
        coordinate = (
            raw["subject_role"],
            raw["subject_id"],
            raw["opponent_id"],
            raw.get("seed"),
            occurrence,
            raw.get("orientation"),
        )
        coordinate_counts.setdefault(coordinate, []).append(raw["schedule_id"])
    duplicate_coordinates = {
        coordinate: ids for coordinate, ids in coordinate_counts.items() if len(ids) > 1
    }
    if duplicate_coordinates:
        codes.append(HealthCode.DUPLICATE_CONDITION_COORDINATE)
        sample_ids = sorted({sid for ids in duplicate_coordinates.values() for sid in ids})
        detail.append(
            f"{len(duplicate_coordinates)} coordinate(s) shared by more than one cell: "
            f"{', '.join(sample_ids[:5])}" + ("..." if len(sample_ids) > 5 else "")
        )

    # Self-consistency: the persisted planned_identities payload must
    # rehash to the artifact's own evaluation_id (B1's invariant) --
    # detectable here too, for an artifact written by a version of this
    # module that predates the B1 fix, or corrupted after the fact. M1:
    # uses the artifact's own recorded `identity_version`, never the
    # current module-level `IDENTITY_VERSION` -- a valid older v2 artifact
    # (identity_version 2, predating H3's local_source_fingerprint) must
    # not be recomputed with today's identity_version and be falsely
    # flagged inconsistent.
    rules_id = data.get("rules_compatibility_id")
    effective_conditions = data.get("effective_conditions")
    seeds = data.get("seeds")
    ticks = data.get("ticks")
    identity_version = data.get("identity_version")
    if not isinstance(rules_id, str):
        codes.append(HealthCode.MISSING_RULES_COMPATIBILITY_ID)
        detail.append("rules_compatibility_id is missing or not a string")
    if not isinstance(effective_conditions, dict):
        codes.append(HealthCode.MISSING_EFFECTIVE_CONDITIONS)
        detail.append("effective_conditions is missing or not an object")
    if (
        planned.get("candidate")
        and isinstance(rules_id, str)
        and isinstance(effective_conditions, dict)
        and isinstance(seeds, list)
        and isinstance(ticks, int)
        and isinstance(identity_version, int)
        and not isinstance(identity_version, bool)
    ):
        recomputed_payload = {
            "identity_version": identity_version,
            "candidate": planned.get("candidate"),
            "baseline": planned.get("baseline"),
            "opponents": opponent_identities,
            "seeds": seeds,
            "ticks": ticks,
            "effective_conditions": effective_conditions,
            "rules_compatibility_id": rules_id,
        }
        # v0.9 Phase 6 (Sec J.1/AA.4.8): identity_version 4's payload gains
        # two sibling keys -- gated on the artifact's own recorded
        # identity_version (M1's existing precedent), never the current
        # module constant, so a valid pre-Phase-6 artifact (identity_version
        # 2/3, which never had these keys) is not falsely flagged
        # inconsistent for a shape it was never supposed to have.
        if identity_version >= 4:
            recomputed_payload["orientation_mode"] = data.get("orientation_mode")
            recomputed_payload["arena_alignment_mode"] = data.get("arena_alignment_mode")
        recomputed_id = stable_id("evaluation-v2", recomputed_payload)
        if recomputed_id != data.get("evaluation_id"):
            codes.append(HealthCode.PLANNED_IDENTITY_INCONSISTENT)
            detail.append(
                "planned_identities/effective_conditions/rules_compatibility_id do not "
                "rehash to the recorded evaluation_id"
            )

    # H2: a cell's recorded condition_fingerprint must itself rehash from
    # the same inputs build_matrix() used to compute it, using the
    # artifact's own recorded effective_conditions_fingerprint (already
    # persisted verbatim by _write_state) rather than re-deriving one --
    # this validates internal cross-consistency of the artifact, not a
    # second independent recomputation of effective_conditions itself.
    conditions_fp = data.get("effective_conditions_fingerprint")
    if isinstance(conditions_fp, str) and isinstance(rules_id, str):
        inconsistent_fingerprints: list[str] = []
        for raw in raw_cells:
            recorded_fp = raw.get("condition_fingerprint")
            if not isinstance(recorded_fp, str):
                continue
            occurrence = raw.get("condition_occurrence_index")
            if not isinstance(occurrence, int) or isinstance(occurrence, bool):
                continue
            try:
                idx = opponent_ids_list.index(raw.get("opponent_id"))
            except ValueError:
                continue
            if idx >= len(opponent_identities):
                continue
            fp_payload = {
                "opponent": opponent_identities[idx],
                "seed": raw.get("seed"),
                "effective_conditions": conditions_fp,
                "rules_compatibility_id": rules_id,
                "condition_occurrence_index": occurrence,
            }
            # v0.9 Phase 6 (Sec I.3/AA.4.3): identity_version 4's per-cell
            # condition_fingerprint payload gains two sibling keys -- same
            # identity_version gate as the evaluation_id recomputation
            # above, for the identical "don't flag a valid older artifact"
            # reason.
            if isinstance(identity_version, int) and identity_version >= 4:
                fp_payload["orientation"] = raw.get("orientation")
                fp_payload["arena_alignment_mode"] = data.get("arena_alignment_mode")
            expected_fp = stable_id("evaluation-condition", fp_payload)
            if expected_fp != recorded_fp:
                inconsistent_fingerprints.append(raw["schedule_id"])
        if inconsistent_fingerprints:
            codes.append(HealthCode.CONDITION_FINGERPRINT_INCONSISTENT)
            detail.append(
                f"{len(inconsistent_fingerprints)} cell(s) have a condition_fingerprint "
                f"inconsistent with their own recorded inputs: {', '.join(inconsistent_fingerprints[:5])}"
                + ("..." if len(inconsistent_fingerprints) > 5 else "")
            )

    # H2: opponent_ids/seeds element types -- a list of the right container
    # type but with malformed elements (a non-string opponent id, a bool or
    # non-int seed) is still a soft/diagnosable issue, not a reason to
    # abort the whole artifact.
    malformed_elements: list[str] = []
    for index, value in enumerate(opponent_ids_list):
        if not isinstance(value, str) or not value:
            malformed_elements.append(f"opponent_ids[{index}]")
    seeds_list_raw = data.get("seeds")
    if isinstance(seeds_list_raw, list):
        for index, value in enumerate(seeds_list_raw):
            if not isinstance(value, int) or isinstance(value, bool):
                malformed_elements.append(f"seeds[{index}]")
    if malformed_elements:
        codes.append(HealthCode.MALFORMED_MATRIX_ELEMENT)
        detail.append(
            f"malformed opponent_ids/seeds element(s): {', '.join(malformed_elements[:5])}"
            + ("..." if len(malformed_elements) > 5 else "")
        )

    # H2: `HEALTHY` is added only now, after every semantic/structural
    # check above has run -- never both `HEALTHY` and a structural-
    # inconsistency code at once.
    if not codes:
        codes.append(HealthCode.HEALTHY)

    real_cells = evaluation_cells_from_raw(raw_cells, path.parent)
    candidate_id = data["candidate_id"]
    baseline_id = data.get("baseline_id")
    # v0.9 Phase 6 (Sec K.2): pooled + per-orientation views, computed
    # identically to the live-run path. A legacy (schema < 4) cell
    # reconstructed by `evaluation_cells_from_raw` defaults to
    # `orientation="candidate_first"` (`EvaluationCell.orientation`'s own
    # default), which is also the historically correct fact.
    aggregates = all_subject_aggregates(candidate_id, baseline_id, real_cells)
    comparison = compare_candidate_baseline(real_cells) if baseline_id is not None else ()

    # v0.9 Phase 6 (Sec L.2/AA.4.6): schema < 4 never recorded these --
    # recovered as certain historical facts, never UNKNOWN.
    if version in _ORIENTATION_AWARE_VERSIONS:
        orientation_mode = _recorded_or_unknown(data, "orientation_mode", expected_type=str)
        arena_alignment_mode = _recorded_or_unknown(data, "arena_alignment_mode", expected_type=str)
    else:
        orientation_mode = ConfidenceValue.recovered("candidate_first_only")
        arena_alignment_mode = ConfidenceValue.recovered("fixed")

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
        # Only fully valid contexts are exposed here -- a malformed entry
        # (wrong container-level type already excluded above; missing
        # fields, wrong field types, or a context_id inconsistent with its
        # own semantic contents) must never be available for
        # `comparison.py` to find by id and treat as a legitimate
        # compatibility record (second closure pass).
        execution_contexts=tuple(valid_execution_contexts),
        candidate_agent_revision_id=candidate_agent_revision_id,
        candidate_agent_revision_error=candidate_agent_revision_error,
        baseline_agent_revision_id=baseline_agent_revision_id,
        baseline_agent_revision_error=baseline_agent_revision_error,
        orientation_mode=orientation_mode,
        arena_alignment_mode=arena_alignment_mode,
    )


__all__ = ["adapt_v2", "adapt_v2_data"]
