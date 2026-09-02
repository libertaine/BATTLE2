# Bytefray v4 Spectator Research Phase 4 — Perspective Projection, Knowledge Semantics, and Analyzer Reconciliation

## Verdict

**PASS.**

Phase 4 established one deterministic, trace-authoritative entrant-perspective
path over a validated replay/API-v2 trace pair. It answers what the engine had
actually supplied to one entrant at a callback boundary without converting
canonical replay omniscience into entrant knowledge.

The central result is deliberately smaller than an enemy tracker:

> Bytefray can reconstruct anonymous, sampled contact memory and historical
> READ samples. It cannot reconstruct persistent enemy identity, multiplicity,
> or continuously current world knowledge because Agent API v2 never supplied
> those facts.

This is enough for a future renderer, provided that the feature is presented as
an **Entrant Perspective** or **Perspective Cam**, not as authoritative enemy
tracking. Fog/Perspective rendering was not implemented in this phase.

| Area | Classification |
|---|---|
| Phase 1 / Phase 3 reconciliation | **COMPLETE** |
| Authoritative API-v2 perspective path | **IMPLEMENTED AND QUALIFIED** |
| Anonymous contact model | **QUALIFIED** |
| `UNKNOWN` / `CURRENT` / `STALE` contract | **QUALIFIED** |
| READ-delivery knowledge | **QUALIFIED** |
| Callback and tick-boundary semantics | **QUALIFIED** |
| Multi-process semantics | **QUALIFIED** |
| 3- and 4-entrant ambiguity | **QUALIFIED** |
| Omniscient separation / negative leakage | **QUALIFIED** |
| Determinism, hash-seed stability, seeking | **QUALIFIED** |
| Canonical simulation and replay isolation | **CONFIRMED** |
| Perspective Projection | **GO** |
| Fog / Perspective Cam rendering | **GO WITH PREREQUISITES** |
| Spectator Director | **GO WITH PREREQUISITES** |
| Fight Night | **REVISE CONCEPT** |
| Color Commentator | **GO WITH PREREQUISITES** |
| **Phase 4 overall** | **PASS** |

### PASS criteria

| # | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | Reconcile Phase 1 and Phase 3 overlap | **PASS** | §2 |
| 2 | One authoritative API-v2 perspective path | **PASS** | §2.2, §7 |
| 3 | Replay-only detection excluded from authoritative knowledge | **PASS** | §2, §10.1 |
| 4 | No invented target identity | **PASS** | §4.2, §9, §10 |
| 5 | Explicit current/history/stale contract | **PASS** | §4.1 |
| 6 | Callback/tick ordering respected | **PASS** | §5.1 |
| 7 | Multi-process behavior correct | **PASS** | §5.2 |
| 8 | Multi-entrant ambiguity tested | **PASS** | §8, §10.2 |
| 9 | No omniscient facts leak | **PASS** | §4.4, §6, §10 |
| 10 | Real matches exercise projection end to end | **PASS** | §8–§10 |
| 11 | Explicit false-knowledge tests | **PASS** | §10 |
| 12 | Deterministic output | **PASS** | §11.1 |
| 13 | Arbitrary seeking equals sequential reconstruction | **PASS** | §11.2 |
| 14 | Simulation/replay unchanged | **PASS** | §12 |
| 15 | Renderer-ready knowledge contract | **PASS** | §16.2 |

No stop condition was triggered. The evidence did require two narrow corrections
to the qualified Phase 3 implementation: a dead entrant's retained replay
anchor is not a live disruption target, and a final hostile READ is not visible
to its reader when no later callback delivers the result. Both corrections are
covered by real-match regressions (§6.2).

---

## 1. Repository baseline

Recorded before any Phase 4 file was modified.

| Fact | Value |
|---|---|
| Repository | `D:\Projects\BATTLE2` |
| Remote | `https://github.com/libertaine/Bytefray.git` (`origin`) |
| Starting branch | `v4-spectator-phase2-development` |
| Starting `HEAD` | `06e3862618290ebb0bde58223c266d7416f38f28` |
| Starting subject | `docs(v4): report Phase 3 qualification` |
| Phase 3 implementation | `794be2366ad1a7465989a75c535f7321236ae4ee` |
| Fetched `origin/main` | `4aa8ac3a4cc0deccfdd6c5b94136933b315335be` |
| Phase 3 line versus `origin/main` | 11 ahead, 0 behind |
| Phase 4 branch created | `v4-spectator-phase4-development` |

Both reported Phase 3 commits exist, are adjacent in the expected order, and
are ancestors of the Phase 4 branch. Phase 4 was not started by assuming the
short SHAs still named `HEAD`.

### 1.1 Git-visible state actually observed

Tracked and staged state was clean. The only non-ignored untracked file was:

```text
?? .claude/settings.local.json
```

It was preserved untouched, unstaged, unstashed, and uncommitted.

The top-level ignored-state inventory was also recorded. It contained:

```text
.claude/scheduled_tasks.lock
.mypy_cache/
.pytest-cache-v141/
.pytest-cache/
.pytest_cache/
.ruff_cache/
.venv/
.vscode/
_legacy/__pycache__/
_legacy/tests/__pycache__/
agent_revisions/
agents/Nemesis/__pycache__/
agents/bomber/model.blob
agents/chatgpt_hunter/chatgpt_hunter.blob
agents/chatgpt_hunter/model.blob
agents/claude_agent/claude_agent.blob
agents/claude_agent/model.blob
agents/hydra/__pycache__/
agents/replicator/model.blob
agents/v4_claimer/__pycache__/
agents/v4_concentrated_attacker/__pycache__/
agents/v4_defender_scout/__pycache__/
agents/v4_local_defender/__pycache__/
agents/v4_scout/__pycache__/
agents/viper/__pycache__/
app/__pycache__/
app/services/__pycache__/
app/views/__pycache__/
app/widgets/__pycache__/
build/
bytefray.egg-info/
client/src/battle_client/__pycache__/
client/src/battle_client/renderers/__pycache__/
client/tests/__pycache__/
combat_replay.jsonl
dist/
engine/.mypy_cache/
engine/src/battle_engine/__pycache__/
engine/src/battle_engine/builtins/__pycache__/
engine/src/battle_engine/data/reference_agents/core_defender/__pycache__/
engine/src/battle_engine/data/starter_agents/v4_claimer/__pycache__/
engine/src/battle_engine/data/starter_agents/v4_concentrated_attacker/__pycache__/
engine/src/battle_engine/data/starter_agents/v4_defender_scout/__pycache__/
engine/src/battle_engine/data/starter_agents/v4_local_defender/__pycache__/
engine/src/battle_engine/data/starter_agents/v4_scout/__pycache__/
engine/src/battle_engine/evaluation_history/__pycache__/
engine/tests/__pycache__/
pytest_full2.log
replay.jsonl
runs/
summary.json
test_replay.jsonl
tests/__pycache__/
tools/__pycache__/
tools/local_ai/local-ai-results/
tournament/scripts/__pycache__/
work/
```

