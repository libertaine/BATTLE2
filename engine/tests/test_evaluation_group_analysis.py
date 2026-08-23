"""v2.0.0-beta2 Phase 3 multi-entrant strategic analysis tests
(docs/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md).

Unit-level: the ``result.json``-reading loader and pure aggregation,
against hand-built fixtures -- mirrors ``test_evaluation_capture.py``'s own
pattern, generalized from a fixed (subject, opponent) pair to an N-entrant
roster. See ``test_agent_evaluation_multi_entrant.py`` for integration
coverage against real ``EvaluationService --group`` runs.
"""

from __future__ import annotations

from pathlib import Path

from battle_engine.evaluation_capture import CORE_CAPTURED_TERMINATION_REASON
from battle_engine.evaluation_group_analysis import (
    EntrantOutcome,
    GroupCellRef,
    analyze_group,
    candidate_focused_view,
    entrant_summary,
    interaction_matrix,
    layout_sensitivity,
    load_group_cell_records,
    seat_sensitivity,
    seed_summary,
)
from battle_engine.result_model import SCHEMA_NAME, SCHEMA_VERSION, write_json_atomic

ROSTER = ("a", "b", "c")


def _entrant(
    seat: str,
    name: str,
    *,
    alive: bool,
    score: float,
    termination_reason: str | None = None,
    kills: int = 0,
    deaths: int = 0,
    alive_ticks: int = 100,
    mem_writes: int = 0,
    territory_last: float = 0.0,
    territory_max: float = 0.0,
    territory_avg: float = 0.0,
) -> dict:
    return {
        "agent_id": seat,
        "name": name,
        "alive": alive,
        "score": score,
        "termination_reason": termination_reason,
        "diagnostic": None,
        "statistics": {
            "alive_ticks": alive_ticks,
            "kills": kills,
            "deaths": deaths,
            "mem_writes": mem_writes,
            "territory_pct_last": territory_last,
            "territory_pct_max": territory_max,
            "territory_pct_avg": territory_avg,
        },
        "metadata": {},
    }


def _write_group_result(
    path: Path, *, ticks: int, winner: str, entrants: list[dict], termination_reason: str = "last_agent_standing"
) -> None:
    payload = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "result_id": "result_x",
        "match_id": "match_x",
        "mode": "b2",
        "status": "completed",
        "winner": winner,
        "termination_reason": termination_reason,
        "ticks": ticks,
        "score": {e["agent_id"]: e["score"] for e in entrants},
        "entrants": entrants,
        "reproducibility": {},
        "replay": None,
        "backend": None,
        "ruleset_id": "bytefray-rules-2",
    }
    write_json_atomic(path, payload)


def _ref(result_path: Path | None, **overrides) -> GroupCellRef:
    defaults = {
        "schedule_id": "s1",
        "roster_agent_ids": ROSTER,
        "seat_agent_ids": ROSTER,
        "layout_id": "spread",
        "seed": 1,
        "result_path": result_path,
    }
    defaults.update(overrides)
    return GroupCellRef(**defaults)


# ---------------------------------------------------------------------------
# Loader: per-entrant extraction
# ---------------------------------------------------------------------------


def test_no_result_path_yields_unavailable_records_for_every_seat():
    records = load_group_cell_records(_ref(None))
    assert len(records) == 3
    assert {r.agent_id for r in records} == set(ROSTER)
    assert all(not r.available for r in records)
    assert all(r.outcome is None for r in records)


def test_unreadable_result_yields_unavailable_records(tmp_path: Path):
    path = tmp_path / "result.json"
    path.write_text("not json", encoding="utf-8")
    records = load_group_cell_records(_ref(path))
    assert len(records) == 3
    assert all(not r.available for r in records)
    assert "unreadable" in (records[0].unavailable_reason or "")


def test_missing_seat_is_unavailable(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=50,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=10),
            _entrant("B", "b", alive=True, score=5),
            # seat "C" missing entirely.
        ],
    )
    records = load_group_cell_records(_ref(path))
    assert all(not r.available for r in records)


def test_extracts_all_entrants_no_omission_seat_mapping_correct(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=80,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=1),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    records = load_group_cell_records(_ref(path))
    assert len(records) == 3
    by_agent = {r.agent_id: r for r in records}
    assert by_agent["a"].seat == "A"
    assert by_agent["b"].seat == "B"
    assert by_agent["c"].seat == "C"
    assert all(r.seat_agent_ids == ROSTER for r in records)


