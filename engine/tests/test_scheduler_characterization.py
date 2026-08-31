from __future__ import annotations

from typing import Any

from battle_engine.config import Config
from battle_engine.core import HALT, JMP, MOV, NOP, STORE, Kernel, enc
from battle_engine.ruleset_policy import RULESET_V1
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


class _RecordingRenderer:
    """Minimal renderer stub so ``LegacyRendererObserver.publish_tick`` fires.

    ``Kernel.renderer`` is ``None`` by default, which makes
    ``LegacyRendererObserver`` skip the call entirely (see ``telemetry.
    LegacyRendererObserver.publish_tick``) -- this stub exists only so the
    tick-lifecycle order tests below can observe that stage actually
    happening, not to exercise renderer content itself.
    """

    def __init__(self, order: list[str]) -> None:
        self.order = order

    def on_init(self, kernel: object) -> None:
        del kernel

    def on_tick(self, tick: int, snapshot: dict[str, Any]) -> None:
        del tick, snapshot
        self.order.append("renderer_publish")

    def on_close(self) -> None:
        pass


def _wrap(monkeypatch, order: list[str], obj: object, name: str, label: str) -> None:
    original = getattr(obj, name)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        order.append(label)
        return original(*args, **kwargs)

    monkeypatch.setattr(obj, name, wrapper)


def test_tick_lifecycle_runs_in_the_documented_order_with_no_death(monkeypatch):
    """Pin ``match.MatchRunner.run``'s per-tick stage order directly.

    See ``engine/src/battle_engine/match.py``'s ``MatchRunner.run``: execute
    -> statistics -> alive scoring -> territory scoring -> death
    attribution (skipped here -- nothing dies) -> replay publication ->
    renderer publication -> ``_alive_prev`` update -> termination check.
    The existing golden-corpus digests in ``test_ruleset_v1_equivalence.py``
    would catch a reordering here too, but only as an opaque hash mismatch;
    this test names the exact stage that moved, which matters once v1.5
    considers extracting this loop into a shared scheduler abstraction.
    """

    order: list[str] = []
    kernel = _kernel(quota=1)
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(NOP))
    kernel.renderer = _RecordingRenderer(order)

    _wrap(monkeypatch, order, kernel.vm, "step", "execute")
    _wrap(monkeypatch, order, kernel.statistics, "record_tick", "statistics")
    _wrap(monkeypatch, order, kernel.scoring, "score_alive", "score_alive")
    _wrap(monkeypatch, order, kernel.scoring, "score_territory", "score_territory")
    _wrap(monkeypatch, order, kernel.scoring, "score_kill", "score_kill")
    _wrap(monkeypatch, order, kernel.sink, "emit", "replay_emit")

    kernel.run(max_ticks=1, verbose=False)

    assert order == [
        "replay_emit",  # header
        "replay_emit",  # tick-0 initial snapshot, published before the loop
        "execute", "execute",  # one vm.step per living agent this tick
        "statistics",
        "score_alive",
        "score_territory",
        # score_kill is skipped: nothing died this tick.
        "replay_emit",  # tick 1 snapshot
        "renderer_publish",
    ]


