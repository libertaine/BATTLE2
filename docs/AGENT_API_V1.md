# Agent API v1 Technical Contract

This document describes the implemented Bytefray Python Agent API v1. The current
runtime supports deterministic Python-versus-Python matches through the native
match service. VM/Python mixed matches remain unsupported.

## Loading contract

A Python agent manifest declares `kind: python`, `api_version: 1`, and an entry
point in `relative/path.py:factory` form. `load_python_agent()` contains the
source path within the agent directory, imports it under a path-derived private
module name, calls the zero-argument factory, and requires callable `reset` and
`act` methods. Every load constructs a fresh module and agent instance.

The loader deliberately executes a fresh module for every entrant load, including
repeated matches and two entrants that use the same source. Module globals are
therefore fresh at match construction rather than shared through Python's import
cache. Globals still persist for that entrant for the duration of its match.

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

### Frozen entrant-seed derivation (Agent API v1 invariant)

The exact derivation algorithm below is part of the Agent API v1 contract,
not a separately versioned RNG axis — see
[COMPATIBILITY.md](COMPATIBILITY.md). It is specified here precisely enough
for an independent implementation to reproduce it byte-for-byte:

1. Build a material string from, in this exact field order, separated by
   NUL (`\0`) bytes:
   - the literal prefix `battle2-python-v1`;
   - the match seed (`Config.seed`), as its decimal string representation;
   - the entrant's slot/order index, as its decimal string representation;
   - the entrant's canonical agent ID string; and
   - the Agent API version in effect (`1`), as its decimal string
     representation.
2. Encode that material string as UTF-8.
3. Compute its SHA-256 digest.
4. Take the digest's first 16 bytes.
5. Interpret those 16 bytes as a big-endian unsigned integer. That integer
   is the entrant's derived seed, passed to `random.Random(seed)`.

Equivalently, in the exact form currently shipping
(`battle_engine.python_runtime.derive_agent_seed`):

```python
def derive_agent_seed(
    match_seed: int, slot: int, agent_id: str, api_version: int = AGENT_API_VERSION
) -> int:
    material = f"battle2-python-v1\0{match_seed}\0{slot}\0{agent_id}\0{api_version}"
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:16], "big")
```

This literal formula — prefix, field order, NUL separators, SHA-256,
first-16-bytes, big-endian interpretation — is frozen for Agent API v1.
Golden-vector regression tests
(`engine/tests/test_python_runtime.py::test_derive_agent_seed_golden_vectors`)
pin literal expected integers for fixed inputs so an accidental change to
this formula is caught immediately, not just a change in relative
behavior. **Any incompatible change to this derivation — a different
prefix, field order, separator, hash algorithm, byte selection, or integer
interpretation — requires bumping `AGENT_API_VERSION` to `2`**, exactly
like any other incompatible Agent API change; it does not get an
independent `RNG_VERSION`/`RNG_COMPATIBILITY_ID` of its own.

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

## Scheduling, failures, and termination

Python-only scheduling is sequential in request/spawn order. Each living
entrant receives up to `Config.instr_per_tick` callbacks, and A completes its
quota before B begins. Writes are therefore visible to later entrants in the
same tick, preserving the native scheduler's first-mover characteristic.

- Import, factory, contract, and reset failures reject initialization before
  tick zero and before a final replay is published.
- An act exception forfeits the entrant with `agent_action_failed`.
- An invalid or unsupported action forfeits it with `agent_action_invalid`.
- `HALT` is a normal unattributed death.

Runtime diagnostics carry a stable code and stage plus applicable entrant ID,
slot, exception type, tick, and zero-based action slot. Human-readable exception
text is whitespace-normalized and bounded; replay failure events use stable
fields rather than exception text or tracebacks. A forfeit is never attributed
as an opponent kill.

Completed internal match results distinguish `last_agent_standing`,
`all_agents_dead`, and `tick_limit`. Entrants separately distinguish a normal
`HALT` from a forfeit. These fields remain internal while the v0.2 summary and
replay compatibility formats are in use.

Python replays are written to a sibling temporary file and atomically published
after successful runtime completion. Preflight, engine, or replay-write failure
removes stale replay and summary outputs at the requested location. An action
forfeit is a completed match outcome, so its replay is published normally.

Internally, each entrant retains the effective match seed, independently derived
entrant seed, request slot, canonical agent ID, API and agent versions, source
SHA-256 digest, arena size, tick limit, and action budget. Absolute source paths
are not added to portable replay or summary data. Canonical exposure of this
metadata belongs with later result/replay normalization.

## Current limitations

- Python/VM and Python/blob mixed matches are rejected.
- Python entrants are not vulnerable to arena code corruption.
- `bytefray run`/tournament still run every Python entrant in-process with
  no hard timeout, exactly as above -- a non-returning callback there is
  still only interruptible by an operator's Ctrl-C/`SystemExit`. Since the
  Agent Lab work (v0.5.0), `bytefray agents test`/`agents validate`
  optionally run each Python entrant's `load`/`reset`/`act` calls through
  one whole-match-lifetime worker subprocess instead, with a per-call
  timeout; see `docs/AGENT_LAB.md`. This is development-time hang
  containment, not a security sandbox, and is not (yet) available to
  `bytefray run`/tournament.
- Python replication and vulnerable-core designs are not implemented.
- Headless Python-only tournaments orchestrate Agent API v1 matches through the
  native service; mixed-runtime tournament divisions remain unsupported.
- Type hints and method signatures are not statically enforced at load time;
  incompatible calls become controlled reset or act failures.

## Stability boundary for 1.0

The loading/lifecycle contract, `Observation`/`AgentAction`, the
deterministic RNG derivation above, homogeneous Python-vs-Python
scheduling, and failure/forfeit semantics described in this document are a
**stable contract candidate for Bytefray 1.0** — see
[COMPATIBILITY.md](COMPATIBILITY.md) and `docs/ROADMAP.md`. This
supersedes any earlier blanket description of the whole Python runtime as
"experimental"; what remains explicitly unsupported/experimental for 1.0
is narrower and listed there: mixed VM/Python matches, security
sandboxing (the worker-subprocess timeout containment above is
development-time hang containment, not a sandbox), hard callback
containment on every `bytefray run`/tournament execution path,
replication, and corruptible Python-core designs.
