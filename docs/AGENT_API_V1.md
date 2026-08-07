# Agent API v1 Technical Contract

This document describes the implemented BATTLE2 Python Agent API v1. Phase 3a
supports deterministic Python-versus-Python matches through the native match
service. VM/Python mixed matches remain unsupported.

## Loading contract

A Python agent manifest declares `kind: python`, `api_version: 1`, and an entry
point in `relative/path.py:factory` form. `load_python_agent()` contains the
source path within the agent directory, imports it under a path-derived private
module name, calls the zero-argument factory, and requires callable `reset` and
`act` methods. Every load constructs a fresh module and agent instance.

Loading failures use the existing typed `AgentValidationError` hierarchy:

| Exception | Code |
|---|---|
| `AgentManifestError` | `agent_manifest_invalid` |
| `UnsupportedAgentAPIVersionError` | `agent_api_version_unsupported` |
| `AgentSourceError` | `agent_source_invalid` |
| `AgentImportError` | `agent_import_failed` |
| `AgentFactoryError` | `agent_factory_failed` |
| `AgentContractError` | `agent_contract_invalid` |

## Lifecycle

```python
class AgentV1(Protocol):
    def reset(self, context: MatchContext) -> None: ...
    def act(self, observation: Observation) -> AgentAction: ...
```

The engine constructs a fresh instance for each match and calls `reset()` once
before tick zero. Each subsequent `act()` call returns exactly one action and
costs one unit of the entrant's per-tick action budget.

`MatchContext` is frozen and contains:

- `agent_id`: match slot identity such as `A` or `B`;
- `seed`: the stable, derived seed for this entrant;
- `arena_size`: shared circular arena size;
- `tick_limit`: requested maximum ticks;
- `action_budget`: actions allowed per tick; and
- `rng`: the entrant's engine-created `random.Random` instance.

The RNG is independent per entrant. Its seed is derived with SHA-256 from the
match seed, slot/order, canonical slot ID, and Agent API version. Python's
randomized `hash()` is not used, and one entrant consuming random values cannot
advance another entrant's stream.

## Observation

`Observation` is frozen and contains only:

```python
tick: int
agent_id: str
pc: int
register_a: int
register_p: int
zero_flag: bool
last_read: int | None
alive: bool
```

The observation exposes the entrant's own engine-controlled state. It does not
expose the arena, ownership, score, opponent state, kernel, VM, or other engine
objects. `pc` is Python controller state: it changes only through `JUMP` and a
taken `JUMP_IF_ZERO`; Python source is not fetched from that address.

## Action vocabulary

An action is `AgentAction(kind, operand=None, value=None)`, where `kind` is an
`ActionKind` enum member:

| Kind | Operands | Semantics |
|---|---|---|
| `NOP` | none | No battlefield state change. |
| `SET_A` | `operand` | Set A, wrapping to unsigned 32-bit. Z is unchanged, like VM `MOV`. |
| `ADD_A` | `operand` | Add to A with 32-bit wrapping and update Z. |
| `READ` | address in `operand` | Read one wrapped arena byte into `last_read` and A; update Z. |
| `WRITE` | address in `operand`, byte in `value` | Write the low eight bits at the wrapped address and claim ownership. |
| `SET_P` | `operand` | Set P with unsigned 32-bit wrapping. |
| `ADD_P` | `operand` | Add to P with unsigned 32-bit wrapping. |
| `JUMP` | `operand` | Set controller PC with unsigned 32-bit wrapping. |
| `JUMP_IF_ZERO` | `operand` | Set controller PC only when Z is true. |
| `HALT` | none | Normal entrant death. |

Operands must be integers; booleans are rejected as operands. Extra, missing,
unsupported, batched, or non-`AgentAction` results are invalid. Agents may do
unrestricted in-process computation while choosing an action, but only this
validated one-operation interface can read or mutate battlefield state.

## Scheduling and failures

Python-only scheduling is sequential in request/spawn order. Each living
entrant receives up to `Config.instr_per_tick` callbacks, and A completes its
quota before B begins. Writes are therefore visible to later entrants in the
same tick, preserving the native scheduler's first-mover characteristic.

- A reset exception rejects initialization before replay creation.
- An act exception forfeits the entrant with `python_act_failed`.
- An invalid action forfeits the entrant with `python_action_invalid`.
- `HALT` is a normal unattributed death.

Runtime forfeits are available as structured internal result diagnostics and
replay events. Normal CLI failures do not expose tracebacks.

## Current limitations

- Python/VM and Python/blob mixed matches are rejected.
- Python entrants are not vulnerable to arena code corruption.
- No hard timeout or process isolation can interrupt a non-returning callback.
- Python replication and vulnerable-core designs are not implemented.
- Tournament execution is not part of Agent API v1 Phase 3a.
- Type hints and method signatures are not statically enforced at load time;
  incompatible calls become controlled reset or act failures.
