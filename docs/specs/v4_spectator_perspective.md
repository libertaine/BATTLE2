# Bytefray v4 Spectator Perspective Projection Specification

## 1. Scope

This specification defines the research contract for reconstructing an API-v2
entrant's perspective from one validated canonical replay and agent trace pair.
It is an observational analysis contract. It does not change the simulation,
Agent API v2, replay schema 4, trace schema 2, or any historical Ruleset.

The authoritative pipeline is:

```text
canonical replay + API-v2 trace
              |
          verify_pair
              |
          derive_events
              |
   perspective projection from ordered trace observations
```

The semantic-event stream and perspective projection have different jobs.
Events answer what factually happened. Projection answers what one entrant had
a defensible basis to know at a callback boundary.

## 2. Source authority

- The canonical replay is authoritative for tick-boundary world memory,
  ownership, process state, entrant lifecycle, termination, and result.
- The API-v2 trace is authoritative for callback order, the exact
  `ObservationV2` delivered to each process, requested actions, and applied
  outcomes.
- Phase 3 semantic derivation is authoritative for its qualified factual event
  vocabulary and deterministic `(tick, sequence)` order.
- This projection is authoritative only for deterministic reconstruction of
  engine-delivered entrant knowledge under the rules below.

The trace binding is an integrity association, not tamper authentication of the
trace body. Projection preserves the Phase 3 `verify_pair` precondition and
runs Phase 3 derivation consistency checks before producing output.

## 3. Phase 1 reconciliation boundary

The replay-only Phase 1 analyzer remains a historical research and broadcast
utility. It is not an API-v2 perspective source.

- Its replay-geometry `DETECTION_GAINED` and `DETECTION_LOST` infer named
  viewer/target entrant pairs at tick boundaries. They are removed from the
  authoritative perspective path because API v2 supplies only anonymous anchor
  addresses at callback time.
- `FOREIGN_OWNERSHIP_OVERWRITE` overlaps Phase 3 `HOSTILE_WRITE`; the former
  remains replay-only, while the latter is the validated-pair factual event.
- `CORE_DISRUPTION` overlaps Phase 3 `PROCESS_DISRUPTED`; the former remains
  replay-only, while the latter preserves exact trace-order causality.
- Phase 1 aggregation remains replay-only until a later Director phase defines
  a new aggregation contract over Phase 3 events.
- Shared strict schema-4 replay loading is reused.

No Phase 1 public or experimental schema is silently renamed or removed.

## 4. Projection input and validation

The supported high-level API accepts replay and trace paths. It must:

1. call `verify_pair()`;
2. run `derive_events()` so existing replay/trace consistency checks remain a
   hard precondition;
3. reject an entrant not named by the validated binding; and
4. consume only that entrant's `DecisionRecordV2` observations, in trace file
   order, when evolving entrant knowledge.

A mismatched, unbound, truncated, non-v2, or replay-inconsistent pair must not
produce a projection through the supported API.

## 5. Projection time

The canonical perspective timeline is sequence-aware. Trace decision file
position is the global callback ordinal; no new trace field is required.

Each selected-entrant callback produces one frame. The frame applies the
observation delivered before that callback's action. Other entrants' callbacks
do not directly update the selected entrant's knowledge.

Tick queries use these precise boundaries:

- `START`: state after selected-entrant callbacks with `current_tick < N`;
- `END`: state after selected-entrant callbacks with `current_tick <= N`.

`END` is the future tick-based renderer default. A tick with no selected-
entrant callback carries the latest delivered state unchanged and reports that
the tick was unsampled. Silence is never converted into an empty observation.

## 6. Anonymous spatial contacts

One contact represents only this fact:

> At a callback boundary, the engine supplied an occupied enemy anchor address.

Contacts are keyed by address. They never contain entrant identity, process
identity, process count, role, or a synthetic track identity. Co-located enemy
processes and entrants collapse to the one address the engine supplied.

An address disappearing and later reappearing is renewed anonymous occupancy
at that address. It is not evidence that the same enemy returned. A READ owner
at the same address identifies the sampled memory cell's owner, not the contact.

## 7. `UNKNOWN`, `CURRENT`, and `STALE`

For an arena address:

- `UNKNOWN`: no delivered observation has ever listed it as enemy occupancy;
- `CURRENT`: it appears in the selected entrant's latest delivered visibility
  sample;
- `STALE`: it appeared in an earlier delivered sample and is absent from a
  later delivered sample.

`CURRENT` means current as of the entrant's latest engine sample. It makes no
claim about canonical world truth after that callback.

