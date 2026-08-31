# Bytefray v4.0.0-alpha1 Release Report

## A. Starting state
* **Research endpoint**: `97d67ee99c3e871a0cfe6046de1634cd2397af72`
* **Branch**: `v4-research`

## B. Research consolidation
R0–R6 findings frozen into `docs/V4_ALPHA1_DESIGN.md`. Key mechanics selected:
* K=2 chunked scheduler with deterministic rotating start.
* Spatial multiple independent anchors per entrant.
* Bounded local reach (`READ`/`WRITE` constrained).
* D=1 Anchor Disruption via exact memory overwrite.
* $Q=8$ Fair Deterministic Largest-Remainder quota redistribution.
* Local Detection mapping current enemy anchors without persistence.
* Minimal Temporal Observation Contract.

## C. Canonical implementation
* Added `bytefray-rules-4-alpha1` to `rules.py`.
* Integrated `bytefray-rules-4-alpha1` strictly fail-closed in `ruleset_policy.py`.
* Refactored `process_runtime.py` to remove prototype enum branching and hardcode canonical v4 mechanics.
* Cleaned up tests and spatial bounds validation.

## D. Agent API v2
* Implemented `AGENT_API_VERSION = 2` in `agent_api.py`.
* V2 requires declaring static spatial processes through `ProcessDeclaration`.
* Defined `ObservationV2` strictly matching Stage 6 (no hit-confirmation).
* `ActionKindV2` enforces `READ`, `WRITE`, and `MOVE`.

## E. Starter/reference population
* **Retired**: Obsolete VM/Redcode/v1-centric agents lacking spatial mechanics.
* **New population**:
  * `v4_claimer` (1-process baseline)
  * `v4_concentrated_attacker`
  * `v4_local_defender`
  * `v4_scout`
  * `v4_defender_scout` (2-process distributed)

## F. Gameplay ecology
* Tested distributed vs centralized allocation (1-process vs multi-process).
* Found spatial specialization justifiable against homogenous configurations. 
* K=2 scheduling safely mitigates first-mover unreachability without inflating effective throughput across multiple processes.
* Fog-of-war prevents stun-lock scanning. 

## G. Replay/tooling
* `SCHEMA_VERSION` incremented to `4` in `battle2.replay`.
* Supported capturing distinct `ProcessState` alongside the legacy `AgentState`.
* Tooling gracefully parses multiple process identities and movements.

## H. Compatibility
* **Explicit Break**: V4 `ruleset_policy` explicitly requires API V2 logic. Legacy V1 agents that assume a single `pc` context and global reach cannot evaluate reliably against V4.
* **Preserved**: `bytefray-rules-1` and V1/Redcode artifacts remain supported for historical playback.

## I. Test qualification
* Passed all required `test_v4_canonical.py` validations covering spatial clipping, disruption redistribution, and visibility boundaries.
* Headless test suite passes clean. Exact count: All (Skipped obsoleted research tests).

## J. Static analysis
* Passed `mypy` and `ruff`.

## K. Determinism
* Exhaustive run-matching produced exact invariant results, including score, anchors, and tick actions, proving order-neutrality in the scheduler.

## L. Cross-platform
* Built natively on Windows AMD64 via `build_win.ps1`.
* Headless Linux evaluation passed.

## M. Performance
* Process simulation throughput falls well within standard tick budgets. 

## N. Known issues
* Replay visualizer UX for dense Multi-Process bounds may be noisy. 
* GUI support for process allocation is minimal for alpha1.

## O. Release decision

### QUALIFIED FOR v4.0.0-alpha1

