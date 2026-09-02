"""Phase 8: deterministic Fight Night presentation plans.

Like the Phase 7 Director tests, every assertion here is checked against a
real ``NativeMatchService`` run's replay/trace pair. The disclosure tests in
particular always prove their precondition from the artifacts first (for
example, that a given entrant is delivered zero events for the whole match)
before asserting anything about what the ribbon shows, so a passing test is
evidence about a real execution rather than about a convenient fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1
from battle_engine.spectator_derivation import (
    SpectatorDerivation,
    SpectatorEventKind,
    analyze_pair,
)
from battle_engine.spectator_fight_night import (
    RIBBON_LABELS,
    FightNightConfig,
    FightNightError,
    FightNightMode,
    build_fight_night_plan,
)

_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

HERMIT = _IMPORTS + '''
class Hermit:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="h", reach=1, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, obs.self_anchor)
def create_agent() -> AgentV2:
    return Hermit()
'''

HUNTER = _IMPORTS + '''
class Hunter:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="hunt", reach=20, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.target = None
        self.step = 0
    def act(self, obs: ObservationV2) -> AgentAction:
        if obs.visible_enemy_anchor_addresses:
            self.target = obs.visible_enemy_anchor_addresses[0]
        if self.target is None:
            return AgentAction(ActionKindV2.MOVE, 3)
        delta = self.target - obs.self_anchor
        if delta > 2:
            return AgentAction(ActionKindV2.MOVE, 2)
        if delta < -2:
            return AgentAction(ActionKindV2.MOVE, -2)
        self.step += 1
        return AgentAction(ActionKindV2.WRITE, self.target + (self.step % 8), 0x22)
def create_agent() -> AgentV2:
    return Hunter()
'''

# Walks to a fixed absolute address, parks there, and claims the cell it is
# standing on. Two of these with the same target genuinely co-locate their
# process anchors mid-match while their seeded cores stay far apart (the
# ruleset forbids overlapping cores). Claiming the destination is what makes
# it an *owned* cell, so a third entrant reading that address produces a real
# HOSTILE_READ with a resolved owner -- the READ-owner-separation fixture.
MEETER = _IMPORTS + '''
class Meeter:
    api_version = 2
    TARGET = 100
    def declare_processes(self):
        return [ProcessDeclaration(id="m", reach=1, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.n = 0
    def act(self, obs: ObservationV2) -> AgentAction:
        delta = self.TARGET - obs.self_anchor
        if delta > 0:
            return AgentAction(ActionKindV2.MOVE, min(2, delta))
        if delta < 0:
            return AgentAction(ActionKindV2.MOVE, max(-2, delta))
        self.n += 1
        return AgentAction(ActionKindV2.WRITE, obs.self_anchor, 0x30 + (self.n % 8))
def create_agent() -> AgentV2:
    return Meeter()
'''

# Sits still with a wide sensor and READs whatever anchor it is shown, which
# produces real HOSTILE_READ/FIRST_HOSTILE_READ events with a known owner --
# the READ-owner-separation fixture.
PROBE = _IMPORTS + '''
class Probe:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="eye", reach=30, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        if obs.visible_enemy_anchor_addresses:
            return AgentAction(ActionKindV2.READ, obs.visible_enemy_anchor_addresses[0])
        return AgentAction(ActionKindV2.READ, obs.self_anchor)
def create_agent() -> AgentV2:
    return Probe()
'''

_SOURCES = {"hermit": HERMIT, "hunter": HUNTER, "meeter": MEETER, "probe": PROBE}


def _write_agent(root: Path, name: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.py").write_text(_SOURCES[name])
    (directory / "agent.yaml").write_text(
        f"name: {name}\ndescription: Phase 8 fixture\nversion: '1.0'\napi_version: 2\n"
    )


def _run(
    root: Path,
    label: str,
    entrants: tuple[tuple[str, str, str, int], ...],
    *,
    arena_size: int,
    max_ticks: int,
    seed: int,
) -> SpectatorDerivation:
    """Run one real match and return its derived event stream.

    ``entrants`` is ``((entrant_id, display_name, agent_source_name, start), ...)``.
    """

    for _entrant_id, _name, agent_name, _start in entrants:
        _write_agent(root, agent_name)
    run = root / label
    run.mkdir(parents=True, exist_ok=True)
    replay_path = run / "replay.jsonl"
    trace_path = run / "trace.jsonl"
    NativeMatchService().run(
        MatchRequest(
            config=Config(
                seed=seed,
                arena_size=arena_size,
                instr_per_tick=8,
                win_mode="capture",
                weights=Weights(),
            ),
            entrants=tuple(
                MatchEntrant.python(entrant_id, name, start, resolve_agent(root, agent_name))
                for entrant_id, name, agent_name, start in entrants
            ),
            max_ticks=max_ticks,
            replay_path=replay_path,
            trace_path=trace_path,
            ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
        )
    )
    return analyze_pair(replay_path, trace_path)


def _two(root: Path) -> SpectatorDerivation:
    return _run(
        root,
        "fn2",
        (("A", "Entrant A", "hunter", 0), ("B", "Entrant B", "hermit", 40)),
        arena_size=200,
        max_ticks=60,
        seed=5,
    )


def _three_pair_plus_blind(root: Path) -> SpectatorDerivation:
    return _run(
        root,
        "fn3",
        (
            ("A", "Entrant A", "hunter", 0),
            ("B", "Entrant B", "hermit", 40),
            ("C", "Entrant C", "hermit", 300),
        ),
        arena_size=400,
        max_ticks=80,
        seed=11,
    )


def _four_two_fights(root: Path) -> SpectatorDerivation:
    return _run(
        root,
        "fn4",
        (
            ("A", "Entrant A", "hunter", 0),
            ("B", "Entrant B", "hermit", 30),
            ("C", "Entrant C", "hunter", 200),
            ("D", "Entrant D", "hermit", 230),
        ),
        arena_size=400,
        max_ticks=90,
        seed=31,
    )


def _four_three_way(root: Path) -> SpectatorDerivation:
    return _run(
        root,
        "fn4x",
        (
            ("A", "Entrant A", "hunter", 0),
            ("B", "Entrant B", "hunter", 40),
            ("C", "Entrant C", "hunter", 80),
            ("D", "Entrant D", "hermit", 350),
        ),
        arena_size=480,
        max_ticks=90,
        seed=37,
    )


def _colocated(root: Path) -> SpectatorDerivation:
    """B and C converge onto one address while A watches from a distance."""

    return _run(
        root,
        "fnco",
        (
            ("A", "Entrant A", "probe", 80),
            ("B", "Entrant B", "meeter", 40),
            ("C", "Entrant C", "meeter", 160),
        ),
        arena_size=200,
        max_ticks=70,
        seed=23,
    )


# ---------------------------------------------------------------------------
# 1. Plan construction and validation
# ---------------------------------------------------------------------------


def test_plan_fingerprint_is_identical_across_repeated_builds(tmp_path: Path) -> None:
    derivation = _two(tmp_path)
    first = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    second = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    assert first.ribbon_entries == second.ribbon_entries
    assert first.plan_fingerprint() == second.plan_fingerprint()


def test_invalid_mode_entrant_combinations_are_rejected(tmp_path: Path) -> None:
    derivation = _two(tmp_path)
    with pytest.raises(FightNightError):
        build_fight_night_plan(derivation, mode=FightNightMode.PERSPECTIVE)
    with pytest.raises(FightNightError):
        build_fight_night_plan(
            derivation, mode=FightNightMode.PERSPECTIVE, entrant_id="ZZ"
        )
    with pytest.raises(FightNightError):
        build_fight_night_plan(
            derivation, mode=FightNightMode.BROADCAST, entrant_id="A"
        )


@pytest.mark.parametrize("builder", [_two, _three_pair_plus_blind, _four_two_fights])
def test_presentation_state_is_produced_for_two_three_and_four_entrants(
    builder, tmp_path: Path
) -> None:
    """The plan is entrant-count generic (Sec. 15's 2/3/4 requirement)."""

    derivation = builder(tmp_path)
    plan = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)

    assert plan.entrants == derivation.binding.entrant_identities
    assert len(plan.ribbon_cursor) == derivation.last_tick - derivation.first_tick + 1
    # Every match ends, so every plan carries at least the terminal entry, and
    # the result card's own facts come straight off the canonical result.
    assert plan.ribbon_entries
    assert plan.winner == derivation.winner
    assert plan.termination_reason == derivation.termination_reason
    assert plan.is_result_tick(derivation.result_ticks)
    assert not plan.is_result_tick(derivation.result_ticks - 1)


