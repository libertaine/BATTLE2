# Bytefray v4 Spectator Research Phase 5 — Perspective Cam Renderer Integration

## Verdict

**PASS AFTER REMEDIATION.**

This verdict supersedes the original **PASS** claimed by the implementation
session. That claim did not correspond to any durable Git state: the Phase 5
work was never committed, and part of the engine implementation was
subsequently destroyed by an external editor write. The engine cursor in this
repository is a *reconstruction*, not the originally written code. Section 8
records the incident, the reconstruction, the independent review, and the
remediation that followed. The qualification figures below are from the
reviewed and remediated commit, not from the original session.

Phase 5 successfully integrated the qualified Phase 4 entrant perspective projection (`PerspectiveProjection`, `PerspectiveState`) into the interactive Pygame replay viewing experience as an independent, non-intrusive **Perspective Cam**.

The integration strictly visualizes the qualified entrant knowledge model without inventing synthetic enemy tracks, continuity, or omniscient leakage.

| Area | Classification |
|---|---|
| Retained `PerspectiveCursor` | **RECONSTRUCTED, THEN INDEPENDENTLY QUALIFIED** (§8.3) |
| `battle_client.perspective` lifecycle | **IMPLEMENTED AND QUALIFIED** |
| Broadcast vs Perspective Mode separation | **QUALIFIED** |
| `ReplaySession` runtime isolation | **CONFIRMED** |
| Anonymous Contact Rendering (CURRENT vs STALE vs UNKNOWN) | **QUALIFIED** |
| Sensor Reach Boundary Visualization | **QUALIFIED** |
| Delivered READ Sample Visualization | **QUALIFIED** |
| Cell Owner vs Contact Separation | **QUALIFIED** |
| HUD Top Band & View Mode Controls | **QUALIFIED** |
| Inspector & Footer Status Integration | **QUALIFIED** |
| Diagnostic Debug Overlay (`F3` / `D`) | **QUALIFIED** |
| CLI `--trace` & `--perspective` options | **QUALIFIED** |
| Designer Companion Trace Auto-Detection | **QUALIFIED** |
| Negative Leakage & Geometry Regressions | **PASSED** |
| Full Repository Test Suite | **PASS (2721 passed, 26 skipped, 2 deselected)** |
| **Phase 5 overall** | **PASS** |

### PASS criteria

| # | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | ReplaySession remains canonical-replay-only | **PASS** | §2.1 |
| 2 | Pure fallback to Broadcast mode on missing/invalid trace | **PASS** | §2.2 |
| 3 | Retained incremental cursor (removes the per-frame $O(\text{history})$ re-fold) | **PASS** | §3, §8.6 |
| 4 | No invented enemy tracks, entrant IDs, or inferred continuity | **PASS** | §4.1 |
| 5 | Clear visual differentiation for CURRENT, STALE, and UNKNOWN | **PASS** | §4.2 |
| 6 | Contact age communicated cleanly without probability decay | **PASS** | §4.3 |
| 7 | No-callback intervals preserve state without spontaneous decay | **PASS** | §4.4 |
| 8 | Latest delivered own-process samples used instead of canonical truth | **PASS** | §4.5 |
| 9 | Cell owner separated from spatial contact identity | **PASS** | §4.6 |
| 10 | Terminal match state isolated from entrant perspective | **PASS** | §4.7 |
| 11 | Keyboard dispatch for perspective cycling (`V`/`P`), direct (`1`–`9`), debug (`F3`/`D`) | **PASS** | §5.1 |
| 12 | CLI flags `--trace` and `--perspective` | **PASS** | §5.2 |
| 13 | Designer launches companion `trace.jsonl` automatically if present | **PASS** | §5.3 |
| 14 | Negative leakage tests confirm no `target_entrant_id` in state | **PASS** | §6.1 |
| 15 | All mandatory regressions passed (geometry, co-location, stale, lag) | **PASS** | §6.2 |

---

## 1. Repository Baseline

Recorded before Phase 5 modifications:

