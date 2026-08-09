# replay_analysis

**Module:** `client/src/battle_client/analysis.py`
**Purpose:** Extract the replay-domain facts `pygame_renderer.py` already
computes as private, renderer-module functions into a small,
renderer-independent module, and migrate the renderer to consume it,
retiring the duplicated private implementations. This is v0.4 Phase 5.

## 0. Provenance and status

An earlier draft of this document (written before Phases 1-4 of the v0.4
"Agent Authoring & Development Feedback Loop" theme, and before Phase
7b's renderer-analysis overlays landed) proposed a greenfield
`ReplayAnalysis` façade class with `MatchSummary`, `AgentLifecycle`,
`agent_state_at`, `events_in_range`, `score_history`/`territory_history`,
and `milestones`. That draft predates the current v0.4 roadmap decision
that replay analysis is supporting architectural work for Phase 5, not a
new feature surface, and predates the three merged Phase 7b commits
(`6386ec1`, `908135f`, `7518163`) that actually built territory/event/
selected-cell analysis — as private functions directly in
`client/src/battle_client/renderers/pygame_renderer.py`, not as a public,
reusable, renderer-independent module. This document replaces that draft
entirely with the design below, reconciled against the renderer
implementation as it exists on `v0.4-foundation` today. None of the old
draft's `MatchSummary`/`AgentLifecycle`/`score_history`/`milestones`
surface is implemented by this phase — see §10 for why.

## 1. Purpose and non-goals

**Purpose.** Give the replay facts the Pygame viewer already derives —
territory ownership, the match's recorded events, and a selected arena
cell's domain state — a single authoritative, headless-importable
implementation in `battle_client.analysis`, and make
`pygame_renderer.py` consume that implementation instead of its own
private copies.

**Non-goals for this phase:**

- Inventing analysis facts the renderer does not already compute. No
  `MatchSummary`, per-agent lifecycle/elimination-cause classification,
  `agent_state_at`, generalized `events_in_range` range queries, score
  history, or match milestones — none of these exist in the current
  renderer, and the audit that scoped this phase explicitly warned
  against turning it back into greenfield analysis work. See §10 for the
  full deferred list.
- A headless CLI, report formatter, or any new public-facing consumer.
  The renderer is this phase's only consumer.
- Any change to replay/result schema, or to how territory/events/cell
  state are *calculated* — this is an extraction of existing, tested
  logic verbatim, not a redesign. If a bug is found during
  characterization, it is reported separately (see §8), not silently
  fixed as part of the move.
- Redesigning the Pygame viewer's behavior, layout, or controls.

## 2. Current renderer implementation inventory

`client/src/battle_client/renderers/pygame_renderer.py` (1163 lines) is
already structured with a clear split between pure, Pygame-free
module-level functions and the stateful `PygameRenderer` class — Pygame
itself is only imported lazily inside `PygameRenderer.run()`, not at
module scope. The module-level functions fall into two groups:

**Domain-analysis-shaped** (facts about the replay, derivable from a
`ReplaySession`/`ReplayState` alone, with no dependency on screen
geometry, click handling, or any renderer-local transient state):

| Function/type | What it computes |
|---|---|
| `territory_summary(state)` | Each entrant's `(owned_cell_count, percentage)` from `state.owners` |
| `TerritoryHistory`, `compute_territory_history(session)` | Every entrant's territory percentage at every recorded tick, via one forward walk that restores the session's cursor afterward |
| `collect_match_events(session)` | Every recorded `(tick, EngineEvent)` pair, in chronological order |
| `events_near_tick(events, tick, window=5)` | Up to `window` most recent events at or before `tick` |
| `SelectedCellInfo`, `selected_cell_info(state, address, ...)` | One arena address's byte value, owner, and (VM-only) occupant |

**Presentation transformation, click geometry, or renderer-local
transient state** (deliberately *not* moved — see §4):

| Function/type | Why it stays |
|---|---|
| `format_event_line` | Human-readable text formatting |
| `resolve_event_click` | Screen-rect click-to-tick mapping |
| `screen_pos_to_address` | Screen-pixel-to-arena-address mapping |
| `format_inspector_lines` | HUD text formatting; also carries a `recently_changed` flag sourced from renderer-local flash state, not from `ReplayState` (see §6) |
| `select_history_window`, `downsample_series`, `territory_graph_points` | Trailing-window selection, point-cap downsampling, and screen-coordinate mapping for the small territory-trend panel — plotting transforms of already-computed history, not new facts |
| `activity_intensity` | Decay curve over the renderer's own `_recent_changes` recency map, which is explicitly viewer-observed/transient state (see its own module-docstring note), not a fact re-derivable headlessly from `ReplaySession` alone |
| `_agent_display_line`, `build_hud_lines` | HUD line assembly/formatting |
| `KeyAction`, `dispatch_key` | Keyboard-to-`PlaybackController` command mapping |
| `PygameRenderer` (the class itself) | Window/surface lifecycle, drawing, click routing, trails/flash/selection bookkeeping — genuine UI/playback state |

`SelectedCellInfo.recently_changed` (§6) is the one field in the
"domain-analysis-shaped" group that is not actually a replay-domain fact:
it is set from `PygameRenderer._flash`, itself populated only by a
genuine ownership change observed on the immediately preceding *linear*
step and cleared on any seek/restart (see `_advance_transient_effects`'s
docstring). It is UI/playback observation history, not something
`ReplaySession` state alone can answer, and is corrected in the
extraction (see §6).

## 3. Extraction boundary

Only the five domain-analysis items in §2's first table move to
`battle_client.analysis`. Everything in the second table remains in
`pygame_renderer.py` — none of it expresses a replay fact independently
of Pygame presentation or renderer-local UI/playback state, so moving it
would not reduce duplication, only relocate presentation code.

This matches the general boundary the task set out:

- **Domain analysis** (moves): territory ownership counts/percentages,
  territory history, event collection/query, selected-cell replay-domain
  state.
- **Presentation transformation** (stays): screen/graph coordinates, text
  formatting, click hit-testing, colors.
- **Playback/UI state** (stays): selected address, flash/trail/activity
  bookkeeping, mouse position, key dispatch, speed, window sizing.

No `MatchSummary`/lifecycle/milestone/score-history extraction happens in
this phase because none of that is proven renderer behavior today — see
§10.

## 4. Chosen API design: pure functions, not a façade class

The old draft's `ReplayAnalysis` class assumed a "construct once, cache
many facts, query later" shape. That shape does not match what actually
exists: the renderer already caches its own two expensive derivations
(`self._match_events`, `self._territory_history`, computed once in
`PygameRenderer.run()`) and does not need a second caching layer wrapping
them. The five extracted items are:

- `territory_summary` and `selected_cell_info`: cheap, stateless,
  per-tick point queries over an already-in-hand `ReplayState` — no
  caching need at all.
- `compute_territory_history` and `collect_match_events`: each already a
  single, self-contained "walk the session once" function, already
  reused as-is by both the renderer's startup precomputation and by
  direct calls elsewhere in the renderer (`build_hud_lines` recomputes
  `collect_match_events` when not given a precomputed list, so it stays
  a plain function callers can invoke however they need).
- `events_near_tick`: a cheap point/range query over an already-collected
  event list.

None of this benefits from being bundled into a stateful object; doing so
would add an abstraction with no current caller who needs it. Per the
task's explicit instruction to choose the smallest architecture that
removes duplication, this phase implements **Option B: pure functions**
(the old draft's §7 called this out as an explicit alternative to the
`ReplayAnalysis` façade) — five functions/dataclasses, each moved
verbatim in behavior from its current renderer implementation, with no
new class, no constructor-time replay walk, and no hidden cache.

## 5. Public API

```python
"""Renderer-independent replay analysis: territory, events, and
selected-cell facts derived from ReplaySession/ReplayState alone.

No Pygame import, directly or indirectly -- battle_client.session is
this module's only battle_client dependency.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Mapping

from battle_engine.replay import EngineEvent
from battle_client.session import ReplaySession, ReplayState


def territory_summary(state: ReplayState) -> dict[str, tuple[int, float]]: ...


@dataclass(frozen=True)
class TerritoryHistory:
    ticks: tuple[int, ...]
    percentages: Mapping[str, tuple[float, ...]]


def compute_territory_history(session: ReplaySession) -> TerritoryHistory: ...


def collect_match_events(session: ReplaySession) -> list[tuple[int, EngineEvent]]: ...


def events_near_tick(
    events: Sequence[tuple[int, EngineEvent]], tick: int, window: int = 5
) -> list[tuple[int, EngineEvent]]: ...


@dataclass(frozen=True)
class SelectedCellInfo:
    address: int
    byte_value: int | None
    owner: str | None
    occupant: str | None


def selected_cell_info(state: ReplayState, address: int) -> SelectedCellInfo | None: ...
```

Every function/dataclass here is moved with **unchanged computation**
from its current `pygame_renderer.py` counterpart (module docstrings
carried over, adapted only to drop renderer-specific framing). The one
deliberate behavior change is `SelectedCellInfo` dropping
`recently_changed` — see §6.

## 6. The `recently_changed` boundary (selected-cell inspection)

The current `SelectedCellInfo.recently_changed` field and
`selected_cell_info(..., recently_changed=...)` parameter are corrected
in this extraction, per §10 of the task's brief ("The analysis layer
should not know about screen coordinates" — and, by the same reasoning,
should not know about renderer-local *temporal* UI bookkeeping either):

