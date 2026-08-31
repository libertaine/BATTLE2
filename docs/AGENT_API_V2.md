# Bytefray Agent API v2

Agent API v2 is the Python programming contract for
`bytefray-rules-4-alpha1`. It is an alpha contract and is intentionally
separate from [Agent API v1](AGENT_API_V1.md), which remains the contract for
Ruleset v1/v2 Python entrants. A manifest selects v2 explicitly:

```yaml
kind: python
api_version: 2
entrypoint: agent.py:create_agent
version: 1.0.0
```

The factory must return a fresh object implementing:

```python
def reset(context: MatchContextV2) -> None: ...
def declare_processes() -> list[ProcessDeclaration]: ...
def act(observation: ObservationV2) -> AgentAction: ...
```

The production loader validates all three methods. `reset()` runs once, then
`declare_processes()` runs and is fully validated before tick 0. Invalid
declarations fail the match without publishing a replay or result.

## Process declaration

`ProcessDeclaration(id, reach, share)` defines the entrant's fixed roster.

- At least one process is required.
- `id` must be a non-empty unique string within the entrant.
- `reach` must be an integer from 1 through `arena_size - 1`.
- `share` must be finite and non-negative; all shares must total 1 (absolute
  tolerance `1e-12`) and at least one share must be positive.
- Declarations do not contain a starting address. Every declared process starts
  co-located at the entrant/core start; remote deployment is earned with
  `MOVE`.
- The roster is fixed for the match. API v2 has no spawn, retirement, or
  destruction operation.

Ruleset v4 alpha1 fixes the entrant action budget at `Q=8`. Shares are
converted to integer per-tick allocations by deterministic largest remainder;
stable process ID breaks equal-remainder ties. When disruption makes a process
ineligible, its share is redistributed among eligible positive-share
processes, preserving the entrant total whenever any process is eligible.

## Match context

`MatchContextV2` contains `agent_id`, the engine-derived deterministic `seed`,
`arena_size`, `tick_limit`, and an entrant-local `random.Random` instance.
Agent code must use `context.rng` rather than global randomness when replayable
behavior matters.

## Observation

Each eligible process callback receives an immutable `ObservationV2`:

- temporal provenance: `current_tick`, `last_callback_tick`,
  `previous_action_tick`;
- acting-process state: `self_process_id`, `self_anchor`, `self_reach`;
- own vulnerable core: `own_core_base`, `own_core_size`;
- current local detection: sorted, unique
  `visible_enemy_anchor_addresses` seen within the reach of any eligible
  friendly process; and
- previous callback feedback: `previous_action_applied`,
  `previous_read_value`, `previous_read_owner`.

Detection is entrant-shared but current-only. The engine does not provide
enemy process IDs, roles, shares, reach, disruption status, a last-known
coordinate, attacker identity, or a disruption-hit confirmation. Agents may
remember earlier observations themselves. A recovering process can infer that
callbacks were missed from the temporal fields without a dedicated
`was_disrupted` flag.

## Actions and addressing

`act()` must return exactly one `AgentAction` whose kind is an `ActionKindV2`:

| Kind | Operand semantics | Result |
| --- | --- | --- |
| `READ` | Absolute arena address | Reads only when the normalized address is within circular `self_reach`; feedback otherwise reports not applied. |
| `WRITE` | Absolute arena address, plus integer `value` | Writes only within circular `self_reach`. A legal write reports ordinary application, never whether it disrupted a process. |
| `MOVE` | Signed relative delta from `self_anchor` | Moves only the acting process; the engine clamps displacement to `[-64, 64]` and wraps in the circular arena. |

This distinction is deliberate: `READ` and `WRITE` are absolute, while
`MOVE` is relative. Starter agents compute an absolute target before emitting
a memory action. Values for non-`WRITE` actions are invalid, as are v1-only
action kinds.

## Scheduling and disruption

Production v4 uses deterministic `K=2` chunked scheduling with the starting
seat rotating by tick against immutable original seat order. Multiple
processes never multiply an entrant's `Q=8` total.

A legal enemy `WRITE` to an exact live process anchor disrupts every enemy
process co-located there. A hit during tick `N` suppresses the affected
processes for the remainder of tick `N`; they are eligible again at tick
`N+1`. Friendly co-located processes are unaffected. There is no explicit
attack, recovery, or disruption action.

## Artifacts and compatibility

Ruleset-v4 production matches write `battle2.replay` schema 4 with process
state on tick and terminal records. Ruleset-v1/v2 matches continue using Agent
API v1 and replay schema 3. Historical identities and bytes are not upgraded
or reinterpreted as v4. See [COMPATIBILITY.md](COMPATIBILITY.md),
[REPLAY_SCHEMA.md](REPLAY_SCHEMA.md), and the
[v4 alpha design](V4_ALPHA1_DESIGN.md).