| Fact | Value |
|---|---|
| Repository | `D:\Projects\BATTLE2` |
| Remote | `https://github.com/libertaine/Bytefray.git` (`origin`) |
| Baseline Commit | `c5afddae9e089ecfecc8991ccf7b8cc335fadcb8` |
| Development Branch | `v4-spectator-phase5-development` |

---

## 2. Architectural Boundary and ReplaySession Isolation

### 2.1 ReplaySession Independence
`ReplaySession` remains strictly canonical-replay-only. It loads and steps through `ReplayHeader`, `TickSnapshot`, and `MatchResult` without any dependency on `agent_trace` or `spectator_perspective`.

### 2.2 Client-Side Perspective Lifecycle
Perspective Cam management is housed in `battle_client.perspective.PerspectiveManager`.
- When a replay is loaded with a valid companion trace, `PerspectiveManager` constructs an immutable `PerspectiveProjection` and retained `PerspectiveCursor` for each entrant.
- If no trace is supplied, the file does not exist, or the trace is mismatched or corrupt, `PerspectiveManager.available` becomes `False`. The viewer operates in standard `BROADCAST` mode without interruption or degradation.

---

## 3. Retained Incremental Playback Cursor (`PerspectiveCursor`)

During sequential 60fps replay playback, performing an $O(N)$ historical fold
of all callbacks on every display frame would introduce rendering stutter on
longer matches. On the Phase 4 large fixture that fold costs **30.2 ms**, which
alone exceeds a 16.7 ms frame budget.

`PerspectiveCursor` was added to
`engine/src/battle_engine/spectator_perspective.py` (exposed via
`PerspectiveProjection.cursor()`). It maintains incremental accumulators
(`_contacts`, `_current`, `_reads`, `_own`, `_core_base`, `_core_size`) and
folds only the frames a query newly crosses.

What it actually guarantees, stated precisely (see §8.6 for measurements):

- **Repeated queries at the same tick and boundary are genuinely $O(1)$** — the
  cached `PerspectiveState` is returned by identity (0.0003 ms measured).
- **Forward movement costs only the newly crossed frames, plus a state
  materialization proportional to accumulated delivered READ history.** It is
  *not* $O(1)$ per frame: `read_history=tuple(self._reads)` re-copies the whole
  accumulated READ list on every query, so sequential cost grows through a
  match (0.0154 ms/tick early → 0.0630 ms/tick late on the large fixture).
- Forward movement is **not** restricted to `tick == current_tick + 1`. The
  cursor locates its target with `bisect` over the frame timeline and advances
  incrementally across any forward jump.
- Backward steps and backward seeks reset the accumulators and replay forward
  from the start of the callback history to the target tick.

The earlier description of this cursor as "$O(1)$ amortized cost per frame"
with `tick == current_tick + 1` monotonic advancement was **inaccurate on both
points** and has been corrected here. The correct statement is that the cursor
removes the per-frame $O(\text{history})$ re-fold, which is what the viewer
needed; at the 3,000-tick scale it is a ~480x improvement over re-folding.

Equivalence between `PerspectiveCursor.state_at_tick` and
`PerspectiveProjection.state_at_tick` is verified exhaustively — every tick on
both boundaries over a multi-process, multi-entrant, co-located match, under an
adversarial seek pattern, and against mutable aliasing — in
`test_perspective_cursor_sequential_and_seeking_equivalence`,
`test_perspective_cursor_matches_projection_across_every_tick_and_boundary`,
`test_perspective_cursor_results_never_mutate_under_later_advancement`, and
`test_perspective_cursor_rejects_queries_outside_the_projection_range`.

---

## 4. Visual Language and Knowledge Presentation

### 4.1 Strict Anonymity for Enemy Contacts
In accordance with Agent API v2 minimal temporal semantics:
- Contacts are rendered as anonymous radar contacts.
- No entrant ID, process ID, process count, or synthetic track ID is ever displayed or stored.
- Multiple enemy processes co-located at the same address produce a single anonymous contact blip.

### 4.2 State Distinctions: CURRENT vs STALE vs UNKNOWN
- **CURRENT Contacts**: Rendered as bright amber/gold radar blips with a central pip and `"CONTACT"` badge.
- **STALE Contacts**: Rendered as ghosted/subdued rings with an age badge (`T-{age}`).
- **UNKNOWN Cells**: Completely unannotated by enemy contact markers.

