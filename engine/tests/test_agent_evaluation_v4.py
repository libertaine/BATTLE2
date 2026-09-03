"""Stable v4 evaluation methodology (v4.0.0-rc1 Phase 1, updated for Phase 2).

Covers docs/research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md's accepted
Sec H specification -- schema 7, arena pinned to 512, 8 deterministic
placement samples, both orientations paired over the same seat-bound
geometry -- and the F.6 evaluation-state-integrity remediation this phase
implements alongside it (an evaluation must never be represented as
successfully complete merely because the scheduler finished attempting
every cell).

Every evaluation here runs through the real ``EvaluationService``/CLI
``main()`` against real, minimal Python agents -- never a hand-built
``EvaluationCell``/artifact -- so a claim like "the schedule has 16 cells"
or "the CLI resolves omitted --ruleset to alpha2" is evidence from an
actual execution, not merely a plausible-looking assertion. See
test_evaluation_history_comparison.py for the (deliberately different, and
separately justified) hand-built-fixture convention used for comparison.py,
a pure function over already-adapted data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    IDENTITY_VERSION_V4,
    LIFECYCLE_STATE_FINISHED,
    LIFECYCLE_STATE_FINISHED_WITH_FAILURES,
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_OPPONENT_FIRST,
    SCHEMA_VERSION_V4,
    STANDARD_V4_ARENA_SIZE,
    STANDARD_V4_SEEDS,
    EvaluationConfigurationError,
    EvaluationRequest,
    EvaluationService,
    is_ruleset_v4_methodology,
    resolve_v4_seed_geometry,
)
from battle_engine.agent_evaluation import main as evaluate_main
from battle_engine.evaluation_history.discovery import adapt_any
from battle_engine.evaluation_history.models import FieldConfidence
from battle_engine.evaluation_history.verification import verify_summary
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
    BYTEFRAY_RULESET_V4_ID,
)

API_V2_SOURCE = """
from battle_engine.agent_api import ActionKindV2, AgentAction, ObservationV2, ProcessDeclaration

class Agent:
    def reset(self, context):
        self.context = context
    def declare_processes(self):
        return [ProcessDeclaration("p", 16, 1.0)]
    def act(self, observation):
        if not isinstance(observation, ObservationV2):
            raise TypeError("expected ObservationV2")
        return AgentAction(ActionKindV2.MOVE, 1)

def create_agent():
    return Agent()
"""

API_V1_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
"""


def _write_api_v2_agent(root: Path, name: str, source: str = API_V2_SOURCE) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "name": name,
                "kind": "python",
                "api_version": 2,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(source, encoding="utf-8")
    return directory


def _write_api_v1_agent(root: Path, name: str, source: str = API_V1_SOURCE) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "name": name,
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(source, encoding="utf-8")
    return directory


def _v4_request(tmp_path: Path, **overrides) -> EvaluationRequest:
    defaults = {
        "candidate_id": "candidate",
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "eval-out",
        "ticks": 5,
        "data_root": tmp_path,
        "ruleset_id": BYTEFRAY_RULESET_V4_ALPHA2_ID,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


# ---------------------------------------------------------------------------
# v4 evaluation schedule (research report Sec H.1)
# ---------------------------------------------------------------------------


def test_default_seeds_are_the_standard_v4_eight(tmp_path: Path):
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=STANDARD_V4_SEEDS)
    result = EvaluationService().run(request)
    assert STANDARD_V4_SEEDS == (1, 2, 3, 4, 5, 6, 7, 8)
    assert {cell.seed for cell in result.cells} == set(STANDARD_V4_SEEDS)


def test_schedule_cardinality_is_k_times_two_orientations_times_opponents(tmp_path: Path):
    """N opponents x 8 seeds x 2 orientations = 16N matches (research report
    Sec H.1 item 12) -- guards against an accidental Cartesian-product bug
    multiplying placements, seeds, or orientations more than intended."""

    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opp_a")
    _write_api_v2_agent(tmp_path, "opp_b")
    request = _v4_request(
        tmp_path, opponent_ids=("opp_a", "opp_b"), seeds=STANDARD_V4_SEEDS
    )
    result = EvaluationService().run(request)
    assert len(result.cells) == 2 * 8 * 2
    assert all(cell.status == "completed" for cell in result.cells)
    for opponent in ("opp_a", "opp_b"):
        cells = [c for c in result.cells if c.opponent_id == opponent]
        assert len(cells) == 16
        assert {c.seed for c in cells} == set(STANDARD_V4_SEEDS)
        assert sum(1 for c in cells if c.orientation == ORIENTATION_CANDIDATE_FIRST) == 8
        assert sum(1 for c in cells if c.orientation == ORIENTATION_OPPONENT_FIRST) == 8


