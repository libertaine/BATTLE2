"""Phase 3: replay/trace pair verification and deterministic semantic derivation.

Every test here runs a real deterministic v4 match and asserts on what that
execution actually produced. Phase 2 shipped a trace whose central record type
was never written by any match while its tests stayed green, because those
tests asserted that artifacts existed and had a plausible shape. Nothing in
this file is allowed to pass without the behavior under test having occurred:
assertions name exact ticks, addresses, owners, audiences, and orderings taken
from the match, not counts or truthiness.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from battle_engine.agent_trace import (
    TRACE_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION_V2,
    read_trace_v2,
)
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1
from battle_engine.spectator_derivation import (
    PairBindingError,
    PairConsistencyError,
    SpectatorEvent,
    SpectatorEventKind,
    analyze_pair,
    derive_events,
    serialize_derivation,
    verify_pair,
)

_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

# A stationary entrant that rewrites one cell of its own core every action.
# Never hostile, never moves: it exists to be found and hit.
ANVIL = _IMPORTS + '''
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
'''

# Walks toward the far side, then reads and overwrites whatever it detects.
HUNTER = _IMPORTS + '''
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
'''

# Two processes whose movement drags the entrant's visible set in and out of
# range several times inside a single tick.
OSCILLATOR = _IMPORTS + '''
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
'''

# Erases a whole enemy core region once it has seen it: produces a real
# core-capture elimination rather than a tick-limit tie.
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

# Never leaves home and cannot see past its own doorstep.
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

# Crashes on a known tick, forfeiting the match.
BRITTLE = _IMPORTS + '''
class Brittle:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="p", reach=8, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        if obs.current_tick == 3:
            raise ValueError("scripted crash")
        return AgentAction(ActionKindV2.MOVE, 1)
def create_agent() -> AgentV2:
    return Brittle()
'''


def _write_agent(root: Path, name: str, source: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.py").write_text(source)
    (directory / "agent.yaml").write_text(
        f"name: {name}\ndescription: Phase 3 fixture\nversion: '1.0'\napi_version: 2\n"
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
    trace: bool = True,
) -> tuple[Path, Path | None, object]:
    """Execute one real traced v4 match and return its artifact paths."""

    name_a, source_a, start_a = entrant_a
    name_b, source_b, start_b = entrant_b
    _write_agent(root, name_a, source_a)
    _write_agent(root, name_b, source_b)
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
        entrants=(
            MatchEntrant.python("A", "Entrant A", start_a, resolve_agent(root, name_a)),
            MatchEntrant.python("B", "Entrant B", start_b, resolve_agent(root, name_b)),
        ),
        max_ticks=max_ticks,
        replay_path=replay_path,
        trace_path=trace_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    result = NativeMatchService().run(request)
    return replay_path, trace_path, result


def _hunt(root: Path, label: str = "hunt", *, max_ticks: int = 12, seed: int = 11):
    return _run_match(
        root,
        label,
        ("hunter", HUNTER, 0),
        ("anvil", ANVIL, 32),
        arena_size=64,
        max_ticks=max_ticks,
        seed=seed,
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


def _of_kind(events, kind: SpectatorEventKind) -> list[SpectatorEvent]:
    return [event for event in events if event.kind is kind]


# ---------------------------------------------------------------------------
# 1. Phase 2 prerequisite: the trace's central record type really is emitted
# ---------------------------------------------------------------------------


def test_a_known_running_process_emits_decision_records_with_real_content(
    tmp_path: Path,
) -> None:
    """Re-prove the repaired Phase 2 wiring before Phase 3 depends on it.

    Phase 2's own defect was that ``DecisionRecordV2`` was never written at
    all while a test asserting ``len(lines) > 2`` still passed. This asserts
    the opposite way round: a specific named process, on a specific tick,
    must have produced a record whose observation and applied result carry
    the exact values that execution implies.
    """

    replay_path, trace_path, result = _hunt(tmp_path)
    assert trace_path is not None
    document = read_trace_v2(trace_path)

    assert document.header.schema_version == TRACE_SCHEMA_VERSION_V2
    assert {(d.agent_id, d.process_id, d.reach) for d in document.declarations} == {
        ("A", "eye", 10),
        ("B", "body", 2),
    }

    # Every entrant gets `instr_per_tick` action slots per tick, so an
    # uninterrupted entrant produces exactly 8 decisions per tick. Anything
    # materially below that means callbacks are being dropped, not that the
    # trace is merely "non-empty".
    per_tick = Counter(
        (d.agent_id, d.observation.current_tick) for d in document.decisions
    )
    assert all(per_tick[("A", tick)] == 8 for tick in range(1, result.ticks_run + 1))
    # B loses its remaining two slots on tick 1 because A's write lands on
    # B's anchor and disrupts it mid-tick, and is fully suppressed on every
    # odd tick after that -- so the count is a statement about the mechanic,
    # not a floor.
    assert per_tick[("B", 1)] == 6
    assert per_tick[("B", 2)] == 8
    assert per_tick[("B", 3)] == 0
    assert len(document.decisions) == 150

    first = document.decisions[0]
    assert first.agent_id == "A"
    assert first.process_id == "eye"
    assert first.observation.current_tick == 1
    assert first.observation.self_process_id == "eye"
    assert first.observation.self_anchor == 0
    assert first.observation.self_reach == 10
    assert first.observation.own_core_base == 0
    assert first.observation.own_core_size == 8
    assert first.observation.visible_enemy_anchor_addresses == ()
    assert first.action is not None
    assert (first.action.kind, first.action.operand) == ("move", 4)
    assert first.applied_result is not None
    assert first.applied_result.status == "APPLIED"
    assert first.applied_result.normalized_address == 4

    # B is stationary and writes its own core base every action, so its very
    # first decision has a fully predictable applied result.
    b_first = next(d for d in document.decisions if d.agent_id == "B")
    assert b_first.process_id == "body"
    assert b_first.observation.own_core_base == 32
    assert b_first.action is not None
    assert (b_first.action.kind, b_first.action.operand, b_first.action.value) == (
        "write",
        32,
        0xCE,
    )
    assert b_first.applied_result is not None
    assert b_first.applied_result.normalized_address == 32

    binding = document.binding
    assert binding is not None
    assert binding.replay_sha256 == hashlib.sha256(replay_path.read_bytes()).hexdigest()
    assert binding.entrant_identities == ("A", "B")
    assert binding.ruleset_id == RULESET_V4_ALPHA1.ruleset_id


def test_applied_read_records_the_owner_and_value_the_engine_returned(
    tmp_path: Path,
) -> None:
    """A hostile READ's applied result must carry the real cell contents."""

    _replay, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    document = read_trace_v2(trace_path)

    hostile = [
        d
        for d in document.decisions
        if d.applied_result is not None
        and d.applied_result.status == "APPLIED"
        and d.applied_result.read_owner is not None
        and d.applied_result.read_owner != d.agent_id
    ]
    assert hostile, "the hunter is expected to read the anvil's core"
    for decision in hostile:
        assert decision.agent_id == "A"
        assert decision.applied_result is not None
        assert decision.applied_result.read_owner == "B"
        # B only ever writes 0xCE into its own core base.
        assert decision.applied_result.normalized_address == 32
        assert decision.applied_result.read_value == 0xCE