def test_winner_maps_to_correct_entrant_survivor_and_eliminated_distinguished(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=80,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=1),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    records = {r.agent_id: r for r in load_group_cell_records(_ref(path))}
    assert records["a"].outcome == EntrantOutcome.WINNER
    assert records["b"].outcome == EntrantOutcome.SURVIVING_NON_WINNER
    assert records["c"].outcome == EntrantOutcome.ELIMINATED
    # Section 9's critical rule: b and c must not collapse into one state.
    assert records["b"].outcome != records["c"].outcome


def test_tie_no_winner_leaves_every_entrant_non_winner(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=200,
        winner="tie",
        entrants=[
            _entrant("A", "a", alive=True, score=10),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=True, score=10),
        ],
    )
    records = load_group_cell_records(_ref(path))
    assert all(r.outcome == EntrantOutcome.SURVIVING_NON_WINNER for r in records)
    assert sum(1 for r in records if r.outcome == EntrantOutcome.WINNER) == 0


def test_score_rank_and_margin_to_winner(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=80,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=True, score=5),
        ],
    )
    records = {r.agent_id: r for r in load_group_cell_records(_ref(path))}
    assert records["a"].score_rank == 1
    assert records["b"].score_rank == 2
    assert records["c"].score_rank == 3
    assert records["a"].margin_to_winner == 0
    assert records["b"].margin_to_winner == 10
    assert records["c"].margin_to_winner == 15


# ---------------------------------------------------------------------------
# Capture: caused/suffered attribution, ambiguity
# ---------------------------------------------------------------------------


def test_capture_attributed_unambiguously_when_exactly_one_death(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=80,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=1),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    records = {r.agent_id: r for r in load_group_cell_records(_ref(path))}
    assert records["a"].captor_of == ("c",)
    assert records["a"].capture_tick_caused == 80
    assert records["c"].captured is True
    assert records["c"].capture_tick == 80
    assert records["b"].captor_of == ()


def test_capture_tick_withheld_when_match_ends_by_tick_limit_not_the_capture(tmp_path: Path):
    """A capture that happens mid-match, with two or more entrants still
    alive afterward, does not end the match -- it keeps running to the
    tick budget under ``tick_limit``. Reporting the final tick count as
    that capture's own tick would overstate it (often severely); this
    module must withhold the tick rather than report a wrong one, while
    still reporting the fact and attribution of the capture itself."""

    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=400,
        winner="A",
        termination_reason="tick_limit",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=1),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    records = {r.agent_id: r for r in load_group_cell_records(_ref(path))}
    # The capture itself is still known and still attributed.
    assert records["c"].captured is True
    assert records["a"].captor_of == ("c",)
    # But its tick is not -- the match did not end when "c" was captured.
    assert records["c"].capture_tick is None
    assert records["a"].capture_tick_caused is None


def test_capture_unattributed_when_two_deaths_same_cell(tmp_path: Path):
    """Section 13: never infer attribution from aggregate kills alone when
    more than one death occurred -- ambiguous, must stay unattributed."""

    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=90,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=2),
            _entrant("B", "b", alive=False, score=8, termination_reason="normal_halt", deaths=1),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    records = {r.agent_id: r for r in load_group_cell_records(_ref(path))}
    assert records["a"].captor_of == ()
    assert records["c"].captured is True
    # H3 (Beta2 Phase 4.1): two deaths occurred in this cell -- "c"'s own
    # termination_reason is alive-count-driven, but that alone does not
    # prove "c" died at the final tick rather than earlier, since "b" also
    # died. The captured *fact* stays known; the tick must not be guessed.
    assert records["c"].capture_tick is None


def test_multi_death_non_terminal_victim_capture_tick_withheld(tmp_path: Path):
    """H3 (Beta2 Phase 4.1): the independent review's exact reproduction --
    at N>=3, a non-terminal capture (B, at tick 50) must never be reported
    with the final match tick (900, when C's later death actually ended the
    match) just because the match as a whole ended by alive-count. Only the
    provably-terminal death (the only one when total_deaths==1) may trust
    ``ticks`` as its own tick; with two deaths in this cell neither victim's
    timing is provable from Tier-2 evidence, so both must be withheld."""

    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=900,
        winner="A",
        termination_reason="last_agent_standing",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=2),
            _entrant(
                "B", "b", alive=False, score=1,
                termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1,
            ),
            _entrant(
                "C", "c", alive=False, score=5,
                termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1,
            ),
        ],
    )
    records = {r.agent_id: r for r in load_group_cell_records(_ref(path))}
    assert records["b"].captured is True
    assert records["c"].captured is True
    # Neither victim's tick may be fabricated from the final match tick --
    # the earlier, non-terminal death (B, at the real tick 50) must not
    # receive capture_tick=900 (B must NOT receive capture_tick = 900).
    assert records["b"].capture_tick is None
    assert records["c"].capture_tick is None
    # Aggregate kill counts alone cannot say which of the two deaths "a"
    # (kills=2) is credited with landing last -- captor attribution stays
    # unambiguous-only, i.e. unattributed here too.
    assert records["a"].captor_of == ()


