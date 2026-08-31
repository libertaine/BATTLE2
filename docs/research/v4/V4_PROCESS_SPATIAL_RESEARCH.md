# Bytefray v4 Research — R3 Process Spatial Reach (Corrected)

This document contains the corrected primary research report for the R3 investigation into spatial process semantics, updating previous findings based on independent review.

## A. Initial repository state
- **Branch**: `v4-research`
- **HEAD**: `3d83017 docs: reorganize current research and historical reports`
- **Origin Sync**: Up to date with `origin/v4-research`.
- **Worktree**: Clean prior to the generation of `v4_r3_spatial_challenge.py` and this report.

## B. Corrections from independent review
The initial R3 report overstated the cost of monolithic movement (claiming a 60-MOVE/75% tax as optimal) and conflated spatial utility with unpriced initial deployment (processes starting in opposite zones). This update:
1. Re-evaluates monolithic movement using optimal boundary-aware pathing (yielding exactly 2 MOVE actions per transition for the principal geometry, rather than 3+).
2. Mandates "paid co-located deployment," forcing multi-process agents to start alongside monolithic agents and expend actions to traverse to remote zones.
3. Separates the objective into two regimes: a "Continuing Bounded-Response" objective (which requires sustained traversal) versus a "Final-Ownership" batched objective (which does not).

## C. Defined strategic objective
The principal strategic test is defined as a **Continuing Bounded-Response Objective**:
> During every complete simulation tick, the entrant must execute at least one successful legal WRITE in each of two spatially separated target regions ($D > 2R$).

- **Targets**: Address 120 and Address 920.
- **Pass Criteria**: Both targets must register a write from the entrant during the required ticks.
- **Duration**: 10 ticks.

## D. Paid co-located deployment
In the corrected primary experiment, both the multi-process entrant and monolithic entrant begin at initial position 100.
- **Multi-process Deployment**: Spends 3 `MOVE` actions initially to deploy its second process to the 920 region boundary. After deployment, both processes remain securely anchored near their respective local objectives.
- **Monolithic Deployment**: Spends the same initial 3 `MOVE` actions to establish boundary position, but must subsequently oscillate if it intends to service both zones repeatedly.

## E. Strong monolithic control
The monolithic `MonoCont` controller was upgraded from its original naive center-pathing to use **boundary-aware pathing**. To service 920 from 120, it does not move to 920 itself; it calculates the shortest circular path to the nearest cell *within reach* of the target (e.g., target 920's boundary at 970). It aggressively optimizes its $Q=8$ budget to traverse the gap exactly once per tick, spending the remainder of the tick farming writes in the destination zone. 

## F. Geometric lower bound
For two targets separated by circular distance $D$ with reach $R$, the gap between legal reach regions is:
$$G = D - 2R$$
With maximum displacement per MOVE $M$, a transition requires at least:
$$\lceil G / M \rceil \text{ MOVE actions.}$$

**Principal Scenario Values:**
- $D = 224$ (distance between 120 and 920)
- $R = 50$
- $G = 124$
- $M = 64$
- **Minimum Transition Cost** = $\lceil 124 / 64 \rceil = 2$ MOVE actions.

## G. Continuing-response result
Under Model C (Movable Anchors), across 10 ticks ($Q=80$ total actions):
- **Multi-Process**: Executed **77 writes** and **3 moves** (initial deployment). Both zones serviced simultaneously.
- **Monolith**: Executed **59 writes** and **21 moves** (initial deployment + continuous boundary-to-boundary oscillation). 

While the monolith *can* achieve the objective, it must pay a recurring structural traversal tax (21 moves vs 3 moves) that mathematically diminishes its useful combat output compared to an entrant with persistent distributed legal action origins.

## H. Negative control
A secondary batched `MonoBatched` controller was tested against a **Final-Ownership** objective (only owning the targets at tick 10). It defended 120 for 9 ticks, traversed once (3 moves), and captured 920 on tick 10.
- **Result**: 77 writes, 3 moves.
- **Conclusion**: Spatial presence provides no significant advantage over a monolith when the objective allows high-latency batching. The value of Model C processes is exclusively derived from low-latency, continuing-response scenarios.

## I. Geometry sensitivity
The capability gap rests entirely on the geometric threshold:
- **If $D \le 2R$**: A single stationary/intermediate anchor can service both targets. Spatial distribution provides no reach exclusivity. The monolith requires 0 movement overhead.
- **If $D > 2R$**: The gap $G$ requires active physical traversal. Traversal cost directly scales with the geometry of $G$, proving the effect is a universal consequence of the spatial model, not a cherry-picked scenario artifact.

## J. Economic interpretation
Under the $Q_{total}=8$ invariant, multi-process identity forces a strict economic trade-off: **action concentration versus spatial coverage**.
- 1 process gets 8 callbacks per tick in one region.
- 2 processes get 4 callbacks per tick in separated regions. 
This balanced fractional division of CPU time implies that independent spatial processes are already naturally priced by the game engine's quota distribution. The research finds no compelling evidence to artificially require an additional process-spawning cost at this time.

## K. Validation
- **Challenge Script**: `v4_r3_spatial_challenge.py` (executed, assertions passed).
- **Core Unit Tests**: 5 v4 semantics tests passed.
- **Mypy**: Engine and client type-checked clean (0 issues).
- **Ruff**: Executed on R3 files, all lint findings resolved (0 errors).

## L. Corrected R3 conclusion
R3 establishes that independent movable anchors provide an engine-enforced spatial capability unavailable to a one-anchor monolithic controller: after paying deployment cost, multiple processes can retain legal action origins in separated reach regions. A one-anchor controller can match one-time outcomes cheaply through batching, but must repeatedly spend MOVE actions when the strategic objective requires continuing or latency-bounded service in multiple separated regions.

The value arises from **persistent distributed spatial presence**, not process identity, observation isolation, or literal simultaneous execution.

## M. Final decision
**Decision C — Movable-anchor spatial processes**

Co-located deployment is fairly priced, deterministic assertions validate the exact traversal gap, the continuing-response objective presents a deeply compelling gameplay scenario, and the required implementation complexity is justified by the strategic depth gained.

## N. Git state
- **Commit SHA**: (To be committed as part of R3 closure)
- **Branch**: `v4-research`
- **Origin Sync**: Fully synchronized. 

## O. Next research boundary
**Stage 4 — Process Disruption.** 
Since processes now possess physical anchors that grant powerful distributed presence, we must determine if those anchors themselves need to be attackable (vulnerable) via targeted overwrites to allow opponents to break remote coverage without chasing the physical anchor. 
*(Do not begin this next step).*
