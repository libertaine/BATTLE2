# Current Native VM Rules Reference

This document describes the native BATTLE VM as currently implemented. It is not a description of Redcode/pMARS, and it does not define future Python-agent gameplay.

## Arena

The native arena is a circular, mutable byte array. Its size is `Config.arena_size` (default `4096`). Every memory address is reduced modulo the arena size, including instruction fetches, 32-bit immediate reads, direct accesses, indirect accesses, code loading, and entry addresses.

The arena starts filled with byte `0`, which is the `NOP` opcode. Agent code is copied into the arena at spawn time and remains mutable. Later-spawned code can overwrite earlier code if regions overlap. An agent continues from its recorded PC even if another agent has replaced those bytes.

The VM maintains a parallel ownership value for every byte:

- loading code assigns its bytes to that agent;
- `STORE` and `STOREI` assign the written byte to the writer;
- later writes replace earlier ownership; and
- reads do not change ownership.

Ownership means “most recent loader/writer,” not protected territory. It is used for territory scoring, statistics, replay diffs, and approximate kill attribution. VM programs cannot read the ownership array directly.

## Instruction encoding and cost

Every opcode costs one scheduler instruction, regardless of encoded size or effect. Opcodes without an immediate occupy one byte. Immediate instructions occupy one opcode byte followed by a four-byte unsigned little-endian value. Immediate reads wrap around the arena.

Registers A and P use 32-bit wrapping arithmetic. Memory writes keep only the low eight bits.

| Opcode | Value | Effect and PC behavior |
|---|---:|---|
| `NOP` | 0 | No state change except `PC = PC + 1`. |
| `MOV imm` | 1 | Set A to the 32-bit immediate; advance PC by 5. |
| `ADD imm` | 2 | Set A to `(A + imm) mod 2^32`, then set Z to 1 when A is zero and 0 otherwise; advance PC by 5. |
| `LOAD addr` | 3 | Read one arena byte at `addr mod arena_size` into A, update Z from that byte, and advance PC by 5. |
| `STORE addr` | 4 | Write A's low byte to `addr mod arena_size`, assign ownership to the agent, increment its write counter, and advance PC by 5. |
| `JMP addr` | 5 | Set PC to `addr mod arena_size`. |
| `JZ addr` | 6 | If Z is 1, jump to `addr mod arena_size`; otherwise advance PC by 5. |
| `HALT` | 7 | Mark the agent dead. PC does not advance. |
| `MOVP imm` | 8 | Set P to the 32-bit immediate; advance PC by 5. |
| `ADDP imm` | 9 | Set P to `(P + imm) mod 2^32`; advance PC by 5. Arena reduction occurs only when P is used as an address. |
| `LOADI` | 10 | Read one byte at `P mod arena_size` into A, update Z, and advance PC by 1. |
| `STOREI` | 11 | Write A's low byte at `P mod arena_size`, assign ownership, increment writes, and advance PC by 1. |

Any fetched byte other than `0` through `11` is an invalid opcode. The VM marks the agent dead and leaves PC on that byte.

## Agent state and accounting

Each VM agent has:

- `agent_id`: slot identity such as A or B;
- `pc`: current program counter;
- `alive`: whether it may be scheduled;
- registers `A`, `P`, and `Z`, initially zero;
- `cpu_used`: instructions attempted in the current tick;
- `mem_writes`: cumulative successful `STORE`/`STOREI` operations; and
- `region`: inclusive start/end addresses of its initially loaded bytes.

The region is descriptive and may wrap. It does not protect code and is not consulted when reading or writing memory.

The scheduler increments `cpu_used` after every `VM.step()` call, including a step that executes `HALT` or dies on an invalid opcode. Statistics accumulate that value after all agents have run for the tick.

## Scheduling

Scheduling is sequential and ordered by spawn order. The CLI currently spawns A, then B, then optional C. For every tick:

1. Clear the tick's replay memory diffs.
2. Give A up to `instr_per_tick` VM steps.
3. Give B up to the same quota.
4. Give C up to the same quota, if present.
5. Record statistics.
6. Award survival and territory score.
7. Attribute deaths and award kill score.
8. Publish the tick replay record.
9. Stop if no more than one agent is alive.

An agent stops its quota immediately upon death. Dead agents are skipped in later ticks.

Execution is not simultaneous. A can alter B's next instruction before B receives any execution in that tick. Spawn order is therefore a competitive advantage and swapping sides can change a result.

