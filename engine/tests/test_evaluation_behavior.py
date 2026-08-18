"""Phase 5 behavior-profile analysis tests (docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md).

Unit-level: dimension extractors, the ``result.json``-reading loader, pure
aggregation, dimension deltas, and outcome independence -- all against
hand-built fixtures, independent of real match execution (see
``test_agent_evaluation_behavior.py``/``test_evaluation_history_behavior.py``
for integration coverage against real ``EvaluationService`` runs and the
CLI).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_OPPONENT_FIRST,
    physical_slots_for_orientation,
)
from battle_engine.evaluation_behavior import (
    DIMENSION_NAMES,
    BehaviorSampleState,
    CellBehaviorSample,
    CellRef,
    analyze_behavior,
    dimension_deltas,
    largest_bounded_differences,
    load_cell_behavior_sample,
)
from battle_engine.result_model import SCHEMA_NAME, SCHEMA_VERSION, write_json_atomic

CANDIDATE = "candidate"
BASELINE = "baseline"


def _sample(**overrides) -> CellBehaviorSample:
    defaults: dict = {
        "schedule_id": "s1",
        "subject_role": CANDIDATE,
        "subject_id": "cand",
        "opponent_id": "opp",
        "seed": 1,
        "orientation": ORIENTATION_CANDIDATE_FIRST,
        "available": True,
        "unavailable_reason": None,
        "ticks_run": 100,
        "alive_ticks": 100,
        "alive": True,
        "mem_writes": 50,
        "kills": 0,
        "deaths": 0,
        "territory_last_pct": 40.0,
        "territory_max_pct": 50.0,
        "territory_avg_pct": 30.0,
        "termination_reason": "tick_limit",
    }
    defaults.update(overrides)
    return CellBehaviorSample(**defaults)


def _write_result_json(
    path: Path,
    *,
    ticks: int,
    entrant_id: str = "A",
    alive: bool = True,
    alive_ticks: int = 10,
    mem_writes: int = 10,
    kills: int = 0,
    deaths: int = 0,
    territory_last: float = 40.0,
    territory_max: float = 50.0,
    territory_avg: float = 30.0,
    termination_reason: str = "tick_limit",
    include_entrant: bool = True,
) -> None:
    entrants = []
    if include_entrant:
        entrants.append(
            {
                "agent_id": entrant_id,
                "name": entrant_id,
                "alive": alive,
                "score": 12,
                "termination_reason": termination_reason,
                "diagnostic": None,
                "statistics": {
                    "name": entrant_id,
                    "alive": alive,
                    "score": 12,
                    "alive_ticks": alive_ticks,
                    "kills": kills,
                    "deaths": deaths,
                    "cpu_total": 0,
                    "mem_writes": mem_writes,
                    "territory_last": int(territory_last),
                    "territory_max": int(territory_max),
                    "territory_avg": territory_avg,
                    "territory_pct_last": territory_last,
                    "territory_pct_max": territory_max,
                    "territory_pct_avg": territory_avg,
                },
                "metadata": {},
            }
        )
    payload = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "result_id": "result_x",
        "match_id": "match_x",
        "mode": "b2",
        "status": "completed",
        "winner": entrant_id,
        "termination_reason": termination_reason,
        "ticks": ticks,
        "score": {entrant_id: 12},
        "entrants": entrants,
        "reproducibility": {},
        "replay": None,
        "backend": None,
        "ruleset_id": "bytefray-rules-1",
    }
    write_json_atomic(path, payload)


# ---------------------------------------------------------------------------
# Dimension extractors: hand-checkable
# ---------------------------------------------------------------------------


def test_survival_fraction_hand_checked():
    from battle_engine.evaluation_behavior import _survival_fraction

    assert _survival_fraction(_sample(alive_ticks=50, ticks_run=200)) == 0.25
    assert _survival_fraction(_sample(alive_ticks=200, ticks_run=200)) == 1.0


def test_survival_fraction_missing_or_zero_ticks_is_none():
    from battle_engine.evaluation_behavior import _survival_fraction

    assert _survival_fraction(_sample(alive_ticks=None)) is None
    assert _survival_fraction(_sample(ticks_run=0)) is None
    assert _survival_fraction(_sample(ticks_run=None)) is None


def test_writes_per_tick_hand_checked():
    from battle_engine.evaluation_behavior import _writes_per_tick

    assert _writes_per_tick(_sample(mem_writes=800, ticks_run=200)) == 4.0


def test_writes_per_alive_tick_hand_checked():
    from battle_engine.evaluation_behavior import _writes_per_alive_tick

    assert _writes_per_alive_tick(_sample(mem_writes=100, alive_ticks=50)) == 2.0
    assert _writes_per_alive_tick(_sample(mem_writes=100, alive_ticks=0)) is None
    assert _writes_per_alive_tick(_sample(mem_writes=100, alive_ticks=None)) is None


def test_territory_retention_hand_checked():
    from battle_engine.evaluation_behavior import _territory_retention

    assert _territory_retention(_sample(territory_last_pct=25.0, territory_max_pct=50.0)) == 0.5
    assert _territory_retention(_sample(territory_last_pct=50.0, territory_max_pct=50.0)) == 1.0


def test_territory_retention_never_held_territory_is_none_not_zero_division():
    from battle_engine.evaluation_behavior import _territory_retention

    assert _territory_retention(_sample(territory_last_pct=0.0, territory_max_pct=0.0)) is None


def test_territory_spread_hand_checked():
    from battle_engine.evaluation_behavior import _territory_spread

    assert _territory_spread(_sample(territory_max_pct=60.0, territory_avg_pct=45.0)) == 15.0


def test_kill_dimensions_hand_checked():
    from battle_engine.evaluation_behavior import _kill_involvement_rate, _kills_per_match

    assert _kills_per_match(_sample(kills=3)) == 3.0
    assert _kill_involvement_rate(_sample(kills=3)) == 1.0
    assert _kill_involvement_rate(_sample(kills=0)) == 0.0
    assert _kill_involvement_rate(_sample(kills=None)) is None


# ---------------------------------------------------------------------------
# load_cell_behavior_sample: real result.json I/O
# ---------------------------------------------------------------------------


def test_load_cell_behavior_sample_reads_real_result_json(tmp_path: Path):
    result_path = tmp_path / "result.json"
    _write_result_json(
        result_path, ticks=200, entrant_id="A", alive_ticks=180, mem_writes=1600,
        kills=0, deaths=0, territory_last=40.0, territory_max=55.0, territory_avg=30.0,
    )
    ref = CellRef(
        schedule_id="s", subject_role=CANDIDATE, subject_id="cand", opponent_id="opp",
        seed=1, orientation=ORIENTATION_CANDIDATE_FIRST, territory_last_fallback=None,
        result_path=result_path,
    )
    sample = load_cell_behavior_sample(ref)
    assert sample.available is True
    assert sample.unavailable_reason is None
    assert sample.ticks_run == 200
    assert sample.alive_ticks == 180
    assert sample.mem_writes == 1600
    assert sample.territory_last_pct == 40.0
    assert sample.territory_max_pct == 55.0
    assert sample.termination_reason == "tick_limit"


def test_load_cell_behavior_sample_opponent_first_reads_opponent_physical_slot(tmp_path: Path):
    """subject_slot for opponent_first is 'B', not 'A' -- must read the right entrant."""

    result_path = tmp_path / "result.json"
    payload_a = {"entrant_id": "A", "mem_writes": 999}
    _write_result_json(result_path, ticks=200, **payload_a)
    # Overwrite with two entrants: A (opponent's physical slot in this
    # orientation) and B (subject's physical slot).
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["entrants"] = [
        {**data["entrants"][0], "agent_id": "A", "statistics": {**data["entrants"][0]["statistics"], "mem_writes": 999}},
        {**data["entrants"][0], "agent_id": "B", "statistics": {**data["entrants"][0]["statistics"], "mem_writes": 42}},
    ]
    result_path.write_text(json.dumps(data), encoding="utf-8")

    ref = CellRef(
        schedule_id="s", subject_role=CANDIDATE, subject_id="cand", opponent_id="opp",
        seed=1, orientation=ORIENTATION_OPPONENT_FIRST, territory_last_fallback=None,
        result_path=result_path,
    )
    sample = load_cell_behavior_sample(ref)
    assert sample.available is True
    assert sample.mem_writes == 42


def test_load_cell_behavior_sample_missing_path_is_unavailable_with_fallback():
    ref = CellRef(
        schedule_id="s", subject_role=CANDIDATE, subject_id="cand", opponent_id="opp",
        seed=1, orientation=ORIENTATION_CANDIDATE_FIRST, territory_last_fallback=61.5,
        result_path=None,
    )
    sample = load_cell_behavior_sample(ref)
    assert sample.available is False
    assert sample.unavailable_reason is not None
    assert sample.territory_last_pct == 61.5  # Tier-1 fallback still populated
    assert sample.mem_writes is None


def test_load_cell_behavior_sample_missing_file_is_unavailable(tmp_path: Path):
    ref = CellRef(
        schedule_id="s", subject_role=CANDIDATE, subject_id="cand", opponent_id="opp",
        seed=1, orientation=ORIENTATION_CANDIDATE_FIRST, territory_last_fallback=None,
        result_path=tmp_path / "does_not_exist" / "result.json",
    )
    sample = load_cell_behavior_sample(ref)
    assert sample.available is False
    assert "unreadable" in sample.unavailable_reason


def test_load_cell_behavior_sample_corrupt_json_is_unavailable(tmp_path: Path):
    result_path = tmp_path / "result.json"
    result_path.write_text("not json at all", encoding="utf-8")
    ref = CellRef(
        schedule_id="s", subject_role=CANDIDATE, subject_id="cand", opponent_id="opp",
        seed=1, orientation=ORIENTATION_CANDIDATE_FIRST, territory_last_fallback=None,
        result_path=result_path,
    )
    sample = load_cell_behavior_sample(ref)
    assert sample.available is False
    assert "unreadable" in sample.unavailable_reason


def test_load_cell_behavior_sample_missing_entrant_is_unavailable(tmp_path: Path):
    result_path = tmp_path / "result.json"
    _write_result_json(result_path, ticks=200, entrant_id="A", include_entrant=False)
    ref = CellRef(
        schedule_id="s", subject_role=CANDIDATE, subject_id="cand", opponent_id="opp",
        seed=1, orientation=ORIENTATION_CANDIDATE_FIRST, territory_last_fallback=None,
        result_path=result_path,
    )
    sample = load_cell_behavior_sample(ref)
    assert sample.available is False
    assert "entrant" in sample.unavailable_reason
    assert sample.ticks_run == 200  # Tier-1-ish envelope data still recorded


# ---------------------------------------------------------------------------
# analyze_behavior: aggregation, grouping, empty/partial data
# ---------------------------------------------------------------------------


_REF_DIR_COUNTER = {"n": 0}


def _refs_from_result_dir(tmp_path: Path, cells: list[dict]) -> list[CellRef]:
    """Write one result.json per cell spec and return matching CellRefs.

    Each call gets its own unique subdirectory prefix (a module-level
    counter, not the loop index alone) so multiple calls against the same
    ``tmp_path`` -- routine in tests comparing two subjects -- never
    collide on the same ``result.json`` path.
    """

    _REF_DIR_COUNTER["n"] += 1
    call_id = _REF_DIR_COUNTER["n"]
    refs = []
    for i, spec in enumerate(cells):
        orientation = spec.get("orientation", ORIENTATION_CANDIDATE_FIRST)
        subject_slot, _opponent_slot = physical_slots_for_orientation(orientation)
        result_path = tmp_path / f"cell{call_id}_{i}" / "result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        _write_result_json(
            result_path,
            ticks=spec.get("ticks", 200),
            entrant_id=subject_slot,
            alive_ticks=spec.get("alive_ticks", 200),
            mem_writes=spec.get("mem_writes", 100),
            kills=spec.get("kills", 0),
            deaths=spec.get("deaths", 0),
            territory_last=spec.get("territory_last", 40.0),
            territory_max=spec.get("territory_max", 50.0),
            territory_avg=spec.get("territory_avg", 30.0),
        )
        refs.append(
            CellRef(
                schedule_id=f"s{call_id}_{i}",
                subject_role=spec.get("subject_role", CANDIDATE),
                subject_id=spec.get("subject_id", "cand"),
                opponent_id=spec.get("opponent_id", "opp"),
                seed=spec.get("seed", i),
                orientation=orientation,
                territory_last_fallback=None,
                result_path=result_path,
            )
        )
    return refs


def test_analyze_behavior_empty_refs_is_insufficient_data():
    analysis = analyze_behavior("cand", None, [])
    assert analysis.candidate_overall.sample_count == 0
    assert analysis.candidate_overall.available_count == 0
    for name in DIMENSION_NAMES:
        dim = analysis.candidate_overall.dimension(name)
        assert dim.state == BehaviorSampleState.INSUFFICIENT_DATA
        assert dim.mean is None
    assert analysis.baseline_overall is None


def test_analyze_behavior_no_baseline_leaves_baseline_fields_none(tmp_path: Path):
    refs = _refs_from_result_dir(tmp_path, [{"opponent_id": "opp_a"}, {"opponent_id": "opp_b"}])
    analysis = analyze_behavior("cand", None, refs)
    assert analysis.baseline_overall is None
    assert analysis.baseline_by_orientation == ()
    assert analysis.baseline_by_opponent == ()
    assert analysis.candidate_vs_baseline_deltas is None
    assert analysis.candidate_vs_baseline_largest is None
    assert analysis.candidate_overall.sample_count == 2


def test_analyze_behavior_by_opponent_grouping(tmp_path: Path):
    refs = _refs_from_result_dir(
        tmp_path,
        [
            {"opponent_id": "opp_a", "mem_writes": 100},
            {"opponent_id": "opp_a", "mem_writes": 100},
            {"opponent_id": "opp_b", "mem_writes": 400},
        ],
    )
    analysis = analyze_behavior("cand", None, refs)
    by_opponent = {p.scope_label: p for p in analysis.candidate_by_opponent}
    assert set(by_opponent) == {"opp_a", "opp_b"}
    assert by_opponent["opp_a"].sample_count == 2
    assert by_opponent["opp_b"].sample_count == 1
    # writes_per_tick = mem_writes/ticks_run = 100/200=0.5 vs 400/200=2.0
    assert by_opponent["opp_a"].dimension("writes_per_tick").mean == 0.5
    assert by_opponent["opp_b"].dimension("writes_per_tick").mean == 2.0


def test_analyze_behavior_by_orientation_grouping(tmp_path: Path):
    refs = _refs_from_result_dir(
        tmp_path,
        [
            {"orientation": ORIENTATION_CANDIDATE_FIRST, "territory_last": 60.0},
            {"orientation": ORIENTATION_OPPONENT_FIRST, "territory_last": 20.0},
        ],
    )
    analysis = analyze_behavior("cand", None, refs)
    by_orientation = {p.scope_label: p for p in analysis.candidate_by_orientation}
    assert by_orientation[ORIENTATION_CANDIDATE_FIRST].dimension("territory_last_pct").mean == 60.0
    assert by_orientation[ORIENTATION_OPPONENT_FIRST].dimension("territory_last_pct").mean == 20.0
    # Orientation deltas: candidate_first - opponent_first = 60 - 20 = 40.
    delta = next(d for d in analysis.candidate_orientation_deltas if d.name == "territory_last_pct")
    assert delta.delta == 40.0


def test_analyze_behavior_partial_availability_degrades_gracefully(tmp_path: Path):
    """One cell's result.json is missing; the profile must still compute
    over the remaining available cell rather than failing outright."""

    refs = _refs_from_result_dir(tmp_path, [{"mem_writes": 100}])
    missing_ref = CellRef(
        schedule_id="missing", subject_role=CANDIDATE, subject_id="cand", opponent_id="opp",
        seed=99, orientation=ORIENTATION_CANDIDATE_FIRST, territory_last_fallback=None,
        result_path=None,
    )
    analysis = analyze_behavior("cand", None, [*refs, missing_ref])
    assert analysis.candidate_overall.sample_count == 2
    assert analysis.candidate_overall.available_count == 1
    # writes_per_tick only has one contributing value (the available cell).
    assert analysis.candidate_overall.dimension("writes_per_tick").n == 1


# ---------------------------------------------------------------------------
# dimension_deltas / largest_bounded_differences
# ---------------------------------------------------------------------------


def test_dimension_deltas_identical_profiles_are_zero(tmp_path: Path):
    refs = _refs_from_result_dir(tmp_path, [{"mem_writes": 100}])
    analysis = analyze_behavior("cand", "base", [
        *refs,
        *_refs_from_result_dir(tmp_path, [{"subject_role": BASELINE, "subject_id": "base", "mem_writes": 100}]),
    ])
    deltas = dimension_deltas(analysis.candidate_overall, analysis.baseline_overall)
    for d in deltas:
        if d.left is not None and d.right is not None:
            assert abs(d.delta) < 1e-9


def test_dimension_deltas_are_antisymmetric(tmp_path: Path):
    refs_c = _refs_from_result_dir(tmp_path, [{"mem_writes": 400, "territory_last": 60.0}])
    refs_b = _refs_from_result_dir(
        tmp_path, [{"subject_role": BASELINE, "subject_id": "base", "mem_writes": 100, "territory_last": 20.0}]
    )
    analysis = analyze_behavior("cand", "base", [*refs_c, *refs_b])
    forward = dimension_deltas(analysis.candidate_overall, analysis.baseline_overall)
    backward = dimension_deltas(analysis.baseline_overall, analysis.candidate_overall)
    for f, b in zip(forward, backward, strict=True):
        assert f.delta == pytest.approx(-b.delta)


def test_largest_bounded_differences_excludes_unbounded_rate_dimensions(tmp_path: Path):
    # A huge writes_per_tick/kills_per_match delta (unbounded units) must
    # never crowd out a genuinely large bounded (fraction/percent) delta.
    refs_c = _refs_from_result_dir(
        tmp_path, [{"mem_writes": 100000, "territory_last": 90.0, "territory_max": 90.0, "territory_avg": 90.0}]
    )
    refs_b = _refs_from_result_dir(
        tmp_path,
        [
            {
                "subject_role": BASELINE, "subject_id": "base",
                "mem_writes": 1, "territory_last": 10.0, "territory_max": 10.0, "territory_avg": 10.0,
            }
        ],
    )
    analysis = analyze_behavior("cand", "base", [*refs_c, *refs_b])
    largest = analysis.candidate_vs_baseline_largest
    assert largest is not None
    assert "writes_per_tick" not in largest
    assert "territory_last_pct" in largest or "territory_max_pct" in largest or "territory_avg_pct" in largest


def test_largest_bounded_differences_missing_data_excluded():
    deltas = dimension_deltas(
        _profile_stub({"survival_fraction": (1.0, 1)}),
        _profile_stub({}),
    )
    assert largest_bounded_differences(deltas) == ()


def _profile_stub(values: dict[str, tuple[float, int]]):
    from battle_engine.evaluation_behavior import _DIMENSIONS, BehaviorProfile, DimensionValue

    dims = {}
    for d in _DIMENSIONS:
        if d.name in values:
            mean, n = values[d.name]
            dims[d.name] = DimensionValue(name=d.name, label=d.label, unit=d.unit, mean=mean, n=n, minimum=mean, maximum=mean)
        else:
            dims[d.name] = DimensionValue(name=d.name, label=d.label, unit=d.unit, mean=None, n=0, minimum=None, maximum=None)
    return BehaviorProfile(
        subject_role=CANDIDATE, subject_id="x", scope_label="all", sample_count=1, available_count=1, dimensions=dims
    )


# ---------------------------------------------------------------------------
# Outcome independence: behavior computation never reads outcome/score
# ---------------------------------------------------------------------------


def test_cell_ref_carries_no_outcome_or_score_field():
    """Structural proof of Sec 6 of the design doc: CellRef -- the only
    input analyze_behavior ever sees -- has no outcome/score/win-loss field
    at all, so behavioral measurement cannot be influenced by (or leak
    into) Phase 4's outcome-based analysis even by accident."""

    field_names = set(CellRef.__dataclass_fields__)
    assert "outcome" not in field_names
    assert "score_subject" not in field_names
    assert "score_opponent" not in field_names


