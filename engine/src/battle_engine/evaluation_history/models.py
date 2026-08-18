"""Common, Qt-free domain model for evaluation history (docs/specs/evaluation_history.md Sec 11/12).

Shared by the v1 and v2 adapters, discovery, and comparison layers. Deliberately
distinguishes recorded/recovered/unknown/conflicting/verified evidence rather
than silently defaulting an absent legacy field to a current-schema value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Any

from battle_engine.agent_evaluation import ComparisonEntry, EvaluationCell, SubjectAggregate
from battle_engine.evaluation_analysis import EvaluationAnalysis
from battle_engine.result_model import stable_id


class FieldConfidence(str, Enum):
    RECORDED = "recorded"
    RECOVERED = "recovered"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"
    VERIFIED = "verified"


class RevisionVerificationStatus(str, Enum):
    """Local agent-revision-store evidence for one role's recorded revision
    (docs/specs/agent_revision.md Sec 7.2). Deliberately four distinct
    states, never conflated (v0.8 audit requirement): a revision id that
    was never recorded is a different fact from one that was recorded but
    whose snapshot isn't on this machine, which is itself a different fact
    from a snapshot that is present but fails to reconstruct/verify.
    """

    NOT_CHECKED = "not_checked"  # no recorded revision id, or --verify not requested
    NOT_AVAILABLE = "not_available"  # revision id recorded; no local snapshot directory found
    INVALID = "invalid"  # local snapshot directory found but fails to verify (corrupt/tampered/malformed)
    VERIFIED = "verified"  # local snapshot found and its fingerprint matches its own directory name


@dataclass(frozen=True)
class ConfidenceValue:
    value: Any
    confidence: FieldConfidence

    @staticmethod
    def recorded(value: Any) -> ConfidenceValue:
        return ConfidenceValue(value, FieldConfidence.RECORDED)

    @staticmethod
    def unknown() -> ConfidenceValue:
        return ConfidenceValue(None, FieldConfidence.UNKNOWN)

    @staticmethod
    def recovered(value: Any) -> ConfidenceValue:
        return ConfidenceValue(value, FieldConfidence.RECOVERED)

    @staticmethod
    def conflicting(candidates: Any) -> ConfidenceValue:
        """M6: usable historical evidence disagreed on this dimension's
        value (e.g. two cells nominally for the same candidate recovered
        different ``source_sha256`` values) -- ``candidates`` carries every
        distinct value seen, not a single guessed winner.
        """

        return ConfidenceValue(candidates, FieldConfidence.CONFLICTING)

    def to_json(self) -> dict[str, Any]:
        return {"value": self.value, "confidence": self.confidence.value}


class HealthCode(str, Enum):
    HEALTHY = "healthy"
    FINISHED_WITH_INIT_FAILURES = "finished_with_init_failures"
    FINISHED_WITH_FAILED_CELLS = "finished_with_failed_cells"
    FINISHED_WITH_CORRUPTED_CELLS = "finished_with_corrupted_cells"
    UNFINISHED = "unfinished"
    SOURCE_DRIFT_ABORTED = "source_drift_aborted"
    MALFORMED_JSON = "malformed_json"
    WRONG_SCHEMA = "wrong_schema"
    UNSUPPORTED_VERSION = "unsupported_version"
    INVALID_REQUIRED_FIELDS = "invalid_required_fields"
    MISSING_NESTED_RESULT = "missing_nested_result"
    MISSING_REPLAY = "missing_replay"
    REPLAY_DIGEST_MISMATCH = "replay_digest_mismatch"
    RESULT_MATRIX_MISMATCH = "result_matrix_mismatch"
    UNKNOWN_LEGACY_CONDITION = "unknown_legacy_condition"
    NON_PORTABLE_ABSOLUTE_PATH = "non_portable_absolute_path"
    DUPLICATE_IDENTITY_LOCATION = "duplicate_identity_location"
    ARTIFACT_PATH_ESCAPE = "artifact_path_escape"
    DUPLICATE_SCHEDULE_ID = "duplicate_schedule_id"
    DANGLING_EXECUTION_CONTEXT = "dangling_execution_context"
    FINISHED_MATRIX_SHORT = "finished_matrix_short"
    PLANNED_IDENTITY_INCONSISTENT = "planned_identity_inconsistent"
    # H2 (v0.7 closure pass): additional non-fatal structural diagnostics --
    # each one is appended to a `HealthReport` alongside whatever else was
    # found, never raised (a single malformed *field*, as opposed to a
    # missing *structural* field required just to construct a cell, must
    # never abort the whole artifact or its siblings).
    INVALID_JSON_ROOT = "invalid_json_root"
    DUPLICATE_CONDITION_COORDINATE = "duplicate_condition_coordinate"
    CONDITION_FINGERPRINT_INCONSISTENT = "condition_fingerprint_inconsistent"
    MISSING_EFFECTIVE_CONDITIONS = "missing_effective_conditions"
    MISSING_RULES_COMPATIBILITY_ID = "missing_rules_compatibility_id"
    MALFORMED_MATRIX_ELEMENT = "malformed_matrix_element"
    INVALID_EXECUTION_CONTEXT_ENTRY = "invalid_execution_context_entry"
    # Second closure pass: `execution_contexts` itself can be present but
    # the wrong container type entirely (e.g. JSON `null`, a string, an
    # object) -- distinct from one malformed *entry* inside an otherwise
    # well-typed list.
    INVALID_EXECUTION_CONTEXTS_CONTAINER = "invalid_execution_contexts_container"


@dataclass(frozen=True)
class HealthReport:
    codes: tuple[HealthCode, ...] = ()
    detail: tuple[str, ...] = ()
    verified: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "codes": [code.value for code in self.codes],
            "detail": list(self.detail),
            "verified": self.verified,
        }


class ArtifactReadError(Exception):
    """A hard discovery/read failure -- caught by discovery, never let escape it."""

    def __init__(self, message: str, *, code: HealthCode):
        super().__init__(message)
        self.code = code


class ArtifactPathEscapeError(ArtifactReadError):
    """A cell-recorded relative path resolves outside its evaluation directory (M4)."""

    def __init__(self, message: str):
        super().__init__(message, code=HealthCode.ARTIFACT_PATH_ESCAPE)


def resolve_contained_path(base_dir: Path, relative: str | Path) -> Path:
    """Resolve ``relative`` (a stored ``artifact_dir``/nested path) beneath ``base_dir``.

    Refuses ``../`` traversal, absolute paths (Windows drive-qualified or
    POSIX-rooted), and symlink escapes -- anything whose fully resolved
    location does not fall under ``base_dir``'s own fully resolved location
    raises :class:`ArtifactPathEscapeError` rather than being silently
    attributed to this evaluation (M4). ``Path.resolve()`` also normalizes
    case/drive on Windows, so containment is checked post-resolution, not
    via string prefix comparison.
    """

    raw = str(relative)
    if Path(raw).is_absolute() or PureWindowsPath(raw).drive:
        raise ArtifactPathEscapeError(
            f"{relative!r} escapes the evaluation directory {Path(base_dir).resolve()}"
        )

    base_resolved = Path(base_dir).resolve()
    candidate = Path(base_dir) / Path(raw)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise ArtifactPathEscapeError(
            f"{relative!r} resolves to {resolved}, which escapes the evaluation "
            f"directory {base_resolved}"
        ) from None
    return resolved


# Second closure pass ("execution-context validation must fail safely"):
# the fields that define whether a v2 artifact's recorded execution
# context is a runtime-compatibility-bearing fact rather than an inert
# label, and each field's expected JSON type. Centralized here (rather
# than duplicated in ``v2_adapter.py`` and ``comparison.py`` separately) so
# discovery-time health reporting and compare-time compatibility checking
# can never silently disagree about what counts as a valid execution
# context. Deliberately excludes ``context_id`` (derived *from* these
# fields, see :func:`execution_context_is_valid`) and ``first_used_at`` (an
# irrelevant bookkeeping timestamp, not a runtime property) -- this is a
# narrow runtime-compatibility rule, not general environment provenance.
EXECUTION_CONTEXT_REQUIRED_FIELD_TYPES: dict[str, type] = {
    "bytefray_version": str,
    "agent_api_version": int,
    "python_version": str,
    "result_schema_version": int,
    "replay_schema_version": int,
    "rules_compatibility_id": str,
}


def _typed_field_present(context: Mapping[str, Any], field: str, expected_type: type) -> bool:
    if field not in context:
        return False
    value = context[field]
    if expected_type is int and isinstance(value, bool):
        return False
    return isinstance(value, expected_type)


def execution_context_is_valid(context: Any) -> bool:
    """Structurally and semantically validate one ``execution_contexts`` entry.

    A context is usable -- for discovery-time ``HEALTHY`` classification
    *and* for compare-time direct-comparison eligibility -- only if:

    * it is a mapping/object (never a bare string, number, list, etc.);
    * its ``context_id`` is a non-empty string;
    * every field in :data:`EXECUTION_CONTEXT_REQUIRED_FIELD_TYPES` is
      present with the expected type (a required field simply absent, or
      present with the wrong type, is never treated as vacuously equal to
      an equally-absent field elsewhere -- absence of evidence is not
      evidence of compatibility);
    * ``context_id`` is recomputed, exactly as
      ``agent_evaluation.current_execution_context`` derives it, from
      those same required fields, and matches the recorded value --
      catching a context whose ``context_id`` does not match its own
      semantic contents (tampered or hand-edited).

    A context missing every field but ``context_id`` (e.g. a hand-edited
    ``{"context_id": "..."}``) fails here on the required-fields check;
    it is *never* silently treated as complete just because the caller
    only inspects ``context_id``.
    """

    if not isinstance(context, dict):
        return False
    context_id = context.get("context_id")
    if not isinstance(context_id, str) or not context_id:
        return False
    for field_name, expected_type in EXECUTION_CONTEXT_REQUIRED_FIELD_TYPES.items():
        if not _typed_field_present(context, field_name, expected_type):
            return False
    recomputed = stable_id(
        "evaluation-context",
        {field: context[field] for field in EXECUTION_CONTEXT_REQUIRED_FIELD_TYPES},
    )
    return recomputed == context_id


@dataclass(frozen=True)
class ArtifactLocation:
    evaluation_json_path: Path
    directory: Path
    file_modified_at: str  # ISO UTC; explicitly labeled fallback, never "created_at"

    def to_json(self) -> dict[str, Any]:
        return {
            "evaluation_json_path": str(self.evaluation_json_path),
            "directory": str(self.directory),
            "file_modified_at": self.file_modified_at,
        }


@dataclass(frozen=True)
class SchemaSupport:
    schema: str
    schema_version: int
    supported: bool
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "supported": self.supported,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AdaptedCell:
    schedule_id: str
    subject_role: str
    subject_id: str
    opponent_id: str
    seed: int
    status: str
    outcome: str | None
    match_id: str | None
    artifact_dir: str  # relative to the evaluation directory, as recorded
    score_subject: float | None
    score_opponent: float | None
    territory_subject: float | None
    territory_opponent: float | None
    opponent_index: ConfidenceValue
    seed_index: ConfidenceValue
    condition_occurrence_index: ConfidenceValue
    condition_fingerprint: ConfidenceValue
    opponent_identity: ConfidenceValue  # dict | None
    # Deep-verification eligibility/outcome (B3/Sec 15). ``None`` means
    # verification was never attempted -- ordinary (non-``--verify``)
    # adaptation always leaves both ``None`` so callers can never mistake
    # "not checked" for "checked and passed". Only ``verify_summary()``
    # (``evaluation_history.verification``) populates these.
    verified: bool | None = None
    verify_error: str | None = None
    # H2: the execution context (runtime provenance) this cell was actually
    # executed/resumed under, referencing an entry in the owning
    # ``EvaluationSummary.execution_contexts`` -- ``UNKNOWN`` for v1 (which
    # never recorded this) or a v2 cell that predates/lacks the reference.
    execution_context_id: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    # H1: the canonical result's own ``result_id``, as recorded on this
    # cell -- lets deep verification cross-check the nested result.json's
    # own ``result_id`` against what the evaluation artifact itself
    # recorded, catching a tampered/mismatched ``result_id`` that a
    # match_id-only check would miss. ``None`` when never recorded (a v1
    # artifact predates this field on some builds, or the cell never
    # completed).
    result_id: str | None = None
    # docs/specs/agent_revision.md Sec 5.4: this cell's opponent's durable
    # revision id/archival error, read from the schema-v3 "agent_revisions"
    # sibling field by the same opponent-occurrence position
    # ``opponent_identity`` already uses. ``UNKNOWN`` for v1/v2 artifacts
    # (which never had this concept) and for a v3 artifact whose
    # "agent_revisions" entry is absent or malformed for this position --
    # never a guessed or substituted value.
    opponent_agent_revision_id: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    opponent_agent_revision_error: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    # Deep-verification outcome for this cell's opponent revision (Sec 7.2),
    # populated only by ``verify_summary`` -- ``NOT_CHECKED`` for ordinary
    # (non-``--verify``) adaptation and for any cell with no recorded
    # revision id to check.
    opponent_revision_verification: RevisionVerificationStatus = RevisionVerificationStatus.NOT_CHECKED
    # v0.9 Phase 6 (Phase 5 spec Sec L.1/L.2): which entrant orientation
    # this cell executed under -- "candidate_first" | "opponent_first".
    # Every historical cell (schema < 4) is recovered as
    # ``ConfidenceValue.recovered("candidate_first")``, never ``unknown()``,
    # because the historical fact is certain: every cell ever executed by
    # any shipped version of this module used the candidate/baseline in the
    # always-first-acting slot, unconditionally (Sec C.6). A schema-4 cell
    # reads this as ``RECORDED``.
    orientation: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)

    @property
    def is_scored(self) -> bool:
        return self.status == "completed" and self.outcome in ("win", "loss", "tie")

    def to_json(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "subject_role": self.subject_role,
            "subject_id": self.subject_id,
            "opponent_id": self.opponent_id,
            "seed": self.seed,
            "status": self.status,
            "outcome": self.outcome,
            "match_id": self.match_id,
            "result_id": self.result_id,
            "artifact_dir": self.artifact_dir,
            "score_subject": self.score_subject,
            "score_opponent": self.score_opponent,
            "territory_subject": self.territory_subject,
            "territory_opponent": self.territory_opponent,
            "execution_context_id": self.execution_context_id.to_json(),
            "opponent_index": self.opponent_index.to_json(),
            "seed_index": self.seed_index.to_json(),
            "condition_occurrence_index": self.condition_occurrence_index.to_json(),
            "condition_fingerprint": self.condition_fingerprint.to_json(),
            "opponent_identity": self.opponent_identity.to_json(),
            "verified": self.verified,
            "verify_error": self.verify_error,
            "opponent_agent_revision_id": self.opponent_agent_revision_id.to_json(),
            "opponent_agent_revision_error": self.opponent_agent_revision_error.to_json(),
            "opponent_revision_verification": self.opponent_revision_verification.value,
            "orientation": self.orientation.to_json(),
        }


@dataclass(frozen=True)
class EvaluationSummary:
    location: ArtifactLocation
    schema: SchemaSupport
    evaluation_id: str
    candidate_id: str
    baseline_id: str | None
    opponent_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    ticks: int
    matrix_size: int
    lifecycle_state: ConfidenceValue
    created_at: ConfidenceValue
    finished_at: ConfidenceValue
    rules_compatibility_id: ConfidenceValue
    candidate_identity: ConfidenceValue
    baseline_identity: ConfidenceValue
    effective_conditions: ConfidenceValue
    cells: tuple[AdaptedCell, ...]
    health: HealthReport
    aggregates_recomputed: tuple[SubjectAggregate, ...]
    comparison_recomputed: tuple[ComparisonEntry, ...]
    # H2: every execution context this artifact's cells were actually
    # executed/resumed under, verbatim as recorded (v2 only -- always empty
    # for v1, which never had this concept). Each cell's own
    # ``execution_context_id`` references one entry here by ``context_id``.
    execution_contexts: tuple[dict[str, Any], ...] = ()
    # docs/specs/agent_revision.md Sec 5.4: candidate/baseline durable
    # revision id/archival error, read once per role from the schema-v3
    # "agent_revisions" sibling field -- mirrors how candidate_identity/
    # baseline_identity above are computed once per role rather than per
    # cell. ``UNKNOWN`` for v1/v2 artifacts (which never had this concept)
    # and for a v3 artifact whose "agent_revisions" entry for this role is
    # absent or malformed.
    candidate_agent_revision_id: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    candidate_agent_revision_error: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    baseline_agent_revision_id: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    baseline_agent_revision_error: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    # Deep-verification outcome for the candidate/baseline revision (Sec
    # 7.2), populated only by ``verify_summary`` -- ``NOT_CHECKED`` for
    # ordinary (non-``--verify``) adaptation and whenever no revision id was
    # recorded for that role.
    candidate_revision_verification: RevisionVerificationStatus = RevisionVerificationStatus.NOT_CHECKED
    baseline_revision_verification: RevisionVerificationStatus = RevisionVerificationStatus.NOT_CHECKED
    # v0.9 Phase 6 (Phase 5 spec Sec J.2/AA.4.4): evaluation-wide methodology
    # metadata, following the exact sibling-key pattern
    # ``rules_compatibility_id`` already uses (never folded into
    # ``effective_conditions``). ``orientation_mode`` is "both" |
    # "candidate_first_only"; every historical (schema < 4) evaluation is
    # recovered as ``recovered("candidate_first_only")`` -- certain, not
    # merely inferred, since no prior schema version could produce anything
    # else. ``arena_alignment_mode``'s only v0.9 value is "fixed"; every
    # historical evaluation is recovered as ``recovered("fixed")`` for the
    # identical certainty reason (Sec AA.2/AA.4.6).
    orientation_mode: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    arena_alignment_mode: ConfidenceValue = field(default_factory=ConfidenceValue.unknown)
    # v1.6 Phase 4 (docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md): derived, never
    # persisted -- computed by the v1/v2 adapters from the same
    # ``real_cells`` they already reconstruct for
    # ``aggregates_recomputed``/``comparison_recomputed`` above (Sec 11),
    # via the one shared ``evaluation_analysis.analyze`` entry point.
    # ``None`` only for a hand-built ``EvaluationSummary`` fixture that
    # never calls it -- every adapter-produced summary always sets this.
    analysis: EvaluationAnalysis | None = None

    def to_json(self) -> dict[str, Any]:
        from dataclasses import asdict

        return {
            "location": self.location.to_json(),
            "schema": self.schema.to_json(),
            "evaluation_id": self.evaluation_id,
            "candidate_id": self.candidate_id,
            "baseline_id": self.baseline_id,
            "opponent_ids": list(self.opponent_ids),
            "seeds": list(self.seeds),
            "ticks": self.ticks,
            "matrix_size": self.matrix_size,
            "lifecycle_state": self.lifecycle_state.to_json(),
            "created_at": self.created_at.to_json(),
            "finished_at": self.finished_at.to_json(),
            "rules_compatibility_id": self.rules_compatibility_id.to_json(),
            "candidate_identity": self.candidate_identity.to_json(),
            "baseline_identity": self.baseline_identity.to_json(),
            "effective_conditions": self.effective_conditions.to_json(),
            "cells": [cell.to_json() for cell in self.cells],
            "health": self.health.to_json(),
            "aggregates_recomputed": [asdict(row) for row in self.aggregates_recomputed],
            "comparison_recomputed": [asdict(row) for row in self.comparison_recomputed],
            "execution_contexts": [dict(item) for item in self.execution_contexts],
            "candidate_agent_revision_id": self.candidate_agent_revision_id.to_json(),
            "candidate_agent_revision_error": self.candidate_agent_revision_error.to_json(),
            "baseline_agent_revision_id": self.baseline_agent_revision_id.to_json(),
            "baseline_agent_revision_error": self.baseline_agent_revision_error.to_json(),
            "candidate_revision_verification": self.candidate_revision_verification.value,
            "baseline_revision_verification": self.baseline_revision_verification.value,
            "orientation_mode": self.orientation_mode.to_json(),
            "arena_alignment_mode": self.arena_alignment_mode.to_json(),
            "analysis": self.analysis.to_json() if self.analysis is not None else None,
        }


def file_modified_at(path: Path) -> str:
    """Filesystem mtime, UTC-normalized -- explicitly a fallback, never ``created_at``."""

    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def evaluation_cells_from_raw(
    raw_cells: list[dict[str, Any]], base_dir: Path
) -> tuple[EvaluationCell, ...]:
    """Rebuild real ``EvaluationCell`` objects from parsed JSON.

    Lets the adapters reuse ``agent_evaluation.aggregate_cells``/
    ``compare_candidate_baseline`` unchanged instead of a second, drifting
    aggregation implementation (docs/specs/evaluation_history.md Sec 11's
    "derived fields must never override contradictory canonical cell
    state" -- satisfied by always recomputing through the one existing
    function rather than trusting a stored ``aggregates``/``comparison``
    block).
    """

    known_fields = {f for f in EvaluationCell.__dataclass_fields__}
    cells = []
    for raw in raw_cells:
        kwargs = {key: value for key, value in raw.items() if key in known_fields}
        kwargs["artifact_dir"] = base_dir / str(raw.get("artifact_dir", "."))
        cells.append(EvaluationCell(**kwargs))
    return tuple(cells)


__all__ = [
    "EXECUTION_CONTEXT_REQUIRED_FIELD_TYPES",
    "AdaptedCell",
    "ArtifactLocation",
    "ArtifactPathEscapeError",
    "ArtifactReadError",
    "ConfidenceValue",
    "EvaluationSummary",
    "FieldConfidence",
    "HealthCode",
    "HealthReport",
    "RevisionVerificationStatus",
    "SchemaSupport",
    "evaluation_cells_from_raw",
    "execution_context_is_valid",
    "file_modified_at",
    "resolve_contained_path",
]
