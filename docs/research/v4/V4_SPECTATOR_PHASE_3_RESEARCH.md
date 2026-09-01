# Bytefray v4 Spectator Research Phase 3 — Deterministic Semantic Event Derivation

## Verdict

**PASS.**

Phase 3 asked whether a real, validated Bytefray match can be deterministically
explained: what factually happened, when, and *who was actually capable of
knowing about it*. The answer is yes, for a small vocabulary of thirteen event
kinds, every one of which was produced by an actual deterministic match and
traced back from canonical source records to derived output.

The most consequential result is not the vocabulary. It is that Phase 1's
replay-only detection model — which is what a Fog of War implementation would
have been built on — is **wrong in two independent ways**, and the API-v2 trace
is what proves it. See §5.2.

| Area | Classification |
|---|---|
| Phase 2 tracing works in real matches (independently re-proven) | **CONFIRMED** |
| Consumer-side replay/trace binding verification | **IMPLEMENTED AND QUALIFIED** |
| Pair consistency beyond the digest (state cross-check) | **IMPLEMENTED AND QUALIFIED** |
| Trace newline / byte-identity question | **NO SEMANTIC CONSEQUENCE — DEFERRED, WITH ONE OPERATIONAL CONSTRAINT DOCUMENTED** |
| Accepted semantic event vocabulary (13 kinds) | **QUALIFIED** |
| Rejected candidates (`PROCESS_CREATED`, `PROCESS_DEATH`) | **NO ENGINE SUPPORT — REJECTED WITH EVIDENCE** |
| Event granularity | **RESOLVED — per entrant/tick for detection, per decision for action facts** |
| Deterministic ordering and identity | **QUALIFIED** |
| Perspective / `visible_to` model | **QUALIFIED, WITH EXPLICIT LIMITS** |
| Phase 1 detection semantics | **DEFECTIVE — two findings, see §5.2** |
| `DISRUPTED` / `REJECTED_QUOTA` contract | **CLARIFIED — reserved, unreachable, spec updated** |
| Simulation isolation | **CONFIRMED** |
| Repeat-run determinism (incl. `PYTHONHASHSEED`) | **CONFIRMED** |
| **Phase 3 overall** | **PASS** |

Fog of War is **GO WITH PREREQUISITES**. Spectator Director is **GO WITH
PREREQUISITES**. Neither was implemented. See §16, §17, and §19.

### Success criteria

| # | Criterion | Met | Where |
|---|---|---|---|
| 1 | Phase 2 tracing independently demonstrated in real matches | ✅ | §2 |
| 2 | Replay/trace pairs validated before analysis | ✅ | §3 |
| 3 | A small useful set of events has objective definitions | ✅ 13 kinds | §6 |
| 4 | Those events are deterministically derived | ✅ | §14 |
| 5 | Their ordering is deterministic | ✅ | §7, §14 |
| 6 | Accepted events have meaningful end-to-end behavioural tests | ✅ 35 tests | §13, §21 |
| 7 | Perspective visibility correctly represented or explicitly limited | ✅ | §8 |
| 8 | Analysis does not affect canonical simulation/replay behaviour | ✅ | §15 |
| 9 | The analyzer produces useful output from representative real matches | ✅ 12-match corpus | §12, §13 |
| 10 | Documentation distinguishes accepted facts from speculative semantics | ✅ | §5, §6 |

No stop condition from the brief's §26 was triggered. The vocabulary was kept
deliberately small: two candidate kinds were rejected for having no engine
mechanic at all, four were deferred for needing an editorial threshold or
choice, and six subjective kinds were left untouched.

---

## 1. Repository baseline

Recorded before any file was modified.

| Fact | Value |
|---|---|
| Repository | `D:\Projects\BATTLE2` |
| Branch | `v4-spectator-phase2-development` |
| `HEAD` at Phase 3 start | `d7b46bb908e4e08edaa116098784c6acb4a6d80b` (`docs(v4): report Phase 2 qualification`) |
| `origin/main` | `4aa8ac3a4cc0deccfdd6c5b94136933b315335be` |
| Working tree at start | Clean. `git status --porcelain` produced no entries. |

`git status` also emitted `warning: could not open directory
'.pytest-cache-v141/': Permission denied`. That directory is a git-ignored,
repo-local pytest cache left by an earlier run under different ACLs; the same
warning appears in `ruff check .`. It is pre-existing, affects no tracked file,
and was not touched.

Phase 2 commits confirmed present and in order:

| Commit | Subject |
|---|---|
| `1e9ea6b` | `docs(v4): specify API-v2 agent trace contract` |
| `b5fe0f4` | `feat(v4): implement api-v2 agent trace schema and observational pipeline` |
| `5b44dc8` | `fix(v4): harden API-v2 trace contract` |
| `d7b46bb` | `docs(v4): report Phase 2 qualification` |

Earlier spectator work also present: `f4cf99d` (Phase 1 wrapper hardening),
`ecbdb5a` (Phase 1 semantic pipeline), `0463630` (Phase 0.6), `94d19da`
(Phase 0.5), `a30a88a` (Phase 0).

**Filesystem state actually observed** — recorded rather than assumed. The
repository root contains a number of untracked working artifacts
(`combat_replay.jsonl`, `test_replay.jsonl`, `replay.jsonl`, `summary.json`,
`pytest_full2.log`, `release_notes.txt`, plus `build/`, `dist/`, `work/`,
`runs/`). All are git-ignored or pre-existing; none were created, modified, or
consumed by Phase 3. Phase 3's own scratch artifacts were written outside the
repository entirely.

### 1.1 Files inspected

| File | Why |
|---|---|
| `docs/specs/v4_api_v2_trace.md` | The Phase 2 contract under test |
| `docs/research/v4/V4_SPECTATOR_PHASE_2_RESEARCH.md` | Phase 2 findings and the wiring-defect lesson |
| `engine/src/battle_engine/agent_trace.py` | Trace record model, `read_trace_v2`, binding record |
| `engine/src/battle_engine/process_runtime.py` | v4 tick loop, `_visible_enemy_anchors`, `_emit_decision_trace`, quota/selection filters, disruption rule |
| `engine/src/battle_engine/match_service.py` | Binding lifecycle, `_finalize_native_artifacts`, `_open_trace_writer` |
| `engine/src/battle_engine/python_runtime.py` | `apply_core_capture` (the elimination mechanic) |
| `engine/src/battle_engine/vm.py` | `_wr8` — the single ownership-mutation path |
| `engine/src/battle_engine/telemetry.py` | Replay record shape (`memory_diffs`, `processes`, `events`) |
| `engine/src/battle_engine/replay.py` | Schema 4 record dataclasses, `write_replay` |
| `engine/src/battle_engine/spectator_events.py` | Phase 1 replay-only analyzer |
| `engine/src/battle_engine/spectator_aggregation.py` | Phase 1 temporal aggregation |
| `engine/tests/test_v4_trace_equivalence.py`, `test_spectator_analyzer.py`, `test_spectator_aggregation.py`, `test_agent_trace.py` | Existing regression coverage |
| `pytest.ini`, `pyproject.toml`, `.gitattributes` | Test paths, lint/type config, line-ending policy |

### 1.2 Files modified or added

| File | Change |
|---|---|
| `engine/src/battle_engine/spectator_derivation.py` | **New.** Pair verification + deterministic semantic derivation + research CLI. |
| `engine/tests/test_v4_spectator_derivation.py` | **New.** 35 behavioural tests over real matches. |
| `tools/spectator_derive.py` | **New.** Source-checkout wrapper, matching the Phase 1 `tools/spectator_analyzer.py` convention. |
| `engine/src/battle_engine/spectator_events.py` | **+19 lines, additive only.** Exposes `load_schema4_replay`/`LoadedReplay` so both analyzers share one replay contract. No existing line changed, no behaviour change. |
| `docs/specs/v4_api_v2_trace.md` | §7.1 added (reserved statuses); §9 extended (reference verifier, byte-identity constraint). |
| `docs/research/v4/V4_SPECTATOR_PHASE_3_RESEARCH.md` | **New.** This document. |

No change to `process_runtime.py`, `match_service.py`, `replay.py`, `vm.py`,
`agent_trace.py`, the scheduler, the Ruleset policy, or any agent-visible
behaviour. Phase 1's analyzer logic was not altered.

---

## 2. Phase 2 prerequisite verification

Phase 2's central deliverable existed structurally but did not execute. Phase 3
re-proved the repaired behaviour independently before building on it, using
real matches rather than hand-built records.

| Requirement | Result | Evidence |
|---|---|---|
| V2 trace declares schema version 2 | **PASS** | `document.header.schema_version == TRACE_SCHEMA_VERSION_V2` |
| Decision records are actually emitted | **PASS** | 5,779 `DecisionRecordV2` records across the 12-match corpus |
| Decision count plausible vs. executed ticks/processes | **PASS** | Exactly 8 per entrant per tick for every uninterrupted entrant; the deficits are all explained by disruption (below) |
| Observations populated | **PASS** | Exact field assertions on the first record of a known process |
| READ records requested and effective data | **PASS** | Hostile reads carry `read_owner="B"`, `read_value=0xCE`, `normalized_address=32` |
| WRITE/MOVE record effective addresses | **PASS** | Every applied action's `normalized_address` cross-checked against the replay |
| Normalized addresses present where applicable | **PASS** | Absent only on rejected actions, where nothing was applied |
| Binding written after replay finalization | **PASS** | `binding.replay_sha256 == sha256(replay bytes)` on every corpus match |
| V1 readers reject V2 traces | **PASS** | Pre-existing Phase 2 regression, re-run green |
| V2 readers parse V2 traces | **PASS** | Every corpus trace parsed by `read_trace_v2` |
| Trace-disabled matches unaffected | **PASS** | §15 |

