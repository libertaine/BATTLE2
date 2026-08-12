# Bytefray Agent Authoring Guide

Bytefray supports built-in and blob entrants in the native VM, Python agents in
homogeneous Python-versus-Python matches, and Redcode warriors through the
separate pMARS backend. Mixed Python/VM matches are not yet supported.

## Agent forms

| Form | Execution path |
|---|---|
| Built-in | Assembled into mutable native VM bytecode. |
| Blob | Loaded directly as native VM bytecode. |
| Python | Loaded through Agent API v1 and run against another Python agent. |
| Redcode | Passed to the separate pMARS backend. |

User agents live under the configured writable data root in
`agents/<discovery-name>/`. The directory name is the CLI discovery ID.

## Recommended: scaffold a starting agent

The fastest way to get a valid, immediately-discoverable Python agent is
`bytefray agents create`:

```bash
bytefray agents create my_agent
```

This writes `agents/my_agent/agent.yaml` and `agents/my_agent/agent.py`
under the configured writable data root (`battle2 agents create` works
identically). The command refuses to touch an existing directory or file at
that path — there is no `--force` — and prints the paths it wrote plus a
suggested next command:

```text
agent: my_agent
manifest: <data_root>/agents/my_agent/agent.yaml
source: <data_root>/agents/my_agent/agent.py
Run 'bytefray run --a-type my_agent --b-type <opponent>' to try it.
```

Edit the generated `agent.py`'s `act` method to replace the placeholder
strategy, then validate before running a real match:

```bash
bytefray agents validate my_agent
```

## Validate before running

`bytefray agents validate <agent-id>` (`battle2 agents validate` works
identically) discovers, loads, resets, and dry-runs one Python agent for a
single deterministic tick, without running a full match:

```text
agent: my_agent
status: valid
api_version: 1
dry_run_action: WRITE operand=232 value=165
```

This proves the agent's Agent API v1 contract is satisfied for one
deterministic dry-run tick — discoverable, loadable, reset successfully,
and returning one action the current runtime accepts. It does **not**
prove the agent will win, survive, or avoid failing on a later tick, and
it proves nothing about strategy quality, later-tick correctness, or
security sandboxing — see [Agent Lab](AGENT_LAB.md) for what the `agents
validate`/`test` timeout does and does not cover.

On failure, `bytefray agents validate` reports a stable machine-readable
`stage`/`code`, a human-readable `error` message, and exits `2` without a
raw traceback:

```text
agent: my_agent
status: invalid
stage: load
code: agent_import_failed
error: Failed importing Python agent source ...: SyntaxError: ...
```

Validation is currently supported for Python (`kind: python`) agents
only; a built-in, blob, Redcode, or unknown agent ID reports a clear
unsupported/unknown result rather than a misleading pass. See
[AGENT_API_V1.md](AGENT_API_V1.md) for the full Agent API v1 contract
this checks. By default, `bytefray agents validate` runs its `reset()`/
`act()` calls through a supervised worker process with a 5-second
per-call timeout (`--timeout`, see [Agent Lab](AGENT_LAB.md)) so a
genuinely non-returning callback is reported and recovered rather than
hanging the command forever. This is development-time hang
**containment**, not a security sandbox: worker code runs with the same
OS privileges as the CLI itself.

Create a second scaffolded agent (or point at an existing one), validate
it too, and run them against each other:

```bash
bytefray run --a-type my_agent --b-type other_python_agent --ticks 100
```

The recommended author workflow is **create → validate → test → replay →
modify → repeat**:

```bash
bytefray agents create my_agent
bytefray agents validate my_agent
bytefray agents test my_agent
bytefray replay <reported-replay-path>
```

See [AGENT_API_V1.md](AGENT_API_V1.md) for the full loading, lifecycle, and
action contract the generated files satisfy.

## Learning from the bundled agents