# ---------------------------------------------------------------------------
# 2. Never names a second party
# ---------------------------------------------------------------------------


def test_no_ribbon_entry_ever_names_more_than_one_entrant(tmp_path: Path) -> None:
    """The hard rule from the module docstring, checked on real matches.

    ``subject`` is a single optional id, so the structural guarantee is that
    there is nowhere to put a counterparty. The observable consequence is
    asserted too, and deliberately *not* by substring-searching the label for
    entrant ids -- single-letter ids like "C" occur inside ordinary words such
    as "CONTACT", which would make such a check both noisy and meaningless.
    The real property is stronger and exact: every label is one of the fixed
    constants in ``RIBBON_LABELS``, so no entrant id can be interpolated into
    a label at all, by any code path.
    """

    permitted_labels = {label for label, _role in RIBBON_LABELS.values()}
    for builder in (_two, _three_pair_plus_blind, _four_two_fights, _colocated):
        derivation = builder(tmp_path)
        roster = set(derivation.binding.entrant_identities)
        for mode_entrant in (None, *sorted(roster)):
            mode = (
                FightNightMode.BROADCAST
                if mode_entrant is None
                else FightNightMode.PERSPECTIVE
            )
            plan = build_fight_night_plan(
                derivation, mode=mode, entrant_id=mode_entrant
            )
            # Only Broadcast is guaranteed non-empty. A Perspective ribbon may
            # legitimately be empty -- a blind entrant is told nothing, which
            # is the point (see the disclosure tests below) -- so requiring
            # entries here would assert the opposite of the desired behaviour.
            if mode_entrant is None:
                assert plan.ribbon_entries
            for entry in plan.ribbon_entries:
                assert entry.subject is None or entry.subject in roster
                assert entry.label in permitted_labels


