"""Source-checkout wrapper for the Phase 3 replay/trace pair analyzer."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_SRC = Path(__file__).resolve().parents[1] / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from battle_engine.spectator_derivation import (
    DERIVATION_SCHEMA,
    DERIVATION_SCHEMA_VERSION,
    PairBinding,
    PairBindingError,
    PairConsistencyError,
    Provenance,
    SpectatorDerivation,
    SpectatorEvent,
    SpectatorEventKind,
    SpectatorPairError,
    analyze_pair,
    derivation_records,
    derive_events,
    event_to_dict,
    explain_derivation,
    main,
    serialize_derivation,
    verify_pair,
)

__all__ = [
    "DERIVATION_SCHEMA",
    "DERIVATION_SCHEMA_VERSION",
    "PairBinding",
    "PairBindingError",
    "PairConsistencyError",
    "Provenance",
    "SpectatorDerivation",
    "SpectatorEvent",
    "SpectatorEventKind",
    "SpectatorPairError",
    "analyze_pair",
    "derivation_records",
    "derive_events",
    "event_to_dict",
    "explain_derivation",
    "main",
    "serialize_derivation",
    "verify_pair",
]


if __name__ == "__main__":
    raise SystemExit(main())
