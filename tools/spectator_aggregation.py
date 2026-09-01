"""Source-checkout wrapper for permanent spectator aggregation."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_SRC = Path(__file__).resolve().parents[1] / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from battle_engine.spectator_aggregation import (
    AGGREGATION_SCHEMA,
    AGGREGATION_SCHEMA_VERSION,
    DEFAULT_AGGREGATION_CONFIG,
    AggregationConfig,
    TemporalAggregate,
    TemporalAggregateKind,
    aggregate_events,
    aggregate_to_dict,
    serialize_aggregates,
)

__all__ = [
    "AGGREGATION_SCHEMA",
    "AGGREGATION_SCHEMA_VERSION",
    "DEFAULT_AGGREGATION_CONFIG",
    "AggregationConfig",
    "TemporalAggregate",
    "TemporalAggregateKind",
    "aggregate_events",
    "aggregate_to_dict",
    "serialize_aggregates",
]
