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
import queue
import re
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from itertools import permutations as _permutations
from itertools import zip_longest
from pathlib import Path
from typing import Any

from battle_engine.agent_api import (
    LOCAL_SOURCE_FINGERPRINT_VERSION,
    AgentValidationError,
    local_source_fingerprint,
)
from battle_engine.agent_revisions import (
    RevisionArchivalResult,
    agent_revisions_root,
    archive_agent_revision_from_walk,
    local_python_subset_fingerprint,
    walk_agent_files,
)
from battle_engine.agent_test import (
    DEFAULT_TICKS,
    OPPONENT_SLOT,
    TESTED_AGENT_SLOT,
    AgentTestError,
    GroupEntrantSpec,
    GroupInitializationFailureOutcome,
    InitializationFailureOutcome,
    test_agent,
    test_agents,
)
from battle_engine.agents import AgentSpec, resolve_agent
from battle_engine.config import Config
from battle_engine.evaluation_presets import (
    ORIENTATION_BOTH as _PRESET_ORIENTATION_BOTH,
)
from battle_engine.evaluation_presets import (
    EvaluationPreset,
    EvaluationPresetError,
    load_preset,
)
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchResult,
    canonical_match_id,
)
from battle_engine.paths import contained_path, get_data_root
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
from battle_engine.rules import BYTEFRAY_RULESET_ID, normalize_ruleset_id
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID

SCHEMA_NAME = "bytefray.evaluation"
SCHEMA_VERSION = 4
# Bumped 2 -> 3: each planned_identities entry (candidate/baseline/each
# opponent) gains "agent_revision_id"/"agent_revision_error"
# (docs/specs/agent_revision.md Sec 5) -- an additive wire-shape change,
# versioned explicitly per AGENTS.md rather than silently changing what a
# reader can expect to find, even though it does NOT change evaluation_id's
# hash payload (see IDENTITY_VERSION below, deliberately left unchanged).
# A v2 evaluation.json is not resumable under this schema_version (Sec 5.3
# of the spec -- the same "old artifact needs a fresh evaluation" pattern
# v1 -> v2 already established); it remains fully readable via
# evaluation_history's own adapters, never mutated.
#
# Bumped 2 -> 3 (identity): agent_identity() gained "local_source_
# fingerprint" (H3), which changes the identity dict's shape/hash for every
# existing candidate/baseline/opponent -- an identity-affecting change,
# versioned explicitly per AGENTS.md rather than silently changing
# evaluation_id's wire meaning in place. agent_revision_id (above) is
# deliberately NOT folded into this hash -- see
# docs/specs/agent_revision.md Sec 1.4 -- so IDENTITY_VERSION does not bump
# again here.
#
# Bumped 3 -> 4 (schema and identity together, v0.9 Phase 6, per
# runs/research_v0.9/PHASE5_EVALUATION_METHODOLOGY_SPEC.md Sec J.1/AA.4.8):
# each cell gains "orientation"/"orientation_index" (schema-additive, and
# identity-affecting because orientation enters schedule_id/
# condition_fingerprint -- two cells differing only by orientation must
# never collide); the evaluation level gains "orientation_mode" and
# "arena_alignment_mode" (both enter _evaluation_id's payload and are
# persisted as top-level sibling fields, following the exact
# EVALUATION_RULES_COMPATIBILITY_ID sibling-key pattern below). None of
# this changes EVALUATION_RULES_COMPATIBILITY_ID itself -- it is a
# methodology/coverage change, never a gameplay-rules change.
IDENTITY_VERSION = 4

# Narrowly scoped compatibility identifier surfaced at evaluation scope, in
# the historical wire field name ``rules_compatibility_id``
# (``bytefray.evaluation``'s per-evaluation and per-execution-context
# payloads). Preserved under its original name and comparison behavior for
# compatibility with existing artifacts and tests -- its *value* now
# changes to track ``BYTEFRAY_RULESET_ID`` (still "bytefray-rules-1" today,
# since Ruleset v1 is what "evaluation-rules-1" always meant; see the
# historical note below). As of v0.10 Phase 2 this is a derived alias of
# ``battle_engine.rules.BYTEFRAY_RULESET_ID``, the first-class gameplay
# Ruleset identity (see docs/RULES.md), rather than an independently
# maintained second rules counter -- a gameplay-semantic change now
# requires exactly one Ruleset bump, not a Ruleset bump plus a separate
# evaluation-rules bump. Deliberately still separate from
# ``ProjectInfo.version``. See docs/COMPATIBILITY.md for the full
# compatibility-axis table.
#
# Historical note: for the whole period this value has existed as the
# literal string ``"evaluation-rules-1"`` (schema v1 onward), it has always
# meant exactly the gameplay semantics ``bytefray-rules-1`` now names
# explicitly -- see docs/RULES.md's "Historical relationship to
# evaluation-rules-1" section for the supporting git-history evidence.
# Evaluation artifacts persisted before this alias existed still literally
# contain the string ``"evaluation-rules-1"``, not ``"bytefray-rules-1"``;
# readers must not pretend otherwise. See docs/specs/evaluation_history.md
# Sec 4 for the original field design.
EVALUATION_RULES_COMPATIBILITY_ID = BYTEFRAY_RULESET_ID

# v0.9's only supported arena-alignment methodology (Phase 5 spec Sec AA):
# every cell in every evaluation places both entrants at the same
# untranslated arena alignment. This is evaluation-level methodology
# provenance, not a gameplay rule -- it never causes address translation
# and never changes EVALUATION_RULES_COMPATIBILITY_ID. Threaded through
# identity/comparison the same sibling-key way
# EVALUATION_RULES_COMPATIBILITY_ID already is (Sec AA.3/AA.4).
EVALUATION_ARENA_ALIGNMENT_MODE = "fixed"

# v2.0.0-beta2 Phase 1 (docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md): the
# Ruleset-v2 1v1 evaluation methodology's own arena-alignment identifier --
# a sibling value to EVALUATION_ARENA_ALIGNMENT_MODE above, never a
# replacement for it. Selected only when a request's --ruleset resolves to
# BYTEFRAY_RULESET_V2_ID; every v1 evaluation (omitted --ruleset, or
# --ruleset bytefray-rules-1) keeps EVALUATION_ARENA_ALIGNMENT_MODE ==
# "fixed" exactly as before -- see resolve_evaluation_methodology.
EVALUATION_ARENA_ALIGNMENT_MODE_V2_STANDARD = "ruleset_v2_standard_placements"

# v2.0.0-beta2 Phase 2: the multi-entrant ("group") v2 methodology's own
# arena-alignment identifier -- a third sibling value. Deliberately
# distinct from EVALUATION_ARENA_ALIGNMENT_MODE_V2_STANDARD above (never
# reused): a 1v1 evaluation and a group evaluation must never be presented
# as comparable merely because a mode label happened to match --
# evaluation_history.comparison's _arena_alignment_id gate already fails
# closed on any string difference, generalizing correctly for free.
EVALUATION_ARENA_ALIGNMENT_MODE_V2_GROUP_STANDARD = "ruleset_v2_group_standard_layouts"

# A second, additive identity/schema recipe used only by an evaluation whose
# resolved Ruleset is BYTEFRAY_RULESET_V2_ID (Sec F/G of the design doc).
# IDENTITY_VERSION/SCHEMA_VERSION above are never bumped for this -- every
# v1 evaluation (omitted or explicit bytefray-rules-1) keeps hashing and
# persisting under identity_version/schema_version 4 exactly as before, so
# no historical evaluation_id, schedule_id, or artifact schema_version is
# affected by these constants merely existing. A v2 evaluation has no
# historical artifact to stay compatible with -- this module's evaluation
# methodology has never supported Ruleset v2 before this phase.
IDENTITY_VERSION_V2 = 5
SCHEMA_VERSION_V2 = 5

# v2.0.0-beta2 Phase 2 (docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md):
# a THIRD, additive identity/schema recipe, used only by a multi-entrant
# ("group") v2 evaluation. Every 1v1 v2 evaluation (Phase 1's own
# capability) keeps hashing/persisting under IDENTITY_VERSION_V2/
# SCHEMA_VERSION_V2 (5) exactly as Phase 1 left it -- group mode introduces
# genuinely new identity-affecting fields (roster, seat assignment, N-seat
# layout) that a pure 1v1 v2 cell never has, mirroring exactly how Phase 1
# itself justified bumping past v1's 4 rather than reusing it. No v6
# artifact has ever existed before this phase, so there is no historical
# compatibility burden for this version.
IDENTITY_VERSION_V2_GROUP = 6
SCHEMA_VERSION_V2_GROUP = 6

# Ruleset-v2's standard 1v1 seed methodology (docs/V2_0_BETA2_PHASE1_
# EVALUATION_METHODOLOGY.md Sec D): alpha.8/alpha.10 proved single-seed
# evaluation insufficient for any RNG-consuming agent (Core Tracker's win
# rate against expansion varied 25%-75% across five seeds at otherwise
# identical conditions). Used only as permanent-v2's *default* when the CLI
# is not given an explicit --seeds/--seed-range and no --preset supplies
# seeds -- an explicit seed selection always overrides it.
STANDARD_V2_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)

CANDIDATE = "candidate"
BASELINE = "baseline"

# Entrant orientation (Phase 5 spec Sec H/I): which of the two match-
# defining agents occupies the always-first-acting physical slot for one
# cell. Named constants, mirroring CANDIDATE/BASELINE above, rather than a
# runtime string validator -- orientation values are always constructed
# internally by build_matrix from this fixed pair, never accepted as
# free-text external/CLI input (the CLI only exposes the boolean
# --single-orientation), so this is the existing project convention for a
# closed internal string enum.
ORIENTATION_CANDIDATE_FIRST = "candidate_first"
ORIENTATION_OPPONENT_FIRST = "opponent_first"
ORIENTATION_MODE_BOTH = "both"
ORIENTATION_MODE_CANDIDATE_FIRST_ONLY = "candidate_first_only"

_OUTCOME_RANK = {"loss": 0, "tie": 1, "win": 2}
_REAL_OUTCOMES = frozenset(_OUTCOME_RANK)
_TERMINAL_RESUME_STATUSES = ("completed", "failed", "corrupted", "drift_detected")


def _utc_now_iso() -> str:
    """Precise UTC timestamp: microsecond precision, ``Z`` suffix (Sec 5)."""

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def physical_slots_for_orientation(orientation: str) -> tuple[str, str]:
    """The physical ``(subject_slot, opponent_slot)`` a cell's orientation executes in.

    ``candidate_first`` (today's only historical behavior): the subject
    occupies the always-first-acting slot, exactly as every cell ever run
    before Phase 6. ``opponent_first``: the physical roles are swapped --
    the opponent occupies the first-acting slot, the subject the second --
    while every *stored* evaluation field stays expressed from the
    evaluation-role (subject/opponent) perspective, never the physical
    slot. See Phase 5 spec Sec H.1/Sec 12.

    Every place that reads real match-execution evidence keyed by physical
    slot (result/envelope score-and-outcome mapping, post-execution
    identity drift, initialization-failure classification, resumed-cell
    verification, and ``evaluation_history.verification``'s deep-verify
    path) must resolve slots through this one function rather than
    hardcoding ``TESTED_AGENT_SLOT``/``OPPONENT_SLOT`` as "subject"/
    "opponent" directly -- that hardcoding is exactly what made every
    cell ever run give the candidate role a first-mover advantage with no
    way to test the reverse (Phase 5 spec Sec C.6/C.7/B.6).
    """

    if orientation == ORIENTATION_OPPONENT_FIRST:
        return OPPONENT_SLOT, TESTED_AGENT_SLOT
    return TESTED_AGENT_SLOT, OPPONENT_SLOT


@dataclass(frozen=True)
class EvaluationPlacement:
    """One deterministic pair of Python-entrant start addresses for a 1v1 cell.

    ``placement_id`` is a short, human-documentable label; ``subject_start``/
    ``opponent_start`` are absolute arena addresses (before ``% arena_size``
    wraparound, matching ``MatchEntrant.python``'s own convention) expressed
    from the *evaluation-role* perspective (subject/opponent) -- independent
    of which physical slot or scheduler order actually executes each role
    for a given cell. Named to mirror ``EvaluationCell.subject_id``/
    ``opponent_id`` (not ``candidate_start``/``opponent_start``): a
    baseline cell's "subject" is the baseline, not the candidate, and
    placement must describe *where the subject starts* regardless of role.
    Deliberately 1v1-scoped (two named fields, not a generic seat map) --
    see ``docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md``'s multi-entrant
    extension seam for how this generalizes to N seats in Beta2 Phase 2.
    """

    placement_id: str
    subject_start: int
    opponent_start: int


def standard_placements(arena_size: int | None = None) -> tuple[EvaluationPlacement, ...]:
    """The standard Ruleset-v2 1v1 placement set (design doc Sec Placement).

    Three deterministic conditions, derived mechanically as fractions of
    ``arena_size`` -- never hand-picked coordinates, never dependent on any
    specific opponent's scan geometry (alpha.7's COLD/HOT fixtures were
    calibrated to one superseded attacker and are deliberately not reused
    here as permanent methodology; see the design doc):

    * ``opposed`` -- maximal, half-arena separation, phase 0. The control
      condition: as far apart as the arena allows.
    * ``quarter`` -- a closer, non-opposed quarter-arena separation, phase
      0. Proves a conclusion is not an artifact of exact-half separation.
    * ``opposed-shifted`` -- the same half-arena separation as ``opposed``,
      phase-shifted by a quarter turn. Proves an ``opposed`` conclusion is
      not an artifact of starting exactly at address 0.

    Non-overlapping by construction: every gap here is a quarter or half of
    ``arena_size``, vastly larger than ``CORE_SIZE`` (8). Never random --
    every coordinate is a pure function of ``arena_size``.
    """

    size = arena_size if arena_size is not None else Config().arena_size
    half = size // 2
    quarter = size // 4
    return (
        EvaluationPlacement("opposed", subject_start=0, opponent_start=half),
        EvaluationPlacement("quarter", subject_start=0, opponent_start=quarter),
        EvaluationPlacement(
            "opposed-shifted",
            subject_start=quarter,
            opponent_start=(quarter + half) % size,
        ),
    )


# ---------------------------------------------------------------------------
# Multi-entrant ("group") domain model (v2.0.0-beta2 Phase 2)
# ---------------------------------------------------------------------------
#
# Deliberately a separate model from EvaluationPlacement/standard_placements
# above, not a generalization written in place of them: Phase 1's 1v1
# identity path must stay untouched, byte-for-byte, forever (see
# docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md's "why two placement
# models" note for the worked proof that standard_layouts(2, ...) below
# reproduces standard_placements()'s exact three 1v1 conditions -- evidence
# this is a genuine generalization, not a coincidence, without ever routing
# 1v1 cells through this new code).


def seat_label(index: int) -> str:
    """The seat identity for position ``index`` (0-based): "A", "B", "C", ...

    Mirrors ``agent_test.TESTED_AGENT_SLOT``/``OPPONENT_SLOT``'s existing
    ``"A"``/``"B"`` convention exactly -- a seat *is* the entrant's
    ``MatchEntrant.agent_id`` for that position, and (per
    ``battle_engine.scheduler.run_sequential_quota``, which executes states
    in exactly the order it is given) also its scheduler/execution-order
    position. There is no separate "execution order" axis to track.
    """

    if not (0 <= index < 26):
        raise ValueError(f"seat_label supports at most 26 seats, got index {index}")
    return chr(ord("A") + index)


@dataclass(frozen=True)
class EvaluationSeatAssignment:
    """One deterministic assignment of a roster's entrants to seats.

    ``seat_agent_ids`` is ordered by seat (index 0 = seat "A", index 1 =
    seat "B", ...) -- the agent_id occupying each seat. This is the
    identity-bearing representation of "permutation": two seat assignments
    are the same experimental condition iff this tuple is equal, which
    correctly treats a roster containing a duplicate agent id (the same
    agent occupying two seats -- self-play) as producing fewer distinct
    conditions than a fully-distinct roster's ``N!`` permutations would,
    since two seats holding the identical agent are truly indistinguishable
    for identity purposes.
    """

    seat_agent_ids: tuple[str, ...]


def enumerate_seat_assignments(roster: Sequence[str]) -> tuple[EvaluationSeatAssignment, ...]:
    """Every distinct seat assignment for ``roster`` (Phase 2: exhaustive
    permutation policy only).

    Deduplicates by the resulting ``seat_agent_ids`` tuple, not by the
    underlying index permutation, so a roster with a repeated agent id
    yields fewer than ``len(roster)!`` assignments (see
    ``EvaluationSeatAssignment``). ``itertools.permutations`` enumerates in
    deterministic lexicographic index order, so generation order is
    reproducible run to run. Future scheduling policies (rotation-only,
    balanced subsets, an explicit preset-driven policy) can live as sibling
    functions with this identical return shape without changing this
    function's own contract -- see the design doc's "permutation model"
    section for why exhaustive-only is the right Phase 2 scope.
    """

    seen: dict[tuple[str, ...], None] = {}
    for perm in _permutations(range(len(roster))):
        seats = tuple(roster[i] for i in perm)
        seen.setdefault(seats, None)
    return tuple(EvaluationSeatAssignment(seat_agent_ids=seats) for seats in seen)


@dataclass(frozen=True)
class EvaluationLayout:
    """One deterministic set of per-seat start addresses for an N-entrant cell.

    ``seat_starts[i]`` is the start address for seat ``i`` (``seat_label(i)``),
    independent of which roster entrant occupies that seat this cell --
    layout and seat assignment are orthogonal identity dimensions, exactly
    as ``EvaluationPlacement``/orientation are for 1v1 (Phase 1J's
    "orientation vs. placement" separation, generalized).
    """

    layout_id: str
    seat_starts: tuple[int, ...]


def standard_layouts(entrant_count: int, arena_size: int | None = None) -> tuple[EvaluationLayout, ...]:
    """The standard Ruleset-v2 multi-entrant layout set for ``entrant_count`` seats.

    Three deterministic conditions, mechanically derived as fractions of
    ``arena_size`` -- the direct N-seat generalization of
    ``standard_placements()``'s own three 1v1 conditions:

    * ``spread`` -- seats evenly spaced starting at address 0 (the N-seat
      generalization of ``opposed``'s maximal, phase-0 separation).
    * ``spread-shifted`` -- the same even spacing, phase-shifted by half a
      seat gap (generalizes ``opposed-shifted``).
    * ``close`` -- a tighter, non-maximal spacing (generalizes ``quarter``).

    For ``entrant_count=2`` this formula reproduces ``standard_placements()``'s
    exact three placements (``opposed``/``opposed-shifted``/``quarter``) --
    verified by ``test_standard_layouts_reproduce_1v1_placements_at_n_equals_2``
    -- but this function is never called for 1v1 cells; only group-mode
    cells (``entrant_count >= 2`` where 2 is reachable only via an explicit
    2-entrant group, not ordinary 1v1) use it, so Phase 1's frozen
    ``standard_placements()`` path is never touched by this addition.

    Requires ``entrant_count >= 2``. Non-overlapping by construction for any
    arena size where ``arena_size // (2 * entrant_count) > CORE_SIZE``, true
    for every arena size this project documents as supported.
    """

    if entrant_count < 2:
        raise ValueError(f"standard_layouts requires at least 2 entrants, got {entrant_count}")
    size = arena_size if arena_size is not None else Config().arena_size
    gap = size // entrant_count
    half_gap = gap // 2
    return (
        EvaluationLayout("spread", tuple((i * gap) % size for i in range(entrant_count))),
        EvaluationLayout(
            "spread-shifted", tuple((i * gap + half_gap) % size for i in range(entrant_count))
        ),
        EvaluationLayout("close", tuple((i * half_gap) % size for i in range(entrant_count))),
    )