The repository-local `.pytest-tmp/` and `.pytest-cache-v141/` trees have
pre-existing Windows ACL problems and can produce `Permission denied` warnings
during inventory and Ruff. No attempt was made to clean, reset, or take
ownership of them. Phase 4 test artifacts were written into distinct named
subdirectories under `.pytest-tmp` and are ignored.

Three pre-existing stashes were left untouched:

```text
stash@{0}: On main: sync_win auto-stash 20251005-193035
stash@{1}: On main: sync_win auto-stash 20251001-214422
stash@{2}: On feature/pygame-window-fit: WIP before pulling main
```

The secondary worktree was also left untouched:

```text
D:/Projects/Bytefray-v1-rc1
HEAD b68c41234d37b2c0bbf9d75478efb70b20121121
branch v1.0-rc1-branding
```

### 1.2 Files inspected

| Area | Files |
|---|---|
| Architecture and contracts | `ARCHITECTURE.md`, `docs/specs/v4_api_v2_trace.md`, `docs/AGENT_API_V2.md`, `docs/REPLAY_SCHEMA.md`, `docs/COMPATIBILITY.md` |
| Prior spectator research | Phase 0.6, Phase 1, Phase 2, and Phase 3 reports under `docs/research/v4/` |
| Phase 1 replay analysis | `spectator_events.py`, `spectator_aggregation.py`, their tests and tool wrapper |
| Phase 3 pair derivation | `spectator_derivation.py`, `test_v4_spectator_derivation.py`, `tools/spectator_derive.py` |
| Trace and runtime | `agent_trace.py`, `agent_api.py`, `process_runtime.py`, `match_service.py`, `python_runtime.py` |
| Replay and viewer seam | `replay.py`, telemetry/result construction, `ReplaySession`, replay viewer/renderers, current Fog-related research code |
| Configuration | `pytest.ini`, `pyproject.toml`, `.gitattributes`, `AGENTS.md` |

### 1.3 Phase 4 files

| File | Change |
|---|---|
| `docs/specs/v4_spectator_perspective.md` | New normative research contract for source authority, time, contacts, stale state, READ delivery, and the future renderer seam. |
| `engine/src/battle_engine/spectator_perspective.py` | New immutable projection, state queries, deterministic serialization, explanation output, and research CLI. |
| `engine/tests/test_v4_spectator_perspective.py` | New 19-test real-match adversarial qualification corpus. |
| `tools/spectator_project.py` | New source-checkout wrapper following existing spectator tool conventions. |
| `engine/src/battle_engine/spectator_derivation.py` | Two narrow Phase 3 semantic corrections found by Phase 4 hostile review. |
| `engine/tests/test_v4_spectator_derivation.py` | Continuing-elimination regression and audience assertion update. |
| `docs/research/v4/V4_SPECTATOR_PHASE_4_RESEARCH.md` | This report. |

No scheduler, Ruleset policy, quota, scoring, replay schema, trace schema,
runtime observation, winner, client, app, or renderer implementation changed.

---

## 2. Phase 1 versus Phase 3 reconciliation

### 2.1 Reconciliation matrix

| Concept | Phase 1 source and definition | Phase 3 source and definition | Authority | Disposition |
|---|---|---|---|---|
| Detection gained | Replay tick-end process geometry; named viewer and target entrant | Union of actual `ObservationV2.visible_enemy_anchor_addresses` delivered during a sampled entrant/tick | Trace for knowledge; Phase 3 event for quiet factual annotation | Phase 1 **REPLAY-ONLY** and **REMOVE FROM AUTHORITATIVE PATH**; Phase 3 **REUSE** for broadcast annotation; projection uses trace directly |
| Detection lost | Difference between replay tick-boundary named geometric contacts | Difference between successive sampled-tick observation unions | Trace callback sequence for current/stale state | Phase 1 **REPLAY-ONLY**; Phase 3 **REUSE** as coalesced event, not state |
| Foreign ownership overwrite / hostile write | Replay memory diffs infer `FOREIGN_OWNERSHIP_OVERWRITE` | Applied trace WRITE correlated to replay owner transition emits `HOSTILE_WRITE` and first occurrence | Validated pair / Phase 3 | Phase 1 **REPLAY-ONLY**; Phase 3 **KEEP**; perspective **OMNISCIENT-ONLY** unless separately delivered |
| Core loss | No separate authoritative concept | `CORE_CELL_LOST` from applied WRITE plus canonical core ownership | Validated pair / Phase 3 | **KEEP**, **OMNISCIENT-ONLY** |
| Core disruption / process disruption | Replay snapshots infer `CORE_DISRUPTION` from spatial state | Applied WRITE plus trace-order anchor reconstruction emits `PROCESS_DISRUPTED` | Validated pair / Phase 3 | Phase 1 **REPLAY-ONLY**; Phase 3 **KEEP**, **OMNISCIENT-ONLY** |
| Hostile READ | Not reconstructible from replay | Applied trace READ with foreign `read_owner` emits factual `HOSTILE_READ`; visibility requires later feedback delivery | Trace plus validated pair | **TRACE-ONLY**; projection uses next same-process observation |
| Effective movement | Replay boundary displacement only | Applied MOVE timeline and boundary displacement emit `EFFECTIVE_MOVE` | Validated pair / Phase 3 | **KEEP** as state-important and presentation-salience-low; own projected location still comes from a later self observation |
| Elimination | Replay alive transition | Replay alive transition after pair consistency checks | Replay / Phase 3 fact | Phase 3 **KEEP**; entrant execution perspective **OMNISCIENT-ONLY** |
| Forfeit | Replay event/result | Replay event/result after pair validation | Replay / Phase 3 fact | Phase 3 **KEEP**; entrant execution perspective **OMNISCIENT-ONLY** |
| Victory | Replay result | Validated replay result | Replay / Phase 3 fact | **KEEP** for broadcast metadata; **OMNISCIENT-ONLY** during execution perspective |
| Match ended | Phase 1 has no distinct matching event | Validated replay result emits `MATCH_ENDED` | Replay / Phase 3 fact | **KEEP**, presentation boundary only |
| Temporal overwrite windows | Phase 1 aggregation over replay-only overwrite events | No Phase 3 equivalent | None for Phase 4 knowledge | **REPLAY-ONLY**; later Director work must **REWRITE** aggregation over authoritative facts |
| Process creation/death | Not a valid v4 lifecycle | Explicitly rejected in Phase 3 | Runtime contract | **REMOVE** as v4 concepts; disruption is the real mechanic |

