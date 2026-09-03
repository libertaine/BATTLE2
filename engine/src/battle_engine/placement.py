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

import hashlib
from collections.abc import Sequence

from battle_engine.ruleset_policy import UnknownRulesetError, resolve_ruleset_policy

# v4 alpha2's minimum circular separation between any two entrant core
# base addresses, in cells. 64 is exactly the value the Phase 4 controlled
# gameplay study's seeded-placement condition used
# (docs/V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md Section F2, whose measured
# ecology is the whole evidence base for adopting seeded placement), so the
# production rule and the studied rule agree; changing it would put the
# study's numbers out of scope for the shipped Ruleset.
#
# It is deliberately far larger than the 8-cell core width: the contract
# alpha2 needs is not merely "cores do not overlap" but "an opponent's core
# is not adjacent enough to be found by accident", and 64 cells is 8 core
# widths of genuine search distance even in the smallest arena the study
# covered.
ALPHA2_MIN_CORE_SEPARATION = 64

# The narrowest separation seeded placement will ever fall back to. Equal to
# ``python_runtime.CORE_SIZE``, spelled as its own literal rather than
# imported, because ``placement`` is deliberately a leaf that the runtime
# imports rather than the other way round. Below this, two cores physically
# overlap and no layout -- seeded or spread -- can prevent it; that case is
# left to ``NativeMatchService``'s existing overlap guard to reject with its
# own diagnostic rather than invented into a second, competing error here.
_MIN_FEASIBLE_SEPARATION = 8

# How many seed-derived candidates one seat may draw before seeded placement
# abandons sampling for its deterministic fallback layout. Bounded on
# purpose: an unbounded retry loop would turn an infeasible
# separation/arena/entrant-count combination into a hang instead of a
# result. With the separation clamped for feasibility below, a seat's draw
# succeeds on its first candidate in the overwhelming majority of cases;
# this ceiling is a guarantee of termination, not an expected code path.
_MAX_PLACEMENT_DRAWS_PER_SEAT = 64


__all__ = [
    "ALPHA2_MIN_CORE_SEPARATION",
    "alpha2_min_separation",
    "core_placement_mode",
    "resolve_direct_match_starts",
    "seeded_seat_starts",
    "spread_seat_starts",
]


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