def resolve_evaluation_ruleset_id(ruleset_id: str | None) -> str:
    """The ``rules_compatibility_id`` a request's optional ``--ruleset`` resolves to.

    ``None`` (omitted) and the explicit v1 identity resolve to the exact
    same historical value evaluation has always used -- Phase 1H's
    "omitted" and "v1" cases are one and the same resolved methodology, byte-
    identical in every downstream hash payload (see ``EvaluationRequest.
    resolved_rules_compatibility_id``).
    """

    if ruleset_id is None:
        return EVALUATION_RULES_COMPATIBILITY_ID
    return normalize_ruleset_id(ruleset_id)


def is_ruleset_v2_methodology(rules_compatibility_id: str) -> bool:
    """Whether a resolved rules-compatibility id selects the v2 evaluation methodology.

    Methodology is tied 1:1 to Ruleset identity (design doc Sec Ruleset
    selection): only ``BYTEFRAY_RULESET_V2_ID`` gets balanced placement/
    standard-seed/capture-metric methodology. Every historical alpha
    Ruleset identity a result/replay artifact might still reference is
    deliberately excluded -- product-facing evaluation methodology never
    advertises an alpha Ruleset identity.
    """

    return rules_compatibility_id == BYTEFRAY_RULESET_V2_ID


def resolved_arena_alignment_mode(is_v2_methodology: bool, group: bool = False) -> str:
    if is_v2_methodology and group:
        return EVALUATION_ARENA_ALIGNMENT_MODE_V2_GROUP_STANDARD
    return (
        EVALUATION_ARENA_ALIGNMENT_MODE_V2_STANDARD
        if is_v2_methodology
        else EVALUATION_ARENA_ALIGNMENT_MODE
    )


def resolved_identity_version(is_v2_methodology: bool, group: bool = False) -> int:
    if is_v2_methodology and group:
        return IDENTITY_VERSION_V2_GROUP
    return IDENTITY_VERSION_V2 if is_v2_methodology else IDENTITY_VERSION


def resolved_schema_version(is_v2_methodology: bool, group: bool = False) -> int:
    if is_v2_methodology and group:
        return SCHEMA_VERSION_V2_GROUP
    return SCHEMA_VERSION_V2 if is_v2_methodology else SCHEMA_VERSION


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
        # H3/B1(v0.7 closure pass): catches an imported local helper/nested
        # local package edit that source_sha256 alone (entry-point file
        # only) would miss. Cross-checked post-execution against the
        # executor's own recorded ``NativeAgentResult.metadata`` -- which
        # now carries a matching ``local_source_fingerprint`` computed by
        # the executor itself at load time (``python_runtime``/
        # ``supervised_runtime``), not a second independent disk read by
        # this module -- see ``_ACTUAL_IDENTITY_FIELDS``/
        # ``_post_execution_identity_drift``.
        "local_source_fingerprint": local_source_fingerprint(spec.dir),
    }


@dataclass(frozen=True)
class EffectiveConditions:
    """Readable effective execution conditions, constant across one evaluation.

    ``agent_test.py`` gives no per-cell override surface for anything but
    seed/ticks (docs/specs/agent_evaluation.md Sec 2 finding 4), so every
    field below is the same for every cell in a matrix -- but it is recorded
    explicitly rather than assumed, per docs/specs/evaluation_history.md
    Sec 3 ("avoid duplicating mutable defaults without resolving them
    first").
    """

    tick_limit: int
    arena_size: int
    action_budget: int
    win_mode: str
    weights: dict[str, float | int]
    agent_api_version: int
    subject_slot: str = TESTED_AGENT_SLOT
    opponent_slot: str = OPPONENT_SLOT
    entrant_order: tuple[str, str] = (TESTED_AGENT_SLOT, OPPONENT_SLOT)
    runtime_kind: str = "python"
    supervision: str = "unsupervised"
    tracing: str = "untraced"


def effective_conditions_for(ticks: int, agent_api_version: int) -> EffectiveConditions:
    defaults = Config()
    return EffectiveConditions(
        tick_limit=ticks,
        arena_size=defaults.arena_size,
        action_budget=defaults.instr_per_tick,
        win_mode=defaults.win_mode,
        weights=asdict(defaults.weights),
        agent_api_version=agent_api_version,
    )


@dataclass(frozen=True)
class ExecutionContext:
    """One observed runtime environment a v2 cell may be attributable to.

    docs/specs/evaluation_history.md Sec 6: every newly executed cell must be
    attributable to an entry in ``execution_contexts``; a resumed/trusted
    cell keeps whatever context it was originally recorded under.
    """

    context_id: str
    bytefray_version: str
    agent_api_version: int
    python_version: str
    result_schema_version: int
    replay_schema_version: int
    rules_compatibility_id: str
    first_used_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def current_execution_context(rules_compatibility_id: str) -> ExecutionContext:
    project = get_project_info()
    payload: dict[str, Any] = {
        "bytefray_version": project.version,
        "agent_api_version": project.agent_api_version,
        "python_version": project.python_version,
        "result_schema_version": project.result_schema_version,
        "replay_schema_version": project.replay_schema_version,
        "rules_compatibility_id": rules_compatibility_id,
    }
    context_id = stable_id("evaluation-context", payload)
    return ExecutionContext(
        context_id=context_id,
        bytefray_version=project.version,
        agent_api_version=project.agent_api_version,
        python_version=project.python_version,
        result_schema_version=project.result_schema_version,
        replay_schema_version=project.replay_schema_version,
        rules_compatibility_id=rules_compatibility_id,
    )


@dataclass(frozen=True)
class CellExecutionResult:
    """``_execute_cell``'s return value (v1.6 Phase 2).

    ``execution_context`` is ``None`` only for the pre-execution-drift early
    return (no execution was attempted, so there is nothing to attribute to
    an environment) -- every other path sets it, mirroring exactly which
    paths called the old ``record_context_usage()`` closure. Replacing that
    closure (a coordinator-local mutable capture, unsafe to call from a
    worker process) with this explicit return value is what lets
    ``_execute_cell`` run unchanged inside a worker subprocess: the worker
    reports the context it observed, and only the coordinator (never a
    worker) decides whether it is new and appends it -- see
    ``_register_execution_context``.
    """

    cell: EvaluationCell
    execution_context: ExecutionContext | None = None


def _register_execution_context(
    context: ExecutionContext,
    execution_contexts: list[dict[str, Any]],
    known_context_ids: set[str],
) -> None:
    """Coordinator-owned dedup/append, extracted from the old ``record_context_
    usage`` closure so both the serial and parallel dispatch paths call the
    exact same logic -- never a worker, and never duplicated.
    """

    if context.context_id in known_context_ids:
        return
    execution_contexts.append({**context.to_dict(), "first_used_at": _utc_now_iso()})
    known_context_ids.add(context.context_id)


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
    orientation: str,
    ruleset_id: str,
    subject_start: int,
    opponent_start: int,
) -> str:
    """Recompute the ``match_id`` a fresh cell run would produce.

    Mirrors ``agent_test._test_agent``'s own ``MatchRequest`` construction
    exactly (same ``Config(seed=...)``, same physical A/B slot entrants,
    ``orientation``-mapped via :func:`physical_slots_for_orientation`) so a
    *resumed* cell's recorded ``match_id`` can be verified against what this
    exact (subject, opponent, seed, orientation) combination would compute
    today -- catching a source-content change the way
    ``tournament_service``'s resume verification already does
    (docs/specs/agent_evaluation.md Sec 14).

    ``canonical_match_id`` reads ``spec.source_path`` from disk at call
    time (see ``match_service.canonical_match_id``), so this helper is only
    safe to use against *live, freshly re-resolved* specs (resume, where
    ``specs`` is this run's own current resolution and is already
    consistent with this run's freshly computed ``evaluation_id``). It must
    never be used to verify a cell just executed in *this* process against
    a frozen preflight snapshot -- a second live read after the fact can
    silently observe the same (already-drifted) content the executor itself
    just read, making the comparison pass despite drift. See
    ``_post_execution_identity_drift`` for that check instead.

    Phase 7 correctness fix: ``canonical_match_id`` is sensitive to the
    *positional order* of ``request.entrants`` -- both each Python entrant's
    derived seed (keyed by ``enumerate()`` position, not the "A"/"B" slot
    label) and the recorded ``entrant_order`` list depend on it
    (``match_service.canonical_match_id``). ``_test_agent`` always
    constructs its entrants tuple as ``(TESTED_AGENT_SLOT-entrant,
    OPPONENT_SLOT-entrant)`` positionally -- slot A's entrant always comes
    first in the tuple, slot B's always second, regardless of which logical
    role (subject/opponent) occupies which slot. This helper must build the
    identical positional order (always ``TESTED_AGENT_SLOT`` first,
    ``OPPONENT_SLOT`` second), with only *which agent* fills each slot
    varying by orientation -- not a "subject first, opponent second" order,
    which silently recomputes a different id than a real ``opponent_first``
    execution actually produced. Previously this caught every
    already-completed ``opponent_first`` cell in a false
    ``resumed_result_mismatch`` on every subsequent resume, even when
    nothing about the match had changed.
    """

    if orientation == ORIENTATION_OPPONENT_FIRST:
        slot_a_agent_id, slot_a_spec, slot_a_start = opponent_id, opponent_spec, opponent_start
        slot_b_agent_id, slot_b_spec, slot_b_start = subject_id, subject_spec, subject_start
    else:
        slot_a_agent_id, slot_a_spec, slot_a_start = subject_id, subject_spec, subject_start
        slot_b_agent_id, slot_b_spec, slot_b_start = opponent_id, opponent_spec, opponent_start
    request = MatchRequest(
        config=Config(seed=seed),
        entrants=(
            MatchEntrant.python(TESTED_AGENT_SLOT, slot_a_agent_id, slot_a_start, slot_a_spec),
            MatchEntrant.python(OPPONENT_SLOT, slot_b_agent_id, slot_b_start, slot_b_spec),
        ),
        max_ticks=ticks,
        replay_path=Path("."),
        ruleset_id=ruleset_id,
    )
    return canonical_match_id(request)


def _expected_group_cell_match_id(
    specs: Mapping[str, AgentSpec],
    seat_agent_ids: Sequence[str],
    seat_starts: Sequence[int],
    seed: int,
    ticks: int,
    ruleset_id: str,
) -> str:
    """The multi-entrant generalization of :func:`_expected_cell_match_id`.

    Mirrors ``agent_test._test_agents``'s own ``MatchRequest`` construction
    exactly: entrants in seat order (``seat_agent_ids[i]`` at
    ``seat_label(i)``), each at its own ``seat_starts[i]``. See
    ``_expected_cell_match_id``'s own docstring for why entrant *positional*
    order (not just each entrant's own identity) is load-bearing for
    ``canonical_match_id`` and must be reproduced exactly.
    """

    request = MatchRequest(
        config=Config(seed=seed),
        entrants=tuple(
            MatchEntrant.python(seat_label(index), agent_id, start, specs[agent_id])
            for index, (agent_id, start) in enumerate(zip(seat_agent_ids, seat_starts, strict=True))
        ),
        max_ticks=ticks,
        replay_path=Path("."),
        ruleset_id=ruleset_id,
    )
    return canonical_match_id(request)


# Identity fields recorded both in a frozen ``agent_identity()`` snapshot and
# in a real match's per-entrant ``NativeAgentResult.metadata`` (Python kind)
# -- the intersection usable to cross-check "what the executor actually
# loaded" against "what was planned" without re-reading disk a second time.
# ``entry_point``/``local_source_fingerprint`` (v0.7 closure pass, B1): the
# executor (``python_runtime``/``supervised_runtime``) now records both --
# the entry point string it actually resolved and imported from, and a
# fingerprint of every local ``.py`` file under the agent directory it
# actually loaded from, computed once at load time and never re-derived --
# so a same-file factory retarget (``agent.yaml`` entry point changed but
# the source file's own bytes untouched, which ``source_sha256`` alone
# cannot see) or a helper-file edit landing after this cell's pre-execution
# drift check but before/during the executor's own load is still caught
# here, against genuine executor evidence rather than a second live re-read.
_ACTUAL_IDENTITY_FIELDS = (
    "source_sha256",
    "api_version",
    "agent_version",
    "entry_point",
    "local_source_fingerprint",
)

# Lazy-import closure pass: the executor also records a *second*,
# independently computed ``local_source_fingerprint_final`` -- over the
# identical deterministic scope as ``local_source_fingerprint`` above, but
# taken only after the whole match has finished (every ``reset()``/
# ``act()`` call already happened). A local helper imported lazily from
# inside ``reset()``/``act()`` (rather than at module load time) can change
# the agent directory's contents after the load-time fingerprint was
# captured but before that lazy import actually executes; the load-time
# fingerprint alone cannot see this. Compared against the same *planned*
# ``local_source_fingerprint`` value as the load-time field -- there is
# only one planned value; both executor-recorded readings must agree with
# it (see ``_post_execution_identity_drift``'s three-way invariant).
_FINAL_ONLY_IDENTITY_FIELDS = (("local_source_fingerprint", "local_source_fingerprint_final"),)