`bytefray agents create`'s scaffold is deliberately minimal -- it proves
the Agent API v1 contract, not a strategy. For actual decision-logic
ideas, read the five bundled Python starter agents' source
(`agents/claimer`, `agents/strider`, `agents/hunter`, `agents/wanderer`,
`agents/adaptive` under the writable data root once initialized): each
module docstring explains its strategy, the state it tracks, what's
reasonable to change, and -- for several of them -- what an earlier
version tried and why it lost in evaluation. They demonstrate patterns
worth reusing directly: tracking a pending `READ`'s address so a later
call can act on `Observation.last_read` correctly (every agent beyond
Claimer needs this), a signature byte to recognize your own already-claimed
cells (`Observation` carries no ownership map), and Adaptive's use of the
engine's `pc`/`JUMP` as an explicit phase state machine. There is no
separate "start from example" scaffold option -- copy one of these
directories into a new agent id under `agents/` and edit `agent.py`
directly; the file is the whole starting point. See the main
[README](../README.md#-try-the-bundled-agents) for compelling matchups to
try first and an `agents evaluate` example.

## Development-test your agent

`bytefray agents validate` and `bytefray agents test` answer genuinely
different questions:

| | `agents validate` | `agents test` |
|---|---|---|
| Question | Can the agent satisfy one Agent API lifecycle call? | Can the agent execute through real match semantics for a short development run, and what happened? |
| Execution | One `reset()`, one `act()`, no VM, no arena, no opponent. | A real match, up to 200 ticks, against a real opponent. |
| Artifacts | None -- a dry run produces no replay/result. | Canonical `replay.jsonl`/`result.json`/`summary.json`, identical in shape to `bytefray run`'s. |
| A forfeit/exception in the checked callback | The one validation failure reported -- validation itself failed. | One entrant's outcome within an otherwise successfully executed match -- the *test* still succeeded. |

`bytefray agents test <agent-id>` (`battle2 agents test` works
identically) runs the agent under test against either an internal
reference Python opponent or, with `--opponent <agent-id>`, another
discovered Python agent, through the exact production match machinery
(`NativeMatchService`) that `bytefray run` uses -- there is no separate
test-only simulation loop, result format, or replay format. `--seed`
(default: the project's own default seed, `1337`) and `--ticks` (default:
`200`, a short development-loop budget distinct from `bytefray run`'s
default of `3000`) override the match's seed and tick budget:

```text
agent: my_agent
opponent: reference
seed: 1337
ticks: 117/200
winner: my_agent
termination: last_agent_standing
result: <data_root>/runs/agents_test/my_agent/<run-label>/result.json
replay: <data_root>/runs/agents_test/my_agent/<run-label>/replay.jsonl
summary: <data_root>/runs/agents_test/my_agent/<run-label>/summary.json
trace: <data_root>/runs/agents_test/my_agent/<run-label>/trace.jsonl

Run 'bytefray replay <replay-path>' to inspect it.
Run 'bytefray agents inspect <run-dir>' to inspect decisions.
```

Like `validate`, `agents test` runs supervised by default (`--timeout`,
default 5 seconds) and writes a `trace.jsonl` development-trace artifact
alongside the usual `replay.jsonl`/`result.json`/`summary.json` unless
`--no-trace` is passed. See [Agent Lab](AGENT_LAB.md) for what that trace
records and how to read it with `bytefray agents inspect`/`diverge`.

**Bytefray exits `0` whenever it successfully evaluated user-agent
behavior, even when that behavior prevented a match from starting.**
A test-agent forfeit, death, or loss within a completed match is one
case. If the agent under test itself fails to load, import, or `reset()`
before tick zero, that is exit `0` too (the evaluation succeeded; it just
found nothing to run), with no replay/result/summary produced, since the
canonical match never began:

```text
agent: my_agent
status: initialization_failed
stage: reset
code: agent_reset_failed
error: Python agent my_agent reset failed: RuntimeError: boom
detail: RuntimeError
result: none
replay: none
```

The identical rule applies to an **explicitly selected `--opponent`**: it
is user-provided agent code being evaluated by this development test just
like the tested agent itself, so its own pre-tick-zero initialization
failure is also exit `0`, identified by the opponent's own discovery id:

```text
agent: my_agent
opponent: other_python_agent
status: initialization_failed
stage: reset
code: agent_reset_failed
error: Python agent other_python_agent reset failed: RuntimeError: boom
detail: RuntimeError
result: none
replay: none
```

Only a problem that is *not* a fact about evaluated user code returns
exit `2`: an unknown agent/opponent, a non-Python agent/opponent, or the
**internal bundled `reference` opponent** (used when `--opponent` is
omitted) failing to initialize. The reference opponent is Bytefray-owned
infrastructure, not user code, so its own failure means the tool or its
bundled fixture is broken -- not a result about your agent.

`bytefray agents test` never opens the replay viewer automatically; run
the printed `bytefray replay <path>` command as a separate, explicit next
step. If you want to compare more than one opponent, or run more than a
short development match, use `bytefray tournament` or `bytefray run`
directly -- see [TOURNAMENTS.md](TOURNAMENTS.md).

## Debugging with Agent Lab: trace, inspect, diverge

`agents validate`/`agents test` cover the first half of the authoring loop
(**create → validate → test**). Agent Lab covers the second half —
**inspect → debug → modify → repeat** — by recording exactly what your
agent saw and decided at each `reset()`/`act()` call, and by containing a
callback that never returns instead of hanging the tool forever. See
[docs/AGENT_LAB.md](AGENT_LAB.md) for the full mental model, troubleshooting,
and more examples; this section is the quick-start version.

**Trace is not replay.** `replay.jsonl` is the canonical match record —
what actually happened in the arena, tick by tick, and is what
`bytefray replay` renders. `trace.jsonl` is a separate, optional
development artifact — what your agent was *shown* (`Observation`) and
what it *decided* (`AgentAction` or a failure diagnostic) at each call
that produced that replay. Use replay to see the match; use trace to see
your agent's reasoning.

**`bytefray agents inspect <run-dir>`** answers "what happened in this
run?" without re-running any agent code — it only parses the already-written
`trace.jsonl`:

```bash
# Summary: record counts, tick range, per-agent failures
bytefray agents inspect runs/agents_test/my_agent/<run-label>

# Everything my_agent decided on tick 37
bytefray agents inspect runs/agents_test/my_agent/<run-label> --tick 37 --agent A

# Just the failures (forfeits, timeouts, exceptions)
bytefray agents inspect runs/agents_test/my_agent/<run-label> --failures
```

**`bytefray agents diverge <run-a> <run-b>`** answers "where did two runs
first disagree?" — useful after changing agent code, to confirm a fix
changed behavior starting at the tick you expect and not earlier:

```bash
bytefray agents diverge runs/agents_test/my_agent/2024-.../ runs/agents_test/my_agent/2024-.../
```

It reports `status: identical` (with no divergence) or the first
`(tick, agent)` where the two traces' actions/diagnostics differ — timing
fields (`wall_time_ms`) and header metadata are never compared, so two
runs that made the identical decisions are never reported as diverged
just because one happened to run faster.

**`--timeout SECONDS`** (both commands, default `5.0`, range `0.1`–`300.0`)
bounds every `load`/`reset()`/`act()` call. When a call exceeds it, that
call is reported with a diagnostic (`agent_load_timeout`/
`agent_reset_timeout`/`agent_action_timeout`) and the affected entrant
forfeits (or, for a load/reset timeout before tick zero, the match never
starts) — the tool always gets its console back. **This is
development-time hang containment, not sandboxing**: a supervised agent
runs with the same OS privileges as the CLI itself and can still read/write
files, open network connections, or consume unbounded CPU up to the
timeout. It only guarantees that Bytefray's own tooling stops *waiting*
and tells you which phase stalled. Pass `--no-trace` to skip writing
`trace.jsonl` for one run (it is cheap enough to leave on by default).

## Using the Agent Designer (GUI)

The same create → validate → test → replay loop is also available from the
PySide6 Agent Designer's **Agent Development** tab (`battle-agent-designer`
or `bytefray design`), without touching a terminal:

