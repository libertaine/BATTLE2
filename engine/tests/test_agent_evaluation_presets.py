"""v1.6 Phase 3 -- evaluation preset resolution, canonical identity,
orientation, parallel composition, resume authority, and history
compatibility (docs/V1_6_PHASE3_EVALUATION_PRESETS.md).

Schema/parsing/path-safety/list-show-validate CLI coverage lives in
``test_evaluation_presets.py``; this file exercises the preset all the way
through ``agent_evaluation.main`` (the one authoritative resolution path)
and the resulting canonical ``evaluation.json`` artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from battle_engine.agent_evaluation import _parser
from battle_engine.agent_evaluation import main as evaluate_main
from battle_engine.evaluation_presets import SCHEMA_NAME as PRESET_SCHEMA_NAME
from battle_engine.evaluation_presets import SCHEMA_VERSION as PRESET_SCHEMA_VERSION
from battle_engine.evaluation_presets import presets_root

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_agent(root: Path, name: str, action: str = NOP_ACTION) -> Path:
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


def _write_preset(root: Path, name: str, body: dict | None = None) -> Path:
    directory = presets_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.yaml"
    payload = {"schema": PRESET_SCHEMA_NAME, "schema_version": PRESET_SCHEMA_VERSION}
    if body:
        payload.update(body)
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _load(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


_VOLATILE_TOP_LEVEL = {"updated_at", "project", "created_at", "finished_at"}
_VOLATILE_EXECUTION_CONTEXT = {"first_used_at"}


def _normalize(data: dict) -> dict:
    normalized = {k: v for k, v in data.items() if k not in _VOLATILE_TOP_LEVEL}
    normalized["execution_contexts"] = [
        {k: v for k, v in ctx.items() if k not in _VOLATILE_EXECUTION_CONTEXT}
        for ctx in data.get("execution_contexts", ())
    ]
    return normalized


@pytest.fixture()
def three_agents(tmp_path: Path) -> Path:
    _write_agent(tmp_path, "candidate")
    _write_agent(tmp_path, "baseline")
    _write_agent(tmp_path, "opp_a")
    _write_agent(tmp_path, "opp_b")
    return tmp_path


# ---------------------------------------------------------------------------
# Resolution layering (Sec 6)
# ---------------------------------------------------------------------------


def test_defaults_plus_preset_values_are_used(three_agents, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(
        three_agents,
        "standard",
        {"opponents": ["opp_a", "opp_b"], "seeds": [1, 2], "ticks": 15},
    )
    out_dir = three_agents / "eval-out"
    exit_code = evaluate_main(
        ["candidate", "--preset", "standard", "--single-orientation", "--output", str(out_dir), "--quiet"]
    )
    assert exit_code == 0
    data = _load(out_dir / "evaluation.json")
    assert data["opponent_ids"] == ["opp_a", "opp_b"]
    assert data["seeds"] == [1, 2]
    assert data["ticks"] == 15
    assert data["baseline_id"] is None


def test_preset_only_values_no_explicit_flags_beyond_preset(three_agents, monkeypatch):
    """A preset may supply every field, including candidate -- a bare
    '--preset <name>' invocation with no positional candidate at all."""

    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(
        three_agents,
        "full",
        {
            "candidate": "candidate",
            "baseline": "baseline",
            "opponents": ["opp_a"],
            "seeds": [7],
            "ticks": 12,
            "orientation": "candidate_first_only",
        },
    )
    out_dir = three_agents / "eval-out"
    exit_code = evaluate_main(["--preset", "full", "--output", str(out_dir), "--quiet"])
    assert exit_code == 0
    data = _load(out_dir / "evaluation.json")
    assert data["candidate_id"] == "candidate"
    assert data["baseline_id"] == "baseline"
    assert data["opponent_ids"] == ["opp_a"]
    assert data["seeds"] == [7]
    assert data["ticks"] == 12


def test_explicit_cli_ticks_overrides_preset_ticks(three_agents, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(three_agents, "standard", {"opponents": ["opp_a"], "seeds": [1], "ticks": 200})
    out_dir = three_agents / "eval-out"
    exit_code = evaluate_main(
        ["candidate", "--preset", "standard", "--ticks", "9", "--output", str(out_dir), "--quiet"]
    )
    assert exit_code == 0
    data = _load(out_dir / "evaluation.json")
    assert data["ticks"] == 9


def test_explicit_cli_opponents_overrides_preset_opponents(three_agents, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(three_agents, "standard", {"opponents": ["opp_a"], "seeds": [1]})
    out_dir = three_agents / "eval-out"
    exit_code = evaluate_main(
        [
            "candidate", "--preset", "standard", "--opponents", "opp_b",
            "--output", str(out_dir), "--quiet",
        ]
    )
    assert exit_code == 0
    data = _load(out_dir / "evaluation.json")
    assert data["opponent_ids"] == ["opp_b"]


def test_empty_preset_opponents_falls_through_to_reused_validation(three_agents, monkeypatch, capsys):
    """An empty 'opponents: []' in the preset is type-valid at load time
    (test_evaluation_presets.py) but, once resolved, is rejected by the
    exact same EvaluationConfigurationError the ordinary --opponents-less
    invocation would hit -- no separate validation path (Sec 6)."""

    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(three_agents, "empty", {"opponents": [], "seeds": [1]})
    exit_code = evaluate_main(["candidate", "--preset", "empty"])
    assert exit_code == 2
    assert "at least one opponent" in capsys.readouterr().err


def test_empty_preset_opponents_explicit_cli_override_succeeds(three_agents, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(three_agents, "empty", {"opponents": [], "seeds": [1]})
    out_dir = three_agents / "eval-out"
    exit_code = evaluate_main(
        ["candidate", "--preset", "empty", "--opponents", "opp_a", "--output", str(out_dir), "--quiet"]
    )
    assert exit_code == 0


# ---------------------------------------------------------------------------
# Candidate-field decision (Sec 4: optional in preset, CLI positional wins)
# ---------------------------------------------------------------------------


def test_candidate_positional_overrides_preset_candidate(three_agents, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(three_agents, "fixed", {"candidate": "baseline", "opponents": ["opp_a"], "seeds": [1]})
    out_dir = three_agents / "eval-out"
    # Positional "candidate" must win over the preset's "candidate: baseline".
    exit_code = evaluate_main(["candidate", "--preset", "fixed", "--output", str(out_dir), "--quiet"])
    assert exit_code == 0
    data = _load(out_dir / "evaluation.json")
    assert data["candidate_id"] == "candidate"


def test_candidate_from_preset_when_cli_omits_it(three_agents, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(three_agents, "fixed", {"candidate": "candidate", "opponents": ["opp_a"], "seeds": [1]})
    out_dir = three_agents / "eval-out"
    exit_code = evaluate_main(["--preset", "fixed", "--output", str(out_dir), "--quiet"])
    assert exit_code == 0
    data = _load(out_dir / "evaluation.json")
    assert data["candidate_id"] == "candidate"


def test_candidate_missing_from_both_is_a_controlled_error(three_agents, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(three_agents, "no_candidate", {"opponents": ["opp_a"], "seeds": [1]})
    exit_code = evaluate_main(["--preset", "no_candidate"])
    assert exit_code == 2
    assert "candidate is required" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Canonical identity (Sec 7)
# ---------------------------------------------------------------------------


def test_canonical_identity_explicit_args_vs_preset_match(three_agents, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    explicit_out = three_agents / "explicit"
    exit_code = evaluate_main(
        [
            "candidate", "--opponents", "opp_a,opp_b", "--seeds", "1,2", "--ticks", "10",
            "--single-orientation", "--output", str(explicit_out), "--quiet",
        ]
    )
    assert exit_code == 0

    _write_preset(
        three_agents,
        "matched",
        {"opponents": ["opp_a", "opp_b"], "seeds": [1, 2], "ticks": 10, "orientation": "candidate_first_only"},
    )
    preset_out = three_agents / "via_preset"
    exit_code = evaluate_main(
        ["candidate", "--preset", "matched", "--output", str(preset_out), "--quiet"]
    )
    assert exit_code == 0

    explicit_data = _normalize(_load(explicit_out / "evaluation.json"))
    preset_data = _normalize(_load(preset_out / "evaluation.json"))
    assert explicit_data["evaluation_id"] == preset_data["evaluation_id"]
    assert explicit_data == preset_data


def test_canonical_identity_differently_named_identical_presets_match(three_agents, monkeypatch):
    body = {"opponents": ["opp_a"], "seeds": [3], "ticks": 8, "orientation": "candidate_first_only"}
    _write_preset(three_agents, "preset_alpha", body)
    _write_preset(three_agents, "preset_beta", body)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))

    out_a = three_agents / "out_a"
    out_b = three_agents / "out_b"
    assert evaluate_main(["candidate", "--preset", "preset_alpha", "--output", str(out_a), "--quiet"]) == 0
    assert evaluate_main(["candidate", "--preset", "preset_beta", "--output", str(out_b), "--quiet"]) == 0

    data_a = _normalize(_load(out_a / "evaluation.json"))
    data_b = _normalize(_load(out_b / "evaluation.json"))
    assert data_a["evaluation_id"] == data_b["evaluation_id"]
    assert data_a == data_b


def test_preset_name_never_appears_in_evaluation_id_payload(three_agents, monkeypatch):
    """Two presets with different *names* but identical content must not
    just coincidentally match -- prove the id is stable across a rename of
    the same file, too (a stronger form of the identical-content case)."""

    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    body = {"opponents": ["opp_a"], "seeds": [1], "orientation": "candidate_first_only"}
    _write_preset(three_agents, "before_rename", body)
    out1 = three_agents / "out1"
    evaluate_main(["candidate", "--preset", "before_rename", "--output", str(out1), "--quiet"])
    id_before = _load(out1 / "evaluation.json")["evaluation_id"]

    (presets_root(three_agents) / "before_rename.yaml").rename(presets_root(three_agents) / "after_rename.yaml")
    out2 = three_agents / "out2"
    evaluate_main(["candidate", "--preset", "after_rename", "--output", str(out2), "--quiet"])
    id_after = _load(out2 / "evaluation.json")["evaluation_id"]

    assert id_before == id_after


# ---------------------------------------------------------------------------
# Orientation semantics (Sec 8)
# ---------------------------------------------------------------------------


def test_orientation_omitted_from_preset_defaults_to_both(three_agents, monkeypatch, capsys):
    """Preset pins --ruleset bytefray-rules-1 (no placement multiplication)
    so the expected match count stays a simple orientation-only count --
    this test is about orientation defaulting, not the RC1 default-Ruleset-
    defect fix's Python-only omitted-Ruleset -> v2 policy."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(
        three_agents,
        "no_orientation",
        {"opponents": ["opp_a"], "seeds": [1], "ruleset": "bytefray-rules-1"},
    )
    exit_code = evaluate_main(["candidate", "--preset", "no_orientation", "--dry-run"])
    assert exit_code == 0
    assert "matches: 2" in capsys.readouterr().out  # 1 subject x 1 opp x 1 seed x 2 orientations