def test_disrupted_and_rejected_quota_statuses_are_never_reachable(
    tmp_path: Path,
) -> None:
    """Confirm the Phase 2 review's unreachable-status finding on real matches.

    ``_select_active_process``/``_effective_process_quotas`` filter disrupted
    and over-quota processes *before* ``act()`` is called, so no observation
    is delivered and no decision record can exist for either case. This
    verifies the contract rather than manufacturing records to exercise the
    enum values.
    """

    statuses: Counter[str] = Counter()
    for label, builder in (("hunt", _hunt), ("kill", _kill)):
        _replay, trace_path, _result = builder(tmp_path, label)
        assert trace_path is not None
        for decision in read_trace_v2(trace_path).decisions:
            statuses[
                decision.applied_result.status
                if decision.applied_result is not None
                else "<none>"
            ] += 1

    assert statuses["DISRUPTED"] == 0
    assert statuses["REJECTED_QUOTA"] == 0
    assert statuses["APPLIED"] > 0
    # Processes really were disrupted in these matches -- the statuses above
    # are absent because disruption is expressed by withholding the callback,
    # not by a decision status.
    _replay, _trace, _result = _kill(tmp_path, "kill_disruption_check")
    replay_text = (tmp_path / "kill_disruption_check" / "replay.jsonl").read_text()
    assert '"disrupted":true' in replay_text.replace(" ", "")


# ---------------------------------------------------------------------------
# 2. Replay/trace binding verification
# ---------------------------------------------------------------------------


def test_verify_pair_accepts_a_matching_replay_and_trace(tmp_path: Path) -> None:
    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    binding = verify_pair(replay_path, trace_path)
    assert binding.replay_sha256 == hashlib.sha256(replay_path.read_bytes()).hexdigest()
    assert binding.entrant_identities == ("A", "B")
    assert binding.ruleset_id == RULESET_V4_ALPHA1.ruleset_id
    assert binding.match_id.startswith("match_")


def test_verify_pair_rejects_a_trace_bound_to_a_different_match(tmp_path: Path) -> None:
    replay_one, _trace_one, _r1 = _hunt(tmp_path, "one", seed=11)
    _replay_two, trace_two, _r2 = _hunt(tmp_path, "two", seed=99)
    assert trace_two is not None
    with pytest.raises(PairBindingError, match="binding mismatch"):
        verify_pair(replay_one, trace_two)


def test_verify_pair_rejects_modified_replay_bytes(tmp_path: Path) -> None:
    """A single flipped byte in the replay must invalidate the pair."""

    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    verify_pair(replay_path, trace_path)

    raw = replay_path.read_bytes()
    index = raw.index(b'"tick"')
    tampered = raw[:index] + b'"tick"' + raw[index + 6 :] + b" "
    replay_path.write_bytes(tampered)
    with pytest.raises(PairBindingError, match="binding mismatch"):
        verify_pair(replay_path, trace_path)


def test_verify_pair_rejects_a_trace_with_no_binding_record(tmp_path: Path) -> None:
    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["record_type"] == "binding"
    trace_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(PairBindingError, match="no binding record"):
        verify_pair(replay_path, trace_path)


def test_verify_pair_distinguishes_a_malformed_trace_from_a_mismatch(
    tmp_path: Path,
) -> None:
    """A structurally broken binding is a different failure from a wrong one."""

    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    binding = json.loads(lines[-1])
    del binding["replay_sha256"]
    lines[-1] = json.dumps(binding, sort_keys=True)
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(PairBindingError, match="unusable API-v2 trace"):
        verify_pair(replay_path, trace_path)


def test_verify_pair_rejects_a_v1_schema_trace(tmp_path: Path) -> None:
    """V1 traces carry no API-v2 observations and must not be analyzed."""

    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["schema_version"] = TRACE_SCHEMA_VERSION
    lines[0] = json.dumps(header, sort_keys=True)
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(PairBindingError, match="unusable API-v2 trace"):
        verify_pair(replay_path, trace_path)


def test_verify_pair_reports_a_missing_replay_clearly(tmp_path: Path) -> None:
    _replay, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    with pytest.raises(PairBindingError, match="cannot read replay"):
        verify_pair(tmp_path / "absent.jsonl", trace_path)


