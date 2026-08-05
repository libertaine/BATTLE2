from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agents import discover_agents, resolve_agent
from battle_engine.builtins import build_agent
from battle_engine.core import (
    ADD,
    ADDP,
    HALT,
    JZ,
    LOAD,
    LOADI,
    MOV,
    MOVP,
    NOP,
    STORE,
    STOREI,
    Agent,
    Config,
    JSONLSink,
    Kernel,
    VM,
    Weights,
    enc,
)


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[dict] = []
        self.closed = False

    def emit(self, record: dict) -> None:
        self.records.append(record)

    def close(self) -> None:
        self.closed = True


def _run_fixed_match(tmp_path: Path, monkeypatch, seed: int) -> tuple:
    monkeypatch.chdir(tmp_path)
    sink = RecordingSink()
    cfg = Config(
        arena_size=128,
        instr_per_tick=2,
        seed=seed,
        weights=Weights(alive=1, kill=5, territory=1, territory_bucket=16),
    )
    kernel = Kernel(cfg, sink)  # type: ignore[arg-type]
    kernel.spawn("A", 0, build_agent("writer", 0, offset=80, byte=0x99))
    kernel.spawn("B", 48, build_agent("runner", 48))
    winner = kernel.run(max_ticks=12, verbose=False)
    return winner, kernel.score, kernel.stats, sink.records


def test_fixed_seed_engine_result_is_deterministic(tmp_path, monkeypatch):
    first = _run_fixed_match(tmp_path, monkeypatch, seed=1337)
    second = _run_fixed_match(tmp_path, monkeypatch, seed=1337)
    assert first == second
    assert first[3][0] == {
        "tick": 0,
        "ver": 6,
        "config": {
            "arena_size": 128,
            "instr_per_tick": 2,
            "seed": 1337,
            "win_mode": "score_fallback",
            "weights": {
                "alive": 1,
                "kill": 5,
                "territory": 1,
                "territory_bucket": 16,
            },
        },
    }


def test_vm_executes_basic_register_memory_and_branch_instructions():
    vm = VM(64)
    code = b"".join(
        [
            enc(MOV, 7),
            enc(ADD, 2),
            enc(STORE, 50),
            enc(LOAD, 50),
            enc(MOVP, 51),
            enc(STOREI),
            enc(ADDP, 1),
            enc(LOADI),
            enc(JZ, 48),
            enc(HALT),
        ]
    )
    vm.load_code(0, code, "A")
    agent = Agent("A", 0)

    for _ in range(9):
        vm.step(agent)

    assert agent.regs == {"A": NOP, "Z": 1, "P": 52}
    assert agent.pc == 48
    assert vm.arena[50] == 9
    assert vm.arena[51] == 9
    assert agent.mem_writes == 2


def test_native_builtin_agents_complete_a_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sink = RecordingSink()
    kernel = Kernel(Config(arena_size=128, instr_per_tick=2), sink)  # type: ignore[arg-type]
    kernel.spawn("A", 0, build_agent("writer", 0, offset=96))
    kernel.spawn("B", 48, build_agent("runner", 48))

    winner = kernel.run(max_ticks=8, verbose=False)

    assert kernel.tick == 8
    assert winner in {"", "A", "B"}
    assert len(sink.records) == 9
    assert sink.closed


def test_last_survivor_wins_and_scoring_tracks_alive_ticks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    kernel = Kernel(
        Config(
            arena_size=32,
            instr_per_tick=1,
            weights=Weights(alive=1, kill=5, territory=0),
        ),
        RecordingSink(),  # type: ignore[arg-type]
    )
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(HALT))

    assert kernel.run(max_ticks=10, verbose=False) == "A"
    assert kernel.tick == 1
    assert kernel.score == {"A": 1, "B": 0}
    assert kernel.stats["A"]["alive_ticks"] == 1
    assert kernel.stats["B"]["deaths"] == 1


def test_jsonl_sink_creates_header_and_tick_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    replay = tmp_path / "replay.jsonl"
    kernel = Kernel(Config(arena_size=32, instr_per_tick=1), JSONLSink(str(replay)))
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(HALT))
    kernel.run(max_ticks=3, verbose=False)

    records = [json.loads(line) for line in replay.read_text().splitlines()]
    assert records[0]["tick"] == 0
    assert records[0]["ver"] == 6
    assert records[1]["tick"] == 1
    assert records[1]["agents"][1]["alive"] is False


def test_agent_discovery_accepts_existing_manifest_shape(tmp_path):
    agent_dir = tmp_path / "agents" / "sample"
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        json.dumps(
            {
                "name": "sample",
                "display": "Sample Agent",
                "defaults": {"aggression": 0.6},
            }
        ),
        encoding="utf-8",
    )
    (agent_dir / "model.blob").write_bytes(enc(NOP))

    specs = discover_agents(tmp_path)
    resolved = resolve_agent(tmp_path, "sample")
    assert list(specs) == ["sample"]
    assert resolved.display == "Sample Agent"
    assert resolved.defaults == {"aggression": 0.6}
    assert resolved.blob == agent_dir / "model.blob"
