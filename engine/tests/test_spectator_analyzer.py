from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from battle_engine.replay import (
    AgentState,
    KillDeathEvent,
    MatchConfiguration,
    MatchResult,
    MemoryDiff,
    ProcessState,
    ReplayHeader,
    RuntimeEvent,
    TickSnapshot,
    write_replay,
)

from tools.spectator_analyzer import (
    SemanticEventKind,
    SpectatorAnalysisError,
    analyze_replay,
    serialize_analysis,
)


def _agent(entrant_id: str, *, alive: bool = True) -> AgentState:
    return AgentState(entrant_id, 0, alive=alive)


def _process(
    entrant_id: str,
    process_id: str,
    anchor: int,
    *,
    reach: int = 0,
    disrupted: bool = False,
) -> ProcessState:
    return ProcessState(process_id, entrant_id, anchor, disrupted, reach)


def _diff(address: int, owner: str | None, *, length: int = 1) -> MemoryDiff:
    return MemoryDiff(address, length, owner, tuple(range(length)))


def _write(
    path: Path,
    ticks: list[TickSnapshot],
    *,
    winner: str | None = None,
    result_ticks: int | None = None,
) -> Path:
    agents = ticks[-1].agents
    processes = ticks[-1].processes
    duration = result_ticks if result_ticks is not None else ticks[-1].tick + 1
    write_replay(
        path,
        [
            ReplayHeader(
                MatchConfiguration(arena_size=16, instr_per_tick=8, seed=7),
                replay_id="replay-test",
                match_id="match-test",
                result_id="result-test",
                runtime_kind="python",
                ruleset_id="bytefray-rules-4-alpha1",
            ),
            *ticks,
            MatchResult(
                winner=winner,
                win_mode="score_fallback",
                ticks=duration,
                agents=agents,
                processes=processes,
                replay_id="replay-test",
                match_id="match-test",
                result_id="result-test",
            ),
        ],
    )
    return path


def _events(path: Path, kind: SemanticEventKind):
    return [event for event in analyze_replay(path).events if event.kind is kind]


def _empty_tick(tick: int = 0) -> TickSnapshot:
    return TickSnapshot(tick=tick)


def test_valid_schema4_replay_is_accepted(tmp_path: Path) -> None:
    path = _write(tmp_path / "valid.jsonl", [_empty_tick()])

    analysis = analyze_replay(path)

    assert analysis.match_id == "match-test"
    assert analysis.first_tick == 0
    assert analysis.last_tick == 0


def test_unsupported_schema_is_rejected_clearly(tmp_path: Path) -> None:
    path = _write(tmp_path / "old.jsonl", [_empty_tick()])
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[0]["schema_version"] = 3
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    with pytest.raises(SpectatorAnalysisError, match="exactly battle2.replay Schema 4"):
        analyze_replay(path)


def test_missing_required_tick_field_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path / "missing.jsonl", [_empty_tick()])
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    del records[1]["processes"]
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    with pytest.raises(SpectatorAnalysisError, match="missing required field.*processes"):
        analyze_replay(path)


def test_missing_memory_diff_owner_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "missing-owner.jsonl",
        [TickSnapshot(tick=0, memory_diffs=(_diff(1, "A"),))],
    )
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    del records[1]["memory_diffs"][0]["owner"]
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    with pytest.raises(SpectatorAnalysisError, match="missing required field.*owner"):
        analyze_replay(path)


def test_truncated_input_is_a_controlled_failure(tmp_path: Path) -> None:
    path = _write(tmp_path / "truncated.jsonl", [_empty_tick()])
    path.write_text(
        path.read_text(encoding="utf-8") + '{"schema":"battle2.replay"',
        encoding="utf-8",
    )

    with pytest.raises(SpectatorAnalysisError, match="invalid replay JSON"):
        analyze_replay(path)


def test_tick_zero_seeds_ownership_and_first_foreign_overwrite(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "ownership.jsonl",
        [
            TickSnapshot(tick=0, memory_diffs=(_diff(3, "B"),)),
            TickSnapshot(tick=1, memory_diffs=(_diff(3, "A"),)),
        ],
    )

    overwrites = _events(path, SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE)

    assert [
        (event.tick, event.previous_owner, event.new_owner, event.address) for event in overwrites
    ] == [(1, "B", "A", 3)]