Naming differences are therefore aliases only where the mechanics genuinely
overlap. `FOREIGN_OWNERSHIP_OVERWRITE` was not renamed in place to
`HOSTILE_WRITE`, and `CORE_DISRUPTION` was not silently replaced. The Phase 1
structures remain available for historical replay-only research; they are no
longer candidates for API-v2 entrant knowledge.

### 2.2 One authoritative path

The supported path is now:

```text
canonical schema-4 replay + API-v2 trace
                    |
                verify_pair
                    |
                derive_events
          (including consistency checks)
                    |
          ordered trace observations
                    |
            project_perspective
                    |
       immutable entrant perspective timeline
```

There are not two competing perspective analyzers. Phase 1 remains a historical
replay/broadcast utility. Phase 3 remains the factual event path. Phase 4 uses
the trace's ordered observations for knowledge state because events intentionally
omit or coalesce information required for a truthful projection.

---

## 3. Authoritative-source decisions

| Information class | Authoritative artifact | Reason |
|---|---|---|
| World memory and ownership at replay boundaries | Canonical replay | Schema 4 records canonical state and diffs. |
| Process anchors/disruption at replay boundaries | Canonical replay | These are canonical snapshots, not necessarily what an entrant was told. |
| Alive/forfeit state, result, termination, winner | Canonical replay | Match lifecycle and result authority. |
| Exact observation supplied to a process | API-v2 trace | Only the trace records callback-time `ObservationV2`. |
| Global callback order | API-v2 trace file position | Existing contract preserves deterministic order; no action ordinal was needed. |
| Requested action and applied outcome | API-v2 trace | Both sides of the callback/action boundary are recorded. |
| Factual spectator event vocabulary | Phase 3 derivation from validated pair | Qualified deterministic facts and `(tick, sequence)` order. |
| Entrant-delivered current and historical knowledge | Phase 4 projection | A policy-constrained fold over that entrant's ordered observations. |
| Presentation overlays | Future viewer/broadcast layer | Must remain separate from execution knowledge. |

The binding verifies that the trace names the replay and `derive_events()`
cross-checks writes, anchors, and disruption against replay truth. The trace
body is not cryptographically authenticated; Phase 4 makes no stronger security
claim.

---

## 4. Knowledge model

Projection represents deterministic memory of engine-delivered facts. It is
not literal agent cognition: an agent can forget, ignore, transform, or persist
the same inputs differently.

### 4.1 `UNKNOWN`, `CURRENT`, and `STALE`

For an arena address:

| State | Qualified meaning | Explicit non-claim |
|---|---|---|
| `UNKNOWN` | No selected-entrant observation has ever listed enemy occupancy at the address. | The canonical world may contain an enemy there. |
| `CURRENT` | The address appears in the selected entrant's latest delivered visibility sample. | It need not still be occupied after that callback. |
| `STALE` | It appeared in an earlier sample and a later delivered sample omitted it. | No claim that the same enemy remains, moved, died, or will return. |

Every selected-entrant callback replaces the entrant-wide current-contact set.
Omitted prior contacts become stale. A stale address observed again becomes
current anonymous occupancy; it does not regain an entity identity. A tick with
no callback performs no transition at all.

`CURRENT` therefore always means *current as of the latest delivered sample*,
not *current in canonical replay world state*.

### 4.2 Contact identity

`ObservedContact` was intentionally not implemented as an enemy track. A
contact stores:

- arena address;
- first-observed callback point;
- last-confirmed callback point;
- observation count;
- optional callback point at which later absence made it stale; and
- source field provenance.

It does not store entrant identity, process identity, role, multiplicity, or a
synthetic track ID. Two enemy processes or two entrants co-located at one
address collapse to one contact because that is exactly what
`ObservationV2` supplies. If a different enemy later occupies the same address,
the projection cannot distinguish it and does not pretend continuity.

### 4.3 READ-derived knowledge

The trace records a READ's applied result immediately after the action, but the
entrant learns that result only on the same process's next callback through
`previous_read_value`, `previous_read_owner`, and previous-action feedback.

Projection correlates those two records and stores:

- process ID;
- requested address;
- normalized address if applied;
- sampled byte value and sampled cell owner;
- action/sample callback point; and
- delivery callback point.

A final successful READ without a later same-process callback is not projected.
A sibling process callback cannot deliver it. A rejected/failed READ may become
historical action feedback, but it contains no fabricated cell value, owner,
normalized address, or private rejection reason.

READ entries are immutable historical samples. A later canonical write does
not update them. Most importantly, a sampled cell owner is **not joined to a
spatial contact** at the same address: memory ownership and anonymous enemy
occupancy are different facts.

### 4.4 World truth versus entrant knowledge

The following are excluded from entrant execution perspective unless an actual
observation supplies them through one of the qualified channels:

- opponent identity or process multiplicity behind a contact;
- opponent process state;
- incoming hostile writes and core-cell loss;
- process disruption, including the causal attacker;
- another entrant's elimination or forfeit;
- match end, winner, and victory; and
- replay-derived geometry that was never sampled.

An omniscient/broadcast consumer may still use canonical replay and Phase 3
events. It is a separate domain, not a richer setting on the same entrant
knowledge object.

---

## 5. Projection time and multi-process semantics

### 5.1 Sequence-aware time