- `battle_client.analysis.SelectedCellInfo` carries only genuine
  `ReplayState`-derived facts: `address`, `byte_value`, `owner`,
  `occupant`. `battle_client.analysis.selected_cell_info(state, address)`
  takes no `recently_changed` argument.
- `pygame_renderer.py` keeps `recently_changed` as renderer-local
  presentation state: `format_inspector_lines(info, *, recently_changed:
  bool = False)` gains an explicit keyword parameter (default `False`,
  preserving current output when omitted), and
  `PygameRenderer._draw_hud`/`build_hud_lines` pass it in separately,
  computed the same way as today — `xy in self._flash` — rather than as
  a field baked into the domain dataclass. `build_hud_lines` gains a
  matching `recently_changed: bool = False` keyword parameter that it
  forwards to `format_inspector_lines`.

This is a narrow, deliberate behavior boundary correction, not a
computation change: the HUD's rendered "(recently changed)" text is
identical before and after for every existing scenario, only the field's
owning module changes.

## 7. Cursor preservation and caching contract

- `compute_territory_history(session)` performs one `restart()` +
  repeated `step_forward()` walk and restores the session's cursor to
  its pre-call tick via `session.seek(original_tick)` before returning —
  this is existing, tested behavior
  (`test_compute_territory_history_restores_session_cursor`), carried
  over unchanged.