### 4.3 Delivered Historical READ Samples vs Cell Ownership
- READ results are rendered as subtle memory cell tints using the sampled cell owner.
- The inspector panel clearly distinguishes memory cell owner samples (`[DELIVERED READ] byte=0x.. cell_owner=..`) from spatial sensor contacts (`[CURRENT CONTACT]` / `[STALE CONTACT]`).

### 4.4 Own-Process State and Reach Visualization
- Own processes are rendered at their latest delivered positions (`OwnProcessKnowledge.anchor`).
- Sensor reach radius is visualized as a translucent boundary circle around each active process anchor.

### 4.5 Terminal Match State
- Match completion, victor, and termination reasons remain part of the authoritative broadcast HUD banner (`MATCH COMPLETE — Winner: ...`).
- Entrant perspective state never hallucinates terminal results or elimination truth prior to authoritative match closeout.

---

## 5. Controls, HUD, and Tooling Integration

### 5.1 Keyboard Dispatch
Keyboard dispatch in `battle_client.player` and `battle_client.renderers.pygame_renderer`:
- `V` / `P`: Cycle perspective view (`BROADCAST` $\to$ `ENTRANT A` $\to$ `ENTRANT B` $\to$ `BROADCAST`).
- `1`–`9`: Direct selection (`1` for Broadcast, `2` for Entrant 1, `3` for Entrant 2, etc.).
- `F3` / `D`: Toggle diagnostic perspective debug overlay.

### 5.2 Top Band & Footer HUD
- Top band header dynamically reflects the active view mode (e.g., `View: ENTRANT A (Hunter) · PERSPECTIVE CAM` or `View: BROADCAST [V to switch]`).
- Footer displays active perspective sample freshness (`Sampled: tick ...` or `Unsampled this tick (last: tick ...)`).

### 5.3 CLI & Designer Auto-Detection
- `battle_client.cli` supports `--trace <path>` and `--perspective <entrant_id>`. If `--trace` is omitted, `trace.jsonl` alongside `replay.jsonl` is auto-detected.
- `app.services.engine_commands.open_pygame_client_direct` automatically passes `--trace` when a companion trace is present.

---

## 6. Qualification and Regression Verification

### 6.1 Negative Leakage Tests
Explicit negative assertions in `client/tests/test_perspective.py` (`test_negative_target_entrant_id_leakage_prohibited`) verify that:
- `ContactKnowledge` contains no `target_entrant_id`, `entrant_id`, `process_id`, or `track_id`.
- Knowledge projections never leak un-sampled enemy positions or IDs.

### 6.2 Regression Suite Summary
All mandatory Phase 5 regressions passed:
1. `test_perspective_manager_broadcast_fallback_on_missing_trace`: Clean degradation on missing trace.
2. `test_perspective_manager_lifecycle_and_mode_cycling`: Deterministic mode transitions.
3. `test_negative_target_entrant_id_leakage_prohibited`: Zero metadata leakage.
4. `test_colocation_ambiguity_and_geometry_trap`: Circular address folding and co-location deduplication.
5. `test_read_owner_separated_from_spatial_contact`: Cell owner / contact separation.
6. `test_stale_contact_transition_and_age`: Accurate staleness transition and age math.
7. `test_no_callback_interval_preserves_state`: Preserved state across unsampled ticks.
8. `test_perspective_cam_keyboard_dispatch`: Complete key action mapping.
9. `test_perspective_top_band_and_footer_rendering`: HUD top band, inspector, and debug overlay smoke.

### 6.3 Full Suite Validation
```text
pytest client/tests:
386 passed, 12 skipped, 2 deselected

Full pytest suite:
2721 passed, 26 skipped, 2 deselected in 276.53s

mypy engine/src/battle_engine:
Success: no issues found in 99 source files

mypy client/src/battle_client:
Success: no issues found in 13 source files

ruff check client engine app:
All checks passed!
```

---

## 7. Next Steps & Roadmap Progression

