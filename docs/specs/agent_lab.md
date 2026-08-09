# Agent Lab (v0.5) — deterministic decision tracing and hung-agent containment

Status: design spec, written before implementation, per `CONTRIBUTING.md`'s
spec → issue → prompt → PR flow. Relationship to v0.4: v0.4.0 shipped
`create → validate → test → replay` (`docs/specs/agent_scaffold.md`,
`agent_validation.md`, `agent_test.md`, `agent_designer_workflow.md`,
`replay_analysis.md`). This spec covers the second half of the loop —
`inspect → debug → modify → repeat` — as **Agent Lab**.

## 1. User problem

Today an agent author can validate one lifecycle call (`agents validate`),
run a deterministic short match (`agents test`), and inspect the resulting
replay (`bytefray replay`). They cannot, without reading raw JSONL by hand:

- see what `Observation` their agent received on a specific tick, or what
  `AgentAction` it returned;
- tell *why* the runtime rejected an action or forfeited the agent;
- find the first tick at which two runs of the same code/seed diverged;
- know whether their agent is hanging inside `reset()` or `act()`, or which
  specific call stalled;
- get any of that back if the agent never returns from a call at all — today
  nothing but Ctrl-C or the OS can stop a hung `agents test`/`agents
  validate`/Designer run (`docs/AGENT_API_V1.md`'s documented limitation,
  confirmed empirically: `python_runtime.py`'s two call sites narrow their
  `except` to `Exception`, deliberately, specifically so a genuine
  non-returning `while True: pass` is *not* caught by anything).

Agent Lab addresses both halves of this: **deterministic behavioral
introspection** (what did the agent see/do, and when did two runs diverge)
and **hung-agent containment** (stop waiting, and say which phase stalled).

## 2. Repository findings

These were established by direct source reading (`engine/src/battle_engine`,
`client/src/battle_client`, `app/`, `docs/specs/`, `.github/workflows/`)
before any design decision below was made.

### Runtime

1. Agent calls happen at exactly two sites, both in
   `python_runtime.py`: `PythonEntrantController.__init__` calls
   `loaded.instance.reset(context)` (line 345); `PythonEntrantController.run`
   calls `state.loaded.instance.act(_observation(tick, state))` (line 402)
   inside the per-tick, per-action-slot loop. `agent_validation.py` calls the
   identical two methods directly (no `PythonEntrantController`) for its
   one-tick dry run.
2. Immediately before `act()`, `Observation` (frozen, 8 primitive fields:
   `tick, agent_id, pc, register_a, register_p, zero_flag, last_read,
   alive`) is the entire runtime state the agent is allowed to see — no
   arena, no opponent state, no VM/Kernel reference.
3. Immediately after an action, `apply_action()` (line 259) has mutated the
   engine-owned `PythonEntrantState` (and, for `WRITE`, one arena byte via
   `vm._wr8`) — this is what the *next* Observation and the tick's
   `MemoryDiff`/`AgentState` replay records reflect.
4. Diagnostics are already fully centralized: one frozen `RuntimeDiagnostic`
   dataclass (`code, stage, message, agent_id, slot, exception_type, tick,
   action_slot`) and four shared `diagnose_*` constructor functions, reused
   verbatim by real matches, `agents validate`, and `agents test`. Every
   spec examined states explicitly that inventing a second diagnostic
   vocabulary is an anti-pattern to avoid.
5. Already captured per tick in the canonical replay: end-of-tick
   `AgentState`, `score`, `memory_diffs` (actual written bytes), and
   `events` (`kill/death`, `spawn/move/territory/claim`, `forfeit`).
   Explicitly **not** captured, confirmed both in `docs/REPLAY_SCHEMA.md`
   ("Python Observation capture: explicitly out of scope") and by reading
   `python_runtime.py` itself: the raw `Observation` handed to each `act()`
   call, the raw `AgentAction` returned, wall-clock call duration, and
   individual RNG draws inside agent code. An agent can make up to
   `config.instr_per_tick` (default 8) actions per tick; only the
   *end-of-tick* state survives into the replay.
6. Action production and action execution are already cleanly separated at
   the call-site level: `action = instance.act(observation)` (production,
   agent-owned) is a distinct statement from `apply_action(action, state,
   vm)` (execution, engine-owned) two lines later. Production never touches
   `vm` or other agents; execution never calls into agent code. This is the
   exact seam Agent Lab instruments — nothing about the boundary needs to
   move.

### Determinism

7. Determinism today rests on: a single `Config.seed` (default 1337);
   `derive_agent_seed(match_seed, slot, agent_id, api_version)`
   (`python_runtime.py:197`) — SHA-256 over an explicit byte string,
   deliberately avoiding Python's randomized `hash()` — producing one
   `int.from_bytes(digest[:16], "big")` seed per entrant; and strictly
   sequential, spawn-order scheduling within a tick (`AGENT_API_V1.md`:
   "entrant A completes its quota before entrant B begins").