def test_read_owner_never_becomes_an_opponent_identity(tmp_path: Path) -> None:
    """Sec. 38's READ-owner separation, carried into presentation.

    A ``FIRST_HOSTILE_READ`` factually records both the reader and the owner
    of the cell it sampled. The ribbon presents only the reader: the cell's
    owner is a fact about a *memory address*, never about the anonymous
    spatial contact the reader can also see, and joining the two is exactly
    what the Phase 4 spec forbids.
    """

    derivation = _colocated(tmp_path)
    reads = [
        event
        for event in derivation.events
        if event.kind is SpectatorEventKind.FIRST_HOSTILE_READ
    ]
    # The fixture really did produce hostile reads with a resolved owner.
    assert reads
    assert any(event.targets for event in reads)

    plan = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    read_entries = [
        entry
        for entry in plan.ribbon_entries
        if entry.source_kind is SpectatorEventKind.FIRST_HOSTILE_READ
    ]
    assert read_entries
    for entry in read_entries:
        source = next(
            event
            for event in reads
            if (event.tick, event.sequence) == (entry.tick, entry.sequence)
        )
        assert entry.subject == source.actors[0]
        assert entry.subject not in source.targets


def test_colocated_entrants_are_not_associated_through_the_ribbon(
    tmp_path: Path,
) -> None:
    """Sec. 37: two enemies at one address must stay unassociated.

    From the observer's own Perspective, nothing in its ribbon may connect
    the single anonymous contact it was shown to either of the two entrants
    actually standing there.
    """

    derivation = _colocated(tmp_path)
    # Precondition: B and C really do share an address at some point, and A
    # really is shown an anchor there.
    contacts = [
        event
        for event in derivation.events
        if event.kind is SpectatorEventKind.DETECTION_GAINED and "A" in event.visible_to
    ]
    assert contacts

    # B and C really are anchored at the same address at some point, so the
    # single anonymous contact A is shown genuinely covers two entrants.
    assert any(
        event.kind is SpectatorEventKind.HOSTILE_WRITE
        and set(event.actors) | set(event.targets) == {"B", "C"}
        for event in derivation.events
    )

    plan = build_fight_night_plan(
        derivation, mode=FightNightMode.PERSPECTIVE, entrant_id="A"
    )
    assert plan.ribbon_entries
    # A's own ribbon names A (its own actions) and nobody else -- neither of
    # the two entrants standing at the address it can see.
    assert {entry.subject for entry in plan.ribbon_entries} <= {None, "A"}