Every selected-entrant callback replaces the entrant-wide current contact set.
Previously current omitted addresses become stale. A stale address seen again
becomes current without acquiring entity continuity. No callback causes no
status transition. Unknown addresses are queried rather than materialized.

This deliberately differs from Phase 3 detection events, which use the union of
all observations in one sampled tick to produce quieter factual events. Those
events cannot define callback-current state.

## 8. Multi-process semantics

Spatial visibility is entrant-wide at each callback because the runtime uses
all currently eligible friendly processes as sensors. The latest callback from
any selected-entrant process therefore replaces the entrant-wide contact set.

The following remain process-local:

- `self_process_id`, `self_anchor`, and `self_reach`;
- previous action feedback;
- READ feedback; and
- callback history.

Projection retains the latest delivered self sample for each declared process.
An older sibling-process sample is historical; it must not be described as
canonical current position. Own process declarations may be shown because the
entrant created them. Opponent declarations are not projected.

## 9. READ-derived knowledge

A READ's applied result is produced after the callback returns. It becomes
engine-delivered knowledge only when the same process later receives an
`ObservationV2` containing the previous action feedback.

Projection correlates that observation with the immediately preceding trace
decision for the same `(entrant, process)` and records:

- requested address;
- normalized address when the READ applied;
- sampled byte value;
- sampled cell owner, which may be `None`;
- the action/sample callback point; and
- the later delivery callback point.

A successful final READ with no later same-process callback is not delivered
knowledge and is absent from projected READ history. A sibling process callback
does not deliver it.

If the later observation reports that the READ did not apply, projection may
record failed action feedback but must not fabricate a cell sample or expose an
internal rejection reason the observation did not carry.

READ entries are immutable historical samples from the moment of delivery.
They are never silently updated from later canonical writes and are never
labelled current world memory. Cell owner identity must not be joined to an
anonymous spatial contact.

## 10. Own state and reconstructed memory

Projection is deterministic memory of facts supplied by the engine, plus the
entrant's own recorded action history needed to correlate feedback. It is not
literal Python-agent cognition. An agent may ignore, forget, or transform the
same inputs internally.

Own core base and size, and process anchor/reach samples, come only from the
selected entrant's observations. Canonical replay positions are not substituted
when a process has not supplied a newer self observation.

## 11. Semantic events and audience

Filtering Phase 3 events by `visible_to` is not sufficient to construct a
perspective:

- detection events intentionally coalesce a tick's observations;
- READ events are timestamped at action application, before feedback delivery;
- ordinary, self-owned, unowned, and rejected READs have no semantic event;
- self samples and previous-action feedback have no semantic event.

Phase 3 events remain factual annotations for broadcast and later presentation
work. Entrant state is reconstructed directly from ordered bound observations.
`EFFECTIVE_MOVE` remains state-important and presentation-salience-low, but own
position knowledge still comes from a later self observation.

## 12. Terminal and omniscient boundary

Hostile writes, core-cell loss, disruption, another entrant's elimination or
forfeit, match termination, and victory are not imported into entrant execution
perspective merely because replay or semantic derivation knows them.

A future viewer may display canonical match-result metadata in a separate
broadcast/presentation overlay. That overlay must not retroactively alter the
entrant's callback knowledge.

The existing Phase 3 derivation is the omniscient event path. Perspective
projection does not replace it.

## 13. Determinism and seeking

- Frames preserve trace file order.
- Addresses, processes, declarations, contacts, and serialized fields use
  explicit total-key ordering.
- Projection identity excludes wall-clock timing and diagnostics.
- Repeated inputs and entrant identity produce byte-identical serialized
  projection across supported hash seeds.
- Direct tick or decision seeking must equal sequential folding to the same
  boundary.

Projection may precompute compact callback deltas and fold them for arbitrary
seek. Checkpoints or caches require measured need; they are not part of this
contract.

## 14. Provenance

Research/debug output must identify why a fact is present:

- contacts name the source decision index and observation field;
- stale contacts name the callback where later absence changed status;
- READ samples name both the action/sample and delivery decision indices; and
- own process samples name their source observation.

Provenance is diagnostic metadata and is not required in a future presentation
wire format.

## 15. Compatibility and future renderer seam

This layer lives in `battle_engine` beside replay-domain spectator derivation.
It depends only on existing engine replay/trace/derivation contracts and the
standard library. It does not import the client or app.

`ReplaySession` remains canonical-replay-only. A future renderer may load a
parallel immutable perspective projection and query it using the session's
current tick. Phase 4 does not implement renderer mode management, Fog Cam,
Director pacing, Fight Night presentation, or commentary.
