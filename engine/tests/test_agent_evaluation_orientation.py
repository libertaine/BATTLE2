"""v0.9 Phase 6: entrant orientation + fixed arena alignment.

Focused regression coverage for the new orientation matrix axis, its
identity/schema-v4 provenance, perspective-correct execution mapping,
resume/retry generalization, CLI/methodology disclosure, and
``evaluation_history`` backward compatibility. See
``runs/research_v0.9/PHASE5_EVALUATION_METHODOLOGY_SPEC.md`` Sections H-W
and ``runs/research_v0.9/PHASE6_IMPLEMENTATION_REPORT.md`` for the design/
acceptance criteria this file exercises. See ``test_agent_evaluation.py``/
``test_agent_evaluation_v2.py`` for the pre-orientation behavior these
tests build on top of, unmodified.
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agent_evaluation import (
    EVALUATION_ARENA_ALIGNMENT_MODE,
    EVALUATION_RULES_COMPATIBILITY_ID,
    IDENTITY_VERSION,
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_MODE_BOTH,
    ORIENTATION_MODE_CANDIDATE_FIRST_ONLY,
    ORIENTATION_OPPONENT_FIRST,
    SCHEMA_VERSION,
    EvaluationRequest,
    EvaluationService,
    _post_execution_identity_drift,
    agent_identity,
    build_matrix,
    main,
    methodology_lines,
)
from battle_engine.agents import resolve_agent
from battle_engine.evaluation_history import FieldConfidence, adapt_any
from battle_engine.evaluation_history.comparison import align
from battle_engine.match_service import NativeAgentResult, NativeMatchResult
from battle_engine.python_runtime import TerminationReason

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_python_agent(root: Path, name: str, action: str = NOP_ACTION) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        f"""
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return {action}
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


def _write_active_agent(root: Path, name: str) -> Path:
    """A deterministic non-NOP agent: claims a fresh cell every tick.

    Its outcome-vs-a-passive-NOP-opponent doesn't depend on which physical
    slot it executes in, which is exactly what makes it useful for proving
    perspective-correct (role-based, not slot-based) result mapping.
    """

    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context):
        self.addr = 0
    def act(self, observation):
        addr = self.addr
        self.addr += 1
        return AgentAction(ActionKind.WRITE, operand=addr, value=1)
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