The decision-count check deserves emphasis because it is the assertion Phase 2
lacked. Each entrant receives `instr_per_tick = 8` action slots per tick, so a
healthy entrant produces exactly 8 records per tick. In the `_hunt` fixture:

```
A: 8 decisions on every one of ticks 1..12
B: 6 on tick 1, 8 on tick 2, 0 on tick 3, 8 on tick 4, 0 on tick 5, ...
```

B's tick-1 deficit is A's write landing on B's anchor mid-tick and disrupting
it; B's zero ticks are full suppression. That pattern is asserted exactly. A
derivation that silently stopped emitting could not produce it, which is
precisely the failure mode `assert len(lines) > 2` could not catch.

**Prerequisite holds. Phase 3 proceeded.**

---

## 3. Replay/trace binding verification

Phase 2 created the binding but deliberately shipped no consumer-side verifier.
Phase 3 is the first real consumer, so `verify_pair()` was implemented first,
using the existing Phase 2 binding contract. No second binding mechanism was
introduced, and canonical replay identity was not modified.

```
Replay A + Trace A   binding matches   -> analysis allowed
Replay A + Trace B   binding mismatch  -> analysis rejected, exit 2, no output
```

`verify_pair(replay, trace)` performs, in order:

1. Parse the trace with `read_trace_v2`. Any parse failure — malformed record,
   missing required field, a V1 `schema_version` — becomes
   `PairBindingError("unusable API-v2 trace ...")`.
2. Require a `BindingRecord` footer. Absent → `PairBindingError("...no binding
   record...")`.
3. Hash the replay's **raw bytes** and compare against `binding.replay_sha256`.
4. Cross-check `binding.match_id` against the replay header's `match_id`, and
   `binding.entrant_identities` against the header's entrant list.

Malformed-versus-mismatched is a real distinction here, not a cosmetic one: a
malformed trace means "this artifact is broken", a mismatch means "these two
artifacts are from different matches", and an operator's response differs.
They are separate error messages and separately tested.

| Case | Behaviour | Test |
|---|---|---|
| Valid pair | Returns a `PairBinding` carrying digest, match id, ruleset, entrants | `test_verify_pair_accepts_a_matching_replay_and_trace` |
| Trace from a different match | `PairBindingError: binding mismatch` | `test_verify_pair_rejects_a_trace_bound_to_a_different_match` |
| One byte changed in the replay | `PairBindingError: binding mismatch` | `test_verify_pair_rejects_modified_replay_bytes` |
| Binding footer removed | `PairBindingError: no binding record` | `test_verify_pair_rejects_a_trace_with_no_binding_record` |
| Binding present but missing `replay_sha256` | `PairBindingError: unusable API-v2 trace` (malformed, not mismatch) | `test_verify_pair_distinguishes_a_malformed_trace_from_a_mismatch` |
| V1 `schema_version` on the header | `PairBindingError: unusable API-v2 trace` | `test_verify_pair_rejects_a_v1_schema_trace` |
| Replay file absent | `PairBindingError: cannot read replay` | `test_verify_pair_reports_a_missing_replay_clearly` |

No security machinery beyond this was added. There is no signing, no MAC, no
tamper-evidence claim: the binding answers "are these the same match", not "was
this forged".

### 3.1 The digest is necessary but not sufficient

A hash over the replay says nothing about the trace's own contents. A trace
edited to claim a write landed one cell over still hashes against the same
replay, because the binding covers the *replay's* bytes.

So the analyzer performs an independent **state cross-check** at every tick
boundary, comparing three reconstructions against canonical truth:

| Check | Reconstructed from | Compared against |
|---|---|---|
| Applied-write sequence for the tick | trace `WRITE` decisions in order | replay `memory_diffs`, range-expanded in order |
| Every process anchor at end of tick | trace applied `MOVE` results | replay `processes[].anchor` |
| Disruption set for the tick | replaying the shared-location rule against reconstructed anchors | replay `processes[].disrupted` |

Any disagreement raises `PairConsistencyError` and analysis stops. All three
held on every tick of every match analysed during Phase 3 — the 12-match
corpus, the 3- and 4-entrant matches, the wraparound-core matches, and every
match built inside the test suite. `test_derivation_rejects_a_trace_whose_
actions_contradict_the_replay` proves the check bites by tampering with a
single applied write's `normalized_address` in a trace that still passes
binding verification.

This is also what makes ownership reconstruction *exact* rather than
approximate. In a v4 match there are exactly two `VM._wr8` call sites
(`process_runtime.py:685` core seeding, `process_runtime.py:1200` applied
`WRITE`); the v1/v3 `seed_core_ownership`/`maintain_core_beacons` paths are not
imported by the v4 runtime. So tick-0 memory diffs plus the trace's applied
writes account for every ownership change in the match, with nothing inferred.

---

## 4. Trace newline / byte-identity investigation

Phase 2 noted `TraceWriter` opens its file in text mode and is therefore
subject to platform newline translation. Phase 3's job was to decide whether
that matters here, not to expand it into a refactor.

Measured on this Windows host, for one corpus match:

| Artifact | Bytes | CRLF line endings | Bare LF | Digest stable across line endings |
|---|---:|---:|---:|---|
| `replay.jsonl` | 32,468 | 28 | 0 | **No** |
| `trace.jsonl` | 190,236 | 311 | 0 | **No** |

Answering the questions directly:

- **Are trace bytes canonical?** No. Nothing hashes them. The Phase 2 binding
  covers the replay's bytes only.
- **Does binding cover trace bytes?** No — replay only.
- **Could CRLF/LF differences affect semantic reading?** No. `read_trace_v2`
  parses via `text.splitlines()`, which treats both identically. Parsing the
  same trace as CRLF and as LF produced **identical** header, records, and
  binding, and identical derived event streams
  (`test_trace_line_endings_do_not_change_the_derived_stream`).
- **Could they affect deterministic golden fixtures?** Only if Phase 3
  introduced any. **It introduced none** — no golden trace, no golden replay,
  no committed artifact with a pinned digest. Every test builds its match at
  run time.
- **Could they affect a planned trace identity?** Phase 3 establishes no trace
  identity. The derived stream's identity is *logical*, derived from parsed
  records, and was proven byte-identical from CRLF and LF inputs.
- **Is normalized logical record content identical across platforms?** Yes,
  demonstrated directly.

**Finding: a storage-byte difference with no semantic consequence for Phase 3.
Documented and deferred.** Fixing `TraceWriter` would be a change with no
observable benefit at this phase, and the same text-mode property exists in
`JSONLSink` and `write_replay` besides.

### 4.1 The genuinely consequential adjacent finding

