from core import Config, Kernel


def test_ticks_progress():
    k = Kernel(ticks_per_second=1000)
    k.run(max_ticks=5, realtime=False)
    assert k.tick == 5


def test_single_agent_early_stop():
    cfg = Config(arena_size=16, instr_per_tick=1)
    k = Kernel(cfg=cfg)
    # NOP instruction (0) keeps the agent alive, but with 1 agent the run should stop early.
    k.spawn("agent1", entry=0, code=bytes([0]))
    k.run(max_ticks=5, realtime=False)
    assert k.tick == 1
    assert k.agents[0].alive
