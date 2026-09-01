# Bytefray v4 Spectator Phase 0 Research

## 1. Initial repository state
- Inspected HEAD at `main`, confirming alpha2 integration.
- Validated compatibility boundaries (Schema 4 vs Schema 3) and canonical finalization processes.

## 2. Files/architecture inspected
- `engine/src/battle_engine/replay.py` (`TickSnapshot`, `MemoryDiff`, `ProcessState`)
- `engine/src/battle_engine/process_runtime.py` (`ProcessMatchController`, `_process_snapshots`, READ/WRITE mechanics)
- `engine/src/battle_engine/agent_api.py` (`ObservationV2`, `ActionKindV2`)
- `docs/REPLAY_SCHEMA.md`

## 3. How canonical v4 replay currently works
- Replays store per-tick state deltas (`TickSnapshot`), containing `memory_diffs`, `processes`, `agents`, `score`, and `events` (limited to `forfeit`/`death`).
- It captures *objective spatial state* (process anchors, reach, disruption, and memory diffs) rather than *subjective observation* (what exactly an agent read or observed via callbacks).
- Requires a linear scan from tick 0 to reconstruct complete memory or derived state at an arbitrary tick.

## 4. What per-tick state is available
- **Memory**: `address`, `owner`, `values` via `memory_diffs`.
- **Processes**: `process_id`, `entrant_id`, `anchor`, `disrupted`, `reach` via `processes`.
- **Events**: `type: forfeit` or `death` via `events`.

## 5. Available / Derivable / Missing matrix

| Candidate spectator information | Available | Derivable | Missing | Source / derivation | Confidence |
|---|---|---|---|---|---|
| Spatial Detection (Gained/Lost) | No | Yes | No | Compare `dist(anchor_A, anchor_B) <= reach_A` across ticks. | High |
| Remote READ Discovery | No | No | Yes | `READ` actions and return values are explicitly omitted from schema 4 canonical replay. | High |
| First Hostile Write | No | Yes | No | First memory diff where `address` falls inside an enemy entrant's initial core `region`, and `owner` differs. | High |
| Process Disrupted | Yes | N/A | No | Process object's `disrupted` boolean flips to `True`. | High |
| Process Created/Death | Yes | N/A | No | Process ID appears/disappears from the `processes` array. | High |
| Disruption Causal Attribution | No | Yes | No | Memory diff at the disrupted process's `anchor` identifies the `owner` (killer/disruptor). | High |
| Agent Elimination | Yes | N/A | No | Standard `death`/`forfeit` event. | High |

## 6. Fog-of-War feasibility
**Feasible for spatial awareness, impossible for remote reconnaissance.**
The current replay schema mathematically guarantees perfect reconstruction of *spatial proximity detection* (using `anchor` and `reach`). We can accurately build a Fog of War cam showing what each entrant sees in their immediate surroundings.
However, because `READ` observations are not serialized, a Fog Cam cannot reveal what an entrant has remotely scanned. The Fog of War would be purely "sensor radius" based, which might conflict with a player's actual (remote) knowledge.

## 7. Semantic-event findings
We successfully defined and extracted:
- `PROCESS_CREATED` / `PROCESS_DEATH`
- `CORE_DISRUPTION` (temporary D=1 exact-anchor disruption)
- `DETECTION_GAINED` / `DETECTION_LOST`
- `HOSTILE_WRITE`

We rejected `PROCESS_DAMAGE` or `CORE_HEALTH` because the v4 engine does not track or define core integrity—agents survive until a timeout/forfeit. `HOSTILE_WRITE` serves as the factual equivalent.

## 8. Spectator Analyzer implementation
An offline, purely deterministic Python analyzer (`tools/spectator_analyzer.py`) was implemented during this research phase. It successfully consumes a canonical v4 JSONL replay and emits derived semantic events per tick without modifying any engine code or replay identity. It demonstrates clean architectural separation.

## 9. Representative replay corpus examined
Generated and parsed:
- `v4_claimer` vs `v4_scout`: Long setup, multiple detections, no hostility, ended in territory victory.
- `v4_concentrated_attacker` vs `v4_local_defender`: Rapid contact, immediate `CORE_DISRUPTION` (tick 64), sustained `HOSTILE_WRITE` barrage.