def alpha2_min_separation(entrant_count: int, arena_size: int) -> int:
    """The minimum circular core separation seeded placement enforces here.

    :data:`ALPHA2_MIN_CORE_SEPARATION` is the rule; this is the rule made
    *feasible* for one specific arena and seat count. ``entrant_count`` cores
    each at least ``s`` cells from every other need ``entrant_count * s <=
    arena_size`` to fit around the ring at all, so the declared 64-cell
    minimum is clamped to ``arena_size // entrant_count`` whenever a match
    is too crowded to honor it. The clamp only ever *loosens* the
    requirement, never tightens it, and is a pure function of the two
    arguments -- so it stays as deterministic and platform-independent as the
    sampling it governs.

    The result is floored at 1 rather than at
    :data:`_MIN_FEASIBLE_SEPARATION`: an arena too small to keep
    ``entrant_count`` 8-cell cores apart cannot be rescued by any layout, and
    ``NativeMatchService``'s overlap guard already rejects that composition
    with a diagnostic naming the real problem. Returning a separation this
    function knows to be unsatisfiable would only substitute a confusing
    fallback layout for that clear error.
    """

    if entrant_count < 1:
        raise ValueError(
            f"alpha2_min_separation requires at least 1 entrant, got {entrant_count}"
        )
    return max(1, min(ALPHA2_MIN_CORE_SEPARATION, arena_size // entrant_count))


def _placement_draw(
    *,
    seed: int,
    arena_size: int,
    entrant_count: int,
    separation: int,
    seat: int,
    attempt: int,
) -> int:
    """One uniform seed-derived candidate address for ``seat``.

    Deliberately a pure SHA-256 counter stream rather than anything from
    :mod:`random`. ``random.Random`` seeded from the same bytes would be
    reproducible *today*, but only ``random.random()``'s sequence is
    documented as stable across Python versions -- ``randrange``/
    ``getrandbits`` are explicitly not -- and alpha2 placement determinism is
    a cross-platform, cross-version release requirement (a Windows/Linux or
    3.10/3.13 disagreement here would silently change match outcomes and
    invalidate a replay). SHA-256 of an ASCII payload is fully specified by
    its standard: identical bytes in, identical bytes out, on every platform
    and every supported Python.

    The payload is domain-separated by a fixed ``"bytefray-rules-4-alpha2:
    placement:"`` namespace label so no other seed-derived quantity in the
    engine (``derive_agent_seed``, the VM's own seeding) can ever collide
    with it, and includes every input that changes the layout -- arena
    size, seat count, and the effective separation -- so two matches
    differing in any of them draw independent streams rather than sharing a
    prefix.

    v4.0.0-rc1 Phase 2: this namespace label is a fixed constant, not the
    *currently executing* Ruleset's own id -- it was never parameterized by
    a ``ruleset_id`` argument, and deliberately keeps its original alpha2
    spelling forever, unrenamed, now that the permanent stable identity
    (``bytefray-rules-4``) also selects ``core_placement="seeded"`` and
    reaches this exact function. Renaming it to track whichever Ruleset id
    triggered the call would silently change *every* seeded placement draw
    for identical ``(seed, arena_size, entrant_count)`` inputs the moment a
    caller's Ruleset id differed -- exactly the "resolved starting
    positions" identity the stable-v4 promotion must keep byte-identical to
    alpha2 (docs/research/v4/V4_RC1_PHASE2_STABLE_CONTRACT_PROMOTION.md
    Sec D). Its only job is domain separation from the engine's other
    seed-derived streams, and it already accomplishes that with a fixed
    string. See ``resolve_direct_match_starts``'s own docstring for the
    full "which Rulesets reach this function" list.

    ``% arena_size`` over a 64-bit draw carries a modulo bias below
    ``arena_size / 2**64``; for any arena this engine supports that is on the
    order of 2**-53, far beneath the point where it could influence an
    ecology measurement, and it is preferred to a rejection loop because it
    is branch-free and therefore trivially identical everywhere.
    """

    payload = (
        "bytefray-rules-4-alpha2:placement:"
        f"{seed}:{arena_size}:{entrant_count}:{separation}:{seat}:{attempt}"
    )
    digest = hashlib.sha256(payload.encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") % arena_size


def _circular_distance(a: int, b: int, arena_size: int) -> int:
    delta = abs(a - b) % arena_size
    return min(delta, arena_size - delta)


def seeded_seat_starts(
    entrant_count: int, arena_size: int, seed: int
) -> tuple[int, ...]:
    """v4 alpha2's seed-derived, minimum-separated seat start addresses.

    The production form of the Phase 4 study's ``seeded_starts`` condition
    (docs/V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md Section F2): the same placement
    *model* -- uniform candidate addresses drawn from the match seed,
    rejection-sampled until every pair of cores is at least
    :func:`alpha2_min_separation` cells apart -- generalized from that
    study's two entrants to any seat count, and re-expressed over a SHA-256
    counter stream so the result is byte-identical on every platform and
    every supported Python version (see :func:`_placement_draw`).

    Seats are placed in seat order, each drawn against the seats already
    placed, so seat ``i``'s address depends only on ``seed``, ``arena_size``,
    ``entrant_count`` and the seats before it -- never on dict/set iteration
    order, agent identity, or anything a caller could vary without also
    varying the recorded match inputs. Swapping which *agent* occupies which
    seat therefore keeps the layout fixed and swaps the occupants, exactly as
    the study's paired both-seat orientations did.

    **Fallback.** If any seat exhausts :data:`_MAX_PLACEMENT_DRAWS_PER_SEAT`
    candidates without satisfying the separation, the whole layout -- not
    just the failing seat -- falls back to :func:`spread_seat_starts`. A
    whole-layout fallback keeps the result internally consistent (never a
    half-seeded, half-spread hybrid whose separation guarantee is neither one
    thing nor the other) and keeps the function total: it always terminates,
    and always returns a layout exactly as separated as the arena
    geometrically permits.
    """

    if entrant_count < 1:
        raise ValueError(
            f"seeded_seat_starts requires at least 1 entrant, got {entrant_count}"
        )
    separation = alpha2_min_separation(entrant_count, arena_size)
    placed: list[int] = []
    for seat in range(entrant_count):
        for attempt in range(_MAX_PLACEMENT_DRAWS_PER_SEAT):
            candidate = _placement_draw(
                seed=seed,
                arena_size=arena_size,
                entrant_count=entrant_count,
                separation=separation,
                seat=seat,
                attempt=attempt,
            )
            if all(
                _circular_distance(candidate, other, arena_size) >= separation
                for other in placed
            ):
                placed.append(candidate)
                break
        else:
            return spread_seat_starts(entrant_count, arena_size)
    return tuple(placed)


def core_placement_mode(ruleset_id: str | None) -> str:
    """The placement mode ``ruleset_id`` declares, failing safe to ``"zero"``.

    ``None`` (no Ruleset selected) and any unregistered identity keep the
    historical literal-``0`` default rather than raising: this module has
    never been the place an unknown Ruleset is rejected, and
    ``resolve_ruleset_policy``'s own fail-closed error already fires later,
    from ``NativeMatchService``, before any entrant executes.
    """

    if ruleset_id is None:
        return "zero"
    try:
        return resolve_ruleset_policy(ruleset_id).core_placement
    except UnknownRulesetError:
        return "zero"


def resolve_direct_match_starts(
    *,
    ruleset_id: str | None,
    arena_size: int,
    entrant_count: int,
    supplied_starts: Sequence[int | None],
    seed: int | None = None,
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

    The v4 alpha2 identity (``bytefray-rules-4-alpha2``) and, since
    v4.0.0-rc1 Phase 2, its permanent stable promotion (``bytefray-rules-4``):
    every omitted start resolves instead to :func:`seeded_seat_starts`'s
    seed-derived, minimum-separated layout, which is alpha2's defining
    gameplay change, carried into the stable identity unmodified. ``seed``
    is therefore **required** for either Ruleset and raises ``ValueError``
    if omitted -- silently substituting a default seed would make every
    such match share one layout, which is precisely the predictability
    alpha2 exists to remove. It is ignored for every other Ruleset, so no
    existing caller's behavior changes by not passing it. Both identities
    resolve to byte-identical addresses for identical ``(seed, arena_size,
    entrant_count)`` inputs -- :func:`_placement_draw`'s domain-separation
    payload is a fixed constant, never the specific Ruleset id, precisely
    so this equivalence holds without a second placement implementation.

    Which Ruleset gets which layout is read from the Ruleset's own
    :attr:`~battle_engine.ruleset_policy.RulesetPolicy.core_placement`
    declaration rather than from a table kept here, so placement is one of
    the semantics a Ruleset *states*, and a new Ruleset cannot acquire a
    placement rule by being forgotten in this module.
    """

    if len(supplied_starts) != entrant_count:
        raise ValueError(
            f"supplied_starts must have exactly {entrant_count} entries, "
            f"got {len(supplied_starts)}"
        )

    mode = core_placement_mode(ruleset_id)
    if mode == "zero":
        return tuple(0 if start is None else start for start in supplied_starts)

    if mode == "seeded":
        if seed is None:
            raise ValueError(
                f"Ruleset {ruleset_id!r} places entrant cores from the match "
                "seed; resolve_direct_match_starts requires an explicit seed."
            )
        defaults = seeded_seat_starts(entrant_count, arena_size, seed)
    else:
        defaults = spread_seat_starts(entrant_count, arena_size)

    return tuple(
        defaults[i] if start is None else start
        for i, start in enumerate(supplied_starts)
    )
