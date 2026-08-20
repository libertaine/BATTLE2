"""Read-only ``bytefray.evaluation`` v1 -> common history model (Sec 10).

Never mutates the v1 artifact and never treats current agent discovery as
historical evidence. Verified directly against v0.6.1 canonical artifacts:
``result.json``'s ``entrants`` list *does* persist a per-entrant
``metadata`` block including ``source_sha256``/``api_version``/
``agent_version`` (correcting a prior factual error in this module/its
report -- M6) -- but it does **not** persist the entry-point path or any
rules-compatibility identifier, so full strict historical identity is
still not recoverable, only these three narrower dimensions. Effective
conditions are recovered only as far as ``reproducibility`` actually
allows (seed/arena/ticks/budget/win_mode/weights -- no rules compatibility
identifier, which v1 never had).

Every recovered dimension below inspects *all* usable cells, never just
the first (M6): equal across every usable cell -> ``RECOVERED``;
disagreement across cells -> ``CONFLICTING`` (carries every distinct value
seen, not a guessed winner); no usable evidence at all -> ``UNKNOWN``.
Because ``rules_compatibility_id`` stays permanently ``UNKNOWN`` for v1
(never recoverable), ``comparison._condition_key`` -- which requires a
known rules id before aligning any cell -- already refuses strict
comparison for every v1 cell regardless of how confidently identity/
conditions were recovered; partial recovery here can never accidentally
unlock a strict comparison that requires entry-point/rules-compatibility
evidence v1 simply does not have.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from battle_engine.agent_evaluation import all_subject_aggregates, compare_candidate_baseline
from battle_engine.agent_test import OPPONENT_SLOT, TESTED_AGENT_SLOT
from battle_engine.evaluation_analysis import analyze as analyze_evaluation
from battle_engine.result_model import ResultEnvelope, read_result

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

_IDENTITY_METADATA_FIELDS = ("source_sha256", "api_version", "agent_version")


def _usable_envelopes(
    raw_cells: list[dict[str, Any]],
    base_dir: Path,
    predicate: Callable[[dict[str, Any]], bool],
):
    for raw in raw_cells:
        if not predicate(raw):
            continue
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
            yield read_result(result_path)
        except (OSError, ValueError, KeyError):
            continue


def _recover_by_consensus(
    values: list[dict[str, Any]],
) -> ConfidenceValue:
    unique: list[dict[str, Any]] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    if not unique:
        return ConfidenceValue.unknown()
    if len(unique) == 1:
        return ConfidenceValue.recovered(unique[0])
    return ConfidenceValue.conflicting(unique)


def _recover_effective_conditions(raw_cells: list[dict[str, Any]], base_dir: Path) -> ConfidenceValue:
    conditions: list[dict[str, Any]] = []
    for envelope in _usable_envelopes(raw_cells, base_dir, lambda raw: True):
        repro = dict(envelope.reproducibility)
        if not repro:
            continue
        conditions.append(
            {
                "tick_limit": repro.get("tick_limit"),
                "arena_size": repro.get("arena_size"),
                "action_budget": repro.get("action_budget"),
                "win_mode": repro.get("win_mode"),
                "weights": repro.get("weights"),
            }
        )
    return _recover_by_consensus(conditions)


def _entrant_metadata_identity(envelope: ResultEnvelope, slot: str) -> dict[str, Any] | None:
    entrant = next((entry for entry in envelope.entrants if entry.get("agent_id") == slot), None)
    if entrant is None:
        return None
    metadata = entrant.get("metadata") or {}
    identity = {field: metadata.get(field) for field in _IDENTITY_METADATA_FIELDS}
    if all(value is None for value in identity.values()):
        return None
    return identity


def _recover_identity(
    raw_cells: list[dict[str, Any]],
    base_dir: Path,
    *,
    predicate: Callable[[dict[str, Any]], bool],
    slot: str,
) -> ConfidenceValue:
    """M6: source_sha256/api_version/agent_version only -- entry_point and
    any rules-compatibility identifier are never persisted by a v1
    canonical result and stay permanently unrecoverable (see module
    docstring for why this is still comparison-safe).
    """

    identities: list[dict[str, Any]] = []
    for envelope in _usable_envelopes(raw_cells, base_dir, predicate):
        identity = _entrant_metadata_identity(envelope, slot)
        if identity is not None:
            identities.append(identity)
    return _recover_by_consensus(identities)


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
    return adapt_v1_data(data, path)


def adapt_v1_data(data: dict[str, Any], path: Path) -> EvaluationSummary:
    """Same as :func:`adapt_v1`, but for an already-parsed JSON object.

    ``path`` must already be resolved -- used by ``discovery.adapt_any``
    to avoid reading/parsing the artifact from disk a second time just to
    dispatch to the right adapter.
    """

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

    # M6: recovered once per distinct opponent_id, from every usable cell
    # (either subject role) that actually played that opponent -- not just
    # the first cell encountered anywhere in the artifact.
    def _matches_opponent(opponent_id: str) -> Callable[[dict[str, Any]], bool]:
        return lambda raw: raw.get("opponent_id") == opponent_id

    opponent_identity_by_id: dict[str, ConfidenceValue] = {
        opponent_id: _recover_identity(
            raw_cells, path.parent, predicate=_matches_opponent(opponent_id), slot=OPPONENT_SLOT
        )
        for opponent_id in set(opponent_ids)
    }

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
                result_id=raw.get("result_id"),
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
                opponent_identity=opponent_identity_by_id.get(
                    raw.get("opponent_id"), ConfidenceValue.unknown()
                ),
                # v0.9 Phase 6 (Phase 5 spec Sec L.2): certain, not merely
                # guessed -- every v1 cell was executed by a shipped version
                # of this module that only ever put the subject in the
                # always-first-acting slot.
                orientation=ConfidenceValue.recovered("candidate_first"),
                # v2.0.0-beta2 Phase 1 (Sec Identity): no v1-schema
                # evaluation ever varied placement -- recovered as the
                # certain historical fact, mirroring orientation immediately
                # above.
                placement=ConfidenceValue.recovered("fixed"),
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
    # v0.9 Phase 6 (Sec K.2): pooled + per-orientation views. Every v1 cell
    # reconstructed by `evaluation_cells_from_raw` defaults to
    # `orientation="candidate_first"` (no v1 cell ever recorded the field),
    # which is also the historically correct fact.
    aggregates = all_subject_aggregates(candidate_id, baseline_id, real_cells)
    comparison = compare_candidate_baseline(real_cells) if baseline_id is not None else ()
    analysis = analyze_evaluation(candidate_id, baseline_id, real_cells)

    candidate_identity = _recover_identity(
        raw_cells,
        path.parent,
        predicate=lambda raw: raw.get("subject_role") == "candidate",
        slot=TESTED_AGENT_SLOT,
    )
    baseline_identity = (
        _recover_identity(
            raw_cells,
            path.parent,
            predicate=lambda raw: raw.get("subject_role") == "baseline",
            slot=TESTED_AGENT_SLOT,
        )
        if baseline_id is not None
        else ConfidenceValue.unknown()
    )

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
        candidate_identity=candidate_identity,
        baseline_identity=baseline_identity,
        effective_conditions=_recover_effective_conditions(raw_cells, path.parent),
        cells=tuple(cells),
        health=HealthReport(codes=tuple(codes), detail=tuple(detail), verified=False),
        aggregates_recomputed=tuple(aggregates),
        comparison_recomputed=tuple(comparison),
        # v0.9 Phase 6 (Phase 5 spec Sec L.2/AA.4.6): certain, not merely
        # guessed -- every v1 evaluation ever executed used candidate_first
        # exclusively (no orientation concept existed) at a single, fixed
        # arena alignment (Sec C.8: entrant.start never affected a Python
        # entrant's actual write addresses).
        orientation_mode=ConfidenceValue.recovered("candidate_first_only"),
        arena_alignment_mode=ConfidenceValue.recovered("fixed"),
        analysis=analysis,
    )


__all__ = ["adapt_v1", "adapt_v1_data"]