8. The VM match path owns its own `Kernel.rng` (`core.py:62`); this is
   invisible to and independent of any Python agent's RNG. Python agents are
   handed a *live* `random.Random` object via `MatchContext.rng`
   (`agent_api.py:71`) at `reset()` — not merely a seed. The bundled
   reference/starter agent persists this object as `self.rng` in `reset()`
   and reads it in every `act()` (`data/agent_template/agent.py`) — i.e.
   agents commonly keep a live reference to engine-handed state across the
   whole match, not just a copy.
9. Subprocess isolation of Python agents does **not** inherently break
   determinism, provided two things are preserved: (a) `MatchContext.rng`'s
   live-object semantics are replaced by *seed-based reconstruction inside
   the same process that owns the agent* — a subprocess can call the exact
   same `derive_agent_seed()` and build its own `random.Random(seed)`
   locally, which is byte-identical to what the parent does today, so long
   as the seed derivation itself is not duplicated/reimplemented; and (b)
   strict spawn-order, sequential-scheduling semantics are not reordered by
   subprocess concurrency. Nothing else in the codebase relies on
   cross-agent shared mutable state reachable from agent code (the one
   shared object, the arena/`VM`, is never handed to agent code — only
   engine-side `apply_action` touches it), and nothing relies on Python's
   randomized-hash `dict`/`set` iteration order (`stable_id`/`canonical_json`
   already sort keys explicitly).
10. To reproduce one `act()` call in isolation, the input needed is exactly
    one `Observation` (trivially JSON-serializable: 8 primitive fields, no
    nested objects) plus whatever internal state the agent's own instance
    has accumulated since `reset()`. `Observation`/`AgentAction` are both
    trivially serializable; `MatchContext` is not, because of the live
    `random.Random` — see finding 9's mitigation.

### Process architecture

11. The architecture assumes one agent instance lives for the entire match
    in-process: `load_python_agent` constructs exactly one instance via the
    factory once; `reset()` is called once; every subsequent `act()` call
    across every tick is made against that same object. No direct
    references to engine objects (VM, Kernel, other agents) are ever handed
    to agent code; the sole exception is `MatchContext.rng` itself (a live
    object, not a copy) — the one place a subprocess redesign has to change
    something.
12. There is no `multiprocessing` usage anywhere in the repository today,
    and no per-agent worker-process infrastructure to build on. The two
    existing subprocess precedents are: `pmars.py`'s
    `subprocess.run(..., timeout=DEFAULT_TIMEOUT_SECONDS)` (the one place
    in the codebase that already does hard external-process timeout
    containment, no shell, argument-list spawn), and the Designer's
    `QProcess`-per-CLI-invocation pattern (out-of-process specifically
    *because* agent code is untrusted and unbounded, but with **no
    timeout** — the only termination path today is a manual, user-triggered
    `kill()`). `AGENT_API_V1.md` explicitly names "per-callback workers...
    whole-match worker containment" as a documented future direction, not
    yet built.
13. `engine/src/battle_engine/launchers.py` already has the exact
    frozen-vs-source resolution and argument-list-only spawn pattern needed
    for a new worker process: `build_agents_command(subcommand, arguments)`
    resolves either `[<battle2.exe>, "agents", subcommand, ...]` (frozen) or
    `[<python>, "-m", "battle_engine", "agents", subcommand, ...]` (source)
    — generic over `subcommand`, so a new internal verb needs no new
    launcher function, only a new dispatch branch in `command.py`'s
    `_agents()`. This sidesteps `multiprocessing`'s Windows-frozen
    `freeze_support()` danger zone entirely: a worker is just another
    invocation of the same already-frozen executable with a hidden
    subcommand, exactly like pMARS/QProcess-launched CLI already are today.

### Replay

