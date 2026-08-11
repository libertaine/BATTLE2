"""Phase 3 revision-capture integration (docs/specs/agent_revision.md Sec 4/5).

Focused mutation/TOCTOU coverage at the evaluation freeze boundary --
``EvaluationService.run()``'s ``_resolve_revision_results`` call. Does not
touch CLI/history/GUI surfaces (deferred to a later phase); see
``test_agent_revisions.py`` for the underlying engine-primitive coverage
these tests build on.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from battle_engine import agent_evaluation
from battle_engine.agent_evaluation import (
    EvaluationConfigurationError,
    EvaluationRequest,
    EvaluationService,
)
from battle_engine.agent_revisions import (
    agent_revision_fingerprint,
    agent_revision_id,
    agent_revisions_root,
    local_python_subset_fingerprint,
    read_manifest,
    verify_revision,
    walk_agent_files,
)

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_python_agent(root: Path, name: str, action: str = NOP_ACTION) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0",
            }
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


def _load(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Same-source-read invariant
# ---------------------------------------------------------------------------


def test_revision_capture_and_planned_identity_describe_the_same_source_read(
    two_agents: Path,
) -> None:
    result = EvaluationService().run(_request(two_agents))
    data = _load(result.state_path)

    candidate_revision_id = data["agent_revisions"]["candidate"]["agent_revision_id"]
    assert candidate_revision_id is not None
    assert data["agent_revisions"]["candidate"]["agent_revision_error"] is None

    store_root = agent_revisions_root(two_agents)
    assert verify_revision(store_root, candidate_revision_id) is True

    # The frozen plan's own local_source_fingerprint (agent_identity()'s
    # independent read) must equal the .py-subset of the same tree the
    # archival walk captured -- the freeze-time cross-check that gates
    # whether archival was even attempted (Sec 4.2).
    candidate_dir = two_agents / "agents" / "candidate"
    walk = walk_agent_files(candidate_dir)
    assert (
        local_python_subset_fingerprint(walk)
        == (data["planned_identities"]["candidate"]["local_source_fingerprint"])
    )


def test_opponent_revision_also_captured(two_agents: Path) -> None:
    result = EvaluationService().run(_request(two_agents))
    data = _load(result.state_path)
    opponent_entries = data["agent_revisions"]["opponents"]
    assert len(opponent_entries) == 1
    assert opponent_entries[0]["agent_revision_id"] is not None
    store_root = agent_revisions_root(two_agents)
    assert verify_revision(store_root, opponent_entries[0]["agent_revision_id"]) is True


def test_evaluation_captures_symlink_cycle_as_revision_omissions(two_agents: Path) -> None:
    candidate_dir = two_agents / "agents" / "candidate"
    loop_a = candidate_dir / "loop_a.dat"
    loop_b = candidate_dir / "loop_b.dat"
    try:
        os.symlink("loop_b.dat", loop_a)
        os.symlink("loop_a.dat", loop_b)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not permitted in this environment.")

    result = EvaluationService().run(_request(two_agents))
    data = _load(result.state_path)

    assert data["lifecycle_state"] == "finished"
    candidate_revision = data["agent_revisions"]["candidate"]
    assert candidate_revision["agent_revision_error"] is None
    revision_id = candidate_revision["agent_revision_id"]
    assert revision_id is not None

    store_root = agent_revisions_root(two_agents)
    manifest = read_manifest(store_root, revision_id)
    assert manifest["complete"] is False
    assert manifest["omitted"] == [
        {"relative_path": "loop_a.dat", "reason": "resolve_error", "target": "loop_b.dat"},
        {"relative_path": "loop_b.dat", "reason": "resolve_error", "target": "loop_a.dat"},
    ]
    assert verify_revision(store_root, revision_id) is True


def test_duplicate_opponent_occurrences_share_one_revision_id(two_agents: Path) -> None:
    result = EvaluationService().run(
        _request(two_agents, opponent_ids=("opponent", "opponent"), seeds=(1, 2))
    )
    data = _load(result.state_path)
    opponent_entries = data["agent_revisions"]["opponents"]
    assert len(opponent_entries) == 2
    assert opponent_entries[0]["agent_revision_id"] is not None
    assert opponent_entries[0]["agent_revision_id"] == opponent_entries[1]["agent_revision_id"]


# ---------------------------------------------------------------------------
# Freeze-time mutation / TOCTOU
# ---------------------------------------------------------------------------


def test_source_mutation_during_freeze_aborts_before_any_cell_executes(
    two_agents: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source edit landing between agent_identity()'s read and the
    archival walk's read (Sec 4.2's residual window, deliberately narrowed
    but not claimed closed) must abort the whole evaluation, not silently
    archive a revision that doesn't match the frozen plan."""

    candidate_dir = two_agents / "agents" / "candidate"
    real_walk_agent_files = agent_evaluation.walk_agent_files
    mutated = {"done": False}

    def mutating_walk(agent_dir: Path):
        if not mutated["done"] and agent_dir == candidate_dir:
            mutated["done"] = True
            (agent_dir / "agent.py").write_text(
                "from battle_engine.agent_api import ActionKind, AgentAction\n"
                "class Agent:\n"
                "    def reset(self, context): pass\n"
                f"    def act(self, observation): return {NOP_ACTION}\n"
                "def create_agent(): return Agent()\n"
                "# mutated after agent_identity() already read the original bytes\n",
                encoding="utf-8",
            )
        return real_walk_agent_files(agent_dir)

    monkeypatch.setattr(agent_evaluation, "walk_agent_files", mutating_walk)

    execute_calls: list[object] = []
    real_execute_cell = EvaluationService._execute_cell

    def spying_execute_cell(self, *args, **kwargs):
        execute_calls.append(args)
        return real_execute_cell(self, *args, **kwargs)

    monkeypatch.setattr(EvaluationService, "_execute_cell", spying_execute_cell)

    request = _request(two_agents)
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(request)

    assert execute_calls == []
    assert not request.output_dir.exists() or not (request.output_dir / "evaluation.json").exists()