def test_same_outcome_different_behavior_profiles(tmp_path: Path):
    """Two subjects that would classify identically under Phase 4 (same
    win/loss shape is irrelevant here -- CellRef never carries outcome at
    all) can still show a materially different behavior profile, because
    the two are computed from entirely disjoint data. Demonstrates the
    required outcome/behavior separation concretely rather than only by
    code-structure argument."""

    aggressive_writer = _refs_from_result_dir(
        tmp_path, [{"mem_writes": 1600, "territory_last": 80.0, "territory_max": 90.0, "territory_avg": 70.0}]
    )
    sparse_writer = _refs_from_result_dir(
        tmp_path,
        [
            {
                "subject_role": BASELINE, "subject_id": "base",
                "mem_writes": 20, "territory_last": 15.0, "territory_max": 20.0, "territory_avg": 10.0,
            }
        ],
    )
    analysis = analyze_behavior("cand", "base", [*aggressive_writer, *sparse_writer])
    assert analysis.candidate_overall.dimension("writes_per_tick").mean != analysis.baseline_overall.dimension("writes_per_tick").mean
    assert analysis.candidate_overall.dimension("territory_avg_pct").mean != analysis.baseline_overall.dimension("territory_avg_pct").mean


# ---------------------------------------------------------------------------
# Determinism / repeatability
# ---------------------------------------------------------------------------


def test_analyze_behavior_is_deterministic_across_repeated_calls(tmp_path: Path):
    refs = _refs_from_result_dir(
        tmp_path,
        [
            {"opponent_id": "opp_a", "seed": 1, "mem_writes": 100},
            {"opponent_id": "opp_b", "seed": 2, "mem_writes": 400, "orientation": ORIENTATION_OPPONENT_FIRST},
        ],
    )
    first = analyze_behavior("cand", None, refs).to_json()
    second = analyze_behavior("cand", None, refs).to_json()
    assert first == second
