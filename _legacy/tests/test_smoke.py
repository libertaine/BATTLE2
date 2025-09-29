from core import Kernel


def test_ticks_progress():
    k = Kernel(ticks_per_second=1000)
    k.run(max_ticks=5, realtime=False)
    assert k.tick == 5