def test_orientations_are_paired_over_the_same_seat_bound_geometry(tmp_path: Path):
    """Both orientation cells of one seed share the resolved seat geometry
    with occupants swapped -- never an independently-drawn placement for
    the reverse orientation (research report Sec H.1 item 4 / Sec G.3)."""

    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(3,))
    result = EvaluationService().run(request)
    assert len(result.cells) == 2
    by_orientation = {cell.orientation: cell for cell in result.cells}
    candidate_first = by_orientation[ORIENTATION_CANDIDATE_FIRST]
    opponent_first = by_orientation[ORIENTATION_OPPONENT_FIRST]

    assert candidate_first.placement_id == opponent_first.placement_id == "seeded-3"
    # Same underlying pair, occupants swapped -- not independently drawn.
    assert candidate_first.subject_start == opponent_first.opponent_start
    assert candidate_first.opponent_start == opponent_first.subject_start
    assert candidate_first.subject_start != candidate_first.opponent_start


def test_placement_reconstructs_exactly_from_seed_via_the_production_seam(tmp_path: Path):
    """The artifact must be verifiable, not merely self-consistent (research
    report Sec H.1 item 7): every persisted start is exactly reconstructible
    from resolve_v4_seed_geometry, the same production placement.
    resolve_direct_match_starts seam bytefray run uses."""

    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1, 2, 3, 4))
    result = EvaluationService().run(request)
    for cell in result.cells:
        seat_a, seat_b = resolve_v4_seed_geometry(
            BYTEFRAY_RULESET_V4_ALPHA2_ID, STANDARD_V4_ARENA_SIZE, cell.seed
        )
        if cell.orientation == ORIENTATION_OPPONENT_FIRST:
            seat_a, seat_b = seat_b, seat_a
        assert (cell.subject_start, cell.opponent_start) == (seat_a, seat_b)


def test_pinned_seed_vectors_match_the_research_report(tmp_path: Path):
    """Cross-validates resolve_v4_seed_geometry against the exact pinned
    vector the research report's own reproduction cites (Sec C.1): seed 3
    at arena 512 resolves to (495, 387)."""

    assert resolve_v4_seed_geometry(BYTEFRAY_RULESET_V4_ALPHA2_ID, 512, 3) == (495, 387)


def test_arena_defaults_to_512_when_omitted(tmp_path: Path):
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path)
    assert request.arena_size is None
    assert request.resolved_arena_size == STANDARD_V4_ARENA_SIZE == 512
    result = EvaluationService().run(request)
    for cell in result.cells:
        assert cell.subject_start < 512
        assert cell.opponent_start < 512


def test_explicit_arena_size_matching_the_pin_is_accepted(tmp_path: Path):
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, arena_size=512)
    result = EvaluationService().run(request)
    assert all(cell.status == "completed" for cell in result.cells)


def test_explicit_incompatible_arena_size_fails_closed(tmp_path: Path):
    """Sec 6.2 of the governing task: a standard v4 evaluation must not be
    able to silently produce a non-standard-arena artifact that still
    claims the standard methodology."""

    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, arena_size=4096)
    with pytest.raises(EvaluationConfigurationError, match="incompatible with the"):
        EvaluationService().run(request)


def test_worker_count_does_not_change_schedule_or_outcome(tmp_path: Path):
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opp_a")
    _write_api_v2_agent(tmp_path, "opp_b")

    serial = EvaluationService().run(
        _v4_request(
            tmp_path,
            opponent_ids=("opp_a", "opp_b"),
            seeds=STANDARD_V4_SEEDS,
            output_dir=tmp_path / "serial",
            workers=1,
        )
    )
    parallel = EvaluationService().run(
        _v4_request(
            tmp_path,
            opponent_ids=("opp_a", "opp_b"),
            seeds=STANDARD_V4_SEEDS,
            output_dir=tmp_path / "parallel",
            workers=4,
        )
    )

    def _canonical(cells):
        return sorted(
            (
                c.opponent_id,
                c.seed,
                c.orientation,
                c.placement_id,
                c.subject_start,
                c.opponent_start,
                c.status,
                c.outcome,
                c.score_subject,
                c.score_opponent,
            )
            for c in cells
        )

    assert len(serial.cells) == len(parallel.cells) == 32
    assert _canonical(serial.cells) == _canonical(parallel.cells)
    assert serial.evaluation_id == parallel.evaluation_id