The default instruction quota is 8. CLI `--quota` changes `Config.instr_per_tick` and must be positive.

## Scoring

Default weights are:

| Component | Default |
|---|---:|
| Alive per completed tick | `1.0` |
| Attributed kill | `5.0` |
| Territory per bucket | `1.0` |
| Cells per territory bucket | `64` |

After execution in each tick:

- Every still-alive agent receives `alive` points.
- Every agent, alive or dead, receives `floor(owned_cells / territory_bucket) * territory` points when the territory weight is positive.
- An attributed killer receives `kill` points.

Territory is cumulative scoring: the current whole-bucket award is added every tick. Initial code bytes count as owned cells. Larger programs therefore begin with more ownership, although only complete buckets score.

Statistics separately retain alive ticks, cumulative CPU, cumulative writes, kills, deaths, and last/maximum/average owned cells.

### Winner resolution

If exactly one agent remains alive, that agent wins regardless of score.

If multiple or zero agents remain at the tick limit:

- `survival` produces no kernel winner and is exposed by the current native service/CLI as a tie.
- `score` and `score_fallback` select the unique highest score.
- Equal highest scores produce a tie.

Agent IDs break sorting order for deterministic ranking but do not break an equal score into a win.

## Death and match termination

An agent dies by:

- executing `HALT`; or
- fetching an invalid opcode.

When a newly dead agent is examined, the engine looks at ownership of the byte at its final PC. If another agent owns that byte, that owner receives kill credit. Self-owned and unowned death locations produce an unattributed death. This is last-writer attribution, not a causal history of the write that led to death.

A match stops after a completed tick when zero or one agents remain, or after the requested tick limit. There is no draw check during an agent's partial turn.

## Determinism

The native VM is deterministic for the same configuration, bytecode, entry addresses, spawn order, and tick limit. Replay emission follows deterministic scheduling and state iteration.

`Config.seed` defaults to `1337`, is recorded in configuration/replay data, and initializes `Kernel.rng`. The current VM, scheduler, and built-in assemblers do not consume that RNG. Changing only the seed therefore does not currently change a native VM match.

This does not define future Python-agent RNG behavior. Wall-clock GUI rendering and pMARS are outside this native determinism statement.

## Current built-ins

| Name | Current implementation behavior |
|---|---|
| `runner` | Cycles through `ADD`, `JZ`, and `JMP` after one initial `NOP`. It writes no memory and does not physically relocate its code. |
| `writer` | Repeatedly writes a fixed byte to one fixed direct address; one write per three-instruction loop. |
| `bomber` | Initializes P, then repeatedly writes indirectly and advances it by a fixed stride; one write per three-instruction loop after setup. |
| `flooder` | Unrolls repeated `STOREI`/`ADDP 1` pairs before jumping back. With the default eight writes per loop, it performs about four writes per eight scheduler instructions after setup, not eight. |
| `spiral` | Performs two writes to the same P address per loop and advances P by a fixed encoded step. The `delta` arithmetic changes A transiently but does not modify the immediate operand of `ADDP`, so the stride does not grow. |
| `seeker` | Scans from P for a target byte. Nonmatches advance P by one; matches write the attack byte at P, advance by the attack stride, and resume scanning. |

These descriptions document current bytecode. They characterize the reference
competitors rather than promising that future rulesets will preserve every
strategy detail.

Starter manifests currently initialize Runner, Writer, Seeker, and Spiral in a writable data root. A starter manifest selects its same-named built-in implementation; it does not contain executable Python code.

## Redcode/pMARS

`battle2 run --mode redcode94` invokes a separate pMARS process. Its core size, cycles, processes, warrior length, minimum distance, rounds, failure handling, and result parsing are pMARS-backend concerns.

Redcode does not execute BATTLE VM opcodes, use BATTLE registers, participate in native scheduling, or currently produce a native BATTLE replay. It produces a normalized summary on success.

## Python runtime rules are not yet defined

Python agent discovery, path-based import, factory construction, fresh instances, structural validation, and typed diagnostics exist. Python agents do not yet participate in native matches.

No rules currently define Python observations, actions, arena or ownership visibility, action budgets, VM-equivalent costs, mortality, exception forfeits, timeouts, or Python-versus-VM scheduling. See [AGENT_API_V1.md](AGENT_API_V1.md) for the implemented loading contract without speculative gameplay semantics.
