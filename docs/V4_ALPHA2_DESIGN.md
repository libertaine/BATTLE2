# Bytefray v4.0.0-alpha2 Gameplay Contract

This document is the authoritative implementation contract for the Ruleset
identity `bytefray-rules-4-alpha2`.

It is written as a **delta** against
[V4_ALPHA1_DESIGN.md](V4_ALPHA1_DESIGN.md), which remains frozen and is not
edited by this document. Every clause of the alpha1 freeze that is not
explicitly changed below carries over to alpha2 unchanged. Alpha1 remains a
fully supported, executable, explicitly selectable Ruleset; alpha2 does not
replace it, deprecate it, or reinterpret any artifact recorded under it.

The evidence behind both changes is
[V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md](V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md)
(the Phase 4 controlled gameplay study, ~36,000 matches) and the Phase 5
alpha1/alpha2 ecology qualification that followed it.

---

## 1. Identity

| Axis | Value |
|---|---|
| Ruleset ID | `bytefray-rules-4-alpha2` |
| Agent API | **v2, unchanged** — no v3, no new observation fields, no new actions |
| Replay schema | **4, unchanged** |
| Result schema | unchanged |
| Runtime kinds | Python only |
| Entrant quota `Q` | 8 |
| Core size | 8 |
| Reach legality | `[1, arena_size - 1]`, uncapped — unchanged from alpha1 |

`bytefray-rules-4-alpha2` is a **separate identity**, never an alias or a
mutation of `bytefray-rules-4-alpha1`. The same agents, seed, arena, and seat
roster can produce a different match under each, so reusing alpha1's identity
would silently reinterpret every persisted alpha1 artifact. Match, result, and
replay identity already carry the Ruleset ID as a first-class axis, so two
otherwise-identical requests under the two Rulesets never collide.

It is spelled `-alpha2`, never a bare `bytefray-rules-4`: both changes are
evidence-supported prerelease candidates, not a matured contract. See
[RULES.md](RULES.md)'s bump policy.

---

## 2. What changes from alpha1

Exactly two gameplay semantics.

### 2.1 Entrant core placement is derived from the match seed

**Alpha1** places entrant cores at an evenly-spaced seat layout anchored at
address 0 — for two entrants, `(0, arena_size // 2)`. This is deterministic,
public, and identical for every match at a given arena size, which makes

```python
enemy_core = own_core_base + arena_size // 2
```

always exactly correct without observing anything.

**Alpha2** derives every entrant's start address from the match seed, subject
to a minimum separation. That expression is no longer generally valid; an
opponent's objective must be *found*, not computed.

Phase 4 Section F2 measured this as the single largest source of strategic
distortion in the alpha1 ecology: the two agents that hardcode the formula won
100% and 80% of their matches, and fell to 21% and 24% the moment placement
became unpredictable.

### 2.2 Intra-entrant process selection is round-robin

**Alpha1** selects the next process to act by scanning an entrant's declared
process list from index 0 on every action slot. Quota freed mid-tick — most
commonly by a sibling becoming disrupted — is therefore always offered to
whichever process was declared first.

**Alpha2** scans from a rotating cursor instead, so action slots are handed
out to eligible processes in rotation.

Phase 4 Section G measured alpha1's scan as an undocumented, accidental
priority ranking distinct from the `share` each process declares, worth up to
~14 percentage points of win rate under mere declaration-order permutation.
Note that alpha1's *selection order* was never specified in the alpha1 design
freeze at all — only its quota *allocation* was (that document's §6, whose
order-invariance guarantee alpha2 preserves exactly). The lever was an
implementation detail that became strategy.

---

## 3. What does not change

Explicitly preserved from alpha1, and verified by the Phase 5 qualification
suite:

* Agent API v2: `declare_processes()`, `ObservationV2`, `ActionKindV2`. No new
  fields, no new actions, no new information. An agent that runs under alpha1
  loads and runs under alpha2.
* Replay schema 4 and the result schema.
* `Q = 8`; core size 8; reach legality and the absence of any reach cost.
* The entrant-level scheduler: `K = 2` chunked, deterministic rotating start.
* Initial process co-location — every process still starts on its entrant's
  own core base. Phase 4 Section F1 tested spreading them and found the effect
  small enough not to justify the rule.
* Disruption semantics: trigger, `D = 1`, co-location blast, automatic expiry.
* Quota allocation **and** redistribution, including largest-remainder
  allocation and stable-identity tie-breaking. Round-robin changes *which*
  eligible process receives the next slot, never how many slots each is owed.
* The visibility contract, the WRITE information boundary, and temporal
  provenance.
* Every alpha1 deferral in that document's §11 — no dynamic spawning, no
  resources, no probabilistic fog of war, no `SCAN`/`ATTACK`/`DISRUPT` action,
  no reach cap, no larger cores.

