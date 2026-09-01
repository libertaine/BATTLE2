"""Minimal deterministic temporal aggregation for factual spectator events."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import pairwise
from typing import Any

from battle_engine.spectator_events import SemanticEvent, SemanticEventKind

AGGREGATION_SCHEMA = "bytefray.spectator_aggregates"
AGGREGATION_SCHEMA_VERSION = 1


class TemporalAggregateKind(str, Enum):
    OVERWRITE_WINDOW = "OVERWRITE_WINDOW"
    RECIPROCAL_OVERWRITE_WINDOW = "RECIPROCAL_OVERWRITE_WINDOW"
    REPEATED_LOCATION_CHURN = "REPEATED_LOCATION_CHURN"
    QUIET_WINDOW = "QUIET_WINDOW"


@dataclass(frozen=True)
class AggregationConfig:
    """Version-1 objective thresholds, explicit so consumers can identify policy."""

    # Bridge one silent tick. This avoids fragmenting a K=2 process cadence
    # into thousands of one-event windows while keeping a two-silent-tick
    # separation factual and visible.
    overwrite_gap_ticks: int = 2
    churn_min_overwrites: int = 4
    quiet_min_ticks: int = 3

    def __post_init__(self) -> None:
        if self.overwrite_gap_ticks < 0:
            raise ValueError("overwrite_gap_ticks must be non-negative")
        if self.churn_min_overwrites < 2:
            raise ValueError("churn_min_overwrites must be at least 2")
        if self.quiet_min_ticks < 1:
            raise ValueError("quiet_min_ticks must be positive")


@dataclass(frozen=True)
class TemporalAggregate:
    kind: TemporalAggregateKind
    start_tick: int
    end_tick: int
    event_count: int
    entrant_ids: tuple[str, ...] = ()
    addresses: tuple[int, ...] = ()


DEFAULT_AGGREGATION_CONFIG = AggregationConfig()


def _overwrite_windows(
    events: Sequence[SemanticEvent], gap_ticks: int
) -> tuple[tuple[SemanticEvent, ...], ...]:
    overwrites = [
        event for event in events if event.kind is SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE
    ]
    if not overwrites:
        return ()

    windows: list[list[SemanticEvent]] = [[overwrites[0]]]
    for event in overwrites[1:]:
        if event.tick - windows[-1][-1].tick <= gap_ticks:
            windows[-1].append(event)
        else:
            windows.append([event])
    return tuple(tuple(window) for window in windows)


def _aggregate_overwrite_window(
    window: Sequence[SemanticEvent], config: AggregationConfig
) -> list[TemporalAggregate]:
    entrant_ids = tuple(
        sorted(
            {
                entrant
                for event in window
                for entrant in (event.previous_owner, event.new_owner)
                if entrant is not None
            }
        )
    )
    addresses = tuple(sorted({event.address for event in window if event.address is not None}))
    aggregates = [
        TemporalAggregate(
            kind=TemporalAggregateKind.OVERWRITE_WINDOW,
            start_tick=window[0].tick,
            end_tick=window[-1].tick,
            event_count=len(window),
            entrant_ids=entrant_ids,
            addresses=addresses,
        )
    ]

    directed_pairs = {
        (event.previous_owner, event.new_owner)
        for event in window
        if event.previous_owner is not None and event.new_owner is not None
    }
    reciprocal_entrants = tuple(
        sorted(
            {
                entrant
                for previous, new in directed_pairs
                if (new, previous) in directed_pairs
                for entrant in (previous, new)
            }
        )
    )
    if reciprocal_entrants:
        aggregates.append(
            TemporalAggregate(
                kind=TemporalAggregateKind.RECIPROCAL_OVERWRITE_WINDOW,
                start_tick=window[0].tick,
                end_tick=window[-1].tick,
                event_count=len(window),
                entrant_ids=reciprocal_entrants,
                addresses=addresses,
            )
        )

    events_by_address: dict[int, list[SemanticEvent]] = {}
    for event in window:
        if event.address is not None:
            events_by_address.setdefault(event.address, []).append(event)
    for address in sorted(events_by_address):
        address_events = events_by_address[address]
        owners = {event.new_owner for event in address_events if event.new_owner is not None}
        if len(address_events) >= config.churn_min_overwrites and len(owners) >= 2:
            aggregates.append(
                TemporalAggregate(
                    kind=TemporalAggregateKind.REPEATED_LOCATION_CHURN,
                    start_tick=address_events[0].tick,
                    end_tick=address_events[-1].tick,
                    event_count=len(address_events),
                    entrant_ids=tuple(sorted(owners)),
                    addresses=(address,),
                )
            )
    return aggregates


def _quiet_windows(
    events: Sequence[SemanticEvent],
    first_tick: int,
    last_tick: int,
    minimum_ticks: int,
) -> list[TemporalAggregate]:
    if last_tick < first_tick:
        raise ValueError("last_tick must not precede first_tick")
    active_ticks = {event.tick for event in events if first_tick <= event.tick <= last_tick}
    quiet: list[TemporalAggregate] = []
    start: int | None = None
    for tick in range(first_tick, last_tick + 1):
        if tick not in active_ticks and start is None:
            start = tick
        if tick in active_ticks and start is not None:
            if tick - start >= minimum_ticks:
                quiet.append(
                    TemporalAggregate(
                        kind=TemporalAggregateKind.QUIET_WINDOW,
                        start_tick=start,
                        end_tick=tick - 1,
                        event_count=0,
                    )
                )
            start = None
    if start is not None and last_tick - start + 1 >= minimum_ticks:
        quiet.append(
            TemporalAggregate(
                kind=TemporalAggregateKind.QUIET_WINDOW,
                start_tick=start,
                end_tick=last_tick,
                event_count=0,
            )
        )
    return quiet


def aggregate_events(
    events: Sequence[SemanticEvent],
    *,
    first_tick: int,
    last_tick: int,
    config: AggregationConfig = DEFAULT_AGGREGATION_CONFIG,
) -> tuple[TemporalAggregate, ...]:
    """Return objective windows without assigning importance or narrative meaning."""

    if any(later.tick < earlier.tick for earlier, later in pairwise(events)):
        raise ValueError("semantic events must be ordered by non-decreasing tick")

    aggregates: list[TemporalAggregate] = []
    for window in _overwrite_windows(events, config.overwrite_gap_ticks):
        aggregates.extend(_aggregate_overwrite_window(window, config))
    aggregates.extend(_quiet_windows(events, first_tick, last_tick, config.quiet_min_ticks))
    kind_order = {
        TemporalAggregateKind.OVERWRITE_WINDOW: 0,
        TemporalAggregateKind.RECIPROCAL_OVERWRITE_WINDOW: 1,
        TemporalAggregateKind.REPEATED_LOCATION_CHURN: 2,
        TemporalAggregateKind.QUIET_WINDOW: 3,
    }
    aggregates.sort(
        key=lambda aggregate: (
            aggregate.start_tick,
            kind_order[aggregate.kind],
            aggregate.end_tick,
            aggregate.addresses,
            aggregate.entrant_ids,
        )
    )
    return tuple(aggregates)


def aggregate_to_dict(aggregate: TemporalAggregate) -> dict[str, Any]:
    return {
        "addresses": list(aggregate.addresses),
        "end_tick": aggregate.end_tick,
        "entrant_ids": list(aggregate.entrant_ids),
        "event_count": aggregate.event_count,
        "kind": aggregate.kind.value,
        "start_tick": aggregate.start_tick,
    }


def serialize_aggregates(aggregates: Sequence[TemporalAggregate]) -> str:
    payload = {
        "aggregates": [aggregate_to_dict(aggregate) for aggregate in aggregates],
        "schema": AGGREGATION_SCHEMA,
        "schema_version": AGGREGATION_SCHEMA_VERSION,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
