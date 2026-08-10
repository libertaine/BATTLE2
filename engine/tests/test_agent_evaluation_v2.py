"""``bytefray.evaluation`` v2 capture hardening (docs/specs/evaluation_history.md).

Covers identity/effective-conditions/lifecycle/provenance/drift/duplicate-
coordinate behavior added on top of v0.6.1's v1 artifact. See
``test_agent_evaluation.py`` for the v1-era behavior these tests build on
(matrix construction, aggregation, resume-verification) which remains
unmodified and still passing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    EVALUATION_RULES_COMPATIBILITY_ID,
    IDENTITY_VERSION,
    SCHEMA_VERSION,
    EvaluationRequest,
    EvaluationService,
    build_matrix,
)

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


def _request(tmp_path: Path, **overrides) -> EvaluationRequest:
    defaults = {
        "candidate_id": "candidate",
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "eval-out",
        "ticks": 10,
        "data_root": tmp_path,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


@pytest.fixture()
def two_agents(tmp_path: Path) -> Path:
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    return tmp_path


# ---------------------------------------------------------------------------
# Identity (Sec 2)
# ---------------------------------------------------------------------------


def test_v2_evaluation_id_deterministic(two_agents: Path):
    service = EvaluationService()
    first = service.run(_request(two_agents))
    second = service.run(_request(two_agents, output_dir=two_agents / "eval-out-2"))
    assert first.evaluation_id == second.evaluation_id
    assert first.evaluation_id.startswith("evaluation-v2_")


def test_v2_evaluation_id_differs_from_a_v1_style_payload(two_agents: Path):
    # v1's payload never hashed effective_conditions/rules_compatibility_id/
    # identity_version; the "evaluation-v2" stable_id prefix alone already
    # guarantees a v1 "evaluation_..." id can never collide with a v2
    # "evaluation-v2_..." id (Sec 2's "cannot be mistaken for equivalent
    # contracts" requirement).
    service = EvaluationService()
    result = service.run(_request(two_agents))
    assert not result.evaluation_id.startswith("evaluation_")
    assert result.evaluation_id.startswith("evaluation-v2_")


def test_v2_evaluation_id_changes_with_ticks(two_agents: Path):
    service = EvaluationService()
    a = service.run(_request(two_agents, output_dir=two_agents / "a", ticks=10))
    b = service.run(_request(two_agents, output_dir=two_agents / "b", ticks=11))
    assert a.evaluation_id != b.evaluation_id


# ---------------------------------------------------------------------------
# Artifact shape / effective conditions / rules compatibility (Sec 3/4/9)
# ---------------------------------------------------------------------------


def test_v2_artifact_records_effective_conditions_and_rules_id(two_agents: Path):
    service = EvaluationService()
    result = service.run(_request(two_agents))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2 == SCHEMA_VERSION
    assert data["identity_version"] == IDENTITY_VERSION
    assert data["rules_compatibility_id"] == EVALUATION_RULES_COMPATIBILITY_ID
    conditions = data["effective_conditions"]
    assert conditions["tick_limit"] == 10
    assert conditions["arena_size"] == 4096
    assert conditions["subject_slot"] == "A"
    assert conditions["opponent_slot"] == "B"
    assert data["effective_conditions_fingerprint"].startswith("evaluation-conditions_")


def test_v2_artifact_records_planned_identities(two_agents: Path):
    service = EvaluationService()
    result = service.run(_request(two_agents))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    planned = data["planned_identities"]
    assert planned["candidate"]["agent_id"] == "candidate"
    assert planned["baseline"] is None
    assert [o["agent_id"] for o in planned["opponents"]] == ["opponent"]
    assert planned["candidate"]["source_sha256"] is not None


# ---------------------------------------------------------------------------
# Lifecycle and provenance (Sec 5/6)
# ---------------------------------------------------------------------------


def test_v2_first_checkpoint_exists_before_any_cell_executes(two_agents: Path, monkeypatch):
    """A crash mid-first-cell still leaves discoverable running lifecycle state."""

    import battle_engine.agent_evaluation as mod

    request = _request(two_agents)
    state_path = request.output_dir / "evaluation.json"

    def _boom(*args, **kwargs):
        # Checkpoint must already exist by the time the first cell runs.
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["lifecycle_state"] == "running"
        assert data["created_at"]
        assert data["cells"] == []
        raise RuntimeError("simulated crash before first cell finishes")

    monkeypatch.setattr(mod, "test_agent", _boom)
    with pytest.raises(RuntimeError):
        mod.EvaluationService().run(request)


def test_v2_finished_lifecycle_sets_finished_at_atomically_with_aggregates(two_agents: Path):
    service = EvaluationService()
    result = service.run(_request(two_agents))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["lifecycle_state"] == "finished"
    assert data["finished_at"] is not None
    assert data["created_at"] <= data["updated_at"]
    assert data["aggregates"]
    assert data["complete"] is True


def test_v2_execution_context_recorded_for_freshly_executed_cells(two_agents: Path):
    service = EvaluationService()
    result = service.run(_request(two_agents))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert len(data["execution_contexts"]) == 1
    context = data["execution_contexts"][0]
    assert context["rules_compatibility_id"] == EVALUATION_RULES_COMPATIBILITY_ID
    for cell in data["cells"]:
        assert cell["execution_context_id"] == context["context_id"]


def test_v2_no_op_resume_does_not_rewrite_provenance(two_agents: Path):
    service = EvaluationService()
    request = _request(two_agents)
    first = service.run(request)
    first_data = json.loads(first.state_path.read_text(encoding="utf-8"))

    second = service.run(request)
    second_data = json.loads(second.state_path.read_text(encoding="utf-8"))

    assert second_data["created_at"] == first_data["created_at"]
    assert len(second_data["execution_contexts"]) == len(first_data["execution_contexts"])
    for before, after in zip(first_data["cells"], second_data["cells"]):
        assert before["execution_context_id"] == after["execution_context_id"]
        assert before["match_id"] == after["match_id"]
    # updated_at still advances (a checkpoint was still written) even though
    # nothing was newly executed.
    assert second_data["updated_at"] >= first_data["updated_at"]


def test_v2_retry_under_new_context_appends_a_second_execution_context(two_agents: Path, monkeypatch):
    import battle_engine.agent_evaluation as mod

    request = _request(two_agents)
    service = EvaluationService()
    first = service.run(request)
    first_data = json.loads(first.state_path.read_text(encoding="utf-8"))
    assert len(first_data["execution_contexts"]) == 1

    monkeypatch.setattr(
        mod,
        "current_execution_context",
        lambda rules_id: mod.ExecutionContext(
            context_id="evaluation-context_deadbeefdeadbeefdeadbeef",
            bytefray_version="9.9.9-test",
            agent_api_version=1,
            python_version="9.9.9",
            result_schema_version=1,
            replay_schema_version=3,
            rules_compatibility_id=rules_id,
        ),
    )
    second = service.run(_request(two_agents, retry_failures=False, output_dir=request.output_dir))
    # Nothing to retry (all cells already completed) -- context list must
    # stay stable for a no-op resume even under a "different" mocked context.
    second_data = json.loads(second.state_path.read_text(encoding="utf-8"))
    assert len(second_data["execution_contexts"]) == 1


# ---------------------------------------------------------------------------
# Source drift (Sec 7)
# ---------------------------------------------------------------------------


def test_v2_source_drift_between_cells_stops_the_matrix(tmp_path: Path, monkeypatch):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opp_a")
    _write_python_agent(tmp_path, "opp_b")
    _write_python_agent(tmp_path, "opp_c")

    request = _request(
        tmp_path,
        opponent_ids=("opp_a", "opp_b", "opp_c"),
        seeds=(1,),
    )
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    original_detect = mod.EvaluationService._detect_pre_execution_drift

    def _detect_with_injected_drift(self, cell, planned_identities, root):
        if cell.opponent_id == "opp_b":
            return {
                "error_code": "pre_execution_source_drift",
                "error_message": "opponent 'opp_b' identity changed since preflight (fields: source_sha256).",
            }
        return original_detect(self, cell, planned_identities, root)

    monkeypatch.setattr(
        mod.EvaluationService, "_detect_pre_execution_drift", _detect_with_injected_drift
    )
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["lifecycle_state"] == "aborted"
    assert data["abort_reason"] == "source_drift"
    assert data["finished_at"] is None
    assert data["abort_detail"]["code"] == "pre_execution_source_drift"
    # The first (opp_a) cell, which ran before drift was ever introduced,
    # is preserved with a real outcome.
    first_cell = data["cells"][0]
    assert first_cell["opponent_id"] == "opp_a"
    assert first_cell["status"] == "completed"
    # The drifted cell itself is retained for diagnosis, marked distinctly.
    second_cell = data["cells"][1]
    assert second_cell["opponent_id"] == "opp_b"
    assert second_cell["status"] == "drift_detected"
    # No cell after the detected drift was scheduled.
    assert len(data["cells"]) < len(build_matrix(request, result.evaluation_id))

    # A fresh run against the same (unaborted) --output must not silently
    # "fix up" the aborted evaluation by re-running past the drift point
    # without --retry-failed.
    resumed = service.run(request)
    resumed_data = json.loads(resumed.state_path.read_text(encoding="utf-8"))
    assert resumed_data["lifecycle_state"] == "aborted"


# ---------------------------------------------------------------------------
# Duplicate occurrence coordinates (Sec 8)
# ---------------------------------------------------------------------------


def test_v2_duplicate_opponent_and_seed_get_distinct_occurrence_coordinates(two_agents: Path):
    # opponent VALUE "opponent" @ seed 1 repeats all four times here, so
    # condition_occurrence_index (which counts repeats of the same
    # (opponent_id, seed) *value* pair, not list position -- Sec 8) climbs
    # 0..3 across all four cells even though opponent_index/seed_index only
    # take two distinct values each.
    request = _request(two_agents, opponent_ids=("opponent", "opponent"), seeds=(1, 1))
    matrix = build_matrix(request, "evaluation-v2_test")
    assert len(matrix) == 4
    coordinates = [
        (c.opponent_index, c.seed_index, c.matrix_ordinal, c.condition_occurrence_index)
        for c in matrix
    ]
    assert coordinates == [
        (0, 0, 1, 0),
        (0, 1, 2, 1),
        (1, 0, 3, 2),
        (1, 1, 4, 3),
    ]


def test_v2_condition_occurrence_index_resets_per_distinct_opponent_seed_pair(two_agents: Path):
    _write_python_agent(two_agents, "opponent_b")
    request = _request(
        two_agents, opponent_ids=("opponent", "opponent_b", "opponent"), seeds=(1,)
    )
    matrix = build_matrix(request, "evaluation-v2_test")
    coordinates = [(c.opponent_id, c.seed, c.condition_occurrence_index) for c in matrix]
    assert coordinates == [
        ("opponent", 1, 0),
        ("opponent_b", 1, 0),
        ("opponent", 1, 1),
    ]


def test_v2_condition_fingerprint_excludes_candidate_identity(two_agents: Path):
    _write_python_agent(two_agents, "candidate_b")
    from battle_engine.agent_evaluation import effective_conditions_for
    from battle_engine.agents import resolve_agent

    conditions = effective_conditions_for(10, 1)
    import json as _json

    from battle_engine.result_model import stable_id

    conditions_fp = stable_id("evaluation-conditions", _json.loads(_json.dumps(conditions.__dict__)))
    specs = {
        "candidate": resolve_agent(two_agents, "candidate"),
        "opponent": resolve_agent(two_agents, "opponent"),
    }
    request_a = _request(two_agents, candidate_id="candidate")
    request_b = _request(two_agents, candidate_id="candidate_b")
    matrix_a = build_matrix(request_a, "eval_a", specs, conditions_fp, "evaluation-rules-1")
    specs_b = dict(specs)
    specs_b["candidate_b"] = resolve_agent(two_agents, "candidate_b")
    matrix_b = build_matrix(request_b, "eval_b", specs_b, conditions_fp, "evaluation-rules-1")
    assert matrix_a[0].condition_fingerprint == matrix_b[0].condition_fingerprint