def test_no_cell_executes_after_freeze_mismatch_with_a_larger_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent-a")
    _write_python_agent(tmp_path, "opponent-b")
    candidate_dir = tmp_path / "agents" / "candidate"

    real_walk_agent_files = agent_evaluation.walk_agent_files
    mutated = {"done": False}

    def mutating_walk(agent_dir: Path):
        if not mutated["done"] and agent_dir == candidate_dir:
            mutated["done"] = True
            (agent_dir / "agent.py").write_text(
                "from battle_engine.agent_api import ActionKind, AgentAction\n"
                "class Agent:\n"
                "    def reset(self, context): pass\n"
                f"    def act(self, observation): return {NOP_ACTION}\n"
                "def create_agent(): return Agent()\n"
                "# mutated\n",
                encoding="utf-8",
            )
        return real_walk_agent_files(agent_dir)

    monkeypatch.setattr(agent_evaluation, "walk_agent_files", mutating_walk)

    request = _request(
        tmp_path,
        opponent_ids=("opponent-a", "opponent-b"),
        seeds=(1, 2, 3),
    )
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(request)

    # No cell's per-match artifact tree was ever created.
    assert not (request.output_dir / "matches").exists()
    assert not (request.output_dir / "evaluation.json").exists()


# ---------------------------------------------------------------------------
# Resume/retry revision retention
# ---------------------------------------------------------------------------


def test_resume_retains_originally_planned_revision_id_despite_wider_source_change(
    two_agents: Path,
) -> None:
    request = _request(two_agents)
    first = EvaluationService().run(request)
    first_data = _load(first.state_path)
    original_revision_id = first_data["agent_revisions"]["candidate"]["agent_revision_id"]
    assert original_revision_id is not None
    assert first_data["lifecycle_state"] == "finished"

    # A manifest-only edit: does not change local_source_fingerprint/
    # source_sha256/entry_point/api_version/agent_version (so evaluation_id
    # is unaffected and resume proceeds), but does change the wider
    # agent_revision_fingerprint (Sec 1.4's core justification for keeping
    # the two fingerprints independent).
    candidate_dir = two_agents / "agents" / "candidate"
    manifest_path = candidate_dir / "agent.yaml"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["display"] = "Renamed For This Test"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    # Sanity: the mutation is real and would produce a different revision
    # fingerprint if recomputed fresh right now.
    mutated_fingerprint = agent_revision_fingerprint(candidate_dir)
    mutated_id = agent_revision_id(mutated_fingerprint)
    assert mutated_id != original_revision_id

    second = EvaluationService().run(_request(two_agents))
    assert second.evaluation_id == first.evaluation_id
    second_data = _load(second.state_path)
    assert second_data["agent_revisions"]["candidate"]["agent_revision_id"] == original_revision_id
    assert second_data["lifecycle_state"] == "finished"


def test_resume_retains_opponent_revision_id_positionally(two_agents: Path) -> None:
    request = _request(two_agents)
    first = EvaluationService().run(request)
    first_data = _load(first.state_path)
    original_opponent_revision = first_data["agent_revisions"]["opponents"][0]["agent_revision_id"]
    assert original_opponent_revision is not None

    opponent_dir = two_agents / "agents" / "opponent"
    manifest_path = opponent_dir / "agent.yaml"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["display"] = "Renamed Opponent"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    second = EvaluationService().run(_request(two_agents))
    second_data = _load(second.state_path)
    assert (
        second_data["agent_revisions"]["opponents"][0]["agent_revision_id"]
        == original_opponent_revision
    )


# ---------------------------------------------------------------------------
# Revision-store write failure: recorded, never silently substituted
# ---------------------------------------------------------------------------