def test_single_death_terminal_capture_tick_trusted(tmp_path: Path):
    """H3 (Beta2 Phase 4.1): the narrowed trust rule is not merely more
    conservative everywhere -- when a cell truly has exactly one death (the
    only case Tier-2 evidence can prove is terminal), the tick is still
    reported, at the smallest N this module's own logic operates on (N=2;
    production ``--group`` runs never schedule N=2 -- see
    ``EvaluationService._validate`` -- but ``load_group_cell_records``
    itself is N-generic and this proves its single-death path is intact)."""

    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=80,
        winner="A",
        termination_reason="last_agent_standing",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=1),
            _entrant(
                "B", "b", alive=False, score=5,
                termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1,
            ),
        ],
    )
    ref = _ref(path, roster_agent_ids=("a", "b"), seat_agent_ids=("a", "b"))
    records = {r.agent_id: r for r in load_group_cell_records(ref)}
    assert records["a"].captor_of == ("b",)
    assert records["a"].capture_tick_caused == 80
    assert records["b"].captured is True
    assert records["b"].capture_tick == 80


def test_capture_tick_mean_median_exclude_unknown_values(tmp_path: Path):
    """H3 (Beta2 Phase 4.1): a withheld (None) capture_tick must never be
    treated as 0 or coerced into the final tick for mean/median -- it is
    simply excluded from the sample, same as entrant_summary/interaction_
    matrix already do for any other None evidence field."""

    known = tmp_path / "known.json"
    _write_group_result(
        known,
        ticks=80,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=1),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    unknown = tmp_path / "unknown.json"
    _write_group_result(
        unknown,
        ticks=900,
        winner="A",
        termination_reason="last_agent_standing",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=2),
            _entrant("B", "b", alive=False, score=1, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    records = list(load_group_cell_records(_ref(known, schedule_id="s1")))
    records += list(load_group_cell_records(_ref(unknown, schedule_id="s2")))
    summary = entrant_summary("c", "all", records)
    # Only the "known" cell's tick (80) contributes -- the "unknown" cell's
    # withheld tick is excluded, never averaged in as 0 or 900.
    assert summary.capture_tick_suffered.n == 1
    assert summary.capture_tick_suffered.mean == 80


def test_capture_without_recorded_kill_is_unattributed(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=30,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    records = {r.agent_id: r for r in load_group_cell_records(_ref(path))}
    assert records["a"].captor_of == ()
    assert records["b"].captor_of == ()
    assert records["c"].captured is True


def test_uncaptured_entrant_handled(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=200,
        winner="tie",
        entrants=[
            _entrant("A", "a", alive=True, score=10),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=True, score=10),
        ],
    )
    records = load_group_cell_records(_ref(path))
    assert all(r.captured is False for r in records)
    assert all(r.capture_tick is None for r in records)


def test_interaction_matrix_reports_pair_and_unattributed(tmp_path: Path):
    attributed = tmp_path / "attributed.json"
    _write_group_result(
        attributed,
        ticks=80,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=1),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    ambiguous = tmp_path / "ambiguous.json"
    _write_group_result(
        ambiguous,
        ticks=90,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=2),
            _entrant("B", "b", alive=False, score=8, termination_reason="normal_halt", deaths=1),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    records = list(load_group_cell_records(_ref(attributed, schedule_id="s1")))
    records += list(load_group_cell_records(_ref(ambiguous, schedule_id="s2")))
    matrix = interaction_matrix(records)
    assert matrix.cells_analyzed == 2
    assert len(matrix.pairs) == 1
    pair = matrix.pairs[0]
    assert (pair.captor_agent_id, pair.victim_agent_id) == ("a", "c")
    assert pair.count == 1
    assert pair.rate == 0.5
    assert pair.capture_ticks == (80,)
    assert matrix.unattributed_captures == 1


# ---------------------------------------------------------------------------
# Aggregation: winner/survival/elimination rates, score, territory, kills
# ---------------------------------------------------------------------------


def test_analyze_group_produces_symmetric_summary_for_every_roster_entrant(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=80,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20, kills=1, territory_last=40, territory_max=50, territory_avg=30),
            _entrant("B", "b", alive=True, score=10, territory_last=20, territory_max=25, territory_avg=15),
            _entrant(
                "C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1,
                territory_last=0, territory_max=10, territory_avg=5,
            ),
        ],
    )
    analysis = analyze_group(ROSTER, [_ref(path)])
    assert {s.agent_id for s in analysis.entrant_summaries} == set(ROSTER)
    a_summary = analysis.summary_for("a")
    assert a_summary is not None
    assert a_summary.winner.successes == 1
    assert a_summary.winner.rate == 1.0
    assert a_summary.survival.rate == 1.0
    assert a_summary.score.mean == 20.0
    assert a_summary.territory_retention.mean == 0.8  # 40/50
    b_summary = analysis.summary_for("b")
    assert b_summary is not None
    assert b_summary.winner.rate == 0.0
    assert b_summary.survival.rate == 1.0
    c_summary = analysis.summary_for("c")
    assert c_summary is not None
    assert c_summary.winner.rate == 0.0
    assert c_summary.survival.rate == 0.0
    assert c_summary.elimination.rate == 1.0
    assert c_summary.capture_suffered.rate == 1.0