`write_replay` also uses a text-mode stream, so **the canonical replay's
`replay_sha256` is itself platform-dependent** — a pre-existing property
already recorded in `docs/V4_ALPHA2_PHASE5_QUALIFICATION.md` ("Raw replay bytes
differ between platforms only by line endings ... a pre-existing property
affecting every Ruleset equally"). Phase 3 does not change it: §4 of the brief
forbids modifying canonical replay identity for spectator purposes, and doing
so would break every existing pinned identity in the repository.

But it has an operational consequence a pair consumer must know, so it is now
in the spec (§9): **replay/trace pairs must be moved and stored as binary.**
Re-encoding a replay's line endings — a text-mode copy, or committing it under
this repository's `* text=auto eol=lf` attribute and checking it out — changes
the digest without changing a single logical record, and `verify_pair` will
correctly refuse the pair. `_replay_digest` therefore reads bytes, deliberately,
and its docstring says why.

This is also the concrete reason Phase 3 commits no replay fixtures. The prior
Bytefray cross-platform CRLF/LF identity failure was exactly a committed
fixture that was not byte-stable under LF and CRLF checkouts; building golden
pair fixtures here would have reproduced it.

---

## 5. Semantic-event candidate matrix

Every candidate from the brief, audited against what the v4 engine actually
provides. "Tick source" names where the tick number comes from; note that
`DecisionRecordV2` has **no `tick` field** — the tick is
`observation.current_tick`.

| Event | Objective definition | Required source data | Tick source | Actor(s) | Target(s) | Perspective visibility | Deterministic? | Verdict |
|---|---|---|---|---|---|---|---|---|
| `DETECTION_GAINED` | An address is in entrant E's union of `visible_enemy_anchor_addresses` over tick T, and was not in E's union for E's previous *sampled* tick | trace `observation.visible_enemy_anchor_addresses` | `observation.current_tick` | E | *none — see §8.1* | E only | Yes | **ACCEPT WITH LIMITATION** |
| `DETECTION_LOST` | Inverse of the above | same | same | E | *none* | E only | Yes | **ACCEPT WITH LIMITATION** |
| `HOSTILE_READ` | An applied `READ` whose `applied_result.read_owner` is another entrant | trace `applied_result` | `observation.current_tick` | reader | cell owner | reader only | Yes | **ACCEPT** |
| `FIRST_HOSTILE_READ` | The first `HOSTILE_READ` for an ordered (actor, target) pair in the match | as above + running state | same | reader | cell owner | reader only | Yes | **ACCEPT** |
| `HOSTILE_WRITE` | An applied `WRITE` whose target cell was owned by another entrant immediately before | trace `WRITE` + ownership reconstructed from replay tick-0 seed | `observation.current_tick` | writer | displaced owner | **nobody** | Yes | **ACCEPT** |
| `FIRST_HOSTILE_WRITE` | First `HOSTILE_WRITE` per ordered (actor, target) pair | as above | same | writer | displaced owner | **nobody** | Yes | **ACCEPT** |
| `CORE_CELL_LOST` | A `HOSTILE_WRITE` whose address is in the victim's own core region | as above + core membership from tick-0 seed | same | attacker | victim | **nobody** | Yes | **ACCEPT** |
| `PROCESS_DISRUPTED` | An applied `WRITE` on a cell where a live enemy process is currently anchored, for a process not already disrupted this tick | trace `WRITE` + reconstructed anchor timeline | `observation.current_tick` | writer | victim entrant + process | **nobody** | Yes | **ACCEPT** |
| `EFFECTIVE_MOVE` | A process's anchor at end of tick T differs from end of tick T−1 | reconstructed anchors, cross-checked against replay `processes[].anchor` | replay tick | mover | — | mover only | Yes | **ACCEPT WITH LIMITATION** |
| `PROCESS_CREATED` | — | — | — | — | — | — | — | **REJECT — no engine mechanic** |
| `PROCESS_DEATH` | — | — | — | — | — | — | — | **REJECT — no engine mechanic** |
| `AGENT_ELIMINATED` | Replay `kill`/`death` tick event | replay `events` | replay tick | killer (if attributed) | victim | **nobody** | Yes | **ACCEPT** |
| `AGENT_FORFEITED` | Replay `forfeit` tick event | replay `events` | replay tick | — | victim | **nobody** | Yes | **ACCEPT** |
| `MATCH_ENDED` | Replay result record | replay result | `result.ticks` | — | — | **nobody** | Yes | **ACCEPT** |
| `VICTORY` | Replay result with a non-null winner | replay result | `result.ticks` | winner | — | **nobody** | Yes | **ACCEPT WITH LIMITATION** |
| `FIRST_BLOOD` | ambiguous | — | — | — | — | — | — | **DEFER** |
| `CORE_DISRUPTION` | conflates two mechanics | — | — | — | — | — | — | **REJECT (renamed)** |
| `LARGE_OVERWRITE` | requires a threshold | — | — | — | — | — | — | **DEFER** |
| `PROCESS_HIT` | duplicate of `PROCESS_DISRUPTED` | — | — | — | — | — | — | **REJECT (redundant)** |
| `AGENT_CRITICAL` | requires a threshold | — | — | — | — | — | — | **DEFER — but see §6.7** |
| `MOMENTUM_SWING`, `COMEBACK`, `DOMINATING`, `DESPERATION`, `PRESSURE`, `TURNING_POINT` | subjective | — | — | — | — | — | — | **DEFER (explicitly out of scope)** |

### 5.1 Rejections and deferrals, with reasons

**`PROCESS_CREATED` / `PROCESS_DEATH` — REJECT, no engine support.** This is a
factual finding about v4, not a scoping choice. An entrant's processes are
fixed by `declare_processes()` before tick 0 and stored in
`ProcessEntrantSpec.processes`; nothing in `ProcessMatchController.run` adds to
or removes from that list. Processes cannot be created, cannot die, and cannot
be individually eliminated. The only per-process state change the engine has is
**disruption**, which is temporary (one tick) and is modelled as
`PROCESS_DISRUPTED`. Any spectator design that assumed process births and
deaths — including the Fight Night concept — needs revising against this.

**`CORE_DISRUPTION` — REJECT as named.** Phase 1 uses this name for the
anchor-hit mechanic, which has nothing to do with core regions: disruption
fires when an enemy `WRITE` lands on a process's *anchor*, wherever that is.
The name conflates it with core capture, a genuinely different mechanic that
ends matches. Phase 3 uses `PROCESS_DISRUPTED` for the anchor hit and
`CORE_CELL_LOST` for the core mechanic. Phase 1's
`SemanticEventKind.CORE_DISRUPTION` was **not** renamed — it is shipped and its
tests are green — but the divergence is recorded here and should be resolved
when the two analyzers are reconciled.

**`FIRST_BLOOD` — DEFER.** At least four defensible definitions exist (first
hostile read, first hostile write, first disruption, first core cell lost), and
choosing among them is editorial. `FIRST_HOSTILE_READ` and
`FIRST_HOSTILE_WRITE` already carry the objective content; a presentation layer
can define `FIRST_BLOOD` on top of them without this layer having to guess.

**`LARGE_OVERWRITE`, `AGENT_CRITICAL` — DEFER.** Both need a threshold ("large",
"critical") that the engine does not supply. Phase 3 declines to invent one.

**`PROCESS_HIT` — REJECT as redundant** with `PROCESS_DISRUPTED`.

**Subjective set — DEFER, as instructed.** No unexpected engine mechanic
supplies an unambiguous objective definition for any of them. No editorial
language entered the vocabulary.

### 5.2 Two defects found in Phase 1's detection semantics

This is Phase 3's most important finding, because Fog of War would have been
built on top of it.

Phase 1's `spectator_events._visible_pairs` reconstructs visibility
*geometrically* from the replay's end-of-tick process snapshots. The engine's
`_visible_enemy_anchors` computes it *immediately before every callback* and
delivers it to the agent. These are not the same thing, and the trace lets the
difference be measured for the first time.

**Defect 1 — Phase 1 leaks omniscient identity.** Its `DETECTION_GAINED` /
`DETECTION_LOST` events carry a `target_entrant_id`. The engine deliberately
does not provide it: `_visible_enemy_anchors` returns
`tuple(sorted(visible))` — bare addresses — and its own docstring states
"identities and structural metadata remain private". An entrant that detects an
occupied address does **not** know whose process occupies it, whether it is one
opponent or three, or anything about it. Phase 1's events assert knowledge the
observer was never given. Measured across the corpus, Phase 1 attaches a target
identity to **every detection event it emits** — in all nine corpus
matches that produce any detection at all.

**Defect 2 — Phase 1 both misses and mistimes real contact.** In the
`contact_window` scenario (a process with reach 4 walking steadily past a
stationary opponent):

| | gains | losses | ticks |
|---|---:|---:|---|
| Phase 1 (replay-only, end-of-tick geometry) | 5 | 5 | gains at 2, 10, 18, 26, 34 — **entrant A only** |
| Phase 3 (trace, delivered observations) | 10 | 10 | gains at 3, 11, 19, 27, 35 for **A and B** |

Two independent errors compound:

- **False negatives.** Entrant B (reach 1) genuinely detected A — the engine
  delivered A's anchor in B's observation — but only *during* a tick, while A
  was passing through. A's anchor at every tick boundary is 8, 16, 24 …, never
  within 1 of B's position, so Phase 1's end-of-tick geometry never sees the
  contact at all. It misses **half of all detection in this match**.
- **Timing error, in the leaking direction.** Phase 1 reports A's detection one
  tick *earlier* than the engine told A. A ends tick 2 at anchor 16, which is
  within reach 4 of B at 20 — so Phase 1 declares detection at tick 2. But A
  received no further observation during tick 2 after arriving there; the first
  observation A was actually handed containing address 20 was during tick 3.
  A replay-only Fog Cam would reveal knowledge to a viewer one tick before the
  entrant possessed it.

A third, smaller instance of the same class appears in the `elimination`
match: Phase 1 emits a `DETECTION_LOST` on the tick the victim dies, because
the dead entrant drops out of its geometric visibility computation. Phase 3
emits none — the surviving entrant received no observation after the death,
because the match ended. Phase 1's event is arguably true as a *world* fact and
false as a *knowledge* fact, and its `viewer_entrant_id` field makes it read as
the latter.

**Conclusion: end-of-tick geometric reconstruction is not a valid proxy for
delivered knowledge.** Perspective projection must be driven by the trace's
observation stream. This is the single hardest prerequisite on the Fog phase.

---

## 6. Accepted event definitions

Thirteen kinds. Each is stated to the precision §8 of the brief demands.

### 6.1 `DETECTION_GAINED` / `DETECTION_LOST`

> **Definition.** Let `U(E, T)` be the union of
> `observation.visible_enemy_anchor_addresses` across every `DecisionRecordV2`
> for entrant `E` whose `observation.current_tick == T`. Let `P(E)` be
> `U(E, T')` for the most recent tick `T' < T` in which `E` produced at least
> one decision, or `∅` if there is none. Then `DETECTION_GAINED` carries
> `U(E,T) \ P(E)` and `DETECTION_LOST` carries `P(E) \ U(E,T)`.
>
> **Source.** `DecisionRecordV2.observation.visible_enemy_anchor_addresses`.
> **Tick.** `observation.current_tick`.
> **Actors.** `(E,)`. **Targets.** `()` — see §8.1.
> **Visible to.** `(E,)`, plus the omniscient spectator.

**Why the union, and not per decision.** The engine re-evaluates visibility
before *every* callback, using all of the entrant's currently-eligible
processes as sensors. An entrant whose own processes move can therefore see its
visible set flip several times inside one tick. Measured in the `OSCILLATOR`
fixture, entrant A's tick-1 observations run
`() → () → (32,) → () → (32,) → (32,) → (32,) → (32,)`: four transitions, none
of which is a spectator moment. Per-decision derivation would emit
gained/lost/gained as events. The union rule emits one `DETECTION_GAINED`.
`test_intra_tick_visibility_oscillation_does_not_become_spectator_events`
asserts both the flapping and its suppression, so the test fails if either the
mechanic or the rule changes.

The union is preferred over "the entrant's last observation in the tick"
because the last observation is *not* the end-of-tick state either (the entrant
may act again afterwards) and because discarding an address the entrant was
genuinely told about would lose real knowledge. The union never claims
knowledge the entrant was not handed, and never discards knowledge it was.

**Edge cases, all handled and tested:**

- *First observation of the match.* `P(E)` starts empty, so first contact is a
  real `DETECTION_GAINED` rather than a silent initial condition.
- *Multiple newly discovered addresses.* Grouped by the decision index that
  first carried each, so simultaneous discoveries produce one event and
  staggered ones produce separate events at their true positions.
- *Multiple decisions by the same entrant in one tick.* Collapsed by the union.
- *An unsampled tick.* If every one of `E`'s processes is disrupted, the
  runtime filters them before `act()` and `E` receives **no observation at all**
  that tick. `U(E,T)` would be empty, and a naive rule would emit
  `DETECTION_LOST` for everything `E` knew. The definition therefore carries
  `P(E)` forward across unsampled ticks. This is not hypothetical: in the
  `_hunt` fixture, entrant B is fully suppressed on ticks 3, 5, 7, 9 and 11.
  `test_a_tick_with_no_callbacks_does_not_fabricate_detection_loss` first
  proves such ticks exist, then asserts no detection event is derived on them.
- *A dead entrant.* Produces no decisions, so it is never sampled again; its
  last known state simply stops updating. Its opponents see its anchors leave
  their visible sets, which is a real `DETECTION_LOST` for them.

**Limitation (why ACCEPT WITH LIMITATION):** detection is *sampled*, not
continuous. Contact that begins and ends entirely between two of an entrant's
callbacks is invisible to this layer, because it was invisible to the entrant.
That is the correct behaviour for a knowledge model and the wrong behaviour for
a world model — the two must not be conflated.

### 6.2 `HOSTILE_READ` / `FIRST_HOSTILE_READ`

> **Definition.** A `DecisionRecordV2` with `action.kind == "read"`,
> `applied_result.status == "APPLIED"`, and `applied_result.read_owner` not
> `None` and not equal to `agent_id`. `FIRST_HOSTILE_READ` additionally
> requires that the ordered pair (reader, owner) has not occurred before.
>
> **Source.** `applied_result.read_owner`, `.read_value`,
> `.normalized_address`. **Actors.** reader. **Targets.** cell owner.
> **Visible to.** the reader only.

Nothing is inferred: `read_owner` is a value the engine computed and returned,
and the reader receives it on its next observation as `previous_read_owner`.
The cell's owner is never told it was inspected — a v4 read mutates nothing —
which makes this the cleanest example in the vocabulary of an event that is
real, attributed, and one-sided.

### 6.3 `HOSTILE_WRITE` / `FIRST_HOSTILE_WRITE`

> **Definition.** An applied `WRITE` whose target cell's owner, immediately
> before the write, was a different entrant. Writing an unowned cell is
> territory claim and is deliberately **not** an event
> (`test_writing_an_unowned_cell_is_not_a_hostile_event`).
>
> **Source.** trace `WRITE` decisions in file order, against an ownership map
> seeded from the replay's tick-0 memory diffs and advanced by each applied
> write. **Actors.** writer. **Targets.** displaced owner.
> **Visible to.** `()` — nobody.

The audience is the finding. The engine tells the writer only that its action
applied; it never reports whose cell it took. It tells the victim nothing at
all — a victim can discover the loss only by reading the cell itself, which
would appear as that entrant's own `HOSTILE_READ`. Both parties can act on this
information; neither is given it.

### 6.4 `CORE_CELL_LOST`

> **Definition.** A `HOSTILE_WRITE` whose address belongs to the victim's own
> core region. Carries `remaining_core_cells`: how many of the victim's core
> cells it still owns after this write.
>
> **Source.** as `HOSTILE_WRITE`, plus core membership from tick-0 diffs
> (cross-checked against each entrant's own reported `own_core_base` /
> `own_core_size`). **Visible to.** `()`.

This exists because it is the only event that *explains* an elimination.
`apply_core_capture` kills an entrant when it owns zero cells of its core, so
`remaining_core_cells` counting to zero is the mechanism, visible in the stream
(§13).

### 6.5 `PROCESS_DISRUPTED`

> **Definition.** An applied `WRITE` on a cell where a live enemy process is
> currently anchored, for a process not already disrupted this tick.
>
> **Source.** trace `WRITE` decisions against a per-process anchor timeline
> reconstructed from applied `MOVE` results. **Visible to.** `()`.

Attribution is exact, and better than replay-only attribution can be. Phase 1
matches disrupted processes against the tick's end-of-tick anchor and falls
back to an "ambiguous" attribution when more than one opponent wrote there.
Reconstructing the anchor timeline instead means a victim that moved onto or
off the address earlier in the same tick is attributed to the write that
actually hit it. The reconstruction is validated against the replay's
`disrupted` flags every tick.

Only the *transition* is an event. The engine re-arms the timer on every
further hit inside the tick and its telemetry counts each one, but the process
is already out of action; emitting one event per hit would report a single
suppression as up to eight identical moments per tick.
`test_process_disruption_is_attributed_to_the_write_that_caused_it` asserts at
most one event per (tick, victim process).

### 6.6 `EFFECTIVE_MOVE`

> **Definition.** A process whose anchor at the end of tick T differs from its
> anchor at the end of tick T−1. **Visible to.** the moving entrant.

Coalesced to the tick boundary deliberately. In the `OSCILLATOR` fixture, 48
executed `MOVE` actions collapse to **two** events, because both processes end
every tick after the first exactly where they started. Per-action movement is
engine detail; "this process is somewhere else now" is the spectator fact, and
it is the one the replay's own per-tick anchor snapshot agrees with.

**Limitation:** this is the vocabulary's highest-volume, lowest-salience kind
(259 of 831 corpus events, 31%). It is retained because Fog of War needs it and
because it is the material §17 uses to show that motion is not mistaken for
drama — but a director must weight it accordingly.

### 6.7 `AGENT_ELIMINATED`, `AGENT_FORFEITED`, `MATCH_ENDED`, `VICTORY`

Direct restatements of the replay's own `kill`/`death`/`forfeit` tick events
and its result record, in the replay's own order. `AGENT_ELIMINATED` carries
the engine's kill attribution when `_attribute_core_capture` determined one
unambiguously, and no attribution otherwise — Phase 3 does not guess.

`VICTORY` is **ACCEPT WITH LIMITATION**: it is emitted only when the replay
result names a winner. A tie stores `winner: null` and yields `MATCH_ENDED`
alone. Ten of the twelve corpus matches are ties, so this is the common case,
not an edge case.

*(Note on the deferred `AGENT_CRITICAL`: `remaining_core_cells` on
`CORE_CELL_LOST` is the objective quantity such an event would need. The
threshold is still editorial, so it stays deferred — but the raw material now
exists.)*

---

## 7. Ordering and identity rules

Event identity is `(tick, sequence)`. `sequence` is the zero-based position
among the events derived for that tick, assigned in one fixed construction
order. No UUIDs, no timestamps, no counters derived from anything but canonical
ordering.

Within a tick, in order:

1. **Events anchored to a trace decision**, sorted by `(decision position in
   the trace file, sub-order)`. Sub-order is
   `DETECTION_GAINED(0) < HOSTILE_READ(1) < FIRST_HOSTILE_READ(2) <
   HOSTILE_WRITE(3) < FIRST_HOSTILE_WRITE(4) < CORE_CELL_LOST(5) <
   PROCESS_DISRUPTED(6)` — the observation the engine delivered precedes the
   action the agent returned, and an action's consequences follow the order the
   engine applies them.
2. **Tick-boundary events**: `EFFECTIVE_MOVE` sorted by `(entrant, process)`,
   then `DETECTION_LOST` sorted by entrant, then the replay's own tick events
   in the replay's own order.
3. **Terminal events** `MATCH_ENDED` then `VICTORY`, appended to the final
   tick's sequence run.

**Detection and hostile action on the same tick.** `DETECTION_GAINED` is
anchored to the exact decision whose observation first carried the address, so
it orders *before* the hostile action that detection enabled — visible in §13's
walkthrough, where A's detection at tick 1 precedes its first hostile write in
the same tick. `DETECTION_LOST` cannot be anchored that way: it is evidenced by
absence across the whole tick, so it sits at the boundary. The asymmetry is
deliberate and documented.

**Simultaneity.** Simultaneous disruptions are ordered by the writes that
caused them (trace order), then by victim. Simultaneous eliminations follow the
replay's own event order, which is entrant-state order in `apply_core_capture`.
Multiple entrants acting on one tick interleave exactly as the scheduler ran
them, because trace order *is* execution order.

**Terminal-event identity.** `MATCH_ENDED`/`VICTORY` carry `result.ticks`,
which is the final tick's number. They therefore continue that tick's sequence
run rather than restarting at 0 — otherwise `(tick, sequence)` would collide
with events already derived there. §13's walkthrough shows the terminal events
at sequence 16 and 17 of tick 2.
`test_event_identity_is_unique_and_contiguous_within_every_tick` asserts
uniqueness, contiguity from 0, and global ordering.

**Forbidden inputs.** No ordering depends on dict insertion, set iteration,
hash values, wall-clock time, filesystem order, or process identity. Every
ordering is either trace file position or an explicit `sorted()` on a total key
of strings and integers. `wall_time_ms` and diagnostic message text — the
trace's two declared nondeterministic fields — are never read into an event.

### 7.1 An ordering limitation worth recording

`DecisionRecordV2` carries **no `action_slot` field**, although the API-v1
`DecisionRecord` does. Intra-tick execution order is therefore carried *only*
by a record's position in the trace file. That is deterministic and this
analyzer preserves it, but it means the trace's decision records cannot be
re-ordered, deduplicated, stored in a set, or merged from multiple sources
without losing information. A future phase that wants order-independent
decision records should add an explicit intra-tick ordinal to the schema.

---

## 8. Perspective / visibility model

`visible_to` names the entrants the v4 engine actually informs. An **empty**
`visible_to` means no entrant is told — the fact is omniscient-only. It never
means "unknown". Serialization always emits the field, including when empty, so
a consumer can tell "nobody knows" from "not stated".

Measured across the whole corpus:

| Event kind | Ever names an entrant? |
|---|---|
| `DETECTION_GAINED`, `DETECTION_LOST` | the observing entrant |
| `HOSTILE_READ`, `FIRST_HOSTILE_READ` | the reading entrant |
| `EFFECTIVE_MOVE` | the moving entrant |
| `HOSTILE_WRITE`, `FIRST_HOSTILE_WRITE` | **nobody** |
| `CORE_CELL_LOST` | **nobody** |
| `PROCESS_DISRUPTED` | **nobody** |
| `AGENT_ELIMINATED`, `AGENT_FORFEITED` | **nobody** |
| `MATCH_ENDED`, `VICTORY` | **nobody** |

Eight of thirteen kinds are omniscient-only. This is provable by exhaustion
rather than by sampling: `ObservationV2` has exactly twelve fields —
`current_tick`, `last_callback_tick`, `previous_action_tick`,
`self_process_id`, `self_anchor`, `self_reach`, `own_core_base`,
`own_core_size`, `visible_enemy_anchor_addresses`, `previous_action_applied`,
`previous_read_value`, `previous_read_owner` — and it is the *entire* surface
through which a v4 entrant learns anything. Nine of those describe the
entrant's own identity, position, and last action; two report the result of its
own last `READ`; one reports occupied addresses. **None** reports an incoming
write, an ownership change to the entrant's own cells, a disruption, or another
entrant's death.

Stated plainly: **v4 entrants are told almost nothing about being attacked.** A victim is not told its cell was
overwritten, that it lost a core cell, that one of its processes was
suppressed, or that an opponent died.
`test_a_victim_is_never_told_its_cell_or_process_was_attacked` and
`test_no_event_ever_tells_an_entrant_something_the_engine_withheld` assert this
across two independent fixtures, and the latter also asserts that every
entrant-visible event's audience is a subset of its own actors — no event ever
informs a bystander.

### 8.1 Detection carries addresses, never targets

`_visible_enemy_anchors` returns bare sorted addresses. Co-located enemies
collapse to one occupied address; identities and structural metadata stay
private. `DETECTION_GAINED`/`DETECTION_LOST` therefore populate `addresses` and
leave `targets` empty. Naming which opponent was detected would be exactly the
Phase 1 leak described in §5.2.

### 8.2 What an entrant can and cannot infer

Distinguishing delivered knowledge from inference matters, because the boundary
is where a Fog Cam would start lying.

| Fact | Delivered? | Inferable? |
|---|---|---|
| An enemy occupies address X | **Yes** — in the observation | — |
| Which enemy occupies X | No | No |
| The byte and owner at an address I read | **Yes** — `previous_read_value` / `previous_read_owner` | — |
| My own action applied | **Yes** — `previous_action_applied` | — |
| Whose cell I overwrote | No | Only by reading it first |
| My cell was overwritten | No | Only by reading it again |
| One of my processes was disrupted | No | **Partly** — a gap between `last_callback_tick` and `current_tick` shows a lost callback, but the engine never states the cause |
| An opponent was eliminated | No | **Partly** — the opponent's anchors leave my visible set, which is indistinguishable from it moving out of range |

The two "partly" rows are correlation, not causation, and Phase 3 does not
promote either into an event. A future Fog phase may model an entrant's
*beliefs* separately, but it must not present an inference as a delivered fact.

### 8.3 A field-fidelity observation

`ObservationV2.last_callback_tick` and `previous_action_tick` are populated from
the same source value in `process_runtime.py`, so they are always equal in
practice. The spec (§5) lists them as distinct fields. This is not a Phase 3
blocker — neither is used in derivation — but it should be reconciled: either
give them distinct meanings or collapse them.

---

## 9. Granularity resolution

The brief asked which level semantic derivation belongs at. The answer is
**both, split by what the fact is about**:

| Fact is about … | Granularity | Why |
|---|---|---|
| an entrant's **knowledge** | per (entrant, tick), union | Visibility is entrant-wide and re-sampled per callback; per-decision comparison produces intra-tick noise (§6.1) |
| a specific **action's effect** | per decision | The engine applied it at an exact point in an exact order; coalescing would destroy attribution |
| a process's **position** | per (process, tick), net | Per-action movement is engine detail, and the replay agrees at tick boundaries |
| **match lifecycle** | per tick / at result | The replay states it at that granularity |

"One decision = one spectator moment" is explicitly rejected. 5,779 decision
records across the corpus produced 831 events — a 7.0× reduction, and a much
larger one for the matches where it matters (the `high_volume` scenario reduces
480 decisions to 1 event).

---

## 10. Analyzer architecture

`engine/src/battle_engine/spectator_derivation.py`, with
`tools/spectator_derive.py` as the source-checkout wrapper — deliberately
mirroring Phase 1's `spectator_events.py` / `tools/spectator_analyzer.py`
convention rather than adding a `bytefray` subcommand. The `bytefray` command's
`COMMANDS` tuple is a public surface; §22 of the brief calls for avoiding
premature public API commitments, and this remains alpha research.

```
verify_pair(replay, trace) -> PairBinding          # binding + identity cross-check
        │
derive_events(binding) -> SpectatorDerivation      # per-tick reconstruction + cross-check
        │
serialize_derivation() / explain_derivation()      # JSONL / auditable walkthrough
```

`analyze_pair(replay, trace)` composes the first two. Holding a `PairBinding` is
the type-level proof that verification happened: `derive_events` takes one and
cannot be handed raw paths.

What was deliberately **not** built: no event bus, no plugin system, no async,
no observer hierarchy, no broker, no persistence layer, no public extension
API, no abstraction for a future commentator. Two frozen dataclasses
(`SpectatorEvent`, `Provenance`), one enum, one derivation function.

CLI:

```
python tools/spectator_derive.py REPLAY.jsonl TRACE.jsonl [--provenance] [--explain] [--verify-only]
```

Default output is JSONL: one header record, one flat record per event, one
result record. Flat-per-event rather than Phase 1's tick-grouped shape, because
a stream is what a director or commentator consumes and what diffs cleanly for
determinism checks. Exit code 2 with a message on stderr and **no stdout** for
any binding or consistency failure.

---

## 11. Provenance

`--provenance` attaches a rule name, source artifact, source record index, and
before/after state to every event; `--explain` renders the same as a
walkthrough. Real output:

```
Tick:        1  (sequence 0)
Event:       DETECTION_GAINED
Actors:      A
Addresses:   [32]
Visible to:  A
Derived from:
  rule:      detection_union_per_entrant_tick
  source:    trace record #4
  before:    visible=[]
  after:     visible=[32]

Tick:        1  (sequence 1)
Event:       HOSTILE_WRITE
Actors:      A
Targets:     B
Process:     axe
Address:     33
Visible to:  omniscient only
Derived from:
  rule:      applied_write_over_foreign_ownership
  source:    trace record #13
  before:    owner[33]=B
  after:     owner[33]=A

Tick:        1  (sequence 3)
Event:       CORE_CELL_LOST
Actors:      A
Targets:     B
Process:     axe
Address:     33
Visible to:  omniscient only
Derived from:
  rule:      applied_write_over_victim_core_cell
  source:    trace record #13
  before:    B core cells owned=8/8
  after:     B core cells owned=7/8
```

`record_index` indexes `TraceDocumentV2.decisions` directly, so a reviewer can
open the trace at that record and check the claim.
`test_provenance_points_at_a_trace_record_that_supports_the_event` does exactly
that mechanically: it dereferences the index and asserts the record's agent,
action kind, and normalized address match the event derived from it.

---

## 12. Representative match corpus

Twelve real deterministic matches, built from small agents (none longer than
twelve lines) using existing repository infrastructure only.

| Scenario | Shape | Winner | Ticks | Decisions | Events |
|---|---|---|---:|---:|---:|
| `no_contact` | two hermits, arena 128 | tie | 40 | 640 | 1 |
| `immediate` | seeker vs. turtle, contact by tick 2 | tie | 25 | 304 | 44 |
| `oscillating` | intra-tick visibility flapping | tie | 12 | 192 | 4 |
| `one_sided` | reaper vs. hermit | tie | 60 | 666 | 246 |
| `competitive` | two seekers, never in range | tie | 50 | 800 | 201 |
| `very_short` | two-tick match | tie | 2 | 32 | 7 |
| `longer` | 120 ticks, repeated interaction | tie | 120 | 1,448 | 173 |
| `forfeit` | scripted crash on tick 4 | B | 4 | 57 | 7 |
| `high_volume` | max write rate, zero aggression | tie | 30 | 480 | **1** |
| `three_way` | multi-event ticks, arena 96 | tie | 40 | 488 | 63 |
| `elimination` | core capture ends the match | **A** | 2 | 32 | 23 |
| `contact_window` | detection opens and closes five times | tie | 40 | 640 | 61 |
| **Total** | | | | **5,779** | **831** |

Coverage against the brief's requested cases: no contact for a substantial
period ✓, immediate contact ✓, repeated detection gain/loss ✓, hostile READ ✓,
hostile WRITE ✓, process death ✗ *(no engine mechanic — the finding itself)*,
entrant elimination ✓, very short match ✓, longer match ✓, one-sided ✓,
competitive ✓, multiple significant events on one tick ✓ (18 on
`elimination` tick 2), high write activity with low strategic importance ✓,
match ending without every candidate event occurring ✓ (10 of 12).

**Every one of the thirteen accepted kinds is produced by at least one real
match.** Three further shapes were verified beyond the corpus, all passing the
per-tick state cross-check: 3- and 4-entrant matches
(`test_derivation_holds_for_more_than_two_entrants` — where the four entrants
resolve into two independent simultaneous fights, A↔B and C↔D, with no
attribution bleeding between them), matches where an entrant's core region
wraps the end of the arena
(`test_derivation_handles_a_core_region_that_wraps_the_arena_end`), and a
3,000-tick / 36,064-decision match on a 1,024-cell arena (§19.9).

Corpus event totals: `EFFECTIVE_MOVE` 259, `PROCESS_DISRUPTED` 150,
`HOSTILE_WRITE` 175, `HOSTILE_READ` 96, `CORE_CELL_LOST` 94,
`DETECTION_GAINED` 18, `MATCH_ENDED` 12, `DETECTION_LOST` 10,
`FIRST_HOSTILE_WRITE` 9, `FIRST_HOSTILE_READ` 4, `VICTORY` 2,
`AGENT_ELIMINATED` 1, `AGENT_FORFEITED` 1.

---

## 13. End-to-end walkthrough

`elimination`: an executioner walks until it detects an opponent, then strips
that opponent's eight core cells. The whole match is two ticks and 32 decision
records, so the entire stream can be asserted exactly — which
`test_core_capture_match_derives_the_exact_expected_event_stream` does,
comparing all 23 events field by field.

```
t=1 s= 0 DETECTION_GAINED    actors=[A]            addresses=[32]  visible_to=[A]
t=1 s= 1 HOSTILE_WRITE       actors=[A] targets=[B] addr=33         visible_to=[]
t=1 s= 2 FIRST_HOSTILE_WRITE actors=[A] targets=[B] addr=33         visible_to=[]
t=1 s= 3 CORE_CELL_LOST      actors=[A] targets=[B] addr=33 rem=7   visible_to=[]
t=1 s= 4 EFFECTIVE_MOVE      actors=[A]  axe 0 -> 28                visible_to=[A]
t=2 s= 0 HOSTILE_WRITE       actors=[A] targets=[B] addr=34         visible_to=[]
t=2 s= 1 CORE_CELL_LOST      actors=[A] targets=[B] addr=34 rem=6   visible_to=[]
t=2 s= 2 HOSTILE_WRITE       actors=[A] targets=[B] addr=35         visible_to=[]
t=2 s= 3 CORE_CELL_LOST      actors=[A] targets=[B] addr=35 rem=5   visible_to=[]
        ... addresses 36, 37, 38, 39 ...
t=2 s=12 HOSTILE_WRITE       actors=[A] targets=[B] addr=32         visible_to=[]
t=2 s=13 CORE_CELL_LOST      actors=[A] targets=[B] addr=32 rem=0   visible_to=[]
t=2 s=14 PROCESS_DISRUPTED   actors=[A] targets=[B] addr=32  proc=z visible_to=[]
t=2 s=15 AGENT_ELIMINATED    actors=[A] targets=[B] cause=kill      visible_to=[]
t=2 s=16 MATCH_ENDED         termination_reason=last_agent_standing visible_to=[]
t=2 s=17 VICTORY             actors=[A]                             visible_to=[]
```

The countdown `rem=7,6,5,4,3,2,1,0` is the derivation's own arithmetic checked
against the mechanic that ends the match, and the final write is simultaneously
a core capture and an anchor hit — one action producing three ordered events.

### 13.1 Source record → event, per accepted kind

| Event | Source | Verified by |
|---|---|---|
| `DETECTION_GAINED` | trace decision #4: `A/axe` observation contains `32`; A's previous union was `∅` | `test_detection_and_hostile_read_events_carry_engine_delivered_values`, `..._provenance_points_at_a_trace_record...` |
| `DETECTION_LOST` | `contact_window`: A's tick-4 union no longer contains B's anchor | `test_detection_lost_is_emitted_when_contact_genuinely_ends` (asserts all 11 transitions with ticks and entrants) |
| `HOSTILE_READ` | trace decision with `read_owner="B"`, `read_value=0xCE`, `normalized_address=32` | `test_applied_read_records_the_owner_and_value_the_engine_returned`, `test_detection_and_hostile_read_...` |
| `FIRST_HOSTILE_READ` | the earliest such record for (A, B), tick 2 | same |
| `HOSTILE_WRITE` | trace decision #13: applied write at 33; reconstructed `owner[33]=B` | `test_hostile_write_names_the_owner_it_displaced` |
| `FIRST_HOSTILE_WRITE` | asserted to sit on each attacker's earliest hostile write | same |
| `CORE_CELL_LOST` | same record; 33 ∈ B's core; `remaining=7` | `test_core_capture_match_derives_the_exact_expected_event_stream` |
| `PROCESS_DISRUPTED` | applied write at 32 where `B/z` is anchored | `test_process_disruption_is_attributed_to_the_write_that_caused_it` |
| `EFFECTIVE_MOVE` | reconstructed anchor 0 → 28, equal to the replay's tick-1 snapshot | `test_effective_move_reports_net_anchor_change_not_each_action` |
| `AGENT_ELIMINATED` | replay tick-2 `kill` event, victim B, killer A | `test_core_capture_...` |
| `AGENT_FORFEITED` | replay tick-3 `forfeit`, reason `agent_action_invalid` | `test_forfeit_is_reported_with_its_engine_reason_and_the_resulting_victory` |
| `MATCH_ENDED` | replay result, `termination_reason=last_agent_standing` | `test_core_capture_...` |
| `VICTORY` | replay result, `winner=A` | `test_core_capture_...`, `test_forfeit_...` |

---

## 14. Repeated-run determinism

| Check | Scope | Result |
|---|---|---|
| Re-derive from identical artifacts | 12 scenarios × 3 | **Identical** stream digest every time |
| Re-execute identical match inputs, then re-derive | 12 scenarios × 3 (36 executions) | Winner, tick count, replay digest, trace **semantic** digest, and derived stream all **identical** |
| Fresh interpreters under `PYTHONHASHSEED` 0 / 1 / 12345 | 12 scenarios × 3 seeds | **Identical** stream digests across all seeds |

The trace semantic digest deliberately excludes `wall_time_ms` and diagnostic
message text — the spec's declared nondeterministic fields — and covers agent,
process, tick, anchor, visible addresses, action, applied result, and
diagnostic *code*. Those are the fields semantics depend on.

`test_repeated_derivation_over_identical_inputs_is_byte_identical`,
`test_repeated_execution_of_one_match_yields_one_semantic_stream`, and
`test_derivation_is_stable_across_python_hash_seeds` (which spawns real
subprocesses with the environment variable set) carry this in the suite.

---

## 15. Simulation isolation

Twelve scenarios executed twice each — once with `trace_path=None`, once with
tracing enabled — comparing canonical outcome and identity:

| Compared | Result |
|---|---|
| Winner | **SAME**, 12/12 |
| Termination reason | **SAME**, 12/12 |
| Tick count | **SAME**, 12/12 |
| Replay SHA-256 | **SAME**, 12/12 |
| `result.json` `result_id` | **SAME**, 12/12 |

`test_tracing_and_analysis_do_not_change_the_canonical_match` carries this,
and strengthens Phase 2's equivalence test in two ways: it compares the
canonical `result_id` (the identity hash over winner, termination, ticks,
score, and entrant state) rather than only the replay digest, and it asserts
that running the analyzer leaves both artifacts byte-identical. The analyzer
opens both files read-only and consumes completed artifacts; it has no path
into match execution.

---

## 16. Fog of War readiness

**GO WITH PREREQUISITES.**

Can we distinguish the four categories?

| Category | Distinguishable? | How |
|---|---|---|
| Omniscient event | **Yes** | `visible_to == ()` |
| Entrant-visible event | **Yes** | `visible_to` names the entrant, from delivered observations |
| Entrant-hidden event | **Yes** | An omniscient event whose `targets` name that entrant |
| Previously-known-but-now-stale | **Partly** | `DETECTION_LOST` marks when contact ended; the layer does not model retained belief |

The observation stream is sufficient for perspective projection of detection
and own-action outcomes. It is *not* sufficient for anything else — eight of
thirteen kinds are omniscient-only, which is a fact about v4, not a gap in the
trace.

**Prerequisites, in priority order:**

1. **Fog must be driven by the trace, not by replay geometry.** §5.2 is the
   blocking finding: replay-only reconstruction both misses real contact and
   reveals it a tick early. Phase 1's `_visible_pairs` must not be the basis of
   a Fog Cam.
2. **Phase 1's detection events must stop asserting `target_entrant_id`,** or
   be superseded. That field is omniscient information.
3. **Decide how to render sampled knowledge continuously.** An entrant's
   knowledge is sampled at callback boundaries; a Fog Cam renders continuously.
   Interpolating between samples invents knowledge. Holding the last sample is
   defensible and must be an explicit decision.
4. **Decide the belief model.** Detection is *current contact*, not memory. A
   Fog Cam showing only current contact will look strange (enemies vanish the
   instant they step out of reach), but showing remembered positions means
   modelling belief, which the engine does not supply. This is a design
   decision, not a derivation problem.
5. **Handle unsampled ticks explicitly in the UI.** A fully-disrupted entrant
   learns nothing for a tick. Rendering that as "sees nothing" would be wrong.

Not a blocker but worth resolving: the `last_callback_tick` /
`previous_action_tick` duplication (§8.3).

---

## 17. Spectator Director / dynamic pacing readiness

**GO WITH PREREQUISITES.** No pacing was implemented and no TPS values chosen.

Event density and mix from the corpus:

| Scenario | Ticks | Events | Events/tick | Hostile | Moves | Busiest tick |
|---|---:|---:|---:|---:|---:|---|
| `high_volume` | 30 | 1 | 0.03 | 0 | 0 | — |
| `no_contact` | 40 | 1 | 0.03 | 0 | 0 | — |
| `oscillating` | 12 | 4 | 0.33 | 0 | 2 | 3 |
| `longer` | 120 | 173 | 1.44 | 168 | 3 | 6 |
| `contact_window` | 40 | 61 | 1.52 | 0 | 40 | 3 |
| `three_way` | 40 | 63 | 1.57 | 58 | 3 | 6 |
| `immediate` | 25 | 44 | 1.76 | 39 | 3 | 6 |
| `competitive` | 50 | 201 | 4.02 | **0** | 200 | 5 |
| `one_sided` | 60 | 246 | 4.10 | 243 | 1 | 9 |
| `elimination` | 2 | 23 | 11.50 | 18 | 1 | **18** |

The four director states separate cleanly — but on **event type**, not volume:

- **Build-Up** — `no_contact`, `high_volume`, `oscillating`: 0.03–0.33
  events/tick, zero hostile.
- **Suspense** — the tick a `DETECTION_GAINED` lands, and the ticks between it
  and first hostile contact. `contact_window` is entirely this: five detection
  windows, zero hostile events.
- **Brawl** — `one_sided`, `longer`, `immediate`: sustained hostile events over
  many ticks.
- **Major Event** — `CORE_CELL_LOST` with a low `remaining_core_cells`,
  `AGENT_ELIMINATED`, `VICTORY`. `elimination` tick 2 carries 18 events ending
  in a kill.

**Could high-frequency harmless activity falsely appear dramatic?** Directly
tested, and the answer is **no** — provided the director reads types.

- `high_volume` runs 480 decisions and 3,416 writes at maximum rate for 30
  ticks and produces **one** event, because every write lands on the writer's
  own core. Raw write volume would have scored it as the busiest match in the
  corpus; the semantic layer scores it as nothing happening.
- `competitive` produces 201 events at 4.02/tick — a density identical to the
  bloodiest match, `one_sided` (4.10/tick) — but **every one is an
  `EFFECTIVE_MOVE` and none is hostile.** Two agents circling in parallel, never
  in range.

So density alone is not a drama signal; density **partitioned by kind** is.
`competitive` versus `one_sided` is the decisive pair: identical rate, opposite
meaning.

**Prerequisites:**

1. Weight by kind, never by raw count, and never by write volume.
2. Decide whether `EFFECTIVE_MOVE` reaches the director at all. It is 31% of
   corpus events and carries almost no drama except as an approach signal.
3. Detection is the only usable **anticipatory** signal — `DETECTION_GAINED`
   precedes contact. A director that reacts only to hostile events will always
   be late.
4. The vocabulary has no "nothing is happening for a long time" event. Long
   quiet stretches must be inferred from absence, which is a director concern.
5. Match length varies by two orders of magnitude (2 to 120 ticks in a small
   corpus). Pacing cannot assume a duration.

---

## 18. Color Commentator implications

Not implemented, as instructed. The vocabulary's suitability as commentary
material:

| Event | Commentatable? |
|---|---|
| `DETECTION_GAINED` / `DETECTION_LOST` | **Yes** — but only as "A has picked something up at 412", never "A has spotted B". The identity is not A's to know. |
| `FIRST_HOSTILE_READ` | **Yes** — genuine narrative beat, and correctly attributed. |
| `FIRST_HOSTILE_WRITE` | **Yes** — first aggression. |
| `CORE_CELL_LOST` | **Yes** — `remaining_core_cells` gives a natural stakes counter. |
| `AGENT_ELIMINATED` / `VICTORY` | **Yes.** |
| `PROCESS_DISRUPTED` | **Aggregated only** — 150 corpus occurrences, often every other tick. |
| `HOSTILE_READ` / `HOSTILE_WRITE` | **Aggregated only** — 271 combined; individually too low-level. |
| `EFFECTIVE_MOVE` | **Probably not** individually — 31% of all events. |
| raw `DecisionRecordV2` | **No** — this is what the semantic layer exists to avoid. |

The critical constraint: a commentator consuming this layer **must respect
`visible_to`**, or it will narrate an entrant's situation using knowledge that
entrant does not have — the audio equivalent of the Phase 1 leak. Since eight
of thirteen kinds are omniscient-only, an omniscient commentator is
straightforward and an in-character one is heavily constrained.

---

## 19. Remaining uncertainties

1. **Phase 1 and Phase 3 now derive overlapping semantics differently.**
   `spectator_events` (replay-only) and `spectator_derivation` (pair) disagree
   on detection, and use different names for disruption. Both ship. This must
   be reconciled before either is presented as *the* spectator layer; Phase 3
   deliberately did not rewrite Phase 1 mid-phase.
2. **Belief and staleness are unmodelled.** The layer reports current contact,
   not what an entrant remembers.
3. **Sampled knowledge is not continuous knowledge.** Contact entirely between
   two callbacks is invisible here — correctly, but a renderer must decide what
   to draw.
4. **`EFFECTIVE_MOVE` volume is unresolved.** Objectively correct, 31% of
   events, low salience.
5. **`DecisionRecordV2` has no intra-tick ordinal** (§7.1).
6. **`last_callback_tick` and `previous_action_tick` are always equal** (§8.3).
7. **Multi-entrant coverage is verified but not corpus-scale.** 3- and
   4-entrant matches pass; the twelve-match corpus is all duels.
8. **Ambiguous kill attribution is untested end-to-end.** The engine can record
   an unattributed `death`; no corpus match produced one.
9. **Performance is adequate but only single-point-measured.** Measured at
   near-worst-case scale (arena 1024, 3,000 ticks, **36,064 decisions**, a
   21.5 MiB trace — against the spec's ~48,000-decision worst case):
   `verify_pair` 0.74 s, `derive_events` 0.98 s, ~36,800 decisions/s, producing
   17,927 events. Match execution itself took 2.46 s, so offline derivation
   costs less than half of running the match. All three per-tick consistency
   cross-checks held across all 3,000 ticks. This is one measurement on one
   host, not a performance characterization.
10. **`CORE_CELL_LOST` assumes non-overlapping cores.** Core membership comes
    from tick-0 ownership; overlapping cores would mis-attribute. Placement
    validation appears to prevent this, and `_check_core_declaration` would
    catch a size mismatch, but it was not tested adversarially.

---

## 20. Test results

Exact counts. `engine/tests/` is **not** the full suite — the repository's
`pytest.ini` configures three `testpaths` (`_legacy/tests`, `engine/tests`,
`client/tests`), and that distinction is preserved here.

| Group | Result |
|---|---|
| Phase 3 focused (`test_v4_spectator_derivation.py`) | **35 passed** |
| Phase 1 spectator regressions (`test_spectator_aggregation.py` + `test_spectator_analyzer.py`) | **39 passed** (11 + 28) |
| Phase 2 trace regressions (`test_v4_trace_equivalence.py` + `test_agent_trace.py`) | **19 passed** (2 + 17) |
| Replay/schema-4 (`test_replay_reconstruction.py` + `test_replay_contract.py`) | **29 passed** |
| `engine/tests/` (all) | **2,309 passed, 14 skipped, 0 failed** |
| **True full repository suite** (all three `testpaths`) | **2,687 passed, 26 skipped, 2 deselected, 0 failed** |
| `ruff check .` | **clean, repo-wide** |
| `mypy engine/src/battle_engine` | **clean, 98 source files** (97 at Phase 2 + `spectator_derivation.py`) |
| `mypy client/src/battle_client` | **clean, 12 source files** |

Collection across the three configured `testpaths` totals **2,715** tests, of
which 2,713 are selected and 2 are deselected by `pytest.ini`'s
`-m "not gui"`.

Both suite figures were produced twice and agree exactly: once with
`-p no:cacheprovider` (used while sequencing runs, to keep the pytest cache out
of the way) and once under the repository's stock configuration with no flags
at all. `engine/tests/` reported 2,309 passed / 14 skipped both times, and the
full suite 2,687 passed / 26 skipped / 2 deselected both times, so nothing in
these numbers depends on how the run was invoked.

### Explaining the 2 deselected tests

Phase 2's report recorded 0 deselected and concluded that "no test in the
current tree currently carries the `gui` marker", filing the difference from
its own baseline as unexplained drift. That conclusion is incorrect, and the
correction is cheap: `client/tests/test_linux_pygame_smoke.py` carries
`@pytest.mark.gui` at lines 8 and 36. Those two tests are the deselection, they
are inside a configured `testpath`, and they are excluded by design (the
display-backed tests run in the dedicated X11 workflow, as `pytest.ini`'s own
comment says).

Measured directly: `pytest --collect-only` reports `2713/2715 tests collected
(2 deselected)`, and the same command with the marker filter removed reports
`2715 tests collected`. The deselection is stable and explained, not drift.
Nothing about it relates to Phase 3 — the large body of `@pytest.mark.gui`
tests under the repository-root `tests/` directory is never collected at all,
because `tests/` is not one of the configured `testpaths`.

Following this repository's rule against editing historical research reports in
place, Phase 2's document is left exactly as written; this is the correction
record.

### Explaining the test-count change

Phase 2's qualified baseline was **2,274 passed / 14 skipped** in
`engine/tests/` and **2,652 passed / 26 skipped** across the true full suite.
Phase 3 adds exactly **35** tests, all in the new
`engine/tests/test_v4_spectator_derivation.py`. No existing test was modified,
renamed, or removed, and no skip was added. The arithmetic closes exactly:

| | Phase 2 baseline | + Phase 3 | Phase 3 measured |
|---|---:|---:|---:|
| `engine/tests/` passed | 2,274 | +35 | **2,309** ✅ |
| `engine/tests/` skipped | 14 | +0 | **14** ✅ |
| Full suite passed | 2,652 | +35 | **2,687** ✅ |
| Full suite skipped | 26 | +0 | **26** ✅ |
| Full suite selected | 2,678 | +35 | **2,713** ✅ |

### A process note on how these numbers were obtained

An earlier attempt at this run produced 7 failures, including in v3 locality
tests that Phase 3 does not touch. Those were **not** real: `pytest.ini` sets
`--basetemp=.pytest-tmp`, and a second pytest invocation was started while the
suite was already running, so the two collided on that directory
(`FileExistsError: Cannot create a file when that file already exists:
'.pytest-tmp'`). The run was discarded and every figure above comes from a
clean sequential re-run with nothing else touching the repository. It is
recorded here rather than quietly dropped, because a reader comparing
intermediate output against this table would otherwise see a discrepancy with
no explanation — and because "concurrent pytest invocations share
`.pytest-tmp`" is a real constraint for anyone re-running this qualification.

---

## 21. Hostile self-review

Working through the brief's own list, with the uncomfortable answers kept.

**Is this code actually exercised?** Yes. Every accepted kind is produced by at
least one real match, and the derivation's internal cross-check runs on every
tick of every analysed match — a derivation that stopped early would fail the
anchor comparison.

**Can a test pass while the feature never runs?** The Phase 2 failure mode was
specifically guarded against. `test_core_capture_match_derives_the_exact_
expected_event_stream` asserts all 23 events by value.
`test_intra_tick_visibility_oscillation...` and
`test_a_tick_with_no_callbacks...` each first *prove the precondition exists* in
the real trace, then assert the derivation's response — so they fail if the
mechanic changes as well as if the rule breaks.

**Are events derived from actual matches or hand-built objects?** Actual
matches, exclusively. There is not one hand-constructed `DecisionRecordV2` in
the test file. The only synthetic data is deliberately corrupted artifacts for
the rejection tests.

**Are perspective rules leaking omniscient information?** Not in Phase 3, and
this is asserted rather than asserted-by-comment. Phase 1 **is** leaking; that
is finding §5.2 and it is reported, not worked around.

**Are we calling something causal when we only know correlation?** Checked
carefully. `PROCESS_DISRUPTED` attribution is causal by reconstruction of the
engine's own rule, validated against the replay's flags. `AGENT_ELIMINATED`
carries the engine's own attribution or none. The two genuinely correlational
signals — an entrant inferring a lost callback, or inferring a death from
vanished anchors — are documented in §8.2 and deliberately **not** promoted
into events.

**Are ordering rules dependent on incidental Python ordering?** No. Verified by
reading every ordering site and by running under three `PYTHONHASHSEED` values
in fresh interpreters.

**Did we create semantics because they sound useful?** `CORE_CELL_LOST` is the
one worth interrogating — it was not on the brief's strong list. It is retained
because it is the only event that explains an elimination, it is derived from
ownership and core membership the artifacts state outright, and it carries a
counter (`remaining_core_cells`) that is exactly the engine's own kill
condition. `FIRST_BLOOD`, `LARGE_OVERWRITE`, and `AGENT_CRITICAL` all failed
the same test and were deferred.

**Did we alter canonical execution?** No. `process_runtime.py`,
`match_service.py`, `replay.py`, and `vm.py` are untouched. §15 measures the
consequence.

**Are we confusing trace diagnostics with deterministic semantic data?**
`wall_time_ms` and diagnostic message text are never read into an event. Only
the diagnostic *code* appears, via the replay's forfeit event.

**Can replay and trace from different matches be analyzed together?** No —
binding verification rejects it, and the state cross-check catches a doctored
trace that survives binding.

**Are tests proving meaningful values?** The suite contains no bare
`assert len(events) > 0`. Where a non-emptiness guard appears it is a
precondition preceding a value assertion.

**Uncomfortable answers kept as findings rather than worked around:** Phase 1's
two detection defects (§5.2); `PROCESS_CREATED`/`PROCESS_DEATH` having no
engine support at all (§5.1); eight of thirteen events being visible to nobody
(§8); the trace lacking an intra-tick ordinal (§7.1); the canonical replay
digest being platform-dependent (§4.1); two `ObservationV2` fields being
duplicates (§8.3).

---

## 22. Roadmap reassessment

| Component | Classification | Reasoning |
|---|---|---|
| **Semantic Spectator Event Layer** | **GO** | Built, qualified, deterministic, evidenced end-to-end on real matches. Reconcile with Phase 1 (§19.1). |
| **Fog of War Cam** | **GO WITH PREREQUISITES** | Feasible from the trace, but only from the trace. Five prerequisites in §16, one of which invalidates the obvious replay-based implementation. |
| **Spectator Director / Dynamic Pacing** | **GO WITH PREREQUISITES** | The four states separate on event type; type-blind or volume-based pacing demonstrably fails (§17). |
| **Fight Night Presentation** | **REVISE CONCEPT** | Not for lack of telemetry — because v4 has **no process creation or death**. Presentation built around processes spawning and dying has no mechanic behind it. What v4 actually offers is anchors moving, contact opening and closing, cells changing hands, processes being suppressed for a tick, and cores being stripped. Fight Night should be re-specified against that. |
| **Color Commentator** | **GO WITH PREREQUISITES** | Enough factual material (§18), conditional on respecting `visible_to` and on aggregating the high-frequency kinds. Sequenced last. |

### Recommended next phase

**Phase 4: Perspective projection and Phase 1/Phase 3 reconciliation.** Not Fog
Cam rendering.

Two pieces, in order:

1. **Reconcile the two analyzers.** Decide whether `spectator_events` becomes a
   degraded replay-only mode of one layer or is retired, and remove
   `target_entrant_id` from replay-derived detection. Shipping two disagreeing
   detection models is the largest correctness risk currently in the tree, and
   it gets more expensive with every layer built on top.
2. **Build and qualify a perspective projection function** —
   `project(events, entrant) -> what this entrant could know` — with an
   explicit, documented belief/staleness model, before any rendering. Then Fog
   Cam is a renderer over a qualified projection rather than a place where
   perspective rules get invented under UI pressure.

The originally hypothesized order (Phase 3 → Fog → Director → Fight Night →
Commentator) is otherwise sound, with one change: **Fight Night should be
re-specified before it is scheduled**, because its animating concept assumes
process lifecycle events that v4 does not have.

---

## 23. Commits

| Commit | Contents |
|---|---|
| `794be2366ad1a7465989a75c535f7321236ae4ee` | `feat(v4): derive deterministic spectator events from validated pairs` — `spectator_derivation.py`, its 35-test suite, the `tools/` wrapper, the additive `spectator_events.py` export, and the trace-spec clarification. |
| *(this document)* | `docs(v4): report Phase 3 qualification` — committed separately, per this repository's convention of keeping feature work and its qualification record in distinct commits. |

Branch `v4-spectator-phase2-development`, local only; neither commit was
pushed. Baseline at Phase 3 start was `d7b46bb`; `origin/main` remains
`4aa8ac3a4cc0deccfdd6c5b94136933b315335be`.

Working tree after both commits: clean, apart from the pre-existing untracked
working artifacts recorded in §1 and the pre-existing
`.pytest-cache-v141/` permission warning.
