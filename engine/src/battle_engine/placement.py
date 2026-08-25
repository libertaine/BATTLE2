"""Deterministic entrant start-address placement for direct native matches.

``bytefray run`` (and, transitively, Agent Designer's Simple/Advanced direct
matches, which invoke the same CLI without ever setting a start address --
see ``battle_engine.launchers.build_designer_match_arguments``) previously
defaulted every omitted ``--a-start``/``--b-start``/``--c-start`` to the
literal integer ``0``. That is a safe, compatible default under Ruleset v1
(no gameplay mechanic depends on the start address at all), but under the
permanent Ruleset v2 identity (``bytefray-rules-2``) every entrant's
``CORE_SIZE``-wide vulnerable core is anchored at its own start address
(``battle_engine.python_runtime.core_addresses``), so defaulting every
omitted start to the same address collapses every entrant's core onto the
same window -- the last entrant seeded owns it, and every earlier entrant is
core-captured before its first action (v2.0.0-rc1's release-blocking
defect).

This module is the one authoritative place that turns a caller's *partial*
knowledge of start addresses (some explicit, some omitted) into the
*complete* set of effective start addresses a match will actually run with.
It is deliberately narrow: GUI-independent, deterministic, and free of any
presentation or persistence concern. It does not validate the result for
overlap -- that is ``battle_engine.match_service.NativeMatchService``'s job
(the one guard every caller, including direct ``MatchRequest`` construction
that bypasses this module entirely, must pass through before any entrant
executes).
"""

from __future__ import annotations

from collections.abc import Sequence

from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V3_ALPHA1_ID,
)

# Which Ruleset identities default an omitted start to a spread seat layout
# rather than to the historical literal ``0``. ``bytefray-rules-2`` is the
# permanent product identity the RC2 fix was written for;
# ``bytefray-rules-3-alpha1`` is added because it inherits the identical
# core mechanic *and* anchors each entrant's locality locus at its start
# address, so collapsing every start to 0 would collapse every locus too.
# Ruleset v1 and every historical alpha identity keep their exact
# historical default.
_SPREAD_START_RULESET_IDS: frozenset[str] = frozenset(
    {BYTEFRAY_RULESET_V2_ID, BYTEFRAY_RULESET_V3_ALPHA1_ID}
)

__all__ = ["resolve_direct_match_starts", "spread_seat_starts"]


def spread_seat_starts(entrant_count: int, arena_size: int) -> tuple[int, ...]:
    """Evenly-spaced seat start addresses, seat 0 anchored at address 0.

    Seat ``i`` starts at ``(i * (arena_size // entrant_count)) % arena_size``
    -- exactly the formula ``agent_evaluation.standard_layouts``'s "spread"
    condition already uses for group-evaluation layouts, extracted here so
    direct-match default placement and group-evaluation layouts share one
    arithmetic source instead of two subtly different ones. For
    ``entrant_count == 2`` this is ``(0, arena_size // 2)`` -- the exact pair
    the governing RC2 task specifies for a 2-entrant arena-512 match.
    """

    if entrant_count < 1:
        raise ValueError(
            f"spread_seat_starts requires at least 1 entrant, got {entrant_count}"
        )
    gap = arena_size // entrant_count
    return tuple((i * gap) % arena_size for i in range(entrant_count))


def resolve_direct_match_starts(
    *,
    ruleset_id: str | None,
    arena_size: int,
    entrant_count: int,
    supplied_starts: Sequence[int | None],
) -> tuple[int, ...]:
    """Resolve effective start addresses for one direct (non-evaluation) match.

    ``supplied_starts`` must have exactly ``entrant_count`` entries, in seat
    order (seat 0 = "A", seat 1 = "B", ...): ``None`` means the caller omitted
    that seat's start, any ``int`` (including explicit ``0``) means the
    caller requested that exact address. This distinction matters -- an
    omitted start and an explicitly requested ``0`` are never conflated.

    Ruleset v1 (``ruleset_id`` ``None`` or the frozen v1 identity) and every
    Ruleset identity other than the permanent Ruleset v2 one (including the
    historical ``bytefray-rules-2-alpha1``/``-alpha11`` identities, whose
    execution semantics this RC2 fix deliberately leaves untouched -- see
    ``docs/V1_5_PHASE3_RULESET_POLICY_DISPATCH.md``'s identity-separation
    rationale): every omitted start resolves to ``0``, exactly the historical
    default this function's introduction does not change for those
    identities.

    The permanent Ruleset v2 identity (``bytefray-rules-2``): every omitted
    start resolves instead to :func:`spread_seat_starts`'s deterministic,
    non-overlapping layout for ``entrant_count`` seats, so a product default
    match no longer collapses every entrant's vulnerable core onto address
    0. Explicit starts are always preserved exactly as supplied, never
    adjusted -- if the final resolved set overlaps, that is a validation
    failure for the caller (``NativeMatchService.run``'s overlap guard) to
    reject, not something this function silently repairs.
    """

    if len(supplied_starts) != entrant_count:
        raise ValueError(
            f"supplied_starts must have exactly {entrant_count} entries, "
            f"got {len(supplied_starts)}"
        )

    if ruleset_id not in _SPREAD_START_RULESET_IDS:
        return tuple(0 if start is None else start for start in supplied_starts)

    defaults = spread_seat_starts(entrant_count, arena_size)
    return tuple(
        defaults[i] if start is None else start
        for i, start in enumerate(supplied_starts)
    )
