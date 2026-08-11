"""``bytefray.evaluation`` v2 capture hardening (docs/specs/evaluation_history.md).

Covers identity/effective-conditions/lifecycle/provenance/drift/duplicate-
coordinate behavior added on top of v0.6.1's v1 artifact. See
``test_agent_evaluation.py`` for the v1-era behavior these tests build on
(matrix construction, aggregation, resume-verification) which remains
unmodified and still passing.
"""

from __future__ import annotations

import hashlib
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
    # Sec 5.3 of docs/specs/agent_revision.md: SCHEMA_VERSION bumped 2 -> 3
    # for the additive "agent_revisions" field; comparing only against the
    # imported constant (not a second hardcoded literal) so this assertion
    # doesn't itself go stale on the next legitimate, reviewed bump.
    assert data["schema_version"] == SCHEMA_VERSION
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


def test_v2_no_op_resume_under_a_mocked_different_runtime_preserves_completion_chronology(
    two_agents: Path, monkeypatch
):
    """M1: a true no-op resume must preserve original execution completion
    chronology even when the resuming process itself is a different
    Bytefray/Python build -- finished_at, created_at, per-cell execution
    provenance, and the execution_contexts list must all stay exactly as
    they were. Only `updated_at` and the writer/resumer-only `project`
    block (explicitly not cell execution provenance) may legitimately
    differ.
    """

    import battle_engine.agent_evaluation as mod

    request = _request(two_agents)
    service = EvaluationService()
    first = service.run(request)
    first_data = json.loads(first.state_path.read_text(encoding="utf-8"))
    assert first_data["lifecycle_state"] == "finished"
    assert first_data["finished_at"] is not None

    monkeypatch.setattr(
        mod,
        "current_execution_context",
        lambda rules_id: mod.ExecutionContext(
            context_id="evaluation-context_mockedmockedmockedmocked",
            bytefray_version="9.9.9-mocked",
            agent_api_version=1,
            python_version="9.9.9",
            result_schema_version=1,
            replay_schema_version=3,
            rules_compatibility_id=rules_id,
        ),
    )
    second = service.run(request)
    second_data = json.loads(second.state_path.read_text(encoding="utf-8"))

    assert second_data["lifecycle_state"] == "finished"
    assert second_data["finished_at"] == first_data["finished_at"]
    assert second_data["created_at"] == first_data["created_at"]
    assert second_data["execution_contexts"] == first_data["execution_contexts"]
    for before, after in zip(first_data["cells"], second_data["cells"]):
        assert before["execution_context_id"] == after["execution_context_id"]
        assert before["match_id"] == after["match_id"]
        assert before["status"] == after["status"] == "completed"
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
# M2: a drift-aborted cell must never be retried by --retry-failed
# ---------------------------------------------------------------------------


def test_drift_artifact_retry_failed_does_not_retry_while_source_remains_changed(
    tmp_path: Path, monkeypatch
):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opp_a")
    _write_python_agent(tmp_path, "opp_b")
    request = _request(tmp_path, opponent_ids=("opp_a", "opp_b"), seeds=(1,))
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    def _detect_with_injected_drift(self, cell, planned_identities, root):
        if cell.opponent_id == "opp_b":
            return {"error_code": "pre_execution_source_drift", "error_message": "boom"}
        return None

    monkeypatch.setattr(
        mod.EvaluationService, "_detect_pre_execution_drift", _detect_with_injected_drift
    )
    first = service.run(request)
    assert first.cells[-1].status == "drift_detected"

    # The (simulated) drift condition is still present -- --retry-failed
    # must still refuse to retry the drifted cell, exactly like an ordinary
    # resume.
    from dataclasses import replace as _replace

    retried = service.run(_replace(request, retry_failures=True))
    retried_data = json.loads(retried.state_path.read_text(encoding="utf-8"))
    assert retried_data["lifecycle_state"] == "aborted"
    assert retried_data["cells"][-1]["status"] == "drift_detected"
    assert retried_data["cells"][-1]["opponent_id"] == "opp_b"


