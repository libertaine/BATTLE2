from __future__ import annotations

from typing import Any

from battle_engine.config import Config
from battle_engine.core import HALT, JMP, MOV, NOP, STORE, Kernel, enc
from battle_engine.telemetry import NullSummarySink


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def emit(self, record: dict[str, Any]) -> None:
        self.records.append(record)

    def close(self) -> None:
        pass


def _kernel(*, quota: int) -> Kernel:
    return Kernel(
        Config(arena_size=64, instr_per_tick=quota),
        sink=RecordingSink(),  # type: ignore[arg-type]
        summary_sink=NullSummarySink(),
    )


def test_alive_entrants_consume_full_quota_in_spawn_order(monkeypatch):
    kernel = _kernel(quota=3)
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(NOP))
    kernel.spawn("C", 32, enc(NOP))
    calls = []
    original_step = kernel.vm.step

    def record_step(agent):
        calls.append(agent.agent_id)
        original_step(agent)

    monkeypatch.setattr(kernel.vm, "step", record_step)
    kernel.run(max_ticks=1, verbose=False)

    assert calls == ["A", "A", "A", "B", "B", "B", "C", "C", "C"]
    assert [agent.cpu_used for agent in kernel.agents] == [3, 3, 3]


def test_first_entrant_write_changes_later_entrant_instruction_same_tick(monkeypatch):
    kernel = _kernel(quota=2)
    kernel.spawn("A", 0, b"".join([enc(MOV, HALT), enc(STORE, 32), enc(JMP, 0)]))
    kernel.spawn("B", 32, enc(NOP))
    calls = []
    original_step = kernel.vm.step

    def record_step(agent):
        calls.append(agent.agent_id)
        original_step(agent)

    monkeypatch.setattr(kernel.vm, "step", record_step)
    kernel.run(max_ticks=1, verbose=False)

    assert calls == ["A", "A", "B"]
    assert kernel.vm.arena[32] == HALT
    assert kernel.vm.writer[32] == "A"
    assert kernel.agents[1].alive is False
    assert kernel.agents[1].cpu_used == 1


def test_dead_entrant_is_skipped_on_later_ticks(monkeypatch):
    kernel = _kernel(quota=2)
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(HALT))
    kernel.spawn("C", 32, enc(NOP))
    calls = []
    original_step = kernel.vm.step

    def record_step(agent):
        calls.append((kernel.tick, agent.agent_id))
        original_step(agent)

    monkeypatch.setattr(kernel.vm, "step", record_step)
    kernel.run(max_ticks=2, verbose=False)

    assert calls == [
        (1, "A"),
        (1, "A"),
        (1, "B"),
        (1, "C"),
        (1, "C"),
        (2, "A"),
        (2, "A"),
        (2, "C"),
        (2, "C"),
    ]


def test_dead_entrant_cpu_total_stops_after_death():
    kernel = _kernel(quota=3)
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(HALT))
    kernel.spawn("C", 32, enc(NOP))

    kernel.run(max_ticks=4, verbose=False)

    assert kernel.tick == 4
    assert kernel.agents[1].alive is False
    assert kernel.agents[1].cpu_used == 0
    assert kernel.stats["B"]["total_cpu"] == 1
    assert kernel.stats["A"]["total_cpu"] == 12
    assert kernel.stats["C"]["total_cpu"] == 12
