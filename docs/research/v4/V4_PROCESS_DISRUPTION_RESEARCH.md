# Bytefray v4 Research — R4 Process Disruption and Spatial Risk

This document concludes the R4 research on process disruption, answering whether the spatial capabilities established in R3 require direct counterplay.

## A. Baseline qualification
- **Starting Commit:** `ad442af56d9fe435a06c3a157e4115f1e721422a` (R3 closure).
- **Test Baseline:** The `engine/tests/test_v4_process_semantics.py` and `engine/tests/test_v4_r3_spatial.py` suites passed (6 tests).

## B. Existing disruption semantics
The research harness currently implements a Stage 4 disruption prototype:
- **Trigger:** An opponent executing a valid `WRITE` to the exact cell occupied by a process anchor.
- **Effect:** The targeted process skips execution (`disrupted_until_tick = current_tick + duration`).
- **Quota:** The scheduler naturally falls back to any non-disrupted processes within the same entrant to fulfill the chunk's quota.
- **Stacking:** Non-cumulative; repeated hits merely refresh the expiration tick.

## C. Counterplay requirement
In R3, spatial anchors provided *persistent distributed legal action origins*—allowing a process to remain in a remote zone indefinitely without ongoing traversal costs. Without direct disruption, an opponent cannot sever this remote presence directly; they must either tank the damage, reclaim arena cells manually, or attack the distant core. Direct process interaction is required to make spatial deployment a two-sided contest rather than a unilateral, permanent advantage.

## D. Candidate disruption models
- **X0 No disruption:** Baseline; insufficient counterplay to R3's persistent reach.
- **X1 Temporary localized disruption:** Process disabled for $N$ ticks; recovers automatically. (Selected prototype).
- **X2 Reach suppression:** Process loses reach but can still execute. Unnecessarily complex.
- **X3 Forced displacement:** Opponent knocks the anchor. Conceptually confusing on a circular ring.
- **X4 Process destruction:** Permanent loss of process. High complexity, forces reopening R2 spawning economics.

## E. Targeting and visibility
Disruption is triggered via an ordinary `WRITE` action to the anchor's cell. This elegantly ensures the attack consumes action quota (1 action) and respects the attacker's own spatial reach limits.

## F. Quota semantics
The prototype scheduling logic revealed a profound mechanic: **Reallocated Quota**.
When a process is disrupted, its scheduled execution opportunities are dynamically reallocated to any surviving, non-disrupted processes belonging to the same entrant. The entrant's total execution capacity ($Q=8$) is perfectly preserved as long as one process survives.

## G. Temporary-disruption experiments
A deterministic adversarial challenge (`v4_r4_disruption_challenge.py`) evaluated a two-process entrant (Base + Scout) versus a dedicated Attacker targeting the Scout's anchor.
- **Outcome:** The attacker successfully stun-locked the Scout for 32 process-ticks.
- **Effect on Victim:** The victim lost its remote spatial coverage. However, its total quota was flawlessly preserved. The Base process received 36 actions (instead of its usual 20), compensating for the Scout's suppression.
- **Analysis:** The attacker spent its own actions to force the victim to exchange *coverage* for *concentration*. 

## H. No-disruption control
Without disruption, the attacker has no structural mechanism to evict the Scout from the remote zone. The attacker would have to overwrite the Scout's writes infinitely, tying up both agents' quotas in a stalemate. Disruption allows the attacker to actually disable the origin of the threat.

## I. Repeated-disruption/stun-lock analysis
Stun-locking a process requires the attacker to continuously spend actions writing to the anchor. Because the victim's quota is reallocated, the attacker is paying an ongoing opportunity cost simply to constrain the victim's spatial footprint. This is a fair and strategic trade, lacking any infinite/free exploits.

## J. Recovery semantics
Automatic recovery based on a tick-timer is vastly superior to explicit recovery actions. It introduces no new API commands, keeps the process cleanly dormant, and avoids bookkeeping penalties.

## K. Destruction comparison
Permanent process destruction (Model X4) would mandate complex process replacement, dynamic spawning (rejected in R2), and bookkeeping overhead. Temporary disruption (Model X1) provides all necessary spatial counterplay and tactical depth without reopening any closed architectural questions.

## L. Distributed-versus-concentrated tradeoff
Process vulnerability inadvertently solves a major design balance problem by introducing a beautiful structural tradeoff:
- **Monolith (Concentrated):** Enjoys maximal local action concentration ($Q=8$) and a minimal attack surface (1 anchor). However, if its single anchor is disrupted, it has no fallback processes and catastrophically forfeits its entire execution quota for the duration.
- **Multi-process (Distributed):** Exposes a massive attack surface (multiple anchors) and suffers lower local concentration ($Q=4$). However, it is structurally resilient; if one anchor is disrupted, its quota falls back to the survivors, naturally converting lost coverage back into action concentration.

## M. Complexity/gameplay assessment
Temporary localized disruption requires zero new API actions, integrates flawlessly with the existing chunked scheduler, demands minimal engine state (`disrupted_until_tick`), and creates deep, intuitive tactical counterplay.

## N. R4 decision
**Decision B — Temporary localized disruption**

Spatial process anchors must be temporarily suppressible via normal memory writes. This minimal-complexity mechanic establishes a profound risk/reward paradigm for process distribution and cleanly counters the permanent-reach advantage established in R3.

## O. Recommended next research
**Stage 5 — Anchor Visibility and Information.** 
Determine whether anchor coordinates are public engine metadata, locally observable within reach boundaries, or entirely hidden (requiring memory reconnaissance) to an opposing agent.
*(Do not begin this next step).*

---
**Provenance:**
- Execution: `v4_r4_disruption_challenge.py` (Asserts quota reallocation and monolith suppression).
- Baseline tests: `engine/tests/test_v4_process_semantics.py` + `test_v4_r3_spatial.py` (6 tests passed).
- Branch: `v4-research`