Trace file position is the global decision ordinal. Each selected-entrant
callback yields one `PerspectiveFrame`, applying the observation that existed
before that callback's action. No schema change or explicit `action_slot` was
needed.

Queries have exact boundaries:

- `state_at_decision(i)` folds through global decision index `i`;
- `state_at_callback(i)` folds through selected-entrant callback ordinal `i`;
- `state_at_tick(N, START)` includes selected-entrant callbacks with tick `< N`;
- `state_at_tick(N, END)` includes selected-entrant callbacks with tick `<= N`.

Tick `END` is the recommended future renderer default. Same-tick flapping is
still available through callback/decision queries. The latest selected-entrant
callback wins at tick end because it is the most recent knowledge the engine
supplied, not because it is convenient to render.

Silence is not blindness: if disruption suppresses every callback in a tick,
the previous delivered state carries forward with `sampled_this_tick=False`.

### 5.2 Multiple processes

The runtime constructs visibility from all eligible friendly process sensors,
so the contact list in each callback is entrant-wide at that instant. The
latest callback from any process therefore replaces entrant-wide current
contacts.

These facts remain process-local:

- `self_process_id`, `self_anchor`, and `self_reach`;
- previous-action feedback and READ delivery; and
- callback provenance.

Projection retains the latest delivered self sample for each declared process.
It labels that sample as observed, not canonical-current. Tests using alpha2's
round-robin process selection prove that a sibling callback does not consume or
deliver another process's pending READ result.

---

## 6. Semantic-event visibility and terminal boundary

### 6.1 Why `visible_to` filtering is insufficient

This is not a valid projector:

```python
[event for event in derivation.events if entrant in event.visible_to]
```

It loses essential information because:

- Phase 3 detection events union an entire sampled tick, while Phase 4 needs
  the latest callback sample and intra-tick gain/loss;
- hostile READ events occur at action time, while knowledge arrives on a later
  same-process callback;
- self-owned, unowned, ordinary, and rejected READs have no semantic event;
- own process samples and previous-action feedback have no semantic event; and
- most world events are correctly omniscient-only.

Phase 3 events remain factual broadcast annotations. Ordered observations own
entrant knowledge.

### 6.2 Phase 3 corrections activated by perspective analysis

Hostile review found two real edge defects rather than reopening mechanics:

1. **Retained dead anchors.** Schema 4 retains declared process snapshots after
   an entrant is eliminated. Phase 3 was using those anchors both for replay
   agreement and as later live disruption targets. In a real 3-entrant match,
   B was eliminated on tick 2 while A and C continued; a later write at B's
   retained address falsely attempted to disrupt B and failed pair consistency.
   The derivation now retains every anchor for replay agreement but limits
   disruption candidates to the replay-derived live entrant set.
2. **Final hostile READ audience.** Phase 3 gave every applied hostile READ a
   reader audience. The action result is produced after the callback, however,
   and a final READ with no later same-process callback is never supplied to
   the entrant. The event remains an omniscient fact, but `visible_to=()` in
   that case. Earlier READs become visible only when the delivery callback
   exists.

Both fixes are observational, preserve the 13 event kinds, and have real-match
regressions. The second correction is visible in the walkthrough: 8 hostile
READ facts, 7 delivered READ samples, and an empty audience on the final event.

### 6.3 Terminal presentation boundary

`AGENT_ELIMINATED`, `AGENT_FORFEITED`, `MATCH_ENDED`, and `VICTORY` remain
canonical/omniscient facts. A future viewer can show a result overlay from
replay metadata after the match. That overlay must not be inserted into the
entrant's execution-time knowledge history.

`EFFECTIVE_MOVE` also remains factual. It is classified
**STATE-IMPORTANT / PRESENTATION-SALIENCE-LOW**: movement affects geometry and
self-location, but later Director/Commentator work may suppress routine moves.

---

## 7. Projection API and analyzer

### 7.1 Supported API

The high-level entry point is:

```python
analyze_perspective(replay_path, trace_path, entrant_id)
    -> PerspectiveProjection
```

It invokes `analyze_pair()`, which invokes `verify_pair()` and all Phase 3
consistency checks, before projection. The lower-level
`project_perspective()` accepts only a `SpectatorDerivation`; passing a raw
`PairBinding` is rejected. An unknown entrant is rejected after pair
validation. A mismatched, unbound, malformed, truncated, v1, or
replay-inconsistent pair cannot produce output through the supported API.

The immutable model comprises:

```text
PerspectiveProjection
  declarations
  ordered PerspectiveFrame deltas
  state_at_tick / state_at_decision / state_at_callback

PerspectiveState
  current_contacts
  stale_contacts
  read_history
  latest own-process samples
  last visibility sample
  sampled_this_tick
```

Serialization uses explicit ordering and omits wall time and diagnostic text
from projection identity.

### 7.2 Research CLI

`tools/spectator_project.py` re-exports the permanent engine contract and runs
the research CLI:

```text
python tools/spectator_project.py REPLAY TRACE --perspective A
python tools/spectator_project.py REPLAY TRACE --perspective A --tick 137
python tools/spectator_project.py REPLAY TRACE --perspective A --tick 137 --tick-start
python tools/spectator_project.py REPLAY TRACE --perspective A --tick 137 --explain
```

Without `--tick`, output is deterministic JSONL for the full projection. With a
tick, output is one state. `--explain` emits auditable text. Pair mismatch exits
with status 2 and emits no apparently valid perspective.

No polished `bytefray` end-user command, UI mode management, event bus, async
machinery, or generalized cognition framework was added.

### 7.3 Provenance example

Exact analyzer output from the 3-entrant co-location fixture includes:

```text
PERSPECTIVE A
tick: 1 (END)
latest delivered visibility: tick 1, decision 15, process eye

CURRENT CONTACTS
  address 32 (anonymous occupancy)
    first observed: tick 1, decision 0, process eye
    last confirmed: tick 1, decision 15, process eye
    source: observation.visible_enemy_anchor_addresses

STALE CONTACTS
  address 40 (anonymous historical occupancy)
    first observed: tick 1, decision 0, process eye
    last confirmed: tick 1, decision 1, process eye
    absent at: tick 1, decision 6, process eye

KNOWN READ RESULTS
  address 32 sampled by eye
    value: 206
    cell owner: 'B' (not contact identity)
    sampled: tick 1, decision 0, process eye
    delivered: tick 1, decision 1, process eye
```

