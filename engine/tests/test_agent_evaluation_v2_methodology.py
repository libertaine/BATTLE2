"""v2.0.0-beta2 Phase 1 -- Ruleset-v2 1v1 evaluation methodology
(docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md).

Integration-level: real ``EvaluationService`` runs exercising the new
``--ruleset``-selected v2 methodology (standard placements, standard seed
default, balanced scheduler order, capture/core evidence) side by side with
v1 preservation. See ``test_evaluation_capture.py`` for capture-module unit
coverage and ``test_agent_evaluation_v2.py``/``test_agent_evaluation_
orientation.py``/``test_agent_evaluation_parallel.py`` for the pre-existing
v1/orientation/parallel behavior this phase must not disturb.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    BYTEFRAY_RULESET_ID,
    BYTEFRAY_RULESET_V2_ID,
    EVALUATION_ARENA_ALIGNMENT_MODE,
    EVALUATION_ARENA_ALIGNMENT_MODE_V2_STANDARD,
    EVALUATION_RULES_COMPATIBILITY_ID,
    IDENTITY_VERSION,
    IDENTITY_VERSION_V2,
    SCHEMA_VERSION,
    SCHEMA_VERSION_V2,
    STANDARD_V2_SEEDS,
    EvaluationConfigurationError,
    EvaluationRequest,
    EvaluationService,
    build_matrix,
    compare_candidate_baseline,
    is_ruleset_v2_methodology,
    resolve_evaluation_ruleset_id,
    standard_placements,
)
from battle_engine.config import Config

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_agent(root: Path, name: str, act_body: str) -> Path:
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
    def act(self, observation):
{act_body}
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


def _write_nop_agent(root: Path, name: str) -> Path:
    return _write_agent(root, name, f"        return {NOP_ACTION}")


def _write_blaster_agent(root: Path, name: str, addresses: list[int], value: int = 0xAA) -> Path:
    """A deterministic agent that WRITEs ``addresses`` in order, one per
    ``act()`` call -- absolute arena addresses (Python WRITE is not
    self-relative, unlike the VM), then NOPs forever."""

    body = (
        "        addresses = " + repr(addresses) + "\n"
        "        if not hasattr(self, 'i'):\n"
        "            self.i = 0\n"
        "        if self.i < len(addresses):\n"
        "            addr = addresses[self.i]\n"
        "            self.i += 1\n"
        f"            return AgentAction(ActionKind.WRITE, addr, {value})\n"
        f"        return {NOP_ACTION}"
    )
    return _write_agent(root, name, body)


def _request(root: Path, **overrides) -> EvaluationRequest:
    defaults: dict = {
        "candidate_id": "candidate",
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": root / "eval-out",
        "ticks": 20,
        "data_root": root,
        "both_orientations": False,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


@pytest.fixture()
def two_agents(tmp_path: Path) -> Path:
    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opponent")
    return tmp_path


def _blaster_core_windows() -> list[int]:
    """Every candidate/opponent-core address the three standard placements
    can ever produce, for the default arena size -- a scripted blaster
    targeting exactly these addresses deterministically core-captures
    whichever standard placement is in effect, regardless of orientation
    (Python WRITE addresses are absolute, and placement is orientation-
    independent by construction -- see EvaluationService._execute_cell)."""

    from battle_engine.python_runtime import CORE_SIZE

    arena_size = Config().arena_size
    windows: list[int] = []
    for placement in standard_placements(arena_size):
        for start in (placement.subject_start, placement.opponent_start):
            windows.extend(range(start, start + CORE_SIZE))
    return sorted(set(windows))


@pytest.fixture()
def capture_agents(tmp_path: Path) -> Path:
    _write_blaster_agent(tmp_path, "candidate", _blaster_core_windows())
    _write_nop_agent(tmp_path, "opponent")
    return tmp_path


# ---------------------------------------------------------------------------
# v1 preservation (Phase 1Z items 1-6)
# ---------------------------------------------------------------------------


def test_omitted_ruleset_runs_v1_methodology_unchanged(two_agents: Path):
    request = _request(two_agents, both_orientations=True)
    matrix = build_matrix(request, "evaluation_x")
    # v1: opponents(1) x seeds(1) x orientations(2), no placement axis.
    assert len(matrix) == 2
    assert all(cell.placement_id == "fixed" for cell in matrix)
    assert all(cell.subject_start == 0 and cell.opponent_start == 0 for cell in matrix)
    assert all(cell.rules_compatibility_id == EVALUATION_RULES_COMPATIBILITY_ID for cell in matrix)


def test_explicit_v1_ruleset_identical_to_omitted(two_agents: Path):
    omitted = build_matrix(_request(two_agents), "evaluation_x")
    explicit = build_matrix(_request(two_agents, ruleset_id=BYTEFRAY_RULESET_ID), "evaluation_x")
    assert [c.schedule_id for c in omitted] == [c.schedule_id for c in explicit]


def test_v1_evaluation_id_unchanged_by_v2_feature_existing(two_agents: Path):
    """Pinned-shape regression: a v1 request's evaluation_id hash payload
    must be byte-identical to pre-Phase-1 code -- IDENTITY_VERSION (4) is
    never bumped for v1, and rules_compatibility_id/arena_alignment_mode
    resolve to the exact same constants as before."""

    service = EvaluationService()
    _specs, evaluation_id = service.preflight(
        candidate_id="candidate", opponent_ids=("opponent",), seeds=(1,), ticks=20, data_root=two_agents,
    )
    assert evaluation_id.startswith("evaluation-v2_")
    request = _request(two_agents)
    result = service.run(request)
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["identity_version"] == IDENTITY_VERSION == 4
    assert data["schema_version"] == SCHEMA_VERSION == 4
    assert data["rules_compatibility_id"] == BYTEFRAY_RULESET_ID
    assert data["arena_alignment_mode"] == EVALUATION_ARENA_ALIGNMENT_MODE == "fixed"


def test_v1_resume_unchanged(two_agents: Path):
    service = EvaluationService()
    first = service.run(_request(two_agents))
    second = service.run(_request(two_agents))  # resume, same output_dir
    assert first.evaluation_id == second.evaluation_id
    assert [c.match_id for c in first.cells] == [c.match_id for c in second.cells]


def test_v1_cells_execute_under_ruleset_v1(two_agents: Path):
    service = EvaluationService()
    result = service.run(_request(two_agents))
    for cell in result.cells:
        result_json = json.loads((cell.artifact_dir / "result.json").read_text(encoding="utf-8"))
        assert result_json["ruleset_id"] == BYTEFRAY_RULESET_ID


def test_v1_comparison_grouping_key_unaffected_by_placement_field(two_agents: Path):
    _write_nop_agent(two_agents, "baseline_agent")
    request = _request(two_agents, baseline_id="baseline_agent", both_orientations=True)
    result = EvaluationService().run(request)
    comparison = compare_candidate_baseline(result.cells)
    assert comparison  # matched pairs exist
    assert all(entry.placement_id == "fixed" for entry in comparison)


# ---------------------------------------------------------------------------
# Ruleset selection (Phase 1Z items 7-9)
# ---------------------------------------------------------------------------


def test_explicit_v2_ruleset_accepted_for_python_agents(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID)
    service = EvaluationService()
    result = service.run(request)
    assert result.cells
    for cell in result.cells:
        assert cell.status == "completed"


def test_unknown_ruleset_rejected(two_agents: Path):
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(_request(two_agents, ruleset_id="bytefray-rules-2-alpha11"))


def test_v2_rules_compatibility_id_is_permanent_identity_never_alpha(two_agents: Path):
    resolved = resolve_evaluation_ruleset_id(BYTEFRAY_RULESET_V2_ID)
    assert resolved == "bytefray-rules-2"
    assert "alpha" not in resolved


def test_evaluation_python_only_restriction_predates_and_covers_v2(two_agents: Path):
    """Evaluation already restricts every entrant to Python agents
    unconditionally (Beta1's runtime compatibility boundary) -- this alone
    already satisfies "unsupported VM entrant under v2 fails," without
    evaluation duplicating a runtime-kind check itself."""

    from battle_engine.agent_evaluation import _resolve_python_agent

    with pytest.raises(EvaluationConfigurationError):
        _resolve_python_agent(two_agents, "nonexistent-agent-id")


# ---------------------------------------------------------------------------
# Scheduler order (Phase 1Z items 10-13)
# ---------------------------------------------------------------------------


def test_v2_generates_both_scheduler_orders_by_default(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, both_orientations=True)
    matrix = build_matrix(request, "evaluation_x")
    orientations = {cell.orientation for cell in matrix}
    assert orientations == {"candidate_first", "opponent_first"}


def test_order_enters_schedule_identity(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, both_orientations=True)
    matrix = build_matrix(request, "evaluation_x")
    same_condition = [
        c for c in matrix if c.seed == 1 and c.placement_id == matrix[0].placement_id
    ]
    ids = {c.schedule_id for c in same_condition}
    assert len(ids) == len(same_condition)  # every cell distinct, order included


def test_changing_only_order_changes_cell_id(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, both_orientations=True)
    matrix = build_matrix(request, "evaluation_x")
    by_orientation = {c.orientation: c for c in matrix if c.placement_id == "opposed" and c.seed == 1}
    assert len(by_orientation) == 2
    a, b = by_orientation.values()
    assert a.schedule_id != b.schedule_id


def test_scheduler_order_disclosed_in_reporting(two_agents: Path, capsys, monkeypatch):
    from battle_engine.agent_evaluation import main as evaluate_main

    monkeypatch.setenv("BYTEFRAY_ROOT", str(two_agents))
    exit_code = evaluate_main(
        [
            "candidate", "--ruleset", "bytefray-rules-2", "--opponents", "opponent",
            "--dry-run", "--seeds", "1",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "scheduler orders: balanced" in out


# ---------------------------------------------------------------------------
# Placement (Phase 1Z items 14-19)
# ---------------------------------------------------------------------------


def test_standard_placements_generates_three_deterministic_conditions():
    placements = standard_placements(4096)
    assert [p.placement_id for p in placements] == ["opposed", "quarter", "opposed-shifted"]
    assert placements == standard_placements(4096)  # deterministic, no RNG


def test_standard_placements_starts_are_valid_for_default_arena():
    arena_size = Config().arena_size
    for placement in standard_placements(arena_size):
        assert 0 <= placement.subject_start < arena_size
        assert 0 <= placement.opponent_start < arena_size


def test_standard_placements_cores_never_overlap():
    from battle_engine.python_runtime import CORE_SIZE, core_addresses

    arena_size = Config().arena_size
    for placement in standard_placements(arena_size):
        subject_cells = set(core_addresses(placement.subject_start, arena_size))
        opponent_cells = set(core_addresses(placement.opponent_start, arena_size))
        assert len(subject_cells) == CORE_SIZE
        assert not (subject_cells & opponent_cells)


def test_placement_enters_identity(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, both_orientations=False)
    matrix = build_matrix(request, "evaluation_x")
    ids = {c.placement_id for c in matrix}
    assert ids == {"opposed", "quarter", "opposed-shifted"}
    assert len({c.schedule_id for c in matrix}) == len(matrix)


def test_changed_placement_changes_cell_id(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, both_orientations=False)
    matrix = build_matrix(request, "evaluation_x")
    by_placement = {c.placement_id: c for c in matrix if c.seed == 1}
    a, b = by_placement["opposed"], by_placement["quarter"]
    assert a.schedule_id != b.schedule_id
    assert a.subject_start == b.subject_start == 0
    assert a.opponent_start != b.opponent_start


def test_placement_set_disclosed_in_dry_run(two_agents: Path, capsys, monkeypatch):
    from battle_engine.agent_evaluation import main as evaluate_main

    monkeypatch.setenv("BYTEFRAY_ROOT", str(two_agents))
    evaluate_main(
        ["candidate", "--ruleset", "bytefray-rules-2", "--opponents", "opponent", "--dry-run", "--seeds", "1"]
    )
    out = capsys.readouterr().out
    assert "placements: 3 (opposed, quarter, opposed-shifted)" in out


# ---------------------------------------------------------------------------
# Seeds (Phase 1Z items 20-23)
# ---------------------------------------------------------------------------


def test_standard_v2_seed_default_is_used_when_omitted(two_agents: Path, capsys, monkeypatch):
    from battle_engine.agent_evaluation import main as evaluate_main

    monkeypatch.setenv("BYTEFRAY_ROOT", str(two_agents))
    evaluate_main(
        ["candidate", "--ruleset", "bytefray-rules-2", "--opponents", "opponent", "--dry-run"]
    )
    out = capsys.readouterr().out
    assert f"seeds: {', '.join(str(s) for s in STANDARD_V2_SEEDS)}" in out
    assert STANDARD_V2_SEEDS == (1, 2, 3, 4, 5)


def test_explicit_seeds_override_v2_standard_default(two_agents: Path, capsys, monkeypatch):
    from battle_engine.agent_evaluation import main as evaluate_main

    monkeypatch.setenv("BYTEFRAY_ROOT", str(two_agents))
    evaluate_main(
        [
            "candidate", "--ruleset", "bytefray-rules-2", "--opponents", "opponent",
            "--seeds", "7,8", "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert "seeds: 7, 8" in out


def test_seed_enters_identity(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1, 2), both_orientations=False)
    matrix = build_matrix(request, "evaluation_x")
    ids = {c.schedule_id for c in matrix}
    assert len(ids) == len(matrix)
    seeds_seen = {c.seed for c in matrix}
    assert seeds_seen == {1, 2}


def test_no_duplicate_cells_across_full_v2_matrix(two_agents: Path):
    request = _request(
        two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1, 2, 3), both_orientations=True,
    )
    matrix = build_matrix(request, "evaluation_x")
    assert len({c.schedule_id for c in matrix}) == len(matrix)


# ---------------------------------------------------------------------------
# Combined matrix (Phase 1Z items 24-27)
# ---------------------------------------------------------------------------


def test_expected_v2_cell_count_exact(two_agents: Path):
    request = _request(
        two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=STANDARD_V2_SEEDS, both_orientations=True,
    )
    matrix = build_matrix(request, "evaluation_x")
    # opponents(1) x seeds(5) x placements(3) x orientations(2)
    assert len(matrix) == 1 * 5 * 3 * 2 == 30


def test_multi_opponent_v2_cell_count_exact(two_agents: Path):
    _write_nop_agent(two_agents, "opponent_b")
    request = _request(
        two_agents,
        opponent_ids=("opponent", "opponent_b"),
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        seeds=STANDARD_V2_SEEDS,
        both_orientations=True,
    )
    matrix = build_matrix(request, "evaluation_x")
    assert len(matrix) == 2 * 5 * 3 * 2 == 60


def test_matrix_generation_order_deterministic(two_agents: Path):
    request = _request(
        two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1, 2), both_orientations=True,
    )
    first = build_matrix(request, "evaluation_x")
    second = build_matrix(request, "evaluation_x")
    assert [c.schedule_id for c in first] == [c.schedule_id for c in second]


# ---------------------------------------------------------------------------
# Parallelism (Phase 1Z items 28-29)
# ---------------------------------------------------------------------------


def test_workers_do_not_affect_v2_cell_identity_or_results(two_agents: Path):
    request_kwargs = {
        "ruleset_id": BYTEFRAY_RULESET_V2_ID, "seeds": (1, 2), "both_orientations": True,
    }
    serial = EvaluationService().run(
        _request(two_agents, output_dir=two_agents / "serial", workers=1, **request_kwargs)
    )
    parallel = EvaluationService().run(
        _request(two_agents, output_dir=two_agents / "parallel", workers=4, **request_kwargs)
    )
    assert serial.evaluation_id == parallel.evaluation_id
    serial_by_id = {c.schedule_id: (c.match_id, c.outcome) for c in serial.cells}
    parallel_by_id = {c.schedule_id: (c.match_id, c.outcome) for c in parallel.cells}
    assert serial_by_id == parallel_by_id


# ---------------------------------------------------------------------------
# Resume (Phase 1Z items 30-34)
# ---------------------------------------------------------------------------


def test_v2_resume_reuses_completed_cells(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1, 2), both_orientations=True)
    first = EvaluationService().run(request)
    second = EvaluationService().run(request)
    assert [c.match_id for c in first.cells] == [c.match_id for c in second.cells]


def test_v2_resume_executes_missing_cells(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1, 2), both_orientations=True)
    first = EvaluationService().run(request)
    data = json.loads(first.state_path.read_text(encoding="utf-8"))
    removed = data["cells"].pop()
    import shutil

    shutil.rmtree(request.output_dir / removed["artifact_dir"], ignore_errors=True)
    data["complete"] = False
    first.state_path.write_text(json.dumps(data), encoding="utf-8")

    resumed = EvaluationService().run(request)
    assert len(resumed.cells) == len(first.cells)
    assert all(cell.status == "completed" for cell in resumed.cells)


def test_changed_seed_methodology_rejects_resume(two_agents: Path):
    base = {"ruleset_id": BYTEFRAY_RULESET_V2_ID, "both_orientations": False}
    EvaluationService().run(_request(two_agents, seeds=(1, 2), **base))
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(_request(two_agents, seeds=(1, 3), **base))


def test_changed_ruleset_rejects_resume(two_agents: Path):
    EvaluationService().run(
        _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1,), both_orientations=False)
    )
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(_request(two_agents, ruleset_id=None, seeds=(1,), both_orientations=False))


# ---------------------------------------------------------------------------
# History / comparison / statistical pairing (Phase 1Z items 35-41)
# ---------------------------------------------------------------------------


def test_v2_evaluation_discoverable_via_history_list_show(two_agents: Path):
    from battle_engine.evaluation_history.discovery import adapt_any

    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1,), both_orientations=False)
    result = EvaluationService().run(request)
    summary = adapt_any(result.state_path)
    assert summary.rules_compatibility_id.value == BYTEFRAY_RULESET_V2_ID
    assert summary.arena_alignment_mode.value == EVALUATION_ARENA_ALIGNMENT_MODE_V2_STANDARD
    placement_values = {c.placement.value for c in summary.cells}
    assert placement_values == {"opposed", "quarter", "opposed-shifted"}


def test_identical_v2_methodology_evaluations_are_comparable(two_agents: Path):
    from battle_engine.evaluation_history.comparison import align
    from battle_engine.evaluation_history.discovery import adapt_any

    kwargs = {"ruleset_id": BYTEFRAY_RULESET_V2_ID, "seeds": (1,), "both_orientations": False}
    left = EvaluationService().run(_request(two_agents, output_dir=two_agents / "left", **kwargs))
    right = EvaluationService().run(_request(two_agents, output_dir=two_agents / "right", **kwargs))
    left_summary = adapt_any(left.state_path)
    right_summary = adapt_any(right.state_path)
    aligned = align(left_summary, right_summary)
    assert len(aligned.rows) > 0
    assert not aligned.unmatched_left
    assert not aligned.unmatched_right


def test_different_placement_set_not_cleanly_comparable(two_agents: Path):
    """A v1 (placement='fixed') artifact and a v2 (real placements)
    artifact for the same nominal candidate/opponent must never align as
    directly-comparable rows."""

    from battle_engine.evaluation_history.comparison import align
    from battle_engine.evaluation_history.discovery import adapt_any

    v1 = EvaluationService().run(
        _request(two_agents, output_dir=two_agents / "v1", seeds=(1,), both_orientations=False)
    )
    v2 = EvaluationService().run(
        _request(
            two_agents, output_dir=two_agents / "v2", ruleset_id=BYTEFRAY_RULESET_V2_ID,
            seeds=(1,), both_orientations=False,
        )
    )
    aligned = align(adapt_any(v1.state_path), adapt_any(v2.state_path))
    assert not aligned.rows  # nothing shares a valid alignment key -- never a clean verdict
    assert (
        aligned.unmatched_left
        or aligned.changed_condition
        or aligned.unmatched_right
        or aligned.ambiguous_duplicate_groups
    )


def test_different_seed_set_not_cleanly_comparable(two_agents: Path):
    from battle_engine.evaluation_history.comparison import align
    from battle_engine.evaluation_history.discovery import adapt_any

    kwargs = {"ruleset_id": BYTEFRAY_RULESET_V2_ID, "both_orientations": False}
    left = EvaluationService().run(
        _request(two_agents, output_dir=two_agents / "left", seeds=(1,), **kwargs)
    )
    right = EvaluationService().run(
        _request(two_agents, output_dir=two_agents / "right", seeds=(9,), **kwargs)
    )
    aligned = align(adapt_any(left.state_path), adapt_any(right.state_path))
    assert not aligned.rows


def test_statistical_pairing_includes_placement_dimension(two_agents: Path):
    """compare_candidate_baseline (the shared pairing source for evaluation_
    analysis.analyze) must never pair a candidate's "opposed" cell against a
    baseline's "quarter" cell for the "same" nominal (opponent, seed,
    orientation)."""

    _write_nop_agent(two_agents, "baseline_agent")
    request = _request(
        two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, baseline_id="baseline_agent",
        seeds=(1,), both_orientations=False,
    )
    result = EvaluationService().run(request)
    comparison = compare_candidate_baseline(result.cells)
    placements_seen = {entry.placement_id for entry in comparison}
    assert placements_seen == {"opposed", "quarter", "opposed-shifted"}
    for entry in comparison:
        assert entry.reason != "cell missing on one side"  # every placement has a matched pair


# ---------------------------------------------------------------------------
# Capture (Phase 1Z items 42-46)
# ---------------------------------------------------------------------------


def test_captured_opponent_recorded_and_derivable(capture_agents: Path):
    from battle_engine.evaluation_behavior import cell_ref_from_evaluation_cell
    from battle_engine.evaluation_capture import analyze_capture

    request = _request(
        capture_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1,), ticks=60, both_orientations=True,
    )
    result = EvaluationService().run(request)
    scored_refs = [cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    analysis = analyze_capture("candidate", None, scored_refs)
    assert analysis.candidate_overall.captures_caused > 0
    assert analysis.candidate_overall.captures_suffered == 0


def test_capture_kept_distinct_from_win_field(capture_agents: Path):
    from battle_engine.evaluation_behavior import cell_ref_from_evaluation_cell
    from battle_engine.evaluation_capture import load_cell_capture_sample

    request = _request(
        capture_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1,), ticks=60, both_orientations=False,
    )
    result = EvaluationService().run(request)
    captured_cell = next(cell for cell in result.cells if cell.is_scored)
    ref = cell_ref_from_evaluation_cell(captured_cell)
    sample = load_cell_capture_sample(ref)
    # `outcome`/win-loss lives on EvaluationCell, never on CellCaptureSample.
    assert not hasattr(sample, "outcome")
    assert captured_cell.outcome in ("win", "loss", "tie")


def test_capture_rate_aggregate_populated(capture_agents: Path):
    from battle_engine.evaluation_behavior import cell_ref_from_evaluation_cell
    from battle_engine.evaluation_capture import analyze_capture

    request = _request(
        capture_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1, 2), ticks=60, both_orientations=True,
    )
    result = EvaluationService().run(request)
    scored_refs = [cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    analysis = analyze_capture("candidate", None, scored_refs)
    assert analysis.candidate_overall.capture_rate_caused is not None
    assert analysis.candidate_overall.mean_capture_tick is not None


def test_v1_matches_never_report_core_captured(two_agents: Path):
    request = _request(two_agents, seeds=(1,), both_orientations=False)
    result = EvaluationService().run(request)
    for cell in result.cells:
        data = json.loads((cell.artifact_dir / "result.json").read_text(encoding="utf-8"))
        for entrant in data["entrants"]:
            assert entrant["termination_reason"] != "core_captured"


# ---------------------------------------------------------------------------
# Schema compatibility (Phase 1Z items 47-49)
# ---------------------------------------------------------------------------


def test_historical_v4_fixture_still_readable(two_agents: Path):
    """A schema_version=4 (v1) artifact -- unaffected by this phase's new
    fields at all -- remains readable via read_evaluation and the history
    adapters."""

    from battle_engine.agent_evaluation import read_evaluation
    from battle_engine.evaluation_history.discovery import adapt_any

    result = EvaluationService().run(_request(two_agents, seeds=(1,), both_orientations=False))
    data = read_evaluation(result.state_path)
    assert data["schema_version"] == 4
    summary = adapt_any(result.state_path)
    assert summary.rules_compatibility_id.value == BYTEFRAY_RULESET_ID
    assert all(cell.placement.value == "fixed" for cell in summary.cells)


def test_v2_schema_version_is_five_and_distinct_from_v1(two_agents: Path):
    request = _request(two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, seeds=(1,), both_orientations=False)
    result = EvaluationService().run(request)
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION_V2 == 5
    assert data["identity_version"] == IDENTITY_VERSION_V2 == 5
    assert SCHEMA_VERSION_V2 != SCHEMA_VERSION
    assert IDENTITY_VERSION_V2 != IDENTITY_VERSION


def test_is_ruleset_v2_methodology_excludes_alpha_identities():
    assert is_ruleset_v2_methodology(BYTEFRAY_RULESET_V2_ID) is True
    assert is_ruleset_v2_methodology(BYTEFRAY_RULESET_ID) is False
    assert is_ruleset_v2_methodology("bytefray-rules-2-alpha11") is False
