# Bytefray v4 Spectator Phase 0.5 — Foundation Qualification

## 1. Initial Repository State and Phase 0 Baseline
- **HEAD Inspected**: Verified branch is at `a30a88a` (Phase 0 output).
- **Working Tree**: Clean.
- **Phase 0 Diff Verification**: Verified `a30a88a` only touched `tools/spectator_analyzer.py` and `docs/research/v4/V4_SPECTATOR_PHASE_0_RESEARCH.md`. Engine code was 100% pristine.

## 2. Independent Validation of Semantic Events
Phase 0 proposed several semantic events. This phase rigorously challenged them against the engine code:

| Event | Phase 0 Definition | Phase 0.5 Correction / Validation | Status |
|---|---|---|---|
| `PROCESS_CREATED` / `DEATH` | PID appears/disappears | **REJECTED**. v4 processes are static (capacity limit 8, no dynamic spawning). Absence never happens; processes are persistent. | **REMOVED** |
| `CORE_DISRUPTION` | `disrupted` flips to `True` | **VALIDATED**. Engine models temporary `D=1` exact-anchor disruption correctly. | **GO** |
| `DETECTION_GAINED` / `LOST` | Process-level proximity | **CORRECTED**. Engine visibility is *entrant-wide*. Furthermore, disrupted processes *cannot see*. Phase 0 failed to account for this. | **REMEDIATED** |
| `HOSTILE_WRITE` | Write inside initial core | **CORRECTED**. Initial core is only `CORE_SIZE=8`, but Bytefray is territorial. A write is hostile if it overwrites *any* cell currently owned by an opponent. | **REMEDIATED** |
| `AGENT_ELIMINATED` | Event type `forfeit`/`death` | **VALIDATED**. | **GO** |
| `VICTORY` | `record_type: result` | **VALIDATED**. | **GO** |

## 3. Challenge: HOSTILE_WRITE
Phase 0 claimed an attack could be defined by a write inside the initial core. 
- **Finding**: This was fundamentally wrong. `AgentState.region` in v4 is typically `(0, 0)`, and even if accurate, it only covers 8 bytes. Bytefray focuses on territory.
- **Remediation**: The Spectator Analyzer was rewritten to maintain a deterministic `owner_map` incrementally across all ticks. `HOSTILE_WRITE` is now defined as: "A memory diff where the writing entrant differs from the previous owner of that cell." This is semantically honest and robust.

## 4. Challenge: CORE_DISRUPTION Causality
Phase 0 claimed causal attribution was directly derivable from the memory diff on the disrupted process's anchor.
- **Finding**: **Deterministic but indirect.** The engine assigns `disrupted_until_tick` when an opponent writes exactly on the `target_addr == other_p.position`. By examining the `owner` of the `MemoryDiff` at that address on that tick, we can indirectly but deterministically trace the attacker.

## 5. Challenge: Detection Semantics
Phase 0 claimed detection was process-to-process.
- **Finding**: **Inaccurate**. `process_runtime.py:_visible_enemy_anchors` collapses spatial facts for the entire entrant. We rewrote the analyzer to evaluate `can_see` on an entrant-to-entrant basis (if *any* undisrupted sensor of A overlaps *any* anchor of B).

## 6. READ / Fog of War Architectural Decision
Phase 0 noted that `READ` observations are omitted from Schema 4. We evaluated Alternatives:
- **Option A (Spatial Only)**: Honest but incomplete.
- **Option B (Persist raw reads)**: Would bloat canonical replay significantly (6,000+ reads per match) and pollute the canonical spatial model.
- **Option C (Knowledge-change events)**: Requires engine to track subjective knowledge, contaminating simulation logic.
- **Option D (agent_trace)**: The engine architecture *already* plans for `bytefray.agent_trace` (per `REPLAY_SCHEMA.md`).
- **Decision**: Adopt **Option A** for the basic Spectator Cam ("Sensor Fog"), and recommend **Option D** (`agent_trace` artifact) for perfect-fidelity perspective when needed. Do not bloat `Schema 4`.

## 7. Event Density vs Drama
Corpus analysis revealed that our corrected `HOSTILE_WRITE` generates thousands of events. E.g., `v4_claimer` vs `v4_scout` triggered ~1400 hostile writes.
- **Finding**: High event density does **not** inherently equal "drama". An undefended march through territory creates the exact same event density as a desperate skirmish.
- **Recommendation**: Event aggregation (e.g., `ENGAGEMENT_START`) must be handled by the **Spectator Director** layer using debouncing and bidirectional-write thresholds, separate from the factual pipeline.

## 8. Full-Suite Regression Failure
The regression suite failed on `test_live_run_group_analysis_covers_every_roster_entrant`.
- **Provenance**: We verified the Phase 0 commit strictly altered `docs/` and `tools/`. We then ran the test in total isolation (`.venv/Scripts/pytest engine/tests/test_agent_evaluation_group_analysis_integration.py`) and it **PASSED in 11.11s**. 
- **Conclusion**: The test fails under the full suite due to global state pollution (likely caching in `EvaluationService` or V1 mock agent conflicts introduced in alpha2). It is completely unrelated to spectator telemetry. 
- **Status**: **UNRESOLVED** (Sent to Independent Review).

## 9. Arbitrary-Tick Seeking
- **Finding**: Reconstructing visibility or ownership at tick 2500 requires processing all prior memory diffs to build the `owner_map` and visibility state machine.
- **Conclusion**: A linear scan in Python takes milliseconds, which is trivial. However, a web client or PySide6 slider would stutter. Spectator-only non-canonical checkpoints should be considered eventually.

## 10. Required Final Decisions
- **Semantic Spectator Pipeline**: **GO**. (Remediated: Definitions corrected, implemented objectively).
- **Perspective / Fog Cam**: **SPATIAL-ONLY**. (Rely on Sensor Fog for default replays; defer absolute knowledge to `agent_trace`).
- **Spectator Director**: **GO WITH EVENT-AGGREGATION PREREQUISITE**.
- **Fight Night**: **GO WITH PREREQUISITES**.
- **Color Commentator**: **RESEARCH FURTHER**.

## 11. Independent Review Queue

### IR-01: Regression Test Pollution
- **Claim**: `test_live_run_group_analysis_covers_every_roster_entrant` fails under the full test suite but passes in isolation.
- **Evidence**: `pytest` output logs vs isolated run logs.
- **Why uncertain**: The exact global state bleeding (ruleset caching vs process pool) wasn't root-caused because engine modifications were out of scope.

### IR-02: Spatial Detection Precision
- **Claim**: Entrant-wide detection correctly excludes disrupted sensors, but `circular_dist <= reach` accurately matches the engine's internal checks.
- **Evidence**: `process_runtime.py:_visible_enemy_anchors`.
- **Why uncertain**: Engine boundary edge cases (inclusive vs exclusive) around `arena_size // 2` might drift in Python floating/integer math versus renderer presentation.

## 12. Final Architecture
`Factual Semantic Pipeline -> Spatial Perspective Cam -> Temporal Aggregator (Director) -> Fight Night`
