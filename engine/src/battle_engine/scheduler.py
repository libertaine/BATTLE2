"""Shared Ruleset-v1 sequential-quota entrant scheduler.

The VM (``match.MatchRunner``), unsupervised Python
(``python_runtime.PythonEntrantController``), and supervised Python
(``supervised_runtime.SupervisedPythonEntrantController``) execution paths
each drive their entrants/execution-states through the identical shape:
give each live state, in order, up to a fixed per-tick quota of sequential
execution opportunities, stopping early -- for that state only -- the
moment it dies. This module is the one shared implementation of that
shape, replacing three separately maintained copies of it.

It answers only: which execution state receives the next execution
opportunity, in what order, how many opportunities per tick, and when to
stop offering more because the state died. It has no opinion on what an
"execution opportunity" does -- that is entirely up to each runtime's
``execute_slot`` callback (a VM instruction step, a Python ``act()`` call,
a supervised worker round-trip). It does not know about scoring,
statistics, replay, termination, or which runtime it is scheduling.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, TypeVar


class _LivenessCheckable(Protocol):
    alive: bool


StateT = TypeVar("StateT", bound=_LivenessCheckable)


def run_sequential_quota(
    states: Iterable[StateT],
    quota: int,
    execute_slot: Callable[[StateT, int], None],
) -> None:
    """Give each live state in ``states``, in order, up to ``quota`` turns.

    For each state, in iteration order: skip it entirely if it is already
    not alive. Otherwise call ``execute_slot(state, slot)`` once per
    ``slot`` in ``range(quota)``, checking ``state.alive`` again before
    each call and stopping -- without calling ``execute_slot`` again --
    the moment it becomes false. A state that dies partway through its
    quota receives no further opportunities that tick; later states are
    unaffected and still receive their own full quota.
    """

    for state in states:
        if not state.alive:
            continue
        for slot in range(quota):
            if not state.alive:
                break
            execute_slot(state, slot)


def run_interleaved_quota(
    states: Iterable[StateT],
    quota: int,
    execute_slot: Callable[[StateT, int], None],
) -> None:
    """Give each live state in ``states`` up to ``quota`` turns in round-robin interleaved order.

    For each slot in ``range(quota)``, each live entrant in ``states`` executes one action,
    skipping states that are not alive.
    """

    state_list = list(states) if not isinstance(states, list) else states
    for slot in range(quota):
        for state in state_list:
            if not state.alive:
                continue
            execute_slot(state, slot)


__all__ = ["run_interleaved_quota", "run_sequential_quota"]

