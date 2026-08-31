"""Bytefray gameplay Ruleset identity.

A single, first-class compatibility axis for Bytefray *gameplay* semantics,
deliberately kept separate from the schema/version identifiers that
describe how those semantics are persisted, exercised, or measured. See
``docs/RULES.md`` for the full Ruleset v1 contract this identifies and
``docs/COMPATIBILITY.md`` for how it relates to the other compatibility
axes (Agent API version, artifact schema versions, evaluation methodology
fields, agent revision identity).

This module is deliberately dependency-free (standard library only) so it
can be imported by the match/runtime, artifact (result/replay), and
evaluation layers without creating a cycle -- see ``docs/COMPATIBILITY.md``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

# Identifies the frozen Bytefray gameplay ruleset described in full in
# docs/RULES.md: scoring formulas, ownership/last-writer semantics,
# scheduling order, mortality and match-termination rules, winner
# resolution, and the shared/VM-specific/Python-specific gameplay clauses
# documented there.
#
# Maintainers must bump this identifier (to "bytefray-rules-2", following
# the same naming pattern) only when one of those *semantics* actually
# changes -- see docs/RULES.md's "Ruleset bump policy" and
# docs/COMPATIBILITY.md's compatibility-axis table for worked examples,
# such as a scoring-formula change, an ownership/kill-attribution change, a
# scheduler-order change, or a redefined arena-addressing/observation
# meaning.
#
# This identifier does NOT change for:
#   * per-match configuration *values* (arena size, weights, tick limit,
#     seed, entrant IDs) -- the *meaning* of those fields is Ruleset-
#     defined, but the values selected for one match are not (see
#     docs/RULES.md's "Configuration values are not Ruleset identity");
#   * the Agent API v1 loading/observation/action contract or its
#     deterministic entrant-seed derivation, which is a separate,
#     independently versioned compatibility axis
#     (``battle_engine.agent_api.AGENT_API_VERSION``; see
#     ``docs/AGENT_API_V1.md``);
#   * artifact/schema wire-format changes (``battle2.result``,
#     ``battle2.replay``, ``bytefray.evaluation``, ...), which version
#     independently; and
#   * evaluation methodology changes (entrant-orientation coverage,
#     arena-alignment disclosure, ...), which are evaluation-scope
#     concerns, not gameplay.
BYTEFRAY_RULESET_ID = "bytefray-rules-1"
BYTEFRAY_RULESET_V4_ALPHA1_ID = "bytefray-rules-4-alpha1"


# v0.10 Phase 4: a finite, explicit historical-alias table -- deliberately
# not a generic "normalize any evaluation-rules-N-shaped string" function.
# Each entry records a relationship actually established by git-history
# evidence (see docs/RULES.md's "Historical relationship to
# evaluation-rules-1"), not a naming-convention guess. Extend this table
# only when equivalent historical evidence justifies a new entry; an
# unrecognized string must never opportunistically normalize.
_RULESET_ALIASES: Mapping[str, str] = {
    "evaluation-rules-1": BYTEFRAY_RULESET_ID,
}


def normalize_ruleset_id(value: str) -> str:
    """Return the canonical Ruleset identity ``value`` semantically denotes.

    Maps a known historical alias (currently only the pre-v0.10
    ``"evaluation-rules-1"`` literal ``bytefray.evaluation`` wrote before
    ``EVALUATION_RULES_COMPATIBILITY_ID`` became a derived alias of this
    module's ``BYTEFRAY_RULESET_ID``) to the current spelling. An
    unrecognized value is returned unchanged -- this is intentionally a
    finite lookup, never prefix/pattern matching, so an unrelated or future
    Ruleset identity can never be silently misclassified as equivalent to
    today's.
    """

    return _RULESET_ALIASES.get(value, value)


# Confidence states for a Ruleset identity attributed to one persisted
# artifact (result/replay). Deliberately a narrower, self-contained
# vocabulary rather than importing evaluation_history's richer
# ``FieldConfidence``/``ConfidenceValue`` machinery, which depends on
# ``battle_engine.agent_evaluation`` and sits well above this
# dependency-free module in the layering (``docs/COMPATIBILITY.md``) --
# see docs/COMPATIBILITY.md's "Legacy compatibility matrix" for how these
# four states apply to each artifact/version/runtime combination.
#
#   recorded       -- the artifact itself carries an explicit ruleset_id.
#   recovered       -- the artifact predates the ruleset_id field, but its
#                       shape/version is evidence-backed as having run under
#                       BYTEFRAY_RULESET_ID (see docs/RULES.md's historical
#                       source-stability evidence).
#   unknown         -- no ruleset_id, and no evidence strong enough to
#                       recover one (e.g. a pre-v0.3 artifact, or a shape
#                       that predates the proven-stable window).
#   not_applicable  -- the artifact was never a candidate for this identity
#                       at all (a Redcode/pMARS result never executes under
#                       Bytefray Ruleset v1).
RulesetConfidence = Literal["recorded", "recovered", "unknown", "not_applicable"]


@dataclass(frozen=True)
class RulesetProvenance:
    """A Ruleset identity attribution together with its confidence."""

    value: str | None
    confidence: RulesetConfidence


__all__ = [
    "BYTEFRAY_RULESET_ID",
    "BYTEFRAY_RULESET_V4_ALPHA1_ID",
    "RulesetConfidence",
    "RulesetProvenance",
    "normalize_ruleset_id",
]
