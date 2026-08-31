# Bytefray v4.0.0-alpha1 Design Freeze

This document is the authoritative implementation contract for `v4.0.0-alpha1`. It consolidates the semantics established during the R0–R6 research phases and strictly defines the core gameplay loop, process model, and API boundaries.

## 1. Scheduler Semantics
* **Algorithm**: Deterministic chunked scheduling.
* **Chunk Size**: `K = 2` (actions per process chunk).
* **Entrant Rotation**: Deterministic rotating start based on the original immutable seat/entrant order.
* **Ticks**: One simulation tick corresponds to one complete entrant-quota pass.
* **Mortality**: Dead entrants are skipped.
* **Quota**: Fixed total action quota ($Q=8$) per entrant.

## 2. Process Model
Processes are execution loci with persistent spatial positions. They do not independently own territory, score, or match-win state; ownership remains entrant-scoped.
* **Roster**: Fixed process roster declared at match start.
* **Identity**: Stable engine identity; `process_id` must be unique per entrant.
* **Spatial Presence**: Each process has an independently persistent movable anchor and a bounded local reach.
* **Lifecycle**: No runtime spawning and no permanent process destruction. 
* **Economy**: Total entrant action throughput remains fixed regardless of the process count.

## 3. Action Model
The programmable action vocabulary is minimal:
* `READ`
* `WRITE`
* `MOVE`
* *Excluded*: `ATTACK`, `DISRUPT`, `SCAN`, `SPAWN`, or explicit energy/recovery actions. Process disruption is purely an emergent effect of `WRITE`.

## 4. Spatial Semantics
* **Reach**: `READ` and `WRITE` targets are strictly bounded by `self_reach`.
* **Addressing**: `READ` and `WRITE` operands are absolute arena addresses;
  `MOVE` is the only relative operand and is a signed delta from the acting
  process anchor.
* **Deployment**: Processes begin co-located at the entrant's core starting position. Spatial deployment is earned solely through `MOVE` actions.
* **Movement**: `MOVE` consumes a normal action, alters only that process's anchor, uses deterministic maximum displacement bounds, and normalizes/wraps around the circular arena.

## 5. Disruption Semantics
* **Trigger**: A legal enemy `WRITE` to the exact normalized anchor address of a live enemy process.
* **Duration**: $D=1$ (a hit during tick $N$ suppresses the target for the
  remainder of tick $N$; it is eligible again at tick $N+1$).
* **Co-location (Blast)**: All live enemy processes occupying that address are disrupted by the `WRITE`. Friendly co-located processes are unaffected.
* **Recovery**: Automatic tick-based expiry; requires no recovery action.
* **Validity**: Dead entrants/processes cannot be disrupted.

## 6. Disrupted-Quota Semantics (Fair Redistribution)
* **Conservation**: The entrant's total $Q$ remains fully available as long as at least one positive-share eligible process survives.
* **Redistribution**: Quota normally belonging to disrupted processes is redistributed proportionally across the eligible surviving processes.
* **Algorithm**: Deterministic largest-remainder allocation.
* **Invariance**: Tie-breaking uses stable process identity. Process list ordering must not change the mathematical allocation. If no processes are eligible, the entrant executes zero callbacks.

## 7. Visibility Semantics (Local Deterministic Detection)
Immediately before an eligible process callback:
* The engine computes live enemy anchors within detection range of *any* eligible friendly process.
* **Radius**: Equals the relevant friendly process's action reach.
* **Result**: Emits normalized, unique, deterministically sorted addresses.
* **Limits**: Information is strictly current-only. The engine does *not* expose enemy process IDs, names, roles, counts, shares, reach values, disruption state, or action history. Agent code owns its memory of last-known coordinates.

## 8. Observation Contract
The Agent API uses the **Minimal Temporal Observation Contract**.
* **Temporal Provenance**: `current_tick`, `last_callback_tick`, `previous_action_tick`.
* **Self Identity**: `self_process_id`, `self_anchor`, `self_reach`.
* **Core Info**: `own_core_base`, `own_core_size`.
* **Detection**: `visible_enemy_anchor_addresses`.
* **Feedback**: `previous_action_applied` (boolean), `previous_read_value`, `previous_read_owner`.
* **Excluded**: Disruption-hit confirmation, attacker ID, enemy identities/roles.

## 9. WRITE Information Boundary
A `WRITE` uniquely reports whether the arena action legally applied to memory (`previous_action_applied`). It explicitly does **not** confirm if an enemy process was disrupted. This maintains the fog-of-war and preserves the value of local detection.

## 10. Temporal Provenance
A process recovering from disruption deduces the event objectively by comparing `current_tick`, `last_callback_tick`, and `previous_action_tick`. Explicit `was_disrupted` flags are purposefully omitted.

## 11. Explicit Alpha1 Deferrals
The following concepts are not part of `v4.0.0-alpha1`:
* Dynamic spawning, process replication, permanent destruction.
* Process maintenance costs or resource currencies.
* Probabilistic fog of war.
* Dedicated `SCAN`, `ATTACK`, or `DISRUPT` commands.
* Engine-maintained enemy tracking.
* Broad balance tuning and ranking-system redesign.
