"""Phase 4 qualification for truthful API-v2 entrant perspective projection.

Every behavioral assertion starts with a real deterministic match and follows
its canonical replay and bound trace through Phase 3 derivation into Phase 4
projection.  Hand-built perspective states are used only for no behavior.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from battle_engine.agent_trace import read_trace_v2
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1, RULESET_V4_ALPHA2
from battle_engine.spectator_derivation import (
    PairBindingError,
    SpectatorEventKind,
    analyze_pair,
    verify_pair,
)
from battle_engine.spectator_events import load_schema4_replay
from battle_engine.spectator_perspective import (
    KnowledgeStatus,
    PerspectiveProjection,
    TickBoundary,
    analyze_perspective,
    explain_state,
    project_perspective,
    serialize_projection,
    serialize_state,
    state_to_dict,
)

_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

ANVIL = (
    _IMPORTS
    + """
class Anvil:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="body", reach=2, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.WRITE, obs.own_core_base, 0xCE)
def create_agent() -> AgentV2:
    return Anvil()
"""
)

SLEEPER = (
    _IMPORTS
    + """
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
"""
)

HUNTER = (
    _IMPORTS
    + """
class Hunter:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="eye", reach=10, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        if obs.visible_enemy_anchor_addresses:
            target = obs.visible_enemy_anchor_addresses[0]
            if obs.current_tick % 2 == 0:
                return AgentAction(ActionKindV2.READ, target)
            return AgentAction(ActionKindV2.WRITE, target, 0x5A)
        return AgentAction(ActionKindV2.MOVE, 4)
def create_agent() -> AgentV2:
    return Hunter()
"""
)

OSCILLATOR = (
    _IMPORTS
    + """
class Oscillator:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="near", reach=15, share=0.5),
                ProcessDeclaration(id="far", reach=15, share=0.5)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.MOVE, 10 if obs.self_anchor < 20 else -10)
def create_agent() -> AgentV2:
    return Oscillator()
"""
)

FLYBY = (
    _IMPORTS
    + """
class Flyby:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="wing", reach=4, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.MOVE, 1)
def create_agent() -> AgentV2:
    return Flyby()
"""
)

APPROACHER = (
    _IMPORTS
    + """
class Approacher:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="step", reach=3, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.MOVE, 4)
def create_agent() -> AgentV2:
    return Approacher()
"""
)

COLOCATOR = (
    _IMPORTS
    + """
class Colocator:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="mover", reach=2, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.moved = False
    def act(self, obs: ObservationV2) -> AgentAction:
        if not self.moved:
            self.moved = True
            return AgentAction(ActionKindV2.MOVE, -8)
        return AgentAction(ActionKindV2.WRITE, obs.own_core_base, 0xCE)
def create_agent() -> AgentV2:
    return Colocator()
"""
)

READ_PROBE = (
    _IMPORTS
    + """
class ReadProbe:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="probe", reach=20, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.step = 0
    def act(self, obs: ObservationV2) -> AgentAction:
        step = self.step
        self.step += 1
        if step == 0:
            target = obs.own_core_base
        elif step == 1:
            target = obs.own_core_base + obs.own_core_size
        elif step == 2:
            target = obs.visible_enemy_anchor_addresses[0]
        elif step == 3:
            target = obs.self_anchor + obs.self_reach + 1
        else:
            target = obs.own_core_base
        return AgentAction(ActionKindV2.READ, target)
def create_agent() -> AgentV2:
    return ReadProbe()
"""
)

WIDE_READER = (
    _IMPORTS
    + """
class WideReader:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="eye", reach=32, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        target = (obs.visible_enemy_anchor_addresses[0]
                  if obs.visible_enemy_anchor_addresses else obs.own_core_base)
        return AgentAction(ActionKindV2.READ, target)
def create_agent() -> AgentV2:
    return WideReader()
"""
)

MULTI_READER = (
    _IMPORTS
    + """
class MultiReader:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="left", reach=8, share=0.5),
                ProcessDeclaration(id="right", reach=8, share=0.5)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, obs.own_core_base)
def create_agent() -> AgentV2:
    return MultiReader()
