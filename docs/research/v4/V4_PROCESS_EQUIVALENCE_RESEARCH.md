# Bytefray v4 Research: Multi-Process Equivalence Challenge (R1b)

## Objective
The purpose of this research stage is to subject the R1 conclusion—that multi-process execution is a defining v4 feature—to an adversarial challenge. The core question is whether the multi-process semantics (Model A) create a genuine strategic capability (an engine-level mechanic), or if a carefully constructed monolithic Python agent can reproduce the behavior by internally time-slicing its action budget using per-role mailboxes.

## Methodology
We implemented a mailbox-aware monolithic version of the successful R1 `TripleProcessDefScoutAtk` entrant (`make_monolithic_triple_sim`). Both agents are bound by:
- Total action budget $Q=8$
- Chunked deterministic scheduler $K=2$
- Identical role implementations (`_defender_logic`, `_scout_logic`, `_coordinated_attacker_logic`)

We ran empirical match matrices comparing the Multi-Process Triple against the Monolithic Triple, both against baseline ecologies and head-to-head. We extracted deterministic action traces to inspect `ProcessObservation` state transmission.

## Findings

### 1. Falsification of Capability Gap
Under the tested fixed-process Model A semantics, independently scheduled process identities do not provide an information capability that cannot be reproduced by a sufficiently designed monolithic controller. 

The engine delivers previous-action feedback synchronously to the monolithic callback before executing and recording the next action. A monolithic dispatcher can therefore preserve feedback in role-local mailboxes and reproduce the genuine multi-process observation/action sequence exactly without consuming additional engine actions.

### 2. Experimental Defect in Original Equivalence Assertions
The first monolithic implementation routed incoming feedback to the virtual role scheduled next instead of to the virtual role that emitted the preceding action. This discarded already-available information and created an artificial divergence.

Once corrected to use proper mailbox-routing:
- The monolithic agent matched the multi-process agent action-for-action and observation-for-observation exactly across all evaluated configurations.
- Final scores, arena states, territory, and survival states were perfectly identical across permutations and seed values.

### 3. API Semantic Distinctions
The isolation of `ProcessObservation` feedback by `(agent_id, process_id)` is specifically an artifact of the v4 research process harness. It does not generalize to the canonical Agent API v1 (`Observation.last_read`), which possesses different persistence semantics.

## Conclusion and Decision

**R1b CLOSED — MONOLITHIC EQUIVALENCE CONFIRMED FOR TESTED MODEL A SEMANTICS**

The original hypothesis of fundamental inequivalence is falsified for the fixed-process Model A configuration.

### Proven
Exact equivalence is guaranteed for the tested fixed-process Model A R1b configuration. A single python agent can perfectly reproduce multi-process timing and logic.

### Not Proven
Universal equivalence is not proven for future process models involving dynamic spawning, process economics, movement, different capacity semantics, or other untested features. These remain subjects for future research.
