"""Bytefray gameplay Ruleset identity.

A single, first-class compatibility axis for Bytefray *gameplay* semantics,
deliberately kept separate from the schema/version identifiers that
describe how those semantics are persisted, exercised, or measured. See
``docs/RULES.md`` for the full Ruleset v1 contract this identifies and
``docs/COMPATIBILITY.md`` for how it relates to the other compatibility
axes (Agent API version, artifact schema versions, evaluation methodology
fields, agent revision identity).
"""

from __future__ import annotations

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


__all__ = ["BYTEFRAY_RULESET_ID"]
