"""v2.0.0-beta2 Phase 3 -- multi-entrant strategic analysis integration
(docs/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md).

Integration-level: real ``EvaluationService --group`` runs feeding
``evaluation_group_analysis.analyze_group`` (the live-run CLI path, via
``agent_evaluation._print_group_analysis``'s own construction) and real
``evaluations show`` reads of the resulting artifact (the historical-read
path, via ``evaluation_history.group_adapter``/``cli._cmd_show``). See
``test_evaluation_group_analysis.py`` for unit-level coverage against
hand-built ``result.json`` fixtures, and
``test_agent_evaluation_multi_entrant.py`` for Phase 2's own roster/seat/
layout/identity coverage this phase does not re-prove.
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agent_evaluation import (
    BYTEFRAY_RULESET_ID,
    BYTEFRAY_RULESET_V2_ID,
    EvaluationRequest,
    EvaluationService,
)
from battle_engine.evaluation_group_analysis import (
    EntrantOutcome,
    analyze_group,
    candidate_focused_view,
    group_cell_ref_from_evaluation_cell,
    load_group_cell_records,
)
from battle_engine.evaluation_history.discovery import adapt_any
from battle_engine.evaluation_history.group_adapter import group_cell_refs
from battle_engine.evaluation_history.models import FieldConfidence, HealthCode

NOP_ACTION = "AgentAction(ActionKind.NOP)"
HALT_ACTION = "AgentAction(ActionKind.HALT)"


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


def _write_halt_agent(root: Path, name: str) -> Path:
    return _write_agent(root, name, f"        return {HALT_ACTION}")


def _request(root: Path, **overrides) -> EvaluationRequest:
    defaults: dict = {
        "candidate_id": "candidate",
        "opponent_ids": ("opp_a", "opp_b"),
        "seeds": (1,),
        "output_dir": root / "eval-out",
        "ticks": 15,
        "data_root": root,
        "both_orientations": False,
        "ruleset_id": BYTEFRAY_RULESET_V2_ID,
        "group": True,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


def test_live_run_group_analysis_covers_every_roster_entrant(tmp_path: Path):
    _write_halt_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    _write_nop_agent(tmp_path, "opp_b")
    result = EvaluationService().run(_request(tmp_path))

    refs = [group_cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    analysis = analyze_group(("candidate", "opp_a", "opp_b"), refs)

    assert {s.agent_id for s in analysis.entrant_summaries} == {"candidate", "opp_a", "opp_b"}
    candidate_summary = analysis.summary_for("candidate")
    assert candidate_summary is not None
    # A HALT agent dies on its very first action, every cell, regardless of
    # seat/layout -- deterministic ELIMINATED, distinct from the two NOP
    # survivors (Sec 9's critical rule, proven here against a real engine
    # run rather than a hand-built fixture).
    assert candidate_summary.elimination.rate == 1.0
    assert candidate_summary.survival.rate == 0.0
    for other_id in ("opp_a", "opp_b"):
        other_summary = analysis.summary_for(other_id)
        assert other_summary is not None
        assert other_summary.survival.rate == 1.0


def test_live_run_records_are_traceable_to_source_cells(tmp_path: Path):
    """Section 32: every aggregate must remain auditable back to its raw
    per-cell evidence -- schedule_id/seat/layout/seed on each record."""

    _write_halt_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    _write_nop_agent(tmp_path, "opp_b")
    result = EvaluationService().run(_request(tmp_path, seeds=(1, 2)))

    refs = [group_cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    analysis = analyze_group(("candidate", "opp_a", "opp_b"), refs)

    schedule_ids = {cell.schedule_id for cell in result.cells if cell.is_scored}
    assert {r.schedule_id for r in analysis.records} <= schedule_ids
    assert len(analysis.records) == len(refs) * 3  # one record per seat per cell


def test_candidate_focused_view_matches_symmetric_summary_end_to_end(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    _write_halt_agent(tmp_path, "opp_b")
    result = EvaluationService().run(_request(tmp_path))

    refs = [group_cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    analysis = analyze_group(("candidate", "opp_a", "opp_b"), refs)
    view = candidate_focused_view(analysis, "candidate")
    assert view.candidate is not None
    assert view.candidate.to_json() == analysis.summary_for("candidate").to_json()
    # opp_b (HALT) is deterministically eliminated -- proves outcome
    # classification is agent-identity-driven, not candidate-designation-driven.
    opp_b_summary = next(s for s in view.other_entrants if s.agent_id == "opp_b")
    assert opp_b_summary.elimination.rate == 1.0


def test_evaluations_show_json_includes_group_analysis_for_v6_artifact(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    _write_nop_agent(tmp_path, "opp_b")
    result = EvaluationService().run(_request(tmp_path))

    summary = adapt_any(result.state_path)
    assert summary.group.value is True
    refs = group_cell_refs(summary)
    assert len(refs) == len([c for c in result.cells if c.is_scored])
    analysis = analyze_group(summary.roster_agent_ids.value or (), refs)
    assert len(analysis.entrant_summaries) == 3
    assert analysis.available_cells == analysis.cells_analyzed


# ---------------------------------------------------------------------------
# H2 (Beta2 Phase 4.1): self-play roster (candidate appears more than once)
# must not be falsely flagged unhealthy. The independent review found a real
# 9-cell self-play group artifact (roster candidate/candidate/opponent)
# reporting CONDITION_FINGERPRINT_INCONSISTENT on every cell -- traced to
# v2_adapter.py inferring "this must be a pairwise cell, resolve its
# opponent identity" from the group cell's joined display label happening
# to equal a real opponent_ids entry, which is exactly what a self-play
# roster's label degenerates to (see v2_adapter.py's own H2 comments).
# ---------------------------------------------------------------------------


def test_self_play_candidate_duplicated_group_artifact_is_healthy(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opponent")
    # roster_agent_ids = (candidate_id, *opponent_ids) = (candidate,
    # candidate, opponent) -- candidate occupies two of the three seats.
    result = EvaluationService().run(_request(tmp_path, opponent_ids=("candidate", "opponent")))

    summary = adapt_any(result.state_path)
    assert summary.group.value is True
    assert summary.health.codes == (HealthCode.HEALTHY,)
    assert HealthCode.CONDITION_FINGERPRINT_INCONSISTENT not in summary.health.codes

    scored_cells = [cell for cell in summary.cells if cell.is_scored]
    assert scored_cells
    for cell in scored_cells:
        assert cell.verify_error is None
        # No bogus pairwise opponent identity: a group cell's opponent_id is
        # a display label only, never a real per-cell opponent, so its
        # opponent_identity must stay UNKNOWN, never silently populated from
        # whichever opponent_ids entry the label happened to string-match.
        assert cell.opponent_identity.confidence == FieldConfidence.UNKNOWN
        # The duplicate roster entry itself must still be represented.
        assert cell.roster.value.count("candidate") == 2

    refs = group_cell_refs(summary)
    assert len(refs) == len(scored_cells)
    analysis = analyze_group(summary.roster_agent_ids.value or (), refs)
    assert {s.agent_id for s in analysis.entrant_summaries} == {"candidate", "opponent"}
    view = candidate_focused_view(analysis, "candidate")
    assert view.candidate is not None


def test_self_play_opponent_duplicated_group_artifact_is_healthy(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opponent")
    # roster_agent_ids = (candidate, opponent, opponent) -- the *opponent*
    # occupies two of the three seats this time, the opposite duplication
    # shape from the test above.
    result = EvaluationService().run(_request(tmp_path, opponent_ids=("opponent", "opponent")))

    summary = adapt_any(result.state_path)
    assert summary.group.value is True
    assert summary.health.codes == (HealthCode.HEALTHY,)
    assert HealthCode.CONDITION_FINGERPRINT_INCONSISTENT not in summary.health.codes

    scored_cells = [cell for cell in summary.cells if cell.is_scored]
    assert scored_cells
    for cell in scored_cells:
        assert cell.opponent_identity.confidence == FieldConfidence.UNKNOWN
        assert cell.roster.value.count("opponent") == 2

    refs = group_cell_refs(summary)
    analysis = analyze_group(summary.roster_agent_ids.value or (), refs)
    assert {s.agent_id for s in analysis.entrant_summaries} == {"candidate", "opponent"}


def test_pairwise_v5_artifact_group_adapter_returns_no_refs(tmp_path: Path):
    """Compatibility: a pairwise (non-group) artifact must never produce a
    spurious group-analysis ref -- group_cell_refs must recognize it has
    nothing to do rather than misinterpreting a pairwise cell as a
    1-entrant "roster"."""

    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    request = _request(tmp_path, opponent_ids=("opp_a",), group=False)
    result = EvaluationService().run(request)

    summary = adapt_any(result.state_path)
    assert summary.group.value is False
    assert group_cell_refs(summary) == ()


def test_non_group_v1_evaluation_unaffected_by_group_analysis_module(tmp_path: Path):
    """v1 preservation: a plain v1 evaluation must produce identical
    results whether or not this phase's group-analysis module exists --
    it is never imported or invoked from the v1/non-group code path."""

    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    request = _request(
        tmp_path, opponent_ids=("opp_a",), group=False, ruleset_id=BYTEFRAY_RULESET_ID
    )
    result = EvaluationService().run(request)
    assert result.cells
    for cell in result.cells:
        assert not cell.is_group
        assert cell.roster_agent_ids == ()


def test_outcome_never_collapses_survivor_and_eliminated(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    _write_halt_agent(tmp_path, "opp_b")
    result = EvaluationService().run(_request(tmp_path))

    refs = [group_cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    records = []
    for ref in refs:
        records.extend(load_group_cell_records(ref))
    outcomes_by_agent = {r.agent_id for r in records if r.outcome == EntrantOutcome.ELIMINATED}
    assert "opp_b" in outcomes_by_agent
    non_eliminated = {r.agent_id for r in records if r.outcome != EntrantOutcome.ELIMINATED}
    assert "candidate" in non_eliminated or "opp_a" in non_eliminated
