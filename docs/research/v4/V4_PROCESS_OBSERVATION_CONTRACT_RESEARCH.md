# Bytefray v4 Research — Stage 6 Process Observation and Combat Feedback Contract

This document concludes the Stage 6 semantic research defining the exact information a process requires to interpret legal gameplay without leaking unnecessary internal state or combat confirmations.

## A. Baseline qualification
* **Starting Commit**: `aacb50c856e6232f6c2acfd46c4eeb1b6c990e75`
* **Test Baseline**: The process semantics, spatial semantics, disruption, and visibility test suites were run on a clean worktree (83 passing `test_v4_*.py` tests).

## B. Current observation inventory
Inspection of the current `ProcessObservation` revealed:
* **Required**: `tick`, `process_id` (self-identity), `position`, `reach`, `core_base`, `core_size`, `read_result`, `read_owner`, `visible_enemy_anchors`.
* **Historical/Research-only**: `role` (agents can manage their own metadata).
* **Internal Leakage / Redundant**: `last_action_kind`, `last_action_operand`, `last_action_value` (agents inherently know what they issued); `shared_memory` (agents can manage their own class-level state); `arena_size` (already in Config).

## C. Callback timing model
The normative observation sequencing is defined as:
1. Scheduler selects entrant chunk.
2. Runtime selects eligible process.
3. Disruption eligibility is checked (`disrupted_until_tick`).
4. Local detection is recomputed globally for the entrant.
5. Observation is constructed (capturing current state + previous feedback).
6. Process callback executes.
7. Action is validated and effects occur.
8. Feedback is stored for the next callback.

## D. Temporal provenance
The contract must provide explicit time provenance to resolve gaps caused by disruption.
* `current_tick`: The actual simulation tick.
* `last_callback_tick`: The last tick this process was selected to run.
* `previous_action_tick`: The tick in which the stored feedback was generated.

## E. READ feedback
Explicit READ feedback remains: `previous_read_value` and `previous_read_owner`. An out-of-reach or failed READ will unambiguously return `None` for both. 

## F. WRITE feedback
**W0 — No disruption confirmation** is selected.
A WRITE reports only whether it legally applied to the memory cell (`previous_action_applied = True`). It explicitly does **not** confirm if an enemy process was disrupted.

## G. MOVE feedback
No explicit success boolean is needed. The `self_anchor` is authoritative; comparing current `self_anchor` against the requested operand allows the agent to deduce bounds clipping or wrapping.

## H. Disruption/recovery feedback
No explicit `was_disrupted` or `attacker_id` field is provided. A recovering process compares `current_tick` against `last_callback_tick` to deterministically deduce that it missed execution slots.

## I. Occupancy field contract
`visible_enemy_anchor_addresses: tuple[int, ...]`. 
Contains exact unique addresses of live enemy anchors within detection range of any friendly process. Deterministically sorted, containing no process identities, counts, or quota metadata.

## J. Friendly/self metadata
* **Self**: `self_process_id` and `self_anchor` are required for internal state routing.
* **Friendly peers**: Not provided by engine. Entrant code can share friendly anchors natively in Python.
* **Role**: Excluded.

## K. Stale-target experiment
Testing the adversarial information-leak scenario (W0 vs W1):
If disruption hit-confirmation (W1) is exposed, an attacker can fire `WRITE` probes at stale coordinates. If it misses, W1 instantly tells the attacker the enemy moved—bypassing the detection radius restriction. Under W0, the attacker only learns the memory write succeeded, preserving the fog-of-war and keeping detection local.

## L. Recovery/stale-feedback experiment
A process issues a READ on tick 3, is disrupted on tick 4, and recovers on tick 5.
Using the minimal temporal contract, the process receives `current_tick = 5` and `previous_action_tick = 3`. The process trivially deduces that a disruption occurred and that the READ feedback is stale, requiring no new API constructs.

## M. Candidate contracts
* **C1 — Minimal temporal contract**: Uses basic action legality and tick provenance. (Selected).
* **C2 — Confirmed-combat contract**: Included hit confirmations. (Rejected due to information leaks).

## N. Compatibility boundary
**Agent API v2 is structurally required.**
Agent API v1 assumes a single contiguous execution stream. The v4 spatial model introduces multiple distributed anchors per entrant, requires routing via `self_process_id`, processes local detection arrays (`visible_enemy_anchor_addresses`), and manages discontinuous execution timelines (`last_callback_tick`). V1 cannot represent these mechanics cleanly.

## O. Replay boundary
* **Must be replayed**: Action choices, disruption triggers.
* **Can be recomputed**: Local detection arrays, `previous_action_applied`.
* **Private**: Agent memory, target prioritization.

## P. Complexity/information assessment
Contract C1 represents the absolute minimum engine-provided information required for deterministic play under v4 mechanics. It closes all identified scanning loopholes while fully equipping agents to handle temporal and spatial state.

## Q. Stage 6 decision
**Decision A — Minimal observation contract**

## R. Consolidation readiness
**Yes.** R0 through R6 have exhaustively established the core scheduler, spatial semantics, disruption risk, visibility rules, and observation boundaries required for the v4 game loop. The semantic foundation is ready.

## S. Git state
* **Commit SHA**: (To be committed).
* **Branch**: `v4-research`
* **Origin Sync**: Ready for push.

## T. Next boundary
**v4 Research Consolidation / Alpha Design Freeze preparation**
