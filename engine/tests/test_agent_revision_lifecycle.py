"""End-to-end agent-revision lifecycle (docs/specs/agent_revision.md Sec 7,
v0.8 audit task Sec 7 "Historical workflow"):

    1. evaluate an agent
    2. evaluation records revision provenance
    3. edit the live agent
    4. history still reports the historical revision
    5. revision source can be inspected from the store
    6. revision can be restored to a safe target
    7. restored content matches the historical revision id
    8. existing agent tooling (agents validate) operates on the restored
       agent, composed rather than a second parallel execution path
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.agent_revisions import (
    agent_revision_fingerprint,
    agent_revisions_root,
    list_revisions,
    verify_revision,
)
from battle_engine.agent_revisions_cli import main as revisions_main
from battle_engine.agent_validation import validate_agent
from battle_engine.evaluation_history import adapt_any

ORIGINAL_ACTION = "AgentAction(ActionKind.NOP)"
EDITED_ACTION = "AgentAction(ActionKind.NOP)"  # behavior unchanged; only a comment differs


def _agent_source(action: str, marker: str) -> str:
    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "class Agent:\n"
        "    def reset(self, context): pass\n"
        f"    def act(self, observation): return {action}\n"
        "def create_agent(): return Agent()\n"
        f"# {marker}\n"
    )


def _write_python_agent(root: Path, name: str, marker: str = "original") -> Path:
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
    (directory / "agent.py").write_text(_agent_source(ORIGINAL_ACTION, marker), encoding="utf-8")
    return directory


def test_evaluate_edit_inspect_restore_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The revisions CLI (unlike EvaluationService/adapt_any, which take an
    # explicit data_root) always resolves the writable root the same way
    # every other bytefray CLI entry point does -- via get_data_root(), so
    # BYTEFRAY_ROOT must point at this test's isolated tmp_path.
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))

    # 1. Evaluate a candidate against an opponent.
    candidate_dir = _write_python_agent(tmp_path, "candidate", marker="original candidate")
    _write_python_agent(tmp_path, "opponent", marker="original opponent")
    original_bytes = (candidate_dir / "agent.py").read_bytes()

    request = EvaluationRequest(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        output_dir=tmp_path / "eval-out",
        ticks=10,
        data_root=tmp_path,
    )
    result = EvaluationService().run(request)

    # 2. The evaluation artifact records durable revision provenance.
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    historical_revision_id = data["agent_revisions"]["candidate"]["agent_revision_id"]
    assert historical_revision_id is not None
    assert data["agent_revisions"]["candidate"]["agent_revision_error"] is None

    # 3. Edit the live candidate agent -- a real, observable source change.
    (candidate_dir / "agent.py").write_text(
        _agent_source(EDITED_ACTION, "edited after evaluation"), encoding="utf-8"
    )
    edited_bytes = (candidate_dir / "agent.py").read_bytes()
    assert edited_bytes != original_bytes
    live_fingerprint_after_edit = agent_revision_fingerprint(candidate_dir)
    assert live_fingerprint_after_edit != historical_revision_id.removeprefix("agent-revision_")

    # 4. History still reports the *historical* revision, unaffected by the edit.
    summary = adapt_any(result.state_path)
    assert summary.candidate_agent_revision_id.value == historical_revision_id

    # 5. The revision's source can be inspected directly from the store.
    store_root = agent_revisions_root(tmp_path)
    assert historical_revision_id in list_revisions(store_root)
    assert verify_revision(store_root, historical_revision_id) is True

    # 6. The revision can be restored to a safe, explicit target -- an
    # unoccupied slot under the live agents/ catalog, chosen explicitly by
    # the caller (never implied/implicit), so ordinary agent tooling can
    # operate on it afterward without a second execution path.
    restore_exit = revisions_main(
        [
            "restore",
            historical_revision_id,
            "--to",
            str(tmp_path / "agents" / "restored-candidate"),
        ]
    )
    assert restore_exit == 0
    restored_dir = tmp_path / "agents" / "restored-candidate"

    # 7. Restored content matches the historical revision id, and is the
    # *original* pre-edit bytes -- not what the live agent looks like now.
    assert agent_revision_fingerprint(restored_dir) == historical_revision_id.removeprefix(
        "agent-revision_"
    )
    assert (restored_dir / "agent.py").read_bytes() == original_bytes
    assert (restored_dir / "agent.py").read_bytes() != edited_bytes

    # 8. Existing agent tooling operates on the restored agent directly --
    # composition, not a second revision-aware execution path.
    # validate_agent() raises AgentValidationFailedError at the first
    # failing stage and only returns a ValidationResult once every stage
    # (discovery/kind/load/reset/act) has succeeded, so simply completing
    # without raising is the success signal.
    validation = validate_agent("restored-candidate", data_root=tmp_path)
    assert validation.agent_id == "restored-candidate"
    assert validation.api_version == 1
