# v1.4 scaling characterization

This document records the evidence used for Bytefray v1.4's ownership and
replay-scaling decisions. It is a workstation measurement, not a universal
performance claim or a CI threshold. Reproduce it from an editable checkout:

```powershell
python tools/benchmark_platform_scaling.py
```

The script uses medians, an isolated temporary data root, three-entrant VM and
Python matches, and no display. It reports its workload and environment as
JSON. `--quick` is available for a shorter diagnostic run.

## Environment and workload

- Windows 11 `10.0.26120`, AMD64 Family 25 Model 33, Python 3.13.14.
- Territory/scoring-statistics microbenchmark: a fixed 16,777,216 owned-cell
  workload at arenas 4,096, 16,384, 65,536, and 262,144; five samples.
- Match benchmark: three entrants, 300 ticks, action budget 4, canonical
  replay/result writing included; three samples at arenas 4,096 and 65,536.
- Replay benchmark: two entrants, arena 16,384, 3,000 ticks, 1,939,072-byte
  replay. Loading and a fixed mixed forward/backward seek sequence use five
  samples; territory history and canonical rewrite use three.

## Before and after incremental ownership counts

Times are median milliseconds. The two match rows are end-to-end, so they
include simulation, scoring/statistics, and canonical artifact work.

| Workload | Before | After | Reduction |
|---|---:|---:|---:|
| Territory work, 4K arena (4,096 iterations) | 971.37 | 4.63 | 99.5% |
| Territory work, 16K arena (1,024 iterations) | 955.25 | 1.12 | 99.9% |
| Territory work, 65K arena (256 iterations) | 985.69 | 0.28 | >99.9% |
| Territory work, 262K arena (64 iterations) | 970.87 | 0.07 | >99.9% |
| VM match, 4K arena | 120.90 | 46.21 | 61.8% |
| VM match, 65K arena | 1,247.26 | 47.43 | 96.2% |
| Python match, 4K arena | 174.66 | 107.08 | 38.7% |
| Python match, 65K arena | 1,302.37 | 87.63 | 93.3% |

The territory workload intentionally keeps the total number of cells constant,
so the post-change time decreases at larger arenas because it performs fewer
O(entrant-count) calls. The important result is that match time no longer grows
linearly with arena size solely because scoring and statistics each recount the
entire ownership array every tick. Absolute timings fluctuate with workstation
load; the scaling shape and equivalence tests are the evidence that matters.

## Replay measurements and checkpoint decision

| Operation, 16K arena / 3,000 ticks | Median ms |
|---|---:|
| Canonical replay rewrite | 45.34 |
| Full replay load | 73.83 |
| Mixed seeks (final, 25%, 75%, 10%, final) | 8.09 |
| One-time territory-history derivation | 460.14 |

`ReplaySession` still buffers typed tick records, applies forward seeks
incrementally, and reconstructs a backward seek from tick zero. The mixed seek
sequence is comfortably below interactive latency on this representative
long replay. Sparse arena checkpoints would multiply memory by arena size and
checkpoint count, introduce another derived-state invariant, and offer little
measured value here. v1.4 therefore keeps the persistence-compatible current
implementation and defers checkpoints/indexes. Territory history is the
heavier operation, but the UI derives it once per loaded session; it is not a
per-frame path. v1.6 may revisit local replay indexes if larger real workloads
show user-visible delay.