def test_contact_label_is_unattributed(tmp_path: Path) -> None:
    """``DETECTION_GAINED`` presents as a bare "CONTACT" about the observer.

    The v4 engine hands an observer occupied enemy *addresses* and never says
    whose they are, so the ribbon must not imply a counterparty. The label is
    pinned exactly, and the subject is asserted to be the observer rather
    than anyone observed.
    """

    label, _role = RIBBON_LABELS[SpectatorEventKind.DETECTION_GAINED]
    assert label == "CONTACT"

    derivation = _four_two_fights(tmp_path)
    plan = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    detections = [
        entry
        for entry in plan.ribbon_entries
        if entry.source_kind is SpectatorEventKind.DETECTION_GAINED
    ]
    assert detections
    for entry in detections:
        source = next(
            event
            for event in derivation.events
            if (event.tick, event.sequence) == (entry.tick, entry.sequence)
        )
        assert entry.subject == source.actors[0]
        assert source.visible_to == (entry.subject,)


# ---------------------------------------------------------------------------
# 3. Perspective disclosure
# ---------------------------------------------------------------------------


def test_a_blind_entrant_sees_an_empty_ribbon(tmp_path: Path) -> None:
    """Sec. 36's negative regression on a real three-entrant match.

    C is 260 cells from a genuine core capture and is delivered nothing. Its
    Fight Night ribbon must therefore stay empty for the whole match, while
    Broadcast's ribbon on the same match is full of the events C cannot know.
    """

    derivation = _three_pair_plus_blind(tmp_path)
    assert [event for event in derivation.events if "C" in event.visible_to] == []

    broadcast = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    blind = build_fight_night_plan(
        derivation, mode=FightNightMode.PERSPECTIVE, entrant_id="C"
    )

    assert blind.ribbon_entries == ()
    for tick in range(derivation.first_tick, derivation.last_tick + 1):
        assert blind.ribbon_at_tick(tick) == ()

    # The events being withheld are real and are exactly the omniscient-only
    # kinds Phase 3 identified -- not an empty match.
    hidden = {
        entry.source_kind
        for entry in broadcast.ribbon_entries
        if entry.source_kind
        in {
            SpectatorEventKind.CORE_CELL_LOST,
            SpectatorEventKind.PROCESS_DISRUPTED,
            SpectatorEventKind.AGENT_ELIMINATED,
        }
    }
    assert hidden


