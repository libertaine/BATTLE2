# Bytefray Ruleset v1 Reference

This document defines **Ruleset v1** (`bytefray-rules-1`), the frozen
gameplay-semantics contract Bytefray intends to carry through the 1.x
series. It describes the native BATTLE VM and the homogeneous Python-vs-
Python runtime as currently implemented, but organizes that description
around one question: *what exactly does `bytefray-rules-1` mean, and what
kind of change would require a new Ruleset identity?*

It is not a description of Redcode/pMARS (see "Implementation details"
below), and it does not define Ruleset v2 or any later ruleset — see
[RULES_V2.md](RULES_V2.md) for the beta `bytefray-rules-2` contract
introduced in `v2.0.0-beta1`, and
[FUTURE_PLANS.md](FUTURE_PLANS.md)'s "Future simulation / combat research"
section for gameplay ideas that would require a still-later ruleset.

## The Ruleset identity

```python
BYTEFRAY_RULESET_ID = "bytefray-rules-1"
```

defined in `battle_engine.rules`, importable by the match, runtime, and
evaluation layers without creating a dependency on any of them. It is the
single, first-class compatibility axis for Bytefray gameplay semantics.
See [COMPATIBILITY.md](COMPATIBILITY.md) for how it relates to the other
independent compatibility axes (Agent API version, artifact schema
versions, evaluation methodology fields, agent revision identity).

`bytefray.evaluation`'s `EVALUATION_RULES_COMPATIBILITY_ID` is a derived
alias of this identity — see "Historical relationship to
evaluation-rules-1" below.

### Five different things people mean by "the rules"

This document, and the codebase, distinguish five different concerns that
are easy to conflate under the single word "rules":

| Concern | What it covers | Where it's defined |
|---|---|---|
| **Ruleset semantics** | The game itself: scoring formulas, ownership, scheduling order, mortality, termination, winner resolution, observation/read/write meaning. | This document; identified by `BYTEFRAY_RULESET_ID`. |
| **Configuration values** | The specific numbers one match uses for Ruleset-defined fields (arena size, weights, tick limit, seed). | `battle_engine.config.Config`/`Weights`; not separately versioned — see "Configuration values are not Ruleset identity" below. |
| **Agent API semantics** | The Python agent programming contract: loading, lifecycle, `Observation`/`AgentAction`, and the deterministic RNG derivation. | [AGENT_API_V1.md](AGENT_API_V1.md); identified by `AGENT_API_VERSION`. |
| **Evaluation methodology** | How `agents evaluate` measures agents: entrant orientation coverage, arena-alignment disclosure, matrix construction. | `docs/specs/evaluation_history.md`, `docs/specs/agent_evaluation.md`; identified by `bytefray.evaluation`'s schema/identity versions and methodology fields, independent of gameplay. |
| **Implementation details** | Reference built-in program behavior, pMARS/Redcode interop — real, but not gameplay rules and not part of `bytefray-rules-1`. | This document's "Implementation details" section. |

The rest of this document covers Ruleset semantics (shared, then
VM-specific, then Python-specific), then configuration exclusions, then a
short pointer to the other four concerns, then the bump policy and
historical evidence.

---

## Shared Ruleset semantics

These rules apply identically to native VM matches and to the homogeneous
Python-vs-Python runtime, wherever both runtimes have the concept at all.

### Arena

The arena is a circular, mutable byte array. Its size is `Config.arena_size`
(default `4096`). Every memory address used by either runtime — instruction
fetches, immediate reads, direct or indirect accesses, code loading, entry
addresses, and Python `READ`/`WRITE` operands — is reduced modulo the arena
size. The arena starts filled with byte `0` (the VM's `NOP` opcode; for
Python entrants this value has no opcode meaning, since Python source is
never fetched from the arena — see "Python-specific Ruleset clauses"
below).

### Ownership

The engine maintains a parallel ownership value for every arena byte:

- a write (VM `STORE`/`STOREI`, Python `WRITE`) assigns that byte to the
  writer;
- a later write replaces earlier ownership; and
- reads never change ownership.

Ownership means "most recent writer," not protected territory — it is used
for territory scoring, statistics, replay diffs, and (VM-only) kill
attribution. Neither runtime's agent code can read the ownership array
directly; it is engine-internal state.