1. **Spectator Pipeline Roadmap Status**:
   - Phase 1: Semantic Spectator Pipeline (**QUALIFIED**)
   - Phase 2: API-v2 Agent Trace Specification & Implementation (**QUALIFIED**)
   - Phase 3: Trace Derivation & Pair Verification (**QUALIFIED**)
   - Phase 4: Entrant Perspective Projection (**QUALIFIED**)
   - Phase 5: Perspective Cam Renderer Integration
     (**QUALIFIED AFTER REMEDIATION** — see §8)

---

## 8. Save-Conflict Incident, Reconstruction, and Independent Review

This section is deliberately durable. The original Phase 5 qualification did
not correspond to a committed Git state, so the history of how this code
reached the repository matters for anyone auditing it later.

### 8.1 What happened

Phase 5 was implemented by an external agent session which reported PASS
against an uncommitted working tree. Before anything was committed, an external
VS Code `WorkspaceEdit` reverted
`engine/src/battle_engine/spectator_perspective.py` from its Phase 5 state back
to its Phase 4 state, deleting roughly 174 lines — `PerspectiveCursor` and
`PerspectiveProjection.cursor()`. The loss was confirmed behaviorally:
`client/tests/test_perspective.py` failed to import `PerspectiveCursor`, and
`engine/tests/test_v4_spectator_perspective.py` dropped to 19 passed / 1 failed.

Exact recovery from editor history, VS Code Local History, and session
transcripts all failed. **The cursor was therefore reconstructed, not
recovered.** The reconstruction was guided by the surviving Phase 5 tests, the
surviving client implementation, the Phase 4 projection contract, and the
documented cursor API. It differed from the lost version by approximately one
line (173 vs 174 insertions), which is evidence of similarity only and is not
proof of equivalence.

All Phase 5 files were then committed in an emergency safety checkpoint,
`3608c4fa8b2d6b9a4b6a9c94451c5205f0d27c9f`, on branch
`v4-spectator-phase5-development`. A second external `WorkspaceEdit` during
recovery had inserted a redundant nested conditional into
`client/src/battle_client/perspective.py` (ruff `SIM102`); because the recovery
session did not own that edit, it was preserved in the checkpoint rather than
silently changed.

### 8.2 A third external revert, found at review time

The independent review opened on a **dirty working tree at `3608c4f`**, with
five files modified. The modifications were not edits but systematic reversions
of Phase 5 back to Phase 4: `app/services/engine_commands.py`,
`client/src/battle_client/cli.py`, and
`client/src/battle_client/renderers/pygame_renderer.py` were **byte-identical to
the Phase 4 baseline** (`--trace`/`--perspective` stripped, Designer trace
forwarding stripped, the entire Perspective Cam render path deleted), and
`client/tests/test_perspective.py` had had an entrant removed from the
co-location fixture. The five modification timestamps spanned 63 seconds, which
is machine-speed, not human-speed.

Two other AI coding agents were found running against this checkout: the
OpenAI Codex VS Code extension (`codex.exe`, with `code_mode_host=true`) and
Google Cloud Code (`cloudcode_cli.exe`). These are the most probable source of
all three "unexplained `WorkspaceEdit`" events.

Because the checkpoint was already in Git, no work was lost. The working tree
was restored from `3608c4f` after the tree was observed stable across three
hash snapshots spanning two minutes, and the reverted state was preserved as a
patch for forensics. **Recommendation: do not run other AI coding agents against
this checkout during a qualification pass.**

### 8.3 Independent audit of the reconstructed cursor

The reconstruction was audited against `_fold_frames`, the reference fold, and
found faithful. `PerspectiveCursor._fold_one` is a line-for-line transcription
of the reference loop body. Two preconditions the reference fold does not need
were checked and hold:

- The cursor's `bisect` requires frames sorted by tick. `project_perspective`
  **enforces** this, rejecting a trace with `"selected-entrant callbacks are out
  of tick order"`, so the invariant is guaranteed rather than assumed.
- `bisect(key=)` requires Python 3.10, and `pyproject.toml` sets
  `requires-python = ">=3.10"`. Valid, but exactly at the supported floor.