# ---------------------------------------------------------------------------
# 3. Pair consistency beyond the digest
# ---------------------------------------------------------------------------


def test_derivation_rejects_a_trace_whose_actions_contradict_the_replay(
    tmp_path: Path,
) -> None:
    """Binding proves provenance; the state cross-check proves agreement.

    A trace edited to claim a write landed somewhere it did not still hashes
    against the same replay -- the binding covers the replay's bytes, not the
    trace's -- so the analyzer must catch the contradiction itself.
    """

    replay_path, trace_path, _result = _kill(tmp_path)
    assert trace_path is not None
    analyze_pair(replay_path, trace_path)

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        record = json.loads(line)
        if (
            record.get("record_type") == "decision_v2"
            and (record.get("applied_result") or {}).get("status") == "APPLIED"
            and (record.get("action") or {}).get("kind") == "write"
        ):
            record["applied_result"]["normalized_address"] += 1
            lines[index] = json.dumps(record, sort_keys=True)
            break
    else:  # pragma: no cover -- the fixture always contains an applied write
        pytest.fail("expected at least one applied WRITE decision to tamper with")
    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    binding = verify_pair(replay_path, trace_path)
    with pytest.raises(PairConsistencyError):
        derive_events(binding)


# ---------------------------------------------------------------------------
# 4. End-to-end event evidence, one accepted kind at a time
# ---------------------------------------------------------------------------


def test_core_capture_match_derives_the_exact_expected_event_stream(
    tmp_path: Path,
) -> None:
    """One short real match, asserted event by event.

    ``EXECUTIONER`` walks until it detects ``SLEEPER``'s anchor, then strips
    that entrant's eight core cells one per action. This asserts the whole
    resulting stream -- kind, tick, sequence, actors, targets, address,
    remaining core cells, and audience -- rather than counting events, so a
    derivation that silently stopped running could not pass it.
    """

    replay_path, trace_path, result = _kill(tmp_path)
    assert trace_path is not None
    assert result.winner == "A"
    assert result.ticks_run == 2

    events = analyze_pair(replay_path, trace_path).events
    summary = [
        (e.tick, e.sequence, e.kind.value, e.actors, e.targets, e.address, e.visible_to)
        for e in events
    ]
    assert summary == [
        (1, 0, "DETECTION_GAINED", ("A",), (), None, ("A",)),
        (1, 1, "HOSTILE_WRITE", ("A",), ("B",), 33, ()),
        (1, 2, "FIRST_HOSTILE_WRITE", ("A",), ("B",), 33, ()),
        (1, 3, "CORE_CELL_LOST", ("A",), ("B",), 33, ()),
        (1, 4, "EFFECTIVE_MOVE", ("A",), (), None, ("A",)),
        (2, 0, "HOSTILE_WRITE", ("A",), ("B",), 34, ()),
        (2, 1, "CORE_CELL_LOST", ("A",), ("B",), 34, ()),
        (2, 2, "HOSTILE_WRITE", ("A",), ("B",), 35, ()),
        (2, 3, "CORE_CELL_LOST", ("A",), ("B",), 35, ()),
        (2, 4, "HOSTILE_WRITE", ("A",), ("B",), 36, ()),
        (2, 5, "CORE_CELL_LOST", ("A",), ("B",), 36, ()),
        (2, 6, "HOSTILE_WRITE", ("A",), ("B",), 37, ()),
        (2, 7, "CORE_CELL_LOST", ("A",), ("B",), 37, ()),
        (2, 8, "HOSTILE_WRITE", ("A",), ("B",), 38, ()),
        (2, 9, "CORE_CELL_LOST", ("A",), ("B",), 38, ()),
        (2, 10, "HOSTILE_WRITE", ("A",), ("B",), 39, ()),
        (2, 11, "CORE_CELL_LOST", ("A",), ("B",), 39, ()),
        (2, 12, "HOSTILE_WRITE", ("A",), ("B",), 32, ()),
        (2, 13, "CORE_CELL_LOST", ("A",), ("B",), 32, ()),
        (2, 14, "PROCESS_DISRUPTED", ("A",), ("B",), 32, ()),
        (2, 15, "AGENT_ELIMINATED", ("A",), ("B",), None, ()),
        (2, 16, "MATCH_ENDED", (), (), None, ()),
        (2, 17, "VICTORY", ("A",), (), None, ()),
    ]

    # The core-loss countdown is the derivation's own arithmetic, checked
    # against the mechanic that actually ends the match: an entrant dies when
    # it owns zero cells of its core.
    assert [e.remaining_core_cells for e in _of_kind(events, SpectatorEventKind.CORE_CELL_LOST)] == [
        7,
        6,
        5,
        4,
        3,
        2,
        1,
        0,
    ]
    elimination = _of_kind(events, SpectatorEventKind.AGENT_ELIMINATED)[0]
    assert elimination.cause == "kill"
    victory = _of_kind(events, SpectatorEventKind.VICTORY)[0]
    assert victory.actors == ("A",)
    assert victory.termination_reason == "last_agent_standing"
    assert _of_kind(events, SpectatorEventKind.MATCH_ENDED)[0].termination_reason == (
        "last_agent_standing"
    )