def test_repeated_writes_preserve_replay_order(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "order.jsonl",
        [
            TickSnapshot(tick=0, memory_diffs=(_diff(2, "A"),)),
            TickSnapshot(
                tick=1,
                memory_diffs=(_diff(2, "B"), _diff(2, "C"), _diff(2, "A")),
            ),
        ],
    )

    overwrites = _events(path, SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE)

    assert [(event.previous_owner, event.new_owner) for event in overwrites] == [
        ("A", "B"),
        ("B", "C"),
        ("C", "A"),
    ]


def test_range_write_expands_in_address_order_with_wraparound(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "range.jsonl",
        [
            TickSnapshot(tick=0, memory_diffs=(_diff(14, "A", length=4),)),
            TickSnapshot(tick=1, memory_diffs=(_diff(14, "B", length=4),)),
        ],
    )

    overwrites = _events(path, SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE)

    assert [event.address for event in overwrites] == [14, 15, 0, 1]


def test_same_owner_rewrite_is_not_foreign(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "same.jsonl",
        [
            TickSnapshot(tick=0, memory_diffs=(_diff(4, "A"),)),
            TickSnapshot(tick=1, memory_diffs=(_diff(4, "A"),)),
        ],
    )

    assert not _events(path, SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE)


def test_null_owner_clears_ownership_without_emitting_overwrite(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "clear.jsonl",
        [
            TickSnapshot(tick=0, memory_diffs=(_diff(4, "A"),)),
            TickSnapshot(tick=1, memory_diffs=(_diff(4, None),)),
            TickSnapshot(tick=2, memory_diffs=(_diff(4, "B"),)),
        ],
    )

    assert not _events(path, SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE)


def test_visibility_is_entrant_wide_across_multiple_sensors_and_targets(tmp_path: Path) -> None:
    processes = (
        _process("A", "near", 0, reach=1),
        _process("A", "far", 8, reach=3),
        _process("B", "outside", 4),
        _process("B", "inside", 10),
    )
    path = _write(
        tmp_path / "entrant-wide.jsonl",
        [TickSnapshot(tick=0, agents=(_agent("A"), _agent("B")), processes=processes)],
    )

    gained = _events(path, SemanticEventKind.DETECTION_GAINED)

    assert [(event.viewer_entrant_id, event.target_entrant_id) for event in gained] == [("A", "B")]


def test_visibility_is_asymmetric_and_inclusive(tmp_path: Path) -> None:
    processes = (
        _process("A", "sensor", 0, reach=3),
        _process("B", "sensor", 3, reach=2),
    )
    path = _write(
        tmp_path / "asymmetric.jsonl",
        [TickSnapshot(tick=0, agents=(_agent("A"), _agent("B")), processes=processes)],
    )

    gained = _events(path, SemanticEventKind.DETECTION_GAINED)

    assert [(event.viewer_entrant_id, event.target_entrant_id) for event in gained] == [("A", "B")]


def test_visibility_uses_circular_arena_distance(tmp_path: Path) -> None:
    processes = (
        _process("A", "sensor", 15, reach=1),
        _process("B", "target", 0, reach=0),
    )
    path = _write(
        tmp_path / "wrap-visibility.jsonl",
        [TickSnapshot(tick=0, agents=(_agent("A"), _agent("B")), processes=processes)],
    )

    pairs = [
        (event.viewer_entrant_id, event.target_entrant_id)
        for event in _events(path, SemanticEventKind.DETECTION_GAINED)
    ]
    assert ("A", "B") in pairs


def test_disrupted_viewer_is_not_sensor_but_disrupted_target_is_observable(
    tmp_path: Path,
) -> None:
    processes = (
        _process("A", "sensor", 0, reach=2),
        _process("B", "same-id", 1, reach=2, disrupted=True),
    )
    path = _write(
        tmp_path / "disrupted-target.jsonl",
        [
            TickSnapshot(
                tick=0,
                agents=(_agent("A"), _agent("B")),
                memory_diffs=(_diff(1, "A"),),
                processes=processes,
            )
        ],
    )

    pairs = [
        (event.viewer_entrant_id, event.target_entrant_id)
        for event in _events(path, SemanticEventKind.DETECTION_GAINED)
    ]
    assert pairs == [("A", "B")]