# ---------------------------------------------------------------------------
# F.6 evaluation-state integrity, exercised against real v4 runs
# ---------------------------------------------------------------------------


def test_all_cells_failed_is_not_reported_as_finished(tmp_path: Path):
    """A genuine `status="failed"` cell (not merely an init-failure
    *outcome*, which is a legitimately scored "completed" result) -- an
    Agent API v1 candidate paired against Agent API v2 opponents under an
    explicit --ruleset bytefray-rules-4-alpha2 is rejected by the Ruleset's
    own runtime-compatibility check before any match executes, exactly the
    ruleset_agent_unsupported failure mode F.6 itself reproduced."""

    _write_api_v1_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1, 2))
    result = EvaluationService().run(request)
    assert result.cells
    assert all(cell.status == "failed" for cell in result.cells)
    assert all(cell.error_code == "ruleset_agent_unsupported" for cell in result.cells)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["lifecycle_state"] == LIFECYCLE_STATE_FINISHED_WITH_FAILURES
    assert data["complete"] is False
    assert data["matrix_size"] == len(data["cells"])


def test_partial_failure_is_not_reported_as_finished(tmp_path: Path):
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opp_ok")
    _write_api_v1_agent(tmp_path, "opp_incompatible")
    request = _v4_request(
        tmp_path, opponent_ids=("opp_ok", "opp_incompatible"), seeds=(1,)
    )
    result = EvaluationService().run(request)

    statuses = {
        cell.opponent_id: {c.status for c in result.cells if c.opponent_id == cell.opponent_id}
        for cell in result.cells
    }
    assert statuses["opp_ok"] == {"completed"}
    assert statuses["opp_incompatible"] == {"failed"}

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["lifecycle_state"] == LIFECYCLE_STATE_FINISHED_WITH_FAILURES
    assert data["complete"] is False


def test_all_cells_succeeding_is_reported_as_finished(tmp_path: Path):
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1, 2))
    result = EvaluationService().run(request)
    assert all(cell.status == "completed" for cell in result.cells)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["lifecycle_state"] == LIFECYCLE_STATE_FINISHED
    assert data["complete"] is True


def test_resume_never_converts_historical_failed_cells_into_success(tmp_path: Path):
    _write_api_v1_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1,))
    first = EvaluationService().run(request)
    first_data = json.loads(first.state_path.read_text(encoding="utf-8"))
    assert first_data["lifecycle_state"] == LIFECYCLE_STATE_FINISHED_WITH_FAILURES

    # A bare resume (default resume=True, retry_failures=False): nothing new
    # is scheduled, since the failed cell is already terminally resolved.
    resumed = EvaluationService().run(request)
    resumed_data = json.loads(resumed.state_path.read_text(encoding="utf-8"))
    assert all(cell.status == "failed" for cell in resumed.cells)
    assert resumed_data["lifecycle_state"] == LIFECYCLE_STATE_FINISHED_WITH_FAILURES
    assert resumed_data["complete"] is False
    # M1: chronology preserved -- a true no-op resume must not mint a new
    # finished_at merely because it re-wrote the checkpoint.
    assert resumed_data["finished_at"] == first_data["finished_at"]


