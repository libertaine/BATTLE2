"""Cross-evaluation comparison: strict conditions, duplicate alignment, verdicts (Sec 14)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .models import AdaptedCell, EvaluationSummary, FieldConfidence

_OUTCOME_RANK = {"loss": 0, "tie": 1, "win": 2}

# H2/H3: fields relevant to whether two execution contexts are the "same
# runtime" for direct-comparison purposes, and the type each must have to
# count as actually *present* (not just absent-and-therefore-None on both
# sides, which is not evidence of compatibility). Deliberately excludes
# `context_id` (derived from these) and `first_used_at` (an irrelevant
# bookkeeping timestamp, not a runtime property) -- this is a narrow
# runtime-compatibility rule for comparison, not general environment
# provenance.
_CONTEXT_REQUIRED_FIELD_TYPES: dict[str, type] = {
    "bytefray_version": str,
    "agent_api_version": int,
    "python_version": str,
    "result_schema_version": int,
    "replay_schema_version": int,
    "rules_compatibility_id": str,
}


def _context_by_id(summary: EvaluationSummary) -> dict[str, dict[str, Any]]:
    return {
        context["context_id"]: context
        for context in summary.execution_contexts
        if isinstance(context.get("context_id"), str)
    }


def _cell_context(cell: AdaptedCell, context_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    context_id = cell.execution_context_id.value
    if not isinstance(context_id, str):
        return None
    return context_by_id.get(context_id)


def _context_field_present(context: dict[str, Any], field: str, expected_type: type) -> bool:
    if field not in context:
        return False
    value = context[field]
    if expected_type is int and isinstance(value, bool):
        return False
    return isinstance(value, expected_type)


def _contexts_compatible(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    """H3: both sides' execution context must be *known* and agree on every
    compatibility-relevant field. An unknown/missing context on either side
    is never treated as compatible -- absence of evidence is not evidence
    of compatibility.

    A required field that is simply absent from a context dict (e.g. a
    hand-edited or malformed ``{"context_id": "..."}`` with nothing else)
    must never be treated as implicitly equal to an equally-absent field on
    the other side -- comparing via plain ``.get(field)`` would let two
    *incomplete* contexts compare ``None == None`` and read as compatible.
    Each required field must actually be present, with the expected type,
    on *both* sides before its values are compared at all.
    """

    if left is None or right is None:
        return False
    for field, expected_type in _CONTEXT_REQUIRED_FIELD_TYPES.items():
        if not _context_field_present(left, field, expected_type):
            return False
        if not _context_field_present(right, field, expected_type):
            return False
        if left[field] != right[field]:
            return False
    return True


@dataclass(frozen=True)
class ComparisonRow:
    opponent_id: str
    seed: int
    condition_occurrence_index: int | None
    left_outcome: str | None
    right_outcome: str | None
    verdict: str  # "improved" | "regressed" | "unchanged" | "inconclusive"
    reason: str | None = None
    left_score: float | None = None
    right_score: float | None = None
    left_territory: float | None = None
    right_territory: float | None = None
    reproducibility_anomaly: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "opponent_id": self.opponent_id,
            "seed": self.seed,
            "condition_occurrence_index": self.condition_occurrence_index,
            "left_outcome": self.left_outcome,
            "right_outcome": self.right_outcome,
            "verdict": self.verdict,
            "reason": self.reason,
            "left_score": self.left_score,
            "right_score": self.right_score,
            "left_territory": self.left_territory,
            "right_territory": self.right_territory,
            "reproducibility_anomaly": self.reproducibility_anomaly,
        }


@dataclass(frozen=True)
class ComparisonDenominators:
    left_total: int = 0
    right_total: int = 0
    condition_intersection: int = 0
    directly_comparable: int = 0
    improved: int = 0
    regressed: int = 0
    unchanged: int = 0
    inconclusive: int = 0
    unmatched_left: int = 0
    unmatched_right: int = 0
    changed_condition: int = 0
    ambiguous_duplicate_groups: int = 0
    corrupt_or_missing: int = 0

    def to_json(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


@dataclass(frozen=True)
class BaselineContext:
    left_baseline_id: str | None
    right_baseline_id: str | None
    identity_status: str
    control_rows: tuple[ComparisonRow, ...] = ()
    control_anomaly: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "left_baseline_id": self.left_baseline_id,
            "right_baseline_id": self.right_baseline_id,
            "identity_status": self.identity_status,
            "control_rows": [row.to_json() for row in self.control_rows],
            "control_anomaly": self.control_anomaly,
        }


@dataclass(frozen=True)
class AlignedComparison:
    orientation: str
    candidate_changed: bool
    candidate_diff: dict[str, Any] | None
    baseline_context: BaselineContext
    rows: tuple[ComparisonRow, ...]
    unmatched_left: tuple[AdaptedCell, ...]
    unmatched_right: tuple[AdaptedCell, ...]
    changed_condition: tuple[tuple[AdaptedCell, AdaptedCell], ...]
    ambiguous_duplicate_groups: tuple[tuple[Any, ...], ...]
    reproducibility_anomalies: tuple[ComparisonRow, ...]
    denominators: ComparisonDenominators
    # Whether this comparison ran against deep-verified evidence (B3/Sec 15,
    # `--verify`) -- an ordinary comparison always leaves this False, and
    # its output must say so plainly rather than implying its evidence was
    # verified.
    deep_verified: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "orientation": self.orientation,
            "candidate_changed": self.candidate_changed,
            "candidate_diff": self.candidate_diff,
            "baseline_context": self.baseline_context.to_json(),
            "rows": [row.to_json() for row in self.rows],
            "unmatched_left": [cell.to_json() for cell in self.unmatched_left],
            "unmatched_right": [cell.to_json() for cell in self.unmatched_right],
            "changed_condition": [
                [left.to_json(), right.to_json()] for left, right in self.changed_condition
            ],
            "ambiguous_duplicate_groups": [list(group) for group in self.ambiguous_duplicate_groups],
            "reproducibility_anomalies": [row.to_json() for row in self.reproducibility_anomalies],
            "denominators": self.denominators.to_json(),
            "deep_verified": self.deep_verified,
        }


def _conditions_fingerprint(summary: EvaluationSummary) -> str | None:
    if summary.effective_conditions.confidence == FieldConfidence.UNKNOWN:
        return None
    return json.dumps(summary.effective_conditions.value, sort_keys=True)


def _rules_id(summary: EvaluationSummary) -> str | None:
    if summary.rules_compatibility_id.confidence == FieldConfidence.UNKNOWN:
        return None
    return summary.rules_compatibility_id.value


def _condition_key(
    cell: AdaptedCell, conditions_fp: str | None, rules_id: str | None
) -> tuple[Any, ...] | None:
    """Sec 14: excludes candidate identity by construction; unknowns never align."""

    if conditions_fp is None or rules_id is None:
        return None
    if cell.opponent_identity.confidence == FieldConfidence.UNKNOWN:
        return None
    if cell.condition_occurrence_index.confidence == FieldConfidence.UNKNOWN:
        return None
    opponent = cell.opponent_identity.value or {}
    return (
        opponent.get("agent_id"),
        opponent.get("source_sha256"),
        opponent.get("entry_point"),
        opponent.get("api_version"),
        # B4: an opponent local-source-only edit (an imported helper/nested
        # local package, not the entry-point file itself) changes neither
        # `source_sha256` nor `entry_point` above but is still a genuinely
        # different opponent revision -- without this, two evaluations
        # separated only by an opponent helper edit would strict-key-match
        # and compare directly, silently attributing any outcome delta to
        # the candidate instead of reporting it as a changed condition.
        opponent.get("local_source_fingerprint"),
        cell.seed,
        conditions_fp,
        rules_id,
        cell.condition_occurrence_index.value,
    )


def verdict(left_outcome: str, right_outcome: str) -> str:
    delta = _OUTCOME_RANK[right_outcome] - _OUTCOME_RANK[left_outcome]
    if delta > 0:
        return "improved"
    if delta < 0:
        return "regressed"
    return "unchanged"


def _candidate_cells(summary: EvaluationSummary) -> tuple[AdaptedCell, ...]:
    return tuple(cell for cell in summary.cells if cell.subject_role == "candidate")


def _baseline_cells(summary: EvaluationSummary) -> tuple[AdaptedCell, ...]:
    return tuple(cell for cell in summary.cells if cell.subject_role == "baseline")


AmbiguousGroup = tuple[str, int, tuple[str, ...], tuple[str, ...]]


def _classify_unmatched(
    unmatched_left: list[AdaptedCell], unmatched_right: list[AdaptedCell]
) -> tuple[
    list[tuple[AdaptedCell, AdaptedCell]],
    list[AmbiguousGroup],
    list[AdaptedCell],
    list[AdaptedCell],
]:
    """M3: classify cells left unmatched by strict condition-key alignment.

    Grouped only by ``(opponent_id, seed)`` -- never by outcome (Sec 14's
    "never pair duplicates based on outcomes"). A group with exactly one
    unmatched cell on each side is an unambiguous ``changed_condition``
    pair: the same nominal (opponent, seed) slot, but some other condition
    dimension (rules id, effective conditions, or the opponent's own
    identity) differs, which is exactly why strict alignment above didn't
    match them. A group with more than one unmatched cell on either side is
    genuinely ambiguous -- pairing them would have to guess which duplicate
    corresponds to which, so it is reported as an ``ambiguous_duplicate_group``
    instead of silently zipped under a coordinate that isn't actually
    unique here (this includes legacy v1 duplicates whose
    ``condition_occurrence_index`` came back ``UNKNOWN`` and so never
    matched anything above at all). A group present on only one side is
    left as ordinary unmatched -- there is nothing "changed" to relate it
    to.
    """

    left_by_key: dict[tuple[str, int], list[AdaptedCell]] = {}
    for cell in unmatched_left:
        left_by_key.setdefault((cell.opponent_id, cell.seed), []).append(cell)
    right_by_key: dict[tuple[str, int], list[AdaptedCell]] = {}
    for cell in unmatched_right:
        right_by_key.setdefault((cell.opponent_id, cell.seed), []).append(cell)

    changed_condition: list[tuple[AdaptedCell, AdaptedCell]] = []
    ambiguous_groups: list[AmbiguousGroup] = []
    consumed_left: set[int] = set()
    consumed_right: set[int] = set()

    for key in sorted(set(left_by_key) | set(right_by_key)):
        left_group = left_by_key.get(key, [])
        right_group = right_by_key.get(key, [])
        if not left_group or not right_group:
            continue
        if len(left_group) == 1 and len(right_group) == 1:
            changed_condition.append((left_group[0], right_group[0]))
            consumed_left.add(id(left_group[0]))
            consumed_right.add(id(right_group[0]))
        else:
            ambiguous_groups.append(
                (
                    key[0],
                    key[1],
                    tuple(cell.schedule_id for cell in left_group),
                    tuple(cell.schedule_id for cell in right_group),
                )
            )
            consumed_left.update(id(cell) for cell in left_group)
            consumed_right.update(id(cell) for cell in right_group)

    remaining_left = [cell for cell in unmatched_left if id(cell) not in consumed_left]
    remaining_right = [cell for cell in unmatched_right if id(cell) not in consumed_right]
    return changed_condition, ambiguous_groups, remaining_left, remaining_right


def _align_cell_sets(
    left_cells: tuple[AdaptedCell, ...],
    right_cells: tuple[AdaptedCell, ...],
    left_conditions_fp: str | None,
    left_rules_id: str | None,
    right_conditions_fp: str | None,
    right_rules_id: str | None,
    *,
    identical_candidate_fingerprint: bool,
    deep_verified: bool = False,
    left_context_by_id: dict[str, dict[str, Any]] | None = None,
    right_context_by_id: dict[str, dict[str, Any]] | None = None,
) -> tuple[
    list[ComparisonRow],
    list[AdaptedCell],
    list[AdaptedCell],
    list[tuple[AdaptedCell, AdaptedCell]],
    list[ComparisonRow],
    list[AmbiguousGroup],
]:
    left_by_key: dict[tuple[Any, ...], list[AdaptedCell]] = {}
    for cell in left_cells:
        key = _condition_key(cell, left_conditions_fp, left_rules_id)
        if key is not None:
            left_by_key.setdefault(key, []).append(cell)
    right_by_key: dict[tuple[Any, ...], list[AdaptedCell]] = {}
    for cell in right_cells:
        key = _condition_key(cell, right_conditions_fp, right_rules_id)
        if key is not None:
            right_by_key.setdefault(key, []).append(cell)

    rows: list[ComparisonRow] = []
    anomalies: list[ComparisonRow] = []
    ambiguous_groups: list[AmbiguousGroup] = []
    unmatched_left: list[AdaptedCell] = list(left_cells)
    unmatched_right: list[AdaptedCell] = list(right_cells)

    all_keys = sorted(set(left_by_key) | set(right_by_key), key=repr)
    for key in all_keys:
        left_group = left_by_key.get(key, [])
        right_group = right_by_key.get(key, [])
        # H4: a strict condition key is supposed to be unique per side (the
        # occurrence index is meant to disambiguate duplicates). If either
        # side nonetheless has more than one cell under the identical key,
        # that uniqueness assumption is already broken -- structurally
        # ambiguous which cell corresponds to which, so this group is never
        # zipped positionally (which would silently guess a pairing and
        # could report an ordinary verdict built from mismatched cells).
        # Reported as ambiguous instead, consuming every cell in the group.
        if len(left_group) > 1 or len(right_group) > 1:
            anchor = left_group[0] if left_group else right_group[0]
            ambiguous_groups.append(
                (
                    anchor.opponent_id,
                    anchor.seed,
                    tuple(cell.schedule_id for cell in left_group),
                    tuple(cell.schedule_id for cell in right_group),
                )
            )
            for cell in left_group:
                unmatched_left.remove(cell)
            for cell in right_group:
                unmatched_right.remove(cell)
            continue
        for left_cell, right_cell in zip(left_group, right_group):
            unmatched_left.remove(left_cell)
            unmatched_right.remove(right_cell)
            if not left_cell.is_scored or not right_cell.is_scored:
                row = ComparisonRow(
                    opponent_id=right_cell.opponent_id,
                    seed=right_cell.seed,
                    condition_occurrence_index=(
                        right_cell.condition_occurrence_index.value
                        if right_cell.condition_occurrence_index.confidence != FieldConfidence.UNKNOWN
                        else None
                    ),
                    left_outcome=left_cell.outcome,
                    right_outcome=right_cell.outcome,
                    verdict="inconclusive",
                    reason=f"left={left_cell.status}/{left_cell.outcome} right={right_cell.status}/{right_cell.outcome}",
                    left_score=left_cell.score_subject,
                    right_score=right_cell.score_subject,
                    left_territory=left_cell.territory_subject,
                    right_territory=right_cell.territory_subject,
                )
                rows.append(row)
                continue
            assert left_cell.outcome is not None and right_cell.outcome is not None
            outcome_verdict = verdict(left_cell.outcome, right_cell.outcome)
            reason: str | None = None
            # B3: when this comparison was run with `--verify`
            # (`deep_verified` requested), a pair may only keep an ordinary
            # improved/regressed/unchanged verdict if *both* cells actually,
            # individually verified. A cell that failed verification, or
            # was never verified at all despite being eligible, must not
            # silently keep contributing an ordinary verdict (and therefore
            # the direct-comparison denominator) just because its outcome
            # happened to be readable -- that would let a corrupted/tampered
            # cell masquerade as scientific evidence.
            if deep_verified and (left_cell.verified is not True or right_cell.verified is not True):
                unverified_side = "left" if left_cell.verified is not True else "right"
                other_unverified = left_cell.verified is not True and right_cell.verified is not True
                reason = (
                    "both cells failed or were never deep-verified; not a controlled comparison"
                    if other_unverified
                    else f"{unverified_side} cell failed or was never deep-verified; not a controlled comparison"
                )
                outcome_verdict = "inconclusive"
            # H3: a materially different or unknown runtime execution
            # context between the two sides is not grounds to report an
            # ordinary improvement/regression/unchanged -- equivalence
            # cannot be established under different (or unknown) runtimes.
            # Conservative rule for this pass: this downgrades *every*
            # outcome verdict, including "unchanged" ("no observed
            # difference" is not the same claim as "confirmed equivalent
            # under a controlled comparison").
            elif not _contexts_compatible(
                _cell_context(left_cell, left_context_by_id or {}),
                _cell_context(right_cell, right_context_by_id or {}),
            ):
                reason = (
                    "execution contexts differ or are unknown; not a controlled "
                    "comparison across incompatible or unknown runtimes"
                )
                outcome_verdict = "inconclusive"
            # A reproducibility anomaly is a claim that identical inputs
            # produced different outcomes -- it must never rest on evidence
            # that was merely read and recomputed from the artifact's own
            # recorded fields. Requiring `deep_verified` (this comparison
            # ran with `--verify`) plus both individual cells having
            # actually verified is what makes that claim trustworthy
            # (B3/Sec 14 "verified baseline-control claims must require
            # genuinely verified eligible cells").
            anomaly = (
                deep_verified
                and identical_candidate_fingerprint
                and outcome_verdict in ("improved", "regressed")
                and left_cell.verified is True
                and right_cell.verified is True
            )
            row = ComparisonRow(
                opponent_id=right_cell.opponent_id,
                seed=right_cell.seed,
                condition_occurrence_index=right_cell.condition_occurrence_index.value,
                left_outcome=left_cell.outcome,
                right_outcome=right_cell.outcome,
                verdict=outcome_verdict,
                reason=reason,
                left_score=left_cell.score_subject,
                right_score=right_cell.score_subject,
                left_territory=left_cell.territory_subject,
                right_territory=right_cell.territory_subject,
                reproducibility_anomaly=anomaly,
            )
            rows.append(row)
            if anomaly:
                anomalies.append(row)

    changed_condition, more_ambiguous_groups, unmatched_left, unmatched_right = _classify_unmatched(
        unmatched_left, unmatched_right
    )
    ambiguous_groups.extend(more_ambiguous_groups)
    return rows, unmatched_left, unmatched_right, changed_condition, anomalies, ambiguous_groups


def align(
    left: EvaluationSummary, right: EvaluationSummary, *, deep_verified: bool = False
) -> AlignedComparison:
    """Right (new) relative to left (old) -- Sec 14. Orientation is always explicit.

    ``deep_verified`` must be ``True`` only when the caller has already run
    ``evaluation_history.verification.verify_summary`` on *both* ``left``
    and ``right`` (i.e. ``bytefray agents evaluations compare --verify``) --
    it gates reproducibility-anomaly and baseline-control-anomaly detection
    (B3/Sec 14), which must never rest on evidence that was only read and
    recomputed from the artifacts' own recorded fields. An ordinary
    (non-``--verify``) comparison leaves this ``False`` and its output must
    say so plainly rather than implying its evidence was verified.
    """

    left_id = left.candidate_identity
    right_id = right.candidate_identity
    candidate_changed = left.candidate_id != right.candidate_id
    candidate_diff: dict[str, Any] | None = None
    identical_candidate_fingerprint = False
    if left_id.confidence != FieldConfidence.UNKNOWN and right_id.confidence != FieldConfidence.UNKNOWN:
        if left_id.value != right_id.value:
            candidate_diff = {
                key: (left_id.value.get(key), right_id.value.get(key))
                for key in set(left_id.value) | set(right_id.value)
                if left_id.value.get(key) != right_id.value.get(key)
            }
        else:
            identical_candidate_fingerprint = True
    elif left.candidate_id != right.candidate_id:
        candidate_diff = {"agent_id": (left.candidate_id, right.candidate_id)}

    left_cfp, right_cfp = _conditions_fingerprint(left), _conditions_fingerprint(right)
    left_rules, right_rules = _rules_id(left), _rules_id(right)
    left_contexts, right_contexts = _context_by_id(left), _context_by_id(right)

    rows, unmatched_left, unmatched_right, changed_condition, anomalies, ambiguous_groups = (
        _align_cell_sets(
            _candidate_cells(left),
            _candidate_cells(right),
            left_cfp,
            left_rules,
            right_cfp,
            right_rules,
            identical_candidate_fingerprint=identical_candidate_fingerprint,
            deep_verified=deep_verified,
            left_context_by_id=left_contexts,
            right_context_by_id=right_contexts,
        )
    )

    # Baseline context (Sec 14.3).
    if left.baseline_id is None and right.baseline_id is None:
        identity_status = "absent_both"
    elif left.baseline_id is None or right.baseline_id is None:
        identity_status = "absent_one"
    elif (
        left.baseline_identity.confidence == FieldConfidence.UNKNOWN
        or right.baseline_identity.confidence == FieldConfidence.UNKNOWN
    ):
        identity_status = "unknown_legacy"
    elif left.baseline_identity.value == right.baseline_identity.value:
        identity_status = "same"
    else:
        identity_status = "changed"

    control_rows: tuple[ComparisonRow, ...] = ()
    control_anomaly = False
    if identity_status == "same":
        control_result = _align_cell_sets(
            _baseline_cells(left),
            _baseline_cells(right),
            left_cfp,
            left_rules,
            right_cfp,
            right_rules,
            identical_candidate_fingerprint=True,
            deep_verified=deep_verified,
            left_context_by_id=left_contexts,
            right_context_by_id=right_contexts,
        )
        control_rows = tuple(control_result[0])
        # A verified baseline-control claim ("the same baseline diverged
        # under nominally identical conditions") reuses the exact same
        # per-row `reproducibility_anomaly` gate as the main comparison --
        # never a weaker `verdict != "unchanged"` check that would fire on
        # unverified evidence.
        control_anomaly = any(row.reproducibility_anomaly for row in control_rows)

    baseline_context = BaselineContext(
        left_baseline_id=left.baseline_id,
        right_baseline_id=right.baseline_id,
        identity_status=identity_status,
        control_rows=control_rows,
        control_anomaly=control_anomaly,
    )

    directly_comparable = sum(1 for row in rows if row.verdict != "inconclusive")
    denominators = ComparisonDenominators(
        left_total=len(_candidate_cells(left)),
        right_total=len(_candidate_cells(right)),
        condition_intersection=len(rows),
        directly_comparable=directly_comparable,
        improved=sum(1 for row in rows if row.verdict == "improved"),
        regressed=sum(1 for row in rows if row.verdict == "regressed"),
        unchanged=sum(1 for row in rows if row.verdict == "unchanged"),
        inconclusive=sum(1 for row in rows if row.verdict == "inconclusive"),
        unmatched_left=len(unmatched_left),
        unmatched_right=len(unmatched_right),
        changed_condition=len(changed_condition),
        ambiguous_duplicate_groups=len(ambiguous_groups),
        corrupt_or_missing=sum(
            1
            for cell in _candidate_cells(left) + _candidate_cells(right)
            if cell.status in ("failed", "corrupted", "drift_detected")
        ),
    )

    return AlignedComparison(
        orientation="right_relative_to_left",
        candidate_changed=candidate_changed,
        candidate_diff=candidate_diff,
        baseline_context=baseline_context,
        rows=tuple(rows),
        unmatched_left=tuple(unmatched_left),
        unmatched_right=tuple(unmatched_right),
        changed_condition=tuple(changed_condition),
        ambiguous_duplicate_groups=tuple(ambiguous_groups),
        reproducibility_anomalies=tuple(anomalies),
        denominators=denominators,
        deep_verified=deep_verified,
    )


__all__ = [
    "AlignedComparison",
    "BaselineContext",
    "ComparisonDenominators",
    "ComparisonRow",
    "align",
    "verdict",
]