def test_detection_and_hostile_read_events_carry_engine_delivered_values(
    tmp_path: Path,
) -> None:
    """Detection names addresses; a hostile read names the owner and byte."""

    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    derivation = analyze_pair(replay_path, trace_path, with_provenance=True)

    gained = _of_kind(derivation.events, SpectatorEventKind.DETECTION_GAINED)
    assert len(gained) == 1
    # A closes from anchor 0 in steps of 4 and is first told about the
    # occupied cell 32 partway through tick 1, at anchor 24 (reach 10).
    assert gained[0].tick == 1
    assert gained[0].actors == ("A",)
    assert gained[0].addresses == (32,)
    assert gained[0].visible_to == ("A",)
    # The engine hands over occupied addresses only. Naming *which* opponent
    # occupies them would be information entrant A was never given.
    assert gained[0].targets == ()

    first_read = _of_kind(derivation.events, SpectatorEventKind.FIRST_HOSTILE_READ)
    assert len(first_read) == 1
    assert first_read[0].tick == 2
    assert first_read[0].actors == ("A",)
    assert first_read[0].targets == ("B",)
    assert first_read[0].targets == ("B",)
    assert first_read[0].address == 32
    assert first_read[0].read_value == 0xCE
    assert first_read[0].visible_to == ("A",)
    assert first_read[0].process_id == "eye"

    reads = _of_kind(derivation.events, SpectatorEventKind.HOSTILE_READ)
    assert all(event.targets == ("B",) and event.read_value == 0xCE for event in reads)
    assert first_read[0].tick == min(event.tick for event in reads)


def test_hostile_write_names_the_owner_it_displaced(tmp_path: Path) -> None:
    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    events = analyze_pair(replay_path, trace_path).events

    writes = _of_kind(events, SpectatorEventKind.HOSTILE_WRITE)
    assert writes, "the hunter is expected to overwrite the anvil's core"

    # Cell 32 is contested: A overwrites B's core base, B rebuilds it, and
    # each side's write is hostile against whoever held the cell last. The
    # displaced owner is reconstructed, never assumed from who started with
    # the cell.
    by_actor = {("A", "B", 0x5A): 0, ("B", "A", 0xCE): 0}
    for event in writes:
        assert event.address == 32
        assert event.visible_to == ()
        assert event.previous_owner == event.targets[0]
        assert event.actors[0] != event.targets[0]
        by_actor[(event.actors[0], event.targets[0], event.value)] += 1
    assert all(count > 0 for count in by_actor.values()), by_actor

    first = _of_kind(events, SpectatorEventKind.FIRST_HOSTILE_WRITE)
    assert {(event.actors, event.targets) for event in first} == {
        (("A",), ("B",)),
        (("B",), ("A",)),
    }
    # Each FIRST_ marker must sit on that attacker's earliest hostile write.
    for marker in first:
        earliest = min(
            (event.tick, event.sequence)
            for event in writes
            if event.actors == marker.actors
        )
        assert (marker.tick, marker.sequence) == (earliest[0], earliest[1] + 1)


def test_writing_an_unowned_cell_is_not_a_hostile_event(tmp_path: Path) -> None:
    """Claiming neutral ground is territory, not aggression."""

    replay_path, trace_path, _result = _run_match(
        tmp_path,
        "neutral",
        ("anvil", ANVIL, 0),
        ("anvil", ANVIL, 32),
        arena_size=64,
        max_ticks=6,
        seed=3,
    )
    assert trace_path is not None
    document = read_trace_v2(trace_path)
    applied_writes = [
        d
        for d in document.decisions
        if d.applied_result is not None and d.applied_result.status == "APPLIED"
    ]
    assert applied_writes, "both entrants write every action"

    events = analyze_pair(replay_path, trace_path).events
    assert _of_kind(events, SpectatorEventKind.HOSTILE_WRITE) == []
    assert _of_kind(events, SpectatorEventKind.CORE_CELL_LOST) == []
    assert [e.kind for e in events] == [SpectatorEventKind.MATCH_ENDED]


def test_process_disruption_is_attributed_to_the_write_that_caused_it(
    tmp_path: Path,
) -> None:
    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    events = analyze_pair(replay_path, trace_path, with_provenance=True).events

    disruptions = _of_kind(events, SpectatorEventKind.PROCESS_DISRUPTED)
    assert disruptions, "writing onto the anvil's anchor must disrupt it"
    for event in disruptions:
        assert event.actors == ("A",)
        assert event.targets == ("B",)
        assert event.process_id == "body"
        assert event.address == 32
        assert event.visible_to == ()
        assert event.provenance is not None
        assert event.provenance.rule == "applied_write_on_enemy_process_anchor"

    # One event per tick per victim process: repeated hits inside a tick
    # re-arm the engine's timer but do not put an already-suppressed process
    # out of action a second time.
    per_tick = Counter((event.tick, event.process_id) for event in disruptions)
    assert set(per_tick.values()) == {1}


