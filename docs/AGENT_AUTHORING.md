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

## Minimal executable Python agent

`agents/example/agent.yaml`:

```yaml
kind: python
api_version: 1
entrypoint: agent.py:create_agent
name: example
display: Example Agent
version: 0.1.0
```

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

Create a second Python agent directory, then run:

```bash
battle2 run --a-type example --b-type other_python_agent --ticks 100
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