"""
)

EXECUTIONER = (
    _IMPORTS
    + """
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
"""
)


def _write_agent(root: Path, name: str, source: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.py").write_text(source, encoding="utf-8")
    (directory / "agent.yaml").write_text(
        f"name: {name}\ndescription: Phase 4 fixture\nversion: '1.0'\napi_version: 2\n",
        encoding="utf-8",
    )


def _run_match(
    root: Path,
    label: str,
    entrants: tuple[tuple[str, str, str, int], ...],
    *,
    arena_size: int = 64,
    max_ticks: int = 12,
    seed: int = 11,
    trace: bool = True,
    ruleset_id: str = RULESET_V4_ALPHA1.ruleset_id,
):
    for _entrant_id, agent_name, source, _start in entrants:
        _write_agent(root, agent_name, source)
    run = root / label
    run.mkdir(parents=True, exist_ok=True)
    replay_path = run / "replay.jsonl"
    trace_path = run / "trace.jsonl" if trace else None
    request = MatchRequest(
        config=Config(
            seed=seed,
            arena_size=arena_size,
            instr_per_tick=8,
            win_mode="capture",
            weights=Weights(),
        ),
        entrants=tuple(
            MatchEntrant.python(
                entrant_id,
                entrant_id,
                start,
                resolve_agent(root, agent_name),
            )
            for entrant_id, agent_name, _source, start in entrants
        ),
        max_ticks=max_ticks,
        replay_path=replay_path,
        trace_path=trace_path,
        ruleset_id=ruleset_id,
    )
    result = NativeMatchService().run(request)
    return replay_path, trace_path, result


def _duel(root: Path, label: str = "duel", *, seed: int = 11):
    return _run_match(
        root,
        label,
        (
            ("A", "hunter", HUNTER, 0),
            ("B", "anvil", ANVIL, 32),
        ),
        seed=seed,
    )


def _contact_addresses(state) -> tuple[int, ...]:
    return tuple(contact.address for contact in state.current_contacts)


def _stale_addresses(state) -> tuple[int, ...]:
    return tuple(contact.address for contact in state.stale_contacts)


def test_supported_api_requires_a_validated_matching_pair(tmp_path: Path) -> None:
    replay_one, trace_one, _result = _duel(tmp_path, "one", seed=11)
    replay_two, trace_two, _result = _duel(tmp_path, "two", seed=99)
    assert trace_one is not None and trace_two is not None

    projection = analyze_perspective(replay_one, trace_one, "A")
    assert isinstance(projection, PerspectiveProjection)
    assert projection.replay_sha256 == hashlib.sha256(replay_one.read_bytes()).hexdigest()

    with pytest.raises(TypeError, match="SpectatorDerivation"):
        project_perspective(verify_pair(replay_one, trace_one), "A")  # type: ignore[arg-type]
    with pytest.raises(PairBindingError, match="binding mismatch"):
        analyze_perspective(replay_one, trace_two, "A")
    with pytest.raises(PairBindingError, match="binding mismatch"):
        analyze_perspective(replay_two, trace_one, "A")


def test_unknown_entrant_is_rejected_after_pair_validation(tmp_path: Path) -> None:
    replay, trace, _result = _duel(tmp_path)
    assert trace is not None
    with pytest.raises(ValueError, match="not present"):
        analyze_perspective(replay, trace, "not-an-entrant")


def test_contact_gain_retention_loss_and_regain_are_callback_exact(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "flyby",
        (
            ("A", "flyby", FLYBY, 0),
            ("B", "sleeper", SLEEPER, 20),
        ),
        max_ticks=20,
        seed=17,
    )
    assert trace is not None
    projection = analyze_perspective(replay, trace, "A")

    gained = [frame for frame in projection.frames if frame.gained_contact_addresses]
    lost = [frame for frame in projection.frames if frame.staled_contact_addresses]
    assert len(gained) >= 3
    assert len(lost) >= 2
    assert gained[0].gained_contact_addresses == (20,)
    assert lost[0].staled_contact_addresses == (20,)

    gained_state = projection.state_at_callback(gained[0].entrant_callback_index)
    assert gained_state.contact_status(20) is KnowledgeStatus.CURRENT
    retained_state = projection.state_at_callback(gained[0].entrant_callback_index + 1)
    assert retained_state.contact_status(20) is KnowledgeStatus.CURRENT
    lost_state = projection.state_at_callback(lost[0].entrant_callback_index)
    assert lost_state.contact_status(20) is KnowledgeStatus.STALE
    regained_state = projection.state_at_callback(gained[1].entrant_callback_index)
    assert regained_state.contact_status(20) is KnowledgeStatus.CURRENT
    contact = regained_state.current_contacts[0]
    assert contact.first_observed_at == gained_state.current_contacts[0].first_observed_at
    assert contact.observation_count > gained_state.current_contacts[0].observation_count
    assert not hasattr(contact, "entrant_id")
    assert not hasattr(contact, "process_id")
    assert not hasattr(contact, "track_id")


def test_callback_projection_preserves_intra_tick_visibility_flapping(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "flap",
        (
            ("A", "oscillator", OSCILLATOR, 0),
            ("B", "anvil", ANVIL, 32),
        ),
        max_ticks=6,
        seed=5,
    )
    assert trace is not None
    projection = analyze_perspective(replay, trace, "A")
    tick_one = [frame for frame in projection.frames if frame.point.tick == 1]
    samples = [frame.visible_contact_addresses for frame in tick_one]
    assert len(set(samples)) > 1
    assert any(frame.gained_contact_addresses for frame in tick_one)
    assert any(frame.staled_contact_addresses for frame in tick_one)

    tick_end = projection.state_at_tick(1)
    assert _contact_addresses(tick_end) == tick_one[-1].visible_contact_addresses
    seen = {address for sample in samples for address in sample}
    for address in seen - set(samples[-1]):
        assert tick_end.contact_status(address) is KnowledgeStatus.STALE

    # Phase 3 deliberately compresses the same callback oscillation to a
    # tick-union detection event. Both views are valid for different jobs.
    detection = [
        event
        for event in analyze_pair(replay, trace).events
        if event.kind in (SpectatorEventKind.DETECTION_GAINED, SpectatorEventKind.DETECTION_LOST)
    ]
    assert [(event.tick, event.kind.value, event.addresses) for event in detection] == [
        (1, "DETECTION_GAINED", (32,))
    ]


def test_end_of_tick_replay_geometry_does_not_override_last_observation(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "geometry_trap",
        (
            ("A", "approacher", APPROACHER, 0),
            ("B", "sleeper", SLEEPER, 32),
        ),
        max_ticks=1,
        seed=5,
    )
    assert trace is not None
    projection = analyze_perspective(replay, trace, "A")
    state = projection.state_at_tick(1)
    snapshot = next(tick for tick in load_schema4_replay(replay).ticks if tick.tick == 1)
    a_sensors = [
        process
        for process in snapshot.processes
        if process.entrant_id == "A" and not process.disrupted
    ]
    b_anchors = [process.anchor for process in snapshot.processes if process.entrant_id == "B"]
    geometry_visible = {
        target
        for sensor in a_sensors
        for target in b_anchors
        if min(abs(sensor.anchor - target), 64 - abs(sensor.anchor - target)) <= sensor.reach
    }
    assert geometry_visible == {32}
    assert state.contact_status(32) is KnowledgeStatus.UNKNOWN
    assert 32 not in _contact_addresses(state)


def test_unsampled_tick_carries_latest_delivered_state_without_fabricating_loss(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "suppressed",
        (
            ("A", "hunter", HUNTER, 0),
            ("B", "oscillator", OSCILLATOR, 32),
        ),
        max_ticks=20,
        seed=11,
    )
    assert trace is not None
    projection = analyze_perspective(replay, trace, "B")
    sampled_ticks = {frame.point.tick for frame in projection.frames}
    silent = next(tick for tick in range(2, projection.last_tick + 1) if tick not in sampled_ticks)
    before = projection.state_at_tick(silent - 1)
    during = projection.state_at_tick(silent)
    assert during.sampled_this_tick is False
    assert during.last_visibility_sample_at == before.last_visibility_sample_at
    assert during.current_contacts == before.current_contacts
    assert during.stale_contacts == before.stale_contacts
    assert during.read_history == before.read_history
    assert during.own_processes == before.own_processes


def test_three_entrant_colocation_remains_one_anonymous_contact(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "colocated",
        (
            ("A", "wide_reader", WIDE_READER, 0),
            ("B", "anvil_b", ANVIL, 32),
            ("C", "colocator", COLOCATOR, 40),
        ),
        max_ticks=1,
        seed=23,
    )
    assert trace is not None
    document = read_trace_v2(trace)
    a_samples = [
        decision.observation.visible_enemy_anchor_addresses
        for decision in document.decisions
        if decision.agent_id == "A"
    ]
    assert (32, 40) in a_samples
    assert (32,) in a_samples
    state = analyze_perspective(replay, trace, "A").state_at_tick(1)
    assert _contact_addresses(state) == (32,)
    assert len(state.current_contacts) == 1
    assert state.read_history
    assert state.read_history[0].owner in {"B", "C"}
    hostile_reads = [
        event
        for event in analyze_pair(replay, trace).events
        if event.kind is SpectatorEventKind.HOSTILE_READ and event.actors == ("A",)
    ]
    assert len(hostile_reads) == 8
    assert all(event.visible_to == ("A",) for event in hostile_reads[:-1])
    assert hostile_reads[-1].visible_to == ()
    assert len(state.read_history) == len(hostile_reads) - 1
    contact = state.current_contacts[0]
    assert not hasattr(contact, "owner")
    assert not hasattr(contact, "entrant_id")
    assert all(
        set(item).isdisjoint({"entrant_id", "process_id", "owner", "target"})
        for item in state_to_dict(state)["current_contacts"]
    )


def test_four_entrant_projection_preserves_multiple_contacts_without_attribution(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "quad",
        (
            ("A", "wide_reader", WIDE_READER, 0),
            ("B", "anvil_b", ANVIL, 16),
            ("C", "anvil_c", ANVIL, 32),
            ("D", "anvil_d", ANVIL, 48),
        ),
        max_ticks=2,
        seed=29,
    )
    assert trace is not None
    a_state = analyze_perspective(replay, trace, "A").state_at_tick(1)
    b_state = analyze_perspective(replay, trace, "B").state_at_tick(1)
    assert _contact_addresses(a_state) == (16, 32, 48)
    assert _contact_addresses(b_state) == ()
    assert all(not hasattr(contact, "entrant_id") for contact in a_state.current_contacts)


def test_read_feedback_becomes_knowledge_only_on_the_next_same_process_callback(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "reads",
        (
            ("A", "read_probe", READ_PROBE, 0),
            ("B", "anvil", ANVIL, 16),
        ),
        max_ticks=1,
        seed=31,
    )
    assert trace is not None
    projection = analyze_perspective(replay, trace, "A")
    assert projection.frames[0].delivered_read is None
    first_delivery = projection.frames[1].delivered_read
    assert first_delivery is not None
    assert first_delivery.sampled_at == projection.frames[0].point
    assert first_delivery.delivered_at == projection.frames[1].point
    assert projection.state_at_callback(0).read_history == ()
    assert projection.state_at_callback(1).read_history == (first_delivery,)

    reads = projection.state_at_tick(1).read_history
    assert len(reads) == 7
    assert (reads[0].normalized_address, reads[0].value, reads[0].owner) == (0, 0xCE, "A")
    assert (reads[1].normalized_address, reads[1].value, reads[1].owner) == (8, 0, None)
    assert (reads[2].normalized_address, reads[2].value, reads[2].owner) == (
        16,
        0xCE,
        "B",
    )
    assert reads[3].applied is False
    assert reads[3].normalized_address is None
    assert reads[3].value is None
    assert reads[3].owner is None

    # All eight A callbacks requested READ, but the final result has no later
    # callback on which the engine can deliver it.
    a_read_decisions = [
        decision
        for decision in read_trace_v2(trace).decisions
        if decision.agent_id == "A"
        and decision.action is not None
        and decision.action.kind == "read"
    ]
    assert len(a_read_decisions) == 8
    assert len(reads) == len(a_read_decisions) - 1


def test_sibling_process_callback_does_not_deliver_pending_read_feedback(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "multi_read",
        (
            ("A", "multi_reader", MULTI_READER, 0),
            ("B", "anvil", ANVIL, 32),
        ),
        max_ticks=1,
        seed=37,
        ruleset_id=RULESET_V4_ALPHA2.ruleset_id,
    )
    assert trace is not None
    projection = analyze_perspective(replay, trace, "A")
    assert [frame.point.process_id for frame in projection.frames[:3]] == [
        "left",
        "right",
        "left",
    ]
    assert projection.frames[0].delivered_read is None
    assert projection.frames[1].delivered_read is None
    delivered = projection.frames[2].delivered_read
    assert delivered is not None
    assert delivered.process_id == "left"
    assert delivered.sampled_at == projection.frames[0].point
    assert delivered.delivered_at == projection.frames[2].point

    state = projection.state_at_tick(1)
    by_process = {process.process_id: process for process in state.own_processes}
    assert set(by_process) == {"left", "right"}
    assert all(process.last_observed_at is not None for process in by_process.values())


def test_read_owner_never_becomes_contact_identity(tmp_path: Path) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "owner_not_contact",
        (
            ("A", "read_probe", READ_PROBE, 0),
            ("B", "anvil", ANVIL, 16),
        ),
        max_ticks=1,
        seed=41,
    )
    assert trace is not None
    state = analyze_perspective(replay, trace, "A").state_at_tick(1)
    foreign = next(read for read in state.read_history if read.owner == "B")
    assert foreign.normalized_address == 16
    contact = next(contact for contact in state.current_contacts if contact.address == 16)
    assert not hasattr(contact, "owner")
    assert not hasattr(contact, "entrant_id")


def test_elimination_and_result_remain_outside_continuing_entrant_perspective(
    tmp_path: Path,
) -> None:
    replay, trace, result = _run_match(
        tmp_path,
        "continuing",
        (
            ("A", "executioner", EXECUTIONER, 0),
            ("B", "sleeper", SLEEPER, 32),
            ("C", "anvil", ANVIL, 64),
        ),
        arena_size=128,
        max_ticks=40,
        seed=43,
    )
    assert trace is not None
    derivation = analyze_pair(replay, trace)
    eliminated = [
        event for event in derivation.events if event.kind is SpectatorEventKind.AGENT_ELIMINATED
    ]
    assert eliminated and eliminated[0].targets == ("B",)
    assert result.ticks_run > eliminated[0].tick

    projection = analyze_perspective(replay, trace, "C")
    state = projection.state_at_tick(eliminated[0].tick)
    payload = state_to_dict(state)
    assert not hasattr(projection, "winner")
    assert not hasattr(state, "events")
    assert not hasattr(state, "eliminated_entrants")
    assert payload["hidden_not_projected"]
    assert all(not hasattr(contact, "entrant_id") for contact in state.current_contacts)


def test_tick_start_end_and_sequence_aware_queries_have_explicit_boundaries(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _duel(tmp_path)
    assert trace is not None
    projection = analyze_perspective(replay, trace, "A")
    start = projection.state_at_tick(1, boundary=TickBoundary.START)
    end = projection.state_at_tick(1, boundary=TickBoundary.END)
    assert start.through_decision_index is None
    assert start.sampled_this_tick is False
    assert end.through_decision_index is not None
    assert end.sampled_this_tick is True

    last_global_at_tick = max(
        index for index, tick in enumerate(projection._decision_ticks) if tick == 1
    )
    callback_state = projection.state_at_decision(last_global_at_tick)
    assert replace(callback_state, boundary=TickBoundary.END) == projection.state_at_tick(1)
    assert replace(projection.state_at_decision(-1), tick=1, boundary=TickBoundary.START) == start


def test_arbitrary_seek_is_path_independent(tmp_path: Path) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "seek",
        (
            ("A", "flyby", FLYBY, 0),
            ("B", "sleeper", SLEEPER, 20),
        ),
        max_ticks=20,
        seed=17,
    )
    assert trace is not None
    projection = analyze_perspective(replay, trace, "A")
    forward = {tick: projection.state_at_tick(tick) for tick in range(21)}
    for tick in (20, 3, 11, 0, 19, 5, 13, 1):
        assert projection.state_at_tick(tick) == forward[tick]
        indices = [
            index
            for index, decision_tick in enumerate(projection._decision_ticks)
            if decision_tick <= tick
        ]
        if indices:
            callback_state = projection.state_at_decision(indices[-1])
            assert replace(callback_state, boundary=TickBoundary.END) == forward[tick]


def test_serialization_and_explanation_are_auditable_and_identity_honest(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _run_match(
        tmp_path,
        "inspect",
        (
            ("A", "read_probe", READ_PROBE, 0),
            ("B", "anvil", ANVIL, 16),
        ),
        max_ticks=1,
        seed=47,
    )
    assert trace is not None
    projection = analyze_perspective(replay, trace, "A")
    records = [json.loads(line) for line in serialize_projection(projection).splitlines()]
    assert records[0]["record_type"] == "perspective_header"
    assert records[0]["contact_identity"] == "anonymous_address_only"
    assert all(record["record_type"] == "perspective_frame" for record in records[1:])

    state = projection.state_at_tick(1)
    state_record = json.loads(serialize_state(state))
    assert state_record["record_type"] == "perspective_state"
    assert state_record["hidden_not_projected"]
    contact = state_record["current_contacts"][0]
    assert set(contact).isdisjoint({"entrant_id", "process_id", "owner", "track_id"})
    explanation = explain_state(state)
    assert "CURRENT CONTACTS" in explanation
    assert "KNOWN READ RESULTS" in explanation
    assert "cell owner: 'B' (not contact identity)" in explanation
    assert "HIDDEN / NOT PROJECTED" in explanation


def test_repeated_projection_is_byte_identical_and_hash_seed_independent(
    tmp_path: Path,
) -> None:
    replay, trace, _result = _duel(tmp_path)
    assert trace is not None
    outputs = {serialize_projection(analyze_perspective(replay, trace, "A")) for _ in range(3)}
    assert len(outputs) == 1

    repository_root = Path(__file__).resolve().parents[2]
    script = repository_root / "tools" / "spectator_project.py"
    digests = set()
    for seed in ("0", "1", "2", "42", "random"):
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                str(replay),
                str(trace),
                "--perspective",
                "A",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        digests.add(hashlib.sha256(completed.stdout.encode()).hexdigest())
    assert len(digests) == 1


def test_repeated_match_execution_yields_identical_projection(tmp_path: Path) -> None:
    streams: set[str] = set()
    outcomes: set[tuple[str | None, int, str]] = set()
    for attempt in range(3):
        replay, trace, result = _duel(tmp_path / str(attempt), seed=53)
        assert trace is not None
        streams.add(serialize_projection(analyze_perspective(replay, trace, "A")))
        outcomes.add(
            (
                result.winner,
                result.ticks_run,
                hashlib.sha256(replay.read_bytes()).hexdigest(),
            )
        )
    assert len(streams) == 1
    assert len(outcomes) == 1


def test_projection_is_observational_and_does_not_change_match_artifacts(
    tmp_path: Path,
) -> None:
    entrants = (
        ("A", "hunter", HUNTER, 0),
        ("B", "anvil", ANVIL, 32),
    )
    untraced_replay, untraced_trace, untraced = _run_match(
        tmp_path,
        "untraced",
        entrants,
        trace=False,
    )
    traced_replay, traced_trace, traced = _run_match(
        tmp_path,
        "traced",
        entrants,
        trace=True,
    )
    assert untraced_trace is None and traced_trace is not None
    assert untraced.winner == traced.winner
    assert untraced.ticks_run == traced.ticks_run
    assert untraced.replay_sha256 == traced.replay_sha256
    assert untraced_replay.read_bytes() == traced_replay.read_bytes()

    before = traced_replay.read_bytes(), traced_trace.read_bytes()
    analyze_perspective(traced_replay, traced_trace, "A")
    assert (traced_replay.read_bytes(), traced_trace.read_bytes()) == before


def test_tool_wrapper_reexports_projection_contract_and_cli_rejects_mismatch(
    tmp_path: Path,
) -> None:
    from battle_engine import spectator_perspective as permanent

    from tools import spectator_project as wrapper

    assert wrapper.analyze_perspective is permanent.analyze_perspective
    assert wrapper.PerspectiveProjection is permanent.PerspectiveProjection
    assert wrapper.serialize_projection is permanent.serialize_projection

    replay_one, trace_one, _result = _duel(tmp_path, "cli_one", seed=59)
    _replay_two, trace_two, _result = _duel(tmp_path, "cli_two", seed=61)
    assert trace_one is not None and trace_two is not None
    repository_root = Path(__file__).resolve().parents[2]
    script = repository_root / "tools" / "spectator_project.py"

    good = subprocess.run(
        [
            sys.executable,
            str(script),
            str(replay_one),
            str(trace_one),
            "--perspective",
            "A",
            "--tick",
            "1",
            "--explain",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert good.returncode == 0
    assert "PERSPECTIVE A" in good.stdout
    assert good.stderr == ""

    bad = subprocess.run(
        [
            sys.executable,
            str(script),
            str(replay_one),
            str(trace_two),
            "--perspective",
            "A",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2
    assert bad.stdout == ""
    assert "binding mismatch" in bad.stderr


def test_perspective_cursor_sequential_and_seeking_equivalence(tmp_path: Path) -> None:
    replay_path, trace_path, _result = _duel(tmp_path, "cursor_duel", seed=88)
    assert trace_path is not None
    projection = analyze_perspective(replay_path, trace_path, "A")
    cursor = projection.cursor()

    # 1. Sequential forward stepping from first_tick to result_ticks
    for tick in range(projection.first_tick, projection.result_ticks + 1):
        direct_state = projection.state_at_tick(tick, boundary=TickBoundary.END)
        cursor_state = cursor.state_at_tick(tick, boundary=TickBoundary.END)
        assert cursor_state == direct_state
        # Repeated call at same tick (e.g. paused frame)
        assert cursor.state_at_tick(tick, boundary=TickBoundary.END) == direct_state

    # 2. Backward stepping
    for tick in range(projection.result_ticks, projection.first_tick - 1, -1):
        direct_state = projection.state_at_tick(tick, boundary=TickBoundary.END)
        cursor_state = cursor.state_at_tick(tick, boundary=TickBoundary.END)
        assert cursor_state == direct_state

    # 3. Arbitrary seeks
    for seek_target in (5, 0, 8, 2, 8, 1, 4):
        if seek_target <= projection.result_ticks:
            direct_state = projection.state_at_tick(seek_target, boundary=TickBoundary.END)
            cursor_state = cursor.state_at_tick(seek_target, boundary=TickBoundary.END)
            assert cursor_state == direct_state

    # 4. START boundary queries
    for tick in range(projection.first_tick, projection.result_ticks + 1):
        direct_start = projection.state_at_tick(tick, boundary=TickBoundary.START)
        cursor_start = cursor.state_at_tick(tick, boundary=TickBoundary.START)
        assert cursor_start == direct_start


def _cursor_case(root: Path):
    """A real multi-process, multi-entrant, co-located match for cursor audits.

    ``A`` declares two processes and issues READs, ``B`` and ``C`` supply the
    contact traffic (including a co-located pair), so one projection exercises
    multi-process own-state, contact gain/loss, co-location, delivered READ
    history, and unsampled ticks together.
    """

    replay_path, trace_path, _result = _run_match(
        root,
        "cursor_multi",
        (
            ("A", "multi_reader", MULTI_READER, 0),
            ("B", "anvil_b", ANVIL, 32),
            ("C", "colocator", COLOCATOR, 40),
        ),
        max_ticks=12,
        seed=23,
    )
    assert trace_path is not None
    return analyze_perspective(replay_path, trace_path, "A")


def test_perspective_cursor_matches_projection_across_every_tick_and_boundary(
    tmp_path: Path,
) -> None:
    """The cursor must equal the reference fold for every supported query.

    Phase 5's cursor was reconstructed after the original implementation was
    lost, so equivalence is proven exhaustively against
    ``PerspectiveProjection.state_at_tick`` rather than sampled.
    """

    projection = _cursor_case(tmp_path)
    ticks = range(projection.first_tick, projection.result_ticks + 1)
    assert len(projection.declarations) == 2, "multi-process own-state coverage required"

    # Interleaving both boundaries at the same tick exercises the bisect_left /
    # bisect_right split, including a START query that must *not* include a
    # frame the immediately preceding END query already folded.
    cursor = projection.cursor()
    for tick in ticks:
        for boundary in (TickBoundary.END, TickBoundary.START, TickBoundary.END):
            assert cursor.state_at_tick(tick, boundary=boundary) == projection.state_at_tick(
                tick, boundary=boundary
            )

    # An adversarial access pattern: restart, large forward jump, backward
    # seek, repeated same-tick reads, and end-of-match, all on one retained
    # cursor whose accumulators must reset correctly on every backward move.
    last = projection.result_ticks
    first = projection.first_tick
    middle = (first + last) // 2
    pattern = (
        last, first, last, middle, first, first, last, middle, middle, first, last
    )
    seeking = projection.cursor()
    for tick in pattern:
        assert seeking.state_at_tick(tick) == projection.state_at_tick(tick)

    # A cursor driven only sequentially and one driven only by seeks must agree
    # at the same tick: the cursor's own history may not influence its answer.
    sequential = projection.cursor()
    for tick in ticks:
        sequential.state_at_tick(tick)
    assert sequential.state_at_tick(middle) == seeking.state_at_tick(middle)


def test_perspective_cursor_results_never_mutate_under_later_advancement(
    tmp_path: Path,
) -> None:
    """A returned state must not change when the cursor advances afterwards.

    The cursor folds through retained mutable accumulators.  If a returned
    ``PerspectiveState`` aliased those accumulators, a rendered frame's
    contacts, READ history, or own-process anchors could silently change
    later in playback.  This is the regression guard for that aliasing.
    """

    projection = _cursor_case(tmp_path)
    cursor = projection.cursor()

    captured: list[tuple[int, object, str]] = []
    for tick in range(projection.first_tick, projection.result_ticks + 1):
        state = cursor.state_at_tick(tick)
        # serialize_state is a full value snapshot taken *before* any further
        # advancement, so a later in-place mutation would diverge from it.
        captured.append((tick, state, serialize_state(state)))

    # Drive the cursor across the whole match again, forwards and backwards,
    # so every accumulator is folded, reset, and re-folded after capture.
    for tick in range(projection.first_tick, projection.result_ticks + 1):
        cursor.state_at_tick(tick)
    for tick in range(projection.result_ticks, projection.first_tick - 1, -1):
        cursor.state_at_tick(tick)

    for tick, state, snapshot in captured:
        assert serialize_state(state) == snapshot, f"cursor state at tick {tick} mutated"
        assert state == projection.state_at_tick(tick)

    # The same guarantee must hold for the cached same-tick result, which is
    # returned by identity rather than rebuilt.
    repeated = cursor.state_at_tick(projection.result_ticks)
    again = cursor.state_at_tick(projection.result_ticks)
    assert repeated is again
    assert repeated == projection.state_at_tick(projection.result_ticks)


def test_perspective_cursor_rejects_queries_outside_the_projection_range(
    tmp_path: Path,
) -> None:
    """Range and type validation must match the projection it stands in for."""

    projection = _cursor_case(tmp_path)
    cursor = projection.cursor()
    for bad_tick in (projection.first_tick - 1, projection.result_ticks + 1):
        with pytest.raises(ValueError):
            cursor.state_at_tick(bad_tick)
        with pytest.raises(ValueError):
            projection.state_at_tick(bad_tick)
    with pytest.raises(ValueError):
        cursor.state_at_tick(projection.first_tick, boundary=TickBoundary.CALLBACK)
    with pytest.raises(TypeError):
        cursor.state_at_tick(True)