def test_drift_artifact_retry_failed_does_not_retry_even_after_source_restored(
    tmp_path: Path, monkeypatch
):
    """Once an evaluation has aborted on drift, that specific artifact is
    terminal for the affected cell -- even reverting the (simulated) drift
    condition does not make --retry-failed re-execute it inside the same
    plan. The only correct recovery is a fresh evaluation (Sec 7/M2)."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opp_a")
    _write_python_agent(tmp_path, "opp_b")
    request = _request(tmp_path, opponent_ids=("opp_a", "opp_b"), seeds=(1,))
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    original_detect = mod.EvaluationService._detect_pre_execution_drift

    def _detect_with_injected_drift(self, cell, planned_identities, root):
        if cell.opponent_id == "opp_b":
            return {"error_code": "pre_execution_source_drift", "error_message": "boom"}
        return original_detect(self, cell, planned_identities, root)

    monkeypatch.setattr(
        mod.EvaluationService, "_detect_pre_execution_drift", _detect_with_injected_drift
    )
    first = service.run(request)
    assert first.cells[-1].status == "drift_detected"

    # "Source restored": the injected drift condition is removed entirely,
    # as if the underlying edit had been reverted.
    monkeypatch.setattr(mod.EvaluationService, "_detect_pre_execution_drift", original_detect)

    from dataclasses import replace as _replace

    retried = service.run(_replace(request, retry_failures=True))
    retried_data = json.loads(retried.state_path.read_text(encoding="utf-8"))
    assert retried_data["lifecycle_state"] == "aborted"
    assert retried_data["cells"][-1]["status"] == "drift_detected"
    assert retried_data["cells"][-1]["opponent_id"] == "opp_b"


# ---------------------------------------------------------------------------
# B1: frozen-plan TOCTOU -- real file/manifest mutations, not monkeypatched
# drift detectors. Each test mutates actual bytes on disk in the gap the
# independent review reproduced (between the pre-execution check and the
# executor's own resolution/execution) and asserts the evaluation aborts
# with the drifted cell recorded honestly, never silently accepted.
# ---------------------------------------------------------------------------


def test_toctou_edit_between_precheck_and_execution_is_detected(tmp_path: Path, monkeypatch):
    """Source changes strictly between the pre-check and ``test_agent``.

    Before the fix, the post-execution check recomputed its "expected"
    match id by re-reading the same (already-edited) file ``test_agent``
    itself had just read, so the comparison trivially passed. The fix
    compares against the identity frozen once at preflight instead.
    """

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    request = _request(tmp_path)
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    real_test_agent = mod.test_agent
    agent_path = tmp_path / "agents" / "candidate" / "agent.py"
    original_source = agent_path.read_text(encoding="utf-8")
    # Hashed straight off disk (not re-encoded from the text read above) so
    # this matches exactly what `agent_identity()`'s `source_sha256` hashes
    # -- avoids a spurious mismatch from newline translation on Windows.
    original_digest = hashlib.sha256(agent_path.read_bytes()).hexdigest()

    def _edit_then_run(*args, **kwargs):
        agent_path.write_text(
            original_source.replace(NOP_ACTION, NOP_ACTION + "  # edited"), encoding="utf-8"
        )
        return real_test_agent(*args, **kwargs)

    monkeypatch.setattr(mod, "test_agent", _edit_then_run)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["lifecycle_state"] == "aborted"
    assert data["abort_reason"] == "source_drift"
    cell = data["cells"][0]
    assert cell["status"] == "drift_detected"
    assert cell["error_code"] == "post_execution_identity_drift"
    # The persisted planned identity must still reflect the ORIGINAL
    # (frozen) content, never the edited file -- proving the write path
    # never re-reads live disk after the fact (the core B1 invariant).
    assert data["planned_identities"]["candidate"]["source_sha256"] == original_digest


def test_toctou_edit_during_execution_is_detected(tmp_path: Path, monkeypatch):
    """Source changes inside ``test_agent``'s own execution.

    Hooks ``python_runtime.load_python_agent`` (used by
    ``PythonEntrantController.__init__``) to edit the opponent's file
    immediately after it is loaded -- deeper than the module boundary
    ``agent_evaluation`` itself controls -- and confirms the post-execution
    check still catches it because it compares the executor's own recorded
    entrant metadata against the frozen plan, not a second disk read.
    """

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    request = _request(tmp_path)
    service = EvaluationService()

    import battle_engine.python_runtime as runtime_mod

    opponent_path = tmp_path / "agents" / "opponent" / "agent.py"
    original_source = opponent_path.read_text(encoding="utf-8")
    real_load = runtime_mod.load_python_agent

    def _load_then_edit(spec):
        loaded = real_load(spec)
        if spec.name == "opponent":
            opponent_path.write_text(
                original_source.replace(NOP_ACTION, NOP_ACTION + "  # edited-during-execution"),
                encoding="utf-8",
            )
        return loaded

    monkeypatch.setattr(runtime_mod, "load_python_agent", _load_then_edit)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    cell = data["cells"][0]
    assert cell["status"] == "drift_detected"
    assert cell["error_code"] == "post_execution_identity_drift"
    assert data["lifecycle_state"] == "aborted"


def test_toctou_edit_then_restore_is_not_falsely_flagged(tmp_path: Path, monkeypatch):
    """A transient edit that fully reverts before ``test_agent`` reads it.

    This is the documented residual TOCTOU window this module cannot
    close (see ``_post_execution_identity_drift``'s docstring): content
    that is back to the originally planned bytes by the time anything
    reads it must complete normally, not be falsely reported as drift.
    """

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    request = _request(tmp_path)
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    real_test_agent = mod.test_agent
    agent_path = tmp_path / "agents" / "candidate" / "agent.py"
    original_source = agent_path.read_text(encoding="utf-8")

    def _edit_restore_then_run(*args, **kwargs):
        agent_path.write_text(
            original_source.replace(NOP_ACTION, NOP_ACTION + "  # transient"), encoding="utf-8"
        )
        agent_path.write_text(original_source, encoding="utf-8")
        return real_test_agent(*args, **kwargs)

    monkeypatch.setattr(mod, "test_agent", _edit_restore_then_run)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["lifecycle_state"] == "finished"
    assert data["cells"][0]["status"] == "completed"


def test_toctou_manifest_entry_point_change_is_detected(tmp_path: Path, monkeypatch):
    """A manifest entry-point retarget between pre-check and execution.

    Entry-point/factory semantics are part of ``agent_identity()``, but a
    changed entry point is only observable through what it causes the
    executor to actually load and run -- this proves that flows through to
    the post-execution metadata check.
    """

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    alt_path = tmp_path / "agents" / "candidate" / "alt_agent.py"
    alt_path.write_text(
        """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.NOP)  # a distinct revision
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "agents" / "candidate" / "agent.yaml"
    request = _request(tmp_path)
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    real_test_agent = mod.test_agent

    def _retarget_entry_point_then_run(*args, **kwargs):
        manifest_path.write_text(
            json.dumps(
                {
                    "kind": "python",
                    "api_version": 1,
                    "entrypoint": "alt_agent.py:create_agent",
                    "version": "1.0",
                }
            ),
            encoding="utf-8",
        )
        return real_test_agent(*args, **kwargs)

    monkeypatch.setattr(mod, "test_agent", _retarget_entry_point_then_run)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    cell = data["cells"][0]
    assert cell["status"] == "drift_detected"
    assert cell["error_code"] == "post_execution_identity_drift"