The same explanation explicitly lists hidden/not-projected categories. These
fields are research diagnostics, not a commitment to a future presentation
wire schema.

---

## 8. Adversarial real-match corpus

All important behaviors were produced through `NativeMatchService` as canonical
Schema 4 replay plus API-v2 trace, then verified, derived, and projected. No
test qualifies a hand-built `PerspectiveState` in isolation.

| Scenario | Ruleset / entrants | Shape qualified |
|---|---|---|
| Hunter / Anvil duel | alpha1, 2 entrants | delayed detection, hostile READ feedback, write/disruption, tick boundaries |
| Flyby / Sleeper | alpha1, 2 entrants, 20 ticks | immediate/delayed gain, retain, lose, regain, wraparound, stale memory |
| Oscillator / Anvil | alpha1, 2 entrants, multiple callbacks | same-tick visibility flapping and latest-callback tick-end state |
| Approacher / Sleeper | alpha1, 2 entrants, 1 tick | end-of-tick geometry sees a contact that the last observation never delivered |
| Hunter / Oscillator | alpha1, 2 entrants | disrupted sensor, tick with no callbacks, state carry-forward |
| Wide Reader / Anvil / Colocator | alpha1, 3 entrants | asymmetric visibility, two addresses, co-location, anonymous collapse, READ owner separation |
| Wide Reader plus three anvils | alpha1, 4 entrants | multiple simultaneous contacts, asymmetry, no cross-attribution |
| READ Probe / Anvil | alpha1, 2 entrants | self-owned, unowned, foreign-owned, rejected/out-of-reach READ, final undelivered READ |
| Multi Reader / Anvil | alpha2, 2 entrants, K=2 | process-local feedback under round-robin callbacks |
| Executioner / Sleeper / Anvil | alpha1, 3 entrants | one entrant eliminated while two continue; terminal and retained-anchor leakage |
| Repeated duel | alpha1, 3 independent executions | replay and projection repeatability |
| Short/normal/large performance fixtures | alpha1, up to 3000 ticks | verification, derivation, projection, combined cost and seeking |

The fixtures also cover friendly and enemy disruption, repeated same-address
contact, multiple potential enemies, successful and failed READs, short and
long matches, and same-tick movement/contact transitions. Co-located contacts
are mechanically possible and were exercised, not merely simulated in a data
object.

---

## 9. Complete replay + trace → event → projection walkthrough

The qualified 3-entrant match used arena size 64, seed 23, one tick, and these
declared processes:

```text
A/eye:   anchor 0,  reach 32
B/body:  anchor 32, reach 2
C/mover: anchor 40, reach 2
```

### 9.1 Ordered trace facts

The exact relevant callback sequence is:

| Global decision | Entrant/process | Self anchor | Visible addresses | Action / feedback |
|---:|---|---:|---|---|
| 0 | A/eye | 0 | `(32, 40)` | READ 32; applied result samples owner B, value 206 after callback |
| 1 | A/eye | 0 | `(32, 40)` | receives decision 0 READ feedback; READ 32 again |
| 4 | C/mover | 40 | `()` | MOVE -8, applied to 32 |
| 5 | C/mover | 32 | `(32,)` | sees anonymous co-located occupancy; writes 40 |
| 6 | A/eye | 0 | `(32,)` | C and B now collapse to one supplied address; receives prior B cell sample |
| 8 | B/body | 32 | `(32,)` | sees anonymous co-located occupancy |
| 15 | A/eye | 0 | `(32,)` | last A sample; final READ has no later delivery callback |
| 17 | B/body | 32 | `(32,)` | last match callback |

The trace never tells A that contact 32 is B, C, or both. It tells A separately
that the byte read from memory cell 32 was owned by B.

### 9.2 Canonical replay truth

At tick 0 replay truth has B at 32 and C at 40. At tick 1 it has B and C both
at 32, with C disrupted. The replay therefore knows identity, multiplicity,
movement, and disruption that A's observation does not.

### 9.3 Phase 3 factual events

The exact derived stream contains 15 events. Relevant examples are:

```text
(tick 1, seq 0)  DETECTION_GAINED A addresses=(32,40), visible_to=(A,)
(tick 1, seq 1)  HOSTILE_READ A -> B at 32, visible_to=(A,)
(tick 1, seq 4)  DETECTION_GAINED C addresses=(32,), visible_to=(C,)
(tick 1, seq 7)  DETECTION_GAINED B addresses=(32,), visible_to=(B,)
(tick 1, seq 8)  PROCESS_DISRUPTED B -> C at 32, visible_to=()
(tick 1, seq 12) HOSTILE_READ A -> B at 32, visible_to=()
(tick 1, seq 13) EFFECTIVE_MOVE C 40 -> 32, visible_to=(C,)
(tick 1, seq 14) MATCH_ENDED, visible_to=()
```

Phase 3 deliberately has one A detection-gained union for `(32, 40)` and no
same-tick detection-lost event. It is a factual, low-noise annotation, not the
callback-current state model.

### 9.4 Projected entrant state

At A decision 0, addresses 32 and 40 are current anonymous contacts. At decision
6, address 32 remains current and 40 becomes stale. At tick 1 END:

```text
current contacts: address 32, anonymous
stale contacts:   address 40, last confirmed decision 1, absent decision 6
READ history:     7 delivered samples of cell 32, owner B, value 206
own state:        A/eye anchor 0, last observed decision 15
not projected:    B/C identity or multiplicity, C's disruption, match end
```

There were 8 applied hostile READ facts but only 7 later delivery callbacks.
The final event remains factual, has `visible_to=()`, and is absent from A's
READ history. This is the exact distinction between world/action truth and
engine-delivered knowledge.

### 9.5 A/B/omniscient readiness example over time

A separate 20-tick Flyby match makes the future renderer differences visible:

| Tick end | Entrant A projection | Entrant B projection | Omniscient replay truth |
|---:|---|---|---|
| 2 | no current/stale contacts; own sample A/wing@15 | no current/stale contacts; B/z@20 | A/wing@16, B/z@20 |
| 3 | current anonymous contact 20; own sample A/wing@23 | no current contact; stale anonymous contact 20 | A/wing@24, B/z@20 |
| 4 | stale anonymous contact 20; own sample A/wing@31 | stale anonymous contact 20 | A/wing@32, B/z@20 |
| 11 | current anonymous contact 20 again; no continuity claim; own sample A/wing@23 | stale anonymous contact 20 | A/wing@24, B/z@20 |