- `collect_match_events(session)` only reads `session.recorded_ticks` and
  calls `session.events_at_tick(tick)` for each — both non-mutating
  lookups (per `docs/specs/replay_session.md` §14) — so it never touches
  the cursor at all; there is nothing to restore.
- `territory_summary` and `selected_cell_info` take an already-obtained
  `ReplayState` snapshot, not a `ReplaySession`, so cursor mutation does
  not apply to them.
- `events_near_tick` operates on an already-collected list, not a
  session.
- None of these five functions cache anything internally between calls;
  each is a plain function a caller may invoke as often as needed. The
  existing caller-side caching pattern (the renderer computing
  `collect_match_events`/`compute_territory_history` once in `run()` and
  passing the results into functions that accept them, e.g.
  `build_hud_lines(..., match_events=...)`) is preserved exactly as it
  works today — this phase does not add caching inside `analysis.py`
  itself, since the one caller that needs it already handles it.

## 8. Characterization-first migration approach

Every one of the five extracted functions/dataclasses has existing,
passing characterization tests in `client/tests/test_pygame_renderer.py`
today (see that file's `territory_summary`, `compute_territory_history`,
`collect_match_events`/`events_near_tick`, and
`selected_cell_info`/`format_inspector_lines` sections). The migration:

1. Moves each function's implementation verbatim into
   `client/src/battle_client/analysis.py`.