def test_eliminated_entrant_is_removed_as_viewer_and_target(tmp_path: Path) -> None:
    processes = (
        _process("A", "p", 0, reach=2),
        _process("B", "p", 1, reach=2),
    )
    path = _write(
        tmp_path / "eliminated.jsonl",
        [
            TickSnapshot(tick=0, agents=(_agent("A"), _agent("B")), processes=processes),
            TickSnapshot(
                tick=1,
                agents=(_agent("A"), _agent("B", alive=False)),
                processes=processes,
                events=(KillDeathEvent("death", "B", "A"),),
            ),
        ],
    )

    lost = _events(path, SemanticEventKind.DETECTION_LOST)

    assert [(event.viewer_entrant_id, event.target_entrant_id) for event in lost] == [
        ("A", "B"),
        ("B", "A"),
    ]


def test_duplicate_process_ids_are_scoped_by_entrant(tmp_path: Path) -> None:
    processes = (
        _process("A", "shared", 0, reach=2),
        _process("B", "shared", 1, reach=2),
        _process("C", "shared", 8, reach=1),
    )
    path = _write(
        tmp_path / "duplicate-process-id.jsonl",
        [
            TickSnapshot(
                tick=0,
                agents=(_agent("A"), _agent("B"), _agent("C")),
                processes=processes,
            )
        ],
    )

    pairs = {
        (event.viewer_entrant_id, event.target_entrant_id)
        for event in _events(path, SemanticEventKind.DETECTION_GAINED)
    }
    assert pairs == {("A", "B"), ("B", "A")}


def test_disruption_is_emitted_for_each_consecutive_hit_tick(tmp_path: Path) -> None:
    agents = (_agent("A"), _agent("B"))
    clear = (_process("A", "writer", 0), _process("B", "target", 5))
    hit = (_process("A", "writer", 0), _process("B", "target", 5, disrupted=True))
    path = _write(
        tmp_path / "consecutive.jsonl",
        [
            TickSnapshot(tick=0, agents=agents, processes=clear),
            TickSnapshot(tick=1, agents=agents, memory_diffs=(_diff(5, "A"),), processes=hit),
            TickSnapshot(tick=2, agents=agents, memory_diffs=(_diff(5, "A"),), processes=hit),
        ],
    )

    disruptions = _events(path, SemanticEventKind.CORE_DISRUPTION)

    assert [event.tick for event in disruptions] == [1, 2]
    assert all(event.attacker_entrant_id == "A" for event in disruptions)


def test_multiple_same_tick_writes_produce_one_process_disruption(tmp_path: Path) -> None:
    agents = (_agent("A"), _agent("B"))
    processes = (
        _process("A", "writer", 0),
        _process("B", "target", 5, disrupted=True),
    )
    path = _write(
        tmp_path / "multiple-writes.jsonl",
        [
            TickSnapshot(tick=0),
            TickSnapshot(
                tick=1,
                agents=agents,
                memory_diffs=(_diff(5, "A"), _diff(5, "A")),
                processes=processes,
            ),
        ],
    )

    disruptions = _events(path, SemanticEventKind.CORE_DISRUPTION)

    assert len(disruptions) == 1
    assert disruptions[0].attribution == "exact"


def test_colocated_enemy_processes_each_receive_disruption_event(tmp_path: Path) -> None:
    agents = (_agent("A"), _agent("B"))
    processes = (
        _process("A", "writer", 0),
        _process("B", "first", 5, disrupted=True),
        _process("B", "second", 5, disrupted=True),
    )
    path = _write(
        tmp_path / "colocated.jsonl",
        [
            TickSnapshot(tick=0),
            TickSnapshot(
                tick=1,
                agents=agents,
                memory_diffs=(_diff(5, "A"),),
                processes=processes,
            ),
        ],
    )

    disruptions = _events(path, SemanticEventKind.CORE_DISRUPTION)

    assert [event.target_process_id for event in disruptions] == ["first", "second"]


def test_friendly_anchor_write_does_not_create_disruption(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "friendly.jsonl",
        [
            TickSnapshot(
                tick=0,
                agents=(_agent("A"),),
                memory_diffs=(_diff(5, "A"),),
                processes=(_process("A", "friendly", 5),),
            )
        ],
    )

    assert not _events(path, SemanticEventKind.CORE_DISRUPTION)