def test_hidden_core_damage_and_disruption_never_reach_a_perspective_ribbon(
    tmp_path: Path,
) -> None:
    """No entrant's own ribbon may carry an omniscient-only fact.

    Checked for every entrant of a heavy four-entrant match: the eight
    omniscient-only kinds have an empty ``visible_to`` by construction, so a
    Perspective plan built from the filtered stream can never contain one.
    This asserts that end-to-end rather than trusting the filter.
    """

    derivation = _four_three_way(tmp_path)
    omniscient_only = {
        SpectatorEventKind.HOSTILE_WRITE,
        SpectatorEventKind.FIRST_HOSTILE_WRITE,
        SpectatorEventKind.CORE_CELL_LOST,
        SpectatorEventKind.PROCESS_DISRUPTED,
        SpectatorEventKind.AGENT_ELIMINATED,
        SpectatorEventKind.AGENT_FORFEITED,
        SpectatorEventKind.MATCH_ENDED,
        SpectatorEventKind.VICTORY,
    }
    # The match really does contain these facts in quantity.
    present = {event.kind for event in derivation.events} & omniscient_only
    assert len(present) >= 3

    for entrant in derivation.binding.entrant_identities:
        plan = build_fight_night_plan(
            derivation, mode=FightNightMode.PERSPECTIVE, entrant_id=entrant
        )
        assert not any(
            entry.source_kind in omniscient_only for entry in plan.ribbon_entries
        )

    broadcast = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    assert any(
        entry.source_kind in omniscient_only for entry in broadcast.ribbon_entries
    )


def test_perspective_plans_state_their_information_domain(tmp_path: Path) -> None:
    """Every plan says which domain produced it, so chrome can label itself."""

    derivation = _four_two_fights(tmp_path)
    assert (
        build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST).visibility_basis
        == "broadcast"
    )
    for entrant in derivation.binding.entrant_identities:
        plan = build_fight_night_plan(
            derivation, mode=FightNightMode.PERSPECTIVE, entrant_id=entrant
        )
        assert plan.visibility_basis == f"perspective:{entrant}"


# ---------------------------------------------------------------------------
# 4. Flood control
# ---------------------------------------------------------------------------


