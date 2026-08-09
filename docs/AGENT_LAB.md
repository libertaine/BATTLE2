# Agent Lab

Agent Lab is the second half of the agent-authoring feedback loop. Where
[AGENT_AUTHORING.md](AGENT_AUTHORING.md) covers **create → validate →
test**, this document covers **inspect → debug → modify → repeat**: seeing
exactly what your agent saw and decided at each call, finding where two
runs first behaved differently, and containing a callback that never
returns instead of hanging the tool. See
[docs/specs/agent_lab.md](specs/agent_lab.md) for the full design
rationale and architecture if you need it; this document is the
user-facing reference.

## Mental model

Every native match already writes a canonical `replay.jsonl` — what
actually happened in the arena, tick by tick. `bytefray agents
test`/`agents validate` additionally write an optional `trace.jsonl` —
what your agent was *shown* and what it *decided* at each `reset()`/
`act()` call that produced that replay.

```
replay.jsonl  -- match state: arena bytes, ownership, score, events
trace.jsonl   -- Agent API decisions: Observation in, AgentAction out (or a failure)
```

They answer different questions. "Did I win, and when did I lose
territory?" is a replay question — use `bytefray replay`. "Why did my
agent write to that address on tick 37?" or "why was my action rejected?"
is a trace question — use `bytefray agents inspect`. Neither replaces the
other, and reading a trace never re-runs your agent's code.

## The commands

| Command | Question it answers | Runs agent code? |
|---|---|---|
| `agents validate` | Can the agent satisfy one Agent API lifecycle call? | Yes (one `reset`/`act`) |
| `agents test` | Can the agent play a short real match, and what happened? | Yes (a full development match) |
| `agents inspect <run-dir>` | What did this run's agent see/decide? | No — reads `trace.jsonl` only |
| `agents diverge <run-a> <run-b>` | Where did two runs first disagree? | No — reads two `trace.jsonl` files only |

`inspect`/`diverge` never execute agent code, need no timeout, and take a
plain filesystem path — either a run directory (they look for
`trace.jsonl` inside it) or a direct path to a trace file.

## Inspecting one run

```bash
# Summary: schema, seed, tick range, decision/reset counts, failures
bytefray agents inspect runs/agents_test/my_agent/<run-label>
```

```text
trace: <data_root>/runs/agents_test/my_agent/<run-label>/trace.jsonl
schema: bytefray.agent_trace v1
match_seed: 1337
supervised: True
agent_call_timeout: 5
agents: A=my_agent, B=reference
ticks: 1-117
decisions: 936
resets: 2
failures: 0
```

```bash
# What both agents decided on exactly tick 37
bytefray agents inspect runs/agents_test/my_agent/<run-label> --tick 37

# Just my_agent's decisions in a window around tick 37
bytefray agents inspect runs/agents_test/my_agent/<run-label> --around 37 --window 5 --agent A

# Only records carrying a failure diagnostic
bytefray agents inspect runs/agents_test/my_agent/<run-label> --failures
```

A decision record shows the full `Observation` the agent received, and
either the `AgentAction` it returned or the diagnostic that explains why
it didn't:

```text
tick: 37
agent: A
action_slot: 2
wall_time_ms: 0.412
  observation.pc: 123
  observation.register_a: 1
  observation.register_p: 4
  observation.zero_flag: False
  observation.last_read: 99
  observation.alive: True
  action: write operand=250 value=165
```

**Tick meaning is unambiguous by construction**: a decision record's
`tick` is exactly the tick the observation was produced for — the same
integer the canonical replay's tick uses for the *result* of that
decision. A decision at tick 37 describes what the agent decided while
`replay.jsonl`'s tick-37 snapshot was being produced; the snapshot itself
already reflects that decision's effects (a successful `WRITE`'s byte
change, or a forfeit event for a failed call).

## Comparing two runs

After changing agent code, run `agents test` again and compare the new
run against the old one:

```bash
bytefray agents diverge \
  runs/agents_test/my_agent/2024-01-01T000000-vs-reference \
  runs/agents_test/my_agent/2024-01-02T000000-vs-reference
```

No divergence:

```text
status: identical
trace_a: .../2024-01-01.../trace.jsonl
trace_b: .../2024-01-02.../trace.jsonl
No divergence found: every matched decision agrees.
```

First disagreement:

```text
status: diverged
trace_a: .../trace.jsonl
trace_b: .../trace.jsonl
tick: 12
agent: A
reason: action/diagnostic differ
--- trace a ---
tick: 12
...
  action: write operand=250 value=165
--- trace b ---
tick: 12
...
  action: write operand=250 value=200
```

**What counts as a divergence**: only the `action`/`diagnostic` at a
matched `(tick, agent, action_slot)` key. `wall_time_ms` and header
metadata (agent display names, seed, timeout) are never compared, so two
runs that made the identical decisions are never reported as diverged
merely because one happened to run faster or was invoked with a
differently-named opponent. A decision present in one trace but missing
from the other at the same key (including one trace simply being shorter)
is itself reported as a divergence — never silently ignored — at the
first tick/agent where that happens.

