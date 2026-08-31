# Bytefray v4 Research — R2: Dynamic Processes, Capacity Economics, and API Semantics

## A. Baseline qualification
Prior to research, two stale tests in `engine/tests/test_v4_process_semantics.py` (`test_process_entrant_action_quota_invariant`, `test_model_c_movable_anchor_and_move_cost`) failed because they instantiated single-entrant matches that terminated immediately after tick 1 due to the last-agent-standing rule. We corrected these by injecting a passive opponent entrant, restoring a clean test baseline.

## B. Existing process semantics
Currently, the v4 process harness (Model A) implements **fixed-process** semantics:
- **Process declaration**: Static list of `ProcessInstance` provided at entrant specification time.
- **IDs**: Hardcoded strings chosen by the agent (`proc_def`, `proc_scout`, etc.). Duplicate IDs are not prevented by the engine and alias feedback/state.
- **Quota**: Fixed at startup; total entrant budget is $Q=8$, distributed via `quota_share`.
- **Scheduler**: K=2 chunked round-robin, operating on the statically defined process list.
- **Lifetime**: Processes exist from match start to match end (or entrant death).
- **Position/reach**: Global arena reach (Model A). No independent physical anchor points.
- **Dynamic mechanics**: None. There is currently no API for runtime creation, destruction, or quota reallocation.

## C. Candidate models
We evaluated five conceptual models for dynamic process economy:
- **Model D1 (Free dynamic spawning)**: Entrant can split its fixed quota at runtime to spawn new processes with no engine-action cost.
- **Model D2 (Spawn action cost)**: Creating a process consumes a finite resource (e.g., an engine action like `SPAWN`).
- **Model D3 (Finite capacity / fixed overhead)**: Processes consume a base overhead plus their execution quota out of a maximum capacity cap.
- **Model D4 (Process slots)**: Entrant is limited to a finite number of active process contexts regardless of quota.
- **Model D5 (Persistent maintenance cost)**: Processes consume bandwidth or compute each tick merely by existing.

## D. Equivalence criteria
For dynamic processes to be genuinely strategic, they must provide an economic, spatial, or temporal opportunity that a monolithic controller—given an equivalent total resource budget—cannot reproduce. If an architecture difference merely organizes code differently but can be matched action-for-action by a monolith that internally simulates the cost, it is an **organizational distinction**, not a strategic mechanic.

## E. Spawn lifecycle
If spawning were implemented (e.g., immediate, next tick, or next scheduler cycle), it would introduce significant deterministic ordering complexity and exploit potential (e.g., action multiplication if a spawned process acts in the same tick). However, because a monolith can internally update its own time-slicing state machine precisely at the moment it returns a simulated "SPAWN" action, no lifecycle rule provides a temporal capability unique to multi-process API support.

## F. Capacity/allocation economics
Mutable quota and fixed overheads impose economic penalties on maintaining multiple contexts. If enforced via engine API, these penalties act as a strategic handicap on multi-process agents.

## G. Process retirement/failure
Allowing voluntary retirement to recover execution capacity creates identical strategic tradeoffs to a monolith simply reallocating its internal logic pathways from one role to another. 

## H. API candidates
A hypothetical API like `return SpawnProcess(...)` would consume an action to request process creation. However, exposing process management at the Agent API level conflates the agent's internal organizational paradigm with its external arena interactions.

## I. Prototype experiments & J. Monolithic falsification attempts
Because R1b definitively proved that a monolith can perfectly route its own previous-action feedback (the "mailbox" architecture), any dynamic cost model applied to the engine process API is isomorphic to a monolith that intentionally pays the same cost (by returning a `WAIT`/`NOP` or `SPAWN` token) and then internally updates its round-robin schedule. 
- **Under D1 (Free)**: A monolith time-slices freely.
- **Under D2-D5 (Costly)**: A monolith pays the action cost once and reallocates internally. 
Since Model A assumes global spatial reach and independent cursors, there is no spatial or physical capability tied to process identity that a monolith lacks. Consequently, dynamic process economies offer exactly zero irreducible strategic capability.

## K. Complexity/gameplay assessment
Implementing dynamic spawning, quota validation, lifecycle activation timing, and maintenance costs would dramatically increase engine complexity, scheduler edge cases (spawn storms, quota rounding exploits), and visualizer burden. Because these mechanics offer no genuine strategic depth that a time-slicing monolith doesn't already possess, they represent unnecessary engine complexity.

## L. Duplicate-ID resolution
Since we are rejecting dynamic processes, process definitions remain static. We recommend **Option A**: Engine-enforced unique process IDs per entrant at validation time, preventing aliasing loops.

## M. R2 decision
**Decision A — No dynamic process economy**
Dynamic spawning/allocation does not add enough strategy to justify the profound increase in engine and API complexity. Retain the fixed Model A semantics. Process identities are an organizational convenience, not an irreducible economic resource.

## N. Recommended next research
The next smallest research boundary is **Process spatial reach and physical anchor models (Models B and C)**. If processes have independent physical locations or movement constraints, they may finally provide a strategic capability that a single monolithic process (which would only possess a single spatial anchor) cannot reproduce.