2. Moves its existing characterization tests into a new
   `client/tests/test_analysis.py`, updating only import paths (and, for
   `selected_cell_info`, dropping/adapting the `recently_changed`-specific
   assertions per §6 — those move to renderer-side
   `format_inspector_lines` tests instead, since that is where the
   behavior now lives).
3. Removes the moved implementations from `pygame_renderer.py` and
   replaces every internal call site with an import from
   `battle_client.analysis`.
4. Leaves every other existing renderer test (click handling, HUD
   assembly, transient-effect bookkeeping, key dispatch, geometry
   helpers) in `test_pygame_renderer.py`, updated only where a moved
   dataclass/function is now imported from `battle_client.analysis`
   instead of `battle_client.renderers.pygame_renderer`, or where
   `format_inspector_lines`'s new keyword-only `recently_changed`
   parameter changes a call site.

No behavior is "cleaned up" during the move beyond §6's deliberate,
documented `recently_changed` boundary correction. If characterization
surfaces an existing bug, it is reported in the final Phase 5 report
rather than silently fixed.

## 9. Headless-importability test

`client/tests/test_analysis.py` includes a test proving
`battle_client.analysis` imports with no Pygame dependency, following the
existing pattern in `test_headless_characterization.py`. Since
`pygame_renderer.py` itself already only imports `pygame` lazily inside
`PygameRenderer.run()` (not at module scope), the meaningful assertion is
that `battle_client.analysis` does not import `battle_client.renderers`
(or anything else Pygame-flavored) at all — `sys.modules` is checked for
the absence of `pygame` after importing `battle_client.analysis` fresh in
a subprocess, mirroring how `test_headless_client_processes_replay_
without_pygame` already verifies the CLI's headless path.

## 10. Explicitly deferred (not implemented this phase)

None of the following exist in the current renderer and none are added
by this phase — all are left for a future spec, if a real consumer
justifies them:

- `MatchSummary` (replay-level summary: winner, arena size, tick count,
  etc. as a single queryable object).
- Per-agent `AgentLifecycle` (spawn tick, elimination tick/cause,
  survival) — the renderer has no elimination-cause classification
  today; `KillDeathEvent`/`RuntimeEvent` are shown as HUD text, never
  resolved into a structured "cause" per agent.
- `agent_state_at(agent_id, tick)` — the renderer only ever reads
  `state.agents` off an already-obtained `ReplayState`; there is no
  existing point-query-by-tick helper to extract.
- A general `events_in_range(start_tick, end_tick)` range query — the
  renderer only ever needs "every event" (`collect_match_events`) or
  "recent events near a tick" (`events_near_tick`); a fully general range
  query has no current caller.
- `score_history` — the renderer never tracks or displays score over
  time, only the current tick's `state.score` in the HUD; only
  *territory* history is a proven, implemented feature.
- `milestones` (chronological elimination/match-end narrative) — no
  current renderer feature assembles this.
- A headless CLI or any other new public consumer.

## 11. Completion criteria

- `docs/specs/replay_analysis.md` (this document) committed.
- `client/src/battle_client/analysis.py` exists, has no Pygame
  dependency, and contains the one authoritative implementation of
  `territory_summary`, `TerritoryHistory`/`compute_territory_history`,
  `collect_match_events`, `events_near_tick`, and
  `SelectedCellInfo`/`selected_cell_info`.
- `pygame_renderer.py` imports and uses those five items rather than
  defining its own copies; `format_inspector_lines`/`build_hud_lines`
  carry `recently_changed` as an explicit renderer-side parameter per
  §6.
- `client/tests/test_analysis.py` exists, passes, and includes a
  headless-import test (§9).
- `client/tests/test_pygame_renderer.py` passes with tests
  migrated/updated per §8.
- The Pygame viewer's behavior is unchanged: play/pause/step/seek/
  restart/speed, territory HUD, territory-trend graph, event timeline,
  click-to-seek, selected-cell inspection, agent trails, and window
  resizing all work exactly as before.
- Full `python -m pytest`, `mypy engine/src/battle_engine`, and
  `mypy client/src/battle_client` all pass; Ruff is clean on
  `analysis.py` and any materially modified files.