Even own projected anchor samples can lag tick-end replay truth because the
agent moved after its last callback observation. A future Perspective Cam must
draw the projection as sampled knowledge rather than silently substitute replay
positions.

---

## 10. False-knowledge evidence

### 10.1 End-of-tick geometry trap

In the Approacher fixture, replay tick-end geometry places A in sensor range of
B at address 32. A's last callback occurred before A's final MOVE changed that
geometry, and no observation ever listed 32. Result:

```text
canonical geometric contact: {32}
A perspective status(32):     UNKNOWN
A current/stale contacts:     absent
```

This is a direct negative proof that replay geometry cannot overwrite
callback-time knowledge.

### 10.2 Identity and multiplicity

- In the 3-entrant fixture, B and C occupy address 32; A has exactly one
  anonymous contact.
- In the 4-entrant fixture, A receives `(16, 32, 48)` while B receives no
  contacts. None carries identity, process ID, owner, or target.
- A READ returning owner B at address 32 remains a cell sample and never labels
  the spatial contact B.
- Reappearance at the same address increments anonymous observation history;
  it does not prove the same enemy returned.

### 10.3 Staleness and silence

- Never observed remains `UNKNOWN` even when replay knows occupancy.
- A delivered address is `CURRENT` only relative to the latest sample.
- Later omission makes it `STALE`; it never remains silently current.
- A tick with no callback makes no observation and therefore cannot create a
  false loss. The previous sample carries forward and the tick is marked
  unsampled.

### 10.4 READ and terminal leakage

- A successful final READ is not projected without a later same-process
  delivery callback.
- A sibling process cannot deliver another process's pending READ.
- A failed READ yields no invented address/value/owner.
- Elimination of B while A and C continue is absent from C's entrant knowledge;
  Phase 3/replay retain it for broadcast truth.
- `PROCESS_DISRUPTED`, `MATCH_ENDED`, and winner/result data are not imported
  into entrant state.

These are assertions over real replay/trace pairs, not assertions that a
manually constructed data object lacks a field.

---

## 11. Determinism, seeking, and performance

### 11.1 Determinism

| Check | Result |
|---|---|
| Three projections of the same pair in one process | Byte-identical serialization |
| Three independent executions of the same seeded match | Identical replay digest, outcome, and projection serialization |
| Fresh analyzer processes with `PYTHONHASHSEED=0,1,2,42,random` | One SHA-256 digest across all five outputs |
| Multi-entrant/contact/stale cases | Stable ordered contacts, reads, processes, and frames |

No set or dictionary iteration defines output order. Trace decision position is
preserved and all serialized collections use explicit total-key ordering.

### 11.2 Arbitrary seeking

For every tick in the Flyby match, direct `state_at_tick(tick)` equaled a
sequential fold through the same callback boundary. Callback and decision seeks
are defined in the same immutable timeline.

The implementation stores compact frames and folds them linearly for a query;
it does not duplicate cumulative histories into every frame. No checkpoint
scheme was justified by the measured workload.

### 11.3 Performance

Measured on Windows NT 10.0.26120.0, Python 3.13.14, AMD Ryzen 9 5900X, 63.9
GiB RAM. Each figure is the median of five runs; parentheses are min/max. Times
are milliseconds.

| Workload | Pair | Derive | Project | Combined | Final seek | Five seeks |
|---|---:|---:|---:|---:|---:|---:|
| Short: 1 tick, 16 decisions, 8 A frames, 4 events | 0.990 (0.897–1.257) | 0.889 (0.858–0.942) | 0.498 (0.459–0.521) | 2.246 (2.201–2.282) | 0.028 | 0.036 |
| Normal: 300 ticks, 4,800 decisions, 2,400 frames, 452 events | 66.527 (65.209–69.496) | 82.417 (75.277–83.059) | 74.821 (70.506–82.307) | 225.886 (210.741–228.309) | 2.744 | 5.175 |
| Large: 3,000 ticks, 48,000 decisions, 24,000 frames, 1 event | 941.170 (925.639–974.757) | 1,088.067 (1,047.314–1,102.880) | 732.809 (731.534–741.070) | 2,811.644 (2,719.491–2,836.184) | 26.846 | 50.654 |

Artifact sizes were 6,773/10,655 bytes (replay/trace) for short,
201,225/2,946,767 for normal, and 4,550,709/29,895,304 for large.

Conclusion: one-time materialization is adequate at the current 3,000-tick
scale. Phase 5 should retain a projection/cursor instead of re-folding from zero
on every render frame. It should measure that integration before introducing
checkpoints; Phase 4 adds none.

---

## 12. Simulation, replay, and compatibility isolation

A traced match and an otherwise identical untraced match produced the exact
same winner, tick count, replay SHA-256, and replay bytes. Running perspective
analysis did not alter either replay or trace bytes.

The production/runtime regression set covering alpha1 and alpha2 placement,
scheduling, processes, observations, and integration is green (§13). No code in
`process_runtime.py`, scheduler policy, Agent API v2, replay schema 4, scoring,
or result construction changed.

Historical Rulesets, Agent API v1, schema-3 replay handling, and Phase 1 public
structures remain untouched. The projection is additive engine analysis code
with standard-library dependencies. `ReplaySession` remains replay-only; Phase
5 can load a parallel immutable projection keyed to the session tick.

The trace newline/replay-byte issue remains exactly where Phase 3 left it. Phase
4 introduced no canonical byte fixture or identity mechanism and did not
rewrite serialization. Bound pairs must still be moved without newline
conversion. Trace file position remained sufficient for ordering, so no action
ordinal was added.

---

## 13. Qualification results

All pytest stages were run sequentially with separate `--basetemp` locations.
`engine/tests/` is reported separately from the true configured repository
suite (`_legacy/tests`, `engine/tests`, and `client/tests`).