def test_orientation_preset_explicit_both(three_agents, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(
        three_agents,
        "both",
        {"opponents": ["opp_a"], "seeds": [1], "orientation": "both", "ruleset": "bytefray-rules-1"},
    )
    exit_code = evaluate_main(["candidate", "--preset", "both", "--dry-run"])
    assert exit_code == 0
    assert "matches: 2" in capsys.readouterr().out


def test_orientation_preset_explicit_single(three_agents, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(
        three_agents,
        "single",
        {
            "opponents": ["opp_a"], "seeds": [1], "orientation": "candidate_first_only",
            "ruleset": "bytefray-rules-1",
        },
    )
    exit_code = evaluate_main(["candidate", "--preset", "single", "--dry-run"])
    assert exit_code == 0
    assert "matches: 1" in capsys.readouterr().out


def test_cli_override_preset_both_to_single(three_agents, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(
        three_agents,
        "both",
        {"opponents": ["opp_a"], "seeds": [1], "orientation": "both", "ruleset": "bytefray-rules-1"},
    )
    exit_code = evaluate_main(
        ["candidate", "--preset", "both", "--single-orientation", "--dry-run"]
    )
    assert exit_code == 0
    assert "matches: 1" in capsys.readouterr().out


def test_cli_override_preset_single_to_both(three_agents, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_preset(
        three_agents,
        "single",
        {
            "opponents": ["opp_a"], "seeds": [1], "orientation": "candidate_first_only",
            "ruleset": "bytefray-rules-1",
        },
    )
    exit_code = evaluate_main(
        ["candidate", "--preset", "single", "--both-orientations", "--dry-run"]
    )
    assert exit_code == 0
    assert "matches: 2" in capsys.readouterr().out


def test_orientation_flags_mutually_exclusive_at_parser_level():
    with pytest.raises(SystemExit):
        _parser().parse_args(
            ["candidate", "--opponents", "opp", "--single-orientation", "--both-orientations"]
        )


# ---------------------------------------------------------------------------
# Parallel composition (Sec 9)
# ---------------------------------------------------------------------------


def test_preset_workers_1_2_4_produce_identical_evaluation(three_agents, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    _write_agent(three_agents, "opp_c")
    _write_preset(
        three_agents,
        "matrix",
        {
            "opponents": ["opp_a", "opp_b", "opp_c"],
            "seeds": [1, 2],
            "ticks": 8,
            "orientation": "candidate_first_only",
        },
    )
    results = {}
    for workers in (1, 2, 4):
        out_dir = three_agents / f"out_{workers}"
        exit_code = evaluate_main(
            ["candidate", "--preset", "matrix", "--workers", str(workers), "--output", str(out_dir), "--quiet"]
        )
        assert exit_code == 0
        results[workers] = _normalize(_load(out_dir / "evaluation.json"))

    assert results[1]["evaluation_id"] == results[2]["evaluation_id"] == results[4]["evaluation_id"]
    for cells_key in ("cells",):
        assert results[1][cells_key] == results[2][cells_key] == results[4][cells_key]
    assert results[1] == results[2] == results[4]


# ---------------------------------------------------------------------------
# Resume authority (Sec 13)
# ---------------------------------------------------------------------------


def test_resume_authority_modified_preset_is_rejected_not_reinterpreted(three_agents, monkeypatch, capsys):
    """Pinned to explicit --ruleset bytefray-rules-1 throughout (preset and
    the final explicit-flags resume alike, so evaluation_id stays
    consistent across every step): this test is about resume authority
    (preset vs. explicit flags), not about which Ruleset is the product
    default, and the fixed 18-cell arithmetic depends on v1's no-placement-
    multiplication methodology."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    for name in ("opp_c", "opp_d", "opp_e", "opp_f"):
        _write_agent(three_agents, name)
    opponents = ["opp_a", "opp_b", "opp_c", "opp_d", "opp_e", "opp_f"]
    _write_preset(
        three_agents,
        "growing",
        {
            "opponents": opponents, "seeds": [1, 2, 3], "ticks": 5,
            "orientation": "candidate_first_only", "ruleset": "bytefray-rules-1",
        },
    )
    out_dir = three_agents / "eval-out"

    import battle_engine.agent_evaluation as mod

    real_write_state = mod.EvaluationService._write_state
    call_count = {"n": 0}

    def _crash_after_second_checkpoint(self, *args, **kwargs):
        real_write_state(self, *args, **kwargs)
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated interruption")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod.EvaluationService, "_write_state", _crash_after_second_checkpoint)
        with pytest.raises(RuntimeError):
            evaluate_main(
                ["candidate", "--preset", "growing", "--output", str(out_dir), "--quiet"]
            )

    interrupted = _load(out_dir / "evaluation.json")
    assert interrupted["lifecycle_state"] == "running"
    interrupted_cell_count = len(interrupted["cells"])
    assert 0 < interrupted_cell_count < 18  # genuine partial progress, not zero and not complete
    original_evaluation_id = interrupted["evaluation_id"]

    # Modify the preset: drop one opponent -- a materially different
    # experiment, and (per Sec 7) a different evaluation_id.
    _write_preset(
        three_agents,
        "growing",
        {
            "opponents": opponents[:-1], "seeds": [1, 2, 3], "ticks": 5,
            "orientation": "candidate_first_only", "ruleset": "bytefray-rules-1",
        },
    )

    exit_code = evaluate_main(
        ["candidate", "--preset", "growing", "--output", str(out_dir), "--quiet"]
    )
    assert exit_code == 2
    assert "does not match this request" in capsys.readouterr().err

    # The frozen, already-durable state at out_dir must be completely
    # untouched by the rejected resume attempt.
    still_interrupted = _load(out_dir / "evaluation.json")
    assert still_interrupted == interrupted
    assert still_interrupted["evaluation_id"] == original_evaluation_id

    # Deleting the preset entirely must fail the same way -- cleanly, before
    # ever touching the frozen evaluation state -- not silently drop it.
    (presets_root(three_agents) / "growing.yaml").unlink()
    exit_code = evaluate_main(
        ["candidate", "--preset", "growing", "--output", str(out_dir), "--quiet"]
    )
    assert exit_code == 2
    assert "Unknown evaluation preset" in capsys.readouterr().err
    assert _load(out_dir / "evaluation.json") == interrupted

    # Resuming via the *original* explicit flags (bypassing the now-deleted
    # preset entirely) must still succeed and continue from the frozen
    # state -- the preset was only ever a convenience for constructing this
    # exact request, never the authority over what happens next.
    exit_code = evaluate_main(
        [
            "candidate", "--opponents", ",".join(opponents), "--seeds", "1,2,3", "--ticks", "5",
            "--single-orientation", "--output", str(out_dir), "--quiet",
            "--ruleset", "bytefray-rules-1",
        ]
    )
    assert exit_code == 0
    resumed = _load(out_dir / "evaluation.json")
    assert resumed["evaluation_id"] == original_evaluation_id
    assert resumed["lifecycle_state"] == "finished"
    assert len(resumed["cells"]) == 18
    assert all(c["status"] == "completed" for c in resumed["cells"])
    # Every cell present before the interruption is preserved unchanged.
    resumed_by_schedule = {c["schedule_id"]: c for c in resumed["cells"]}
    for cell in interrupted["cells"]:
        assert resumed_by_schedule[cell["schedule_id"]]["outcome"] == cell["outcome"]


# ---------------------------------------------------------------------------
# History compatibility (Sec 16)
# ---------------------------------------------------------------------------


def test_preset_originated_evaluation_readable_by_evaluation_history(three_agents, monkeypatch):
    from battle_engine.evaluation_history import discovery

    monkeypatch.setenv("BYTEFRAY_ROOT", str(three_agents))
    # Pinned to explicit v1 (no placement multiplication): this test is
    # about evaluation_history discovery/adaptation, not Ruleset defaulting.
    _write_preset(
        three_agents,
        "standard",
        {"opponents": ["opp_a"], "seeds": [1], "ticks": 5, "ruleset": "bytefray-rules-1"},
    )
    out_dir = three_agents / "runs" / "evaluations" / "via-preset"
    exit_code = evaluate_main(
        ["candidate", "--preset", "standard", "--single-orientation", "--output", str(out_dir), "--quiet"]
    )
    assert exit_code == 0

    summary = discovery.adapt_any(out_dir / "evaluation.json")
    assert summary.schema.supported
    assert summary.candidate_id == "candidate"
    assert len(summary.cells) == 1
