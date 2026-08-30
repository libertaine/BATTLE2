# Bytefray v4 Research: Multi-Process Equivalence Challenge (R1b)

## Objective
The purpose of this research stage is to subject the R1 conclusion—that multi-process execution is a defining v4 feature—to an adversarial challenge. The core question is whether the multi-process semantics (Model A) create a genuine strategic capability (an engine-level mechanic), or if a carefully constructed monolithic Python agent can perfectly reproduce the behavior by internally time-slicing its action budget.

## Methodology
We implemented a monolithic version of the successful R1 `TripleProcessDefScoutAtk` entrant (`make_monolithic_triple_sim`). Both agents are bound by:
- Total action budget $Q=8$
- Chunked deterministic scheduler $K=2$
- Identical role implementations (`_defender_logic`, `_scout_logic`, `_coordinated_attacker_logic`)

We ran empirical match matrices comparing the Multi-Process Triple against the Monolithic Triple, both against baseline ecologies and head-to-head. We also extracted deterministic action traces to inspect `ProcessObservation` state transmission.

## Findings

### 1. Empirical Match Results
In identical matchups against single-process baselines (Claimer, Defender) and head-to-head, the Monolithic Triple exhibited perfectly symmetric macro-behavior with the Multi-Process Triple. In head-to-head, both agents achieved exactly 1114.0 mean score and 136.0 mean territory across all permutations and seeds, with identical action, read, write, and pass distributions.

However, this symmetric outcome was an artifact of the specific `_scout_logic` scanning stride (128 cells) and the `_coordinated_attacker_logic` fallback sweep stride (16 cells) missing each other's 8-cell cores due to arena size modulo arithmetic. 

### 2. Tracing the Observation Pipeline (The Strategic Divergence)
Underneath the macro-symmetry, the action traces revealed a fundamental and unbridgeable capability gap between the two architectures.

The engine provides observation results (such as `read_owner` and `read_val`) in the `ProcessObservation` of the *immediately following* action for a given `process_id`.

**In the Multi-Process Architecture:**
The engine segregates `last_obs_results` by `process_id`. When the Scout process issues a `READ` on its second slot of Tick $T$, the result is safely preserved in the engine's state until the Scout's first slot of Tick $T+1$.
Trace extract (Multi-Process):
```text
Tick  1 | Proc: proc_scout | LastKind: ActionKind.READ | ReadOwner: None  | Action: read
Tick  2 | Proc: proc_scout | LastKind: ActionKind.READ | ReadOwner: None  | Action: read
```

**In the Monolithic Architecture:**
There is only one `process_id`. The monolithic agent must execute its sub-roles sequentially: Defender (4) → Scout (2) → Attacker (2).
When the Scout issues a `READ` on action slot 6, the next time the agent is called is action slot 7 (Attacker). The Attacker does a `WRITE`. On the next tick, the agent is called for action slot 0 (Defender). The Scout's read result is permanently lost because the engine overwrote the agent's single observation buffer with the result of the Attacker's `WRITE`.
Trace extract (Monolithic):
```text
Tick  1 | Proc: proc_monolithic | LastKind: ActionKind.READ | ReadOwner: None | Action: write  (Attacker overwrites buffer)
Tick  2 | Proc: proc_monolithic | LastKind: ActionKind.NOP  | ReadOwner: None | Action: read   (Scout receives Defender's NOP)
Tick  2 | Proc: proc_monolithic | LastKind: ActionKind.READ | ReadOwner: None | Action: read   (Scout receives its own read)
```

As a result, the Monolithic Scout only successfully processes *one* read per tick, cutting its effective observation bandwidth in half compared to the Multi-Process Scout. The monolith cannot preserve pipelined observation states across its internal role transitions.

## Conclusion and Decision

**Decision B: Multi-process execution is a genuine engine-level strategic mechanic.**

The isolation of `ProcessObservation` buffers by `process_id` creates an independently timed observation advantage. A monolithic agent cannot safely pipeline asynchronous actions (like `READ` -> `EVAL`) if those pipelines must be interrupted by other roles requiring immediate engine actions. The chunked K=2 scheduler, combined with process-isolated observation buffers, grants multi-process entrants strategic capabilities that are mathematically impossible for a monolith to replicate under the same action budget.
