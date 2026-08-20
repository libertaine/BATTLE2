"""Beta1 Phase 2 -- authoritative Ruleset/runtime-kind compatibility boundary.

Covers ``docs/V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md``'s core requirement:
permanent ``bytefray-rules-2`` executes Python entrants only, and any VM
entrant is rejected by ``NativeMatchService.run`` -- the one authoritative
seam every production caller (CLI, tournament, Agent Lab) inherits --
before any entrant executes, before any replay/result artifact is written,
and with a typed, actionable error distinct from the pre-existing
mixed-VM/Python-composition rejection. Ruleset v1 and every historical
alpha identity (``bytefray-rules-2-alpha1``, ``bytefray-rules-2-alpha11``)
must keep their exact pre-Phase-2 VM behavior unchanged -- v1 executes VM
matches normally; the alpha identities keep dispatching successfully but
inertly (no core mechanic) on a VM entrant, exactly as before this phase.
"""

from __future__ import annotations

import json

import pytest
from battle_engine.builtins import build_agent
from battle_engine.config import Config
from battle_engine.core import HALT, enc
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    RulesetRuntimeUnsupportedError,
    UnsupportedMatchCompositionError,
)
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA1_ID,
    BYTEFRAY_RULESET_V2_ALPHA11_ID,
    BYTEFRAY_RULESET_V2_ID,
    RULESET_V2,
)

V1 = BYTEFRAY_RULESET_ID
ALPHA1 = BYTEFRAY_RULESET_V2_ALPHA1_ID
ALPHA11 = BYTEFRAY_RULESET_V2_ALPHA11_ID
V2 = BYTEFRAY_RULESET_V2_ID


def _vm_entrant(slot: str, name: str, start: int) -> MatchEntrant:
    return MatchEntrant(slot, name, start, build_agent("runner", start))


def _halting_vm_entrant(slot: str, name: str, start: int) -> MatchEntrant:
    return MatchEntrant(slot, name, start, enc(HALT))


def _python_entrant(root, agent_id: str, *, slot: str, start: int) -> MatchEntrant:
    from battle_engine.agents import resolve_agent

    agent_dir = root / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    manifest = {
        "kind": "python",
        "api_version": 1,
        "entrypoint": "agent.py:create_agent",
        "version": "1.0",
    }
    (agent_dir / "agent.yaml").write_text(json.dumps(manifest), encoding="utf-8")
    (agent_dir / "agent.py").write_text(
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "class Agent:\n"
        "    def reset(self, context): pass\n"
        "    def act(self, observation): return AgentAction(ActionKind.NOP)\n"
        "def create_agent(): return Agent()\n",
        encoding="utf-8",
    )
    return MatchEntrant.python(slot, agent_id, start, resolve_agent(root, agent_id))


def _request(tmp_path, entrants, *, ruleset_id: str | None, run_name: str = "run") -> MatchRequest:
    return MatchRequest(
        Config(arena_size=128, instr_per_tick=8),
        entrants,
        max_ticks=5,
        replay_path=tmp_path / run_name / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
    )


# ---------------------------------------------------------------------------
# RulesetPolicy.unsupported_runtime_kinds -- pure data-level checks
# ---------------------------------------------------------------------------


def test_v2_policy_declares_python_only() -> None:
    assert RULESET_V2.supported_runtime_kinds == frozenset({"python"})
    assert RULESET_V2.unsupported_runtime_kinds({"python"}) == frozenset()
    assert RULESET_V2.unsupported_runtime_kinds({"vm"}) == frozenset({"vm"})
    assert RULESET_V2.unsupported_runtime_kinds({"vm", "python"}) == frozenset({"vm"})


@pytest.mark.parametrize("ruleset_id", [V1, ALPHA1, ALPHA11])
def test_v1_and_alpha_policies_are_unrestricted(ruleset_id: str) -> None:
    from battle_engine.ruleset_policy import resolve_ruleset_policy

    policy = resolve_ruleset_policy(ruleset_id)
    assert policy.supported_runtime_kinds is None
    assert policy.unsupported_runtime_kinds({"vm"}) == frozenset()
    assert policy.unsupported_runtime_kinds({"python"}) == frozenset()


# ---------------------------------------------------------------------------
# Permanent v2: Python accepted, VM rejected, at any homogeneous N
# ---------------------------------------------------------------------------


def test_v2_accepts_two_python_entrants(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "alpha", slot="A", start=0),
        _python_entrant(tmp_path, "beta", slot="B", start=32),
    )
    result = NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V2))
    assert result.replay_path.is_file()
    assert result.result_path is not None and result.result_path.is_file()


def test_v2_accepts_three_python_entrants(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "alpha", slot="A", start=0),
        _python_entrant(tmp_path, "beta", slot="B", start=32),
        _python_entrant(tmp_path, "gamma", slot="C", start=64),
    )
    result = NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V2))
    assert result.result_path is not None and result.result_path.is_file()
    assert len(result.agents) == 3


def test_v2_rejects_vm_vs_vm(tmp_path) -> None:
    entrants = (_vm_entrant("A", "runner", 0), _vm_entrant("B", "runner", 32))
    with pytest.raises(RulesetRuntimeUnsupportedError) as excinfo:
        NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V2))
    assert excinfo.value.ruleset_id == V2
    assert excinfo.value.unsupported_kinds == ("vm",)


