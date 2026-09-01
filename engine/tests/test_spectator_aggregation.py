from __future__ import annotations

from battle_engine.spectator_aggregation import (
    AggregationConfig,
    TemporalAggregateKind,
    aggregate_events,
    serialize_aggregates,
)
from battle_engine.spectator_events import SemanticEvent, SemanticEventKind


def _overwrite(
    tick: int,
    previous_owner: str,
    new_owner: str,
    address: int,
) -> SemanticEvent:
    return SemanticEvent(
        tick=tick,
        kind=SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE,
        attacker_entrant_id=new_owner,
        target_entrant_id=previous_owner,
        previous_owner=previous_owner,
        new_owner=new_owner,
        address=address,
    )


def test_overwrite_windows_join_only_within_configured_tick_gap() -> None:
    events = (
        _overwrite(1, "A", "B", 4),
        _overwrite(2, "B", "A", 5),
        _overwrite(4, "A", "B", 6),
    )

    aggregates = aggregate_events(
        events,
        first_tick=0,
        last_tick=4,
        config=AggregationConfig(overwrite_gap_ticks=1),
    )
    windows = [
        aggregate
        for aggregate in aggregates
        if aggregate.kind is TemporalAggregateKind.OVERWRITE_WINDOW
    ]

    assert [(item.start_tick, item.end_tick, item.event_count) for item in windows] == [
        (1, 2, 2),
        (4, 4, 1),
    ]


def test_reciprocal_window_requires_both_overwrite_directions() -> None:
    one_way = (_overwrite(1, "A", "B", 4), _overwrite(2, "A", "B", 5))
    reciprocal = (*one_way, _overwrite(2, "B", "A", 6))

    one_way_result = aggregate_events(one_way, first_tick=0, last_tick=2)
    reciprocal_result = aggregate_events(reciprocal, first_tick=0, last_tick=2)

    assert all(
        aggregate.kind is not TemporalAggregateKind.RECIPROCAL_OVERWRITE_WINDOW
        for aggregate in one_way_result
    )
    summary = next(
        aggregate
        for aggregate in reciprocal_result
        if aggregate.kind is TemporalAggregateKind.RECIPROCAL_OVERWRITE_WINDOW
    )
    assert summary.entrant_ids == ("A", "B")
    assert summary.event_count == 3


def test_repeated_location_churn_has_explicit_count_and_owner_thresholds() -> None:
    events = tuple(
        _overwrite(tick, previous, new, 7)
        for tick, previous, new in (
            (1, "A", "B"),
            (1, "B", "A"),
            (2, "A", "B"),
            (2, "B", "A"),
        )
    )

    aggregates = aggregate_events(events, first_tick=0, last_tick=2)
    churn = next(
        aggregate
        for aggregate in aggregates
        if aggregate.kind is TemporalAggregateKind.REPEATED_LOCATION_CHURN
    )

    assert churn.addresses == (7,)
    assert churn.event_count == 4
    assert churn.entrant_ids == ("A", "B")


def test_three_overwrites_do_not_cross_default_churn_threshold() -> None:
    events = (
        _overwrite(1, "A", "B", 7),
        _overwrite(1, "B", "A", 7),
        _overwrite(2, "A", "B", 7),
    )

    aggregates = aggregate_events(events, first_tick=0, last_tick=2)

    assert all(
        aggregate.kind is not TemporalAggregateKind.REPEATED_LOCATION_CHURN
        for aggregate in aggregates
    )


def test_churn_threshold_is_explicitly_configurable() -> None:
    events = (
        _overwrite(1, "A", "B", 7),
        _overwrite(1, "B", "A", 7),
        _overwrite(2, "A", "B", 7),
    )

    aggregates = aggregate_events(
        events,
        first_tick=0,
        last_tick=2,
        config=AggregationConfig(churn_min_overwrites=3),
    )

    assert any(
        aggregate.kind is TemporalAggregateKind.REPEATED_LOCATION_CHURN for aggregate in aggregates
    )


def test_quiet_windows_are_maximal_and_respect_minimum_duration() -> None:
    events = (
        SemanticEvent(2, SemanticEventKind.DETECTION_GAINED),
        SemanticEvent(7, SemanticEventKind.VICTORY),
    )

    aggregates = aggregate_events(events, first_tick=0, last_tick=10)
    quiet = [
        aggregate
        for aggregate in aggregates
        if aggregate.kind is TemporalAggregateKind.QUIET_WINDOW
    ]

    assert [(item.start_tick, item.end_tick) for item in quiet] == [(3, 6), (8, 10)]


def test_high_density_irrelevant_churn_collapses_without_importance_claim() -> None:
    events = tuple(
        _overwrite(tick // 100, "A" if tick % 2 else "B", "B" if tick % 2 else "A", 15)
        for tick in range(700)
    )

    aggregates = aggregate_events(events, first_tick=0, last_tick=6)

    assert len(events) == 700
    assert [aggregate.kind for aggregate in aggregates] == [
        TemporalAggregateKind.OVERWRITE_WINDOW,
        TemporalAggregateKind.RECIPROCAL_OVERWRITE_WINDOW,
        TemporalAggregateKind.REPEATED_LOCATION_CHURN,
    ]
    assert all(aggregate.event_count == 700 for aggregate in aggregates)


def test_low_density_decisive_facts_remain_factual_not_scored() -> None:
    events = (
        _overwrite(3, "B", "A", 5),
        SemanticEvent(
            3,
            SemanticEventKind.CORE_DISRUPTION,
            attacker_entrant_id="A",
            target_entrant_id="B",
            target_process_id="core",
            address=5,
        ),
        SemanticEvent(
            3,
            SemanticEventKind.AGENT_ELIMINATED,
            entrant_id="B",
            killer_entrant_id="A",
        ),
        SemanticEvent(3, SemanticEventKind.VICTORY, entrant_id="A"),
    )

    aggregates = aggregate_events(events, first_tick=0, last_tick=3)

    assert [aggregate.kind for aggregate in aggregates] == [
        TemporalAggregateKind.QUIET_WINDOW,
        TemporalAggregateKind.OVERWRITE_WINDOW,
    ]
    assert events[-1].kind is SemanticEventKind.VICTORY


def test_aggregate_serialization_is_byte_deterministic() -> None:
    events = (_overwrite(1, "A", "B", 4), _overwrite(1, "B", "A", 4))
    aggregates = aggregate_events(events, first_tick=0, last_tick=3)

    assert serialize_aggregates(aggregates) == serialize_aggregates(aggregates)


def test_tool_wrapper_reexports_permanent_aggregation_contract() -> None:
    from battle_engine import spectator_aggregation as permanent

    from tools import spectator_aggregation as wrapper

    assert wrapper.aggregate_events is permanent.aggregate_events
    assert wrapper.AggregationConfig is permanent.AggregationConfig
    assert wrapper.TemporalAggregate is permanent.TemporalAggregate


def test_events_must_arrive_in_non_decreasing_tick_order() -> None:
    events = (_overwrite(2, "A", "B", 1), _overwrite(1, "B", "A", 1))

    try:
        aggregate_events(events, first_tick=0, last_tick=2)
    except ValueError as exc:
        assert str(exc) == "semantic events must be ordered by non-decreasing tick"
    else:  # pragma: no cover - explicit assertion without pytest dependency
        raise AssertionError("out-of-order semantic events were accepted")