| Gate | Exact result |
|---|---|
| Phase 1 spectator regressions (`test_spectator_analyzer.py`, `test_spectator_aggregation.py`) | **39 passed** in 0.92 s |
| Phase 2 trace regressions (`test_v4_trace_equivalence.py`, `test_agent_trace.py`) | **19 passed** in 0.35 s |
| Phase 3 derivation focused | **36 passed** in 2.98 s |
| Phase 4 perspective focused | **19 passed** in 2.75 s |
| Final combined Phase 3 + Phase 4 after audience correction | **55 passed** in 5.55 s |
| Replay/schema (`test_replay_reconstruction.py`, `test_replay_contract.py`) | **29 passed** in 0.38 s |
| Relevant v4 runtime/API set | **124 passed** in 2.91 s |
| Final `engine/tests/` | **2,329 passed, 14 skipped** in 274.43 s |
| Final true configured repository suite | **2,707 passed, 26 skipped, 2 deselected** in 275.62 s |
| `ruff check .` | **All checks passed**; known inaccessible ignored-cache warning only |
| `mypy engine/src/battle_engine` | **Success: no issues in 99 source files** |
| `mypy client/src/battle_client` | **Success: no issues in 12 source files** |

The relevant v4 runtime/API set comprised:

```text
test_v4_stage6_observation.py
test_v4_r3_spatial.py
test_v4_production_integration.py
test_v4_process_semantics.py
test_v4_interleaved_scheduler.py
test_v4_alpha2_scheduler.py
test_v4_alpha2_placement.py
test_v4_alpha2_integration.py
```

### 13.1 Count reconciliation

Phase 3 ended at 2,309 passed / 14 skipped in engine and 2,687 passed / 26
skipped / 2 deselected in the full suite. Phase 4 adds 19 perspective tests and
one Phase 3 retained-anchor regression, with no new skip:

| | Phase 3 | Phase 4 addition | Measured |
|---|---:|---:|---:|
| Engine passed | 2,309 | +20 | **2,329** |
| Engine skipped | 14 | +0 | **14** |
| Full passed | 2,687 | +20 | **2,707** |
| Full skipped | 26 | +0 | **26** |
| Full deselected GUI tests | 2 | +0 | **2** |

The 2 deselected tests remain the two intentionally GUI-marked Linux Pygame
smokes documented in Phase 3. No test was weakened or converted to a skip.

The final full suite was rerun after the final hostile-READ audience correction.
Static checks were also rerun on that exact final source. An attempted parallel
static launch hit a Windows executable-access collision before any checker ran;
the sequential reruns above are the authoritative results.

---

## 14. Hostile self-review

**Did projection reconstruct omniscient truth?** No. The geometry-trap test has
canonical contact at 32 and projected `UNKNOWN`. Eliminations, disruption,
writes, terminal state, and opponent process snapshots remain absent.

**Did it infer target identity from canonical ownership?** No. Contacts have no
identity field. A READ cell owner is serialized and explained as "not contact
identity" and is never joined to a contact.

**Did it create unjustified continuity?** No. Contact history is keyed only by
address and described as renewed anonymous occupancy. It does not claim the
same enemy moved away or returned.

**Are stale contacts speculative tracks?** No. `STALE` records only that an
address once appeared and a later delivered sample omitted it. It makes no
occupancy or identity claim.

**Did replay-only detection re-enter the path?** No. The supported API derives
for validation, then folds exact trace observations. End-of-tick geometry never
updates perspective.

**Does end-of-tick world truth overwrite callback truth?** No. The trap and
Flyby examples demonstrate that both contact and own anchor samples may differ
from replay tick end.

**Can an eliminated enemy leak through retained process anchors?** No. Entrant
projection never imports them, and Phase 3 disruption derivation now separates
retained replay anchors from the live-target set.

**Can sibling processes contradict current visibility?** Each callback's
visibility is entrant-wide and the latest sample replaces the prior set.
Process-local self and feedback histories remain separate. Same-tick flapping
is preserved in frames.

**Are READ results treated as permanently true?** No. They are immutable
historical samples with both sample and delivery provenance. They are never
updated from replay or labelled current memory.

**Can multiple enemies at one address be distinguished?** No—and the model
states that truthfully by emitting one anonymous address. The 3-entrant test
proves the limitation.

**Does the data structure imply more certainty than the observation?** No
identity, count, process, role, or track fields exist on contacts. Own anchors
are labelled latest delivered samples.

**Can a mismatched pair be projected?** Not through supported APIs. Both path
orders, the lower-level type boundary, and the CLI failure path are tested.

**Can tests pass while real projection never runs?** No. All 19 Phase 4 tests
run `NativeMatchService`, parse real artifacts, execute validation/derivation,
and call the permanent projector or wrapper.

**Does ordering depend on incidental collections?** No. Frames preserve trace
position; output collections have explicit sorting; five hash-seed processes
produce one digest.

**Was runtime behavior modified for presentation?** No. All Phase 4 code is
offline analysis/test/spec/tooling, plus two offline derivation corrections.

The two uncomfortable Phase 3 answers—dead retained anchors and undelivered
final READ audience—were fixed and regression-tested rather than hidden in the
report.

---

## 15. Known limitations and unresolved semantic ambiguities

1. **Sampled, not continuous.** `CURRENT` means latest delivered sample, not
   live replay truth. A renderer must communicate or at least preserve that
   distinction.
2. **Anonymous and count-free.** The engine supplies addresses, so identity,
   process count, entrant count, and continuity cannot be reconstructed.
3. **Own state may lag.** A process can act after observing; the next replay
   boundary may differ from its last supplied self anchor.
4. **No-callback intervals.** State carries forward as last-known with an
   explicit unsampled flag. Phase 5 must not render silence as a new empty
   scan.
5. **READ delivery ends at callbacks.** A final action result can be factual in
   trace/Phase 3 but never delivered knowledge.
6. **READ owner semantics.** Owner identifies the sampled cell, not a nearby
   process or contact. There is no justified join.
7. **Terminal knowledge.** The engine does not deliver a terminal observation
   to all entrants; result overlays remain a separate broadcast boundary.
8. **Linear seeks.** A query folds compact prior frames. Measured 3,000-tick
   cost is adequate, but Phase 5 must avoid doing a full fold every display
   frame.
9. **Binding is not authentication.** Pair association plus state cross-checks
   are strong consistency preconditions, not tamper-proof provenance.
10. **No omniscient projection object.** Omniscient data already exists as
    replay plus Phase 3 events. Phase 4 did not wrap it in a second state API.