# ---------------------------------------------------------------------------
# B1 (v0.7 closure pass): frozen execution-time identity must catch a
# same-file factory retarget and a local-helper-only edit, neither of which
# changes the entry file's own `source_sha256` -- these require the
# executor's own recorded `entry_point`/`local_source_fingerprint` (not a
# second live disk read) to be part of the post-execution comparison.
# ---------------------------------------------------------------------------


def test_toctou_same_file_factory_retarget_is_detected(tmp_path: Path, monkeypatch):
    """``agent.yaml`` retargeted from ``create_agent`` to ``create_alt`` --
    both factories live in the *same unchanged* ``agent.py`` file, so
    `source_sha256` never changes and cannot be what catches this. Only the
    executor's own recorded `entry_point` (the string it actually resolved
    and imported from) can."""

    candidate_dir = _write_python_agent(tmp_path, "candidate")
    (candidate_dir / "agent.py").write_text(
        """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
def create_alt(): return Agent()
""",
        encoding="utf-8",
    )
    _write_python_agent(tmp_path, "opponent")
    manifest_path = candidate_dir / "agent.yaml"
    original_source_sha256 = hashlib.sha256((candidate_dir / "agent.py").read_bytes()).hexdigest()
    request = _request(tmp_path)
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    real_test_agent = mod.test_agent

    def _retarget_factory_then_run(*args, **kwargs):
        manifest_path.write_text(
            json.dumps(
                {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_alt", "version": "1.0"}
            ),
            encoding="utf-8",
        )
        return real_test_agent(*args, **kwargs)

    monkeypatch.setattr(mod, "test_agent", _retarget_factory_then_run)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    cell = data["cells"][0]
    assert cell["status"] == "drift_detected"
    assert cell["error_code"] == "post_execution_identity_drift"
    assert "entry_point" in cell["error_message"]
    # The entry file's own bytes never changed -- source_sha256 alone would
    # have missed this; the failure must be attributed to entry_point.
    assert (candidate_dir / "agent.py").read_bytes()
    assert hashlib.sha256((candidate_dir / "agent.py").read_bytes()).hexdigest() == original_source_sha256

    # Persisted planned identity must still reflect the ORIGINAL frozen
    # entry point, never the retargeted one.
    planned_candidate = data["planned_identities"]["candidate"]
    assert planned_candidate["entry_point"] == "agent.py:create_agent"

    # The evaluation ID must still reproduce deterministically from the
    # exact persisted plan (identity_version/candidate/baseline/opponents/
    # seeds/ticks/effective_conditions/rules_compatibility_id) -- the drift
    # abort must never have mutated the frozen plan that defines it.
    from battle_engine.agent_evaluation import IDENTITY_VERSION as CURRENT_IDENTITY_VERSION
    from battle_engine.result_model import stable_id

    recomputed = stable_id(
        "evaluation-v2",
        {
            "identity_version": data["identity_version"],
            "candidate": data["planned_identities"]["candidate"],
            "baseline": data["planned_identities"]["baseline"],
            "opponents": data["planned_identities"]["opponents"],
            "seeds": data["seeds"],
            "ticks": data["ticks"],
            "effective_conditions": data["effective_conditions"],
            "rules_compatibility_id": data["rules_compatibility_id"],
        },
    )
    assert data["identity_version"] == CURRENT_IDENTITY_VERSION
    assert recomputed == data["evaluation_id"]


def test_toctou_local_helper_edit_after_precheck_is_detected(tmp_path: Path, monkeypatch):
    """A local helper file (not the entry-point file itself) edited after
    the pre-execution check and left in place must still be caught, via
    the executor's own recorded `local_source_fingerprint` of the whole
    agent directory it actually loaded from -- `source_sha256` (entry file
    only) cannot see this class of edit at all."""

    candidate_dir = _write_python_agent(tmp_path, "candidate")
    helper_path = candidate_dir / "helper.py"
    helper_path.write_text("VALUE = 1\n", encoding="utf-8")
    _write_python_agent(tmp_path, "opponent")
    request = _request(tmp_path)
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    real_test_agent = mod.test_agent

    def _edit_helper_then_run(*args, **kwargs):
        helper_path.write_text("VALUE = 2  # edited after precheck, left in place\n", encoding="utf-8")
        return real_test_agent(*args, **kwargs)

    monkeypatch.setattr(mod, "test_agent", _edit_helper_then_run)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    cell = data["cells"][0]
    assert cell["status"] == "drift_detected"
    assert cell["error_code"] == "post_execution_identity_drift"
    assert "local_source_fingerprint" in cell["error_message"]
    # The persisted plan must still reflect the identity frozen BEFORE the
    # helper edit (the original two-file fingerprint), never re-derived
    # from the now-edited directory.
    from battle_engine.agent_api import local_source_fingerprint

    assert data["planned_identities"]["candidate"]["local_source_fingerprint"] != local_source_fingerprint(
        candidate_dir
    )


# ---------------------------------------------------------------------------
# Second closure pass: a local helper imported *lazily* from inside
# reset()/act() -- rather than at module load time -- can change between
# the executor's load-time ("initial") fingerprint and the moment that
# lazy import actually executes. The load-time fingerprint alone cannot
# see this; only a second, "final" fingerprint taken after the match
# finishes (python_runtime.PythonEntrantController.run) can.
# ---------------------------------------------------------------------------


def _write_lazy_helper_candidate(root: Path) -> tuple[Path, Path]:
    """A candidate whose act() lazily imports helper.py fresh on every
    call (via importlib.util directly, bypassing sys.modules caching --
    ordinary `import helper` would only ever read the file once per
    process), rather than importing it at module load time. Its own
    behavior is made to depend on the imported value (HALT immediately if
    helper.VALUE == 2, otherwise run an ordinary NOP loop) so a test can
    prove from the match's own observable outcome (ticks_run) that a given
    helper.py revision was actually read and acted on by a real act() call,
    not merely present on disk.
    """

    directory = root / "agents" / "candidate"
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
import importlib.util
from pathlib import Path

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        helper_path = Path(__file__).parent / "helper.py"
        spec = importlib.util.spec_from_file_location("lazy_helper_probe", helper_path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        if helper.VALUE == 2:
            return AgentAction(ActionKind.HALT)
        return AgentAction(ActionKind.NOP)

def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    helper_path = directory / "helper.py"
    helper_path.write_text("VALUE = 1\n", encoding="utf-8")
    return directory, helper_path


def test_lazy_import_helper_edit_after_initial_fingerprint_is_detected(
    tmp_path: Path, monkeypatch
):
    """Required regression test: an initial fingerprint is captured at
    controller construction; the helper is then changed; a lazy import
    inside act() demonstrably observes and acts on the changed helper
    (proven via the real match's own ticks_run); the evaluation records
    drift, not a valid completed cell."""

    _, helper_path = _write_lazy_helper_candidate(tmp_path)
    _write_python_agent(tmp_path, "opponent")
    request = _request(tmp_path, ticks=20)
    service = EvaluationService()

    import battle_engine.python_runtime as runtime_mod

    real_run = runtime_mod.PythonEntrantController.run

    def _edit_helper_then_run(self, sink, *, verbose):
        # PythonEntrantController.__init__ has already captured the
        # *initial* load-time fingerprint (over "VALUE = 1") by the time
        # `.run()` is called. Edit the helper now -- strictly between that
        # capture and the tick loop's act() calls -- so the lazy import
        # inside act() observes this edit.
        helper_path.write_text("VALUE = 2  # edited after initial fingerprint\n", encoding="utf-8")
        return real_run(self, sink, verbose=verbose)

    monkeypatch.setattr(runtime_mod.PythonEntrantController, "run", _edit_helper_then_run)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    cell = data["cells"][0]
    assert cell["status"] == "drift_detected"
    assert cell["error_code"] == "post_execution_identity_drift"

    fields_text = cell["error_message"].split("(fields: ", 1)[1].split(")", 1)[0]
    mismatched_fields = [field.strip() for field in fields_text.split(",")]
    # Only the *final* fingerprint mismatches -- the load-time one
    # genuinely matched the frozen plan (the edit landed after it was
    # captured), so it must not itself be reported as mismatched too.
    assert mismatched_fields == ["local_source_fingerprint_final"]

    # Prove the changed helper actually executed: the real match ran to
    # completion and halted at tick 1, which only happens if act() saw
    # helper.VALUE == 2.
    cell_dir = result.state_path.parent / cell["artifact_dir"]
    match_result_data = json.loads((cell_dir / "result.json").read_text(encoding="utf-8"))
    assert match_result_data["ticks"] == 1


def test_lazy_import_unchanged_helper_execution_remains_valid(tmp_path: Path):
    """Confirmation: ordinary unchanged-source execution (the lazy-import
    candidate's helper never edited) still completes normally."""

    _write_lazy_helper_candidate(tmp_path)
    _write_python_agent(tmp_path, "opponent")
    request = _request(tmp_path, ticks=20)
    service = EvaluationService()

    result = service.run(request)
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    cell = data["cells"][0]
    assert cell["status"] == "completed"
    assert data["lifecycle_state"] == "finished"

    # act() ran the ordinary NOP loop the whole time (helper.VALUE stayed
    # 1), so the match used the full tick budget rather than halting early.
    cell_dir = result.state_path.parent / cell["artifact_dir"]
    match_result_data = json.loads((cell_dir / "result.json").read_text(encoding="utf-8"))
    assert match_result_data["ticks"] == 20


def test_lazy_import_helper_edit_and_restore_before_final_check_is_not_falsely_flagged(
    tmp_path: Path, monkeypatch
):
    """Confirmation: the final-fingerprint check shares the same narrow
    residual race as the existing load/digest edit-and-restore limitation,
    not a new or broader one. Here the agent's own act() call reads a
    transiently edited helper (proven by halting at tick 1) and then
    restores the original bytes itself before the match finishes -- by the
    time the executor's final fingerprint is computed (after the whole
    match loop), the directory already matches the frozen plan again, so
    this must not be falsely reported as drift despite the transient edit
    having been demonstrably read and acted on."""

    directory = tmp_path / "agents" / "candidate"
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
import importlib.util
from pathlib import Path

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        helper_path = Path(__file__).parent / "helper.py"
        spec = importlib.util.spec_from_file_location("lazy_helper_probe_restore", helper_path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        observed = helper.VALUE
        helper_path.write_text("VALUE = 1")
        if observed == 2:
            return AgentAction(ActionKind.HALT)
        return AgentAction(ActionKind.NOP)

def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    helper_path = directory / "helper.py"
    # No trailing newline, deliberately -- the agent's own restore write
    # below must reproduce these exact bytes for this to be a genuine
    # edit-and-restore (byte-identical), not merely a same-VALUE rewrite.
    helper_path.write_text("VALUE = 1", encoding="utf-8")
    _write_python_agent(tmp_path, "opponent")
    request = _request(tmp_path, ticks=20)
    service = EvaluationService()

    import battle_engine.python_runtime as runtime_mod

    real_run = runtime_mod.PythonEntrantController.run

    def _edit_then_run(self, sink, *, verbose):
        helper_path.write_text("VALUE = 2", encoding="utf-8")
        return real_run(self, sink, verbose=verbose)

    monkeypatch.setattr(runtime_mod.PythonEntrantController, "run", _edit_then_run)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    cell = data["cells"][0]
    assert cell["status"] == "completed"
    assert data["lifecycle_state"] == "finished"

    cell_dir = result.state_path.parent / cell["artifact_dir"]
    match_result_data = json.loads((cell_dir / "result.json").read_text(encoding="utf-8"))
    # Halted at tick 1 -- proves the transient edit WAS read and acted on;
    # it is simply not detectable after having fully reverted by the time
    # the final fingerprint is computed.
    assert match_result_data["ticks"] == 1
    assert helper_path.read_text(encoding="utf-8") == "VALUE = 1"


def test_toctou_initialization_failure_after_intervening_source_change_is_flagged_as_drift(
    tmp_path: Path, monkeypatch
):
    """An init failure caused by a post-precheck edit must not be silently
    attributed to the original, frozen agent as an ordinary
    ``subject_init_failed`` outcome -- it belongs to a different (edited)
    revision than what was planned and must abort as drift instead.
    """

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    request = _request(tmp_path)
    service = EvaluationService()

    import battle_engine.agent_evaluation as mod

    real_test_agent = mod.test_agent
    agent_path = tmp_path / "agents" / "candidate" / "agent.py"

    def _break_then_run(*args, **kwargs):
        agent_path.write_text(
            """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): raise RuntimeError("boom")
    def act(self, observation): return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
""",
            encoding="utf-8",
        )
        return real_test_agent(*args, **kwargs)

    monkeypatch.setattr(mod, "test_agent", _break_then_run)
    result = service.run(request)

    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    cell = data["cells"][0]
    assert cell["status"] == "drift_detected"
    assert cell["outcome"] != "subject_init_failed"


def test_persisted_planned_identity_rehashes_to_the_recorded_evaluation_id(two_agents: Path):
    """The core B1 invariant: recomputing the v2 evaluation-id payload from
    the persisted ``planned_identities`` must reproduce the stored
    ``evaluation_id`` exactly -- the artifact can never claim one plan while
    having persisted a different one.
    """

    from battle_engine.agent_evaluation import EVALUATION_RULES_COMPATIBILITY_ID
    from battle_engine.result_model import stable_id

    service = EvaluationService()
    result = service.run(_request(two_agents))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    planned = data["planned_identities"]
    payload = {
        "identity_version": IDENTITY_VERSION,
        "candidate": planned["candidate"],
        "baseline": planned["baseline"],
        "opponents": planned["opponents"],
        "seeds": data["seeds"],
        "ticks": data["ticks"],
        "effective_conditions": data["effective_conditions"],
        "rules_compatibility_id": EVALUATION_RULES_COMPATIBILITY_ID,
    }
    assert stable_id("evaluation-v2", payload) == data["evaluation_id"]


# ---------------------------------------------------------------------------
# B2: resume must never erase a completed artifact before verification
# ---------------------------------------------------------------------------


def test_resume_failure_before_first_prior_cell_verification_preserves_state(
    two_agents: Path, monkeypatch
):
    """A crash injected in ``_resolve_from_state`` for the very first prior
    cell must leave the already-persisted (finished) artifact untouched --
    it must not have been pre-emptively overwritten with an empty
    ``cells=()`` checkpoint the instant resume started.
    """

    request = _request(two_agents, opponent_ids=("opponent",), seeds=(1, 2))
    service = EvaluationService()
    first = service.run(request)
    original_bytes = first.state_path.read_bytes()
    original_data = json.loads(original_bytes)
    assert original_data["lifecycle_state"] == "finished"
    assert len(original_data["cells"]) == 2

    import battle_engine.agent_evaluation as mod

    def _boom(self, cell, previous, specs, req):
        raise RuntimeError("simulated crash before first prior-cell verification")

    monkeypatch.setattr(mod.EvaluationService, "_resolve_from_state", _boom)
    with pytest.raises(RuntimeError):
        EvaluationService().run(request)

    assert first.state_path.read_bytes() == original_bytes


def test_resume_failure_after_one_prior_cell_verification_preserves_state(
    two_agents: Path, monkeypatch
):
    """A crash after the first prior cell verifies successfully but before
    the second does must still leave the original finished artifact fully
    intact -- not a truncated one-cell ``running`` snapshot.
    """

    request = _request(two_agents, opponent_ids=("opponent",), seeds=(1, 2))
    service = EvaluationService()
    first = service.run(request)
    original_bytes = first.state_path.read_bytes()

    import battle_engine.agent_evaluation as mod

    real_resolve = mod.EvaluationService._resolve_from_state
    calls = {"n": 0}

    def _boom_on_second(self, cell, previous, specs, req):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated crash after first prior-cell verification")
        return real_resolve(self, cell, previous, specs, req)

    monkeypatch.setattr(mod.EvaluationService, "_resolve_from_state", _boom_on_second)
    with pytest.raises(RuntimeError):
        EvaluationService().run(request)

    assert first.state_path.read_bytes() == original_bytes


def test_resume_failure_after_final_prior_cell_verification_preserves_state(
    two_agents: Path, monkeypatch
):
    """A crash after every prior cell has verified (in-memory reconstruction
    complete) but before the final aggregation/write must still leave the
    original finished artifact intact -- proves the fixed loop never writes
    a partial reconstruction mid-flight, only ever the final consolidated
    state. This is also the "original finished state survives a failed
    no-op resume" requirement.
    """

    request = _request(two_agents, opponent_ids=("opponent",), seeds=(1, 2))
    service = EvaluationService()
    first = service.run(request)
    original_bytes = first.state_path.read_bytes()

    import battle_engine.agent_evaluation as mod

    def _boom(self, req, cells):
        raise RuntimeError("simulated crash after final prior-cell verification")

    monkeypatch.setattr(mod.EvaluationService, "_all_aggregates", _boom)
    with pytest.raises(RuntimeError):
        EvaluationService().run(request)

    assert first.state_path.read_bytes() == original_bytes


def test_resume_failure_during_retry_preparation_preserves_untouched_cells(
    two_agents: Path, monkeypatch
):
    """A crash while deciding whether a failed cell should be retried must
    not have already erased a *different*, untouched, already-completed
    cell earlier in the matrix.
    """

    request = _request(two_agents, opponent_ids=("opponent",), seeds=(1, 2))
    service = EvaluationService()
    first = service.run(request)
    state_path = first.state_path
    data = json.loads(state_path.read_text(encoding="utf-8"))
    # Cell 0 stays a genuine completed cell (untouched); cell 1 is tampered
    # into a "failed" cell the way a real infra failure would leave it, so
    # --retry-failed has something to retry.
    data["cells"][1]["status"] = "failed"
    data["cells"][1]["outcome"] = None
    data["cells"][1]["error_code"] = "engine_failed"
    state_path.write_text(json.dumps(data), encoding="utf-8")
    original_bytes = state_path.read_bytes()

    import battle_engine.agent_evaluation as mod

    real_resolve = mod.EvaluationService._resolve_from_state

    def _boom_on_retry_candidate(self, cell, previous, specs, req):
        if previous.get("status") == "failed":
            raise RuntimeError("simulated crash during retry preparation")
        return real_resolve(self, cell, previous, specs, req)

    monkeypatch.setattr(mod.EvaluationService, "_resolve_from_state", _boom_on_retry_candidate)
    from dataclasses import replace as _replace

    with pytest.raises(RuntimeError):
        EvaluationService().run(_replace(request, retry_failures=True))

    # The untouched completed cell (and the whole artifact) must be exactly
    # as tampered/persisted before this crashed retry attempt -- no
    # temporary erasure of cells the retry never even reached.
    assert state_path.read_bytes() == original_bytes


def test_retry_checkpoint_never_erases_a_later_already_durable_cell(
    two_agents: Path, monkeypatch
):
    """B2 repro, exactly as specified: seed 1 failed, seed 2 completed;
    resume with retry_failures=True; retry seed 1; crash immediately after
    its checkpoint. Before the fix, that checkpoint serialized only the
    matrix prefix reconstructed so far in this run's own loop (just the
    retried seed-1 cell), silently dropping the already-durable seed-2 cell
    from disk. The checkpoint written right before the crash must be at
    least as complete as what was already durable.
    """

    request = _request(two_agents, opponent_ids=("opponent",), seeds=(1, 2))
    service = EvaluationService()
    first = service.run(request)
    state_path = first.state_path
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["cells"][0]["seed"] == 1
    assert data["cells"][1]["seed"] == 2
    assert data["cells"][1]["status"] == "completed"
    # Seed 1 tampered into a failed cell (simulating a real infra failure)
    # so --retry-failed has something to retry; seed 2 stays genuinely
    # durable, untouched.
    data["cells"][0]["status"] = "failed"
    data["cells"][0]["outcome"] = None
    data["cells"][0]["error_code"] = "engine_failed"
    state_path.write_text(json.dumps(data), encoding="utf-8")

    import battle_engine.agent_evaluation as mod

    real_write_state = mod.EvaluationService._write_state
    call_count = {"n": 0}

    def _write_then_crash_once(self, *args, **kwargs):
        real_write_state(self, *args, **kwargs)
        call_count["n"] += 1
        if call_count["n"] == 1:
            # The retried seed-1 cell's own checkpoint has just been
            # durably written to disk -- crash immediately after it, before
            # this run's loop ever reaches seed 2.
            raise RuntimeError("simulated crash immediately after the retried cell's checkpoint")

    monkeypatch.setattr(mod.EvaluationService, "_write_state", _write_then_crash_once)
    from dataclasses import replace as _replace

    with pytest.raises(RuntimeError):
        EvaluationService().run(_replace(request, retry_failures=True))

    assert call_count["n"] == 1
    post_crash = json.loads(state_path.read_text(encoding="utf-8"))
    cells_by_seed = {cell["seed"]: cell for cell in post_crash["cells"]}
    # The already-durable seed-2 cell must still be present and untouched.
    assert 2 in cells_by_seed
    assert cells_by_seed[2]["status"] == "completed"
    assert cells_by_seed[2]["match_id"] == data["cells"][1]["match_id"]
    # The retried seed-1 cell itself was freshly re-executed and succeeded.
    assert 1 in cells_by_seed
    assert cells_by_seed[1]["status"] == "completed"


def test_fresh_evaluation_still_gets_the_first_checkpoint_before_any_cell(
    two_agents: Path, monkeypatch
):
    """Regression guard: the B2 fix (skip the pre-loop checkpoint when
    resuming) must not regress Sec 5's crash-safety guarantee for a
    genuinely *new* evaluation, which has no prior cells to protect.
    """

    import battle_engine.agent_evaluation as mod

    request = _request(two_agents)
    state_path = request.output_dir / "evaluation.json"

    def _boom(*args, **kwargs):
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["lifecycle_state"] == "running"
        assert data["cells"] == []
        raise RuntimeError("simulated crash before first cell finishes")

    monkeypatch.setattr(mod, "test_agent", _boom)
    with pytest.raises(RuntimeError):
        EvaluationService().run(request)


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


# ---------------------------------------------------------------------------
# H3: local source fingerprint (imported helper / nested local package)
# ---------------------------------------------------------------------------


def _write_helper_agent(root: Path, name: str) -> Path:
    """A local package-shaped agent: agent.py imports a sibling helper.py
    via its own directory on sys.path -- a realistic pattern the framework
    itself does not set up automatically (no import machinery adds an
    agent's directory to sys.path), but does not prevent either."""

    agent_dir = root / "agents" / name
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (agent_dir / "agent.py").write_text(
        """
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import helper
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return helper.pick_action()
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    (agent_dir / "helper.py").write_text(
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "def pick_action(): return AgentAction(ActionKind.NOP)\n",
        encoding="utf-8",
    )
    return agent_dir


def test_local_source_fingerprint_changes_when_entry_point_edited(tmp_path: Path):
    from battle_engine.agent_evaluation import local_source_fingerprint

    agent_dir = _write_helper_agent(tmp_path, "candidate")
    before = local_source_fingerprint(agent_dir)
    (agent_dir / "agent.py").write_text(
        (agent_dir / "agent.py").read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8"
    )
    assert local_source_fingerprint(agent_dir) != before


def test_local_source_fingerprint_changes_when_imported_helper_edited(tmp_path: Path):
    """The exact gap H3 closes: source_digest (entry-point file only) is
    blind to a helper-only edit, but local_source_fingerprint is not."""

    from battle_engine.agent_evaluation import local_source_fingerprint, source_digest

    agent_dir = _write_helper_agent(tmp_path, "candidate")
    entry_point_digest_before = source_digest(agent_dir / "agent.py")
    fingerprint_before = local_source_fingerprint(agent_dir)

    (agent_dir / "helper.py").write_text(
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "def pick_action(): return AgentAction(ActionKind.NOP)  # edited helper\n",
        encoding="utf-8",
    )

    assert source_digest(agent_dir / "agent.py") == entry_point_digest_before
    assert local_source_fingerprint(agent_dir) != fingerprint_before


def test_local_source_fingerprint_changes_when_nested_local_package_edited(tmp_path: Path):
    from battle_engine.agent_evaluation import local_source_fingerprint

    agent_dir = _write_helper_agent(tmp_path, "candidate")
    package_dir = agent_dir / "strategy"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    before = local_source_fingerprint(agent_dir)

    (package_dir / "__init__.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert local_source_fingerprint(agent_dir) != before


def test_local_source_fingerprint_ignores_pycache(tmp_path: Path):
    from battle_engine.agent_evaluation import local_source_fingerprint

    agent_dir = _write_helper_agent(tmp_path, "candidate")
    before = local_source_fingerprint(agent_dir)

    cache_dir = agent_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "agent.cpython-313.py").write_text("# not real bytecode, just proving exclusion\n", encoding="utf-8")

    assert local_source_fingerprint(agent_dir) == before


def test_local_source_fingerprint_none_for_missing_directory(tmp_path: Path):
    from battle_engine.agent_evaluation import local_source_fingerprint

    assert local_source_fingerprint(tmp_path / "does-not-exist") is None


def test_local_source_fingerprint_documents_the_external_dependency_limitation(tmp_path: Path):
    """Explicit boundary: a file outside the agent's own directory that the
    agent nonetheless manages to import (e.g. via an absolute sys.path
    trick, or an installed package) is never hashed -- this is a deliberate
    scope limit (H3), not an oversight."""

    from battle_engine.agent_evaluation import local_source_fingerprint

    agent_dir = _write_helper_agent(tmp_path, "candidate")
    outside_dir = tmp_path / "outside_shared_code"
    outside_dir.mkdir()
    external_helper = outside_dir / "external_helper.py"
    external_helper.write_text("VALUE = 1\n", encoding="utf-8")

    before = local_source_fingerprint(agent_dir)
    external_helper.write_text("VALUE = 2\n", encoding="utf-8")
    assert local_source_fingerprint(agent_dir) == before


def test_evaluation_id_changes_after_helper_only_edit(tmp_path: Path):
    _write_helper_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    service = EvaluationService()
    _specs_before, evaluation_id_before = service.preflight(
        candidate_id="candidate", opponent_ids=("opponent",), seeds=(1,), ticks=10, data_root=tmp_path
    )

    helper_path = tmp_path / "agents" / "candidate" / "helper.py"
    helper_path.write_text(
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "def pick_action(): return AgentAction(ActionKind.NOP)  # edited\n",
        encoding="utf-8",
    )
    _specs_after, evaluation_id_after = service.preflight(
        candidate_id="candidate", opponent_ids=("opponent",), seeds=(1,), ticks=10, data_root=tmp_path
    )
    assert evaluation_id_before != evaluation_id_after


def test_resume_after_helper_edit_requires_a_new_plan_not_a_silent_new_revision(tmp_path: Path):
    """A changed local helper must force a new evaluation plan (a different
    evaluation_id/output directory), never silently execute the edited
    revision inside the old plan's artifact."""

    _write_helper_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    service = EvaluationService()
    request = EvaluationRequest(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        output_dir=tmp_path / "eval-out",
        ticks=10,
        data_root=tmp_path,
    )
    first = service.run(request)

    helper_path = tmp_path / "agents" / "candidate" / "helper.py"
    helper_path.write_text(
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "def pick_action(): return AgentAction(ActionKind.NOP)  # edited\n",
        encoding="utf-8",
    )

    from battle_engine.agent_evaluation import EvaluationConfigurationError

    # Resuming the *same* output directory under the edited helper must be
    # rejected outright -- its frozen plan no longer matches this request.
    with pytest.raises(EvaluationConfigurationError):
        service.run(request)

    # The correct path is a fresh plan under its own (different) evaluation
    # id/output directory, which succeeds normally.
    _specs, evaluation_id_after = service.preflight(
        candidate_id="candidate", opponent_ids=("opponent",), seeds=(1,), ticks=10, data_root=tmp_path
    )
    assert evaluation_id_after != first.evaluation_id