def test_resume_of_a_successful_v4_evaluation_reconstructs_cleanly(tmp_path: Path):
    """A regression test for a bug found and fixed during this phase:
    EvaluationService._resolve_from_state's resumed-cell verification
    (_expected_cell_match_id) previously read request.arena_size (None
    when omitted) instead of request.resolved_arena_size, so resuming an
    identical v4 evaluation re-derived the expected match id assuming
    arena 4096 while the original cells actually ran at the pinned 512 --
    every resumed cell was spuriously flagged "corrupted"/
    "resumed_result_mismatch" instead of being cleanly resolved from
    state. This test resumes a *successfully completed* v4 evaluation
    (unlike the all-failed-cells test above, whose "failed" cells return
    early in _resolve_from_state and never reach that code path at all)."""

    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1, 2, 3, 4))
    first = EvaluationService().run(request)
    assert all(cell.status == "completed" for cell in first.cells)

    resumed = EvaluationService().run(request)
    assert all(cell.status == "completed" for cell in resumed.cells)
    assert not any(cell.status == "corrupted" for cell in resumed.cells)

    resumed_data = json.loads(resumed.state_path.read_text(encoding="utf-8"))
    assert resumed_data["lifecycle_state"] == LIFECYCLE_STATE_FINISHED
    assert resumed_data["complete"] is True

    first_by_schedule = {c.schedule_id: c for c in first.cells}
    for cell in resumed.cells:
        original = first_by_schedule[cell.schedule_id]
        assert cell.match_id == original.match_id
        assert cell.result_id == original.result_id
        assert cell.subject_start == original.subject_start
        assert cell.opponent_start == original.opponent_start