**No mutable-state aliasing was found.** Although the cursor folds through
retained mutable accumulators, every returned value is copied out at
construction: `ContactKnowledge` is frozen and reads accumulator fields by
value, `_own` entries are replaced rather than mutated, and `read_history` is a
fresh tuple. `PerspectiveState` is frozen with tuple fields, so even the
identity-shared cached state cannot be mutated by a caller. This is now locked
by `test_perspective_cursor_results_never_mutate_under_later_advancement`.

### 8.4 Remediation applied by the review

Committed as `898485328b21951233be63332528493020d579d4`:

| Finding | Disposition |
|---|---|
| `SIM102` redundant nested conditional (external edit) | Removed; behavior-preserving, the duplicate reassigned the same mode under the same guard |
| `--perspective` / `--trace` could fail **silently** | CLI now reports the reason on stderr for a missing trace, a mismatched pair, and an unknown entrant id |
| Cursor equivalence proven only by one sampled test | Replaced with exhaustive equivalence, adversarial seeks, aliasing guard, and range validation |
| Grid render path covered only by a hand-built mock | Added a real-projection renderer test proving the perspective grid paints none of an unobserved enemy's canonical cells |

The reconstructed engine cursor, the renderer, `hud_layout.py`, and the Designer
integration were **not modified** by the review.

### 8.5 Findings reported but deliberately not changed

- `client/src/battle_client/perspective.py` catches
  `(SpectatorPairError, PerspectiveError, Exception)`. The tuple is redundant —
  `Exception` already subsumes the other two — but the behavior (a viewer that
  survives any projection failure) is intended, and narrowing it would require
  touching imports for no functional gain.
- `PerspectiveManager.__init__` eagerly builds a projection **and** cursor for
  every entrant. On the 3,000-tick fixture this blocks for **3.5 s** before the
  viewer opens, and scales with entrant count. Correct, but a real startup cost
  on large replays; lazy per-entrant construction is the obvious future fix.
- The stale-contact age badge is tick-granular (`tick - last_observed_at.tick`)
  while staleness is callback-granular. A contact gained and lost within one
  tick renders as `T-0` while STALE. Truthful, but potentially confusing.
- `EXPANDED_HELP_LINES` documents `V perspective` but not the `1`–`9` direct
  selectors or the `D`/`F3` debug overlay, and it displaced the previous
  `click inspect/seek` hint.

### 8.6 Cursor performance (measured, not asserted)

Phase 4 large fixture regenerated for this review: 3,000 ticks, 48,000
decisions, 24,000 frames, entrant `A` declaring two processes and issuing a
READ on every callback. Windows, Python 3.13.14, median of repeated runs.

| Operation | Cost |
|---|---:|
| `analyze_perspective` (projection creation) | 2664.563 ms |
| `projection.cursor()` | 0.0020 ms |
| Sequential advance, early (798 accumulated reads) | 0.0154 ms/tick |
| Sequential advance, mid (12,798 reads) | 0.0492 ms/tick |
| Sequential advance, late (23,598 reads) | 0.0630 ms/tick |
| Same-tick cached access | 0.00030 ms |
| Small forward jump (+10 ticks) | 0.1430 ms |
| Large forward seek (first to last) | 28.8809 ms |
| Backward seek (full accumulator reset) | 29.1576 ms |
| **Direct `state_at_tick` fold — the per-frame cost without a cursor** | **30.2015 ms** |
| Warm perspective switch A/B (client path) | 0.00060 ms |
| `PerspectiveManager.__init__`, 2 entrants | 3501 ms |

The 4.1x growth from early to late sequential advance tracks accumulated READ
history and is the direct evidence against the original per-frame constant-time
claim. The cursor is nonetheless clearly justified: 0.063 ms versus 30.2 ms is a
~480x reduction, moving per-frame cost from 181% of a 60fps budget to 0.4% of
it. Because the client pre-builds every entrant's cursor, switching perspective
is effectively free.

### 8.7 Knowledge-boundary evidence from real matches

Rendered through the **real** pygame stack (SDL dummy video driver), not test
doubles:

