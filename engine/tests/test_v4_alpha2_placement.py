from __future__ import annotations

"""v4 alpha2 qualification: seed-derived, minimum-separated core placement.

Covers the placement half of the alpha2 Ruleset delta
(``docs/V4_ALPHA2_DESIGN.md``): the invariants the rule must hold for every
seed and seat count, the exact deterministic vectors that must agree across
Windows and Linux, and the firewall proving alpha1's historical placement is
untouched by alpha2 existing.
"""

import pytest
from battle_engine.placement import (
    ALPHA2_MIN_CORE_SEPARATION,
    alpha2_min_separation,
    core_placement_mode,
    resolve_direct_match_starts,
    seeded_seat_starts,
    spread_seat_starts,
)
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA1_ID,
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V3_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
)

ARENA_SIZES = (256, 512, 1024)
SEEDS = tuple(range(64))


def _circular_distance(a: int, b: int, arena_size: int) -> int:
    delta = abs(a - b) % arena_size
    return min(delta, arena_size - delta)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arena_size", ARENA_SIZES)
@pytest.mark.parametrize("entrant_count", (2, 3, 4))
def test_same_seed_and_composition_gives_the_same_starts(
    arena_size: int, entrant_count: int
) -> None:
    """The defining reproducibility property: placement is a pure function.

    Repeated within one process here; the cross-platform half of the same
    claim is the pinned vectors below, which a Linux run compares against
    the identical literals.
    """

    for seed in SEEDS:
        first = seeded_seat_starts(entrant_count, arena_size, seed)
        assert first == seeded_seat_starts(entrant_count, arena_size, seed)


def test_placement_is_independent_of_hash_and_iteration_order() -> None:
    """Placement must not move with PYTHONHASHSEED.

    The implementation derives every candidate from SHA-256 over an ASCII
    payload and walks seats by integer index, so there is no set/dict
    iteration or ``hash()`` anywhere on the path. This asserts the
    consequence directly rather than trusting the reading: the vectors below
    are literals, and a build whose placement depended on hash randomization
    would disagree with them on some run of the suite.
    """

    import os
    import subprocess
    import sys

    script = (
        "from battle_engine.placement import seeded_seat_starts;"
        "print([seeded_seat_starts(2, 512, s) for s in range(4)])"
    )
    # Hand the child this process's own import path rather than trusting it to
    # find an installed battle_engine: a source checkout run from a venv that
    # has not installed the package (which is how the Linux qualification
    # environment is set up) reaches it through pytest's rootdir insertion,
    # which a bare subprocess does not inherit.
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(path for path in sys.path if path),
    }
    outputs = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env={**env, "PYTHONHASHSEED": str(value)},
        ).stdout.strip()
        for value in (0, 1, 12345)
    }
    assert len(outputs) == 1
    assert outputs.pop() == str(
        [seeded_seat_starts(2, 512, seed) for seed in range(4)]
    )


# ---------------------------------------------------------------------------
# Deterministic golden vectors (cross-platform contract)
# ---------------------------------------------------------------------------

#: Exact alpha2 placements a conforming build must produce. These are the
#: release-blocking cross-platform contract: a Windows and a Linux build that
#: disagree on any entry here do not run the same Ruleset, and a replay
#: recorded on one cannot be reproduced on the other. Changing a value is
#: changing the Ruleset, never a test-maintenance edit.
ALPHA2_PLACEMENT_VECTORS = {
    (2, 256, 0): (82, 219),
    (2, 256, 1): (24, 162),
    (2, 512, 0): (209, 63),
    (2, 512, 1): (380, 263),
    (2, 512, 7): (324, 167),
    (2, 1024, 0): (238, 503),
    (2, 1024, 42): (721, 912),
    (3, 256, 0): (135, 54, 200),
    (3, 512, 3): (406, 134, 52),
    (4, 1024, 5): (127, 790, 983, 725),
    (8, 1024, 9): (336, 266, 686, 962, 854, 166, 53, 599),
}


def test_pinned_alpha2_placement_vectors() -> None:
    for (entrant_count, arena_size, seed), expected in ALPHA2_PLACEMENT_VECTORS.items():
        assert seeded_seat_starts(entrant_count, arena_size, seed) == expected, (
            entrant_count,
            arena_size,
            seed,
        )


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arena_size", ARENA_SIZES)
@pytest.mark.parametrize("entrant_count", (2, 3, 4, 8))
def test_starts_are_in_bounds_and_never_overlap(
    arena_size: int, entrant_count: int
) -> None:
    separation = alpha2_min_separation(entrant_count, arena_size)
    for seed in SEEDS:
        starts = seeded_seat_starts(entrant_count, arena_size, seed)
        assert len(starts) == entrant_count
        assert all(0 <= start < arena_size for start in starts)
        assert len(set(starts)) == entrant_count
        for i, a in enumerate(starts):
            for b in starts[i + 1 :]:
                assert _circular_distance(a, b, arena_size) >= separation