def _post_execution_identity_drift(
    cell: EvaluationCell,
    match_result: NativeMatchResult,
    planned_identities: Mapping[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Cross-check the executor's own recorded entrant metadata against the frozen plan.

    Orientation-aware (Phase 5 spec Sec H.1): resolves which physical slot
    each role actually executed in via ``physical_slots_for_orientation``,
    rather than assuming subject=A/opponent=B -- for an ``opponent_first``
    cell the subject really executed in slot B and the opponent in slot A,
    and checking the wrong slot would silently compare each side's frozen
    identity against the other side's executed metadata.

    ``NativeAgentResult.metadata`` for a Python entrant is populated by
    ``python_runtime.PythonEntrantController``/``match_service.
    _build_python_result`` from the exact source the executor just loaded
    and ran -- it is not a second independent disk read performed by this
    module after the fact. Comparing it against ``planned_identities``
    (frozen once at preflight, before any cell executed) is therefore the
    strongest available check that the identity actually used for
    acceptance corresponds to what the executor actually loaded (Sec 7
    finding), and -- unlike recomputing ``canonical_match_id`` from a live
    ``AgentSpec.source_path`` after execution -- cannot be silently
    defeated by a source edit that is already in place by the time this
    check runs.

    The required invariant (v0.7 closure pass, lazy-import fix) is now
    three-way, not two-way::

        initial executor fingerprint == frozen planned fingerprint == final executor fingerprint

    i.e. both ``local_source_fingerprint`` (captured at load time, before
    ``reset()``/``act()`` ever run) *and* ``local_source_fingerprint_final``
    (captured after the match finishes, so every lazy import a running
    agent performed has already happened) must each independently equal
    the frozen plan's single recorded value. A local helper imported
    lazily from inside ``reset()``/``act()`` -- rather than at module load
    time -- can change between those two executor-recorded readings; the
    load-time fingerprint alone cannot see that, since the lazy import
    that actually reads the changed file has not happened yet when it is
    captured.

    A residual TOCTOU remains and is documented rather than hidden: inside
    ``python_runtime.PythonEntrantController.__init__`` (and its supervised
    counterpart), the agent module is loaded/executed first and its
    ``source_sha256``/``local_source_fingerprint`` are each computed by a
    *separate* subsequent read (see ``PythonEntrantState.source_digest``/
    ``PythonEntrantState.local_source_fingerprint``); symmetrically, the
    final fingerprint is computed once, in a separate step, after the tick
    loop's last actual local-file read. An edit that lands and is then
    reverted before the nearest such read captures it -- at either end --
    is not detectable from outside that call. This module neither
    introduces nor can close that inner window; it only guarantees that
    whatever the executor itself recorded as having run, at both points,
    is cross-checked against the frozen plan.
    """

    subject_slot, opponent_slot = physical_slots_for_orientation(cell.orientation)
    for role, agent_id, slot in (
        (cell.subject_role, cell.subject_id, subject_slot),
        ("opponent", cell.opponent_id, opponent_slot),
    ):
        planned = planned_identities.get(agent_id)
        if planned is None:
            continue
        agent_result = match_result.agents_by_id.get(slot)
        if agent_result is None:
            continue
        actual_metadata = agent_result.metadata
        mismatched = sorted(
            field
            for field in _ACTUAL_IDENTITY_FIELDS
            if planned.get(field) != actual_metadata.get(field)
        )
        mismatched.extend(
            actual_field
            for planned_field, actual_field in _FINAL_ONLY_IDENTITY_FIELDS
            if planned.get(planned_field) != actual_metadata.get(actual_field)
        )
        mismatched.sort()
        if mismatched:
            return {
                "error_code": "post_execution_identity_drift",
                "error_message": (
                    f"{role} {agent_id!r} executed identity does not match the "
                    f"frozen plan (fields: {', '.join(mismatched)}); agent source "
                    "or configuration changed during execution."
                )[:240],
            }
    return None


def _post_execution_identity_drift_group(
    cell: EvaluationCell,
    match_result: NativeMatchResult,
    planned_identities: Mapping[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """The multi-entrant (N seats) generalization of
    :func:`_post_execution_identity_drift` (v2.0.0-beta2 Phase 2).

    Seat *is* physical slot for a group cell (``seat_label(i)`` is
    literally the ``MatchEntrant.agent_id`` each seat executed as -- see
    ``EvaluationSeatAssignment``), so there is no orientation-style
    slot-resolution step here: seat index directly indexes both
    ``cell.seat_agent_ids`` and ``match_result.agents_by_id``.
    """

    for index, agent_id in enumerate(cell.seat_agent_ids):
        planned = planned_identities.get(agent_id)
        if planned is None:
            continue
        agent_result = match_result.agents_by_id.get(seat_label(index))
        if agent_result is None:
            continue
        actual_metadata = agent_result.metadata
        mismatched = sorted(
            field
            for field in _ACTUAL_IDENTITY_FIELDS
            if planned.get(field) != actual_metadata.get(field)
        )
        mismatched.extend(
            actual_field
            for planned_field, actual_field in _FINAL_ONLY_IDENTITY_FIELDS
            if planned.get(planned_field) != actual_metadata.get(actual_field)
        )
        mismatched.sort()
        if mismatched:
            return {
                "error_code": "post_execution_identity_drift",
                "error_message": (
                    f"seat {seat_label(index)} {agent_id!r} executed identity does not "
                    f"match the frozen plan (fields: {', '.join(mismatched)}); agent "
                    "source or configuration changed during execution."
                )[:240],
            }
    return None


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
    data_root: Path | None = None
    # v0.9 Phase 6 (Phase 5 spec Sec H.3/I.2): both entrant orientations run
    # by default -- a default that still only ran candidate_first would
    # reproduce the exact "misleading default methodology" trap the shipped
    # `adaptive` starter agent's own first-mover exploit (spec Sec B.6)
    # demonstrates is real. False restores exactly today's historical,
    # single-orientation (candidate_first-only) behavior and matrix size.
    both_orientations: bool = True
    # v1.6 Phase 2: bounded subprocess-worker parallelism across independent
    # EvaluationCells (docs/V1_6_PHASE2_PARALLEL_EVALUATION.md). Default 1 is
    # the serial-equivalent path -- deliberately conservative, matching this
    # module's existing default-conservatism precedent (--seeds). Never part
    # of _evaluation_id's hash payload (see _evaluation_id below): worker
    # count must never affect what an evaluation *means*, only how fast it
    # runs.
    workers: int = 1
    # v2.0.0-beta2 Phase 1: explicit Ruleset selection for `agents evaluate`,
    # mirroring `agent_test`'s own `--ruleset` precedent. `None` (the
    # default) and the explicit v1 identity both resolve to the exact
    # historical v1 evaluation methodology, byte-identical in every
    # downstream identity hash -- see `resolved_rules_compatibility_id`/
    # `resolve_evaluation_ruleset_id`. Only `BYTEFRAY_RULESET_V2_ID`
    # activates the balanced-placement/standard-seed/capture-metric v2
    # methodology.
    ruleset_id: str | None = None
    # v2.0.0-beta2 Phase 2: opt into multi-entrant ("group") methodology --
    # `candidate_id` plus every `opponent_ids` entry are fielded TOGETHER as
    # one N-entrant roster each cell, instead of Phase 1's pairwise "one
    # cell per opponent" matrix. Default False preserves every existing
    # evaluation's exact pairwise behavior, v1 and v2 1v1 alike, completely
    # unchanged. Requires v2 methodology (`is_v2_methodology`) -- validated
    # in `EvaluationService._validate`, never silently ignored.
    group: bool = False

    @property
    def orientation_mode(self) -> str:
        return ORIENTATION_MODE_BOTH if self.both_orientations else ORIENTATION_MODE_CANDIDATE_FIRST_ONLY

    @property
    def resolved_rules_compatibility_id(self) -> str:
        return resolve_evaluation_ruleset_id(self.ruleset_id)

    @property
    def is_v2_methodology(self) -> bool:
        return is_ruleset_v2_methodology(self.resolved_rules_compatibility_id)

    @property
    def roster_agent_ids(self) -> tuple[str, ...]:
        """The full multi-entrant roster (candidate + every opponent), in
        request order, preserving duplicates -- meaningful only when
        ``group`` is True. See ``canonical_roster`` for the identity form.
        """

        return (self.candidate_id, *self.opponent_ids)

    @property
    def canonical_roster(self) -> tuple[str, ...]:
        """The roster's canonical (sorted, order-independent) identity form.

        Roster *membership* is order-independent -- "Claimer+Core Defender
        +Reactive Core Defender" is the same roster regardless of which
        order the user listed them in; seat *assignment* (the ordered,
        permutation-bearing axis) is a separate identity dimension, carried
        per cell by ``EvaluationCell.seat_agent_ids``, never here. Sorting
        preserves duplicate agent ids correctly (a self-play roster's
        repeat count survives sorting).
        """

        return tuple(sorted(self.roster_agent_ids))


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
    # Duplicate occurrence coordinates (docs/specs/evaluation_history.md
    # Sec 8) -- distinct from schedule_id, survive candidate-source changes
    # across evaluations, and are what cross-evaluation alignment uses.
    opponent_index: int = -1
    seed_index: int = -1
    matrix_ordinal: int = 0
    condition_occurrence_index: int = 0
    # Execution provenance and comparison support (Sec 6, Sec 14).
    execution_context_id: str | None = None
    condition_fingerprint: str | None = None
    # v0.9 Phase 6 (Phase 5 spec Sec I.2): which evaluation-defining agent
    # occupies the always-first-acting physical slot for this specific
    # cell -- a matrix axis, structurally a sibling of seed/opponent_index,
    # never folded into EffectiveConditions (Sec I.1). Two cells differing
    # only by orientation must never collide in identity (Sec 9/W.1-2);
    # `orientation_index` (0 or 1) is the duplicate-occurrence-style
    # coordinate build_matrix assigns alongside it, mirroring
    # condition_occurrence_index's own role for repeated (opponent, seed)
    # tuples.
    orientation: str = ORIENTATION_CANDIDATE_FIRST
    orientation_index: int = 0
    # v2.0.0-beta2 Phase 1 (design doc Sec Placement/Sec Identity): which
    # deterministic start-address pair this cell executed under, and this
    # cell's own resolved Ruleset -- matrix axes, structurally siblings of
    # seed/orientation, mirroring orientation's own default-sentinel
    # pattern exactly. Every v1 cell (the overwhelming majority, forever)
    # gets the fixed historical sentinel values below; only a v2-methodology
    # cell (`rules_compatibility_id == BYTEFRAY_RULESET_V2_ID`) ever sets
    # `placement_id` to anything other than "fixed" or either start to a
    # nonzero address. `rules_compatibility_id` is stored per cell (not
    # read from a module constant at execution time) because `_execute_cell`
    # must stay a pure function of its own arguments (v1.6 Phase 2's worker-
    # purity invariant) -- see EvaluationService._execute_cell.
    rules_compatibility_id: str = EVALUATION_RULES_COMPATIBILITY_ID
    placement_id: str = "fixed"
    subject_start: int = 0
    opponent_start: int = 0
    placement_index: int = 0
    # v2.0.0-beta2 Phase 2 (design doc Sec Identity): multi-entrant
    # ("group") axes -- matrix-axis siblings of placement_id/orientation
    # above, mirroring their identical default-sentinel pattern. Every
    # non-group cell (every 1v1 cell ever scheduled, v1 or v2, forever)
    # gets the empty-tuple/empty-string sentinels below; only a
    # `request.group=True` cell ever populates them. `roster_agent_ids` is
    # the canonical (sorted) roster; `seat_agent_ids` is the ordered
    # per-seat assignment for this specific cell (also its scheduler/
    # execution order -- see `seat_label`); `layout_id`/`seat_starts`
    # mirror `placement_id`/(`subject_start`,`opponent_start`)'s role, for
    # N seats instead of 2. `opponent_id` is still populated for a group
    # cell (every OTHER roster agent id, canonically joined) but is
    # display/artifact-labeling only there -- never identity-bearing;
    # `seat_agent_ids`/`roster_agent_ids` are authoritative.
    roster_agent_ids: tuple[str, ...] = ()
    seat_agent_ids: tuple[str, ...] = ()
    layout_id: str = ""
    seat_starts: tuple[int, ...] = ()
    seat_assignment_index: int = 0
    layout_index: int = 0

    @property
    def is_group(self) -> bool:
        return bool(self.roster_agent_ids)

    @property
    def subject_seat(self) -> str | None:
        """The seat label the subject occupies in this group cell, or
        ``None`` for a non-group cell.

        If ``subject_id`` occupies more than one seat (self-play, a
        duplicate agent id in the roster), the first (lowest-index)
        occurrence is used, deterministically -- a documented Phase 2
        simplification for reporting the subject's own outcome; every
        seat's real result remains fully recoverable from this cell's own
        persisted ``result.json`` regardless.
        """

        if not self.is_group:
            return None
        try:
            index = self.seat_agent_ids.index(self.subject_id)
        except ValueError:
            return None
        return seat_label(index)

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
    # v0.9 Phase 6 (Phase 5 spec Sec K.2): which cells this aggregate
    # summarizes -- "all" (pooled across both orientations, today's only
    # view before Phase 6), "candidate_first", or "opponent_first". Never
    # averaged away: all three are always computed side by side (see
    # `all_subject_aggregates`) so a regression hidden by pooling (e.g.
    # candidate wins every candidate-first cell but loses every
    # opponent-first cell) stays visible without extra author effort.
    orientation_scope: str = "all"

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
    # A repeated (opponent_id, seed) pair produces multiple ComparisonEntry
    # rows (see compare_candidate_baseline below); these carry each row's
    # exact paired cell identity so a consumer (the Designer results dialog)
    # can resolve the specific duplicate a row was built from instead of
    # re-deriving it from (opponent_id, seed) alone, which -- absent this --
    # always resolves to the *first* matching duplicate regardless of which
    # row was actually selected.
    candidate_schedule_id: str | None = None
    baseline_schedule_id: str | None = None
    # v0.9 Phase 6 (Phase 5 spec Sec K.3): part of the grouping key now, so
    # it must be visible on the entry itself -- without it, a
    # both_orientations comparison would show two rows with an identical
    # "opponent=X seed=Y" header that are actually different orientation
    # pairs, with no way to tell them apart.
    orientation: str = ORIENTATION_CANDIDATE_FIRST
    # v2.0.0-beta2 Phase 1 (design doc Sec Compare/Sec Q): part of the
    # grouping key now, mirroring orientation immediately above -- without
    # it, a v2 both_orientations-and-placements comparison could pair a
    # candidate's "opposed" cell against a baseline's "quarter" cell for
    # the "same" nominal (opponent, seed, orientation), silently
    # attributing a placement effect to a candidate/baseline difference
    # that isn't real. Always "fixed" for v1 comparisons.
    placement_id: str = "fixed"


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

    @property
    def drift_cells(self) -> tuple[EvaluationCell, ...]:
        return tuple(cell for cell in self.cells if cell.status == "drift_detected")


def _safe_path_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "entrant"


def build_matrix(
    request: EvaluationRequest,
    evaluation_id: str,
    specs: Mapping[str, AgentSpec] | None = None,
    conditions_fingerprint: str | None = None,
    rules_compatibility_id: str | None = None,
    arena_alignment_mode: str | None = None,
) -> tuple[EvaluationCell, ...]:
    """Build the deterministic subject x opponent x seed x placement x orientation matrix.

    Iteration order is candidate, then baseline (if present); opponents
    and seeds in exact request order, never re-sorted or deduplicated
    (docs/specs/agent_evaluation.md Sec 7); placement (v2.0.0-beta2 Phase 1)
    nests inside seed; entrant orientation nests innermost, ``candidate_
    first`` then ``opponent_first`` when ``request.both_orientations``
    (Phase 5 spec Sec I.3) -- only ``candidate_first`` otherwise.

    Placement is resolved from ``request.ruleset_id`` (via ``request.
    is_v2_methodology``), never from an external parameter: a v1-methodology
    request (omitted or explicit ``bytefray-rules-1``) generates exactly one
    placement per (subject, opponent, seed) -- the historical fixed
    alignment, ``placement_id="fixed"``, both starts ``0`` -- reproducing
    today's exact matrix shape and size. A v2-methodology request
    (``bytefray-rules-2``) generates ``len(standard_placements())`` (3)
    placements per (subject, opponent, seed) instead.

    ``specs``/``conditions_fingerprint``/``rules_compatibility_id``/
    ``arena_alignment_mode`` are optional and, when given, feed only
    ``condition_fingerprint`` -- unrelated to placement/ruleset resolution,
    which always comes from ``request`` itself so even a ``--dry-run``
    (no specs/conditions_fingerprint) matrix preview shows real placements.
    """

    subjects: list[tuple[str, str]] = [(CANDIDATE, request.candidate_id)]
    if request.baseline_id is not None:
        subjects.append((BASELINE, request.baseline_id))

    orientations: tuple[str, ...] = (
        (ORIENTATION_CANDIDATE_FIRST, ORIENTATION_OPPONENT_FIRST)
        if request.both_orientations
        else (ORIENTATION_CANDIDATE_FIRST,)
    )

    resolved_rules_id = request.resolved_rules_compatibility_id
    resolved_is_v2 = is_ruleset_v2_methodology(resolved_rules_id)

    # v2.0.0-beta2 Phase 2: multi-entrant ("group") matrix generation is a
    # structurally different generation strategy (seed x layout x seat
    # assignment, over one N-entrant roster) from the pairwise loop below
    # (subject x opponent x seed x placement x orientation) -- it lives in
    # its own function and returns early, rather than threading a "group"
    # branch through every line of the pairwise loop.
    if request.group and resolved_is_v2:
        return _build_group_matrix(
            request, evaluation_id, resolved_rules_id, specs, conditions_fingerprint
        )

    placements: tuple[EvaluationPlacement | None, ...] = (
        standard_placements() if resolved_is_v2 else (None,)
    )

    cells: list[EvaluationCell] = []
    ordinal = 0
    for role, subject_id in subjects:
        occurrence_counts: dict[tuple[str, int], int] = {}
        for opponent_index, opponent_id in enumerate(request.opponent_ids):
            for seed_index, seed in enumerate(request.seeds):
                condition_occurrence_index = occurrence_counts.get((opponent_id, seed), 0)
                occurrence_counts[(opponent_id, seed)] = condition_occurrence_index + 1
                for placement_index, placement in enumerate(placements):
                    placement_id = placement.placement_id if placement is not None else "fixed"
                    subject_start = placement.subject_start if placement is not None else 0
                    opponent_start = placement.opponent_start if placement is not None else 0
                    for orientation_index, orientation in enumerate(orientations):
                        ordinal += 1
                        # `ordinal` is included so a repeated (role,
                        # subject_id, opponent_id, seed, placement,
                        # orientation) tuple -- explicitly preserved as
                        # distinct cells above -- still gets a distinct
                        # schedule_id. Without it, duplicate cells collide
                        # in the resume-state lookup dict
                        # (EvaluationService._resolve_from_state keys prior
                        # cells by schedule_id), which silently
                        # misattributes one duplicate's persisted state to
                        # another and can demote a legitimately never-yet-
                        # run duplicate to "corrupted". `orientation` is
                        # included in its own right too (not just via
                        # ordinal) so two cells differing only by
                        # orientation are guaranteed distinct even if the
                        # ordinal derivation ever changed (v0.9 Phase 6,
                        # Sec 9/W.1). `placement_id` joins it for the exact
                        # same reason (Phase 1F): a v1-methodology request
                        # never varies placement, so this is a no-op there
                        # (every cell shares "fixed") -- only meaningful,
                        # and only ever exercised, under v2 methodology.
                        schedule_id = stable_id(
                            "evaluation-cell",
                            {
                                "evaluation_id": evaluation_id,
                                "role": role,
                                "subject_id": subject_id,
                                "opponent_id": opponent_id,
                                "seed": seed,
                                "orientation": orientation,
                                "placement_id": placement_id,
                                "ordinal": ordinal,
                            },
                        )
                        label = (
                            f"{ordinal:04d}-{role}-{_safe_path_segment(subject_id)}"
                            f"-vs-{_safe_path_segment(opponent_id)}-seed{seed}"
                            f"-{placement_id}-{orientation}"
                            if resolved_is_v2
                            else f"{ordinal:04d}-{role}-{_safe_path_segment(subject_id)}"
                            f"-vs-{_safe_path_segment(opponent_id)}-seed{seed}-{orientation}"
                        )
                        condition_fingerprint = None
                        if specs is not None and conditions_fingerprint is not None:
                            fp_payload: dict[str, Any] = {
                                "opponent": agent_identity(specs[opponent_id]),
                                "seed": seed,
                                "effective_conditions": conditions_fingerprint,
                                "rules_compatibility_id": rules_compatibility_id,
                                "condition_occurrence_index": condition_occurrence_index,
                                "orientation": orientation,
                                "arena_alignment_mode": arena_alignment_mode,
                            }
                            # Only added when placement genuinely varies
                            # (v2) -- an unconditional key here would change
                            # every v1 condition_fingerprint's hash for a
                            # dimension that never actually varies under v1
                            # methodology (Phase 1F/1G: smallest honest
                            # identity evolution, byte-identical v1 output).
                            if placement is not None:
                                fp_payload["placement"] = {
                                    "placement_id": placement.placement_id,
                                    "subject_start": placement.subject_start,
                                    "opponent_start": placement.opponent_start,
                                }
                            condition_fingerprint = stable_id("evaluation-condition", fp_payload)
                        cells.append(
                            EvaluationCell(
                                schedule_id=schedule_id,
                                subject_role=role,
                                subject_id=subject_id,
                                opponent_id=opponent_id,
                                seed=seed,
                                artifact_dir=request.output_dir / "matches" / label,
                                opponent_index=opponent_index,
                                seed_index=seed_index,
                                matrix_ordinal=ordinal,
                                condition_occurrence_index=condition_occurrence_index,
                                condition_fingerprint=condition_fingerprint,
                                orientation=orientation,
                                orientation_index=orientation_index,
                                rules_compatibility_id=resolved_rules_id,
                                placement_id=placement_id,
                                subject_start=subject_start,
                                opponent_start=opponent_start,
                                placement_index=placement_index,
                            )
                        )
    return tuple(cells)


def _build_group_matrix(
    request: EvaluationRequest,
    evaluation_id: str,
    resolved_rules_id: str,
    specs: Mapping[str, AgentSpec] | None,
    conditions_fingerprint: str | None,
) -> tuple[EvaluationCell, ...]:
    """Multi-entrant ("group") matrix: seed x layout x seat assignment.

    Only ever called when ``request.group`` and ``request.is_v2_methodology``
    are both true (validated in ``EvaluationService._validate`` before this
    is reached). The full roster (``request.candidate_id`` plus every
    ``request.opponent_ids`` entry, duplicates preserved) is fielded
    together each cell -- one N-entrant match per cell, never N pairwise
    1v1 matches. Seed and layout nest outside seat assignment, matching
    the pairwise matrix's own "environment axes outside the
    permutation/orientation axis" convention.
    """

    roster = request.roster_agent_ids
    canonical_roster = request.canonical_roster
    layouts = standard_layouts(len(roster))
    seat_assignments = enumerate_seat_assignments(roster)
    arena_alignment_mode = EVALUATION_ARENA_ALIGNMENT_MODE_V2_GROUP_STANDARD

    cells: list[EvaluationCell] = []
    ordinal = 0
    for seed_index, seed in enumerate(request.seeds):
        for layout_index, layout in enumerate(layouts):
            for assignment_index, assignment in enumerate(seat_assignments):
                ordinal += 1
                seat_agent_ids = assignment.seat_agent_ids
                other_agent_ids = tuple(
                    sorted(agent_id for agent_id in seat_agent_ids if agent_id != request.candidate_id)
                )
                opponent_label = "+".join(other_agent_ids) if other_agent_ids else "none"
                # `ordinal` guarantees a distinct schedule_id even under a
                # repeated (seed, layout_id, seat_agent_ids) tuple (e.g. a
                # user-supplied duplicate seed) -- the identical defensive
                # role `ordinal` already plays in the pairwise matrix above
                # (Phase 1F/v0.9 Phase 6 precedent).
                schedule_id = stable_id(
                    "evaluation-cell",
                    {
                        "evaluation_id": evaluation_id,
                        "role": CANDIDATE,
                        "roster": list(canonical_roster),
                        "seat_agent_ids": list(seat_agent_ids),
                        "seed": seed,
                        "layout_id": layout.layout_id,
                        "ordinal": ordinal,
                    },
                )
                label = (
                    f"{ordinal:04d}-group-"
                    f"{_safe_path_segment('-'.join(seat_agent_ids))}-seed{seed}-{layout.layout_id}"
                )
                condition_fingerprint = None
                if specs is not None and conditions_fingerprint is not None:
                    fp_payload: dict[str, Any] = {
                        "roster": [agent_identity(specs[agent_id]) for agent_id in canonical_roster],
                        "seat_agent_ids": list(seat_agent_ids),
                        "seed": seed,
                        "effective_conditions": conditions_fingerprint,
                        "rules_compatibility_id": resolved_rules_id,
                        "arena_alignment_mode": arena_alignment_mode,
                        "layout": {
                            "layout_id": layout.layout_id,
                            "seat_starts": list(layout.seat_starts),
                        },
                    }
                    condition_fingerprint = stable_id("evaluation-condition", fp_payload)
                cells.append(
                    EvaluationCell(
                        schedule_id=schedule_id,
                        subject_role=CANDIDATE,
                        subject_id=request.candidate_id,
                        opponent_id=opponent_label,
                        seed=seed,
                        artifact_dir=request.output_dir / "matches" / label,
                        seed_index=seed_index,
                        matrix_ordinal=ordinal,
                        condition_fingerprint=condition_fingerprint,
                        rules_compatibility_id=resolved_rules_id,
                        roster_agent_ids=canonical_roster,
                        seat_agent_ids=seat_agent_ids,
                        layout_id=layout.layout_id,
                        seat_starts=layout.seat_starts,
                        seat_assignment_index=assignment_index,
                        layout_index=layout_index,
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


def all_subject_aggregates(
    candidate_id: str, baseline_id: str | None, cells: Sequence[EvaluationCell]
) -> tuple[SubjectAggregate, ...]:
    """Pooled + per-orientation aggregate views for candidate (and baseline).

    v0.9 Phase 6 (Phase 5 spec Sec K.2): three views per subject -- pooled
    (``orientation_scope="all"``, today's only view before Phase 6, now
    spanning up to 2x the cells), ``candidate_first``, and
    ``opponent_first`` -- always computed and surfaced together, reusing
    :func:`aggregate_cells` unchanged for each (never a second, drifting
    aggregation implementation). Shared by
    ``EvaluationService._all_aggregates`` (the live-run path) and
    ``evaluation_history``'s v1/v2 adapters (the historical-read path) so
    both compute this identically; a legacy cell reconstructed without a
    recorded ``orientation`` field defaults to ``candidate_first``
    (``EvaluationCell.orientation``'s own default), which is also the
    historically correct fact for every pre-Phase-6 cell (Sec L.2).
    """

    subjects: list[tuple[str, str]] = [(CANDIDATE, candidate_id)]
    if baseline_id is not None:
        subjects.append((BASELINE, baseline_id))
    scoped_cells: dict[str, list[EvaluationCell]] = {
        "all": list(cells),
        ORIENTATION_CANDIDATE_FIRST: [
            cell for cell in cells if cell.orientation == ORIENTATION_CANDIDATE_FIRST
        ],
        ORIENTATION_OPPONENT_FIRST: [
            cell for cell in cells if cell.orientation == ORIENTATION_OPPONENT_FIRST
        ],
    }
    aggregates: list[SubjectAggregate] = []
    for role, subject_id in subjects:
        for scope, scope_cells in scoped_cells.items():
            aggregates.append(
                replace(aggregate_cells(role, subject_id, scope_cells), orientation_scope=scope)
            )
    return tuple(aggregates)


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
    # Grouped into lists (not a plain {(opponent_id, seed, orientation):
    # cell} dict) and paired positionally below so a repeated (opponent_id,
    # seed, orientation) triple -- explicitly preserved as distinct cells by
    # build_matrix -- produces one comparison entry per duplicate occurrence
    # instead of silently collapsing all but the last-seen duplicate on
    # each side into a single entry (which previously undercounted "of
    # {total} matched cells" and dropped some duplicates from the
    # comparison entirely).
    #
    # v0.9 Phase 6 (Phase 5 spec Sec K.3): orientation joined the grouping
    # key alongside (opponent_id, seed) -- without it, a candidate's
    # candidate_first cell could pair against a baseline's opponent_first
    # cell for the "same" nominal matchup, silently attributing an
    # orientation effect to a candidate/baseline difference that isn't
    # real. This is the direct comparison-side consequence of never
    # averaging orientation away within a cell (Sec H.2).
    candidate_by_key: dict[tuple[str, int, str, str], list[EvaluationCell]] = {}
    for cell in cells:
        if cell.subject_role == CANDIDATE:
            candidate_by_key.setdefault(
                (cell.opponent_id, cell.seed, cell.orientation, cell.placement_id), []
            ).append(cell)
    baseline_by_key: dict[tuple[str, int, str, str], list[EvaluationCell]] = {}
    for cell in cells:
        if cell.subject_role == BASELINE:
            baseline_by_key.setdefault(
                (cell.opponent_id, cell.seed, cell.orientation, cell.placement_id), []
            ).append(cell)
    keys = sorted(set(candidate_by_key) | set(baseline_by_key))

    entries: list[ComparisonEntry] = []
    for opponent_id, seed, orientation, placement_id in keys:
        key = (opponent_id, seed, orientation, placement_id)
        candidate_list = candidate_by_key.get(key, [])
        baseline_list = baseline_by_key.get(key, [])
        for candidate_cell, baseline_cell in zip_longest(candidate_list, baseline_list):
            if candidate_cell is None or baseline_cell is None:
                entries.append(
                    ComparisonEntry(
                        opponent_id=opponent_id,
                        seed=seed,
                        orientation=orientation,
                        placement_id=placement_id,
                        classification="inconclusive",
                        candidate_outcome=candidate_cell.outcome if candidate_cell else None,
                        baseline_outcome=baseline_cell.outcome if baseline_cell else None,
                        reason="cell missing on one side",
                        candidate_schedule_id=candidate_cell.schedule_id if candidate_cell else None,
                        baseline_schedule_id=baseline_cell.schedule_id if baseline_cell else None,
                    )
                )
                continue
            if not candidate_cell.is_scored or not baseline_cell.is_scored:
                entries.append(
                    ComparisonEntry(
                        opponent_id=opponent_id,
                        seed=seed,
                        orientation=orientation,
                        placement_id=placement_id,
                        classification="inconclusive",
                        candidate_outcome=candidate_cell.outcome,
                        baseline_outcome=baseline_cell.outcome,
                        reason=(
                            f"candidate={candidate_cell.status}/{candidate_cell.outcome} "
                            f"baseline={baseline_cell.status}/{baseline_cell.outcome}"
                        ),
                        candidate_schedule_id=candidate_cell.schedule_id,
                        baseline_schedule_id=baseline_cell.schedule_id,
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
                    orientation=orientation,
                    placement_id=placement_id,
                    classification=classification,
                    candidate_outcome=candidate_cell.outcome,
                    baseline_outcome=baseline_cell.outcome,
                    candidate_score=candidate_cell.score_subject,
                    baseline_score=baseline_cell.score_subject,
                    candidate_score_differential=candidate_score_diff,
                    baseline_score_differential=baseline_score_diff,
                    candidate_territory=candidate_cell.territory_subject,
                    baseline_territory=baseline_cell.territory_subject,
                    candidate_schedule_id=candidate_cell.schedule_id,
                    baseline_schedule_id=baseline_cell.schedule_id,
                )
            )
    return tuple(entries)


def rerun_command(
    subject_id: str,
    opponent_id: str,
    seed: int,
    ticks: int,
    orientation: str = ORIENTATION_CANDIDATE_FIRST,
) -> str:
    """The exact ``agents test`` invocation that reproduces one cell (Sec 8/10).

    v0.9 Phase 6 (Phase 5 spec Sec H.1): an ``opponent_first`` cell's real
    physical match ran with roles swapped
    (``test_agent(opponent_id, opponent=subject_id, ...)``) -- the printed
    command mirrors that exactly, so it reproduces the cell byte for byte
    rather than silently reproducing the opposite orientation.
    """

    if orientation == ORIENTATION_OPPONENT_FIRST:
        first_id, second_id = opponent_id, subject_id
    else:
        first_id, second_id = subject_id, opponent_id
    return f"bytefray agents test {first_id} --opponent {second_id} --seed {seed} --ticks {ticks}"


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
    """Resolve outcome/score/territory from the correct physical slot for ``cell.orientation``.

    Every stored field is expressed from the evaluation-role (subject/
    opponent) perspective regardless of which physical slot actually
    executed each role (Phase 5 spec Sec H.1/Sec 12) -- see
    :func:`physical_slots_for_orientation`.
    """

    subject_slot, opponent_slot = physical_slots_for_orientation(cell.orientation)
    winner = match_result.winner
    outcome = (
        "tie"
        if winner == WINNER_TIE_SENTINEL
        else "win"
        if winner == subject_slot
        else "loss"
    )
    agents_by_id = match_result.agents_by_id
    subject_agent = agents_by_id.get(subject_slot)
    opponent_agent = agents_by_id.get(opponent_slot)
    return replace(
        cell,
        status="completed",
        outcome=outcome,
        match_id=match_result.match_id,
        result_id=match_result.result_id,
        ticks_run=match_result.ticks_run,
        score_subject=float(match_result.score.get(subject_slot, 0)),
        score_opponent=float(match_result.score.get(opponent_slot, 0)),
        territory_subject=(subject_agent.territory_pct_last if subject_agent else None),
        territory_opponent=(opponent_agent.territory_pct_last if opponent_agent else None),
        error_code=None,
        error_message=None,
    )


def _cell_from_match_result_group(cell: EvaluationCell, match_result: NativeMatchResult) -> EvaluationCell:
    """The multi-entrant generalization of :func:`_cell_from_match_result`.

    Only the subject's (candidate's) own outcome/score/territory are
    resolved into the shared summary fields -- `score_opponent`/
    `territory_opponent` stay `None` for a group cell (ill-defined for
    more than one "opponent"); every seat's full result remains fully
    recoverable from this cell's own persisted result.json (Phase 1's
    "cell stores summary, result.json stores everything" pattern,
    unchanged). Per-seat breakdowns beyond the subject's own perspective
    are explicitly deferred to a later phase -- see the design doc's
    "analysis compatibility" section.
    """

    subject_slot = cell.subject_seat
    winner = match_result.winner
    outcome = (
        "tie"
        if winner == WINNER_TIE_SENTINEL
        else "win"
        if winner == subject_slot
        else "loss"
    )
    subject_agent = match_result.agents_by_id.get(subject_slot) if subject_slot else None
    return replace(
        cell,
        status="completed",
        outcome=outcome,
        match_id=match_result.match_id,
        result_id=match_result.result_id,
        ticks_run=match_result.ticks_run,
        score_subject=float(match_result.score.get(subject_slot, 0)) if subject_slot else None,
        territory_subject=(subject_agent.territory_pct_last if subject_agent else None),
        error_code=None,
        error_message=None,
    )


def _cell_from_envelope_group(cell: EvaluationCell, envelope: ResultEnvelope) -> EvaluationCell:
    """Envelope-based mirror of :func:`_cell_from_match_result_group` (resume path)."""

    subject_slot = cell.subject_seat
    winner = envelope.winner
    outcome = (
        "tie"
        if winner == WINNER_TIE_SENTINEL
        else "win"
        if winner == subject_slot
        else "loss"
    )
    subject_entrant = next(
        (entry for entry in envelope.entrants if entry.get("agent_id") == subject_slot), {}
    )
    subject_stats = subject_entrant.get("statistics", {}) or {}
    return replace(
        cell,
        status="completed",
        outcome=outcome,
        match_id=envelope.match_id,
        result_id=envelope.result_id,
        ticks_run=envelope.ticks,
        score_subject=float(envelope.score.get(subject_slot, 0)) if subject_slot else None,
        territory_subject=subject_stats.get("territory_pct_last"),
        error_code=None,
        error_message=None,
    )


def _cell_from_envelope(cell: EvaluationCell, envelope: ResultEnvelope) -> EvaluationCell:
    """Envelope-based mirror of :func:`_cell_from_match_result` (resume path)."""

    subject_slot, opponent_slot = physical_slots_for_orientation(cell.orientation)
    winner = envelope.winner
    outcome = (
        "tie"
        if winner == WINNER_TIE_SENTINEL
        else "win"
        if winner == subject_slot
        else "loss"
    )
    subject_entrant = next(
        (entry for entry in envelope.entrants if entry.get("agent_id") == subject_slot), {}
    )
    opponent_entrant = next(
        (entry for entry in envelope.entrants if entry.get("agent_id") == opponent_slot), {}
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
        score_subject=float(envelope.score.get(subject_slot, 0)),
        score_opponent=float(envelope.score.get(opponent_slot, 0)),
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
        # A resumed cell's own execution provenance is preserved verbatim --
        # never rewritten to the resuming process's context (Sec 5/Sec 6).
        execution_context_id=previous.get("execution_context_id"),
    )


def _checkpoint_cells(
    completed_by_schedule_id: Mapping[str, EvaluationCell],
    matrix: Sequence[EvaluationCell],
    prior_cells: Mapping[str, Any],
) -> list[EvaluationCell]:
    """B2: a checkpoint must never be less complete than the durable state
    already on disk.

    ``completed_by_schedule_id`` covers only the cells resolved or executed
    *so far* -- during a retry, that is strictly less than every cell a
    *prior* run already durably persisted (e.g. seed 2 completed in an
    earlier run, then seed 1 is retried in this one; the map after seed 1's
    retry contains only seed 1). Writing it verbatim as a mid-run checkpoint
    would silently drop every already-durable cell not yet reached.

    This backfills exactly those cells: any matrix cell not already covered
    by ``completed_by_schedule_id`` that has a prior persisted entry keeps
    that entry verbatim (reconstructed via ``_cell_from_state``), in matrix
    order. A cell with no prior durable state at all (genuinely never before
    recorded) is left out entirely -- never fabricated as a placeholder --
    so an ordinary first-ever run's intermediate checkpoints are byte-for-
    byte unaffected (this is a no-op whenever ``prior_cells`` is empty).

    Keyed by ``schedule_id`` rather than assuming a positionally
    matrix-ordered input (v1.6 Phase 2, docs/V1_6_PHASE2_PARALLEL_
    EVALUATION.md): the parallel dispatch path resolves cells in
    wall-clock/completion order, not matrix order, so canonical ordering is
    reconstructed here -- by walking ``matrix`` and looking each cell up --
    for both the serial and parallel dispatch paths alike. One ordering
    implementation, not two.
    """

    merged: list[EvaluationCell] = []
    for cell in matrix:
        resolved = completed_by_schedule_id.get(cell.schedule_id)
        if resolved is not None:
            merged.append(resolved)
            continue
        previous = prior_cells.get(cell.schedule_id)
        if previous is not None:
            merged.append(_cell_from_state(cell, previous))
    return merged


def _drift_detail(cell: EvaluationCell) -> dict[str, Any]:
    """The ``abort_detail`` payload shape for a drift-detected cell (unchanged
    from pre-Phase-2 behavior -- see ``EvaluationService.run``)."""

    return {
        "role": cell.subject_role,
        "subject_id": cell.subject_id,
        "opponent_id": cell.opponent_id,
        "schedule_id": cell.schedule_id,
        "code": cell.error_code,
        "detail": cell.error_message,
    }


def _drain_abandoned_cells(
    pending_queue: queue.Queue[EvaluationCell | None],
) -> list[EvaluationCell]:
    """Non-blocking drain of whatever is still sitting in ``pending_queue``.

    Used by the parallel dispatch path (v1.6 Phase 2) both when a drift is
    observed (those cells are simply abandoned -- never dispatched, never
    recorded at all, matching what today's serial ``break`` already does for
    matrix positions it never reaches) and when every worker has died with
    cells still queued (those are recorded as failed, never silently
    dropped -- see ``_run_pending_parallel``). A best-effort race against
    dispatcher threads concurrently popping the same queue is acceptable
    here: whichever side wins a given item only changes which cell happens
    to be "one more in flight" at the moment of the decision, which is
    already an explicitly disclosed, worker-count/timing-dependent behavior
    (Phase 0-1 baseline Sec 8).
    """

    drained: list[EvaluationCell] = []
    while True:
        try:
            item = pending_queue.get_nowait()
        except queue.Empty:
            break
        if item is not None:
            drained.append(item)
    return drained


def _evaluation_dispatcher_loop(
    handle: Any,
    pending_queue: queue.Queue[EvaluationCell | None],
    results_queue: queue.Queue[tuple[str, CellExecutionResult | None, Any]],
    ticks: int,
    data_root: Path | None,
    planned_identities: Mapping[str, dict[str, Any]],
) -> None:
    """One dispatcher thread's body: owns exactly one worker subprocess handle
    for its entire lifetime, processing cells strictly one at a time against
    it -- mirrors ``agent_worker.AgentWorkerHandle``'s existing single-
    in-flight-call model exactly, so no wire-protocol correlation IDs are
    needed. Blocks indefinitely on ``pending_queue.get()`` between cells
    (never a polling timeout): the coordinator never pushes a shutdown
    sentinel (``None``) until it is certain no more work -- including any
    retry -- will ever be enqueued, so a thread can never legitimately give
    up early, and never blocks forever on work that will never arrive.

    Imports ``battle_engine.evaluation_worker`` and ``battle_engine.
    agent_worker.WorkerCallStatus`` lazily (function-local): this module
    cannot import ``evaluation_worker`` at module scope without a circular
    import, since ``evaluation_worker`` itself imports this module.
    """

    from battle_engine.agent_worker import WorkerCallStatus
    from battle_engine.evaluation_worker import WorkerFailure, _cell_from_wire

    while True:
        cell = pending_queue.get()
        if cell is None:
            return
        call_result = handle.submit_cell(
            cell, ticks=ticks, data_root=data_root, planned_identities=planned_identities
        )
        if call_result.status == WorkerCallStatus.OK:
            payload = call_result.payload or {}
            resolved_cell = _cell_from_wire(payload["cell"])
            context_payload = payload.get("execution_context")
            context = ExecutionContext(**context_payload) if context_payload else None
            results_queue.put(
                (cell.schedule_id, CellExecutionResult(cell=resolved_cell, execution_context=context), None)
            )
        elif call_result.status == WorkerCallStatus.FAILED:
            # A well-formed {"ok": false, ...} -- the worker's own
            # belt-and-suspenders catch-all (evaluation_worker._handle_run_
            # cell), expected to be rare since _execute_cell/test_agent
            # already handle nearly everything internally. The worker
            # process itself is still alive and protocol-intact; only this
            # one cell failed -- this dispatcher thread keeps running.
            diagnostic = (call_result.payload or {}).get("diagnostic") or {}
            failed_cell = replace(
                cell,
                status="failed",
                outcome=None,
                error_code=str(diagnostic.get("code", "evaluation_worker_error")),
                error_message=str(diagnostic.get("message", ""))[:240],
            )
            results_queue.put((cell.schedule_id, CellExecutionResult(cell=failed_cell), None))
        else:
            # EXITED / PROTOCOL_ERROR / TIMEOUT (TIMEOUT is unreachable --
            # submit_cell never passes a protocol timeout): this worker is
            # presumed dead. Report the failure and stop -- no automatic
            # replacement subprocess is spawned (v1.6 Phase 2 Sec 9's
            # smallest-change policy); the coordinator decides whether to
            # retry this specific cell on a different, still-live worker.
            results_queue.put(
                (
                    cell.schedule_id,
                    None,
                    WorkerFailure(schedule_id=cell.schedule_id, status=call_result.status, detail=str(call_result.status)),
                )
            )
            handle.close()
            return


def _resumed_cell_mismatch(
    envelope: ResultEnvelope, cell: EvaluationCell, expected_match_id: str
) -> str | None:
    """Sec 14: adapted from ``tournament_service._resumed_result_mismatch``."""

    entrant_order = tuple(str(entry.get("agent_id")) for entry in envelope.entrants)
    # v2.0.0-beta2 Phase 2: a group cell's expected physical slot order is
    # seat_label(0..N-1) -- N seats, not the fixed 2-entrant (A, B) pair.
    expected_order = (
        tuple(seat_label(index) for index in range(len(cell.seat_agent_ids)))
        if cell.is_group
        else (TESTED_AGENT_SLOT, OPPONENT_SLOT)
    )
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
    # H5: the replay filename comes from a persisted result.json this
    # module does not control -- resolve it through the same containment
    # discipline as any other nested artifact path (M4) rather than a bare
    # join, which a `../`, absolute, or symlink-escaping filename could
    # otherwise walk outside the cell's own artifact directory.
    replay_path = contained_path(cell.artifact_dir, envelope.replay.filename)
    if replay_path is None:
        return (
            f"result replay filename {envelope.replay.filename!r} escapes the "
            "cell's artifact directory"
        )
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
    if header.ruleset_id != envelope.ruleset_id:
        return (
            f"replay header ruleset_id {header.ruleset_id!r} does not match "
            f"result envelope ruleset_id {envelope.ruleset_id!r}"
        )
    return None


# ---------------------------------------------------------------------------
# Revision capture (docs/specs/agent_revision.md Sec 4/5 -- Phase 3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RevisionPlanEntry:
    """The two revision fields rendered into one ``planned_identities`` entry.

    Deliberately narrower than ``agent_revisions.RevisionArchivalResult``:
    ``complete``/``omitted`` are not persisted here at all (Sec 5.1 of the
    spec -- they already live durably in the revision store's own
    ``manifest.json``, keyed by ``agent_revision_id``; duplicating them
    into every evaluation artifact that references a revision would be a
    second, driftable copy of the same fact).
    """

    agent_revision_id: str | None
    agent_revision_error: str | None


def _revision_entry_from_raw(raw: Any) -> _RevisionPlanEntry | None:
    if not isinstance(raw, Mapping):
        return None
    revision_id = raw.get("agent_revision_id")
    if not isinstance(revision_id, str):
        return None
    error = raw.get("agent_revision_error")
    return _RevisionPlanEntry(revision_id, error if isinstance(error, str) else None)


def _prior_revision_by_agent_id(prior: Mapping[str, Any]) -> dict[str, _RevisionPlanEntry]:
    """Recover any already-recorded ``agent_revision_id``s from a prior checkpoint.

    Resume/retry must retain the originally planned revision ID (Sec 4 of
    docs/specs/agent_revision.md) -- this is what lets ``_resolve_revision_
    results`` skip re-archiving (and re-reading the source tree) for any
    agent that already has a durable, recorded revision from an earlier
    invocation of this same evaluation, rather than silently recomputing
    one every time ``run()`` is called. An agent with no usable prior
    ``agent_revision_id`` (a pre-Phase-3 v2 artifact -- no ``agent_revisions``
    key at all -- or a prior invocation whose archival never produced an id)
    is simply absent from the returned mapping -- ``_resolve_revision_
    results`` then archives it fresh, exactly as it would for a first
    invocation.

    ``agent_revisions`` (Sec 5.1/5.2 of the spec, as actually implemented)
    is a role-keyed sibling of ``planned_identities`` -- ``candidate``/
    ``baseline``/``opponents`` -- deliberately carrying no ``agent_id``
    field of its own (unlike ``planned_identities``' entries), so it never
    risks being mistaken for something that could be merged back into
    ``planned_identities`` and rehashed. Recovering an agent_id-keyed
    lookup therefore means correlating positionally against the prior
    artifact's own ``candidate_id``/``baseline_id``/``opponent_ids`` --
    the same ordered-list convention ``_evaluation_id``'s own
    ``"opponents": [identities[opponent_id] for opponent_id in
    request.opponent_ids]`` already uses.
    """

    agent_revisions = prior.get("agent_revisions")
    if not isinstance(agent_revisions, Mapping):
        return {}

    result: dict[str, _RevisionPlanEntry] = {}

    candidate_id = prior.get("candidate_id")
    if isinstance(candidate_id, str):
        entry = _revision_entry_from_raw(agent_revisions.get("candidate"))
        if entry is not None:
            result[candidate_id] = entry

    baseline_id = prior.get("baseline_id")
    if isinstance(baseline_id, str):
        entry = _revision_entry_from_raw(agent_revisions.get("baseline"))
        if entry is not None and baseline_id not in result:
            result[baseline_id] = entry

    opponent_ids = prior.get("opponent_ids")
    opponent_revisions = agent_revisions.get("opponents")
    if isinstance(opponent_ids, list) and isinstance(opponent_revisions, list):
        for agent_id, raw in zip(opponent_ids, opponent_revisions):
            if not isinstance(agent_id, str) or agent_id in result:
                continue
            entry = _revision_entry_from_raw(raw)
            if entry is not None:
                result[agent_id] = entry
    return result


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
        data_root: Path | None = None,
        both_orientations: bool = True,
        ruleset_id: str | None = None,
        group: bool = False,
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
            data_root=data_root,
            both_orientations=both_orientations,
            ruleset_id=ruleset_id,
            group=group,
        )
        specs = self._validate(request)
        conditions = self._effective_conditions(request)
        identities = {agent_id: agent_identity(spec) for agent_id, spec in specs.items()}
        evaluation_id = self._evaluation_id(request, identities, conditions)
        return specs, evaluation_id

    def run(
        self,
        request: EvaluationRequest,
        *,
        checkpoint_batch_size: int = 16,
        checkpoint_batch_interval: float = 1.0,
    ) -> EvaluationResult:
        """Run (or resume) an evaluation.

        ``checkpoint_batch_size``/``checkpoint_batch_interval`` (v1.6 Phase
        2, docs/V1_6_PHASE2_PARALLEL_EVALUATION.md Sec 8): ``evaluation.json``
        is checkpointed after every ``checkpoint_batch_size`` newly-completed
        cells or every ``checkpoint_batch_interval`` seconds, whichever comes
        first -- applied uniformly regardless of ``request.workers``, since
        the O(n^2) cumulative cost of rewriting the whole, growing ``cells``
        list after literally every single cell (Phase 0-1 baseline Sec 5.4)
        exists independent of dispatch mode. The unconditional checkpoint
        before any cell executes and the unconditional final checkpoint are
        both unaffected -- only the *frequency* of the intermediate
        checkpoints changes, never their completeness (each one is always a
        full, canonically matrix-ordered snapshot) or the final persisted
        content. On an ungraceful crash, at most ``checkpoint_batch_size``
        cells or ``checkpoint_batch_interval`` seconds of already-completed
        work (whichever bound was reached last) is not yet durable; resume
        simply re-executes exactly those cells, the same as it always has
        for any cell absent from a prior checkpoint -- no new durable
        "in-progress" cell state is introduced.
        """

        specs = self._validate(request)
        # Frozen at validate time, deliberately never re-derived from a live
        # AgentSpec.source_path later -- Sec 7's pre-check compares a fresh
        # resolve against *this* snapshot, not against `specs` (whose
        # source_path would just re-read whatever the file currently
        # contains, silently defeating drift detection). `evaluation_id` is
        # derived from this exact same dict (never from a second independent
        # `agent_identity()` call) so the persisted `planned_identities`
        # payload is *structurally* guaranteed to reproduce the recorded
        # `evaluation_id` -- see `_evaluation_id` and `_write_state` below.
        planned_identities = {agent_id: agent_identity(spec) for agent_id, spec in specs.items()}
        conditions = self._effective_conditions(request)
        conditions_fp = stable_id("evaluation-conditions", asdict(conditions))
        evaluation_id = self._evaluation_id(request, planned_identities, conditions)
        resolved_rules_id = request.resolved_rules_compatibility_id
        resolved_is_v2 = is_ruleset_v2_methodology(resolved_rules_id)
        resolved_group = request.group and resolved_is_v2
        state_path = request.output_dir / "evaluation.json"
        prior = (
            self._load_state(
                state_path, evaluation_id, resolved_schema_version(resolved_is_v2, resolved_group)
            )
            if request.resume
            else {}
        )
        prior_cells = {item["schedule_id"]: item for item in prior.get("cells", ())}
        # Revision capture (docs/specs/agent_revision.md Sec 4): resolved
        # here, after `prior` is loaded (so an already-planned agent's
        # revision ID can be retained rather than recomputed) and strictly
        # before `matrix`/any checkpoint/any cell execution. A detected
        # freeze-time mismatch raises out of this call, aborting `run()`
        # before any of that happens -- no evaluation.json is written or
        # modified for this invocation.
        revision_plan = self._resolve_revision_results(request, specs, planned_identities, prior)
        matrix = build_matrix(
            request,
            evaluation_id,
            specs,
            conditions_fp,
            resolved_rules_id,
            resolved_arena_alignment_mode(resolved_is_v2, resolved_group),
        )

        created_at = prior.get("created_at") or _utc_now_iso()
        execution_contexts: list[dict[str, Any]] = list(prior.get("execution_contexts", ()))
        known_context_ids: set[str] = {
            item["context_id"] for item in execution_contexts if item.get("context_id") is not None
        }

        # First checkpoint: written before any cell executes, so a crash
        # during cell 1 still leaves discoverable lifecycle state (Sec 5).
        # Only valid for a genuinely *new* evaluation (no prior cells) --
        # writing an empty ``cells=()`` checkpoint over an *existing*
        # artifact's already-persisted cells would erase it the instant
        # resume starts, before a single prior cell has even been
        # reconstructed/verified (B2). A resumed artifact's own on-disk
        # state already serves as adequate discoverable state; it is left
        # untouched until this run has something at least as good to
        # replace it with.
        if not prior_cells:
            self._write_state(
                state_path,
                evaluation_id,
                request,
                (),
                matrix,
                planned_identities=planned_identities,
                revision_plan=revision_plan,
                conditions=conditions,
                created_at=created_at,
                lifecycle_state="running",
                execution_contexts=execution_contexts,
            )

        # -- Phase A: resolve everything possible from prior state --------
        #
        # A single forward pass over `matrix`, in order -- zero dependency
        # on dispatch mode, no threads involved (v1.6 Phase 2 Sec 4).
        # Mirrors today's per-cell resume decision exactly. Stops early
        # (matching the old loop's `break`) the instant it resolves a cell
        # whose *persisted* status is already `drift_detected` -- cells at
        # or after that point in matrix order are never eligible for
        # dispatch this run, exactly as the old serial loop never reached
        # them either (M2: the only correct recovery from a drifted
        # evaluation is a fresh one). Any *pending* cell strictly before
        # that point may still independently drift when actually executed
        # in Phase B below -- since it is, by construction, earlier in
        # matrix order, that drift (if any) is what actually determines the
        # abort point; see the min-matrix_ordinal selection after Phase B.
        completed_by_schedule_id: dict[str, EvaluationCell] = {}
        pending: list[EvaluationCell] = []
        drifted_cells: list[EvaluationCell] = []
        for cell in matrix:
            previous = prior_cells.get(cell.schedule_id)
            resolved: EvaluationCell | None = None
            if previous is not None:
                resolved = self._resolve_from_state(cell, previous, specs, request)
                if (
                    resolved is not None
                    # M2: `drift_detected` is deliberately excluded here --
                    # it signals the *frozen plan itself* no longer
                    # matches the agent(s) as they exist on disk. Retrying
                    # inside this same artifact would silently execute a
                    # new revision under the old plan's evaluation_id; the
                    # only correct recovery is a fresh evaluation (a new
                    # plan/output directory), never `--retry-failed` on
                    # this one -- regardless of whether the source has
                    # since been restored to its original content.
                    and resolved.status in ("failed", "corrupted")
                    and request.retry_failures
                ):
                    resolved = None
            if resolved is not None:
                completed_by_schedule_id[cell.schedule_id] = resolved
                if resolved.status == "drift_detected":
                    drifted_cells.append(resolved)
                    break
            else:
                pending.append(cell)

        # -- Phase B: dispatch `pending` (serial or a bounded worker pool) --
        any_newly_executed = False
        batch_count = 0
        last_checkpoint_time = time.monotonic()

        def ingest(result: CellExecutionResult) -> bool:
            """Coordinator-only: record one Phase-B result, register its
            execution context, and checkpoint on the batch policy. Returns
            True iff this result is itself a newly observed drift (the
            caller stops feeding further cells to workers when this fires).
            """

            nonlocal any_newly_executed, batch_count, last_checkpoint_time
            any_newly_executed = True
            completed_by_schedule_id[result.cell.schedule_id] = result.cell
            if result.execution_context is not None:
                _register_execution_context(result.execution_context, execution_contexts, known_context_ids)
            is_drift = result.cell.status == "drift_detected"
            if is_drift:
                drifted_cells.append(result.cell)
            batch_count += 1
            now = time.monotonic()
            if batch_count >= checkpoint_batch_size or (now - last_checkpoint_time) >= checkpoint_batch_interval:
                self._write_state(
                    state_path,
                    evaluation_id,
                    request,
                    _checkpoint_cells(completed_by_schedule_id, matrix, prior_cells),
                    matrix,
                    planned_identities=planned_identities,
                    revision_plan=revision_plan,
                    conditions=conditions,
                    created_at=created_at,
                    lifecycle_state="running",
                    execution_contexts=execution_contexts,
                )
                batch_count = 0
                last_checkpoint_time = now
            return is_drift

        if pending:
            if request.workers <= 1:
                for cell in pending:
                    result = self._execute_cell(
                        cell, request.ticks, request.data_root, planned_identities
                    )
                    if ingest(result):
                        break
            else:
                self._run_pending_parallel(pending, request, planned_identities, ingest)

        # The authoritative drift (if any) is the one with the smallest
        # `matrix_ordinal` among every drifted cell actually observed this
        # run -- whether resolved instantly from prior state (Phase A) or
        # discovered by real execution (Phase B). Phase A's own early
        # `break` already guarantees `pending` never contains a cell at or
        # after a Phase-A-found drift point, so any Phase-B drift is always
        # earlier in matrix order and naturally wins this selection -- no
        # special-case "which phase wins" logic is needed (v1.6 Phase 2
        # Sec 6/Sec 7; Phase 0-1 baseline Sec 8 option (a)).
        drift = _drift_detail(min(drifted_cells, key=lambda c: c.matrix_ordinal)) if drifted_cells else None

        # Every derived view (aggregates, comparison, the persisted `cells[]`,
        # and the returned `EvaluationResult.cells`) is built from this one
        # canonically matrix-ordered list -- never from `completed_by_
        # schedule_id`'s raw insertion order, which (under parallel dispatch)
        # reflects wall-clock completion order, not matrix order. This keeps
        # every worker count's output identical for anything order-sensitive,
        # and matches invariant #4 (docs/V1_6_PHASE2_PARALLEL_EVALUATION.md).
        final_cells = _checkpoint_cells(completed_by_schedule_id, matrix, prior_cells)

        aggregates = self._all_aggregates(request, final_cells)
        comparison = compare_candidate_baseline(final_cells) if request.baseline_id is not None else ()
        # M1: a true no-op resume -- everything reconstructed from prior
        # state, nothing newly executed, and that prior state was already a
        # genuinely finished evaluation -- must preserve the original
        # completion chronology rather than minting a new `finished_at` on
        # every idle resume. A resume that did real new work (or completes
        # for the first time) still gets its own fresh timestamp.
        if drift is not None:
            finished_at = None
        elif (
            not any_newly_executed
            and prior.get("lifecycle_state") == "finished"
            and isinstance(prior.get("finished_at"), str)
        ):
            finished_at = prior["finished_at"]
        else:
            finished_at = _utc_now_iso()
        self._write_state(
            state_path,
            evaluation_id,
            request,
            final_cells,
            matrix,
            aggregates=aggregates,
            comparison=comparison,
            planned_identities=planned_identities,
            revision_plan=revision_plan,
            conditions=conditions,
            created_at=created_at,
            lifecycle_state="aborted" if drift is not None else "finished",
            finished_at=finished_at,
            abort_reason="source_drift" if drift is not None else None,
            abort_detail=drift,
            execution_contexts=execution_contexts,
        )
        return EvaluationResult(
            evaluation_id=evaluation_id,
            request=request,
            cells=tuple(final_cells),
            aggregates=aggregates,
            comparison=comparison,
            state_path=state_path,
        )

    # -- parallel dispatch (v1.6 Phase 2) ----------------------------------

    def _run_pending_parallel(
        self,
        pending: list[EvaluationCell],
        request: EvaluationRequest,
        planned_identities: Mapping[str, dict[str, Any]],
        ingest: Callable[[CellExecutionResult], bool],
    ) -> None:
        """Dispatch ``pending`` across ``min(request.workers, len(pending))``
        long-lived worker subprocesses.

        Only this method (and the dispatcher threads it starts) touch the
        two thread-safe queues; ``ingest`` (and everything it touches --
        ``completed_by_schedule_id``, ``execution_contexts``, checkpoint
        timing) is only ever called from *this* thread (the coordinator),
        never from a dispatcher thread -- dispatcher threads only ever push
        onto ``results``. See docs/V1_6_PHASE2_PARALLEL_EVALUATION.md Sec 4
        for the full race-freedom argument (in particular: why no polling
        timeout is needed anywhere in this method, and why a dead worker can
        never strand a cell forever).
        """

        from battle_engine.evaluation_worker import EvaluationCellWorkerHandle

        pending_by_schedule_id = {cell.schedule_id: cell for cell in pending}
        worker_count = min(request.workers, len(pending))

        pending_queue: queue.Queue[EvaluationCell | None] = queue.Queue()
        for cell in pending:
            pending_queue.put(cell)
        results_queue: queue.Queue[tuple[str, CellExecutionResult | None, Any]] = queue.Queue()

        handles = [EvaluationCellWorkerHandle() for _ in range(worker_count)]
        for handle in handles:
            handle.start()
        threads = [
            threading.Thread(
                target=_evaluation_dispatcher_loop,
                args=(handle, pending_queue, results_queue, request.ticks, request.data_root, planned_identities),
                daemon=True,
            )
            for handle in handles
        ]
        for thread in threads:
            thread.start()

        outstanding = len(pending)
        retried: set[str] = set()
        live_worker_count = len(threads)
        stop_requested = False

        try:
            while outstanding > 0:
                schedule_id, result, failure = results_queue.get()
                if failure is not None:
                    live_worker_count -= 1
                    if schedule_id not in retried and live_worker_count > 0 and not stop_requested:
                        retried.add(schedule_id)
                        pending_queue.put(pending_by_schedule_id[schedule_id])
                    else:
                        outstanding -= 1
                        error_code = (
                            "evaluation_worker_exited"
                            if schedule_id in retried
                            else "evaluation_worker_unavailable"
                        )
                        failed_cell = replace(
                            pending_by_schedule_id[schedule_id],
                            status="failed",
                            outcome=None,
                            error_code=error_code,
                            error_message=(
                                "the evaluation cell worker process exited while "
                                "executing this cell."
                            ),
                        )
                        ingest(CellExecutionResult(cell=failed_cell))
                    if live_worker_count == 0 and not stop_requested:
                        for stranded in _drain_abandoned_cells(pending_queue):
                            outstanding -= 1
                            stranded_cell = replace(
                                stranded,
                                status="failed",
                                outcome=None,
                                error_code="evaluation_worker_unavailable",
                                error_message="no evaluation worker was available to execute this cell.",
                            )
                            ingest(CellExecutionResult(cell=stranded_cell))
                else:
                    outstanding -= 1
                    assert result is not None
                    if ingest(result) and not stop_requested:
                        stop_requested = True
                        # Cells still sitting in the queue are simply
                        # abandoned -- never dispatched, never recorded at
                        # all (matches what the serial loop's `break`
                        # already does for matrix positions it never
                        # reaches). Already in-flight cells are left alone
                        # and allowed to finish normally.
                        for abandoned in _drain_abandoned_cells(pending_queue):
                            outstanding -= 1
        finally:
            # No more work will ever be enqueued past this point (the loop
            # above only exits once every dispatched cell has produced a
            # result and nothing remains in `pending_queue`) -- safe to
            # shut every surviving thread down now. A thread can only be
            # blocked on `pending_queue.get()` here, never mid-`submit_cell`
            # (that would still be `outstanding`), so a shutdown sentinel
            # always reaches it promptly.
            for _ in threads:
                pending_queue.put(None)
            for thread in threads:
                thread.join(timeout=5.0)
            for handle in handles:
                handle.close()

    # -- validation -----------------------------------------------------

    def _validate(self, request: EvaluationRequest) -> dict[str, AgentSpec]:
        if not request.opponent_ids:
            raise EvaluationConfigurationError("Evaluation requires at least one opponent.")
        if not request.seeds:
            raise EvaluationConfigurationError("Evaluation requires at least one seed.")
        if request.ticks < 1:
            raise EvaluationConfigurationError("Evaluation requires a positive tick limit.")
        if request.workers < 1:
            raise EvaluationConfigurationError("Evaluation requires a positive worker count.")
        if request.baseline_id is not None and request.baseline_id == request.candidate_id:
            raise EvaluationConfigurationError(
                "Candidate and baseline must be different agents."
            )
        # Phase 1H: evaluation is product-facing and must never expose a
        # historical alpha Ruleset identity, even though
        # resolve_ruleset_policy would happily resolve one -- mirrors
        # agent_test's own --ruleset choices exactly. Every entrant is
        # already restricted to Python agents by _resolve_python_agent
        # below regardless of Ruleset, so this never needs to separately
        # duplicate the runtime-kind check Beta1's runtime boundary already
        # performs (RulesetRuntimeUnsupportedError, raised through
        # AgentTestError/test_agent if that boundary is ever reached).
        if request.ruleset_id is not None and request.ruleset_id not in (
            BYTEFRAY_RULESET_ID,
            BYTEFRAY_RULESET_V2_ID,
        ):
            raise EvaluationConfigurationError(
                f"Unsupported evaluation --ruleset {request.ruleset_id!r}; expected "
                f"{BYTEFRAY_RULESET_ID!r} or {BYTEFRAY_RULESET_V2_ID!r}."
            )
        # v2.0.0-beta2 Phase 2: multi-entrant ("group") methodology
        # constraints -- fail closed rather than silently degrading to
        # pairwise or silently ignoring `group`.
        if request.group:
            if not request.is_v2_methodology:
                raise EvaluationConfigurationError(
                    "Multi-entrant (--group) evaluation requires --ruleset bytefray-rules-2."
                )
            if request.baseline_id is not None:
                raise EvaluationConfigurationError(
                    "Multi-entrant (--group) evaluation does not support --baseline "
                    "comparison in this phase; compare two separate evaluations instead."
                )
            if len(request.opponent_ids) < 2:
                raise EvaluationConfigurationError(
                    "Multi-entrant (--group) evaluation requires at least two opponents "
                    "(a 3+ entrant roster); use ordinary 1v1 evaluation for a single opponent."
                )
        subject_ids = [request.candidate_id]
        if request.baseline_id is not None:
            subject_ids.append(request.baseline_id)
        all_ids = sorted(set(subject_ids) | set(request.opponent_ids))
        root = request.data_root or get_data_root()
        return {agent_id: _resolve_python_agent(root, agent_id) for agent_id in all_ids}

    def _effective_conditions(self, request: EvaluationRequest) -> EffectiveConditions:
        return effective_conditions_for(request.ticks, get_project_info().agent_api_version)

    def _evaluation_id(
        self,
        request: EvaluationRequest,
        identities: Mapping[str, dict[str, Any]],
        conditions: EffectiveConditions,
    ) -> str:
        """Derive the evaluation id from an already-frozen identity snapshot.

        Deliberately takes ``identities`` (a plain ``agent_id -> agent_identity()``
        dict), never ``specs``/``AgentSpec`` -- computing identity here via a
        second, independent ``agent_identity()`` call would re-read each
        entrant's source file from disk a second time, which could observe
        different bytes than whatever snapshot the caller persists as
        ``planned_identities`` if a source edit lands in between. Every
        caller must build ``identities`` exactly once and pass that same
        dict to both this method and ``_write_state`` (Sec 7/B1).
        """

        resolved_rules_id = request.resolved_rules_compatibility_id
        resolved_is_v2 = is_ruleset_v2_methodology(resolved_rules_id)
        resolved_group = request.group and resolved_is_v2
        payload: dict[str, Any] = {
            "identity_version": resolved_identity_version(resolved_is_v2, resolved_group),
            "candidate": identities[request.candidate_id],
            "baseline": (
                identities[request.baseline_id] if request.baseline_id is not None else None
            ),
            "opponents": [identities[opponent_id] for opponent_id in request.opponent_ids],
            "seeds": list(request.seeds),
            "ticks": request.ticks,
            "effective_conditions": asdict(conditions),
            # v0.10 Phase 2/v2.0.0-beta2 Phase 1: was the module constant
            # EVALUATION_RULES_COMPATIBILITY_ID unconditionally; now the
            # request's own resolved value -- for every v1 request (omitted
            # or explicit bytefray-rules-1) that resolved value is exactly
            # EVALUATION_RULES_COMPATIBILITY_ID, so this key's contribution
            # to the hash is byte-identical to before for every v1
            # evaluation_id ever computed. Only an explicit --ruleset
            # bytefray-rules-2 request ever changes this key's value.
            "rules_compatibility_id": resolved_rules_id,
            # v0.9 Phase 6 (Phase 5 spec Sec J.2/AA.4.2, sibling key, never
            # folded into "effective_conditions"): "fixed" for v0.9, a
            # second value for v2.0.0-beta2 Phase 1 1v1, a third for Phase
            # 2 group mode (resolved_arena_alignment_mode) -- never
            # collides across methodologies.
            "arena_alignment_mode": resolved_arena_alignment_mode(resolved_is_v2, resolved_group),
        }
        if resolved_group:
            # v2.0.0-beta2 Phase 2: multi-entrant identity. `orientation_
            # mode` is not meaningful here -- seat assignment (per cell,
            # not evaluation-wide) is the generalized scheduler-order axis
            # instead, so it is omitted rather than hashed as a stale
            # value. The actual resolved layout set (not just a mode
            # label) enters the hash directly, mirroring Phase 1F's own
            # "placements" precedent exactly -- two different N-seat
            # layout sets must never collide on evaluation_id.
            payload["group"] = True
            payload["layouts"] = [
                {"layout_id": layout.layout_id, "seat_starts": list(layout.seat_starts)}
                for layout in standard_layouts(len(request.roster_agent_ids))
            ]
        else:
            payload["orientation_mode"] = request.orientation_mode
            # Phase 1F: the actual resolved placement set, not just a mode
            # label -- two different v2 placement sets must never collide
            # on evaluation_id. Omitted entirely for v1 (placements is
            # always `None` there) so a v1 payload's key set is byte-
            # identical to every evaluation_id ever computed before Phase 1.
            if resolved_is_v2:
                payload["placements"] = [
                    {
                        "placement_id": placement.placement_id,
                        "subject_start": placement.subject_start,
                        "opponent_start": placement.opponent_start,
                    }
                    for placement in standard_placements()
                ]
        return stable_id("evaluation-v2", payload)

    def _resolve_revision_results(
        self,
        request: EvaluationRequest,
        specs: Mapping[str, AgentSpec],
        planned_identities: Mapping[str, dict[str, Any]],
        prior: Mapping[str, Any],
    ) -> dict[str, _RevisionPlanEntry]:
        """One ``_RevisionPlanEntry`` per distinct agent_id in ``specs``.

        Reused verbatim from ``prior`` when already recorded there (resume/
        retry must retain the originally planned revision ID -- never
        silently recompute one for an agent this evaluation has already
        durably planned, docs/specs/agent_revision.md Sec 4). Freshly
        archived otherwise, from the *same* ``walk_agent_files`` read used
        for the freeze-time consistency check immediately below -- one
        read, never a second independent one racing against
        ``agent_identity()``'s own (Sec 4.2).

        Must be called after ``planned_identities`` is built and after
        ``prior`` is loaded, but before ``evaluation_id``/anything derived
        from it is trusted for scheduling, and strictly before any cell
        executes or any checkpoint is written -- a detected mismatch (see
        below) raises out of this method, aborting ``run()`` before any of
        that happens.
        """

        prior_revisions = _prior_revision_by_agent_id(prior)
        root = request.data_root or get_data_root()
        store_root = agent_revisions_root(root)

        resolved: dict[str, _RevisionPlanEntry] = {}
        for agent_id, spec in specs.items():
            if agent_id in prior_revisions:
                resolved[agent_id] = prior_revisions[agent_id]
                continue

            # Not yet planned by any prior invocation of this evaluation --
            # archive fresh. `walk` is read exactly once and used for both
            # the cross-check below and the archive write itself
            # (`archive_agent_revision_from_walk`), so revision capture and
            # `planned_identities[agent_id]` describe the same source read
            # as closely as this process can prove (Sec 4.2): the frozen
            # `local_source_fingerprint` was computed moments earlier, in
            # this same freeze step, by `agent_identity()`'s own
            # independent read.
            walk = walk_agent_files(spec.dir)
            cross_check = local_python_subset_fingerprint(walk)
            if cross_check != planned_identities[agent_id].get("local_source_fingerprint"):
                raise EvaluationConfigurationError(
                    f"Revision archival observed source for agent {agent_id!r} that "
                    "does not match the frozen evaluation plan; aborting before any "
                    "cell executes. Source changed during evaluation planning -- "
                    "start a fresh evaluation."
                )

            result: RevisionArchivalResult = archive_agent_revision_from_walk(
                walk, store_root=store_root, source_agent_id=agent_id
            )
            resolved[agent_id] = _RevisionPlanEntry(result.agent_revision_id, result.error)
        return resolved

    # -- resume -----------------------------------------------------------

    def _resolve_from_state(
        self,
        cell: EvaluationCell,
        previous: Mapping[str, Any],
        specs: dict[str, AgentSpec],
        request: EvaluationRequest,
    ) -> EvaluationCell | None:
        status = previous.get("status")
        if status not in _TERMINAL_RESUME_STATUSES:
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

        if cell.is_group:
            expected_match_id = _expected_group_cell_match_id(
                specs,
                cell.seat_agent_ids,
                cell.seat_starts,
                cell.seed,
                request.ticks,
                cell.rules_compatibility_id,
            )
        else:
            expected_match_id = _expected_cell_match_id(
                specs[cell.subject_id],
                cell.subject_id,
                specs[cell.opponent_id],
                cell.opponent_id,
                cell.seed,
                request.ticks,
                cell.orientation,
                cell.rules_compatibility_id,
                cell.subject_start,
                cell.opponent_start,
            )
        mismatch = _resumed_cell_mismatch(envelope, cell, expected_match_id)
        if mismatch is not None:
            return replace(
                _cell_from_state(cell, previous),
                status="corrupted",
                error_code="resumed_result_mismatch",
                error_message=mismatch[:240],
            )
        resolved = _cell_from_envelope_group(cell, envelope) if cell.is_group else _cell_from_envelope(cell, envelope)
        return replace(
            resolved,
            execution_context_id=previous.get("execution_context_id"),
        )

    # -- execution --------------------------------------------------------

    def _execute_cell(
        self,
        cell: EvaluationCell,
        ticks: int,
        data_root: Path | None,
        planned_identities: Mapping[str, dict[str, Any]],
    ) -> CellExecutionResult:
        """Execute one cell. Pure apart from filesystem I/O under ``cell.artifact_
        dir`` and reading agent source under ``data_root``/the default data
        root -- no coordinator state is read or mutated, which is exactly what
        lets this run unchanged inside a worker subprocess (v1.6 Phase 2).

        Takes ``ticks``/``data_root`` directly rather than a whole
        ``EvaluationRequest`` -- these are the only two fields this method
        ever reads; narrowing the signature means a worker process can never
        accidentally gain access to a coordinator-only field (``resume``,
        ``retry_failures``, ``workers``, ...) that has no valid meaning
        per-cell.
        """

        root = data_root or get_data_root()
        drift = self._detect_pre_execution_drift(cell, planned_identities, root)
        if drift is not None:
            return CellExecutionResult(cell=replace(cell, status="drift_detected", **drift))

        # v2.0.0-beta2 Phase 2: a group cell is executed through an
        # entirely separate branch (agent_test.test_agents, not test_agent)
        # -- the pairwise path below is completely unmodified by this
        # addition, byte-for-byte, matching build_matrix's own "separate
        # function, early return" precedent for the same reason.
        if cell.is_group:
            return self._execute_group_cell(cell, ticks, data_root, root, planned_identities)

        # v0.9 Phase 6 (Phase 5 spec Sec H.1/T.4): `candidate_first` reuses
        # the exact historical call; `opponent_first` calls the same
        # unmodified executor with the two positional roles swapped --
        # this alone is the entire "opposite entrant orientation"
        # mechanism, no scheduler/executor change. Every subsequent
        # mapping in this method resolves physical slot <-> evaluation
        # role via `physical_slots_for_orientation`, never by assuming
        # subject==A/opponent==B.
        # v2.0.0-beta2 Phase 1 (design doc Sec Placement/Sec J): placement
        # describes *where the subject/opponent start*, independent of
        # which physical slot/scheduler order executes each role -- the
        # subject always starts at `cell.subject_start` regardless of
        # orientation, exactly like every other subject/opponent-role field
        # this method already resolves through orientation rather than
        # assuming subject==A/opponent==B.
        if cell.orientation == ORIENTATION_OPPONENT_FIRST:
            test_agent_id, test_opponent_id = cell.opponent_id, cell.subject_id
            test_agent_start, test_opponent_start = cell.opponent_start, cell.subject_start
        else:
            test_agent_id, test_opponent_id = cell.subject_id, cell.opponent_id
            test_agent_start, test_opponent_start = cell.subject_start, cell.opponent_start

        # Computed once here, after the pre-execution-drift early return
        # (which must keep making zero calls, matching the old closure's
        # exact behavior) -- current_execution_context() is a pure function
        # of environment (and this cell's own resolved Ruleset) only, so
        # every remaining branch below reuses this same value rather than
        # recomputing it. Reads `cell.rules_compatibility_id`, never the
        # module constant, so a v2 cell's execution context correctly
        # records "bytefray-rules-2" -- this method must stay a pure
        # function of its own arguments for v1.6 Phase 2 worker-subprocess
        # purity, so this cannot read `EvaluationRequest.ruleset_id`
        # directly.
        context = current_execution_context(cell.rules_compatibility_id)

        try:
            outcome = test_agent(
                test_agent_id,
                opponent=test_opponent_id,
                seed=cell.seed,
                ticks=ticks,
                timeout=None,
                trace=False,
                run_dir=cell.artifact_dir,
                data_root=data_root,
                ruleset_id=cell.rules_compatibility_id,
                agent_start=test_agent_start,
                opponent_start=test_opponent_start,
            )
        except AgentTestError as exc:
            return CellExecutionResult(
                cell=replace(
                    cell,
                    status="failed",
                    outcome=None,
                    error_code=exc.diagnostic.code,
                    error_message=" ".join(str(exc).split())[:240],
                    execution_context_id=context.context_id,
                ),
                execution_context=context,
            )
        if isinstance(outcome, InitializationFailureOutcome):
            # A ``RuntimeDiagnostic`` carries no source/version identity
            # fields (see ``python_runtime.RuntimeDiagnostic``), so unlike a
            # completed match there is no executor-recorded ground truth to
            # cross-check here. A live re-resolve against the frozen plan is
            # the only signal available -- it cannot detect an edit that
            # lands and then reverts before this point (the same documented
            # residual as ``_post_execution_identity_drift``), but it does
            # catch a durable edit that caused the observed initialization
            # failure, preventing that failure from being silently
            # attributed to the original, frozen agent (Sec 7 "initialization
            # failure after intervening source change").
            post_init_drift = self._detect_pre_execution_drift(cell, planned_identities, root)
            if post_init_drift is not None:
                return CellExecutionResult(
                    cell=replace(
                        cell,
                        status="drift_detected",
                        **post_init_drift,
                        execution_context_id=context.context_id,
                    ),
                    execution_context=context,
                )
            failed_slot = outcome.diagnostic.agent_id
            subject_slot, _opponent_slot = physical_slots_for_orientation(cell.orientation)
            result_outcome = (
                "subject_init_failed" if failed_slot == subject_slot else "opponent_init_failed"
            )
            return CellExecutionResult(
                cell=replace(
                    cell,
                    status="completed",
                    outcome=result_outcome,
                    error_code=outcome.diagnostic.code,
                    error_message=" ".join(outcome.diagnostic.message.split())[:240],
                    execution_context_id=context.context_id,
                ),
                execution_context=context,
            )
        post_drift = _post_execution_identity_drift(cell, outcome.match_result, planned_identities)
        if post_drift is not None:
            return CellExecutionResult(
                cell=replace(
                    cell,
                    status="drift_detected",
                    **post_drift,
                    execution_context_id=context.context_id,
                ),
                execution_context=context,
            )
        return CellExecutionResult(
            cell=replace(
                _cell_from_match_result(cell, outcome.match_result),
                execution_context_id=context.context_id,
            ),
            execution_context=context,
        )

    def _execute_group_cell(
        self,
        cell: EvaluationCell,
        ticks: int,
        data_root: Path | None,
        root: Path,
        planned_identities: Mapping[str, dict[str, Any]],
    ) -> CellExecutionResult:
        """The multi-entrant generalization of the pairwise branch of
        :meth:`_execute_cell` (v2.0.0-beta2 Phase 2).

        Same purity contract (pure apart from filesystem I/O under
        ``cell.artifact_dir``/reading agent source under ``root``) --
        called only from ``_execute_cell``, after the shared pre-execution
        drift check has already passed.
        """

        context = current_execution_context(cell.rules_compatibility_id)
        entrants = [
            GroupEntrantSpec(seat=seat_label(index), agent_id=agent_id, start=start)
            for index, (agent_id, start) in enumerate(
                zip(cell.seat_agent_ids, cell.seat_starts, strict=True)
            )
        ]

        try:
            outcome = test_agents(
                entrants,
                seed=cell.seed,
                ticks=ticks,
                timeout=None,
                trace=False,
                run_dir=cell.artifact_dir,
                data_root=data_root,
                ruleset_id=cell.rules_compatibility_id,
            )
        except AgentTestError as exc:
            return CellExecutionResult(
                cell=replace(
                    cell,
                    status="failed",
                    outcome=None,
                    error_code=exc.diagnostic.code,
                    error_message=" ".join(str(exc).split())[:240],
                    execution_context_id=context.context_id,
                ),
                execution_context=context,
            )
        if isinstance(outcome, GroupInitializationFailureOutcome):
            post_init_drift = self._detect_pre_execution_drift(cell, planned_identities, root)
            if post_init_drift is not None:
                return CellExecutionResult(
                    cell=replace(
                        cell,
                        status="drift_detected",
                        **post_init_drift,
                        execution_context_id=context.context_id,
                    ),
                    execution_context=context,
                )
            # "subject_init_failed" only when the *candidate's own* seat is
            # the one that failed to initialize -- any other failed seat is
            # reported as "opponent_init_failed", mirroring the pairwise
            # path's exact two-value vocabulary (Phase 2 does not introduce
            # a third "which opponent" outcome value here; the failed
            # agent's own id/seat is still fully recorded in error_message).
            result_outcome = (
                "subject_init_failed" if outcome.seat == cell.subject_seat else "opponent_init_failed"
            )
            return CellExecutionResult(
                cell=replace(
                    cell,
                    status="completed",
                    outcome=result_outcome,
                    error_code=outcome.diagnostic.code,
                    error_message=(
                        f"seat {outcome.seat} ({outcome.agent_id}): "
                        + " ".join(outcome.diagnostic.message.split())
                    )[:240],
                    execution_context_id=context.context_id,
                ),
                execution_context=context,
            )
        post_drift = _post_execution_identity_drift_group(cell, outcome.match_result, planned_identities)
        if post_drift is not None:
            return CellExecutionResult(
                cell=replace(
                    cell,
                    status="drift_detected",
                    **post_drift,
                    execution_context_id=context.context_id,
                ),
                execution_context=context,
            )
        return CellExecutionResult(
            cell=replace(
                _cell_from_match_result_group(cell, outcome.match_result),
                execution_context_id=context.context_id,
            ),
            execution_context=context,
        )

    def _detect_pre_execution_drift(
        self,
        cell: EvaluationCell,
        planned_identities: Mapping[str, dict[str, Any]],
        root: Path,
    ) -> dict[str, Any] | None:
        """Sec 7 pre-check: re-resolve and compare against the *frozen* plan.

        ``planned_identities`` must be a snapshot captured once at preflight
        time (never re-derived from a live ``AgentSpec.source_path``) -- both
        sides of this comparison reading the same evolving file would
        silently defeat drift detection. Catches a source/identity change
        between preflight and this specific cell's execution --
        ``agent_test.test_agent`` re-resolves both agents itself, so nothing
        else in this codepath would otherwise notice.
        """

        # v2.0.0-beta2 Phase 2: a group cell's `opponent_id` is a joined
        # display label (see EvaluationCell's own docstring), never a real
        # agent id -- resolving it would always fail. Check the real
        # per-seat roster instead; `dict.fromkeys` dedupes a repeated agent
        # id (self-play) so it is checked once, not once per occupied seat.
        role_and_agent_ids: tuple[tuple[str, str], ...] = (
            tuple(("roster", agent_id) for agent_id in dict.fromkeys(cell.seat_agent_ids))
            if cell.is_group
            else ((cell.subject_role, cell.subject_id), ("opponent", cell.opponent_id))
        )
        for role, agent_id in role_and_agent_ids:
            planned_identity = planned_identities.get(agent_id)
            if planned_identity is None:
                continue
            try:
                current = _resolve_python_agent(root, agent_id)
            except EvaluationConfigurationError as exc:
                return {
                    "error_code": "pre_execution_agent_unresolvable",
                    "error_message": f"{role} {agent_id!r} no longer resolves: {exc}"[:240],
                }
            current_identity = agent_identity(current)
            if planned_identity != current_identity:
                changed = sorted(
                    key
                    for key in planned_identity
                    if planned_identity[key] != current_identity[key]
                )
                return {
                    "error_code": "pre_execution_source_drift",
                    "error_message": (
                        f"{role} {agent_id!r} identity changed since preflight "
                        f"(fields: {', '.join(changed)})."
                    )[:240],
                }
        return None

    # -- aggregation --------------------------------------------------------

    def _all_aggregates(
        self, request: EvaluationRequest, cells: Sequence[EvaluationCell]
    ) -> tuple[SubjectAggregate, ...]:
        return all_subject_aggregates(request.candidate_id, request.baseline_id, cells)

    # -- persistence --------------------------------------------------------

    def _load_state(self, path: Path, evaluation_id: str, expected_schema_version: int) -> dict[str, Any]:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA_NAME:
            raise EvaluationConfigurationError(
                f"Existing evaluation state at {path} uses an unrecognized schema."
            )
        # v2.0.0-beta2 Phase 1: `expected_schema_version` is resolved from
        # *this* request's own methodology (v1 -> SCHEMA_VERSION, v2 ->
        # SCHEMA_VERSION_V2), never the bare module constant -- a v1 resume
        # request must keep matching only SCHEMA_VERSION exactly as before
        # (unaffected by SCHEMA_VERSION_V2 existing), and a v2 resume
        # request must fail closed against a differently-versioned existing
        # artifact rather than silently reinterpreting it.
        if data.get("schema_version") != expected_schema_version:
            raise EvaluationConfigurationError(
                f"Existing evaluation state at {path} uses unsupported schema version "
                f"{data.get('schema_version')!r} (expected {expected_schema_version})."
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
        planned_identities: Mapping[str, dict[str, Any]],
        revision_plan: Mapping[str, _RevisionPlanEntry],
        conditions: EffectiveConditions,
        created_at: str,
        lifecycle_state: str,
        execution_contexts: Sequence[Mapping[str, Any]],
        aggregates: Sequence[SubjectAggregate] = (),
        comparison: Sequence[ComparisonEntry] = (),
        finished_at: str | None = None,
        abort_reason: str | None = None,
        abort_detail: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist one checkpoint. Never re-derives entrant identity from disk.

        ``planned_identities`` must be the exact ``agent_id -> agent_identity()``
        snapshot ``run()`` built once at preflight (or an unchanged carry-over
        of a prior artifact's own recorded snapshot -- see the B2 resume
        path) -- this method only reshapes it into the persisted
        ``candidate``/``baseline``/``opponents`` structure by lookup, so the
        written ``planned_identities`` payload is structurally guaranteed to
        reproduce ``evaluation_id`` (both come from the same frozen dict; see
        ``_evaluation_id``).

        ``revision_plan`` (docs/specs/agent_revision.md Sec 5.2, revised)
        is rendered into its own **sibling top-level field**,
        ``agent_revisions`` -- never merged into ``planned_identities``
        itself. An earlier version of this method merged the two fields
        directly into each ``planned_identities.candidate``/``.baseline``/
        ``.opponents[]`` entry; that broke the existing, tested "B1"
        invariant (``test_persisted_planned_identity_rehashes_to_the_
        recorded_evaluation_id`` and siblings) that recomputing
        ``evaluation_id`` from ``planned_identities`` *as persisted in the
        artifact* must reproduce the stored value exactly -- a reader
        rehashing the persisted dict verbatim would have picked up the two
        extra keys and produced a different hash than the one actually
        stored. Keeping ``agent_revisions`` a wholly separate JSON key
        keeps ``planned_identities`` byte-for-byte identical to what
        ``_evaluation_id`` hashed, with no copying or filtering required to
        prove it -- the same object is written both times.
        """

        project = get_project_info()

        def _revision_payload(agent_id: str) -> dict[str, str | None]:
            entry = revision_plan.get(agent_id)
            return {
                "agent_revision_id": entry.agent_revision_id if entry is not None else None,
                "agent_revision_error": entry.agent_revision_error if entry is not None else None,
            }

        planned_identities_payload = {
            "candidate": planned_identities[request.candidate_id],
            "baseline": (
                planned_identities[request.baseline_id]
                if request.baseline_id is not None
                else None
            ),
            "opponents": [
                planned_identities[opponent_id] for opponent_id in request.opponent_ids
            ],
        }
        agent_revisions_payload = {
            "candidate": _revision_payload(request.candidate_id),
            "baseline": (
                _revision_payload(request.baseline_id) if request.baseline_id is not None else None
            ),
            "opponents": [_revision_payload(opponent_id) for opponent_id in request.opponent_ids],
        }
        conditions_dict = asdict(conditions)
        resolved_rules_id = request.resolved_rules_compatibility_id
        resolved_is_v2 = is_ruleset_v2_methodology(resolved_rules_id)
        resolved_group = request.group and resolved_is_v2
        write_json_atomic(
            path,
            {
                "schema": SCHEMA_NAME,
                # v2.0.0-beta2 Phase 1: resolved per request, never the bare
                # module constant -- for every v1 request (omitted or
                # explicit bytefray-rules-1) this is exactly SCHEMA_VERSION/
                # IDENTITY_VERSION (4), byte-identical to every artifact
                # this module has ever written. An explicit --ruleset
                # bytefray-rules-2 1v1 request writes SCHEMA_VERSION_V2/
                # IDENTITY_VERSION_V2 (5, Phase 1); a --group request on top
                # of that writes SCHEMA_VERSION_V2_GROUP/
                # IDENTITY_VERSION_V2_GROUP (6, Phase 2) -- each a brand-new
                # artifact shape with no historical instance to stay
                # compatible with.
                "schema_version": resolved_schema_version(resolved_is_v2, resolved_group),
                "identity_version": resolved_identity_version(resolved_is_v2, resolved_group),
                "evaluation_id": evaluation_id,
                "candidate_id": request.candidate_id,
                "baseline_id": request.baseline_id,
                "opponent_ids": list(request.opponent_ids),
                "seeds": list(request.seeds),
                "ticks": request.ticks,
                "matrix_size": len(matrix),
                "planned_identities": planned_identities_payload,
                "agent_revisions": agent_revisions_payload,
                "effective_conditions": conditions_dict,
                "effective_conditions_fingerprint": stable_id(
                    "evaluation-conditions", conditions_dict
                ),
                "rules_compatibility_id": resolved_rules_id,
                # v0.9 Phase 6: sibling top-level fields, same pattern as
                # rules_compatibility_id immediately above (Phase 5 spec
                # Sec AA.3/AA.4) -- evaluation-wide methodology, never
                # folded into effective_conditions.
                "orientation_mode": request.orientation_mode,
                "arena_alignment_mode": resolved_arena_alignment_mode(resolved_is_v2, resolved_group),
                # v2.0.0-beta2 Phase 2: additive top-level disclosure of
                # multi-entrant methodology -- never identity-affecting on
                # its own (the resolved layout set already is, via
                # arena_alignment_mode's distinct value and each cell's own
                # roster/seat fields); purely for `evaluations show`/`list`
                # and JSON consumers to see at a glance without scanning
                # cells.
                "group": resolved_group,
                "roster_agent_ids": list(request.canonical_roster) if resolved_group else None,
                "created_at": created_at,
                "updated_at": _utc_now_iso(),
                "finished_at": finished_at,
                "lifecycle_state": lifecycle_state,
                "abort_reason": abort_reason,
                "abort_detail": dict(abort_detail) if abort_detail is not None else None,
                "execution_contexts": [dict(item) for item in execution_contexts],
                # Writer/resumer bookkeeping only (which Bytefray build most
                # recently touched this artifact) -- refreshed on every
                # write, including a no-op resume under a different
                # runtime. It is *not* cell execution provenance; that is
                # `execution_contexts`/each cell's own `execution_context_id`
                # (Sec 6/H2), which are never rewritten by a resuming
                # process (M1).
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
    # v2.0.0-beta2 Phase 1/2: a caller reading an arbitrary on-disk
    # artifact (unlike _load_state, which already knows this run's own
    # resolved methodology) cannot know in advance whether it is a v1
    # (SCHEMA_VERSION), v2 1v1 (SCHEMA_VERSION_V2), or v2 group
    # (SCHEMA_VERSION_V2_GROUP) artifact -- all three are equally "this
    # module's own current schema," just under different resolved
    # methodologies.
    _supported_versions = (SCHEMA_VERSION, SCHEMA_VERSION_V2, SCHEMA_VERSION_V2_GROUP)
    if data.get("schema_version") not in _supported_versions:
        raise EvaluationConfigurationError(
            f"{path}: unsupported schema version {data.get('schema_version')!r} "
            f"(expected one of {_supported_versions})."
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
    parser.add_argument(
        "candidate_id",
        nargs="?",
        default=None,
        help="candidate agent's discovery id (may instead be set by --preset)",
    )
    parser.add_argument(
        "--preset",
        default=None,
        help=(
            "name of a bytefray.evaluation_preset (see 'bytefray agents "
            "evaluation-presets') supplying default values for any option not "
            "explicitly given below; an explicit option always overrides the "
            "preset. Never affects evaluation_id or any per-cell result -- see "
            "docs/V1_6_PHASE3_EVALUATION_PRESETS.md."
        ),
    )
    parser.add_argument(
        "--baseline", default=None, help="baseline agent's discovery id to compare against"
    )
    parser.add_argument(
        "--ruleset",
        choices=[BYTEFRAY_RULESET_ID, BYTEFRAY_RULESET_V2_ID],
        default=None,
        help=(
            f"gameplay Ruleset identity (default: {BYTEFRAY_RULESET_ID}, the historical "
            f"evaluation methodology, unchanged). {BYTEFRAY_RULESET_V2_ID} runs the "
            "balanced Ruleset-v2 1v1 methodology: standard placement set, standard seed "
            "set default, and capture/core evidence. See "
            "docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md."
        ),
    )
    parser.add_argument(
        "--opponents",
        default=None,
        help="comma-separated opponent discovery ids (may instead be set by --preset)",
    )
    parser.add_argument(
        "--group",
        action="store_true",
        help=(
            "multi-entrant methodology: field the candidate and every --opponents "
            "entry TOGETHER as one N-entrant roster each cell (standard layouts x "
            "standard seat permutations), instead of one pairwise 1v1 cell per "
            "opponent. Requires --ruleset bytefray-rules-2 and at least two "
            "--opponents (a 3+ entrant roster); does not support --baseline in this "
            "phase. See docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md."
        ),
    )
    seed_group = parser.add_mutually_exclusive_group()
    seed_group.add_argument("--seeds", default=None, help="comma-separated explicit seeds")
    seed_group.add_argument(
        "--seed-range", default=None, help="inclusive seed range START:END"
    )
    parser.add_argument(
        "--ticks",
        type=_positive_int,
        default=None,
        help=f"tick budget per cell (default: {DEFAULT_TICKS}, unless set by --preset)",
    )
    parser.add_argument("--output", type=Path, default=None, help="evaluation artifact directory")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the matrix and exit without running anything"
    )
    parser.add_argument("--quiet", action="store_true")
    orientation_group = parser.add_mutually_exclusive_group()
    orientation_group.add_argument(
        "--single-orientation",
        action="store_true",
        default=None,
        help=(
            "opt out of the both-entrant-orientations methodology; candidate_first "
            "only, matching pre-v0.9 behavior and matrix size. Overrides --preset. "
            "Does not generalize across entrant order -- see docs/AGENT_LAB.md."
        ),
    )
    orientation_group.add_argument(
        "--both-orientations",
        action="store_true",
        default=None,
        help=(
            "force the both-entrant-orientations methodology, overriding a "
            "--preset that requested single-orientation. Redundant with the "
            "ordinary default when no --preset is given."
        ),
    )
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=1,
        help=(
            "number of evaluation cells to execute concurrently, via a pool of "
            "long-lived worker subprocesses (default: 1, serial). Never affects "
            "evaluation_id or any per-cell result -- only wall-clock speed. Never "
            "settable by --preset -- execution machinery, not experiment content. "
            "See docs/V1_6_PHASE2_PARALLEL_EVALUATION.md."
        ),
    )
    return parser


def _resolve_seeds(args: argparse.Namespace) -> tuple[int, ...]:
    if args.seeds is not None:
        return parse_seed_list(args.seeds)
    if args.seed_range is not None:
        return parse_seed_range(args.seed_range)
    return (Config().seed,)


def methodology_lines(
    orientation_mode: str, *, arena_alignment_mode: str = EVALUATION_ARENA_ALIGNMENT_MODE
) -> tuple[str, str]:
    """Shared human-readable methodology disclosure (Phase 5 spec Sec O.1/AA.5).

    Takes the same ``orientation_mode`` string vocabulary
    (``ORIENTATION_MODE_BOTH``/``ORIENTATION_MODE_CANDIDATE_FIRST_ONLY``)
    identity/provenance already use, rather than a bare bool, so both the
    live-run CLI (``request.orientation_mode``) and the historical-read
    path (``evaluation_history``'s recovered/recorded
    ``EvaluationSummary.orientation_mode.value``) can call this one shared
    function -- never two independently authored copies of the same
    wording (Designer reuses it too, via
    ``app.services.designer_workflows``). Must never describe a
    both-orientations evaluation as "fully unbiased"/"fully robust": it
    discloses entrant-orientation coverage and, separately, that arena
    alignment is always fixed in v0.9 (translation robustness is not
    evaluated -- Sec AA.1/AA.2).
    """

    orientation_line = (
        "Entrant orientation: both"
        if orientation_mode == ORIENTATION_MODE_BOTH
        else (
            "Entrant orientation: candidate-first only — does not generalize "
            "across entrant order"
        )
    )
    alignment_line = (
        f"Arena alignment: {arena_alignment_mode} — translation robustness not evaluated"
    )
    return orientation_line, alignment_line


def _print_v2_methodology(request: EvaluationRequest, matrix: Sequence[EvaluationCell]) -> None:
    """Phase 1S: make an expanded v2 matrix's size/conditions obvious up front.

    Never left to be inferred from a final win rate -- a permanent-v2
    evaluation multiplies every opponent's cell count by
    ``len(standard_placements()) * (2 if both_orientations else 1)``, which
    a user must see stated plainly, not reverse-engineer from ``matches:``.
    """

    print(f"ruleset: {request.resolved_rules_compatibility_id}")
    print(f"seeds: {', '.join(str(seed) for seed in request.seeds)}")
    if request.group:
        _print_group_methodology(request)
        return
    placements = standard_placements()
    orientations = 2 if request.both_orientations else 1
    cells_per_opponent = len(request.seeds) * len(placements) * orientations
    print(f"placements: {len(placements)} ({', '.join(p.placement_id for p in placements)})")
    print(f"scheduler orders: {'balanced' if request.both_orientations else 'candidate-first only'}")
    print(f"cells/opponent: {cells_per_opponent}")


def _print_group_methodology(request: EvaluationRequest) -> None:
    """v2.0.0-beta2 Phase 2: multi-entrant matrix disclosure, mirroring
    the 1v1 disclosure above exactly -- ruleset/seeds are already printed
    by the caller; roster/layout/permutation/cell-count are this mode's
    own additional dimensions.
    """

    roster = request.roster_agent_ids
    layouts = standard_layouts(len(roster))
    seat_assignments = enumerate_seat_assignments(roster)
    cells = len(request.seeds) * len(layouts) * len(seat_assignments)
    print(f"roster: {', '.join(roster)} ({len(roster)} entrants)")
    print(f"layouts: {len(layouts)} ({', '.join(layout.layout_id for layout in layouts)})")
    print(f"seat assignments: {len(seat_assignments)}")
    print(f"cells: {cells}")


def _print_matrix(
    request: EvaluationRequest,
    matrix: Sequence[EvaluationCell],
    preset: EvaluationPreset | None = None,
) -> None:
    if preset is not None:
        print(f"preset: {preset.name}  (content_digest={preset.content_digest})")
    print(f"candidate: {request.candidate_id}")
    print(f"baseline: {request.baseline_id if request.baseline_id else 'none'}")
    print(f"opponents: {', '.join(request.opponent_ids)}")
    if request.is_v2_methodology:
        _print_v2_methodology(request, matrix)
    else:
        print(f"seeds: {', '.join(str(seed) for seed in request.seeds)}")
    print(f"ticks: {request.ticks}")
    # v2.0.0-beta2 Phase 2: "subjects: N opponents: M" and the 2-value
    # "Entrant orientation: both/candidate-first only" line both describe
    # 1v1 methodology's own axes (subject_role, orientation) -- neither is
    # a meaningful description of a group evaluation's roster/seat-
    # assignment axes, and printing them anyway would misrepresent group
    # semantics as if a 2-value orientation were still the scheduler-order
    # axis (Phase 2 design-audit finding). `_print_group_methodology`
    # already discloses roster/layouts/seat assignments above; only the
    # arena-alignment line (still correct and useful for group -- it names
    # the resolved group methodology identifier) is kept.
    if not request.group:
        subjects = [request.candidate_id] + ([request.baseline_id] if request.baseline_id else [])
        print(f"subjects: {len(subjects)}  opponents: {len(request.opponent_ids)}  seeds: {len(request.seeds)}")
    print(f"matches: {len(matrix)}")
    _, alignment_line = methodology_lines(
        request.orientation_mode,
        arena_alignment_mode=resolved_arena_alignment_mode(request.is_v2_methodology, request.group),
    )
    if not request.group:
        orientation_line, _ = methodology_lines(request.orientation_mode)
        print(orientation_line)
    print(alignment_line)


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


def _print_orientation_breakdown(subject_aggregates: Sequence[SubjectAggregate]) -> None:
    """K.2: a compact per-orientation win-rate line alongside the pooled block.

    Never averages an orientation split away -- printed only alongside the
    pooled aggregate, so a regression hidden by pooling (candidate wins
    every candidate-first cell but loses every opponent-first cell) stays
    visible in the ordinary, non-verbose CLI output.
    """

    candidate_first = next(
        (a for a in subject_aggregates if a.orientation_scope == ORIENTATION_CANDIDATE_FIRST), None
    )
    opponent_first = next(
        (a for a in subject_aggregates if a.orientation_scope == ORIENTATION_OPPONENT_FIRST), None
    )
    if candidate_first is not None and opponent_first is not None:
        print(
            f"  candidate_first: {candidate_first.win_rate_display}   "
            f"opponent_first: {opponent_first.win_rate_display}"
        )


def _print_comparison_entry(entry: ComparisonEntry, ticks: int) -> None:
    placement_suffix = f" placement={entry.placement_id}" if entry.placement_id != "fixed" else ""
    print(
        f"  opponent={entry.opponent_id} seed={entry.seed} orientation={entry.orientation}"
        f"{placement_suffix}"
    )
    print(f"    candidate: {entry.candidate_outcome}  baseline: {entry.baseline_outcome}")
    if entry.reason:
        print(f"    reason: {entry.reason}")
    if entry.candidate_score is not None and entry.baseline_score is not None:
        print(f"    score: candidate={entry.candidate_score:g} baseline={entry.baseline_score:g}")
    print(
        "    rerun candidate: "
        f"{rerun_command('<candidate>', entry.opponent_id, entry.seed, ticks, entry.orientation)}"
    )
    if entry.baseline_outcome is not None:
        print(
            "    rerun baseline:  "
            f"{rerun_command('<baseline>', entry.opponent_id, entry.seed, ticks, entry.orientation)}"
        )


def _print_evidence(analysis: Any) -> None:
    """v1.6 Phase 4 (docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md Sec 12): a
    concise Wilson-interval + exact paired evidence block -- magnitude and
    sample size shown before any p-value, never a bare
    SIGNIFICANT/NOT SIGNIFICANT verdict. ``analysis`` is an
    ``evaluation_analysis.EvaluationAnalysis``, typed as ``Any`` here only
    to avoid a top-level circular import (``evaluation_analysis`` imports
    from this module); see the deferred import at each call site.
    """

    from battle_engine.evaluation_analysis import EvidenceState

    def _rate_line(label: str, estimate: Any) -> str:
        interval = estimate.win_interval
        if interval is None:
            return f"  {label}: insufficient data (0 scored matches)"
        pct = 100.0 * (estimate.observed_win_rate or 0.0)
        return (
            f"  {label}: {estimate.wins}/{estimate.matches_played} ({pct:.0f}%)  "
            f"{round(interval.confidence_level * 100)}% CI "
            f"[{100.0 * interval.lower:.0f}%, {100.0 * interval.upper:.0f}%]"
        )

    print("evidence:")
    print(_rate_line(f"candidate ({analysis.candidate_id})", analysis.candidate_overall))
    if analysis.baseline_overall is not None:
        print(_rate_line(f"baseline ({analysis.baseline_id})", analysis.baseline_overall))
    paired = analysis.overall_paired
    if paired is not None:
        if paired.state == EvidenceState.NO_MATCHED_CONDITIONS:
            print("  paired: no matched candidate/baseline conditions")
        elif paired.state == EvidenceState.NO_DISCORDANT_PAIRS:
            print(
                f"  paired: {paired.paired_count} matched conditions, no discordant pairs "
                "(all unchanged/inconclusive) -- interval/exact test not meaningful"
            )
        else:
            interval = paired.better_interval
            assert interval is not None and paired.exact_p_value is not None
            print(
                f"  paired: candidate better in {paired.improved}/{paired.discordant} discordant "
                f"conditions ({100.0 * (paired.better_proportion_of_discordant or 0.0):.0f}%)  "
                f"{round(interval.confidence_level * 100)}% CI "
                f"[{100.0 * interval.lower:.0f}%, {100.0 * interval.upper:.0f}%]  "
                f"exact two-sided p={paired.exact_p_value:.3g}"
            )
        print(f"  {analysis.opponent_consistency}")
        print(f"  {analysis.orientation_consistency}")


def _fmt_fraction_pct(value: float | None) -> str:
    return f"{100.0 * value:.0f}%" if value is not None else "n/a"


def _fmt_percent(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "n/a"


def _fmt_rate(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _print_behavior(analysis: Any) -> None:
    """v1.6 Phase 5 (docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md Sec 18): a concise
    behavior-profile block -- survival, write activity, territory
    occupancy/retention, kill interaction -- describing *how* the
    candidate played, deliberately kept separate from the evidence: block
    above (which describes outcome) and never derived from it. ``analysis``
    is an ``evaluation_behavior.BehaviorAnalysis``, typed ``Any`` here only
    to avoid a top-level circular import (mirrors ``_print_evidence``'s
    existing pattern -- ``evaluation_behavior`` imports from this module).
    """

    from battle_engine.evaluation_behavior import largest_bounded_differences

    overall = analysis.candidate_overall
    if overall.sample_count == 0:
        return
    survival = overall.dimension("survival_fraction")
    writes = overall.dimension("writes_per_tick")
    last = overall.dimension("territory_last_pct")
    peak = overall.dimension("territory_max_pct")
    avg = overall.dimension("territory_avg_pct")
    retention = overall.dimension("territory_retention")
    kills = overall.dimension("kills_per_match")
    deaths = overall.dimension("deaths_per_match")
    print("behavior:")
    print(
        f"  survival: {_fmt_fraction_pct(survival.mean)} (n={survival.n})   "
        f"writes/tick: {_fmt_rate(writes.mean)}"
    )
    print(
        f"  territory: last={_fmt_percent(last.mean)}  peak={_fmt_percent(peak.mean)}  "
        f"avg={_fmt_percent(avg.mean)}  retention={_fmt_fraction_pct(retention.mean)}"
    )
    print(f"  kills: {_fmt_rate(kills.mean)}/match   deaths: {_fmt_rate(deaths.mean)}/match")
    orientation_largest = largest_bounded_differences(analysis.candidate_orientation_deltas, limit=2)
    if orientation_largest:
        print(f"  orientation-sensitive dimensions: {', '.join(orientation_largest)}")
    if analysis.candidate_vs_baseline_largest:
        print(
            "  largest candidate-vs-baseline behavioral differences: "
            + ", ".join(analysis.candidate_vs_baseline_largest)
        )


def _print_capture_aggregate(aggregate: Any) -> None:
    print(f"  captures caused: {aggregate.captures_caused}/{aggregate.available_count}")
    print(f"  captures suffered: {aggregate.captures_suffered}/{aggregate.available_count}")
    print(
        f"  capture rate: caused={_fmt_fraction_pct(aggregate.capture_rate_caused)} "
        f"suffered={_fmt_fraction_pct(aggregate.capture_rate_suffered)}"
    )
    print(f"  survival rate (capture-avoidance): {_fmt_fraction_pct(aggregate.survival_rate)}")
    if aggregate.capture_ticks:
        print(
            f"  capture tick: mean={_fmt_rate(aggregate.mean_capture_tick)} "
            f"median={_fmt_rate(aggregate.median_capture_tick)}"
        )


def _print_capture(analysis: Any) -> None:
    print("capture/core evidence:")
    print(f"[candidate] {analysis.candidate_id}")
    _print_capture_aggregate(analysis.candidate_overall)
    if analysis.baseline_overall is not None:
        print(f"[baseline] {analysis.baseline_id}")
        _print_capture_aggregate(analysis.baseline_overall)


def _print_result(result: EvaluationResult, request: EvaluationRequest) -> None:
    print(f"evaluation: {result.evaluation_id}")
    # v2.0.0-beta2 Phase 2: skip the 1v1-only "Entrant orientation:" line
    # for a group evaluation -- see _print_matrix's identical guard.
    orientation_line, alignment_line = methodology_lines(
        request.orientation_mode,
        arena_alignment_mode=resolved_arena_alignment_mode(request.is_v2_methodology, request.group),
    )
    if not request.group:
        print(orientation_line)
    print(alignment_line)
    for aggregate in result.aggregates:
        if aggregate.orientation_scope != "all":
            continue
        _print_aggregate(aggregate)
        # v2.0.0-beta2 Phase 2: orientation is not a meaningful axis for a
        # group cell (seat assignment is the generalized scheduler-order
        # axis instead, per-cell, never pooled into an evaluation-wide
        # orientation breakdown) -- every group cell defaults to
        # "candidate_first" (EvaluationCell.orientation's own sentinel),
        # so printing this breakdown for a group evaluation would show a
        # misleading "opponent_first: 0" rather than "not applicable".
        if request.both_orientations and not request.group:
            subject_aggregates = [
                a
                for a in result.aggregates
                if a.subject_role == aggregate.subject_role and a.subject_id == aggregate.subject_id
            ]
            _print_orientation_breakdown(subject_aggregates)
    # v2.0.0-beta2 Phase 2: evaluation_behavior/evaluation_capture's Tier-2
    # readers resolve the subject's physical match slot via `cell.
    # orientation` (a 2-value candidate_first/opponent_first axis) --
    # meaningless for a group cell, whose subject occupies whichever seat
    # `cell.subject_seat` says, not a fixed slot "A". Rather than silently
    # read the WRONG seat's result.json entry (candidate's seat varies per
    # cell in group mode), this is deferred explicitly to a later phase --
    # see docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md's "analysis
    # compatibility" section.
    if request.group:
        print("behavior/capture analysis: deferred for multi-entrant evaluations (see design doc)")
    else:
        from battle_engine.evaluation_behavior import (
            analyze_behavior,
            cell_ref_from_evaluation_cell,
        )

        scored_refs = [cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
        _print_behavior(analyze_behavior(request.candidate_id, request.baseline_id, scored_refs))
        if request.is_v2_methodology:
            from battle_engine.evaluation_capture import analyze_capture

            _print_capture(analyze_capture(request.candidate_id, request.baseline_id, scored_refs))
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
        from battle_engine.evaluation_analysis import analyze as _analyze_evaluation

        _print_evidence(
            _analyze_evaluation(request.candidate_id, request.baseline_id, result.cells)
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
    drifted = result.drift_cells
    if drifted:
        print(
            "SOURCE DRIFT DETECTED -- evaluation aborted; matrix execution stopped "
            "before completion. Start a fresh evaluation to evaluate the changed agent:"
        )
        for cell in drifted:
            print(
                f"  {cell.subject_role}={cell.subject_id} opponent={cell.opponent_id} "
                f"seed={cell.seed} code={cell.error_code} error={cell.error_message}"
            )
    print(f"evaluation artifact: {result.state_path}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    # v1.6 Phase 3: resolution layering is (1) ordinary defaults, (2) the
    # --preset (if any), (3) an explicit CLI option -- explicit always wins.
    # This is the one authoritative resolution path: a preset only ever
    # supplies values into the same variables an explicit invocation would
    # set directly below, so nothing downstream of this block (preflight,
    # EvaluationRequest, evaluation_id) can tell a preset was involved. See
    # docs/V1_6_PHASE3_EVALUATION_PRESETS.md.
    preset: EvaluationPreset | None = None
    if args.preset is not None:
        try:
            preset = load_preset(get_data_root(), args.preset)
        except EvaluationPresetError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    candidate_id = args.candidate_id
    if candidate_id is None and preset is not None:
        candidate_id = preset.candidate_id
    if candidate_id is None:
        print(
            "ERROR: candidate is required (supply it as a positional argument, "
            "or set 'candidate' in the --preset).",
            file=sys.stderr,
        )
        return 2

    baseline_id = args.baseline
    if baseline_id is None and preset is not None:
        baseline_id = preset.baseline_id

    # v2.0.0-beta2 Phase 1: resolved before seeds -- the standard v2 seed
    # default (below) depends on whether this evaluation is v1 or v2
    # methodology. Same three-tier resolution as every other option
    # (explicit CLI > --preset > ordinary default); "ordinary default" here
    # is `None` (v1, unchanged), never silently promoted to v2.
    ruleset_id = args.ruleset
    if ruleset_id is None and preset is not None:
        ruleset_id = preset.ruleset_id
    resolved_is_v2 = ruleset_id is not None and is_ruleset_v2_methodology(
        resolve_evaluation_ruleset_id(ruleset_id)
    )

    try:
        if args.opponents is not None:
            opponent_ids = parse_opponents(args.opponents)
        elif preset is not None and preset.opponent_ids is not None:
            opponent_ids = preset.opponent_ids
        else:
            raise EvaluationConfigurationError(
                "opponents are required (supply --opponents, or set 'opponents' "
                "in the --preset)."
            )

        if args.seeds is not None or args.seed_range is not None:
            seeds = _resolve_seeds(args)
        elif preset is not None and preset.seeds is not None:
            seeds = preset.seeds
        elif preset is not None and preset.seed_range is not None:
            seeds = tuple(range(preset.seed_range[0], preset.seed_range[1] + 1))
        elif resolved_is_v2:
            # Phase 1D: permanent-v2's standard seed methodology -- an
            # explicit --seeds/--seed-range or --preset seed selection
            # always overrides this (see the branches above, checked
            # first).
            seeds = STANDARD_V2_SEEDS
        else:
            seeds = (Config().seed,)
    except EvaluationConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.ticks is not None:
        ticks = args.ticks
    elif preset is not None and preset.ticks is not None:
        ticks = preset.ticks
    else:
        ticks = DEFAULT_TICKS

    if args.single_orientation:
        both_orientations = False
    elif args.both_orientations:
        both_orientations = True
    elif preset is not None and preset.orientation is not None:
        both_orientations = preset.orientation == _PRESET_ORIENTATION_BOTH
    else:
        both_orientations = True

    service = EvaluationService()
    try:
        _specs, evaluation_id = service.preflight(
            candidate_id=candidate_id,
            opponent_ids=opponent_ids,
            seeds=seeds,
            baseline_id=baseline_id,
            ticks=ticks,
            both_orientations=both_orientations,
            ruleset_id=ruleset_id,
            group=args.group,
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
        candidate_id=candidate_id,
        opponent_ids=opponent_ids,
        seeds=seeds,
        output_dir=output_dir,
        baseline_id=baseline_id,
        ticks=ticks,
        retry_failures=args.retry_failed,
        both_orientations=both_orientations,
        workers=args.workers,
        ruleset_id=ruleset_id,
        group=args.group,
    )
    matrix = build_matrix(request, evaluation_id)
    if not args.quiet or args.dry_run:
        _print_matrix(request, matrix, preset)
    if args.dry_run:
        return 0

    try:
        result = service.run(request)
    except EvaluationConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        _print_result(result, request)
    return 1 if (result.failed_cells or result.corrupted_cells or result.drift_cells) else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASELINE",
    "BYTEFRAY_RULESET_ID",
    "BYTEFRAY_RULESET_V2_ID",
    "CANDIDATE",
    "EVALUATION_ARENA_ALIGNMENT_MODE",
    "EVALUATION_ARENA_ALIGNMENT_MODE_V2_GROUP_STANDARD",
    "EVALUATION_ARENA_ALIGNMENT_MODE_V2_STANDARD",
    "EVALUATION_RULES_COMPATIBILITY_ID",
    "IDENTITY_VERSION",
    "IDENTITY_VERSION_V2",
    "IDENTITY_VERSION_V2_GROUP",
    "LOCAL_SOURCE_FINGERPRINT_VERSION",
    "ORIENTATION_CANDIDATE_FIRST",
    "ORIENTATION_MODE_BOTH",
    "ORIENTATION_MODE_CANDIDATE_FIRST_ONLY",
    "ORIENTATION_OPPONENT_FIRST",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "SCHEMA_VERSION_V2",
    "SCHEMA_VERSION_V2_GROUP",
    "STANDARD_V2_SEEDS",
    "ComparisonEntry",
    "EffectiveConditions",
    "EvaluationCell",
    "EvaluationConfigurationError",
    "EvaluationLayout",
    "EvaluationPlacement",
    "EvaluationRequest",
    "EvaluationResult",
    "EvaluationSeatAssignment",
    "EvaluationService",
    "ExecutionContext",
    "SubjectAggregate",
    "agent_identity",
    "aggregate_cells",
    "all_subject_aggregates",
    "build_matrix",
    "classify",
    "compare_candidate_baseline",
    "current_execution_context",
    "effective_conditions_for",
    "enumerate_seat_assignments",
    "is_ruleset_v2_methodology",
    "local_source_fingerprint",
    "main",
    "methodology_lines",
    "parse_opponents",
    "parse_seed_list",
    "parse_seed_range",
    "physical_slots_for_orientation",
    "read_evaluation",
    "rerun_command",
    "resolve_evaluation_ruleset_id",
    "resolved_arena_alignment_mode",
    "resolved_identity_version",
    "resolved_schema_version",
    "seat_label",
    "source_digest",
    "standard_layouts",
    "standard_placements",
]