11. **No renderer or end-user mode.** The tool is a research/debug seam only.
12. **Line-ending identity remains deferred.** Pairs still require binary-safe
    movement; Phase 4 did not activate a new reason to redesign bytes.

These are contract boundaries rather than blockers. The only unresolved UX
question is how Phase 5 should visually communicate sample age without implying
radar-quality continuous tracking.

---

## 16. Roadmap reassessment

### 16.1 Classifications

| Component | Verdict | Reason |
|---|---|---|
| **Perspective Projection** | **GO** | Implemented, deterministic, bound, identity-honest, real-match qualified, and renderer-consumable. |
| **Fog / Perspective Cam Rendering** | **GO WITH PREREQUISITES** | Render the qualified projection in parallel with replay; distinguish current/stale/unknown, retain sample age, and keep terminal/broadcast overlays separate. Do not infer identity or refold from zero each frame. |
| **Spectator Director / Dynamic Pacing** | **GO WITH PREREQUISITES** | Must separate shot selection from disclosure. An omniscient Director may choose an interesting moment, but an entrant-mode renderer must still reveal only that projection. Perspective-only pacing and broadcast pacing are different products. |
| **Fight Night** | **REVISE CONCEPT** | Phase 3's conclusion stands: v4 drama is contact opening/closing, anchor movement, territorial/core loss, disruption/suppression, and entrant elimination—not process birth/death. Phase 4 adds that entrant mode can reveal only a subset, often anonymously. |
| **Color Commentator** | **GO WITH PREREQUISITES** | In entrant mode it can be leak-free only by consuming projected state/deltas, never raw replay or all Phase 3 events. Broadcast commentary may use omniscient facts. No commentary was implemented. |

### 16.2 Feature name

Recommended user-facing concept: **Perspective Cam**, with a selected
**Entrant Perspective**. "Sensor View" is accurate but narrower than the READ
and own-state history. "Fog of War" is familiar but risks promising continuous,
identified enemy tracking that Bytefray does not provide.

The UI may still use "Fog" informally, but its contract should describe:

```text
current anonymous sensor contacts
stale anonymous contact memory
historical READ samples
latest delivered own-process samples
separate broadcast result overlay
```

### 16.3 Recommended next phase

**Phase 5: Perspective Cam rendering.** Load a validated projection alongside
the existing replay session, query tick-end state with an efficient retained
cursor/cache, visually distinguish current/stale/unknown and sample age, and
provide an explicit broadcast/omniscient comparison without contaminating
entrant state.

No Director, Fight Night redesign, or Commentator should precede that renderer
integration. The provisional sequence remains:

```text
Phase 5  Perspective Cam rendering
Phase 6  Spectator Director / dynamic pacing
Phase 7  Revised Fight Night
Phase 8  Color Commentator
```

---

## 17. Commits and final repository state

| Commit | Contents |
|---|---|
| `a834d33a0e4f4e0bda223ff750fc102976254b0e` | `docs(v4): specify spectator perspective semantics` |
| `5ee64dc68a437aae4a0dfa8cb3a9774867cb6d2a` | `fix(v4): ignore eliminated spectator disruption targets` |
| `e0439b3a68880acf1ade0107c35870da5e18ae03` | `feat(v4): add deterministic spectator perspective projection` |
| `caa38077cc8922bccbf63f18fa2173c967a5e5da` | `test(v4): qualify spectator knowledge boundaries` |
| `b24fedef0c71fb1eca53274b44b012701e204910` | `fix(v4): align hostile read audience with delivery` |
| *(this document)* | `docs(v4): report Phase 4 qualification` |

The implementation diff from the qualified Phase 3 report commit, before this
document, was 6 files, 2,278 insertions, and 9 deletions. `git diff --check`
was clean. New/changed files use LF in accordance with `.gitattributes`; no
unrelated newline normalization was committed.

The branch is `v4-spectator-phase4-development`. The only Git-visible
untracked file remains `.claude/settings.local.json`, deliberately untouched.
Existing stashes, the v1 RC1 worktree, ignored agent experiments, caches, and
generated artifacts remain untouched. Nothing was pushed.

---

## 18. Requested final-report cross-reference

| Requested item | Location |
|---:|---|
| 1. Initial repository state | §1 |
| 2. Confirmed Phase 3 baseline | §1 |
| 3. Files inspected | §1.2 |
| 4. Phase 1/Phase 3 reconciliation matrix | §2.1 |
| 5. Authoritative-source decisions | §3 |
| 6. Knowledge-model definition | §4 |
| 7. Current/stale/unknown semantics | §4.1 |
| 8. Contact identity model | §4.2 |
| 9. READ-derived model | §4.3 |
| 10. World truth/knowledge boundary | §4.4 |
| 11. Callback/tick decision | §5.1 |
| 12. Multi-process semantics | §5.2 |
| 13. Multi-entrant ambiguity | §8, §10.2 |
| 14. Event filtering | §6.1 |
| 15. Terminal boundary | §6.3 |
| 16. Projection implementation | §7.1 |
| 17. Analyzer/CLI | §7.2 |
| 18. Provenance examples | §7.3 |
| 19. Real-match corpus | §8 |
| 20. False-knowledge examples | §10 |
| 21. Full walkthrough | §9 |
| 22. Determinism | §11.1 |
| 23. Hash-seed results | §11.1 |
| 24. Arbitrary seek | §11.2 |
| 25. Performance | §11.3 |
| 26. Simulation/replay isolation | §12 |
| 27. Phase 1 regressions | §13 |
| 28. Phase 2 regressions | §13 |
| 29. Phase 3 regressions | §13 |
| 30. Replay/runtime results | §13 |
| 31. Engine suite | §13 |
| 32. True full suite | §13 |
| 33. Ruff | §13 |
| 34. mypy | §13 |
| 35. Known limitations | §15 |
| 36. Unresolved ambiguities | §15 |
| 37. Fog/Perspective readiness | §16 |
| 38. Director implications | §16.1 |
| 39. Fight Night implications | §16.1 |
| 40. Commentator implications | §16.1 |
| 41. Recommended next phase | §16.3 |
| 42. Commit SHAs | §17 |
| 43. Final working-tree state | §17 |
| 44. Push status | §17 |