14. Debugging information (per-callback Observation/Action) *could*
    technically be added as new optional fields on `TickSnapshot` — v3 was
    explicitly designed to be extended in place with safe defaults. But the
    schema's own documentation draws a deliberate, hard line: per-callback
    agent state is "agent diagnostic history, not match state"
    (`REPLAY_SCHEMA.md`). Folding it into `battle2.replay` would go against
    that documented intent and would inflate every canonical replay
    (measured: a 200-tick 2-agent match's `replay.jsonl` is ~193 KB today)
    even for ordinary tournament/production matches that never asked for
    tracing. A separate, opt-in artifact is more consistent with existing
    precedent and imposes zero cost on callers who don't ask for it.

### GUI

15. The Designer's Agent Development tab (`app/views/development.py`) is
    unambiguously the right home — it already owns the
    `create → validate → test → replay` loop end-to-end; a fourth top-level
    tab would fragment that loop for no benefit. `app/` has exactly two
    existing `QDialog` subclasses (`NewAgentDialog`, `TournamentDialog`),
    neither a read-only tick-navigation viewer — a Trace Inspector dialog is
    a new *shape* in `app/`, but its tick-stepping semantics can mirror
    `battle_client.session.ReplaySession`'s existing
    `seek`/`step_forward`/`current_tick` API rather than inventing new
    navigation vocabulary. Replay viewing can and should remain external
    (`Open Replay` already launches the existing external viewer
    in-process via `open_pygame_client_direct`) — nothing about trace
    inspection requires embedding Pygame; `PygameCanvas` was already
    evaluated and explicitly rejected for the Development tab in
    `agent_designer_workflow.md` §16 for unrelated reasons that still hold
    (it doesn't call the renderer's real lifecycle methods).

## 3. Alternatives considered and rejected

**Trace folded into `battle2.replay`.** Rejected (finding 14): contradicts
documented schema intent, inflates every match's canonical artifact size
regardless of whether tracing was requested, and could not cleanly express
"more than one action per tick" without further schema surgery. A sibling
`trace.jsonl` costs nothing when absent and nothing changes for `bytefray
run`/tournament/`replay` consumers.

**Hung-agent containment: Option A (whole-process external timeout only).**
Rejected as the *sole* mechanism: it can only report "the match hung," not
which phase/agent/call stalled — the exact question the challenge asks
Agent Lab to answer. Kept as a documented parent-side safety net
underneath Option B (see §6).

**Hung-agent containment: Option C (match-level heartbeat supervisor,
no worker process).** Considered: a supervisor thread could poll "which
phase are we nominally in" and time out the whole match. Rejected because
it cannot recover a single stuck call and continue the match with the
survivor — CPython has no safe way to force a hung synchronous call in the
*same* process to return control, so a supervisor without a process
boundary can only ever kill the entire match, same ceiling as Option A.

**Hung-agent containment: `multiprocessing`/`ProcessPoolExecutor`.**
Rejected in favor of plain `subprocess.Popen` + the existing
`launchers.py`/`build_agents_command` pattern. `multiprocessing` on
Windows requires `spawn` start method plus `freeze_support()` wired into
every frozen entry point, and the repository has zero existing precedent
or packaging coverage for that combination. A worker that is simply
another invocation of the same executable (source or frozen) with a
hidden `agents _worker` subcommand needs none of that — it reuses the
exact spawn-safe, argument-list-only mechanism `pmars.py` and Designer's
`QProcess` launches already use in production today.

**Hung-agent containment: per-*call* subprocess (fresh process per
`act()`).** Rejected: `random.Random` state and any agent-instance state
accumulated in `reset()`/prior `act()` calls would have to be serialized
and restored every single call — for a 200-tick match at
`instr_per_tick=8`, up to 1,600 calls per agent. The chosen design (§6)
keeps one worker process alive for the agent's whole match — RNG and
instance state simply live there, no serialization of agent internals
ever needed, and IPC only carries the already-trivially-serializable
`Observation`/`AgentAction`/diagnostic payloads.

**One worker abstraction reused for `bytefray run`/tournament too.**
Rejected for this iteration. `bytefray run`/tournament are the "normal
match path" the challenge explicitly says must stay unchanged and must
not be destabilized to support development-time timeouts. `MatchRequest`
gains two new, independently optional fields (`trace_path`,
`agent_call_timeout`) that default to `None`/absent, so every existing
caller (`cli.py`, `tournament_service.py`) is provably unaffected — the
in-process, untimed `PythonEntrantController` path they use today is not
touched. If workers later prove valuable for normal execution too, that
is a separate, later decision with its own justification; nothing here
forecloses it, but nothing here assumes it either.

**Trace/replay divergence: general diff framework.** Rejected. A trace
record is `(tick, agent_id, phase) -> (observation, action_or_diagnostic)`;
first divergence between two traces is a single linear merge-compare over
that keyspace (§9) — under 80 lines including CLI wiring. Building a
generic diff engine would be solving a problem Agent Lab does not have.

## 4. Chosen architecture

Two independently-optional `MatchRequest` fields, both defaulting to "off,"
so `bytefray run` and the tournament service are provably unaffected:

- `trace_path: Path | None = None` — when set, `bytefray.agent_trace` v1
  decision records are appended as the match runs (works with or without
  supervision; see below).
- `agent_call_timeout: float | None = None` — when set, Python entrants for
  *this* match run through **one worker subprocess per Python entrant, kept
  alive for the whole match** (Option B, refined per finding 13: no
  `multiprocessing`, just `subprocess.Popen` on the same executable with a
  new hidden `agents _worker` verb, mirroring `pmars.py`'s external-timeout
  precedent at per-call granularity instead of whole-process granularity).
  The worker owns the agent instance, its derived RNG, `reset()`, and
  `act()`; the parent (engine) continues to own the arena, tick scheduling,
  and `apply_action` — execution stays exactly where it is today (finding
  6), only production moves out of process.

`agent_test.py` and `agent_validation.py` (the two "development test" CLI
tools, plus the Designer buttons that shell out to them) set both fields by
default; `bytefray run`/`tournament` never set either, so their code path
is byte-for-byte what it was in v0.4.0.

```
normal match path (bytefray run, tournament)
    MatchRequest(trace_path=None, agent_call_timeout=None)
    -> PythonEntrantController                     [unchanged, in-process, untimed]

development/debug match path (agents test, agents validate, Designer)
    MatchRequest(trace_path=<path>, agent_call_timeout=<seconds>)
    -> SupervisedPythonEntrantController
           -> AgentWorkerHandle (subprocess) per Python entrant
           -> same apply_action/tick-scheduling/scoring loop as today
```

Both paths still terminate in the identical `_finalize_native_artifacts`
canonical-replay/result writer — "both ultimately use the same
authoritative match semantics" (challenge's own scope constraint) holds by
construction, since only the entrant *production* mechanism differs.

## 5. Trace schema — `bytefray.agent_trace` v1

Separate, optional, append-friendly JSONL, versioned independently of
`battle2.replay`/`battle2.result`. One JSON object per line.

**Header record** (first line):
```json
{"schema": "bytefray.agent_trace", "schema_version": 1, "record_type": "header",
 "match_seed": 1337, "agents": {"A": "my_agent", "B": "reference"},
 "supervised": true, "agent_call_timeout": 5.0}
```

**Decision record** (one per `act()` call attempt, in call order):
```json
{"record_type": "decision", "tick": 37, "agent_id": "A", "action_slot": 2,
 "wall_time_ms": 0.41,
 "observation": {"tick": 37, "agent_id": "A", "pc": 123, "register_a": 1,
                 "register_p": 4, "zero_flag": false, "last_read": 99,
                 "alive": true},
 "action": {"kind": "write", "operand": 250, "value": 165},
 "diagnostic": null}
```
`action` is `null` and `diagnostic` is populated (the exact
`RuntimeDiagnostic` fields, `asdict`-serialized) when the call raised,
returned an invalid action, timed out, or the worker exited unexpectedly.
Exactly one of `action`/`diagnostic` is non-null.

**Reset record** (one per entrant, before tick 1):
```json
{"record_type": "reset", "agent_id": "A", "wall_time_ms": 1.8, "diagnostic": null}
```

**Tick meaning is unambiguous by construction, not by convention**: a
decision record's `tick` is the exact `tick` value passed into
`_observation(tick, state)` at that call site — the identical integer the
canonical replay's `TickSnapshot.tick` uses for the tick being produced.
A decision record for tick *N* describes the observation seen and action
attempted *while producing* `TickSnapshot` *N*; the snapshot itself
reflects the *post-action* effects. This is documented as "trace tick N
inputs, describes what the agent decided that shaped replay tick N's
outputs" and is exercised by an explicit correlation test (§15).

Trace files are pure Agent API boundary data — `Observation`,
`AgentAction`, `RuntimeDiagnostic` fields, plus scalar timing/index
integers. No agent Python object is ever serialized.

## 6. Process model

`engine/src/battle_engine/agent_worker.py` (new):

- **Wire format**: newline-delimited JSON (NDJSON) over the worker's stdin
  (parent → worker requests) and stdout (worker → parent responses), one
  object per line, flushed immediately after each write. stderr is left
  for the worker's own crash output (captured, attached to a diagnostic on
  unexpected exit; never parsed as protocol).