def test_v2_rejects_python_vs_vm_as_mixed_composition_not_ruleset_error(tmp_path) -> None:
    """Mixed VM/Python is rejected by the pre-existing homogeneity check first.

    This is the existing, Ruleset-independent restriction
    (``UnsupportedMatchCompositionError``) -- it fires before Ruleset
    resolution even happens, so its wording never mentions Ruleset v2 and
    is never confused with the permanent-v2 Python-only restriction.
    """

    entrants = (
        _python_entrant(tmp_path, "alpha", slot="A", start=0),
        _vm_entrant("B", "runner", 32),
    )
    with pytest.raises(UnsupportedMatchCompositionError) as excinfo:
        NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V2))
    assert "Mixed VM/Python" in str(excinfo.value)
    assert "bytefray-rules-2" not in str(excinfo.value)


def test_v2_rejects_vm_vs_python_as_mixed_composition_not_ruleset_error(tmp_path) -> None:
    entrants = (
        _vm_entrant("A", "runner", 0),
        _python_entrant(tmp_path, "alpha", slot="B", start=32),
    )
    with pytest.raises(UnsupportedMatchCompositionError):
        NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V2))


def test_v2_rejects_three_way_all_vm(tmp_path) -> None:
    entrants = (
        _vm_entrant("A", "runner", 0),
        _vm_entrant("B", "runner", 32),
        _vm_entrant("C", "runner", 64),
    )
    with pytest.raises(RulesetRuntimeUnsupportedError):
        NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V2))


def test_v2_error_message_is_actionable(tmp_path) -> None:
    entrants = (_vm_entrant("A", "runner", 0), _vm_entrant("B", "runner", 32))
    with pytest.raises(RulesetRuntimeUnsupportedError) as excinfo:
        NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V2))
    message = str(excinfo.value)
    assert "bytefray-rules-2" in message
    assert "Python entrants only" in message
    assert "bytefray-rules-1" in message


# ---------------------------------------------------------------------------
# Mutation safety: zero execution, zero artifacts, before any runtime starts
# ---------------------------------------------------------------------------


def test_v2_vm_rejection_writes_no_replay_or_result(tmp_path) -> None:
    entrants = (_vm_entrant("A", "runner", 0), _vm_entrant("B", "runner", 32))
    request = _request(tmp_path, entrants, ruleset_id=V2, run_name="doomed")
    run_dir = tmp_path / "doomed"

    with pytest.raises(RulesetRuntimeUnsupportedError):
        NativeMatchService().run(request)

    assert not run_dir.exists()
    assert not request.replay_path.exists()
    assert not request.replay_path.with_name("result.json").exists()
    assert not request.replay_path.with_name("summary.json").exists()


def test_v2_vm_rejection_executes_zero_instructions(tmp_path, monkeypatch) -> None:
    """No VM/kernel construction happens at all -- the check fires first."""

    from battle_engine import match_service as match_service_module

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("Kernel must never be constructed for a rejected v2/VM request")

    monkeypatch.setattr(match_service_module, "Kernel", _fail_if_called)

    entrants = (_halting_vm_entrant("A", "runner", 0), _halting_vm_entrant("B", "runner", 32))
    with pytest.raises(RulesetRuntimeUnsupportedError):
        NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V2))


# ---------------------------------------------------------------------------
# Legacy identities: v1 and every historical alpha keep exact prior VM behavior
# ---------------------------------------------------------------------------


def test_v1_vm_matches_still_execute_normally(tmp_path) -> None:
    entrants = (_vm_entrant("A", "runner", 0), _vm_entrant("B", "runner", 32))
    result = NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=None))
    assert result.result_path is not None and result.result_path.is_file()


def test_v1_python_matches_still_execute_normally(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "alpha", slot="A", start=0),
        _python_entrant(tmp_path, "beta", slot="B", start=32),
    )
    result = NativeMatchService().run(_request(tmp_path, entrants, ruleset_id=V1))
    assert result.result_path is not None and result.result_path.is_file()


@pytest.mark.parametrize("ruleset_id", [ALPHA1, ALPHA11])
def test_alpha_identities_still_dispatch_successfully_on_vm(tmp_path, ruleset_id: str) -> None:
    """Historical alpha VM behavior (dispatch succeeds, mechanic inert) is preserved.

    Beta1 Phase 2 deliberately does not extend the new fail-closed
    restriction to the historical alpha identities -- only permanent
    ``bytefray-rules-2`` gets it (docs/V2_0_BETA1_PLAN.md Sec 3).
    """

    entrants = (_vm_entrant("A", "runner", 0), _vm_entrant("B", "runner", 32))
    result = NativeMatchService().run(
        _request(tmp_path, entrants, ruleset_id=ruleset_id, run_name=f"alpha-{ruleset_id}")
    )
    assert result.result_path is not None and result.result_path.is_file()
    data = json.loads(result.result_path.read_text(encoding="utf-8"))
    assert data["ruleset_id"] == ruleset_id
