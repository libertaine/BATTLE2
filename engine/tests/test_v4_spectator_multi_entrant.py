"""Phase 8A: Director behaviour on real 3- and 4-entrant matches.

Phase 7 qualified the Director against a two-entrant corpus only and recorded
that gap as its own limitation (Phase 7 research document Sec. 23 item 3).
This module closes it with real multi-entrant matches -- every assertion below
is checked against a genuine ``NativeMatchService`` run's replay/trace pair,
never a hand-built event list, so a claim about "what the Director does when
two entrants fight and a third is blind" is a claim about an execution that
actually happened.

The two questions Phase 8's brief asks by name (Sec. 7/8) are both answered
here as executable assertions rather than only in prose: whether Broadcast
becomes permanently slow when *someone* is always fighting, and whether
several unrelated simultaneous engagements defeat the sustained-activity
fatigue rule.
"""

from __future__ import annotations

from pathlib import Path

from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1
from battle_engine.spectator_derivation import SpectatorDerivation, analyze_pair
from battle_engine.spectator_director import (
    DEFAULT_DIRECTOR_CONFIG,
    DirectorConfig,
    DirectorMode,
    DirectorPacingState,
    DirectorPlan,
    DirectorReason,
    build_director_plan,
)

_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

# Reach 1, never moves: cannot see anything all match, so its Perspective
# stream is the strongest possible "blind bystander" case.
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

# Closes on the first enemy anchor it is shown and writes around it.
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