def _write_reset_failing_agent(root: Path, name: str, message: str = "boom") -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        f"""
class Agent:
    def reset(self, context):
        raise RuntimeError({message!r})
    def act(self, observation):
        return None
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


def _request(tmp_path: Path, **overrides) -> EvaluationRequest:
    defaults = {
        "candidate_id": "candidate",
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "eval-out",
        "ticks": 15,
        "data_root": tmp_path,
        # This file is specifically about orientation, so both_orientations
        # defaults True here -- the opposite convention of every other
        # evaluation test file, which pins False to stay orthogonal to it.
        "both_orientations": True,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


def _two_agents(tmp_path: Path) -> Path:
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    return tmp_path


# ---------------------------------------------------------------------------
# 1-5: matrix construction (cardinality, ordering, identity)
# ---------------------------------------------------------------------------


def test_matrix_cardinality_doubles_under_default_both_orientations():
    request = EvaluationRequest(
        candidate_id="cand",
        opponent_ids=("a", "b"),
        seeds=(1, 2),
        output_dir=Path("out"),
    )
    matrix = build_matrix(request, "evaluation_x")
    assert len(matrix) == 2 * 2 * 2  # opponents x seeds x orientations


def test_single_orientation_preserves_legacy_cardinality():
    request = EvaluationRequest(
        candidate_id="cand",
        opponent_ids=("a", "b"),
        seeds=(1, 2),
        output_dir=Path("out"),
        both_orientations=False,
    )
    matrix = build_matrix(request, "evaluation_x")
    assert len(matrix) == 2 * 2
    assert all(cell.orientation == ORIENTATION_CANDIDATE_FIRST for cell in matrix)


def test_orientation_ordering_is_deterministic_candidate_first_then_opponent_first():
    request = EvaluationRequest(
        candidate_id="cand", opponent_ids=("a",), seeds=(1,), output_dir=Path("out")
    )
    matrix = build_matrix(request, "evaluation_x")
    assert [cell.orientation for cell in matrix] == [
        ORIENTATION_CANDIDATE_FIRST,
        ORIENTATION_OPPONENT_FIRST,
    ]
    assert [cell.orientation_index for cell in matrix] == [0, 1]


def test_schedule_ids_differ_by_orientation_only():
    request = EvaluationRequest(
        candidate_id="cand", opponent_ids=("a",), seeds=(1,), output_dir=Path("out")
    )
    matrix = build_matrix(request, "evaluation_x")
    cf, of = matrix
    assert cf.opponent_id == of.opponent_id and cf.seed == of.seed
    assert cf.schedule_id != of.schedule_id


def test_condition_fingerprints_differ_by_orientation_only(tmp_path):
    root = _two_agents(tmp_path)
    specs = {"candidate": resolve_agent(root, "candidate"), "opponent": resolve_agent(root, "opponent")}
    request = EvaluationRequest(
        candidate_id="candidate", opponent_ids=("opponent",), seeds=(1,), output_dir=Path("out")
    )
    matrix = build_matrix(
        request,
        "evaluation_x",
        specs,
        "conditions-fp",
        EVALUATION_RULES_COMPATIBILITY_ID,
        EVALUATION_ARENA_ALIGNMENT_MODE,
    )
    cf, of = matrix
    assert cf.condition_fingerprint is not None
    assert of.condition_fingerprint is not None
    assert cf.condition_fingerprint != of.condition_fingerprint


def test_artifact_dir_labels_never_collide_between_orientations():
    request = EvaluationRequest(
        candidate_id="cand", opponent_ids=("a",), seeds=(1,), output_dir=Path("out")
    )
    matrix = build_matrix(request, "evaluation_x")
    cf, of = matrix
    assert cf.artifact_dir != of.artifact_dir
    assert "candidate_first" in str(cf.artifact_dir)
    assert "opponent_first" in str(of.artifact_dir)


# ---------------------------------------------------------------------------
# 6-9: identity / schema-v4 / rules-compatibility
# ---------------------------------------------------------------------------


def test_evaluation_id_differs_between_both_and_single_orientation(tmp_path):
    root = _two_agents(tmp_path)
    service = EvaluationService()
    _specs_both, id_both = service.preflight(
        candidate_id="candidate", opponent_ids=("opponent",), seeds=(1,), data_root=root,
        both_orientations=True,
    )
    _specs_single, id_single = service.preflight(
        candidate_id="candidate", opponent_ids=("opponent",), seeds=(1,), data_root=root,
        both_orientations=False,
    )
    assert id_both != id_single


def test_schema_and_identity_v4_round_trip(tmp_path):
    root = _two_agents(tmp_path)
    service = EvaluationService()
    result = service.run(_request(root))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert SCHEMA_VERSION == 4
    assert IDENTITY_VERSION == 4
    assert data["schema_version"] == 4
    assert data["identity_version"] == 4
    assert data["orientation_mode"] == ORIENTATION_MODE_BOTH == "both"
    assert data["arena_alignment_mode"] == EVALUATION_ARENA_ALIGNMENT_MODE == "fixed"
    cell_orientations = {cell["orientation"] for cell in data["cells"]}
    assert cell_orientations == {"candidate_first", "opponent_first"}


def test_rules_compatibility_id_unchanged_by_orientation(tmp_path):
    root = _two_agents(tmp_path)
    service = EvaluationService()
    both = service.run(_request(root, output_dir=root / "both", both_orientations=True))
    single = service.run(_request(root, output_dir=root / "single", both_orientations=False))
    data_both = json.loads(both.state_path.read_text(encoding="utf-8"))
    data_single = json.loads(single.state_path.read_text(encoding="utf-8"))
    assert data_both["rules_compatibility_id"] == EVALUATION_RULES_COMPATIBILITY_ID
    assert data_single["rules_compatibility_id"] == EVALUATION_RULES_COMPATIBILITY_ID


def test_single_orientation_run_reproduces_legacy_cell_count_and_shape(tmp_path):
    root = _two_agents(tmp_path)
    service = EvaluationService()
    result = service.run(_request(root, opponent_ids=("opponent",), seeds=(1, 2), both_orientations=False))
    assert len(result.cells) == 2
    assert all(cell.orientation == ORIENTATION_CANDIDATE_FIRST for cell in result.cells)


# ---------------------------------------------------------------------------
# 10-11: execution/perspective mapping
# ---------------------------------------------------------------------------


def test_opponent_first_calls_executor_with_roles_physically_swapped(tmp_path, monkeypatch):
    root = _two_agents(tmp_path)
    import battle_engine.agent_evaluation as mod

    real_test_agent = mod.test_agent
    calls: list[tuple[str, str]] = []

    def _spy(agent_id, *, opponent, **kwargs):
        calls.append((agent_id, opponent))
        return real_test_agent(agent_id, opponent=opponent, **kwargs)

    monkeypatch.setattr(mod, "test_agent", _spy)
    service = EvaluationService()
    service.run(_request(root))

    assert ("candidate", "opponent") in calls  # candidate_first: unmodified historical call
    assert ("opponent", "candidate") in calls  # opponent_first: roles swapped


def test_perspective_correct_outcome_and_score_mapping_both_orientations(tmp_path):
    """The evaluation *role* (candidate/subject), not the physical slot,
    determines which side a win/score is attributed to -- regression for
    exactly the hazard Phase 5 spec Sec 12/H.1 calls out. Also a fault-
    injection proof for post-execution identity drift (Sec 14/W.8): if the
    drift check read the wrong physical slot for an opponent_first cell, it
    would falsely flag every cell here as `drift_detected` instead of
    `completed`, since candidate/opponent are different agents.
    """

    _write_active_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    service = EvaluationService()
    result = service.run(_request(tmp_path, ticks=30))

    assert len(result.cells) == 2
    assert result.drift_cells == ()
    for cell in result.cells:
        assert cell.status == "completed", cell.error_message
        assert cell.outcome == "win"
        assert cell.score_subject is not None and cell.score_opponent is not None
        assert cell.score_subject > cell.score_opponent


def test_initialization_failure_mapping_both_orientations_candidate_broken(tmp_path):
    _write_reset_failing_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    service = EvaluationService()
    result = service.run(_request(tmp_path))
    by_orientation = {cell.orientation: cell for cell in result.cells}
    # The broken agent is always the "candidate"/subject role, regardless
    # of which physical slot it actually executed in.
    assert by_orientation["candidate_first"].outcome == "subject_init_failed"
    assert by_orientation["opponent_first"].outcome == "subject_init_failed"


def test_initialization_failure_mapping_both_orientations_opponent_broken(tmp_path):
    _write_python_agent(tmp_path, "candidate")
    _write_reset_failing_agent(tmp_path, "opponent")
    service = EvaluationService()
    result = service.run(_request(tmp_path))
    by_orientation = {cell.orientation: cell for cell in result.cells}
    assert by_orientation["candidate_first"].outcome == "opponent_init_failed"
    assert by_orientation["opponent_first"].outcome == "opponent_init_failed"


# ---------------------------------------------------------------------------
# 14: post-execution drift, direct unit-level slot-mapping proof
# ---------------------------------------------------------------------------


def _fake_agent_result(agent_id: str, slot: str, metadata: dict) -> NativeAgentResult:
    return NativeAgentResult(
        agent_id=slot,
        name=agent_id,
        alive=True,
        score=0,
        alive_ticks=1,
        kills=0,
        deaths=0,
        cpu_total=0,
        mem_writes=0,
        territory_last=0,
        territory_max=0,
        territory_avg=0.0,
        territory_pct_last=0.0,
        territory_pct_max=0.0,
        territory_pct_avg=0.0,
        metadata=metadata,
    )


def test_post_execution_drift_reads_the_correct_physical_slot_per_orientation(tmp_path):
    """Direct unit-level proof of Phase 5 spec Sec 14/W.8: hand-construct a
    match result where physical slot A carries the candidate's actual
    identity and slot B the opponent's (i.e. exactly what a real
    `candidate_first` execution produces), then evaluate
    `_post_execution_identity_drift` against both a `candidate_first` and
    an `opponent_first` cell using the *same* match result and the *same*
    planned identities.

    A `candidate_first` cell must see no drift (subject=A matches, opponent
    =B matches). An `opponent_first` cell evaluated against that same
    physical layout must see drift on *both* sides (subject is supposed to
    be in slot B but slot B actually holds the opponent's identity, and
    vice versa) -- proving the function actually reads
    `physical_slots_for_orientation(cell.orientation)` rather than a fixed
    subject=A/opponent=B assumption.
    """

    # Candidate and opponent must have genuinely different source bytes --
    # two byte-identical NOP agents would have identical source_sha256/
    # local_source_fingerprint, making a "wrong slot" mismatch undetectable
    # by construction and defeating this fault-injection test.
    root = tmp_path
    _write_active_agent(root, "candidate")
    _write_python_agent(root, "opponent")
    candidate_identity = agent_identity(resolve_agent(root, "candidate"))
    opponent_identity = agent_identity(resolve_agent(root, "opponent"))
    assert candidate_identity["source_sha256"] != opponent_identity["source_sha256"]
    planned_identities = {"candidate": candidate_identity, "opponent": opponent_identity}

    metadata_fields = ("source_sha256", "api_version", "agent_version", "entry_point", "local_source_fingerprint")
    slot_a_metadata = {field: candidate_identity[field] for field in metadata_fields}
    slot_a_metadata["local_source_fingerprint_final"] = candidate_identity["local_source_fingerprint"]
    slot_b_metadata = {field: opponent_identity[field] for field in metadata_fields}
    slot_b_metadata["local_source_fingerprint_final"] = opponent_identity["local_source_fingerprint"]

    match_result = NativeMatchResult(
        winner="A",
        ticks_run=1,
        score={"A": 1, "B": 0},
        agents=(
            _fake_agent_result("candidate", "A", slot_a_metadata),
            _fake_agent_result("opponent", "B", slot_b_metadata),
        ),
        replay_path=tmp_path / "replay.jsonl",
        termination_reason=TerminationReason.TICK_LIMIT,
    )

    base_matrix = build_matrix(
        EvaluationRequest(
            candidate_id="candidate", opponent_ids=("opponent",), seeds=(1,), output_dir=Path("out")
        ),
        "evaluation_x",
    )
    candidate_first_cell = next(c for c in base_matrix if c.orientation == ORIENTATION_CANDIDATE_FIRST)
    opponent_first_cell = next(c for c in base_matrix if c.orientation == ORIENTATION_OPPONENT_FIRST)

    assert _post_execution_identity_drift(candidate_first_cell, match_result, planned_identities) is None
    drift = _post_execution_identity_drift(opponent_first_cell, match_result, planned_identities)
    assert drift is not None
    assert drift["error_code"] == "post_execution_identity_drift"


# ---------------------------------------------------------------------------
# 15-16: resume / retry generalize per-orientation for free
# ---------------------------------------------------------------------------


def test_noop_resume_of_a_fully_completed_both_orientations_evaluation_does_not_corrupt_opponent_first(
    tmp_path,
):
    """Phase 7 regression: re-running the identical evaluate request against
    an already-fully-completed ``--output`` (the most ordinary resume case
    -- nothing missing, nothing failed) must be a pure no-op. Resume
    re-verifies every prior cell's recorded ``match_id`` against a freshly
    recomputed expectation (``_expected_cell_match_id``); that recomputation
    previously built its ``MatchRequest.entrants`` tuple in
    (subject-first, opponent-second) order for an ``opponent_first`` cell,
    instead of the physical (``TESTED_AGENT_SLOT``-first,
    ``OPPONENT_SLOT``-second) order ``_test_agent`` actually always uses --
    ``canonical_match_id`` is sensitive to that positional order (both the
    per-entrant derived seed and the recorded ``entrant_order`` list), so
    the mismatched order silently recomputed a *different* id than what a
    real ``opponent_first`` execution produced. Every already-completed
    ``opponent_first`` cell was falsely demoted to ``corrupted`` with a
    ``resumed_result_mismatch`` on every subsequent resume, even though
    nothing about the match had actually changed."""

    root = _two_agents(tmp_path)
    service = EvaluationService()
    request = _request(root)

    first = service.run(request)
    assert {cell.orientation: cell.status for cell in first.cells} == {
        "candidate_first": "completed",
        "opponent_first": "completed",
    }

    second = service.run(request)
    statuses = {cell.orientation: cell.status for cell in second.cells}
    assert statuses == {"candidate_first": "completed", "opponent_first": "completed"}
    assert second.corrupted_cells == ()


def test_resume_executes_only_the_missing_orientation(tmp_path, monkeypatch):
    root = _two_agents(tmp_path)
    import battle_engine.agent_evaluation as mod

    real_execute_cell = mod.EvaluationService._execute_cell
    executed: list[str] = []

    def _tracking_execute_cell(self, cell, *args, **kwargs):
        executed.append(cell.orientation)
        return real_execute_cell(self, cell, *args, **kwargs)

    monkeypatch.setattr(mod.EvaluationService, "_execute_cell", _tracking_execute_cell)

    request = _request(root)
    service = EvaluationService()
    service.run(request)
    assert sorted(executed) == ["candidate_first", "opponent_first"]

    # Simulate an interrupted run: drop the opponent_first cell from the
    # persisted state, then resume.
    state_path = request.output_dir / "evaluation.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["cells"] = [c for c in data["cells"] if c["orientation"] == "candidate_first"]
    data["complete"] = False
    data["lifecycle_state"] = "running"
    state_path.write_text(json.dumps(data), encoding="utf-8")

    executed.clear()
    result = service.run(request)
    assert executed == ["opponent_first"]  # only the missing orientation re-ran
    orientations = {cell.orientation for cell in result.cells}
    assert orientations == {"candidate_first", "opponent_first"}
    assert len(result.cells) == 2


def test_retry_failed_reruns_only_the_failed_orientation(tmp_path, monkeypatch):
    root = _two_agents(tmp_path)
    request = _request(root)
    service = EvaluationService()
    result = service.run(request)
    state_path = request.output_dir / "evaluation.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    for cell in data["cells"]:
        if cell["orientation"] == "opponent_first":
            cell["status"] = "failed"
            cell["error_code"] = "simulated_failure"
    data["complete"] = True
    state_path.write_text(json.dumps(data), encoding="utf-8")

    import battle_engine.agent_evaluation as mod

    real_execute_cell = mod.EvaluationService._execute_cell
    executed: list[str] = []

    def _tracking_execute_cell(self, cell, *args, **kwargs):
        executed.append(cell.orientation)
        return real_execute_cell(self, cell, *args, **kwargs)

    monkeypatch.setattr(mod.EvaluationService, "_execute_cell", _tracking_execute_cell)

    retry_request = _request(root, retry_failures=True)
    result = service.run(retry_request)
    assert executed == ["opponent_first"]
    completed = {cell.orientation: cell for cell in result.cells}
    assert completed["opponent_first"].status == "completed"
    assert completed["candidate_first"].status == "completed"


# ---------------------------------------------------------------------------
# 17-19: evaluation_history backward compatibility / comparison
# ---------------------------------------------------------------------------


def test_legacy_v1_artifact_orientation_recovered_candidate_first(tmp_path):
    v1_artifact = {
        "schema": "bytefray.evaluation",
        "schema_version": 1,
        "evaluation_id": "evaluation_abc123",
        "candidate_id": "candidate",
        "opponent_ids": ["opponent"],
        "seeds": [1],
        "ticks": 10,
        "complete": True,
        "cells": [
            {
                "schedule_id": "s1",
                "subject_role": "candidate",
                "subject_id": "candidate",
                "opponent_id": "opponent",
                "seed": 1,
                "status": "completed",
                "outcome": "win",
                "artifact_dir": "matches/0001",
            }
        ],
    }
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps(v1_artifact), encoding="utf-8")
    summary = adapt_any(path)
    assert summary.orientation_mode.value == "candidate_first_only"
    assert summary.orientation_mode.confidence == FieldConfidence.RECOVERED
    assert summary.arena_alignment_mode.value == "fixed"
    assert summary.arena_alignment_mode.confidence == FieldConfidence.RECOVERED
    assert len(summary.cells) == 1
    assert summary.cells[0].orientation.value == "candidate_first"
    assert summary.cells[0].orientation.confidence == FieldConfidence.RECOVERED


def test_legacy_v2_shaped_artifact_orientation_and_alignment_recovered(tmp_path):
    root = _two_agents(tmp_path)
    service = EvaluationService()
    result = service.run(_request(root, both_orientations=False))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    # Reshape into a pre-Phase-6 v2-family artifact (schema_version 3):
    # strip the v0.9 fields entirely, exactly as a genuine old artifact
    # would never have had them.
    data["schema_version"] = 3
    data["identity_version"] = 3
    del data["orientation_mode"]
    del data["arena_alignment_mode"]
    for cell in data["cells"]:
        del cell["orientation"]
        del cell["orientation_index"]
    path = tmp_path / "v3-shaped.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    summary = adapt_any(path)
    assert summary.schema.schema_version == 3
    assert summary.orientation_mode.value == "candidate_first_only"
    assert summary.orientation_mode.confidence == FieldConfidence.RECOVERED
    assert summary.arena_alignment_mode.value == "fixed"
    assert summary.arena_alignment_mode.confidence == FieldConfidence.RECOVERED
    for cell in summary.cells:
        assert cell.orientation.value == "candidate_first"
        assert cell.orientation.confidence == FieldConfidence.RECOVERED


def test_new_both_orientations_evaluation_vs_legacy_leaves_opponent_first_unmatched(tmp_path):
    root = _two_agents(tmp_path)
    service = EvaluationService()

    legacy_result = service.run(_request(root, output_dir=root / "legacy", both_orientations=False))
    legacy_data = json.loads(legacy_result.state_path.read_text(encoding="utf-8"))
    legacy_data["schema_version"] = 3
    legacy_data["identity_version"] = 3
    del legacy_data["orientation_mode"]
    del legacy_data["arena_alignment_mode"]
    for cell in legacy_data["cells"]:
        del cell["orientation"]
        del cell["orientation_index"]
    legacy_path = root / "legacy" / "evaluation.json"
    legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

    new_result = service.run(_request(root, output_dir=root / "new", both_orientations=True))

    left = adapt_any(legacy_path)
    right = adapt_any(new_result.state_path)
    comparison = align(left, right)

    # The candidate_first cell aligns; the opponent_first cell has no
    # legacy counterpart and must surface as unmatched, never silently
    # folded into an improved/regressed verdict.
    assert comparison.denominators.condition_intersection == 1
    assert comparison.denominators.unmatched_right == 1
    unmatched_orientations = {cell.orientation.value for cell in comparison.unmatched_right}
    assert unmatched_orientations == {"opponent_first"}


# ---------------------------------------------------------------------------
# 20-23: CLI methodology disclosure
# ---------------------------------------------------------------------------


def test_cli_default_run_reports_both_orientations_methodology(tmp_path, monkeypatch, capsys):
    _write_python_agent(tmp_path, "cand")
    _write_python_agent(tmp_path, "opp")
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = main(["cand", "--opponents", "opp", "--seeds", "1", "--dry-run"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "matches: 2" in out
    assert "Entrant orientation: both" in out
    assert "Arena alignment: fixed" in out
    assert "translation robustness not evaluated" in out


def test_cli_single_orientation_flag_reproduces_legacy_matrix_and_label(tmp_path, monkeypatch, capsys):
    _write_python_agent(tmp_path, "cand")
    _write_python_agent(tmp_path, "opp")
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = main(
        ["cand", "--opponents", "opp", "--seeds", "1", "--dry-run", "--single-orientation"]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "matches: 1" in out
    assert "candidate-first only" in out
    assert "does not generalize across entrant order" in out
    assert "Arena alignment: fixed" in out


def test_methodology_lines_never_claim_unbiased_or_fully_robust():
    for mode in (ORIENTATION_MODE_BOTH, ORIENTATION_MODE_CANDIDATE_FIRST_ONLY):
        lines = methodology_lines(mode)
        text = " ".join(lines).lower()
        assert "unbiased" not in text
        assert "fully robust" not in text
        assert "bias-free" not in text


def test_both_orientation_cells_never_flagged_as_duplicate_condition_coordinate(tmp_path):
    """Regression: a candidate_first and opponent_first cell for the same
    (opponent, seed) legitimately share `condition_occurrence_index` (Sec
    I.3 -- orientation, not occurrence, distinguishes them), which must
    never be misreported by `evaluation_history`'s structural
    DUPLICATE_CONDITION_COORDINATE health check (found via manual CLI
    smoke validation)."""

    from battle_engine.evaluation_history.models import HealthCode

    root = _two_agents(tmp_path)
    service = EvaluationService()
    result = service.run(_request(root))
    summary = adapt_any(result.state_path)
    assert HealthCode.DUPLICATE_CONDITION_COORDINATE not in summary.health.codes
    assert HealthCode.HEALTHY in summary.health.codes


def test_genuine_duplicate_condition_coordinate_still_flagged_within_schema_v4_artifact(tmp_path):
    """Positive control for the regression above (Phase 7 validation): the
    orientation-aware DUPLICATE_CONDITION_COORDINATE fix must not have
    turned into a broad suppression of the health check. Two schema-v4
    cells that share *everything* including `orientation` (an actual
    duplicate, not a legitimate candidate_first/opponent_first pair) must
    still be flagged."""

    from battle_engine.evaluation_history.models import HealthCode

    root = _two_agents(tmp_path)
    service = EvaluationService()
    result = service.run(_request(root, both_orientations=False))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert len(data["cells"]) == 1
    genuine_duplicate = dict(data["cells"][0], schedule_id="duplicate-schedule-id")
    assert genuine_duplicate["orientation"] == data["cells"][0]["orientation"] == "candidate_first"
    assert (
        genuine_duplicate["condition_occurrence_index"]
        == data["cells"][0]["condition_occurrence_index"]
        == 0
    )
    data["cells"].append(genuine_duplicate)
    path = tmp_path / "duplicated.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    summary = adapt_any(path)
    assert HealthCode.DUPLICATE_CONDITION_COORDINATE in summary.health.codes
    assert HealthCode.HEALTHY not in summary.health.codes


def test_evaluations_show_prints_methodology_lines(tmp_path, capsys):
    from battle_engine.evaluation_history.cli import main as evaluations_main

    root = _two_agents(tmp_path)
    service = EvaluationService()
    result = service.run(_request(root))

    exit_code = evaluations_main(["show", str(result.state_path.parent)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Entrant orientation: both" in out
    assert "Arena alignment: fixed" in out
    assert "orientation_mode: both" in out