def test_multiple_attackers_are_reported_as_ambiguous(tmp_path: Path) -> None:
    processes = (
        _process("A", "a", 0),
        _process("B", "target", 5, disrupted=True),
        _process("C", "c", 9),
    )
    path = _write(
        tmp_path / "ambiguous.jsonl",
        [
            TickSnapshot(tick=0),
            TickSnapshot(
                tick=1,
                agents=(_agent("A"), _agent("B"), _agent("C")),
                memory_diffs=(_diff(5, "A"), _diff(5, "C")),
                processes=processes,
            ),
        ],
    )

    disruption = _events(path, SemanticEventKind.CORE_DISRUPTION)[0]

    assert disruption.attacker_entrant_id is None
    assert disruption.attribution == "ambiguous"
    assert disruption.candidate_attacker_entrant_ids == ("A", "C")


def test_kill_and_forfeit_preserve_canonical_details(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "termination.jsonl",
        [
            TickSnapshot(
                tick=0,
                events=(
                    KillDeathEvent("kill", "B", "A"),
                    RuntimeEvent("forfeit", "C", "timeout", "act", 0, 3),
                ),
            )
        ],
    )

    analysis = analyze_replay(path)

    assert analysis.events[0].kind is SemanticEventKind.AGENT_ELIMINATED
    assert analysis.events[0].cause == "kill"
    assert analysis.events[0].killer_entrant_id == "A"
    assert analysis.events[1].kind is SemanticEventKind.AGENT_FORFEITED
    assert analysis.events[1].reason == "timeout"
    assert analysis.events[1].stage == "act"
    assert analysis.events[1].action_slot == 3


def test_winner_produces_final_victory_event(tmp_path: Path) -> None:
    path = _write(tmp_path / "victory.jsonl", [_empty_tick()], winner="A", result_ticks=1)

    victory = _events(path, SemanticEventKind.VICTORY)

    assert [(event.tick, event.entrant_id, event.cause) for event in victory] == [
        (1, "A", "score_fallback")
    ]


def test_same_tick_order_contract_is_causal_and_stable(tmp_path: Path) -> None:
    agents = (_agent("A"), _agent("B"))
    initial = (_process("A", "a", 0, reach=2), _process("B", "b", 1, reach=2))
    terminal = (
        _process("A", "a", 0, reach=2),
        _process("B", "b", 1, reach=2, disrupted=True),
    )
    path = _write(
        tmp_path / "same-tick.jsonl",
        [
            TickSnapshot(
                tick=0,
                agents=agents,
                memory_diffs=(_diff(1, "B"),),
                processes=initial,
            ),
            TickSnapshot(
                tick=1,
                agents=(_agent("A"), _agent("B", alive=False)),
                memory_diffs=(_diff(1, "A"),),
                processes=terminal,
                events=(KillDeathEvent("death", "B", "A"),),
            ),
        ],
    )

    tick_one = [event for event in analyze_replay(path).events if event.tick == 1]

    assert [event.kind for event in tick_one] == [
        SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE,
        SemanticEventKind.CORE_DISRUPTION,
        SemanticEventKind.DETECTION_LOST,
        SemanticEventKind.DETECTION_LOST,
        SemanticEventKind.AGENT_ELIMINATED,
    ]


def test_same_replay_serializes_byte_identically(tmp_path: Path) -> None:
    path = _write(tmp_path / "deterministic.jsonl", [_empty_tick()], winner="A")

    assert serialize_analysis(analyze_replay(path)) == serialize_analysis(analyze_replay(path))


def test_hash_seed_does_not_change_three_entrant_output(tmp_path: Path) -> None:
    processes = tuple(
        _process(entrant, "sensor", index, reach=8) for index, entrant in enumerate(("A", "B", "C"))
    )
    path = _write(
        tmp_path / "hash-seed.jsonl",
        [
            TickSnapshot(
                tick=0,
                agents=tuple(_agent(entrant) for entrant in ("A", "B", "C")),
                processes=processes,
            )
        ],
    )
    repo_root = Path(__file__).resolve().parents[2]
    outputs = []
    for seed in ("1", "7", "91"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        completed = subprocess.run(
            [sys.executable, "tools/spectator_analyzer.py", str(path)],
            cwd=repo_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(completed.stdout)

    assert outputs[0] == outputs[1] == outputs[2]