def test_cli_exit_code_reflects_real_cell_outcome(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    # An Agent API v1 agent, incompatible with the explicit --ruleset
    # bytefray-rules-4-alpha2 below -- fails every cell with a genuine
    # status="failed"/ruleset_agent_unsupported, exactly F.6's own failure
    # mode, rather than a hand-built/simulated one.
    _write_api_v1_agent(tmp_path, "broken")

    ok_exit = evaluate_main(
        [
            "candidate",
            "--opponents",
            "opponent",
            "--ruleset",
            BYTEFRAY_RULESET_V4_ALPHA2_ID,
            "--seeds",
            "1",
            "--ticks",
            "5",
            "--output",
            str(tmp_path / "ok"),
            "--quiet",
        ]
    )
    assert ok_exit == 0

    fail_exit = evaluate_main(
        [
            "candidate",
            "--opponents",
            "broken",
            "--ruleset",
            BYTEFRAY_RULESET_V4_ALPHA2_ID,
            "--seeds",
            "1",
            "--ticks",
            "5",
            "--output",
            str(tmp_path / "fail"),
            "--quiet",
        ]
    )
    assert fail_exit == 1
    fail_data = json.loads((tmp_path / "fail" / "evaluation.json").read_text(encoding="utf-8"))
    assert fail_data["lifecycle_state"] == LIFECYCLE_STATE_FINISHED_WITH_FAILURES
    assert fail_data["complete"] is False


# ---------------------------------------------------------------------------
# F.6 root cause: omitted --ruleset resolution (CLI)
# ---------------------------------------------------------------------------


def test_omitted_ruleset_with_api_v1_roster_resolves_to_ruleset_2(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_api_v1_agent(tmp_path, "candidate")
    _write_api_v1_agent(tmp_path, "opponent")
    exit_code = evaluate_main(
        [
            "candidate",
            "--opponents",
            "opponent",
            "--seeds",
            "1",
            "--ticks",
            "5",
            "--output",
            str(tmp_path / "out"),
            "--quiet",
        ]
    )
    assert exit_code == 0
    data = json.loads((tmp_path / "out" / "evaluation.json").read_text(encoding="utf-8"))
    assert data["rules_compatibility_id"] == BYTEFRAY_RULESET_V2_ID
    assert all(cell["status"] == "completed" for cell in data["cells"])


def test_omitted_ruleset_with_api_v2_roster_resolves_to_stable_v4(tmp_path: Path, monkeypatch):
    """The F.6 fix itself, exercised end to end through the real CLI: an
    Agent API v2 roster with omitted --ruleset must no longer write an
    artifact where every cell fails ruleset_agent_unsupported."""

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    exit_code = evaluate_main(
        [
            "candidate",
            "--opponents",
            "opponent",
            "--seeds",
            "1",
            "--ticks",
            "5",
            "--output",
            str(tmp_path / "out"),
            "--quiet",
        ]
    )
    assert exit_code == 0
    data = json.loads((tmp_path / "out" / "evaluation.json").read_text(encoding="utf-8"))
    # v4.0.0-rc1 Phase 2: the omitted-Ruleset default for an Agent API v2
    # roster is now the permanent stable identity, not alpha2 -- see
    # ruleset_policy.OMITTED_RULESET_CANDIDATES.
    assert data["rules_compatibility_id"] == BYTEFRAY_RULESET_V4_ID
    assert data["arena_alignment_mode"] == "ruleset_v4_seeded_placements"
    assert data["schema_version"] == SCHEMA_VERSION_V4 == 7
    assert data["lifecycle_state"] == LIFECYCLE_STATE_FINISHED
    assert data["complete"] is True
    assert all(cell["status"] == "completed" for cell in data["cells"])
    assert not any(cell.get("error_code") == "ruleset_agent_unsupported" for cell in data["cells"])


def test_explicit_stable_v4_ruleset_matches_the_omitted_default(tmp_path: Path, monkeypatch):
    """Explicit --ruleset bytefray-rules-4 must resolve to exactly the same
    methodology the omitted default now reaches."""

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    exit_code = evaluate_main(
        [
            "candidate",
            "--opponents",
            "opponent",
            "--ruleset",
            BYTEFRAY_RULESET_V4_ID,
            "--seeds",
            "1",
            "--ticks",
            "5",
            "--output",
            str(tmp_path / "out"),
            "--quiet",
        ]
    )
    assert exit_code == 0
    data = json.loads((tmp_path / "out" / "evaluation.json").read_text(encoding="utf-8"))
    assert data["rules_compatibility_id"] == BYTEFRAY_RULESET_V4_ID
    assert data["arena_alignment_mode"] == "ruleset_v4_seeded_placements"
    assert data["schema_version"] == SCHEMA_VERSION_V4 == 7


def test_explicit_alpha2_ruleset_uses_the_stable_v4_methodology_under_its_own_identity(
    tmp_path: Path, monkeypatch
):
    """alpha2 keeps the schema-7 v4-seeded methodology it was qualified
    under in Phase 1 -- Phase 2's promotion changes which Ruleset an
    *omitted* selection reaches, never alpha2's own explicit behavior, and
    an alpha2 artifact stays honestly self-attributed as alpha2, never
    silently rewritten to the stable identity."""

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    exit_code = evaluate_main(
        [
            "candidate",
            "--opponents",
            "opponent",
            "--ruleset",
            BYTEFRAY_RULESET_V4_ALPHA2_ID,
            "--seeds",
            "1",
            "--ticks",
            "5",
            "--output",
            str(tmp_path / "out"),
            "--quiet",
        ]
    )
    assert exit_code == 0
    data = json.loads((tmp_path / "out" / "evaluation.json").read_text(encoding="utf-8"))
    assert data["rules_compatibility_id"] == BYTEFRAY_RULESET_V4_ALPHA2_ID
    assert data["arena_alignment_mode"] == "ruleset_v4_seeded_placements"
    assert data["schema_version"] == SCHEMA_VERSION_V4 == 7


def test_explicit_alpha1_ruleset_keeps_its_historical_fixed_placement_methodology(
    tmp_path: Path, monkeypatch
):
    """alpha1 must not be silently reinterpreted as the new v4 methodology
    merely because it shares an Agent API generation with alpha2."""

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    exit_code = evaluate_main(
        [
            "candidate",
            "--opponents",
            "opponent",
            "--ruleset",
            BYTEFRAY_RULESET_V4_ALPHA1_ID,
            "--seeds",
            "1",
            "--ticks",
            "5",
            "--output",
            str(tmp_path / "out"),
            "--quiet",
        ]
    )
    assert exit_code == 0
    data = json.loads((tmp_path / "out" / "evaluation.json").read_text(encoding="utf-8"))
    assert data["rules_compatibility_id"] == BYTEFRAY_RULESET_V4_ALPHA1_ID
    assert data["arena_alignment_mode"] == "ruleset_v2_standard_placements"
    assert data["schema_version"] == 5
    assert {cell["placement_id"] for cell in data["cells"]} == {"opposed", "quarter", "opposed-shifted"}


def test_omitted_ruleset_with_incompatible_mixed_roster_fails_closed(tmp_path: Path, monkeypatch):
    """An Agent API v1 candidate paired with an Agent API v2 opponent has no
    compatible Ruleset; automatic resolution must fail closed with a clear
    error rather than guessing (NoCompatibleRulesetError)."""

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_api_v1_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    exit_code = evaluate_main(
        [
            "candidate",
            "--opponents",
            "opponent",
            "--seeds",
            "1",
            "--ticks",
            "5",
            "--output",
            str(tmp_path / "out"),
            "--quiet",
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "out" / "evaluation.json").exists()


# ---------------------------------------------------------------------------
# Schema 7: serialization, parsing, verification, historical compatibility
# ---------------------------------------------------------------------------


def test_schema_7_round_trips_through_evaluation_history(tmp_path: Path):
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1, 2))
    result = EvaluationService().run(request)

    summary = adapt_any(result.state_path)
    assert summary.schema.schema_version == SCHEMA_VERSION_V4 == 7
    assert summary.schema.supported is True
    assert summary.arena_alignment_mode.value == "ruleset_v4_seeded_placements"
    assert summary.rules_compatibility_id.value == BYTEFRAY_RULESET_V4_ALPHA2_ID
    assert summary.health.codes and summary.health.codes[0].value == "healthy"

    for cell in summary.cells:
        assert cell.placement.confidence == FieldConfidence.RECORDED
        assert cell.placement.value.startswith("seeded-")
        assert cell.subject_start.confidence == FieldConfidence.RECORDED
        assert cell.opponent_start.confidence == FieldConfidence.RECORDED
        assert cell.orientation.confidence == FieldConfidence.RECORDED


def test_schema_7_deep_verification_passes_on_a_clean_artifact(tmp_path: Path):
    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1, 2, 3))
    result = EvaluationService().run(request)

    summary = adapt_any(result.state_path)
    verified_summary, verification = verify_summary(summary, data_root=tmp_path)
    assert verification.eligible_count == len(result.cells)
    assert verification.all_eligible_verified
    assert all(cell.verified for cell in verified_summary.cells)