- **Requests**: `{"cmd": "load", "spec": {...AgentSpec fields, Paths as
  str...}, "agent_id": "A", "slot": 0}`, `{"cmd": "reset", "match_seed":
  1337, "api_version": 1, "tick_limit": N, "action_budget": M}`,
  `{"cmd": "act", "observation": {...}}`, `{"cmd": "shutdown"}`.
- **Responses**: `{"ok": true, ...}` or `{"ok": false, "diagnostic":
  {...RuntimeDiagnostic fields...}}`. The worker reconstructs its own
  `random.Random` from `derive_agent_seed(match_seed, slot, agent_id,
  api_version)` — the *exact* production function, imported unchanged from
  `battle_engine.python_runtime` — never receiving a live RNG object over
  the wire, which is what makes worker-mode byte-identical to in-process
  mode (finding 9).
- **Parent side**: `AgentWorkerHandle` spawns the worker via
  `launchers.build_agents_command("_worker", [])` (no shell, argument list,
  frozen-or-source resolved exactly like every other child process in this
  codebase) with `subprocess.Popen(..., stdin=PIPE, stdout=PIPE,
  stderr=PIPE, text=True, bufsize=1)`, then starts one dedicated daemon
  reader thread that blocks on `stdout.readline()` in a loop and pushes
  each decoded line onto a `queue.Queue` (chosen specifically because
  Windows named/anonymous pipes to a child process are not `select()`-able
  the way POSIX pipes are — a blocking-read-plus-queue is the one pattern
  that is portable to both platforms without new C extensions). Every
  request/response round trip is `queue.get(timeout=T)`; on `queue.Empty`,
  the call is timed out: the handle calls `Popen.kill()` (unconditional,
  no grace period — mirrors the Designer's own documented `_dispose_process`
  policy, "the only softer option that exists anywhere in this codebase
  today would have to be newly invented"), joins the reader thread, and
  returns a timeout diagnostic to the caller. `readline()` returning `""`
  (EOF) before a response arrives is distinguished from a timeout and
  reported as `agent_worker_exited` with the child's exit code.
- **Cleanup**: `SupervisedPythonEntrantController` closes every worker in a
  `finally` (parent process exit, exception, or normal completion all
  reach it); each `AgentWorkerHandle.close()` sends `shutdown`, waits a
  short bounded join, and force-kills if the worker hasn't exited — no
  code path can leave a worker process outliving its parent's `run()` call.
  If the *parent itself* is killed (Ctrl-C reaching the console process
  group, or the Designer's own process ending), the worker's stdin pipe
  breaks; the worker's blocking `readline()` on its own stdin returns EOF
  and the worker exits on its own — no explicit parent-liveness heartbeat
  needed for this failure mode, since it is the natural consequence of a
  closed pipe, and is covered by a test (§15).

## 7. Timeout semantics

- One timeout value (`agent_call_timeout`, seconds, `float`) applies
  uniformly to *load* (worker startup + `load_python_agent` inside it),
  *reset*, and *each individual* `act()` call — one number, not four, to
  keep the CLI/API surface small; splitting them out is not justified by
  any evidence gathered (no finding above suggests load/reset/act need
  materially different budgets for a development-loop use case).
- **Default: 5.0 seconds.** Chosen as "forgiving enough for ordinary
  Python, finite" per the challenge's own framing — generous relative to
  the measured supervised overhead (§13: single-digit milliseconds per
  call in the common case), while still bounding a `agents test` run's
  worst case (`200 ticks * 8 actions * 5s = 8000s` absolute ceiling per
  agent if *every single call* hung, which does not happen in practice
  since a hang forfeits its entrant and the match proceeds with the
  survivor — see below).
- **CLI**: `--timeout SECONDS` on `agents test` and `agents validate`.
  Bounds enforced at the argument parser: `0.1 <= timeout <= 300.0`
  (`argparse.ArgumentTypeError` outside that range) — a value below 0.1s
  could not complete even a trivial `reset()` on a loaded interpreter, and
  above 300s stops being a "development loop" tool and starts being
  indistinguishable from no timeout at all.
- **Diagnostics** (new codes, same `RuntimeDiagnostic` shape, same
  `diagnose_*` construction pattern as the four existing functions):
  - `agent_load_timeout` (stage `"load"`)
  - `agent_reset_timeout` (stage `"reset"`)
  - `agent_action_timeout` (stage `"action"`, carries `tick`/`action_slot`)
  - `agent_worker_exited` (stage matches whichever call was outstanding;
    carries `exception_type="WorkerExited"` and the child's exit code in
    the message text)
  - `agent_worker_protocol_error` (a response line failed to parse as
    JSON, or was missing required fields — treated as equivalent to a
    crash, never raised to the caller as a raw `JSONDecodeError`)
- **Result/replay behavior on timeout**: identical shape to today's
  existing failure handling, reusing the exact same control flow —
  a load/reset timeout during initialization raises
  `PythonEntrantInitializationError(diagnostic)` (match never starts,
  exactly like a real reset exception today); an `act()` timeout forfeits
  that entrant via the existing `_forfeit()` path (match continues with
  the survivor, exactly like an `act()` exception today) and appends a
  `RuntimeEvent(event_type="forfeit", reason="agent_action_timeout", ...)`
  to that tick's replay events, same as any other forfeit reason. No new
  replay schema surface is needed — timeout forfeits are structurally
  identical to exception forfeits, just a different `reason` string.
- **Unsupervised path (`agent_call_timeout=None`) is unaffected** — this
  is the load-bearing compatibility guarantee for `bytefray
  run`/tournament: zero behavior change, zero new failure modes, because
  the code path they execute is textually the same `PythonEntrantController`
  that shipped in v0.4.0.

## 8. Determinism contract

**Claim**: for fixed `(agent source, opponent source, seed, config)`, a
supervised run's sequence of `(tick, agent_id, action)` decisions is
identical to an unsupervised run's, and identical across repeated
supervised runs, *provided no call actually times out* (a timeout is, by
definition, the one case where wall-clock reality — not the deterministic
model — decides the outcome; this is stated as an explicit, documented
exception, not silently glossed over).

**Why this holds** (grounded in findings 7–10): the only piece of
`MatchContext`/entrant state that is not already a plain serializable
primitive is the live `random.Random` object, and the worker reconstructs
it from the identical `derive_agent_seed()` call the parent uses today —
not a copy of the parent's live object, a *re-derivation*, which is
provably identical because the function is deterministic and pure. Every
other value crossing the process boundary (`Observation`, `AgentAction`,
diagnostics) is already a primitive-only dataclass. Scheduling order is
untouched: the parent still calls entrants strictly in spawn order, one
`act()` request at a time, and blocks for that entrant's response before
moving to the next action slot — there is no concurrency between entrants'
`act()` calls to reorder.

**Tests proving this** (§15): same-seed-same-code run twice, unsupervised
vs. supervised, assert identical winner/termination/score and
tick-by-tick identical `battle2.replay` tick records (excluding only
fields that are allowed to differ for reasons unrelated to determinism,
e.g. none currently — replay content itself carries no wall-clock/PID/etc,
so full equality is the actual bar); and two independent supervised runs
of the same input, trace-vs-trace, asserting `first_divergence(...)`
returns `None`.

## 9. First-divergence tool

`bytefray agents diverge <trace-a> <trace-b>` (and the underlying
`battle_engine.agent_trace.first_divergence(a, b) -> Divergence | None`).
Both trace documents are parsed into `(tick, agent_id) -> DecisionRecord`
maps; the function walks ticks in increasing order and, within a tick,
agents in the order they first appear in trace A, comparing each matched
`(tick, agent_id)` pair's `action`/`diagnostic`. Returns the first
`(tick, agent_id)` where they differ (different action kind/operand/value,
one succeeded and the other has a diagnostic, or one trace has a decision
the other lacks at the same key) — `None` if every matched key agrees
through the shorter trace's range (a length mismatch alone, with no
observed disagreement, is reported as `"traces diverge in length"` at the
first tick past the shorter trace's end, not silently ignored).

## 10. CLI UX

Following the existing `bytefray agents <verb>` nested-dispatch pattern
(`command.py`'s `_agents()` — one more `if argv and argv[0] == "<verb>"`
branch per verb, each a lazy import of a dedicated `<verb>_main`):

```
bytefray agents test <agent-id> [--opponent ID] [--seed N] [--ticks N]
                                 [--timeout SECONDS] [--no-trace]
bytefray agents validate <agent-id> [--timeout SECONDS] [--no-trace]

bytefray agents inspect <run-dir> [--tick N] [--agent ID]
                                   [--around N [--window K]] [--failures]
bytefray agents diverge <run-dir-a> <run-dir-b>
```

- `--timeout` defaults to 5.0 (§7); `--no-trace` opts an individual run out
  of the (otherwise on-by-default, since it is cheap — §13) trace artifact.
- `<run-dir>` for `inspect`/`diverge` is the same directory `agents test`
  already prints (`runs/agents_test/<agent-id>/<run-label>/`) — the tool
  reads `trace.jsonl` from inside it; a bare path directly to a
  `trace.jsonl` file is also accepted, so a trace can be inspected even if
  copied elsewhere.
- No `--tick`: prints a summary (record counts, tick range, per-agent
  forfeit/timeout counts) — a fast overview before drilling in.
- `--tick N`: prints the decision record(s) at that tick (both agents
  unless `--agent` narrows it), in the same `label: value` stdout
  convention every other `agents` verb already uses — no new output
  format invented.
- `--around N --window K`: prints decisions for ticks `[N-K, N+K]`.
- `--failures`: prints only decision/reset records carrying a diagnostic.
- `agents inspect`/`agents diverge` execute **zero agent code** — they only
  parse an already-written JSONL file — so unlike `validate`/`test` they
  need no timeout, no QProcess/subprocess isolation, and no `--data-root`
  ambiguity; they take a filesystem path directly.
- Exit codes: `0` for a successful inspection/comparison (including "no
  divergence found" — that is a successful, informative answer, not a
  failure); `2` for a missing/unreadable/malformed trace file
  (`code="trace_file_missing"`/`"trace_format_invalid"`, same
  `RuntimeDiagnostic`-shaped stderr as every other tool failure).

## 11. Designer UX

Extends the existing Agent Development tab (`app/views/development.py`),
no new top-level tab (finding 15):

```
Development Test
  Opponent [combo]  Seed [spin]  Ticks [spin]  Timeout (s) [spin, default 5.0]
  [ Test ]

Last development test
  ...status text (unchanged)...

  [ Inspect Trace ]   [ Open Replay ]
```

`Inspect Trace` is enabled exactly when the last completed test wrote a
`trace.jsonl` (i.e. always, unless `--no-trace` — not exposed in the GUI,
tracing is unconditionally on there since §13 shows it's cheap). Clicking
it opens `TraceInspectorDialog` (new, `app/views/trace_inspector.py`) —
**not** run via `QProcess**: it only reads the already-written trace file
from disk, no agent code executes, so it can safely run on the GUI thread
exactly like the existing `Open Replay`/manifest-reading code paths do.

Dialog layout (deliberately modest — no source editor, no general
debugger, per the challenge's explicit constraint):
- Tick `QSpinBox` (bounded to the trace's recorded tick range) +
  Agent `QComboBox` (populated from the trace header's `agents` map).
- Prev/Next `QPushButton`s step to the previous/next decision record for
  the selected agent (skipping ticks where that agent made no call, e.g.
  after it died).
- Read-only `QPlainTextEdit` showing the selected record's tick, phase,
  wall time, full `Observation`, `AgentAction` or diagnostic — formatted
  text, not a raw JSON dump.
- A `Failures only` `QCheckBox` restricts Prev/Next to records carrying a
  diagnostic.

Parsing is entirely delegated to the Qt-free `battle_engine.agent_trace`
module (finding 15/challenge constraint "backed by a Qt-free
parser/domain model... do not bury JSON parsing inside widget callbacks")
— the dialog only formats already-parsed `DecisionRecord`/`ResetRecord`
dataclasses for display. This is the same reuse this codebase already
established for `agent_workflows.py` (Qt-free presentation parsing) and
`battle_client.analysis` (Qt/Pygame-free replay-domain functions) — Agent
Lab does not invent a new layering convention, it follows the one already
in use twice.

## 12. Artifact layout

```
runs/agents_test/<agent-id>/<run-label>/
    replay.jsonl     (unchanged, battle2.replay v3)
    result.json      (unchanged, battle2.result v1)
    summary.json      (unchanged, compatibility v2)
    trace.jsonl       (new, optional, bytefray.agent_trace v1)
```
Additive only. No consumer of the existing three files is touched; nothing
reads or requires `trace.jsonl` to exist. `agents validate` gains no run
directory (it has none today — it is a pure dry run with no persisted
artifacts beyond its own printed diagnostic) but *can* write a trace file
if `--timeout`/tracing is requested, via an explicit `--trace-path`
sibling option (default: none — validate's trace, if requested, must name
its own destination since there's no existing run directory to place it
in).

## 13. Performance

Measured on this checkout (200-tick, `instr_per_tick=8`, Python-vs-Python,
scaffold agent vs. bundled reference), wall-clock, best of 3:

| Mode | Time |
|---|---|
| baseline (`agents test`, v0.4.0 unmodified code path) | (measured, see final report) |
| traced, unsupervised (`trace_path` set, `agent_call_timeout=None`) | (measured, see final report) |
| supervised + traced (both set, default 5.0s timeout, no timeouts hit) | (measured, see final report) |

(Concrete numbers land in the implementation's final report, not
speculated here — the spec commits to *measuring*, not to a number chosen
in advance.)

## 14. Error model

No new diagnostic *shape* — every failure path returns the existing
`RuntimeDiagnostic` dataclass. New *codes* (§7) slot into the existing
`stage` vocabulary (`load`/`reset`/`action`) rather than inventing new
stages. `agents inspect`/`agents diverge` reuse the same dataclass for
their own tool-level failures (missing file, malformed JSON) with two new
codes (`trace_file_missing`, `trace_format_invalid`) — consistent with
`agent_test.py`'s own precedent of adding a small number of tool-specific
codes on top of the shared vocabulary rather than forking it.

## 15. Tests

- `engine/tests/test_agent_trace.py`: schema round-trip (write → read →
  equal), malformed-line handling (`TraceFormatError`), header validation,
  `first_divergence` (identical traces → `None`; one differing action →
  correct `(tick, agent_id)`; length mismatch → reported, not silently
  ignored).
- `engine/tests/test_agent_worker.py`: `AgentWorkerHandle` load/reset/act
  round trip against a real spawned worker process; per-call timeout
  (`act()` sleeps beyond the configured timeout) — **every such test uses
  a short worker-side sleep with an external pytest-level wall-clock
  timeout on the *test itself*** so a genuine implementation defect cannot
  hang the suite; worker crash (`os._exit` mid-`act()`) distinguished from
  timeout; malformed-response protocol error; parent-side cleanup leaves
  no process behind (checked via `psutil`-free `Popen.poll()` polling with
  its own bounded wait, not an indefinite `wait()`).
- `engine/tests/test_supervised_runtime.py`: `SupervisedPythonEntrantController`
  produces a `PythonRuntimeResult` structurally comparable to
  `PythonEntrantController`'s for the same deterministic inputs; a hung
  `act()` forfeits only that entrant and the match completes with the
  survivor; a hung `reset()` aborts initialization exactly like today's
  exception path.
- `engine/tests/test_agent_test.py` / `test_agent_validation.py`
  (extended, not forked): new fault-injection source-string fixtures
  (matching the existing inline-source-in-test-module convention, §6/8 of
  prior specs) covering `reset()` infinite loop and `act()` infinite loop,
  each wrapped in the same external-safety-timeout discipline as above.
- Determinism: same-seed-same-code repeated-run tests, both
  unsupervised-vs-supervised and supervised-vs-supervised (§8).
- Replay/trace correlation: fixture match with known forfeits at known
  ticks; assert `trace.jsonl`'s decision tick *N* diagnostic matches
  `replay.jsonl`'s `TickSnapshot` *N* forfeit event for the same agent —
  proves the "tick means observation-input-tick, replay tick N reflects
  that decision's effects" contract (§5) is not just documented but true.
- CLI: `agents inspect`/`agents diverge` subprocess-level tests (exit
  codes, `--tick`/`--around`/`--failures` filtering, malformed-file exit
  2).
- GUI (`gui`-marked, root `tests/`): `TraceInspectorDialog` opens from a
  fixture trace file without executing any agent code; tick/agent
  selectors and Prev/Next navigate correctly; `Inspect Trace` button
  enablement tracks whether the last test wrote a trace.
- Regression: full existing v0.4 authoring-workflow suite
  (`test_agent_scaffold.py`, `test_agent_validation.py`,
  `test_agent_test.py`, `test_agent_development_*` GUI tests) continues to
  pass unmodified, proving `agent_call_timeout=None`/`trace_path=None`
  behavior is unchanged.

## 16. Packaging

- New hidden verb `agents _worker` needs no new PyInstaller `.spec`/`datas`
  entries — it is dispatched from inside the already-bundled
  `battle_engine` package via the existing `battle2.exe`/source
  interpreter, exactly like `create`/`validate`/`test` today.
  `tools/agent_designer.spec`/`tools/battle2.spec` already bundle
  `battle_engine/data/agent_template` (the historical gap flagged in
  `agent_designer_workflow.md` §17.3 is already fixed as of this branch's
  base commit — confirmed by re-reading both spec files directly).
- No new executable (challenge's explicit preference) — the worker is
  reached only via the existing `battle2`/`bytefray` entry points.
- Frozen-build verification: extend `tools/build_win.ps1`'s existing
  `agents create` smoke section with an `agents test --timeout 5` smoke
  invocation against the frozen `battle2.exe`, proving the worker
  subprocess spawns correctly from a frozen parent (this is the one
  genuinely new frozen-specific risk — a frozen worker invoking `-m
  battle_engine` would be wrong; it must resolve through
  `_packaged_executable`, which `build_agents_command` already does).

## 17. Security / non-security boundary

Agent Lab's worker isolation is **development-time hang containment, not a
security sandbox.** This is stated here and repeated in the worker
module's docstring, the CLI `--help` text, and the Designer dialog: worker
agent code runs with the same OS-level privileges as the parent — it can
read/write files, open network connections, spawn further processes, and
consume unbounded CPU/memory up to the timeout. The only guarantee is that
Bytefray's own tooling will stop *waiting* for it and will report which
phase stalled. No claim of protection against deliberately hostile code is
made anywhere in the implementation.

## 18. Deferred / explicitly out of scope

- Extending worker-based execution to `bytefray run`/tournament (§3 —
  reversible future decision, not needed now).
- Per-RNG-draw logging inside agent code (would require instrumenting
  agent-authored code itself, crossing the "not a source debugger"
  boundary the challenge draws).
- A general trace diff/report framework beyond `first_divergence`.
- Embedding the Pygame renderer inside the Designer (already
  independently rejected, finding 15).
- Splitting `--timeout` into separate load/reset/act values (no evidence
  motivates it yet; can be added additively later if a real need appears).
- Mixed VM/Python matches remain unsupported — unrelated to and unaffected
  by this spec.

## Strongest argument against this architecture

The worker-per-entrant subprocess model roughly doubles the moving parts
in the Python match path for the *development* tools specifically: a new
wire protocol, a new process lifecycle, and a new class of failure modes
(protocol desync, partial-line reads, orphaned processes on unusual
termination) that simply do not exist in the unsupervised path. A
reviewer could reasonably ask whether Option A (bare external
whole-process timeout around `agents test` itself, already how the
Designer isolates `agents test`/`validate` via QProcess, just adding a
timer) would have delivered most of the practical value — "my agent
hung, and Bytefray told me so and got its console back" — for a small
fraction of this implementation's surface area.

This does not change the design, for one reason the audit already
established directly from the challenge's own success criteria: Option A
cannot answer *which phase stalled* (finding/§3), and "did it hang inside
reset() or act()?" is one of the explicit example questions Agent Lab is
asked to answer, not an optional nicety. A whole-process timeout can only
ever report "the match didn't finish in time" — it cannot distinguish a
legitimately slow-but-alive 200-tick match from a genuinely hung tick 3.
The residual risk (more moving parts, new failure modes) is accepted and
mitigated by keeping the worker boundary *additive and optional*
(`agent_call_timeout=None` is a complete, provable escape hatch back to
today's exact behavior) rather than a replacement for the existing path.

## Success criteria

- `agents test`/`agents validate` gain optional, off-by-default-safe,
  on-by-default-in-the-CLI-defaults timeout containment that can name the
  stalled phase/agent and recover the surrounding tool without killing the
  whole process.
- A `trace.jsonl` sibling artifact exists, is versioned, is
  human-inspectable, and costs negligible overhead relative to the
  existing baseline (§13).
- `bytefray agents inspect`/`bytefray agents diverge` and the Designer's
  `Inspect Trace` dialog answer the challenge's example questions ("what
  did it see on tick 37," "why was the action rejected," "where did two
  runs diverge") without reading raw JSONL by hand.
- Zero behavior change proven by tests for `bytefray run`/tournament/every
  v0.4 authoring workflow.
- No claim of security sandboxing anywhere in code, docs, or UI text.