def test_eliminated_process_anchor_is_not_a_later_disruption_target(
    tmp_path: Path,
) -> None:
    """A retained replay anchor is not evidence that its entrant is alive.

    Schema 4 keeps every declared process in later tick snapshots after core
    capture. Runtime disruption eligibility, however, excludes a dead
    entrant immediately. The derivation must retain that anchor for replay
    agreement without treating it as a live target on subsequent ticks.
    """

    for name, source in (
        ("executioner", EXECUTIONER),
        ("sleeper", SLEEPER),
        ("anvil", ANVIL),
    ):
        _write_agent(tmp_path, name, source)
    run = tmp_path / "continuing_after_elimination"
    run.mkdir(parents=True, exist_ok=True)
    request = MatchRequest(
        config=Config(
            seed=43,
            arena_size=128,
            instr_per_tick=8,
            win_mode="capture",
            weights=Weights(),
        ),
        entrants=(
            MatchEntrant.python("A", "A", 0, resolve_agent(tmp_path, "executioner")),
            MatchEntrant.python("B", "B", 32, resolve_agent(tmp_path, "sleeper")),
            MatchEntrant.python("C", "C", 64, resolve_agent(tmp_path, "anvil")),
        ),
        max_ticks=4,
        replay_path=run / "replay.jsonl",
        trace_path=run / "trace.jsonl",
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    NativeMatchService().run(request)

    derivation = analyze_pair(run / "replay.jsonl", run / "trace.jsonl")
    eliminated = _of_kind(derivation.events, SpectatorEventKind.AGENT_ELIMINATED)
    assert [(event.tick, event.targets) for event in eliminated] == [(2, ("B",))]
    assert derivation.result_ticks == 4
    assert not any(
        event.kind is SpectatorEventKind.PROCESS_DISRUPTED
        and event.targets == ("B",)
        and event.tick > 2
        for event in derivation.events
    )


def test_forfeit_is_reported_with_its_engine_reason_and_the_resulting_victory(
    tmp_path: Path,
) -> None:
    replay_path, trace_path, result = _run_match(
        tmp_path,
        "forfeit",
        ("brittle", BRITTLE, 0),
        ("anvil", ANVIL, 32),
        arena_size=64,
        max_ticks=10,
        seed=9,
    )
    assert trace_path is not None
    assert result.winner == "B"
    events = analyze_pair(replay_path, trace_path).events

    forfeits = _of_kind(events, SpectatorEventKind.AGENT_FORFEITED)
    assert len(forfeits) == 1
    assert forfeits[0].tick == 3
    assert forfeits[0].targets == ("A",)
    assert forfeits[0].cause == "forfeit"
    assert forfeits[0].reason == "agent_action_invalid"
    assert forfeits[0].visible_to == ()

    victory = _of_kind(events, SpectatorEventKind.VICTORY)
    assert len(victory) == 1
    assert victory[0].actors == ("B",)
    assert victory[0].tick == result.ticks_run


def test_effective_move_reports_net_anchor_change_not_each_action(
    tmp_path: Path,
) -> None:
    """A process that ends a tick where it started produces no move event."""

    replay_path, trace_path, _result = _run_match(
        tmp_path,
        "oscillate",
        ("oscillator", OSCILLATOR, 0),
        ("anvil", ANVIL, 32),
        arena_size=64,
        max_ticks=6,
        seed=5,
    )
    assert trace_path is not None
    document = read_trace_v2(trace_path)
    moves_taken = sum(
        1
        for d in document.decisions
        if d.action is not None and d.action.kind == "move" and d.agent_id == "A"
    )
    assert moves_taken >= 40, "the oscillator moves on every one of its actions"

    events = analyze_pair(replay_path, trace_path).events
    move_events = _of_kind(events, SpectatorEventKind.EFFECTIVE_MOVE)
    # Both processes return to their starting anchor at the end of every tick
    # after the first, so 48 executed MOVE actions collapse to two net moves.
    assert len(move_events) == 2
    assert {(e.actors, e.process_id, e.from_address, e.to_address) for e in move_events} == {
        (("A",), "near", 0, 20),
        (("A",), "far", 0, 20),
    }
    assert all(event.visible_to == ("A",) for event in move_events)


# ---------------------------------------------------------------------------
# 5. Detection granularity and sampling
# ---------------------------------------------------------------------------


def test_intra_tick_visibility_oscillation_does_not_become_spectator_events(
    tmp_path: Path,
) -> None:
    """The v4 engine re-evaluates visibility before *every* callback.

    A process moving in and out of range inside one tick makes its entrant's
    delivered visible set flip several times within that tick. Deriving
    detection per decision would emit that flapping as gained/lost events; the
    union-per-tick rule must not.
    """

    replay_path, trace_path, _result = _run_match(
        tmp_path,
        "flap",
        ("oscillator", OSCILLATOR, 0),
        ("anvil", ANVIL, 32),
        arena_size=64,
        max_ticks=6,
        seed=5,
    )
    assert trace_path is not None
    document = read_trace_v2(trace_path)

    # Prove the flapping is real before asserting it is suppressed.
    tick_one = [
        d.observation.visible_enemy_anchor_addresses
        for d in document.decisions
        if d.agent_id == "A" and d.observation.current_tick == 1
    ]
    transitions = sum(
        1 for before, after in itertools.pairwise(tick_one) if before != after
    )
    assert transitions >= 3, f"expected intra-tick visibility flapping, saw {tick_one}"

    events = analyze_pair(replay_path, trace_path).events
    detection = [
        e
        for e in events
        if e.kind in (SpectatorEventKind.DETECTION_GAINED, SpectatorEventKind.DETECTION_LOST)
    ]
    assert [(e.tick, e.kind.value, e.addresses) for e in detection] == [
        (1, "DETECTION_GAINED", (32,))
    ]


def test_a_tick_with_no_callbacks_does_not_fabricate_detection_loss(
    tmp_path: Path,
) -> None:
    """A fully disrupted entrant is unsampled, not blind.

    When every one of an entrant's processes is disrupted, the runtime filters
    them out before ``act()`` and that entrant receives no observation at all
    for the tick. Treating the resulting silence as "sees nothing" would emit
    a DETECTION_LOST the entrant never experienced.
    """

    replay_path, trace_path, _result = _run_match(
        tmp_path,
        "suppressed",
        ("hunter", HUNTER, 0),
        ("oscillator", OSCILLATOR, 32),
        arena_size=64,
        max_ticks=20,
        seed=11,
    )
    assert trace_path is not None
    document = read_trace_v2(trace_path)

    acting_ticks = {
        (d.agent_id, d.observation.current_tick) for d in document.decisions
    }
    all_ticks = {d.observation.current_tick for d in document.decisions}
    silent = sorted(tick for tick in all_ticks if ("B", tick) not in acting_ticks)
    assert silent, "expected at least one tick where B is fully disrupted"

    events = analyze_pair(replay_path, trace_path).events
    b_detection = [
        e
        for e in events
        if e.actors == ("B",)
        and e.kind in (SpectatorEventKind.DETECTION_GAINED, SpectatorEventKind.DETECTION_LOST)
    ]
    assert all(event.tick not in silent for event in b_detection), (
        f"detection events derived on unsampled ticks {silent}: "
        f"{[(e.tick, e.kind.value) for e in b_detection]}"
    )


def test_detection_lost_is_emitted_when_contact_genuinely_ends(
    tmp_path: Path,
) -> None:
    """Suppressing flapping must not suppress a real loss of contact."""

    flyby = _IMPORTS + '''
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
'''
    replay_path, trace_path, _result = _run_match(
        tmp_path,
        "window",
        ("flyby", flyby, 0),
        ("sleeper", SLEEPER, 20),
        arena_size=64,
        max_ticks=20,
        seed=17,
    )
    assert trace_path is not None
    events = analyze_pair(replay_path, trace_path).events
    windows = [
        (e.tick, e.kind.value, e.actors[0])
        for e in events
        if e.kind in (SpectatorEventKind.DETECTION_GAINED, SpectatorEventKind.DETECTION_LOST)
    ]
    assert windows == [
        (3, "DETECTION_GAINED", "A"),
        (3, "DETECTION_GAINED", "B"),
        (4, "DETECTION_LOST", "B"),
        (5, "DETECTION_LOST", "A"),
        (11, "DETECTION_GAINED", "A"),
        (11, "DETECTION_GAINED", "B"),
        (12, "DETECTION_LOST", "B"),
        (13, "DETECTION_LOST", "A"),
        (19, "DETECTION_GAINED", "A"),
        (19, "DETECTION_GAINED", "B"),
        (20, "DETECTION_LOST", "B"),
    ]


def test_derivation_holds_for_more_than_two_entrants(tmp_path: Path) -> None:
    """Nothing in the model assumes a duel.

    The state cross-check inside the derivation compares reconstructed
    ownership, anchors, and disruption against the replay on every tick, so a
    four-entrant match completing without :class:`PairConsistencyError` is
    itself the assertion that the reconstruction stayed exact.
    """

    for name, source in (("hunter", HUNTER), ("anvil", ANVIL)):
        _write_agent(tmp_path, name, source)
    run = tmp_path / "quad"
    run.mkdir(parents=True, exist_ok=True)
    request = MatchRequest(
        config=Config(
            seed=8, arena_size=64, instr_per_tick=8, win_mode="capture", weights=Weights()
        ),
        entrants=(
            MatchEntrant.python("A", "A", 0, resolve_agent(tmp_path, "hunter")),
            MatchEntrant.python("B", "B", 16, resolve_agent(tmp_path, "anvil")),
            MatchEntrant.python("C", "C", 32, resolve_agent(tmp_path, "hunter")),
            MatchEntrant.python("D", "D", 48, resolve_agent(tmp_path, "anvil")),
        ),
        max_ticks=12,
        replay_path=run / "replay.jsonl",
        trace_path=run / "trace.jsonl",
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    NativeMatchService().run(request)

    derivation = analyze_pair(run / "replay.jsonl", run / "trace.jsonl")
    assert derivation.binding.entrant_identities == ("A", "B", "C", "D")
    actors = {event.actors[0] for event in derivation.events if event.actors}
    assert {"A", "C"} <= actors, "both hunters should register hostile activity"
    hostile = _of_kind(derivation.events, SpectatorEventKind.HOSTILE_WRITE)
    # Each hunter reaches only its nearest neighbour, and each anvil rebuilds
    # the contested cell, so aggression pairs up A<->B and C<->D with no
    # cross-pair contact -- attribution never bleeds between simultaneous
    # fights.
    assert {(e.actors[0], e.targets[0]) for e in hostile} == {
        ("A", "B"),
        ("B", "A"),
        ("C", "D"),
        ("D", "C"),
    }
    identities = [(event.tick, event.sequence) for event in derivation.events]
    assert len(set(identities)) == len(identities)


def test_derivation_handles_a_core_region_that_wraps_the_arena_end(
    tmp_path: Path,
) -> None:
    """Core membership and ownership must follow the arena's circularity."""

    replay_path, trace_path, _result = _run_match(
        tmp_path,
        "wrapped",
        ("hunter", HUNTER, 60),
        ("anvil", ANVIL, 30),
        arena_size=64,
        max_ticks=12,
        seed=4,
    )
    assert trace_path is not None
    derivation = analyze_pair(replay_path, trace_path)

    # A's core starts at 60 and wraps: 60, 61, 62, 63, 0, 1, 2, 3.
    document = read_trace_v2(trace_path)
    a_observation = next(d for d in document.decisions if d.agent_id == "A").observation
    assert (a_observation.own_core_base, a_observation.own_core_size) == (60, 8)
    losses = _of_kind(derivation.events, SpectatorEventKind.CORE_CELL_LOST)
    assert losses, "the anvil's core is contested in this fixture"
    assert all(0 <= event.address < 64 for event in losses if event.address is not None)


# ---------------------------------------------------------------------------
# 6. Perspective / visibility model
# ---------------------------------------------------------------------------


def test_no_event_ever_tells_an_entrant_something_the_engine_withheld(
    tmp_path: Path,
) -> None:
    """The audience model is the Fog phase's foundation; assert it directly."""

    entrant_visible = {
        SpectatorEventKind.DETECTION_GAINED,
        SpectatorEventKind.DETECTION_LOST,
        SpectatorEventKind.HOSTILE_READ,
        SpectatorEventKind.FIRST_HOSTILE_READ,
        SpectatorEventKind.EFFECTIVE_MOVE,
    }
    for label, builder in (("audit_hunt", _hunt), ("audit_kill", _kill)):
        replay_path, trace_path, _result = builder(tmp_path, label)
        assert trace_path is not None
        for event in analyze_pair(replay_path, trace_path).events:
            if event.kind in entrant_visible:
                # A READ result is supplied on the same process's next
                # callback. A final-callback READ remains factual but has no
                # delivered audience.
                if event.kind not in (
                    SpectatorEventKind.HOSTILE_READ,
                    SpectatorEventKind.FIRST_HOSTILE_READ,
                ):
                    assert event.visible_to, f"{event.kind} must name its observer"
                # Only the acting/observing entrant is ever told.
                assert set(event.visible_to) <= set(event.actors)
            else:
                assert event.visible_to == (), (
                    f"{event.kind.value} is omniscient-only: no v4 mechanic informs an "
                    f"entrant of it, but it named {event.visible_to}"
                )


def test_a_victim_is_never_told_its_cell_or_process_was_attacked(
    tmp_path: Path,
) -> None:
    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    events = analyze_pair(replay_path, trace_path).events
    attacked = [
        event
        for event in events
        if event.kind
        in (
            SpectatorEventKind.HOSTILE_WRITE,
            SpectatorEventKind.CORE_CELL_LOST,
            SpectatorEventKind.PROCESS_DISRUPTED,
        )
    ]
    assert attacked
    assert {event.targets[0] for event in attacked} == {"A", "B"}, (
        "cell 32 is contested, so both entrants take hostile hits here"
    )
    for event in attacked:
        victim = event.targets[0]
        assert victim not in event.visible_to
        assert event.visible_to == ()


# ---------------------------------------------------------------------------
# 7. Ordering, identity, and determinism
# ---------------------------------------------------------------------------


def test_event_identity_is_unique_and_contiguous_within_every_tick(
    tmp_path: Path,
) -> None:
    """``(tick, sequence)`` must be a real identity, including on the last tick.

    The terminal MATCH_ENDED/VICTORY events carry the final tick's number, so
    they have to continue that tick's sequence run rather than restarting it.
    """

    for label, builder in (("ident_hunt", _hunt), ("ident_kill", _kill)):
        replay_path, trace_path, _result = builder(tmp_path, label)
        assert trace_path is not None
        events = analyze_pair(replay_path, trace_path).events
        identities = [(event.tick, event.sequence) for event in events]
        assert len(set(identities)) == len(identities)
        by_tick: dict[int, list[int]] = {}
        for tick, sequence in identities:
            by_tick.setdefault(tick, []).append(sequence)
        for tick, sequences in by_tick.items():
            assert sequences == list(range(len(sequences))), f"tick {tick}: {sequences}"
        assert identities == sorted(identities)


def test_repeated_derivation_over_identical_inputs_is_byte_identical(
    tmp_path: Path,
) -> None:
    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    streams = {serialize_derivation(analyze_pair(replay_path, trace_path)) for _ in range(3)}
    assert len(streams) == 1


def test_repeated_execution_of_one_match_yields_one_semantic_stream(
    tmp_path: Path,
) -> None:
    """Re-run the same match inputs; the derived semantics must not move."""

    outcomes: set[tuple[str | None, int, str]] = set()
    streams: set[str] = set()
    for attempt in range(3):
        replay_path, trace_path, result = _hunt(tmp_path / f"run{attempt}")
        assert trace_path is not None
        outcomes.add(
            (
                result.winner,
                result.ticks_run,
                hashlib.sha256(replay_path.read_bytes()).hexdigest(),
            )
        )
        streams.add(serialize_derivation(analyze_pair(replay_path, trace_path)))
    assert len(outcomes) == 1
    assert len(streams) == 1


def test_derivation_is_stable_across_python_hash_seeds(tmp_path: Path) -> None:
    """Nothing in the ordering may depend on set or dict iteration order."""

    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    script = tmp_path / "seed_probe.py"
    script.write_text(
        "import hashlib, sys\n"
        "from battle_engine.spectator_derivation import analyze_pair, serialize_derivation\n"
        "stream = serialize_derivation(analyze_pair(sys.argv[1], sys.argv[2]))\n"
        "print(hashlib.sha256(stream.encode()).hexdigest())\n",
        encoding="utf-8",
    )
    digests = set()
    for seed in ("0", "1", "12345"):
        completed = subprocess.run(
            [sys.executable, str(script), str(replay_path), str(trace_path)],
            capture_output=True,
            text=True,
            check=True,
            env={**dict(__import__("os").environ), "PYTHONHASHSEED": seed},
        )
        digests.add(completed.stdout.strip())
    assert len(digests) == 1


def test_trace_line_endings_do_not_change_the_derived_stream(tmp_path: Path) -> None:
    """The trace's storage bytes are not canonical; its records are.

    ``TraceWriter`` opens its file in text mode, so a trace written on Windows
    stores CRLF and the same trace written on Linux stores LF. Nothing hashes
    those bytes -- the Phase 2 binding covers the *replay* -- so this asserts
    the property that lets Phase 3 defer the newline question rather than
    widening into a writer refactor.
    """

    replay_path, trace_path, _result = _hunt(tmp_path)
    assert trace_path is not None
    raw = trace_path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    alternate = tmp_path / "trace_alt.jsonl"
    alternate.write_bytes(normalized)

    if raw != normalized:
        assert hashlib.sha256(raw).hexdigest() != hashlib.sha256(normalized).hexdigest()
    assert read_trace_v2(trace_path).records == read_trace_v2(alternate).records
    assert serialize_derivation(analyze_pair(replay_path, trace_path)) == serialize_derivation(
        analyze_pair(replay_path, alternate)
    )


# ---------------------------------------------------------------------------
# 8. Simulation isolation
# ---------------------------------------------------------------------------


def test_tracing_and_analysis_do_not_change_the_canonical_match(
    tmp_path: Path,
) -> None:
    """Analysis is observational: it consumes finished artifacts only."""

    untraced_replay, untraced_trace, untraced = _run_match(
        tmp_path,
        "untraced",
        ("hunter", HUNTER, 0),
        ("anvil", ANVIL, 32),
        arena_size=64,
        max_ticks=12,
        seed=11,
        trace=False,
    )
    assert untraced_trace is None
    traced_replay, traced_trace, traced = _run_match(
        tmp_path,
        "traced",
        ("hunter", HUNTER, 0),
        ("anvil", ANVIL, 32),
        arena_size=64,
        max_ticks=12,
        seed=11,
        trace=True,
    )
    assert traced_trace is not None

    assert untraced.winner == traced.winner
    assert untraced.termination_reason == traced.termination_reason
    assert untraced.ticks_run == traced.ticks_run
    assert untraced.replay_sha256 == traced.replay_sha256
    assert (
        hashlib.sha256(untraced_replay.read_bytes()).hexdigest()
        == hashlib.sha256(traced_replay.read_bytes()).hexdigest()
    )
    untraced_result = json.loads(untraced_replay.with_name("result.json").read_text())
    traced_result = json.loads(traced_replay.with_name("result.json").read_text())
    assert untraced_result["result_id"] == traced_result["result_id"]

    # Running the analyzer must not touch either artifact.
    before = traced_replay.read_bytes(), traced_trace.read_bytes()
    analyze_pair(traced_replay, traced_trace)
    assert (traced_replay.read_bytes(), traced_trace.read_bytes()) == before


# ---------------------------------------------------------------------------
# 9. Provenance and the research CLI surface
# ---------------------------------------------------------------------------


def test_provenance_points_at_a_trace_record_that_supports_the_event(
    tmp_path: Path,
) -> None:
    """An independent reviewer must be able to follow record -> rule -> event."""

    replay_path, trace_path, _result = _kill(tmp_path)
    assert trace_path is not None
    document = read_trace_v2(trace_path)
    events = analyze_pair(replay_path, trace_path, with_provenance=True).events

    write = _of_kind(events, SpectatorEventKind.FIRST_HOSTILE_WRITE)[0]
    assert write.provenance is not None
    assert write.provenance.rule == "applied_write_over_foreign_ownership"
    assert write.provenance.source == "trace"
    assert write.provenance.record_index is not None
    source = document.decisions[write.provenance.record_index]
    assert source.agent_id == write.actors[0]
    assert source.action is not None and source.action.kind == "write"
    assert source.applied_result is not None
    assert source.applied_result.normalized_address == write.address
    assert write.provenance.before == "owner[33]=B"
    assert write.provenance.after == "owner[33]=A"

    detection = _of_kind(events, SpectatorEventKind.DETECTION_GAINED)[0]
    assert detection.provenance is not None
    assert detection.provenance.record_index is not None
    observed = document.decisions[detection.provenance.record_index]
    assert observed.agent_id == detection.actors[0]
    assert set(detection.addresses) <= set(observed.observation.visible_enemy_anchor_addresses)


def test_derivation_jsonl_round_trips_through_the_documented_schema(
    tmp_path: Path,
) -> None:
    replay_path, trace_path, _result = _kill(tmp_path)
    assert trace_path is not None
    derivation = analyze_pair(replay_path, trace_path)
    records = [json.loads(line) for line in serialize_derivation(derivation).splitlines()]

    assert records[0]["record_type"] == "header"
    assert records[0]["source"]["replay_sha256"] == derivation.binding.replay_sha256
    assert records[0]["source"]["entrants"] == ["A", "B"]
    assert records[-1]["record_type"] == "result"
    assert records[-1]["event_count"] == len(derivation.events)
    assert records[-1]["winner"] == "A"

    body = records[1:-1]
    assert len(body) == len(derivation.events)
    assert all(record["record_type"] == "event" for record in body)
    # An omniscient-only event must serialize an explicit empty audience, not
    # omit the field: a consumer has to tell "nobody knows" from "not stated".
    hostile = next(record for record in body if record["kind"] == "HOSTILE_WRITE")
    assert hostile["visible_to"] == []
    assert hostile["previous_owner"] == "B"


def test_tool_wrapper_reexports_the_pair_analyzer_contract() -> None:
    from battle_engine import spectator_derivation as permanent

    from tools import spectator_derive as wrapper

    assert wrapper.analyze_pair is permanent.analyze_pair
    assert wrapper.verify_pair is permanent.verify_pair
    assert wrapper.SpectatorEvent is permanent.SpectatorEvent
    assert wrapper.serialize_derivation is permanent.serialize_derivation


def test_cli_rejects_a_mismatched_pair_and_accepts_a_matching_one(
    tmp_path: Path,
) -> None:
    replay_one, trace_one, _r1 = _hunt(tmp_path, "cli_one", seed=11)
    _replay_two, trace_two, _r2 = _hunt(tmp_path, "cli_two", seed=99)
    assert trace_one is not None and trace_two is not None
    repository_root = Path(__file__).resolve().parents[2]
    script = repository_root / "tools" / "spectator_derive.py"

    good = subprocess.run(
        [sys.executable, str(script), str(replay_one), str(trace_one)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert good.returncode == 0
    assert json.loads(good.stdout.splitlines()[0])["record_type"] == "header"

    bad = subprocess.run(
        [sys.executable, str(script), str(replay_one), str(trace_two)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2
    assert bad.stdout == ""
    assert "binding mismatch" in bad.stderr