def test_available_count_excludes_unavailable_cells(tmp_path: Path):
    good = tmp_path / "good.json"
    _write_group_result(
        good, ticks=50, winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=10),
            _entrant("B", "b", alive=True, score=5),
            _entrant("C", "c", alive=True, score=5),
        ],
    )
    refs = [_ref(good, schedule_id="s1"), _ref(None, schedule_id="s2")]
    analysis = analyze_group(ROSTER, refs)
    a_summary = analysis.summary_for("a")
    assert a_summary is not None
    assert a_summary.sample_count == 2
    assert a_summary.available_count == 1
    assert analysis.cells_analyzed == 2
    assert analysis.available_cells == 1


# ---------------------------------------------------------------------------
# Seat / layout / seed sensitivity
# ---------------------------------------------------------------------------


def _cell(schedule_id: str, seats: tuple[str, str, str], winner_agent: str, **kwargs) -> tuple[GroupCellRef, Path]:
    """Build one cell where ``winner_agent`` wins outright and the other two survive."""

    tmp_path: Path = kwargs.pop("tmp_path")
    layout_id = kwargs.pop("layout_id", "spread")
    seed = kwargs.pop("seed", 1)
    path = tmp_path / f"{schedule_id}.json"
    winner_seat = "ABC"[seats.index(winner_agent)]
    entrants = [
        _entrant("ABC"[i], agent_id, alive=True, score=(20 if agent_id == winner_agent else 5))
        for i, agent_id in enumerate(seats)
    ]
    _write_group_result(path, ticks=60, winner=winner_seat, entrants=entrants)
    return _ref(path, schedule_id=schedule_id, seat_agent_ids=seats, layout_id=layout_id, seed=seed), path


def test_seat_sensitivity_range_visible_when_outcome_depends_on_seat(tmp_path: Path):
    ref1, _ = _cell("s1", ("a", "b", "c"), "a", tmp_path=tmp_path)  # a in seat A, a wins
    ref2, _ = _cell("s2", ("b", "a", "c"), "b", tmp_path=tmp_path)  # a in seat B, a does not win
    records = list(load_group_cell_records(ref1)) + list(load_group_cell_records(ref2))
    sensitivity = seat_sensitivity("a", records)
    by_seat = {s.scope_label: s for s in sensitivity.by_seat}
    assert by_seat["A"].winner.rate == 1.0
    assert by_seat["B"].winner.rate == 0.0
    assert sensitivity.winner_rate_range == 1.0


def test_layout_sensitivity_range_visible_when_outcome_depends_on_layout(tmp_path: Path):
    ref1, _ = _cell("s1", ("a", "b", "c"), "a", tmp_path=tmp_path, layout_id="spread")
    ref2, _ = _cell("s2", ("a", "b", "c"), "b", tmp_path=tmp_path, layout_id="close")
    records = list(load_group_cell_records(ref1)) + list(load_group_cell_records(ref2))
    sensitivity = layout_sensitivity("a", records)
    by_layout = {s.scope_label: s for s in sensitivity.by_layout}
    assert by_layout["spread"].winner.rate == 1.0
    assert by_layout["close"].winner.rate == 0.0
    assert sensitivity.winner_rate_range == 1.0


def test_seed_summary_identifies_best_and_worst_seed(tmp_path: Path):
    ref1, _ = _cell("s1", ("a", "b", "c"), "a", tmp_path=tmp_path, seed=1)
    ref2, _ = _cell("s2", ("a", "b", "c"), "b", tmp_path=tmp_path, seed=2)
    records = list(load_group_cell_records(ref1)) + list(load_group_cell_records(ref2))
    summary = seed_summary("a", records)
    assert summary.best_seed == 1
    assert summary.worst_seed == 2
    assert summary.winner_rate_range == 1.0


