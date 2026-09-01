# Bytefray v4 API-v2 Agent Trace Specification

## 1. Overview
The API-v2 agent trace (`bytefray.agent_trace`, schema version 2) is an optional, deterministic artifact recording the exact interaction history between the v4 engine and API-v2 agents. 
While the canonical replay (`battle2.replay`) records the objective physical match history (memory diffs, process status), the trace records the subjective engine-to-agent callbacks (`ObservationV2`, `AgentAction`, applied results).

It is explicitly separated from the canonical replay to ensure match identity and execution performance remain unaffected by dense telemetry. It enables future deterministic reconstruction of the "entrant perspective" (e.g., Fog of War analysis).

## 2. Record Model
The trace contains:
1. `HeaderRecordV2`: Identity, ruleset, agents, `schema_version: 2`.
2. `ResetRecord`: Sent during `reset()`.
3. `DeclarationRecord`: Sent when capturing `declare_processes()`.
4. `DecisionRecordV2`: Emitted for every `act()` callback.
5. `BindingRecord`: A required final footer linking the trace to its canonical replay.

## 3. Emission Points
- **Reset**: Emitted inside `ProcessMatchController.from_python_entrants` before the agent's `reset()` callback is invoked.
- **Declaration**: Emitted immediately after `declare_processes()` is returned.
- **Decision**: Emitted synchronously within `ProcessMatchController.run` during process scheduling.
- **Diagnostic**: Embedded in any of the above if the agent raises an exception or returns a malformed structure.
- **Binding**: Emitted at the end of the match in `NativeMatchService` after the canonical replay is flushed and its SHA-256 digest is calculated.

## 4. Callback Ordering and Identity
Callbacks are ordered exactly as they execute in the v4 scheduler.
Identity is strictly maintained via the tuple `(entrant_id, process_id)`. `process_id` is local to the entrant.
Ordering relies implicitly on append-order, which corresponds to `tick` and the deterministic process scheduler rotation.

## 5. ObservationV2 Capture
The entire `ObservationV2` is captured losslessly in `TraceObservationV2`. No fields are dropped or projected into v1 structures. 
- Deterministic: `current_tick`, `last_callback_tick`, `previous_action_tick`, `self_process_id`, `self_anchor`, `self_reach`, `own_core_base`, `own_core_size`, `visible_enemy_anchor_addresses`, `previous_action_applied`, `previous_read_value`, `previous_read_owner`.

## 6. READ / WRITE / MOVE Coverage
`TraceActionV2` captures the exact fields returned by the agent (`kind`, `operand`, `value`).
Since READ actions do not mutate memory and are excluded from the canonical replay, the trace preserves the critical knowledge acquisition step. WRITE and MOVE capture their requested intent.

## 7. Requested vs. Applied Action Model
A process's requested `AgentAction` frequently differs from the applied outcome due to disruption, invalid syntax, spatial constraints, or quota limits.
Each `DecisionRecordV2` will contain an `applied_result` object capturing:
- `status`: One of `APPLIED`, `REJECTED_INVALID`, `REJECTED_OUT_OF_REACH`, `REJECTED_QUOTA`, `DISRUPTED`, `EXCEPTION`.
- `normalized_address`: The circular-wrapped address actually executed (if applicable).
- `read_value`, `read_owner`: The outcome of a READ.

## 8. Diagnostics and Nondeterministic Fields
Semantic identity excludes diagnostic/nondeterministic fields:
- `wall_time_ms` (Host timing)
- `diagnostic` (Exception stack traces, host paths)
These fields are stored for debugging but must not influence semantic identity.

## 9. Replay Binding
A `BindingRecord` must be appended as the final record in the trace. It contains:
- `match_id`
- `replay_sha256`
- `ruleset_id`
- `entrant_identities` (ordered list)

Consumers (like Replay Viewer or analyzers) **must reject** the trace if it fails to perfectly match the loaded canonical replay bytes and metadata.

## 10. Compatibility and Versioning
The trace will use `TRACE_SCHEMA_VERSION = 2`.
Existing API-v1 trace tooling is explicitly required to reject version 2 via the `schema_version` header check, rather than attempting silent lossy parsing. 
V1 tracing code will be cleanly separated or versioned alongside V2, avoiding mutating the API-v1 `DecisionRecord`.

## 11. Size and Retention Model
At V4 alpha2 rates (max 8 processes, 2 K-quota, ~3000 ticks = ~48,000 decisions), uncompressed JSONL traces can reach ~30MB.
Trace generation is strictly opt-in (`--trace`). When generated, consumers are responsible for retention and compression. The artifact does not automatically compress itself during execution to avoid latency.

## 12. Failure Isolation
If trace writing fails (e.g., disk full) during a match, the `TraceWriter` will silence the OS error and permanently disable itself for the remainder of the match. The simulation must continue completely unaffected.

## 13. Determinism
Match behavior, scheduler decisions, and outcome must remain mathematically identical whether tracing is enabled or disabled.
