"""v3 Phase 4: `agent_test.py` gains `alive_weight`/`territory_weight`,
generalizing Phase 3's `kill_weight`-only contract to the other two
`Weights` fields Phase 4's defense-payoff experiment independently varies
(with `kill_weight` held at Phase 3's own accepted offense payoff).

Mirrors `test_v3_phase3_offense_payoff_evaluation.py`'s governing
invariant: omission (of any subset of the three) must reproduce
``Config()``'s own default ``Weights`` unchanged, byte for byte.
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agent_scaffold import create_agent as scaffold_create_agent
from battle_engine.agent_test import GroupEntrantSpec, _resolved_weights
from battle_engine.agent_test import test_agent as run_development_test
from battle_engine.agent_test import test_agents as run_group_development_test
from battle_engine.config import Config

ROOT = Path(__file__).resolve().parents[2]
NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_python_agent(root: Path, name: str, action: str = NOP_ACTION) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
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


# ---------------------------------------------------------------------------
# `_resolved_weights` unit tests (hermetic, no execution)
# ---------------------------------------------------------------------------


def test_resolved_weights_all_omitted_returns_defaults_unchanged():
    defaults = Config()
    result = _resolved_weights(defaults, kill_weight=None, alive_weight=None, territory_weight=None)
    assert result == defaults.weights
    assert result is defaults.weights  # no copy when nothing is overridden


def test_resolved_weights_kill_only():
    defaults = Config()
    result = _resolved_weights(defaults, kill_weight=1600.0, alive_weight=None, territory_weight=None)
    assert result.kill == 1600.0
    assert result.alive == defaults.weights.alive
    assert result.territory == defaults.weights.territory
    assert result.territory_bucket == defaults.weights.territory_bucket


def test_resolved_weights_territory_only():
    defaults = Config()
    result = _resolved_weights(defaults, kill_weight=None, alive_weight=None, territory_weight=20.0)
    assert result.territory == 20.0
    assert result.kill == defaults.weights.kill
    assert result.alive == defaults.weights.alive


def test_resolved_weights_alive_only():
    defaults = Config()
    result = _resolved_weights(defaults, kill_weight=None, alive_weight=50.0, territory_weight=None)
    assert result.alive == 50.0
    assert result.kill == defaults.weights.kill
    assert result.territory == defaults.weights.territory


def test_resolved_weights_combined_kill_and_territory():
    """Phase 4's own governing shape: offense payoff held fixed, territory varied."""

    defaults = Config()
    result = _resolved_weights(defaults, kill_weight=1600.0, alive_weight=None, territory_weight=5.0)
    assert result.kill == 1600.0
    assert result.territory == 5.0
    assert result.alive == defaults.weights.alive


def test_resolved_weights_explicit_default_equals_omission():
    defaults = Config()
    omitted = _resolved_weights(defaults, kill_weight=None, alive_weight=None, territory_weight=None)
    explicit = _resolved_weights(
        defaults,
        kill_weight=defaults.weights.kill,
        alive_weight=defaults.weights.alive,
        territory_weight=defaults.weights.territory,
    )
    assert omitted == explicit


# ---------------------------------------------------------------------------
# End-to-end: pairwise (`test_agent`)
# ---------------------------------------------------------------------------


def test_territory_weight_omitted_matches_explicit_default(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    omitted = run_development_test("example", data_root=tmp_path, resource_root=ROOT, seed=1, ticks=20)
    explicit = run_development_test(
        "example",
        data_root=tmp_path,
        resource_root=ROOT,
        seed=1,
        ticks=20,
        territory_weight=Config().weights.territory,
    )
    assert omitted.match_result.match_id == explicit.match_result.match_id
    assert omitted.match_result.score == explicit.match_result.score


def test_non_default_territory_weight_changes_identity_and_score(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    default_run = run_development_test("example", data_root=tmp_path, resource_root=ROOT, seed=1, ticks=20)
    varied = run_development_test(
        "example", data_root=tmp_path, resource_root=ROOT, seed=1, ticks=20, territory_weight=20.0
    )
    assert default_run.match_result.match_id != varied.match_result.match_id
    assert default_run.match_result.score != varied.match_result.score


def test_kill_weight_and_territory_weight_combine_independently(tmp_path):
    """Phase 4's governing shape end-to-end: fixing kill_weight at Phase 3's
    payoff while varying territory_weight must reach the executed match's
    Config with both overrides applied simultaneously."""

    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    combined = run_development_test(
        "example",
        data_root=tmp_path,
        resource_root=ROOT,
        seed=1,
        ticks=20,
        run_dir=tmp_path / "combined",
        kill_weight=1600.0,
        territory_weight=5.0,
    )
    payload = json.loads((tmp_path / "combined" / "result.json").read_text(encoding="utf-8"))
    reproducibility = payload.get("reproducibility") or payload["result"]["reproducibility"]
    assert reproducibility["weights"]["kill"] == 1600.0
    assert reproducibility["weights"]["territory"] == 5.0
    assert reproducibility["weights"]["alive"] == Config().weights.alive
    assert combined.match_result.result_id


def test_alive_weight_omitted_matches_explicit_default(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    omitted = run_development_test("example", data_root=tmp_path, resource_root=ROOT, seed=1, ticks=20)
    explicit = run_development_test(
        "example",
        data_root=tmp_path,
        resource_root=ROOT,
        seed=1,
        ticks=20,
        alive_weight=Config().weights.alive,
    )
    assert omitted.match_result.match_id == explicit.match_result.match_id


# ---------------------------------------------------------------------------
# End-to-end: group (`test_agents`)
# ---------------------------------------------------------------------------


def test_group_territory_weight_reaches_executed_match(tmp_path):
    _write_python_agent(tmp_path, "a")
    _write_python_agent(tmp_path, "b")
    _write_python_agent(tmp_path, "c")
    entrants = [
        GroupEntrantSpec(seat="A", agent_id="a", start=0),
        GroupEntrantSpec(seat="B", agent_id="b", start=1365),
        GroupEntrantSpec(seat="C", agent_id="c", start=2730),
    ]
    run_dir = tmp_path / "group-run"
    run_group_development_test(
        entrants,
        seed=1,
        ticks=20,
        trace=False,
        run_dir=run_dir,
        data_root=tmp_path,
        ruleset_id="bytefray-rules-2",
        kill_weight=1600.0,
        territory_weight=5.0,
    )
    payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    reproducibility = payload.get("reproducibility") or payload["result"]["reproducibility"]
    assert reproducibility["weights"]["kill"] == 1600.0
    assert reproducibility["weights"]["territory"] == 5.0