@pytest.mark.parametrize("arena_size", ARENA_SIZES)
def test_two_entrant_separation_is_the_studied_sixty_four_cells(
    arena_size: int,
) -> None:
    """The production rule must match the Phase 4 condition it inherits.

    Section F2's seeded-placement ecology was measured at a 64-cell minimum
    separation. A production rule that quietly used a different one would
    put that entire measurement out of scope for the shipped Ruleset.
    """

    assert alpha2_min_separation(2, arena_size) == ALPHA2_MIN_CORE_SEPARATION
    for seed in SEEDS:
        a, b = seeded_seat_starts(2, arena_size, seed)
        assert _circular_distance(a, b, arena_size) >= 64


def test_minimum_separation_loosens_only_when_the_arena_cannot_fit_it() -> None:
    """The clamp exists for feasibility and must never tighten the rule."""

    assert alpha2_min_separation(2, 512) == 64
    assert alpha2_min_separation(8, 512) == 64
    # 16 seats at 64 cells needs 1024 cells; a 512-cell arena cannot.
    assert alpha2_min_separation(16, 512) == 32
    assert alpha2_min_separation(64, 512) == 8
    for entrant_count in range(1, 33):
        for arena_size in ARENA_SIZES:
            separation = alpha2_min_separation(entrant_count, arena_size)
            assert 1 <= separation <= ALPHA2_MIN_CORE_SEPARATION
            assert separation * entrant_count <= arena_size or separation == 1


def test_sampling_falls_back_deterministically_instead_of_looping_forever() -> None:
    """An arena too crowded to sample must terminate with the spread layout.

    The guarantee under test is termination plus determinism, not a
    particular layout: an unbounded retry loop would turn an infeasible
    geometry into a hang, and a per-seat fallback would return a layout
    that is neither fully seeded nor fully spread.
    """

    crowded = seeded_seat_starts(64, 128, 3)
    assert crowded == spread_seat_starts(64, 128)
    assert crowded == seeded_seat_starts(64, 128, 3)
    assert crowded == seeded_seat_starts(64, 128, 99), (
        "a fallback layout is seed-independent by construction"
    )


def test_a_single_seat_is_placed_without_a_separation_constraint() -> None:
    for seed in SEEDS[:8]:
        (start,) = seeded_seat_starts(1, 512, seed)
        assert 0 <= start < 512


@pytest.mark.parametrize("entrant_count", (0, -1))
def test_a_non_positive_seat_count_is_rejected(entrant_count: int) -> None:
    with pytest.raises(ValueError, match="at least 1 entrant"):
        seeded_seat_starts(entrant_count, 512, 0)
    with pytest.raises(ValueError, match="at least 1 entrant"):
        alpha2_min_separation(entrant_count, 512)


