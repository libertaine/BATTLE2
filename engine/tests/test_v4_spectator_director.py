"""Phase 7: deterministic spectator playback-pacing (Director) plans.

Every state-machine assertion here is checked against ticks discovered from a
real derived event stream -- never a hand-picked tick number -- following
this repository's standing evidence rule: assert on exact values taken from
an actual execution, not on non-emptiness or an assumed shape. The one
deliberate exception is the narrow, explicitly-named pure-function test for
identity-independence (Sec. 33/34), which constructs `SpectatorEvent` values
directly because it is proving a property of the Director's own lookup logic
in isolation, not claiming anything about engine wiring.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1
from battle_engine.spectator_derivation import (
    PairBindingError,
    SpectatorEvent,
    SpectatorEventKind,
    analyze_pair,
)
from battle_engine.spectator_director import (
    DEFAULT_SIGNIFICANCE,
    DirectorConfig,
    DirectorError,
    DirectorMode,
    DirectorPacingState,
    DirectorReason,
    EventSignificance,
    build_director_plan,
    build_director_plan_from_pair,
)

_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

# Walks steadily in one direction and never reads or writes. Used to produce
# a clean, isolated DETECTION_GAINED/DETECTION_LOST pair with nothing else in
# the stream, for testing lookback decay through RECOVERY back to CRUISE.
GHOST = _IMPORTS + '''
class Ghost:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="drift", reach=12, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.MOVE, 1)
def create_agent() -> AgentV2:
    return Ghost()
'''

# Stationary, reads only its own cell. Never produces a hostile event.
ROCK = _IMPORTS + '''
class Rock:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="z", reach=1, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, obs.self_anchor)
def create_agent() -> AgentV2:
    return Rock()
'''

# Walks until it detects an opponent, then strips its core -- a real
# escalating core-capture ending in elimination (mirrors the Phase 3
# `elimination` corpus scenario). Used for CONTACT -> ENGAGEMENT ->
# IMPACT_HOLD escalation and the mandatory Perspective hidden-event
# non-reaction regression (the victim, SLEEPER, never sees any of it).
EXECUTIONER = _IMPORTS + '''
class Executioner:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="axe", reach=24, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.target = None
        self.step = 0
    def act(self, obs: ObservationV2) -> AgentAction:
        if self.target is None and obs.visible_enemy_anchor_addresses:
            self.target = obs.visible_enemy_anchor_addresses[0]
        if self.target is None or obs.self_anchor + 4 < self.target:
            return AgentAction(ActionKindV2.MOVE, 4)
        self.step += 1
        return AgentAction(ActionKindV2.WRITE, self.target + (self.step % 8), 0x11)
def create_agent() -> AgentV2:
    return Executioner()
'''

# Never leaves home, reach 1: cannot see the executioner approach or attack.
SLEEPER = _IMPORTS + '''
class Sleeper:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="z", reach=1, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, obs.self_anchor)
def create_agent() -> AgentV2:
    return Sleeper()
'''


def _write_agent(root: Path, name: str, source: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.py").write_text(source)
    (directory / "agent.yaml").write_text(
        f"name: {name}\ndescription: Phase 7 fixture\nversion: '1.0'\napi_version: 2\n"
    )


def _run_match(
    root: Path,
    label: str,
    entrant_a: tuple[str, str, int],
    entrant_b: tuple[str, str, int],
    *,
    arena_size: int,
    max_ticks: int,
    seed: int,
) -> tuple[Path, Path]:
    name_a, source_a, start_a = entrant_a
    name_b, source_b, start_b = entrant_b
    _write_agent(root, name_a, source_a)
    _write_agent(root, name_b, source_b)
    run = root / label
    run.mkdir(parents=True, exist_ok=True)
    replay_path = run / "replay.jsonl"
    trace_path = run / "trace.jsonl"
    request = MatchRequest(
        config=Config(
            seed=seed,
            arena_size=arena_size,
            instr_per_tick=8,
            win_mode="capture",
            weights=Weights(),
        ),
        entrants=(
            MatchEntrant.python("A", "Entrant A", start_a, resolve_agent(root, name_a)),
            MatchEntrant.python("B", "Entrant B", start_b, resolve_agent(root, name_b)),
        ),
        max_ticks=max_ticks,
        replay_path=replay_path,
        trace_path=trace_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    NativeMatchService().run(request)
    return replay_path, trace_path


def _drift_by(root: Path, label: str = "drift"):
    """A -> passes B once, then quiet for the rest of a 30-tick match."""

    return _run_match(
        root,
        label,
        ("ghost", GHOST, 0),
        ("rock", ROCK, 100),
        arena_size=200,
        max_ticks=30,
        seed=7,
    )


def _kill(root: Path, label: str = "kill"):
    return _run_match(
        root,
        label,
        ("executioner", EXECUTIONER, 0),
        ("sleeper", SLEEPER, 32),
        arena_size=64,
        max_ticks=40,
        seed=13,
    )


# ---------------------------------------------------------------------------
# 1. Deterministic plan generation
# ---------------------------------------------------------------------------


def test_plan_fingerprint_is_identical_across_repeated_builds(tmp_path: Path) -> None:
    replay_path, trace_path = _kill(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)

    plan_a = build_director_plan(derivation, mode=DirectorMode.BROADCAST)
    plan_b = build_director_plan(derivation, mode=DirectorMode.BROADCAST)

    assert plan_a.decisions == plan_b.decisions
    assert plan_a.plan_fingerprint() == plan_b.plan_fingerprint()


def test_plan_fingerprint_differs_between_broadcast_and_perspective(tmp_path: Path) -> None:
    replay_path, trace_path = _kill(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)

    broadcast_plan = build_director_plan(derivation, mode=DirectorMode.BROADCAST)
    perspective_plan = build_director_plan(
        derivation, mode=DirectorMode.PERSPECTIVE, entrant_id="B"
    )

    assert broadcast_plan.plan_fingerprint() != perspective_plan.plan_fingerprint()
    assert broadcast_plan.decisions != perspective_plan.decisions


# ---------------------------------------------------------------------------
# 2. Event significance mapping
# ---------------------------------------------------------------------------


def test_default_significance_matches_the_phase_7_starting_hypothesis() -> None:
    major = {
        SpectatorEventKind.AGENT_ELIMINATED,
        SpectatorEventKind.AGENT_FORFEITED,
        SpectatorEventKind.VICTORY,
        SpectatorEventKind.MATCH_ENDED,
    }
    high = {
        SpectatorEventKind.PROCESS_DISRUPTED,
        SpectatorEventKind.CORE_CELL_LOST,
        SpectatorEventKind.FIRST_HOSTILE_WRITE,
    }
    medium = {
        SpectatorEventKind.DETECTION_GAINED,
        SpectatorEventKind.FIRST_HOSTILE_READ,
        SpectatorEventKind.HOSTILE_WRITE,
    }
    low = {
        SpectatorEventKind.HOSTILE_READ,
        SpectatorEventKind.DETECTION_LOST,
        SpectatorEventKind.EFFECTIVE_MOVE,
    }
    assert {k for k, v in DEFAULT_SIGNIFICANCE.items() if v is EventSignificance.MAJOR} == major
    assert {k for k, v in DEFAULT_SIGNIFICANCE.items() if v is EventSignificance.HIGH} == high
    assert {k for k, v in DEFAULT_SIGNIFICANCE.items() if v is EventSignificance.MEDIUM} == medium
    assert {k for k, v in DEFAULT_SIGNIFICANCE.items() if v is EventSignificance.LOW} == low
    # Every one of the 13 accepted kinds is mapped; none silently defaults to NONE.
    assert set(DEFAULT_SIGNIFICANCE) == set(SpectatorEventKind)


def test_significance_lookup_ignores_actor_and_target_identity() -> None:
    """The state machine must key off `event.kind` alone (Sec. 33/34).

    A pure property test of `DirectorConfig.significance_for`, constructed
    directly rather than derived from a match: it proves the lookup itself
    cannot distinguish "HOSTILE_WRITE by A against B" from "by C against D",
    which is the property that makes co-location/READ-owner identity
    independence true by construction rather than by convention.
    """

    config = DirectorConfig()
    event_1 = SpectatorEvent(
        tick=5, sequence=0, kind=SpectatorEventKind.HOSTILE_WRITE, actors=("A",), targets=("B",)
    )
    event_2 = SpectatorEvent(
        tick=9, sequence=2, kind=SpectatorEventKind.HOSTILE_WRITE, actors=("C",), targets=("D",),
        previous_owner="D",
    )
    assert config.significance_for(event_1.kind) == config.significance_for(event_2.kind)
    assert config.significance_for(event_1.kind) is EventSignificance.MEDIUM


# ---------------------------------------------------------------------------
# 3/4. State transitions, hysteresis/cooldown, and recovery ramp
# ---------------------------------------------------------------------------


def test_contact_decays_through_recovery_back_to_cruise(tmp_path: Path) -> None:
    replay_path, trace_path = _drift_by(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)

    # Precondition, proven from the real artifact: no *hostile* event
    # contaminates the fixture (Ghost only ever moves; Rock only ever reads
    # its own cell). EFFECTIVE_MOVE fires every tick Ghost moves, which is
    # every tick -- it is LOW-tier and must not itself drive escalation.
    kinds = {event.kind for event in derivation.events}
    assert kinds <= {
        SpectatorEventKind.DETECTION_GAINED,
        SpectatorEventKind.DETECTION_LOST,
        SpectatorEventKind.EFFECTIVE_MOVE,
        SpectatorEventKind.MATCH_ENDED,
    }
    # MEDIUM/HIGH only: MATCH_ENDED is MAJOR-tier and always sits at the
    # final tick, which would swamp this specifically mid-match contact
    # signal -- the terminal hold has its own dedicated tests above.
    medium_or_high = [
        event
        for event in derivation.events
        if DEFAULT_SIGNIFICANCE.get(event.kind, EventSignificance.NONE)
        in (EventSignificance.MEDIUM, EventSignificance.HIGH)
    ]
    assert medium_or_high, "fixture must produce at least one MEDIUM/HIGH event to test decay"
    last_signal_tick = max(event.tick for event in medium_or_high)
    # Precondition: the quiet tail is long enough to observe full decay
    # before the terminal tick's own hold (tested separately) takes over.
    assert last_signal_tick + 6 < derivation.result_ticks

    config = DirectorConfig(contact_lookback_ticks=3, recovery_ticks=2)
    plan = build_director_plan(derivation, mode=DirectorMode.BROADCAST, config=config)

    assert plan.decision_for_tick(last_signal_tick).state == DirectorPacingState.CONTACT
    assert plan.decision_for_tick(last_signal_tick).reason == DirectorReason.CONTACT_SIGNAL
    assert plan.decision_for_tick(last_signal_tick + 3).state == DirectorPacingState.CONTACT
    assert plan.decision_for_tick(last_signal_tick + 4).state == DirectorPacingState.RECOVERY
    assert plan.decision_for_tick(last_signal_tick + 4).reason == DirectorReason.RECOVERY_RAMP
    assert plan.decision_for_tick(last_signal_tick + 5).state == DirectorPacingState.RECOVERY
    assert plan.decision_for_tick(last_signal_tick + 6).state == DirectorPacingState.CRUISE
    assert plan.decision_for_tick(last_signal_tick + 6).reason == DirectorReason.NO_SIGNIFICANT_ACTIVITY

    # Rate ordering: contact is deliberately the slowest, cruise the fastest,
    # recovery strictly between them (Sec. 15's non-monotonic pacing curve).
    contact_rate = plan.decision_for_tick(last_signal_tick).rate_tps
    recovery_rate = plan.decision_for_tick(last_signal_tick + 4).rate_tps
    cruise_rate = plan.decision_for_tick(last_signal_tick + 6).rate_tps
    assert contact_rate < recovery_rate < cruise_rate


def test_high_tier_events_escalate_to_engagement_and_major_events_hold(tmp_path: Path) -> None:
    replay_path, trace_path = _kill(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)

    high_events = [
        e for e in derivation.events
        if DEFAULT_SIGNIFICANCE.get(e.kind) in (EventSignificance.HIGH,)
    ]
    major_events = [
        e for e in derivation.events
        if DEFAULT_SIGNIFICANCE.get(e.kind) is EventSignificance.MAJOR
    ]
    assert high_events, "the core-capture fixture must produce HIGH-tier events"
    assert major_events, "the core-capture fixture must end in a MAJOR event"

    plan = build_director_plan(derivation, mode=DirectorMode.BROADCAST)

    assert any(d.state == DirectorPacingState.ENGAGEMENT for d in plan.decisions)
    major_tick = min(e.tick for e in major_events)
    major_decision = plan.decision_for_tick(major_tick)
    assert major_decision.state == DirectorPacingState.IMPACT_HOLD
    assert major_decision.reason == DirectorReason.MAJOR_EVENT_HOLD
    assert major_decision.hold_ms == DirectorConfig().impact_hold_ms
    assert major_decision.source_events, "a hold must cite the event(s) that triggered it"


def test_broadcast_terminal_hold_is_driven_by_the_real_match_ended_event(tmp_path: Path) -> None:
    """A tie ending on the tick limit still gets a readable terminal hold.

    `MATCH_ENDED` is itself MAJOR-tier and present in the full (Broadcast)
    stream, so the ordinary per-tick escalation path already produces the
    hold here, citing the real event -- the mode-independent override exists
    for Perspective mode, where `MATCH_ENDED` is always absent (see below).
    """

    replay_path, trace_path = _drift_by(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)
    assert derivation.termination_reason != "last_agent_standing"

    plan = build_director_plan(derivation, mode=DirectorMode.BROADCAST)
    terminal = plan.decision_for_tick(derivation.result_ticks)
    assert terminal.state == DirectorPacingState.IMPACT_HOLD
    assert terminal.reason == DirectorReason.MAJOR_EVENT_HOLD
    assert terminal.hold_ms > 0
    assert terminal.source_events


def test_perspective_terminal_hold_uses_the_mode_independent_override(tmp_path: Path) -> None:
    """Perspective mode never sees `MATCH_ENDED` directly (it is omniscient-only),
    so its terminal hold must come from the derivation-level override, not an
    event citation.
    """

    replay_path, trace_path = _drift_by(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)

    plan = build_director_plan(derivation, mode=DirectorMode.PERSPECTIVE, entrant_id="A")
    terminal = plan.decision_for_tick(derivation.result_ticks)
    assert terminal.state == DirectorPacingState.IMPACT_HOLD
    assert terminal.reason == DirectorReason.TERMINAL_HOLD
    assert terminal.hold_ms > 0
    assert terminal.source_events == ()


# ---------------------------------------------------------------------------
# 5. Mandatory timing-disclosure negative regression (Sec. 31/48)
# ---------------------------------------------------------------------------


def test_perspective_director_never_reacts_to_omniscient_only_events(tmp_path: Path) -> None:
    """The victim's Perspective Director must stay quiet through its own death.

    `sleeper` (entrant B) has reach 1 and never moves; it cannot see the
    executioner approach, strip its core, or eliminate it. Broadcast, over
    the same match, must escalate all the way to a hold. This is the
    mandatory Phase 7 regression: an omniscient event occurring while the
    selected entrant cannot observe it must never change Perspective pacing.
    """

    replay_path, trace_path = _kill(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)

    # Precondition, proven from the real artifact: B's own visible_to set is
    # empty for every event in the match -- B is genuinely told nothing.
    b_visible_events = [e for e in derivation.events if "B" in e.visible_to]
    assert b_visible_events == [], "fixture must leave the victim with zero delivered events"
    assert any(
        DEFAULT_SIGNIFICANCE.get(e.kind) in (EventSignificance.HIGH, EventSignificance.MAJOR)
        for e in derivation.events
    ), "the match must actually contain hidden high-severity events to test against"

    broadcast_plan = build_director_plan(derivation, mode=DirectorMode.BROADCAST)
    perspective_plan = build_director_plan(
        derivation, mode=DirectorMode.PERSPECTIVE, entrant_id="B"
    )

    assert any(d.state == DirectorPacingState.ENGAGEMENT for d in broadcast_plan.decisions)
    assert any(d.state == DirectorPacingState.IMPACT_HOLD for d in broadcast_plan.decisions)

    terminal_tick = derivation.result_ticks
    for tick in range(derivation.first_tick, terminal_tick):
        decision = perspective_plan.decision_for_tick(tick)
        assert decision.state == DirectorPacingState.CRUISE, (
            f"Perspective(B) reacted at tick {tick}: {decision.reason} "
            f"(state {decision.state}) -- an omniscient-only event leaked through timing"
        )
        assert decision.source_events == ()

    # The terminal hold is the one mode-independent exception, driven by
    # match-level metadata rather than a per-entrant-filtered event -- and it
    # is legitimate because the existing renderer already shows the same
    # terminal banner identically in every mode at this same tick.
    assert perspective_plan.decision_for_tick(terminal_tick).state == DirectorPacingState.IMPACT_HOLD
    assert perspective_plan.decision_for_tick(terminal_tick).reason == DirectorReason.TERMINAL_HOLD


# ---------------------------------------------------------------------------
# 6. Causal (no-lookahead) proof
# ---------------------------------------------------------------------------


def test_a_decision_at_tick_n_never_depends_on_events_after_tick_n(tmp_path: Path) -> None:
    # `_kill` ends in as few as 2 ticks on this seed -- too short to
    # truncate meaningfully. `_drift_by` runs its full 30-tick span and
    # carries a real mid-match contact event, giving a substantial prefix to
    # compare.
    replay_path, trace_path = _drift_by(tmp_path)
    full_derivation = analyze_pair(replay_path, trace_path)

    cutoff = full_derivation.result_ticks - 3
    assert cutoff > full_derivation.first_tick, "fixture too short to truncate meaningfully"

    # Push result_ticks far beyond either range so the terminal-hold special
    # case (which deliberately IS keyed on a tick's own identity, not
    # lookahead -- see the module docstring) cannot contaminate this proof.
    full_no_terminal = replace(full_derivation, result_ticks=10_000)
    truncated = replace(
        full_derivation,
        events=tuple(e for e in full_derivation.events if e.tick <= cutoff),
        last_tick=cutoff,
        result_ticks=10_000,
    )

    full_plan = build_director_plan(full_no_terminal, mode=DirectorMode.BROADCAST)
    truncated_plan = build_director_plan(truncated, mode=DirectorMode.BROADCAST)

    for tick in range(full_derivation.first_tick, cutoff + 1):
        assert full_plan.decision_for_tick(tick) == truncated_plan.decision_for_tick(tick), (
            f"tick {tick} differed between the full and truncated derivation -- "
            "a decision used an event from beyond its own tick"
        )


# ---------------------------------------------------------------------------
# 7. Seek equivalence / same-tick lookup
# ---------------------------------------------------------------------------


def test_decision_for_tick_is_path_independent(tmp_path: Path) -> None:
    replay_path, trace_path = _kill(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)
    plan = build_director_plan(derivation, mode=DirectorMode.BROADCAST)

    forward = [plan.decision_for_tick(t) for t in range(plan.first_tick, plan.last_tick + 1)]
    backward = [plan.decision_for_tick(t) for t in reversed(range(plan.first_tick, plan.last_tick + 1))]
    assert forward == list(reversed(backward))

    # Same-tick repeated lookup: identical every time, no mutation, no drift.
    sample_tick = plan.first_tick + (plan.last_tick - plan.first_tick) // 2
    first_read = plan.decision_for_tick(sample_tick)
    for _ in range(5):
        assert plan.decision_for_tick(sample_tick) == first_read


# ---------------------------------------------------------------------------
# 8. Invalid mode/entrant combinations and trace-unavailable behaviour
# ---------------------------------------------------------------------------


def test_perspective_mode_requires_a_known_entrant(tmp_path: Path) -> None:
    replay_path, trace_path = _kill(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)

    with pytest.raises(DirectorError):
        build_director_plan(derivation, mode=DirectorMode.PERSPECTIVE, entrant_id=None)
    with pytest.raises(DirectorError):
        build_director_plan(derivation, mode=DirectorMode.PERSPECTIVE, entrant_id="ghost")
    with pytest.raises(DirectorError):
        build_director_plan(derivation, mode=DirectorMode.BROADCAST, entrant_id="B")


def test_director_never_fabricates_a_plan_for_a_mismatched_pair(tmp_path: Path) -> None:
    # Two genuinely different matches (different agents/scenario), so their
    # replay bytes cannot coincidentally match -- `_kill` run twice with the
    # same seed and agents is fully deterministic and would produce
    # byte-identical replays, defeating this test.
    replay_path_1, _trace_path_1 = _kill(tmp_path, "kill-1")
    _replay_path_2, trace_path_2 = _drift_by(tmp_path, "drift-2")

    with pytest.raises(PairBindingError):
        build_director_plan_from_pair(
            replay_path_1, trace_path_2, mode=DirectorMode.BROADCAST
        )