- **Delayed detection.** At tick 0 the entrant's own anchor is `None` while
  canonical replay places it at 0; no contact appears until a sample actually
  delivers one at tick 1.
- **CURRENT to STALE to CURRENT.** A flyby fixture gains, loses, and regains a
  contact at address 32 across ticks 1–15. Transitions coincide with delivered
  callbacks; no transition is produced by the passage of time alone.
- **Co-location / geometry trap.** Canonical enemy anchors `[32, 40]`; entrant
  `A` renders exactly **one** anonymous contact at `[32]` and never a labelled
  `B` or `C` marker.
- **READ-owner separation.** A delivered READ reports `addr=32 owner=B` at the
  same tick and address as an anonymous contact. The contact carries no owner
  field, and the footer inspector resolves address 32 as `[CURRENT CONTACT]`
  without ever joining the READ owner to it.
- **Simulation isolation.** After exhaustive viewing across all modes with
  forward, backward, seek, restart, and debug-overlay passes, the replay
  SHA-256, trace SHA-256, byte sizes, winner, termination reason, and tick
  count were all unchanged.

### 8.8 What was NOT verified

- **Human visual inspection was not performed.** pygame cannot be imported by
  this checkout's virtualenv: the interpreter is Python 3.13.14 but the
  installed pygame binaries are `cp311`. This is a pre-existing environment
  condition, unrelated to Phase 5, and is why every renderer test uses fakes.
  Real-pygame evidence above was obtained by driving the renderer under the
  system Python 3.11 with the venv's packages on `PYTHONPATH`, headlessly. No
  screenshots were taken and none are claimed.
- **Designer GUI tests did not run.** All 58 are `gui`-marked and deselected by
  `pytest.ini` on this platform; they are covered by the `linux-gui-smoke.yml`
  workflow. The Designer integration was instead verified behaviorally:
  `--trace` is forwarded when a companion trace exists, argv is byte-identical
  to the pre-Phase-5 form when it does not, and a path containing spaces
  survives as a single argv entry with no shell.
- **One environmental test failure was observed and dismissed with evidence.**
  `test_evaluation_history_verification.py::test_verify_summary_passes_for_a_healthy_n4_group_artifact`
  raised `PermissionError` once during a full engine-suite run, then passed
  alone, passed with its whole file, and passed in the authoritative full-suite
  run. The repository root contains `.pytest-cache-v141`, an untracked and
  **un-gitignored** directory whose ACL cannot even be read; it also breaks
  `git status` and `ruff` directory walks. This is the Windows ACL incident
  `pytest.ini` already documents. It is unrelated to Phase 5 and should be
  removed by an account able to take ownership.

### 8.9 Qualification integrity

The commit under qualification was immutable throughout. `HEAD` was
`8984853` before and after the full suite, `git status --short` was empty
before and after, and SHA-256 digests of all nine Phase 5-critical files were
recomputed after the run and were **identical**.

| Suite | Result |
|---|---|
| `client/tests/test_perspective.py` | 9 passed |
| `engine/tests/test_v4_spectator_perspective.py` | 23 passed |
| `client/tests/test_pygame_renderer.py` | 138 passed |
| `client/tests/` | 386 passed, 12 skipped, 2 deselected |
| Phase 1 regression (`test_spectator_analyzer`, `test_spectator_aggregation`) | 39 passed |
| Phase 2 regression (`test_agent_trace`, `test_v4_trace_equivalence`) | 19 passed |
| Phase 3 regression (`test_v4_spectator_derivation`) | 36 passed |
| Phase 4 regression (`test_v4_spectator_perspective`) | 23 passed |
| Replay / runtime / scheduler regression | 77 passed |
| `engine/tests/` | 2332 passed, 14 skipped (1 environmental flake, §8.8) |
| **Full configured repository suite** | **2721 passed, 26 skipped, 2 deselected** |

The full-suite arithmetic reconciles against the original session's reported
2717: the review added three cursor tests and one renderer test, and
2717 + 4 = 2721. Skips and deselections are unchanged.

`ruff check .`, `mypy engine/src/battle_engine` (99 files),
`mypy client/src/battle_client` (13 files), and `git diff --check` are all
clean.