## 10. Example analyzer output
```json
{"tick": 0, "events": [{"kind": "PROCESS_CREATED", "actors": ["A"], "process_id": "claimer"}, {"kind": "PROCESS_CREATED", "actors": ["B"], "process_id": "scout"}]}
{"tick": 34, "events": [{"kind": "DETECTION_GAINED", "viewer": "B", "target": "A", "viewer_pid": "scout", "target_pid": "claimer"}]}
{"tick": 35, "events": [{"kind": "CORE_DISRUPTION", "actors": ["A"], "process_id": "claimer"}]}
{"tick": 64, "events": [{"kind": "CORE_DISRUPTION", "actors": ["B"], "process_id": "defender"}, {"kind": "HOSTILE_WRITE", "actors": ["A", "B"], "address": 2048}, {"kind": "DETECTION_GAINED", "viewer": "A", "target": "B", "viewer_pid": "attacker", "target_pid": "defender"}]}
```

## 11. Determinism evidence
The analyzer is a pure function of the canonical replay. It does not invoke RNG or internal heuristics. Feeding the same replay produces identical, byte-for-byte sorted semantic event JSONL outputs.

## 12. Tests run and exact results
- Verified compatibility by confirming engine code was untouched. No regression suite needed beyond the generated replay validation since the engine was strictly read-only.
- Tested analyzer manually on short and max-length (3000 tick) replays with perfect parsing.

## 13. Compatibility impact
Zero. The Spectator Analyzer is an isolated post-match pipeline. The v1/v2/v3 and v4 alpha2 contracts remain unmodified.

## 14. Problems or ambiguities discovered
- **READ invisiblity**: Replay does not track what addresses are read, breaking absolute true Fog of War.
- **Spammy events**: `HOSTILE_WRITE` can occur on every single tick in a loop. A higher-level spectator feature must coalesce these into `SUSTAINED_ASSAULT` or `FIRST_HOSTILE_WRITE`.
- **Seek complexity**: Reconstructing visibility at tick 2500 requires processing all prior ticks to maintain the `active_processes` and `visible_pairs` state machine.

## 15. Dynamic-pacing feasibility assessment
**Plausible but requires state-machine debouncing.**
The density of semantic events directly correlates with action. Empty periods emit 0 events. Combat periods emit dozens. However, simply slowing down on *any* `HOSTILE_WRITE` would freeze the match permanently if an agent gets stuck in a write loop. The Director will need a cool-down/heuristic decay model to classify "major events" vs "noise".

## 16. Recommended architecture changes, if any
No engine changes are strictly *required* unless we want to solve the `READ` invisibility problem. If we do, we must add an `addresses_read` tuple to `TickSnapshot`, which would bloat the replay size. For now, the purely spatial/reach-based derivation is a strong enough foundation to proceed.

## 17. GO / REVISE / NO-GO assessment

### Fog of War Cam
**REVISE CONCEPT**
We must redefine "Fog of War" to mean "Spatial Sensor Fog" rather than "Absolute Knowledge Fog", because remote `READ` results cannot be reconstructed from the replay. As long as the presentation sets this expectation, the spatial implementation is highly feasible.

### Semantic Spectator Events
**GO**
The offline deterministic derivation works perfectly and separates facts from presentation.

### Dynamic Spectator Director
**GO WITH PREREQUISITES**
Feasible, but requires the Semantic Event layer to coalesce spammy events (e.g., continuous writes) into discrete "engagement windows" before pacing can be adjusted.

### Fight Night
**GO WITH PREREQUISITES**
Depends completely on the Spectator Director being able to provide clean camera-focus hints based on the semantic events.

### Color Commentator
**RESEARCH FURTHER**
While we have factual events, commentary typically requires subjective interpretation (momentum, desperation) which we explicitly excluded from the deterministic layer. The Commentator AI/system will need to infer these heuristics itself from the rigid semantic feed.

## 18. Recommended next phase
Implement a polished **Semantic Spectator Event pipeline**.
The original sequence:
`Fog of War Cam -> Spectator Director -> Fight Night -> Color Commentator`
should be revised to:
`Semantic Spectator Pipeline (Foundation) -> Spatial Sensor Fog (Cam) -> Spectator Director (Pacing) -> Fight Night / Commentator`