---

## 4. Placement algorithm

Implemented in `battle_engine.placement`; declared by the Ruleset as
`RulesetPolicy.core_placement == "seeded"`.

### 4.1 Minimum separation

The rule is **64 cells** of minimum circular separation between any two
entrant core base addresses (`ALPHA2_MIN_CORE_SEPARATION`). This is exactly
the value the Phase 4 seeded-placement condition used, so that study's
measured ecology applies to the shipped Ruleset.

It is deliberately far wider than the 8-cell core. The contract alpha2 needs
is not merely "cores do not overlap" but "an opponent's core is not adjacent
enough to be found by accident".

`entrant_count` cores each at least `s` apart need `entrant_count * s <=
arena_size` to fit around the ring, so the declared minimum is clamped to
`arena_size // entrant_count` when a match is too crowded to honour it
(`alpha2_min_separation`). The clamp only ever *loosens* the requirement and
is a pure function of seat count and arena size. An arena too small to keep
the cores apart at all is left to `NativeMatchService`'s existing overlap
guard to reject with its own diagnostic, rather than papered over here.

### 4.2 Candidate generation

Candidates come from a **SHA-256 counter stream**, not from `random`:

```
sha256("bytefray-rules-4-alpha2:placement:"
       f"{seed}:{arena_size}:{entrant_count}:{separation}:{seat}:{attempt}")
```

taking the first 8 bytes as a big-endian integer modulo `arena_size`.

`random.Random` seeded from the same material would be reproducible today, but
only `random.random()`'s sequence is documented as stable across Python
versions — `randrange`/`getrandbits` explicitly are not — and alpha2 placement
determinism is a cross-platform, cross-version release requirement. SHA-256 of
an ASCII payload is fully specified by its standard.

The payload is domain-separated by the Ruleset identity so it cannot collide
with any other seed-derived quantity in the engine, and includes every input
that changes the layout, so two matches differing in any of them draw
independent streams rather than sharing a prefix.

The modulo bias over a 64-bit draw is below `arena_size / 2**64` — on the
order of `2**-53` for any supported arena — and is preferred to a rejection
loop because it is branch-free and therefore trivially identical everywhere.

### 4.3 Seats, collisions, and fallback

Seats are placed in **seat order**. Seat *i* draws candidates until one is at
least `separation` cells (circular) from every seat already placed. Seat *i*'s
address therefore depends only on the seed, arena size, seat count, and the
seats before it — never on dict/set iteration order, agent identity, or
anything a caller could vary without also varying the recorded match inputs.

Swapping which *agent* occupies which seat leaves the layout fixed and swaps
the occupants, which is what makes a paired both-seat comparison meaningful:
seat advantage can be measured because the geometry is held constant.

Sampling is **bounded**: 64 candidates per seat. An unbounded retry loop would
turn an infeasible geometry into a hang. If any seat exhausts its candidates,
the **whole layout** — not just the failing seat — falls back to the alpha1
evenly-spread seat layout. A whole-layout fallback keeps the result internally
consistent rather than producing a half-seeded hybrid whose separation
guarantee is neither one thing nor the other, and makes the function total: it
always terminates and always returns a layout as separated as the arena
geometrically permits.

### 4.4 Multi-entrant behaviour

The algorithm is defined for any seat count, not only two. Three or more
entrants are placed by the same seat-ordered rejection sampling against every
previously placed seat, with the separation clamp keeping the requirement
feasible.

### 4.5 Where placement is resolved

Placement resolves in `placement.resolve_direct_match_starts`, the existing
authoritative seam that turns a caller's partial knowledge of start addresses
into the complete set a match runs with. Consequences:

* The **resolved** start addresses are what enter `MatchRequest`, and
  therefore what enter `canonical_match_id` and the persisted artifacts. A
  layout is reproducible from a recorded seed, arena size, and seat count
  alone.
* **Explicit starts are still honoured exactly.** Passing `--a-start`/
  `--b-start` under alpha2 gives those addresses, unadjusted, exactly as under
  every other Ruleset. This is what lets an alpha1 layout be replayed under
  alpha2 semantics for comparison.
* Because the seed is required to place, `resolve_direct_match_starts` raises
  rather than substituting a default seed for a seeded-placement Ruleset —
  every such match sharing one layout is precisely the predictability alpha2
  exists to remove.

Tournament pairings are re-placed from their own derived per-match seed rather
than the roster-wide `index * spacing` layout, which would otherwise
reintroduce fixed predictable placement from the harness rather than from the
Ruleset. This is applied during scheduling, so the execute and resume paths
compute the same `canonical_match_id`.