def test_schema_7_deep_verification_fails_closed_on_tampered_placement(tmp_path: Path):
    """A corrupt artifact must fail verification rather than being trusted
    because its top-level summary looks plausible."""

    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1,))
    result = EvaluationService().run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    data["cells"][0]["subject_start"] = (data["cells"][0]["subject_start"] + 1) % 512
    result.state_path.write_text(json.dumps(data), encoding="utf-8")

    summary = adapt_any(result.state_path)
    _verified_summary, verification = verify_summary(summary, data_root=tmp_path)
    assert not verification.all_eligible_verified
    assert verification.failed
    assert "reconstruct" in (verification.failed[0].error or "")


def test_older_schema_versions_are_still_supported_and_not_reinterpreted(tmp_path: Path):
    """Adding schema 7 must not disturb schema 4/5/6 support -- read
    directly from the version tuple rather than assumed."""

    from battle_engine.evaluation_history.v2_adapter import SUPPORTED_V2_VERSIONS

    assert SUPPORTED_V2_VERSIONS == (2, 3, 4, 5, 6, 7)


def test_read_evaluation_accepts_schema_7_and_rejects_unknown_versions(tmp_path: Path):
    from battle_engine.agent_evaluation import read_evaluation

    _write_api_v2_agent(tmp_path, "candidate")
    _write_api_v2_agent(tmp_path, "opponent")
    request = _v4_request(tmp_path, seeds=(1,))
    result = EvaluationService().run(request)

    data = read_evaluation(result.state_path)
    assert data["schema_version"] == 7

    tampered = json.loads(result.state_path.read_text(encoding="utf-8"))
    tampered["schema_version"] = 999
    bogus_path = tmp_path / "bogus.json"
    bogus_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(EvaluationConfigurationError, match="unsupported schema version"):
        read_evaluation(bogus_path)


# ---------------------------------------------------------------------------
# Methodology identity helpers
# ---------------------------------------------------------------------------


def test_is_ruleset_v4_methodology_is_exactly_alpha2_and_stable_v4():
    """v4.0.0-rc1 Phase 2: the permanent stable identity joins alpha2 in
    selecting the v4-seeded methodology; alpha1 still does not."""

    assert is_ruleset_v4_methodology(BYTEFRAY_RULESET_V4_ALPHA2_ID) is True
    assert is_ruleset_v4_methodology(BYTEFRAY_RULESET_V4_ID) is True
    assert is_ruleset_v4_methodology(BYTEFRAY_RULESET_V4_ALPHA1_ID) is False
    assert is_ruleset_v4_methodology(BYTEFRAY_RULESET_V2_ID) is False


def test_identity_and_schema_version_constants_are_both_seven():
    assert IDENTITY_VERSION_V4 == SCHEMA_VERSION_V4 == 7
