"""Source-checkout wrapper for the Phase 7 spectator Director research tool."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_SRC = Path(__file__).resolve().parents[1] / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from battle_engine.spectator_director import (
    DEFAULT_DIRECTOR_CONFIG,
    DEFAULT_SIGNIFICANCE,
    DIRECTOR_SCHEMA,
    DIRECTOR_SCHEMA_VERSION,
    DirectorConfig,
    DirectorDecision,
    DirectorError,
    DirectorMode,
    DirectorPacingState,
    DirectorPlan,
    DirectorReason,
    EventSignificance,
    build_director_plan,
    build_director_plan_from_pair,
    decision_to_dict,
    explain_plan,
    main,
    plan_records,
    serialize_plan,
)

__all__ = [
    "DEFAULT_DIRECTOR_CONFIG",
    "DEFAULT_SIGNIFICANCE",
    "DIRECTOR_SCHEMA",
    "DIRECTOR_SCHEMA_VERSION",
    "DirectorConfig",
    "DirectorDecision",
    "DirectorError",
    "DirectorMode",
    "DirectorPacingState",
    "DirectorPlan",
    "DirectorReason",
    "EventSignificance",
    "build_director_plan",
    "build_director_plan_from_pair",
    "decision_to_dict",
    "explain_plan",
    "main",
    "plan_records",
    "serialize_plan",
]


if __name__ == "__main__":
    raise SystemExit(main())