# ---------------------------------------------------------------------------
# Unpredictability: the whole point of the change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arena_size", ARENA_SIZES)
def test_different_seeds_produce_meaningfully_varied_placement(
    arena_size: int,
) -> None:
    """Alpha2 placement must actually move, not merely be seed-*derived*."""

    layouts = {seeded_seat_starts(2, arena_size, seed) for seed in SEEDS}
    assert len(layouts) >= len(SEEDS) - 1
    firsts = {start for start, _ in layouts}
    # Coverage across the ring, not a narrow band: at least half the
    # 64-cell buckets the arena divides into see a seat-0 placement.
    buckets = {start // 64 for start in firsts}
    assert len(buckets) >= (arena_size // 64) // 2


@pytest.mark.parametrize("arena_size", ARENA_SIZES)
def test_alpha2_does_not_expose_closed_form_opposite_placement(
    arena_size: int,
) -> None:
    """The exact formula Hydra and Nemesis hardcode must stop being valid.

    ``enemy_core == own_core_base + arena_size // 2`` is always exactly true
    under alpha1 and must be true only by coincidence under alpha2. A single
    counterexample would technically satisfy "not generally valid", so this
    asserts the far stronger property the ecology actually depends on: the
    formula is wrong for the overwhelming majority of seeds.
    """

    half = arena_size // 2
    exact = sum(
        (a + half) % arena_size == b
        for a, b in (seeded_seat_starts(2, arena_size, seed) for seed in SEEDS)
    )
    assert exact <= 1
    # And it is not merely *offset*: the miss distance itself varies.
    misses = {
        _circular_distance((a + half) % arena_size, b, arena_size)
        for a, b in (seeded_seat_starts(2, arena_size, seed) for seed in SEEDS)
    }
    assert len(misses) >= len(SEEDS) // 2


# ---------------------------------------------------------------------------
# Ruleset routing, and the alpha1 firewall
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ruleset_id", "expected"),
    [
        (None, "zero"),
        (BYTEFRAY_RULESET_ID, "zero"),
        (BYTEFRAY_RULESET_V2_ALPHA1_ID, "zero"),
        ("bytefray-rules-not-a-real-identity", "zero"),
        (BYTEFRAY_RULESET_V2_ID, "seat_spread"),
        (BYTEFRAY_RULESET_V3_ALPHA1_ID, "seat_spread"),
        (BYTEFRAY_RULESET_V4_ALPHA1_ID, "seat_spread"),
        (BYTEFRAY_RULESET_V4_ALPHA2_ID, "seeded"),
    ],
)
def test_each_ruleset_keeps_its_own_placement_mode(
    ruleset_id: str | None, expected: str
) -> None:
    assert core_placement_mode(ruleset_id) == expected


@pytest.mark.parametrize("arena_size", ARENA_SIZES)
@pytest.mark.parametrize(
    "ruleset_id",
    [
        None,
        BYTEFRAY_RULESET_ID,
        BYTEFRAY_RULESET_V2_ALPHA1_ID,
        BYTEFRAY_RULESET_V2_ID,
        BYTEFRAY_RULESET_V3_ALPHA1_ID,
        BYTEFRAY_RULESET_V4_ALPHA1_ID,
    ],
)
def test_every_pre_alpha2_ruleset_keeps_its_exact_historical_placement(
    ruleset_id: str | None, arena_size: int
) -> None:
    """The placement firewall: alpha2 must be invisible to every other Ruleset.

    Includes passing a ``seed`` these Rulesets ignore, because the seed
    parameter is new and must not be able to perturb a historical layout by
    being present.
    """

    expected = (
        spread_seat_starts(2, arena_size)
        if core_placement_mode(ruleset_id) == "seat_spread"
        else (0, 0)
    )
    assert (
        resolve_direct_match_starts(
            ruleset_id=ruleset_id,
            arena_size=arena_size,
            entrant_count=2,
            supplied_starts=[None, None],
        )
        == expected
    )
    assert (
        resolve_direct_match_starts(
            ruleset_id=ruleset_id,
            arena_size=arena_size,
            entrant_count=2,
            supplied_starts=[None, None],
            seed=999,
        )
        == expected
    )


def test_alpha1_placement_is_the_historical_opposite_pair() -> None:
    """Named separately from the loop above because this exact pair is what
    the alpha1 ecology, its agents, and its persisted corpus all encode."""

    for arena_size in ARENA_SIZES:
        assert resolve_direct_match_starts(
            ruleset_id=BYTEFRAY_RULESET_V4_ALPHA1_ID,
            arena_size=arena_size,
            entrant_count=2,
            supplied_starts=[None, None],
        ) == (0, arena_size // 2)


def test_alpha2_requires_a_seed_rather_than_inventing_one() -> None:
    with pytest.raises(ValueError, match="requires an explicit seed"):
        resolve_direct_match_starts(
            ruleset_id=BYTEFRAY_RULESET_V4_ALPHA2_ID,
            arena_size=512,
            entrant_count=2,
            supplied_starts=[None, None],
        )


def test_explicit_starts_survive_alpha2_placement_untouched() -> None:
    """Reproducing a specific historical layout under alpha2 stays possible.

    Explicit starts have never been adjusted by this resolver, and seeded
    placement must not become the first exception -- otherwise an alpha1
    match could not be re-run under alpha2 semantics for comparison.
    """

    assert resolve_direct_match_starts(
        ruleset_id=BYTEFRAY_RULESET_V4_ALPHA2_ID,
        arena_size=512,
        entrant_count=2,
        supplied_starts=[0, 256],
        seed=7,
    ) == (0, 256)
    # A partially-supplied layout fills only the omitted seat.
    resolved = resolve_direct_match_starts(
        ruleset_id=BYTEFRAY_RULESET_V4_ALPHA2_ID,
        arena_size=512,
        entrant_count=2,
        supplied_starts=[0, None],
        seed=7,
    )
    assert resolved[0] == 0
    assert resolved[1] == seeded_seat_starts(2, 512, 7)[1]


def test_seat_order_is_stable_when_only_the_occupants_swap() -> None:
    """Both seat orientations of one seed share a layout and swap occupants.

    This is what makes a paired both-seat comparison meaningful: seat
    advantage can be measured because the geometry is held fixed while the
    agents trade places, exactly as the Phase 4 orientations did.
    """

    layout = seeded_seat_starts(2, 512, 11)
    assert seeded_seat_starts(2, 512, 11) == layout
    assert layout[0] != layout[1]
