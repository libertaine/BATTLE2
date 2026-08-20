"""v2.0.0-beta2 Phase 1 capture/core-interaction analysis tests
(docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md Sec Capture).

Unit-level: the ``result.json``-reading loader and pure aggregation, against
hand-built fixtures -- mirrors ``test_evaluation_behavior.py``'s own pattern.
See ``test_agent_evaluation_v2_methodology.py`` for integration coverage
against real ``EvaluationService`` v2 runs.
"""

from __future__ import annotations

from pathlib import Path

from battle_engine.agent_evaluation import ORIENTATION_CANDIDATE_FIRST, ORIENTATION_OPPONENT_FIRST
from battle_engine.evaluation_behavior import CellRef
from battle_engine.evaluation_capture import (
    CORE_CAPTURED_TERMINATION_REASON,
    analyze_capture,
    load_cell_capture_sample,
)
from battle_engine.result_model import SCHEMA_NAME, SCHEMA_VERSION, write_json_atomic

CANDIDATE = "candidate"
BASELINE = "baseline"


def _entrant(agent_id: str, *, termination_reason: str | None, kills: int = 0) -> dict:
    return {
        "agent_id": agent_id,
        "name": agent_id,
        "alive": termination_reason != CORE_CAPTURED_TERMINATION_REASON,
        "score": 12,
        "termination_reason": termination_reason,
        "diagnostic": None,
        "statistics": {"kills": kills, "deaths": 1 if termination_reason else 0},
        "metadata": {},
    }


def _write_result_json(
    path: Path,
    *,
    ticks: int,
    subject_termination: str | None,
    opponent_termination: str | None,
    subject_kills: int = 0,
    opponent_kills: int = 0,
    subject_slot: str = "A",
    opponent_slot: str = "B",
) -> None:
    payload = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "result_id": "result_x",
        "match_id": "match_x",
        "mode": "b2",
        "status": "completed",
        "winner": opponent_slot if subject_termination == CORE_CAPTURED_TERMINATION_REASON else subject_slot,
        "termination_reason": "core_captured" if (subject_termination or opponent_termination) else "tick_limit",
        "ticks": ticks,
        "score": {subject_slot: 10, opponent_slot: 5},
        "entrants": [
            _entrant(subject_slot, termination_reason=subject_termination, kills=subject_kills),
            _entrant(opponent_slot, termination_reason=opponent_termination, kills=opponent_kills),
        ],
        "reproducibility": {},
        "replay": None,
        "backend": None,
        "ruleset_id": "bytefray-rules-2",
    }
    write_json_atomic(path, payload)


def _ref(result_path: Path | None, *, orientation: str = ORIENTATION_CANDIDATE_FIRST, **overrides) -> CellRef:
    defaults = {
        "schedule_id": "s1",
        "subject_role": CANDIDATE,
        "subject_id": "cand",
        "opponent_id": "opp",
        "seed": 1,
        "orientation": orientation,
        "territory_last_fallback": None,
        "result_path": result_path,
    }
    defaults.update(overrides)
    return CellRef(**defaults)


# ---------------------------------------------------------------------------
# Loader: unavailable cases
# ---------------------------------------------------------------------------


def test_no_result_path_is_unavailable():
    sample = load_cell_capture_sample(_ref(None))
    assert sample.available is False
    assert sample.subject_captured is None


def test_unreadable_result_is_unavailable(tmp_path: Path):
    path = tmp_path / "result.json"
    path.write_text("not json", encoding="utf-8")
    sample = load_cell_capture_sample(_ref(path))
    assert sample.available is False
    assert "unreadable" in (sample.unavailable_reason or "")


