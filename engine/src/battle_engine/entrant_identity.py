"""Entrant identity: who a competitor is, independent of match or runtime.

This is the v1.5 Phase 5 identity seam
(``docs/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md``): a small,
dependency-free module -- like ``rules.py`` and ``scheduler.py`` before it --
sitting at the bottom of the runtime import graph so both the VM path
(``agent_state.Agent``) and the Python path (``python_runtime.
PythonEntrantState``) can reference the same identity concept without either
importing the other's module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntrantIdentity:
    """Who a competitor is, independent of any one match or execution state.

    Deliberately narrow: ``agent_id`` (the canonical, match-slot-scoped
    identity string already authoritative everywhere in Ruleset v1 -- see
    ``docs/RULES.md``) and ``name`` (a display label, never authoritative for
    anything the engine keys or attributes by). Neither field mutates once a
    match starts, and both remain meaningful whether this entrant is
    resolved onto a VM ``Agent`` or a Python ``PythonEntrantState`` execution
    state.

    What is deliberately *not* here: match-specific resolved participation
    data (slot, start address, loaded VM code, resolved Python spec --
    ``match_service.MatchEntrant``'s job) and mutable execution state (PC,
    registers, liveness, RNG, CPU/write accounting -- ``Agent``'s and
    ``PythonEntrantState``'s job). Runtime kind (``"vm"``/``"python"``) is
    also deliberately excluded -- it is resolved *execution configuration*
    for this match, not something that remains true about the competitor in
    the abstract (see the Phase 5 doc's "What `kind` is, and is not" for the
    full reasoning) -- even though it still participates in deterministic
    match identity at the ``MatchEntrant``/``canonical_match_id`` layer,
    unchanged from before this type existed.
    """

    agent_id: str
    name: str


__all__ = ["EntrantIdentity"]