def test_tick_lifecycle_scores_the_kill_after_territory_and_before_replay_publication(
    monkeypatch,
):
    """Same stage order, with an actual kill so ``score_kill`` participates.

    ``_attribute_deaths`` (which calls ``score_kill``) runs after both
    ``score_alive``/``score_territory`` and before the tick's replay record
    is published -- see ``match.MatchRunner.run``. B's program counter is
    an invalid opcode owned by A, so B dies on its first step and A is
    attributed the kill (the same setup as ``test_match_services.
    test_kernel_attributes_kill_to_memory_owner``).
    """

    order: list[str] = []
    kernel = _kernel(quota=1)
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(NOP))
    kernel.vm._wr8(16, 0xFF, "A")
    kernel.renderer = _RecordingRenderer(order)

    _wrap(monkeypatch, order, kernel.statistics, "record_tick", "statistics")
    _wrap(monkeypatch, order, kernel.scoring, "score_alive", "score_alive")
    _wrap(monkeypatch, order, kernel.scoring, "score_territory", "score_territory")
    _wrap(monkeypatch, order, kernel.scoring, "score_kill", "score_kill")
    _wrap(monkeypatch, order, kernel.sink, "emit", "replay_emit")

    kernel.run(max_ticks=1, verbose=False)

    assert kernel.agents[1].alive is False
    assert order == [
        "replay_emit",  # header
        "replay_emit",  # tick-0 initial snapshot
        "statistics",
        "score_alive",
        "score_territory",
        "score_kill",
        "replay_emit",  # tick 1 snapshot, published after death attribution
        "renderer_publish",
    ]


class _RecordingRulesetPolicy:
    """Delegates to ``RULESET_V1`` while recording when termination is checked.

    ``RulesetPolicy`` is a frozen dataclass, so its bound methods cannot be
    monkeypatched in place the way ``kernel.vm.step``/``kernel.statistics.
    record_tick``/etc. are spied on above -- this stand-in is passed to
    ``Kernel(..., ruleset_policy=...)`` instead, matching the duck-typed
    seam ``Kernel``/``MatchRunner`` already use.
    """

    ruleset_id = RULESET_V1.ruleset_id

    def __init__(self, order: list[str]) -> None:
        self._order = order

    def run_scheduler(self, states, quota, execute_slot, *args, **kwargs):  # type: ignore[no-untyped-def]
        RULESET_V1.run_scheduler(states, quota, execute_slot, *args, **kwargs)


    def resolve_termination(self, *, alive_count, tick, max_ticks):  # type: ignore[no-untyped-def]
        self._order.append("termination_check")
        return RULESET_V1.resolve_termination(
            alive_count=alive_count, tick=tick, max_ticks=max_ticks
        )


def test_tick_lifecycle_checks_termination_after_renderer_publication(monkeypatch):
    """Prove the termination check is still the last stage each tick.

    Phase 4 replaces the inline ``sum(agent.alive ...) <= 1`` comparison
    that used to sit here with a call to ``RulesetPolicy.resolve_
    termination``. This test extends ``test_tick_lifecycle_runs_in_the_
    documented_order_with_no_death``'s stage-order proof with the one stage
    that predates Phase 4: the termination check itself must still run
    after replay publication, renderer publication, and the ``_alive_prev``
    bookkeeping update -- moving it earlier could let a stale alive count
    decide whether to keep ticking.
    """

    order: list[str] = []
    kernel = Kernel(
        Config(arena_size=64, instr_per_tick=1),
        sink=RecordingSink(),  # type: ignore[arg-type]
        summary_sink=NullSummarySink(),
        ruleset_policy=_RecordingRulesetPolicy(order),  # type: ignore[arg-type]
    )
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(NOP))
    kernel.renderer = _RecordingRenderer(order)

    _wrap(monkeypatch, order, kernel.vm, "step", "execute")
    _wrap(monkeypatch, order, kernel.statistics, "record_tick", "statistics")
    _wrap(monkeypatch, order, kernel.scoring, "score_alive", "score_alive")
    _wrap(monkeypatch, order, kernel.scoring, "score_territory", "score_territory")
    _wrap(monkeypatch, order, kernel.sink, "emit", "replay_emit")

    kernel.run(max_ticks=1, verbose=False)

    assert order == [
        "replay_emit",  # header
        "replay_emit",  # tick-0 initial snapshot
        "execute", "execute",  # one vm.step per living agent this tick
        "statistics",
        "score_alive",
        "score_territory",
        # score_kill is skipped: nothing died this tick.
        "replay_emit",  # tick 1 snapshot
        "renderer_publish",
        "termination_check",
    ]
