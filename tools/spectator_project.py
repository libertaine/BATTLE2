"""Source-checkout wrapper for Phase 4 entrant-perspective projection."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_SRC = Path(__file__).resolve().parents[1] / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from battle_engine.spectator_perspective import (
    PERSPECTIVE_SCHEMA,
    PERSPECTIVE_SCHEMA_VERSION,
    CallbackPoint,
    ContactKnowledge,
    DeclaredProcess,
    KnowledgeStatus,
    OwnProcessKnowledge,
    PerspectiveConsistencyError,
    PerspectiveError,
    PerspectiveFrame,
    PerspectiveProjection,
    PerspectiveState,
    ReadKnowledge,
    TickBoundary,
    analyze_perspective,
    explain_state,
    frame_to_dict,
    main,
    project_perspective,
    projection_records,
    serialize_projection,
    serialize_state,
    state_to_dict,
)

__all__ = [
    "PERSPECTIVE_SCHEMA",
    "PERSPECTIVE_SCHEMA_VERSION",
    "CallbackPoint",
    "ContactKnowledge",
    "DeclaredProcess",
    "KnowledgeStatus",
    "OwnProcessKnowledge",
    "PerspectiveConsistencyError",
    "PerspectiveError",
    "PerspectiveFrame",
    "PerspectiveProjection",
    "PerspectiveState",
    "ReadKnowledge",
    "TickBoundary",
    "analyze_perspective",
    "explain_state",
    "frame_to_dict",
    "main",
    "project_perspective",
    "projection_records",
    "serialize_projection",
    "serialize_state",
    "state_to_dict",
]


if __name__ == "__main__":
    raise SystemExit(main())
