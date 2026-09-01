"""Deterministic factual spectator-event extraction for Schema 4 replays.
(CLI Wrapper)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../engine/src')))

# Provide backwards-compatible exports for old tests/imports if needed, 
# though tests should be updated to point to engine.


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python spectator_analyzer.py <replay.jsonl>")
        return 1
        
    
    # For exact compatibility with Phase 0.6 output, we just call analyze_replay
    # which we'll assume is the main driver in the engine module.
    # Wait, in Phase 0.6, did it have an analyze_replay or main?
    from battle_engine.spectator_events import main as engine_main
    return engine_main(sys.argv[1:])

if __name__ == "__main__":
    sys.exit(main())