def _write_agent(root: Path, name: str, source: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.py").write_text(source)
    (directory / "agent.yaml").write_text(
        f"name: {name}\ndescription: Phase 8 fixture\nversion: '1.0'\napi_version: 2\n"
    )


def _run_match(
    root: Path,
    label: str,
    entrants: tuple[tuple[str, str, str, int], ...],
    *,
    arena_size: int,
    max_ticks: int,
    seed: int,
) -> tuple[Path, Path]:
    """Run one real N-entrant match.

    ``entrants`` is ``((entrant_id, display_name, agent_source_name, start), ...)``.
    Starts must be at least ``CORE_SIZE`` apart -- the v4 ruleset rejects
    overlapping entrant cores outright.
    """

    sources = {"hermit": HERMIT, "hunter": HUNTER}
    for _entrant_id, _name, agent_name, _start in entrants:
        _write_agent(root, agent_name, sources[agent_name])
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
        entrants=tuple(
            MatchEntrant.python(entrant_id, name, start, resolve_agent(root, agent_name))
            for entrant_id, name, agent_name, start in entrants
        ),
        max_ticks=max_ticks,
        replay_path=replay_path,
        trace_path=trace_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    NativeMatchService().run(request)
    return replay_path, trace_path


def _three_entrant_pair_plus_blind(root: Path) -> SpectatorDerivation:
    """A hunts B at one end of a 400-cell arena; C sits blind at the other."""

    replay_path, trace_path = _run_match(
        root,
        "p3",
        (
            ("A", "Entrant A", "hunter", 0),
            ("B", "Entrant B", "hermit", 40),
            ("C", "Entrant C", "hermit", 300),
        ),
        arena_size=400,
        max_ticks=80,
        seed=11,
    )
    return analyze_pair(replay_path, trace_path)


def _four_entrant_two_fights(root: Path) -> SpectatorDerivation:
    """Two independent simultaneous engagements: A vs B, and C vs D."""

    replay_path, trace_path = _run_match(
        root,
        "p4",
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
    return analyze_pair(replay_path, trace_path)


def _four_entrant_three_way(root: Path) -> SpectatorDerivation:
    """Three hunters in mutual reach plus one distant blind entrant.

    The heaviest sustained-activity case in the Phase 8 corpus: three
    entrants continuously disrupting each other for the whole match while D
    is told nothing at all.
    """

    replay_path, trace_path = _run_match(
        root,
        "p4x",
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
    return analyze_pair(replay_path, trace_path)


def _duration_seconds(plan: DirectorPlan) -> float:
    """Total wall-clock playback the plan schedules, holds included."""

    return sum(1.0 / d.rate_tps + d.hold_ms / 1000.0 for d in plan.decisions)


def _flat_seconds(derivation: SpectatorDerivation) -> float:
    ticks = derivation.last_tick - derivation.first_tick + 1
    return ticks / DEFAULT_DIRECTOR_CONFIG.cruise_rate_tps


# ---------------------------------------------------------------------------
# 1. Broadcast pacing stays bounded with 3 and 4 entrants
# ---------------------------------------------------------------------------


def test_three_entrant_broadcast_pacing_stays_bounded(tmp_path: Path) -> None:
    derivation = _three_entrant_pair_plus_blind(tmp_path)
    assert len(derivation.binding.entrant_identities) == 3

    plan = build_director_plan(derivation, mode=DirectorMode.BROADCAST)
    inflation = _duration_seconds(plan) / _flat_seconds(derivation)

    # Phase 7 accepted 2.10x as its two-entrant worst case and disclosed it.
    # A third entrant must not push Broadcast past that: the whole point of
    # the Sec. 7 question is whether more entrants means a permanently slow
    # match, and the measured answer here is that it does not.
    assert inflation < 2.10

    # And the match genuinely does escalate somewhere -- otherwise the bound
    # above would be trivially satisfied by a match that never left CRUISE.
    states = {d.state for d in plan.decisions}
    assert DirectorPacingState.ENGAGEMENT in states
    assert DirectorPacingState.IMPACT_HOLD in states


def test_four_entrant_broadcast_pacing_stays_bounded(tmp_path: Path) -> None:
    derivation = _four_entrant_two_fights(tmp_path)
    assert len(derivation.binding.entrant_identities) == 4

    plan = build_director_plan(derivation, mode=DirectorMode.BROADCAST)
    inflation = _duration_seconds(plan) / _flat_seconds(derivation)
    assert inflation < 2.10

    # Two independent engagements really did both happen and both escalated.
    assert sum(1 for d in plan.decisions if d.state is DirectorPacingState.ENGAGEMENT) > 0
    eliminated = [
        event for event in derivation.events if event.kind.value == "AGENT_ELIMINATED"
    ]
    assert len(eliminated) == 2


# ---------------------------------------------------------------------------
# 2. Sustained-activity fatigue under multi-entrant load
# ---------------------------------------------------------------------------


def test_multiple_simultaneous_engagements_do_not_defeat_sustained_fatigue(
    tmp_path: Path,
) -> None:
    """Three entrants fighting at once must not compound into a slog.

    The Phase 8 brief (Sec. 8) asks whether several unrelated engagements can
    keep refreshing "important activity" so that fatigue never fires. They
    cannot, and the reason is structural rather than lucky: fatigue triggers
    on a *continuous elevated streak*, so extra concurrent engagements make
    that streak more continuous, engaging fatigue sooner rather than later.

    Proven as a counterfactual against the same real match: the identical
    derivation is planned twice, differing only in whether the fatigue
    threshold is reachable.
    """

    derivation = _four_entrant_three_way(tmp_path)
    flat = _flat_seconds(derivation)

    with_fatigue = build_director_plan(derivation, mode=DirectorMode.BROADCAST)
    without_fatigue = build_director_plan(
        derivation,
        mode=DirectorMode.BROADCAST,
        config=DirectorConfig(sustain_ticks_before_fatigue=10**9),
    )

    # This match really is a sustained-activity case: the Director is elevated
    # for the overwhelming majority of it, which is what makes the comparison
    # meaningful rather than a no-op.
    elevated = sum(
        1
        for d in with_fatigue.decisions
        if d.state in (DirectorPacingState.CONTACT, DirectorPacingState.ENGAGEMENT)
    )
    assert elevated / len(with_fatigue.decisions) > 0.5

    assert _duration_seconds(without_fatigue) > _duration_seconds(with_fatigue)
    assert _duration_seconds(with_fatigue) / flat < 2.10
    # The rule actually fired, and said so in the decision's own reason field
    # rather than only showing up as a smaller number.
    assert any(
        d.reason
        in (DirectorReason.SUSTAINED_CONTACT, DirectorReason.SUSTAINED_ENGAGEMENT)
        for d in with_fatigue.decisions
    )


# ---------------------------------------------------------------------------
# 3. Multi-entrant timing disclosure
# ---------------------------------------------------------------------------


def test_a_blind_entrant_is_not_slowed_by_a_fight_it_cannot_see(tmp_path: Path) -> None:
    """The Sec. 9 requirement, on a real three-entrant match.

    C is a reach-1 hermit 260 cells away from a genuine core capture. The
    precondition is proven from the artifacts first -- C is delivered zero
    events for the entire match -- and only then is its pacing asserted.
    """

    derivation = _three_entrant_pair_plus_blind(tmp_path)
    assert [event for event in derivation.events if "C" in event.visible_to] == []

    broadcast = build_director_plan(derivation, mode=DirectorMode.BROADCAST)
    blind = build_director_plan(
        derivation, mode=DirectorMode.PERSPECTIVE, entrant_id="C"
    )

    terminal = derivation.result_ticks
    for decision in blind.decisions:
        if decision.tick >= terminal:
            continue
        assert decision.state is DirectorPacingState.CRUISE
        assert decision.source_events == ()

    # Broadcast, on the same match at the same ticks, does escalate -- so the
    # flat CRUISE above is a real information boundary, not an inert match.
    assert any(
        d.state is DirectorPacingState.ENGAGEMENT
        for d in broadcast.decisions
        if d.tick < terminal
    )
    assert _duration_seconds(blind) < _duration_seconds(broadcast)


def test_four_entrant_blind_bystander_is_unaffected_by_a_three_way_fight(
    tmp_path: Path,
) -> None:
    """The same boundary under the heaviest activity in the Phase 8 corpus."""

    derivation = _four_entrant_three_way(tmp_path)
    assert [event for event in derivation.events if "D" in event.visible_to] == []
    # The fight D cannot see is genuinely large, not a token one.
    assert len(derivation.events) > 100

    blind = build_director_plan(
        derivation, mode=DirectorMode.PERSPECTIVE, entrant_id="D"
    )
    terminal = derivation.result_ticks
    assert all(
        d.state is DirectorPacingState.CRUISE
        for d in blind.decisions
        if d.tick < terminal
    )

    # Every *other* entrant, seeing real contact, is paced differently -- the
    # plans are not simply all identical for an unrelated reason.
    for entrant in ("A", "B", "C"):
        plan = build_director_plan(
            derivation, mode=DirectorMode.PERSPECTIVE, entrant_id=entrant
        )
        assert plan.decisions != blind.decisions


def test_perspective_plans_are_independent_across_four_entrants(tmp_path: Path) -> None:
    """Switching selected entrant must change pacing only via allowed info."""

    derivation = _four_entrant_two_fights(tmp_path)
    plans = {
        entrant: build_director_plan(
            derivation, mode=DirectorMode.PERSPECTIVE, entrant_id=entrant
        )
        for entrant in derivation.binding.entrant_identities
    }

    # The two engaged hunters see contact; the two blind hermits see nothing.
    for entrant in ("B", "D"):
        assert [e for e in derivation.events if entrant in e.visible_to] == []
    for entrant in ("A", "C"):
        assert [e for e in derivation.events if entrant in e.visible_to] != []

    terminal = derivation.result_ticks
    for entrant in ("B", "D"):
        assert all(
            d.state is DirectorPacingState.CRUISE
            for d in plans[entrant].decisions
            if d.tick < terminal
        )
    # Two equally-blind entrants are paced identically. Compared on the
    # pacing fields rather than the whole decision: `visibility_basis` is
    # deliberately per-entrant ("perspective:B" vs "perspective:D") so a
    # decision can always be traced back to the information domain that
    # produced it, and would differ here even though the pacing does not.
    def pacing(plan: DirectorPlan) -> list[tuple[object, ...]]:
        return [
            (d.tick, d.state, d.rate_tps, d.hold_ms, d.reason, d.source_events)
            for d in plan.decisions
        ]

    assert pacing(plans["B"]) == pacing(plans["D"])
    assert pacing(plans["A"]) != pacing(plans["B"])


def test_multi_entrant_plans_are_deterministic_and_path_independent(
    tmp_path: Path,
) -> None:
    """Rebuilding, and querying out of order, must reproduce byte-identically.

    Direct coverage of the Sec. 10 gate items 4 and 5 at four entrants:
    a plan is a pure function of its inputs, and ``decision_for_tick`` is an
    index lookup that cannot depend on the order ticks are requested in.
    """

    derivation = _four_entrant_two_fights(tmp_path)
    for entrant in (None, "A", "D"):
        mode = DirectorMode.BROADCAST if entrant is None else DirectorMode.PERSPECTIVE
        first = build_director_plan(derivation, mode=mode, entrant_id=entrant)
        second = build_director_plan(derivation, mode=mode, entrant_id=entrant)
        assert first.plan_fingerprint() == second.plan_fingerprint()

        ticks = list(range(derivation.first_tick, derivation.last_tick + 1))
        forward = [first.decision_for_tick(t) for t in ticks]
        backward = [first.decision_for_tick(t) for t in reversed(ticks)]
        shuffled = [first.decision_for_tick(t) for t in sorted(ticks, key=lambda t: t % 7)]
        assert list(reversed(backward)) == forward
        assert sorted(shuffled, key=lambda d: d.tick) == forward