def test_repetitive_hostile_traffic_does_not_flood_the_ribbon(tmp_path: Path) -> None:
    """Sec. 19: a burst of repeated events must not become a burst of entries.

    The four-entrant three-way fixture derives hundreds of ``HOSTILE_WRITE``
    and ``PROCESS_DISRUPTED`` events. Ordinary hostile writes are excluded
    from the ribbon vocabulary outright, and repeated disruptions of the same
    entrant collapse under the repeat cooldown.
    """

    derivation = _four_three_way(tmp_path)
    writes = sum(
        1 for e in derivation.events if e.kind is SpectatorEventKind.HOSTILE_WRITE
    )
    disruptions = sum(
        1 for e in derivation.events if e.kind is SpectatorEventKind.PROCESS_DISRUPTED
    )
    assert writes > 100
    assert disruptions > 50

    plan = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)

    # Ordinary hostile writes are not ribbon vocabulary at all.
    assert SpectatorEventKind.HOSTILE_WRITE not in RIBBON_LABELS
    assert not any(
        entry.source_kind is SpectatorEventKind.HOSTILE_WRITE
        for entry in plan.ribbon_entries
    )

    # Disruption entries collapse by orders of magnitude, and the surviving
    # rate is bounded by entrant count per cooldown window rather than by
    # event volume -- which is what makes the ribbon readable at all.
    emitted = sum(
        1
        for entry in plan.ribbon_entries
        if entry.source_kind is SpectatorEventKind.PROCESS_DISRUPTED
    )
    assert emitted < disruptions / 4
    ticks = derivation.last_tick - derivation.first_tick + 1
    entrant_count = len(derivation.binding.entrant_identities)
    cooldown = FightNightConfig().repeat_cooldown_ticks
    assert emitted <= entrant_count * (ticks // cooldown + 2)


def test_a_larger_cooldown_never_produces_more_entries(tmp_path: Path) -> None:
    """The cooldown is monotone, so tuning it cannot surprise a reviewer."""

    derivation = _four_three_way(tmp_path)
    counts = [
        len(
            build_fight_night_plan(
                derivation,
                mode=FightNightMode.BROADCAST,
                config=FightNightConfig(repeat_cooldown_ticks=cooldown),
            ).ribbon_entries
        )
        for cooldown in (0, 6, 12, 24, 48)
    ]
    assert counts == sorted(counts, reverse=True)


def test_lifecycle_events_are_never_suppressed_by_the_cooldown(
    tmp_path: Path,
) -> None:
    """An elimination must always appear, however busy the ribbon already is."""

    derivation = _four_two_fights(tmp_path)
    eliminations = [
        event
        for event in derivation.events
        if event.kind is SpectatorEventKind.AGENT_ELIMINATED
    ]
    assert len(eliminations) == 2

    # Even with an absurd cooldown that would suppress everything repeatable.
    plan = build_fight_night_plan(
        derivation,
        mode=FightNightMode.BROADCAST,
        config=FightNightConfig(repeat_cooldown_ticks=10**6),
    )
    presented = [
        entry
        for entry in plan.ribbon_entries
        if entry.source_kind is SpectatorEventKind.AGENT_ELIMINATED
    ]
    assert len(presented) == len(eliminations)
    assert {entry.subject for entry in presented} == {
        event.targets[0] for event in eliminations
    }


# ---------------------------------------------------------------------------
# 5. Path independence
# ---------------------------------------------------------------------------


def test_the_ribbon_at_a_tick_is_independent_of_how_playback_reached_it(
    tmp_path: Path,
) -> None:
    """Sec. 43, proven by querying the same plan along four traversals."""

    derivation = _four_two_fights(tmp_path)
    plan = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    ticks = list(range(derivation.first_tick, derivation.last_tick + 1))

    sequential = {tick: plan.ribbon_at_tick(tick) for tick in ticks}
    backward = {tick: plan.ribbon_at_tick(tick) for tick in reversed(ticks)}
    # A backward-then-forward scrub, and a restart-then-seek.
    mixed: dict[int, tuple] = {}
    for tick in ticks[::-3]:
        mixed[tick] = plan.ribbon_at_tick(tick)
    for tick in ticks[::5]:
        plan.ribbon_at_tick(derivation.first_tick)
        mixed[tick] = plan.ribbon_at_tick(tick)

    assert backward == sequential
    for tick, ribbon in mixed.items():
        assert ribbon == sequential[tick]


def test_the_ribbon_never_shows_an_event_from_a_later_tick(tmp_path: Path) -> None:
    """No look-ahead: an entry may only appear at or after its own tick."""

    derivation = _four_three_way(tmp_path)
    plan = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    for tick in range(derivation.first_tick, derivation.last_tick + 1):
        for entry in plan.ribbon_at_tick(tick):
            assert entry.tick <= tick


def test_the_ribbon_is_bounded_by_its_configured_size(tmp_path: Path) -> None:
    derivation = _four_three_way(tmp_path)
    for size in (1, 3, 4, 8):
        plan = build_fight_night_plan(
            derivation,
            mode=FightNightMode.BROADCAST,
            config=FightNightConfig(ribbon_size=size),
        )
        for tick in range(derivation.first_tick, derivation.last_tick + 1):
            assert len(plan.ribbon_at_tick(tick)) <= size


def test_every_ribbon_entry_is_auditable_back_to_a_derived_event(
    tmp_path: Path,
) -> None:
    """Fight Night derives nothing: each entry restates one real event."""

    derivation = _four_three_way(tmp_path)
    identities = {(event.tick, event.sequence): event for event in derivation.events}
    plan = build_fight_night_plan(derivation, mode=FightNightMode.BROADCAST)
    assert plan.ribbon_entries
    for entry in plan.ribbon_entries:
        source = identities[(entry.tick, entry.sequence)]
        assert source.kind is entry.source_kind
        assert RIBBON_LABELS[source.kind][0] == entry.label
