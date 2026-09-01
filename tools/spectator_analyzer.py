"""Source-checkout wrapper for permanent spectator-event infrastructure."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_SRC = Path(__file__).resolve().parents[1] / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from battle_engine.spectator_events import (
    SEMANTIC_SCHEMA,
    SEMANTIC_SCHEMA_VERSION,
    SOURCE_SCHEMA,
    SOURCE_SCHEMA_VERSION,
    SemanticEvent,
    SemanticEventKind,
    SpectatorAnalysis,
    SpectatorAnalysisError,
    analysis_records,
    analyze_replay,
    circular_distance,
    main,
    semantic_event_to_dict,
    serialize_analysis,
)

__all__ = [
    "SEMANTIC_SCHEMA",
    "SEMANTIC_SCHEMA_VERSION",
    "SOURCE_SCHEMA",
    "SOURCE_SCHEMA_VERSION",
    "SemanticEvent",
    "SemanticEventKind",
    "SpectatorAnalysis",
    "SpectatorAnalysisError",
    "analysis_records",
    "analyze_replay",
    "circular_distance",
    "main",
    "semantic_event_to_dict",
    "serialize_analysis",
]


if __name__ == "__main__":
    raise SystemExit(main())