`bytefray agents evaluate` does **not** accept alpha2. Evaluation's placement
conditions (`standard_placements`/`standard_layouts`) are an explicit,
disclosed methodology axis, and running them under alpha2 would produce
artifacts labelled alpha2 that actually ran alpha1's fixed opposite placement
— the exact distortion alpha2 removes. Its existing fail-closed `--ruleset`
guard rejects alpha2 with a clear message. Adopting alpha2 in evaluation needs
a methodology decision this Ruleset change does not supply.

---

## 5. Process selection algorithm

Implemented in `ProcessMatchController._select_active_process`; declared by
the Ruleset as `RulesetPolicy.process_selection == "round_robin"`.

Both modes select only from processes that are eligible this tick and still
under their effective allocation, and neither can change how large that
allocation is.

| Clause | Behaviour |
|---|---|
| **Initial cursor** | `0` for every entrant, set once at controller construction. An entrant's first action of the match still goes to its first declared process, and a single-process entrant is bit-for-bit unaffected by this mode. |
| **Advancement** | Only on a successful selection, to `(selected_index + 1) % process_count`. A slot that selects nothing leaves the cursor untouched, so a wasted slot never silently skips a process's turn. |
| **Disruption** | A disrupted process is absent from the effective allocation entirely, so it is passed over without consuming its turn; the scan continues to the next candidate in rotation. It rejoins at its own list position once eligible again. |
| **Quota exhaustion** | Identical treatment: a process at its allocation is not a candidate. When no process has quota left, the scan completes without selecting — exactly as alpha1 does. |
| **Redistribution** | Handled entirely upstream by the unchanged allocator. Selection sees only the resulting larger allocations and hands the extra slots out in rotation rather than all to the earliest-declared process. |
| **Tick boundary** | The cursor deliberately does **not** reset. It is match-scoped, so rotation continues across ticks and no process gets a systematic first-slot advantage every tick merely by being declared first. Resetting per tick would reintroduce a weaker form of the same bias. This is the behaviour Phase 4 measured. |
| **All processes ineligible** | The entrant receives no action for that slot — unchanged from alpha1. |

The cursor is keyed by `agent_id` and advanced by integer index into the
declared process list, never by dict or set iteration order, so rotation is
reproducible across platforms and Python versions.

---

## 6. Compatibility and availability

### Agents

Agent API v2 is unchanged, so **every** API-v2 agent loads and runs under
alpha2. What changes for some of them is whether their *strategy* still works:
an agent that hardcodes `own_core_base + arena_size // 2` will aim at empty
memory. That is a deliberate, disclosed gameplay-balance change to a Ruleset,
not a compatibility break — the assumption those agents encode was a
Ruleset-level historical accident, never a documented Agent API contract.

`hydra_alpha2` and `nemesis_alpha2` are alpha2-targeted derivatives that
acquire targets from `visible_enemy_anchor_addresses` and `READ`/
`previous_read_owner` search instead. The historical `hydra` and `Nemesis`
are unchanged and remain the alpha1 controls.

### Ruleset selection

| Surface | Behaviour |
|---|---|
| Omitted `--ruleset`, Agent API v2 roster | resolves to **alpha2** (the newest intended v4 development Ruleset) |
| Omitted `--ruleset`, Agent API v1 roster | `bytefray-rules-2`, unchanged |
| `bytefray run`, `agents test`, `tournament` | both v4 alphas selectable by name |
| Agent Designer — Simple | current gameplay only: `bytefray-rules-2` and alpha2 |
| Agent Designer — Advanced/Development | both v4 alphas, alpha2 listed first |
| `agents evaluate` | alpha1 only among the v4 alphas (see §4.5) |

Alpha1 is never hidden: it stays registered, explicitly selectable everywhere
a Ruleset can be named, and is what every persisted alpha1 artifact resolves
to.

### Replay and result schemas

Unchanged at 4 and its current version respectively. Seeded placement only
changes a per-entrant `start` *value* schema 4 already carries; round-robin
only changes the order of records the schema already defines. A Ruleset change
is not a schema change.

---

## 7. Explicit alpha2 non-goals

Alpha2 deliberately adopts the **smallest** evidence-supported change set.
Phase 4 tested and rejected, or found insufficient evidence for, all of the
following, and none is part of alpha2:

* larger cores (breaks one dominant strategy but converts the roster's most
  symmetric matchup into permanent stalemate);
* any reach cap (disarms the dominant agents rather than creating graduated
  local play; raised the tick-limit rate from 47% to 91%);
* initial process spread (measured effect too small to justify the rule);
* disruption immunity, cooldowns, or resources;
* dynamic spawning;
* Agent API v3, replay schema 5, or any change to the observation contract.

Adding any of these requires new evidence, not a preference.
