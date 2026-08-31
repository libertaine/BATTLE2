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
- The monolithic agent matched the multi-process agent action-for-action across all evaluated configurations.
- Final scores, arena bytes, ownership/territory, and survival/termination outcome (winner, reason, and per-agent alive state) were exactly identical across every tested opponent archetype and both entrant seat orders (focal-first and opponent-first) -- `tools/v4_r1b_equivalence_challenge.py`.

This is exact deterministic differential testing, not a statistical study: `Config.seed` is not consumed anywhere in the process runtime, and no role logic here uses randomness, so there is no independent-sample dimension to report -- each (opponent, seat order) combination has exactly one possible outcome, and it matched.

### 3. API Semantic Distinctions
The isolation of `ProcessObservation` feedback by `(agent_id, process_id)` is specifically an artifact of the v4 research process harness. It does not generalize to the canonical Agent API v1 (`Observation.last_read`), which possesses different persistence semantics.

### 4. Duplicate `process_id` Is Unvalidated (Future Process-API Item)
`ProcessMatchController` does not reject or otherwise validate that an entrant's `process_id` values are unique. Internally, per-tick quota accounting and last-observation feedback are keyed by `(agent_id, process_id)`; two `ProcessInstance` entries sharing an ID within the same entrant silently alias onto the same counter and feedback slot, and in practice the first-declared process with the duplicated ID claims the shared quota every tick while the later one(s) are never invoked (characterized in `test_duplicate_process_id_aliases_and_starves`, `engine/tests/test_v4_process_semantics_r1b.py`). This is not an engine capability finding -- it is an unvalidated corner of the research-only process API that a future process-API design should address explicitly (reject, or define aliasing semantics), rather than something this closure relies on or endorses.

## Conclusion and Decision

**R1b CLOSED — MONOLITHIC EQUIVALENCE CONFIRMED FOR TESTED MODEL A SEMANTICS**

The original hypothesis of fundamental inequivalence is falsified for the fixed-process Model A configuration.

### Proven
Exact equivalence is guaranteed for the tested fixed-process Model A R1b configuration. A single python agent can perfectly reproduce multi-process timing and logic.

### Not Proven
Universal equivalence is not proven for future process models involving dynamic spawning, process economics, movement, different capacity semantics, or other untested features. These remain subjects for future research. Duplicate-`process_id` handling within a single entrant (Finding 4) is also unvalidated and is an open item for any future process-API design, not a property this closure establishes.
