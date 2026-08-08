# Bytefray Agent Authoring Guide

Bytefray supports built-in and blob entrants in the native VM, Python agents in
experimental Python-versus-Python matches, and Redcode warriors through the
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
prove the agent will win, survive, or avoid failing on a later tick; it
proves nothing about strategy quality, timeout safety, or sandboxing (no
runtime timeout/process containment exists yet — see "Not yet
implemented" below).

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
this checks. Validation is not sandboxed and has no timeout: `reset`/
`act` run the same unrestricted in-process Python a real match runs.

Create a second scaffolded agent (or point at an existing one), validate
it too, and run them against each other:

```bash
bytefray run --a-type my_agent --b-type other_python_agent --ticks 100
```

The recommended author workflow is **create → validate → run**. See
[AGENT_API_V1.md](AGENT_API_V1.md) for the full loading, lifecycle, and
action contract the generated files satisfy.

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
- hard timeout/process containment for callbacks;
- Python replication or redundant-core architectures;
- human-controlled entrants; and
- mixed-runtime or GUI-managed tournament execution.

Python code can perform arbitrary in-process computation and a non-returning
`act()` cannot yet be interrupted safely. Run only agents you trust.

## Other formats

The native built-ins are `runner`, `writer`, `bomber`, `flooder`, `spiral`, and
`seeker`; their exact VM behavior is documented in [RULES.md](RULES.md). A blob
agent supplies `model.blob`. Redcode uses `battle2 run --mode redcode94` and does
not participate in Agent API scheduling.