def test_full_permutation_detail_preserved_alongside_seat_grouping(tmp_path: Path):
    """Section 16: seat grouping must never destroy the underlying
    full-permutation (seat_agent_ids) evidence each record still carries."""

    ref1, _ = _cell("s1", ("a", "b", "c"), "a", tmp_path=tmp_path)
    ref2, _ = _cell("s2", ("a", "c", "b"), "a", tmp_path=tmp_path)
    records = list(load_group_cell_records(ref1)) + list(load_group_cell_records(ref2))
    a_records = [r for r in records if r.agent_id == "a"]
    assert len(a_records) == 2
    assert {r.seat_agent_ids for r in a_records} == {("a", "b", "c"), ("a", "c", "b")}


# ---------------------------------------------------------------------------
# Symmetry and candidate-focused compatibility view
# ---------------------------------------------------------------------------


def test_analyze_group_never_takes_a_candidate_id():
    import inspect

    signature = inspect.signature(analyze_group)
    assert "candidate_id" not in signature.parameters


def test_candidate_focused_view_is_pure_selection(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path,
        ticks=80,
        winner="A",
        entrants=[
            _entrant("A", "a", alive=True, score=20),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=False, score=5, termination_reason=CORE_CAPTURED_TERMINATION_REASON, deaths=1),
        ],
    )
    analysis = analyze_group(ROSTER, [_ref(path)])
    view_a = candidate_focused_view(analysis, "a")
    view_c = candidate_focused_view(analysis, "c")
    assert view_a.candidate is not None
    assert view_a.candidate.agent_id == "a"
    assert view_c.candidate is not None
    assert view_c.candidate.agent_id == "c"
    # Section 21: selecting a different focal entrant must not change any
    # entrant's own underlying numbers -- both views are pure selections
    # over the same symmetric analysis.entrant_summaries.
    assert view_a.candidate.to_json() == analysis.summary_for("a").to_json()
    assert view_c.candidate.to_json() == analysis.summary_for("c").to_json()
    assert {s.agent_id for s in view_a.other_entrants} == {"b", "c"}
    assert {s.agent_id for s in view_c.other_entrants} == {"a", "b"}


# ---------------------------------------------------------------------------
# Sparse data must never crash or produce invalid statistics
# ---------------------------------------------------------------------------


def test_zero_cells_produces_insufficient_data_not_a_crash():
    analysis = analyze_group(ROSTER, [])
    a_summary = analysis.summary_for("a")
    assert a_summary is not None
    assert a_summary.available_count == 0
    assert a_summary.winner.rate is None
    assert a_summary.winner.interval is None
    assert a_summary.score.mean is None


def test_one_cell_produces_a_valid_summary(tmp_path: Path):
    path = tmp_path / "result.json"
    _write_group_result(
        path, ticks=50, winner="tie",
        entrants=[
            _entrant("A", "a", alive=True, score=10),
            _entrant("B", "b", alive=True, score=10),
            _entrant("C", "c", alive=True, score=10),
        ],
    )
    analysis = analyze_group(ROSTER, [_ref(path)])
    assert analysis.interaction_matrix.unattributed_captures == 0
    assert analysis.interaction_matrix.pairs == ()
    for summary in analysis.entrant_summaries:
        assert summary.winner.rate == 0.0
        assert summary.survival.rate == 1.0


def test_all_ties_no_deaths_no_captures_stable(tmp_path: Path):
    refs = []
    for i in range(3):
        path = tmp_path / f"tie-{i}.json"
        _write_group_result(
            path, ticks=200, winner="tie",
            entrants=[
                _entrant("A", "a", alive=True, score=10),
                _entrant("B", "b", alive=True, score=10),
                _entrant("C", "c", alive=True, score=10),
            ],
        )
        refs.append(_ref(path, schedule_id=f"tie-{i}"))
    analysis = analyze_group(ROSTER, refs)
    for summary in analysis.entrant_summaries:
        assert summary.winner.rate == 0.0
        assert summary.capture_caused.rate == 0.0
        assert summary.capture_suffered.trials == 3
        assert summary.capture_suffered.rate == 0.0


def test_missing_optional_evidence_does_not_crash_aggregation(tmp_path: Path):
    refs = [_ref(None, schedule_id="missing-1"), _ref(None, schedule_id="missing-2")]
    analysis = analyze_group(ROSTER, refs)
    assert analysis.available_cells == 0
    for summary in analysis.entrant_summaries:
        assert summary.sample_count == 2
        assert summary.available_count == 0