## Timeout semantics

`--timeout SECONDS` (default `5.0`, valid range `0.1`–`300.0`) applies
uniformly to worker startup + agent load, `reset()`, and *each individual*
`act()` call — one number, not four. When a call exceeds it:

| Stage | Diagnostic | Effect |
|---|---|---|
| load | `agent_load_timeout` | Match never starts (initialization failure) |
| reset | `agent_reset_timeout` | Match never starts (initialization failure) |
| act | `agent_action_timeout` | That entrant forfeits; the match continues with the survivor |

A worker that crashes or exits unexpectedly is reported as
`agent_worker_exited`; a response that can't be parsed is
`agent_worker_protocol_error`. All five reuse the same structured
diagnostic shape (`code`/`stage`/`message`) every other Agent API failure
already uses — there is no separate error vocabulary to learn.

`agents test`/`agents validate` are supervised by default at their CLI
entry points (5-second timeout); `bytefray run`/`bytefray tournament`
remain completely unsupervised and untimed, exactly as before Agent Lab
existed — nothing about normal match/tournament execution changed.

## Security boundary

**Agent Lab's worker isolation is development-time hang containment, not
a security sandbox.** Supervised agent code runs with the same OS-level
privileges as Bytefray itself: it can read/write files, open network
connections, spawn further processes, and consume unbounded CPU/memory up
to the timeout. The only guarantee is that Bytefray's own tooling stops
*waiting* for a stalled call and reports which phase stalled. There is no
protection against deliberately hostile code anywhere in this design —
**run only agents you trust**, supervised or not.

## Performance tradeoff

Supervised execution spawns one worker subprocess per Python entrant and
adds an IPC round trip to every `load`/`reset`/`act` call. Measured on a
200-tick, `instr_per_tick=8`, Python-vs-Python development match on this
checkout (best of 3):

| Mode | Wall time (best of 3) |
|---|---|
| unsupervised, untraced (`bytefray run`'s own code path) | ~121 ms |
| unsupervised, traced (`trace_path` set, no timeout) | ~196 ms |
| supervised, traced (default 5.0s timeout, no timeouts hit) | ~811 ms |

Tracing alone is cheap (a few dozen extra milliseconds for a whole
200-tick match) — leaving it on by default (as `agents test`/`agents
validate` do) costs little. Supervision's per-call IPC round trip is the
dominant cost, an order of magnitude slower than the unsupervised path —
this is the accepted, documented tradeoff for being able to name which
phase hung rather than only reporting "the match didn't finish." A
development loop calling `agents test` a handful of times while iterating
on one agent stays well under a second either way; it is not intended for
tight inner-loop use at tournament scale (`bytefray run`/`tournament`
never pay this cost — see "Timeout semantics" above).

## Troubleshooting

**"No trace.jsonl found under directory"** — the run was made with
`--no-trace`, or the path doesn't point at an `agents test`/`agents
validate` run directory. Point `agents inspect`/`diverge` at the exact
directory the failing command printed, or at the `trace.jsonl` file
directly.

**A trace file fails to parse** — `agents inspect`/`diverge` exit `2`
with `code: trace_format_invalid` and an exact `file:line` location. A
trace is only ever malformed if something outside Bytefray's own writer
touched it (hand-edited, copied mid-write, or from an incompatible
schema version) — the writer itself flushes one complete JSON line per
record, never a torn partial write under a normal process kill (see
`battle_engine.agent_trace.TraceWriter`'s docstring for exactly what is
and isn't guaranteed).

**"Could not read trace: unsupported trace schema version"** — the trace
was written by a newer/older Bytefray than the one reading it. Trace
files are not intended to outlive the Bytefray version that wrote them
across a schema bump; re-run `agents test`/`agents validate` to produce a
fresh one.

**A supervised run is much slower than I expected** — see "Performance
tradeoff" above; this is expected for the supervised path. If you don't
need hang containment for this particular run, `--timeout` still defaults
to on for the CLI, so there is currently no `--no-timeout` escape hatch
short of calling the library functions (`test_agent`/`validate_agent`)
directly with `timeout=None`, which is what `bytefray run`/`tournament`
already do.

**My agent's `input()` call raised `EOFError` under a supervised run** —
expected and intentional: a supervised worker's protocol messages travel
over the same stdin/stdout pipes an ordinary Python process would expose
to `input()`/`print()`. The worker redirects agent-visible `stdout` to
`stderr` and agent-visible `stdin` to an empty, already-at-EOF stream
before any agent code runs, specifically so agent I/O can never desync
the protocol — `print()` for debug output is safe (it lands on stderr,
visible in the worker's captured crash context on a later failure), but
an agent should not depend on reading interactively from stdin in either
supervised or unsupervised mode.