1. **New Agent…** prompts for an agent id and calls the identical scaffold
   used by `bytefray agents create` (an id that would be rejected by the
   CLI is rejected here too, with the same rule shown inline). The new
   agent is selected automatically once created.
2. **Validate** runs `bytefray agents validate <agent-id>` out-of-process
   and shows "Last validation: Valid" with the API version and dry-run
   action, or "Invalid" with the failing stage/code/error -- the same
   outcome the CLI reports, not a re-implementation of it.
3. **Development Test** runs `bytefray agents test <agent-id>` with the
   panel's Opponent (default `Reference`), Seed (default `1337`), Ticks
   (default `200`), and **Timeout (s)** (default `5.0`) options, mirroring
   `--opponent`/`--seed`/`--ticks`/`--timeout` exactly (see "Debugging with
   Agent Lab" above for what the timeout does). The result area shows
   "Last development test: Complete" with winner/termination/ticks and any
   forfeits, "Initialization failed" for a pre-tick-zero failure of the
   tested agent or an explicit opponent (no replay exists in that case), or
   "Could not be completed" for a tool/infrastructure failure -- kept
   visually distinct so a bad agent and a broken tool are never confused.
4. **Open Replay** (inside the Development Test result) launches the
   existing external Pygame replay viewer for a completed test's replay.
   It is independent of the Simple/Advanced tabs' own "Open Last Replay"
   button -- running a development test never changes what that other
   button opens.
5. **Inspect Trace** (next to Open Replay) opens the read-only Trace
   Inspector dialog over that test's `trace.jsonl` -- tick/agent selectors
   and Prev/Next step through recorded decisions, with a "Failures only"
   filter. It is enabled whenever the last completed test wrote a trace
   (always, unless a run used `--no-trace`). Unlike Validate/Test, opening
   it runs no agent code and cannot hang: it only reads an already-written
   file, directly on the GUI thread.
6. **Open Agent Folder** opens the agent's directory in the OS file
   browser so `agent.py` can be edited in an external editor; return to
   the Designer and click Validate/Test again to see the effect.

Only one Designer-owned process (a match, a tournament, a validation, or a
development test) ever runs at a time: while any of them is active, every
other Run/Validate/Test control is disabled. Validate/Test are supervised
by default (the same development-time hang containment described above,
not a security sandbox) so a hung callback is caught and reported on its
own; the Simple/Advanced tab's existing Stop button remains available as a
manual fallback (or closing the Designer window), acting on whichever
operation is currently running -- never a graceful mid-call interruption,
just an unconditional process kill.

## Underlying file format (manual reference)

The scaffold command has no template selection — this section documents the
same minimal shape by hand, useful when you want to understand or hand-edit
the underlying manifest/source format rather than start from the generated
files. It intentionally matches what `bytefray agents create` generates.

`agents/example/agent.yaml`:

```yaml
kind: python
api_version: 1
entrypoint: agent.py:create_agent
version: "0.1.0"
```

`name`/`display` are recognized but deliberately omitted here: agent
identity is always the directory basename, never a manifest field, so
adding a `name` that merely duplicates the directory risks silently
drifting from it if the directory is later renamed.

`agents/example/agent.py`:

```python
from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation


class ExampleAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng

    def act(self, observation: Observation) -> AgentAction:
        # One callback returns exactly one charged battlefield operation.
        address = self.rng.randrange(256)
        return AgentAction(ActionKind.WRITE, address, 0xA5)


def create_agent() -> ExampleAgent:
    return ExampleAgent()
```

Both selected agents must resolve to `kind: python`. Selecting a Python agent
against a built-in or blob produces a clear unsupported-composition error.

## Runtime model

The factory is called once per load and must return an object with callable
`reset(context)` and `act(observation)` methods. The engine creates a fresh
instance and independent deterministic RNG for each entrant, calls `reset`
exactly once, then permits up to `--quota` actions per tick.

Each load also executes a fresh private module. Module globals persist within
one entrant's match, but they are not reused by a later match or another entrant,
even when the same source file is selected again.

Entrants execute sequentially in slot order. A completes its quota before B,
so A's writes are visible to B later in that tick. Internal Python computation
is not charged or sandboxed; fairness is defined as equal charged battlefield
operations.

Observations contain only the entrant's tick, identity, controller PC, A/P/Z
state, last read byte, and alive state. They contain no arena, ownership map,
score, opponent state, or engine objects.

Available action kinds are:

```text
NOP, SET_A, ADD_A, READ, WRITE,
SET_P, ADD_P, JUMP, JUMP_IF_ZERO, HALT
```

See [AGENT_API_V1.md](AGENT_API_V1.md) for exact operands, wrapping, read/write
semantics, deterministic seed derivation, and typed failures.

## Failure behavior

Import, factory, contract, and reset failures reject the match before tick zero
and leave no replay or summary that can be mistaken for success. An act
exception, malformed action, unsupported action, or invalid operand forfeits
that entrant; a normal `HALT` simply ends it. The match continues while another
entrant remains. Forfeits produce stable structured replay events without raw
exception text or tracebacks and do not create opponent kills.

## Not yet implemented

- mixed Python/VM or Python/blob matches;
- corruptible Python executable cores or arena-based Python mortality;
- Python replication or redundant-core architectures;
- human-controlled entrants; and
- mixed-runtime or GUI-managed tournament execution.

`bytefray agents validate`/`test` (and the Designer's Validate/Test) are
supervised with a timeout by default (see "Debugging with Agent Lab"
above) — a non-returning `act()`/`reset()` there is reported and
recovered rather than hanging the tool. **`bytefray run` and
`bytefray tournament` remain unsupervised and untimed**, exactly as
before Agent Lab: a non-returning `act()` in an ordinary match or
tournament run still cannot be interrupted safely short of killing the
process. In every case — supervised or not — Python code can perform
arbitrary in-process computation and runs with the same OS privileges as
Bytefray itself; this is development-time hang containment, never a
security boundary. Run only agents you trust.

## Other formats

The native built-ins are `runner`, `writer`, `bomber`, `flooder`, `spiral`, and
`seeker`; their exact VM behavior is documented in [RULES.md](RULES.md). A blob
agent supplies `model.blob`. Redcode uses `battle2 run --mode redcode94` and does
not participate in Agent API scheduling.