### Register and memory width

Registers `A` and `P` use 32-bit wrapping arithmetic in both runtimes (VM
`MOV`/`ADD`/`MOVP`/`ADDP`; Python `SET_A`/`ADD_A`/`SET_P`/`ADD_P`). Memory
writes keep only the low eight bits of the value being written, in both
runtimes.

### Scheduling order

Scheduling is sequential and ordered by spawn/request order — A before B
before optional C. For every tick, each living entrant receives up to
`Config.instr_per_tick` VM steps (or, for Python, `act()` callbacks) before
the next entrant begins; an entrant that dies mid-quota stops immediately
and is skipped in later ticks. Because execution is not simultaneous, an
earlier entrant can alter what a later entrant observes or is affected by
before the later entrant acts at all in that tick — spawn/request order is
therefore a competitive factor, and swapping which entrant occupies which
slot can change a result. This first-mover characteristic is why
`bytefray agents evaluate` runs both entrant orientations by default (see
`docs/specs/evaluation_history.md`) — an evaluation-methodology concern
layered on top of this Ruleset behavior, not a change to it.

### Instruction/action accounting

Every VM opcode step, and every Python `act()` callback, costs exactly one
unit of the entrant's per-tick budget (`Config.instr_per_tick`), regardless
of what the instruction/action did or how large its encoding was.

### Scoring

Default weights (`battle_engine.config.Weights`):

| Component | Default |
|---|---:|
| Alive per completed tick | `1.0` |
| Attributed kill | `5.0` |
| Territory per bucket | `1.0` |
| Cells per territory bucket | `64` |

After execution in each tick:

- **Survival scoring formula**: every still-alive entrant receives `alive`
  points.
- **Territory scoring formula**: every entrant, alive or dead, receives
  `floor(owned_cells / territory_bucket) * territory` points whenever the
  territory weight is positive. This is cumulative: the current whole-
  bucket award is added every tick, and initial/loaded ownership counts
  toward it.
- **Kill scoring formula**: an attributed killer receives `kill` points.
  (VM-only in practice — see "VM-specific Ruleset clauses"; Python deaths
  never produce kill attribution, so this formula's precondition is never
  met for a Python match.)

Statistics separately retain alive ticks, cumulative CPU/action counts,
cumulative writes, kills, deaths, and last/maximum/average owned cells, in
both runtimes.

### Winner resolution

One authoritative implementation (`battle_engine.results.resolve_winner`)
is shared by both runtimes:

- if exactly one entrant remains alive, that entrant wins regardless of
  score;
- otherwise, under `win_mode: "survival"`, there is no winner (a tie);
- otherwise (`"score"`/`"score_fallback"`), the unique highest score wins;
  an exact tie in top score produces no winner.

Entrant IDs break sorting order for deterministic ranking/reporting but
never break an equal score into a win.

### Mortality and match termination

An entrant dies by executing `HALT`, or through a runtime-specific forfeit
condition (see the VM- and Python-specific clauses below). A match stops
after a completed tick once zero or one entrants remain alive, or once the
requested tick limit is reached — there is no mid-tick draw check while an
entrant is still part-way through its own turn.

### Observation and information boundaries

Neither runtime's agent code can see the complete arena, the ownership
array, opponents' internal state, score, or other engine objects directly.
The VM exposes state only through its registers and explicit `LOAD`/
`LOADI` reads of arena bytes; Python exposes state only through the
restricted `Observation` and the `READ` action (see [AGENT_API_V1.md](AGENT_API_V1.md)
for the exact Python contract — not duplicated here since it is a
programming-interface concern, not a gameplay rule).

### Arbitrary READ/WRITE

Both runtimes allow an entrant to read or write **any** arena address —
including addresses outside anything it has ever touched, addresses it
does not own, and (implementation permitting) another entrant's own code
or claimed cells. There is no access-control concept in Ruleset v1 beyond
ownership bookkeeping for scoring/attribution purposes; contesting another
entrant's cells by simply overwriting them is the core mechanic, not an
edge case.

### Seed as a gameplay concept