def test_missing_entrant_is_unavailable(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_result_json(path, ticks=50, subject_termination=None, opponent_termination=None, opponent_slot="A")
    # Both entrants share slot "A" above -- opponent slot "B" is genuinely
    # absent from this result, exactly like a malformed/legacy artifact.
    sample = load_cell_capture_sample(_ref(path))
    assert sample.available is False


# ---------------------------------------------------------------------------
# Loader: capture facts
# ---------------------------------------------------------------------------


def test_no_capture_when_neither_entrant_core_captured(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_result_json(path, ticks=200, subject_termination=None, opponent_termination=None)
    sample = load_cell_capture_sample(_ref(path))
    assert sample.available is True
    assert sample.subject_captured is False
    assert sample.opponent_captured is False
    assert sample.capture_tick is None
    assert sample.killer is None


def test_subject_captured_by_opponent_attributed(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_result_json(
        path, ticks=74, subject_termination=CORE_CAPTURED_TERMINATION_REASON, opponent_termination=None,
        opponent_kills=1,
    )
    sample = load_cell_capture_sample(_ref(path))
    assert sample.subject_captured is True
    assert sample.opponent_captured is False
    assert sample.capture_tick == 74
    assert sample.killer == "opponent"


def test_opponent_captured_by_subject_attributed(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_result_json(
        path, ticks=81, subject_termination=None, opponent_termination=CORE_CAPTURED_TERMINATION_REASON,
        subject_kills=1,
    )
    sample = load_cell_capture_sample(_ref(path))
    assert sample.subject_captured is False
    assert sample.opponent_captured is True
    assert sample.capture_tick == 81
    assert sample.killer == "subject"


def test_capture_without_recorded_kill_is_unattributed(tmp_path: Path):
    """Self-inflicted (or otherwise unattributable) capture: killer stays
    None rather than guessed -- mirrors python_runtime's own "killer !=
    victim" exclusion (docs/RULES_V2.md)."""

    path = tmp_path / "result.json"
    _write_result_json(
        path, ticks=30, subject_termination=CORE_CAPTURED_TERMINATION_REASON, opponent_termination=None,
        opponent_kills=0,
    )
    sample = load_cell_capture_sample(_ref(path))
    assert sample.subject_captured is True
    assert sample.killer is None


def test_capture_distinct_from_win_loss():
    """Phase 1M: capture is never conflated with outcome -- CellCaptureSample
    carries no win/loss/outcome field at all, only capture facts."""

    assert not hasattr(load_cell_capture_sample(_ref(None)), "outcome")


def test_orientation_resolves_correct_physical_slots(tmp_path: Path):
    path = tmp_path / "result.json"
    # Subject occupies slot B under opponent_first orientation -- captured
    # here means slot B's termination_reason is core_captured.
    _write_result_json(
        path, ticks=90, subject_termination=None, opponent_termination=None,
        subject_slot="B", opponent_slot="A",
    )
    sample = load_cell_capture_sample(_ref(path, orientation=ORIENTATION_OPPONENT_FIRST))
    assert sample.available is True


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_aggregate_captures_caused_and_suffered(tmp_path: Path):
    refs = []
    for i in range(3):
        path = tmp_path / f"caused-{i}.json"
        _write_result_json(
            path, ticks=50 + i, subject_termination=None,
            opponent_termination=CORE_CAPTURED_TERMINATION_REASON, subject_kills=1,
        )
        refs.append(_ref(path, schedule_id=f"caused-{i}"))
    for i in range(2):
        path = tmp_path / f"suffered-{i}.json"
        _write_result_json(
            path, ticks=60 + i, subject_termination=CORE_CAPTURED_TERMINATION_REASON,
            opponent_termination=None, opponent_kills=1,
        )
        refs.append(_ref(path, schedule_id=f"suffered-{i}"))
    for i in range(5):
        path = tmp_path / f"neither-{i}.json"
        _write_result_json(path, ticks=200, subject_termination=None, opponent_termination=None)
        refs.append(_ref(path, schedule_id=f"neither-{i}"))

    analysis = analyze_capture("cand", None, refs)
    agg = analysis.candidate_overall
    assert agg.available_count == 10
    assert agg.captures_caused == 3
    assert agg.captures_suffered == 2
    assert agg.capture_rate_caused == 0.3
    assert agg.capture_rate_suffered == 0.2
    assert agg.survival_rate == 0.8
    assert len(agg.capture_ticks) == 5
    assert agg.mean_capture_tick is not None
    assert agg.median_capture_tick is not None


def test_aggregate_with_no_cells_has_none_rates():
    analysis = analyze_capture("cand", None, [])
    agg = analysis.candidate_overall
    assert agg.available_count == 0
    assert agg.capture_rate_caused is None
    assert agg.capture_rate_suffered is None
    assert agg.survival_rate is None


def test_aggregate_baseline_computed_independently(tmp_path: Path):
    cand_path = tmp_path / "cand.json"
    _write_result_json(cand_path, ticks=40, subject_termination=None, opponent_termination=None)
    base_path = tmp_path / "base.json"
    _write_result_json(
        base_path, ticks=45, subject_termination=CORE_CAPTURED_TERMINATION_REASON,
        opponent_termination=None, opponent_kills=1,
    )
    refs = [
        _ref(cand_path, schedule_id="c1", subject_role=CANDIDATE, subject_id="cand"),
        _ref(base_path, schedule_id="b1", subject_role=BASELINE, subject_id="base"),
    ]
    analysis = analyze_capture("cand", "base", refs)
    assert analysis.candidate_overall.captures_suffered == 0
    assert analysis.baseline_overall is not None
    assert analysis.baseline_overall.captures_suffered == 1


def test_to_json_roundtrip_shapes(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_result_json(path, ticks=50, subject_termination=None, opponent_termination=None)
    analysis = analyze_capture("cand", None, [_ref(path)])
    data = analysis.to_json()
    assert data["candidate_id"] == "cand"
    assert data["baseline_id"] is None
    assert "capture_rate_caused" in data["candidate_overall"]