def test_revision_store_write_failure_is_recorded_not_substituted(
    two_agents: Path,
) -> None:
    # A file sitting where agent_revisions/ would need to be created --
    # forces every archival write in this evaluation to fail, without
    # relying on platform-specific permission semantics (mirrors the same
    # technique used in test_agent_revisions.py). data_root doubles as
    # both the agent catalog root and the revision-store root
    # (agent_revisions_root(data_root)), so the blocking file must sit
    # under the *same* root the agents/ directory already lives in, not a
    # separate, agent-free root.
    (two_agents / "agent_revisions").write_text("not a directory", encoding="utf-8")

    request = _request(two_agents)
    result = EvaluationService().run(request)
    data = _load(result.state_path)
    assert data["lifecycle_state"] == "finished"

    candidate_entry = data["agent_revisions"]["candidate"]
    assert candidate_entry["agent_revision_error"] is not None
    assert candidate_entry["agent_revision_id"] is not None

    # Not silently substituted: the recorded id is still the *correct*
    # content-derived id, identical to what a working store would compute
    # for the same source tree.
    candidate_dir = two_agents / "agents" / "candidate"
    expected_fingerprint = agent_revision_fingerprint(candidate_dir)
    assert candidate_entry["agent_revision_id"] == agent_revision_id(expected_fingerprint)


def test_evaluation_id_unaffected_by_revision_store_write_failure(
    two_agents: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    working = EvaluationService().run(_request(two_agents, output_dir=two_agents / "working"))

    # A second data root with an identical copy of the same agents (so
    # planned identities/evaluation_id inputs match exactly) but with its
    # agent_revisions path blocked -- isolates "store write fails" from
    # "agent resolution fails" (both would otherwise share one data_root).
    broken_root = tmp_path_factory.mktemp("broken-data-root")
    shutil.copytree(two_agents / "agents", broken_root / "agents")
    (broken_root / "agent_revisions").write_text("not a directory", encoding="utf-8")
    broken = EvaluationService().run(
        _request(broken_root, output_dir=two_agents / "broken", data_root=broken_root)
    )

    assert working.evaluation_id == broken.evaluation_id


# ---------------------------------------------------------------------------
# evaluation_id / v0.7 identity unchanged; v1/v2 artifacts stay readable
# ---------------------------------------------------------------------------


def test_planned_identities_payload_carries_no_revision_fields(two_agents: Path) -> None:
    """planned_identities must remain byte-for-byte what agent_identity()
    produces -- agent_revisions is a wholly separate sibling key (Sec 5.2,
    revised after the first implementation attempt broke the existing "B1"
    rehash invariant by merging the two)."""

    result = EvaluationService().run(_request(two_agents))
    data = _load(result.state_path)
    for role_entry in (
        data["planned_identities"]["candidate"],
        *[o for o in data["planned_identities"]["opponents"]],
    ):
        assert "agent_revision_id" not in role_entry
        assert "agent_revision_error" not in role_entry
    assert "agent_revisions" in data


def test_v2_shaped_artifact_rejected_by_existing_schema_gate_not_a_new_crash(
    two_agents: Path,
) -> None:
    """A schema_version 2-style artifact (no agent_revisions key at all --
    the exact shape a pre-Phase-3 build would have written) hitting
    ``_load_state``'s pre-existing schema_version gate must still fail with
    the same typed, documented error v1 -> v2 already established (Sec 5.3:
    "a v2 evaluation.json is not resumable under this schema_version"),
    never a new, un-typed crash (e.g. a bare ``KeyError`` on the now-
    missing ``agent_revisions`` key) introduced by this phase's changes."""

    request = _request(two_agents)
    result = EvaluationService().run(request)
    data = _load(result.state_path)
    data["schema_version"] = 2
    del data["agent_revisions"]
    result.state_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(EvaluationConfigurationError, match="unsupported schema version"):
        EvaluationService().run(request)


def test_prior_revision_lookup_degrades_gracefully_without_agent_revisions_key() -> None:
    """Unit-level coverage for the defensive branch integration can't reach
    today (_load_state's own gate already guarantees a resumable ``prior``
    always has schema_version == SCHEMA_VERSION, hence always has
    ``agent_revisions``) -- ``_prior_revision_by_agent_id`` must still
    degrade to "nothing recorded yet" rather than raising, matching
    AGENTS.md's "treat malformed persisted artifacts as untrusted input"
    for any future caller that doesn't happen to share that guarantee."""

    from battle_engine.agent_evaluation import _prior_revision_by_agent_id

    assert _prior_revision_by_agent_id({}) == {}
    assert _prior_revision_by_agent_id({"candidate_id": "candidate"}) == {}
    assert (
        _prior_revision_by_agent_id(
            {"candidate_id": "candidate", "agent_revisions": "not-a-mapping"}
        )
        == {}
    )