`Config.seed` is a genuinely Ruleset-relevant concept for the Python
runtime, since it is the deterministic root from which each entrant's
independent RNG stream is derived (see [AGENT_API_V1.md](AGENT_API_V1.md)
for the exact derivation, which is an Agent API v1 contract detail, not a
Ruleset clause itself — see "What belongs to Agent API instead" below).
For the native VM, `Config.seed` is recorded in configuration/replay data
and initializes `Kernel.rng`, but the current VM, scheduler, and built-in
assemblers do not consume that RNG — changing only the seed does not
currently change a native VM match's outcome. The *particular* seed value
used for one match is configuration, not Ruleset identity, in both cases —
see "Configuration values are not Ruleset identity" below.

---

## VM-specific Ruleset clauses

These clauses apply only to native VM matches; the Python runtime has no
analogue for most of them, by design (see "Python-specific Ruleset
clauses" below).

### Load-time ownership and overlap

Agent bytecode is copied into the arena at spawn time and remains mutable
for the rest of the match. Loading code assigns its bytes to the loading
agent, exactly like an ordinary write. Later-spawned code can overwrite
earlier code if their regions overlap; an agent continues executing from
its recorded program counter even if another agent has since replaced the
bytes at that address.

### Opcode encoding and fetch model

Every opcode costs one scheduler instruction, regardless of encoded size.
Opcodes without an immediate occupy one byte; immediate instructions occupy
one opcode byte followed by a four-byte unsigned little-endian value, and
immediate reads wrap around the arena exactly like any other address.

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

### Self-modifying arena code

Because agent bytecode lives in the same mutable arena every entrant reads
and writes, an entrant's own code — or another entrant's code — can be
overwritten during the match, changing what executes on a later fetch at
that address. This is not a special case; it follows directly from the
arena and ownership rules above.

### Invalid-opcode death

Any fetched byte other than `0` through `11` is an invalid opcode. The VM
marks the agent dead and leaves its PC on that byte (relevant to kill
attribution below).

### Agent state and accounting

Each VM agent tracks `agent_id`, `pc`, `alive`, registers `A`/`P`/`Z`
(initially zero), `cpu_used` (instructions attempted in the current tick),
`mem_writes` (cumulative successful `STORE`/`STOREI` count), and `region`
(the inclusive start/end addresses of its initially loaded bytes — purely
descriptive; it does not protect code and is never consulted when reading
or writing memory). `cpu_used` increments after every VM step, including a
step that executes `HALT` or dies on an invalid opcode.

### Kill scoring and attribution

When a newly dead agent is examined, the engine looks at ownership of the
byte at its final PC. If another agent owns that byte, that owner receives
kill credit (the shared kill scoring formula above). Self-owned and
unowned death locations produce an unattributed death. This is
last-writer attribution, not a causal history of the write that actually
caused death — it can misattribute a kill to whichever agent happened to
own that byte, not necessarily whichever agent's action was responsible.

### Determinism

The native VM is deterministic for a given configuration, bytecode, entry
addresses, spawn order, and tick limit; replay emission follows
deterministic scheduling and state iteration. This does not extend to
wall-clock GUI rendering or pMARS, which are outside this determinism
statement.

---

## Python-specific Ruleset clauses

These clauses apply only to the homogeneous Python-vs-Python runtime.
Mixed VM/Python matches are not implemented (see "What Ruleset v1 does not
cover" below) — every clause here assumes both entrants are Python.

### Source is not arena content

Python agent source code is never stored in the arena and cannot currently
be corrupted by another entrant's arena writes — unlike VM bytecode, a
Python entrant's own logic is not a target of the shared-arena contest.

### Actions map into the same shared arena

A Python entrant's `READ`/`WRITE` actions operate on the identical shared,
circular, ownership-tracked arena the VM uses — the same modulo
addressing, the same ownership assignment on write, and the same territory
scoring. Python's `pc` is controller-side bookkeeping (it only moves via
explicit `JUMP`/`JUMP_IF_ZERO` actions and wraps mod 2^32, not mod
`arena_size`); nothing is ever fetched from it, unlike the VM's real
instruction pointer.

### Mortality causes

A Python entrant's mortality is limited to: executing `HALT`; returning an
invalid or unsupported action; raising an exception from `reset()`/`act()`;
or the match reaching its termination condition. Malformed-action and
callback-failure deaths are always **forfeits**, distinguished internally
from a normal `HALT`. A forfeit is never attributed as an opponent kill —
see the next clause.

### No Python kill attribution

Python deaths — normal `HALT` or forfeit alike — never produce invented
kill attribution. This is a deliberate absence, not an oversight: the VM's
kill-attribution mechanism above depends on VM-specific fetch-time PC
ownership that has no meaningful Python analogue, since nothing is ever
"fetched" from a Python entrant's `pc`.

### Homogeneous-only execution

The current runtime supports only homogeneous Python-vs-Python matches.
Mixed VM/Python composition, corruptible Python cores, hard callback
containment on every execution path, and replication designs are not
implemented — see "What Ruleset v1 does not cover" and
[COMPATIBILITY.md](COMPATIBILITY.md) for the stable-vs-experimental
boundary this implies for 1.0.

---

## Configuration values are not Ruleset identity

`BYTEFRAY_RULESET_ID` does not change merely because one match uses
different values for Ruleset-defined fields:

```text
arena_size
tick_limit
instr_per_tick / action budget
weights (alive, kill, territory, territory_bucket)
win_mode
seed
entrant IDs
```

The **meaning** of those fields is Ruleset-defined; the **values** selected
for one match are per-match configuration. For example:

```text
"territory weight contributes to score according to floor(owned_cells /
 territory_bucket) * territory"
    = Ruleset (this document)

"territory_weight = 4 for this match"
    = Configuration (battle_engine.config.Weights)
```

A future change to the *formula* itself would require a Ruleset bump; a
future change to a *default value*, or an operator passing a non-default
value, does not.

---

## What Ruleset v1 does not cover

- **Agent API semantics** — the Python loading contract, lifecycle,
  `Observation`/`AgentAction` field definitions, and the deterministic
  entrant-seed RNG derivation belong to Agent API v1, versioned
  independently as `AGENT_API_VERSION`. See [AGENT_API_V1.md](AGENT_API_V1.md)
  for the complete contract, including the frozen RNG derivation formula.
  This document deliberately does not duplicate those field definitions.
- **Evaluation methodology** — entrant-orientation coverage, arena-
  alignment disclosure, and matrix construction are properties of
  `bytefray agents evaluate`, not of the game itself. See
  `docs/specs/evaluation_history.md` and `docs/specs/agent_evaluation.md`.
- **Redcode/pMARS** — see "Implementation details" below; pMARS matches do
  not execute under Ruleset v1 at all.
- **Mixed VM/Python matches, security sandboxing, and replication** — not
  implemented; see [FUTURE_PLANS.md](FUTURE_PLANS.md) for research-stage
  ideas that could eventually require a still-later ruleset. **Corruptible
  Python-core designs** are implemented, but under Ruleset v2
  (`bytefray-rules-2`, `v2.0.0-beta1`), not Ruleset v1 — see
  [RULES_V2.md](RULES_V2.md).

---

## Ruleset bump policy

A `BYTEFRAY_RULESET_ID` bump **is** required for a change such as:

- a scoring formula change (survival, territory, or kill);
- an ownership-semantics change;
- a kill-attribution change;
- a scheduler-order/quota-semantics change;
- a mortality-rules change;
- a winner-resolution change;
- an arena-addressing semantics change; or
- an observation/read/write gameplay-meaning change.

A `BYTEFRAY_RULESET_ID` bump is **not** required solely for:

- changing the default arena size;
- changing default scoring weights;
- changing the default tick limit;
- adding non-semantic telemetry;
- changing artifact wire format (schema bumps are their own axis);
- UI changes;
- storage-layout changes;
- an evaluation-orientation or arena-alignment methodology change;
- an agent-revision storage implementation change.

See [COMPATIBILITY.md](COMPATIBILITY.md) for a worked table mapping
example changes to which compatibility axis (Ruleset, Agent API, schema,
or methodology) they actually require.

---

## Historical relationship to evaluation-rules-1

`bytefray.evaluation`'s `EVALUATION_RULES_COMPATIBILITY_ID` was introduced
in v0.7.0 as the literal string `"evaluation-rules-1"`, narrowly scoped to
"scoring/winner-resolution/scheduling-order/derived-seed" semantics — in
other words, exactly the gameplay semantics this document now calls
`bytefray-rules-1`. As of v0.10 Phase 2,
`EVALUATION_RULES_COMPATIBILITY_ID` is a derived alias of
`BYTEFRAY_RULESET_ID` rather than an independently maintained value (see
`battle_engine.agent_evaluation`).

This alias is justified by direct inspection of the source history: the
gameplay-semantic modules this document describes —
`engine/src/battle_engine/{vm,match,scoring,results}.py` — are
byte-for-byte unchanged across every tagged release from `v0.3.0` (Bytefray
Rename & Native Core, which introduced Agent API v1 and the
`battle2.result`/`battle2.replay` schemas) through `v0.9.0`
(Orientation-Aware Evaluation), and the Python runtime's own gameplay-
relevant scheduling and RNG-derivation code
(`battle_engine.python_runtime.derive_agent_seed` and its call sites) is
likewise unchanged across that same range — the only changes to
`python_runtime.py` in that window were purely additive (Agent Lab tracing
and supervised-timeout support), not to gameplay or RNG semantics. In
other words, for the entire historical period during which
`"evaluation-rules-1"` has existed, it has always meant exactly the
gameplay semantics `"bytefray-rules-1"` now names explicitly.

This alias does **not** retroactively rewrite history: an
`evaluation.json` artifact persisted before this alias existed still
literally contains the string `"evaluation-rules-1"` in its
`rules_compatibility_id` field, never `"bytefray-rules-1"`. Readers must
continue to interpret `"evaluation-rules-1"` as the historical value it
actually is, not pretend an old artifact used the newer spelling. See
[COMPATIBILITY.md](COMPATIBILITY.md) for the general historical-alias
policy.

The maintenance rule going forward: **a gameplay-semantic change requires
one Ruleset bump, not separate Ruleset and evaluation-rules bumps** — since
`EVALUATION_RULES_COMPATIBILITY_ID` now derives from `BYTEFRAY_RULESET_ID`,
bumping the latter is sufficient.

---

## Implementation details

The following are real, current implementation behavior, not Ruleset
semantics — they are reference program behavior and interop details, not
part of what `bytefray-rules-1` freezes.

### Current built-ins

| Name | Current implementation behavior |
|---|---|
| `runner` | Cycles through `ADD`, `JZ`, and `JMP` after one initial `NOP`. It writes no memory and does not physically relocate its code. |
| `writer` | Repeatedly writes a fixed byte to one fixed direct address; one write per three-instruction loop. |
| `bomber` | Initializes P, then repeatedly writes indirectly and advances it by a fixed stride; one write per three-instruction loop after setup. |
| `flooder` | Unrolls repeated `STOREI`/`ADDP 1` pairs before jumping back. With the default eight writes per loop, it performs about four writes per eight scheduler instructions after setup, not eight. |
| `spiral` | Performs two writes to the same P address per loop and advances P by a fixed encoded step. The `delta` arithmetic changes A transiently but does not modify the immediate operand of `ADDP`, so the stride does not grow. |
| `seeker` | Scans from P for a target byte. Nonmatches advance P by one; matches write the attack byte at P, advance by the attack stride, and resume scanning. |

These descriptions document current bytecode. They characterize the
reference competitors rather than promising that future rulesets will
preserve every strategy detail. Starter manifests currently initialize
Runner, Writer, Seeker, and Spiral in a writable data root; a starter
manifest selects its same-named built-in implementation and does not
contain executable Python code.

### Redcode/pMARS — not Ruleset v1

`bytefray run --mode redcode94` invokes a separate pMARS process. Its core
size, cycles, processes, warrior length, minimum distance, rounds, failure
handling, and result parsing are pMARS-backend concerns, not part of
Ruleset v1. Redcode does not execute BATTLE VM opcodes, use BATTLE
registers, participate in native scheduling, use `BYTEFRAY_RULESET_ID`, or
currently produce a native BATTLE replay. It produces a normalized summary
on success. No Redcode/pMARS artifact is, or should be described as, using
Bytefray Ruleset v1.
